import os
from collections import defaultdict
from .database import DatabaseManager
from loguru import logger
from .engines.phash import PHashEngine
from .engines.clip import CLIPEngine
from .engines.blip import BLIPEngine
from .engines.mobilenet import MobileNetEngine

class Deduper:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.engine = PHashEngine(db_manager)
        
    def set_engine(self, engine_type):
        if engine_type == 'phash':
            self.engine = PHashEngine(self.db_manager)
        elif engine_type == 'clip':
            self.engine = CLIPEngine(self.db_manager)
        elif engine_type == 'blip':
            self.engine = BLIPEngine(self.db_manager)
        elif engine_type == 'mobilenet':
            self.engine = MobileNetEngine(self.db_manager)
        else:
            logger.warning(f"Unknown engine type: {engine_type}, defaulting to pHash")
            self.engine = PHashEngine(self.db_manager)
            
        self.engine.initialize()

    def find_duplicates(self, threshold=5, include_ignored=False, root_paths=None, progress_callback=None):
        """
        Find duplicate groups using the active engine.
        Returns a list of lists: [[dict(file_row), ...], group2, ...]
        """
        groups = self.engine.find_duplicates(
            files=None, 
            threshold=threshold, 
            root_paths=root_paths, 
            include_ignored=include_ignored,
            progress_callback=progress_callback
        )
        
        # Persist AI matches if it's an AI engine
        is_ai = isinstance(self.engine, (CLIPEngine, BLIPEngine, MobileNetEngine))
        if is_ai and groups:
            self.save_ai_matches(groups)
            
        return groups

    def save_ai_matches(self, groups):
        """
        Persist AI-found groups to DB as 'ai_match' pairs.
        Optimization: Uses Star Topology (Hub-and-Spoke) instead of Full Mesh.
        Connects group[0] to all other members. Reduces edges from N*(N-1)/2 to N-1.
        """
        if not groups: return

        logger.info(f"Persisting AI matches for {len(groups)} groups...")
        
        count = 0
        pairs = []
        for group in groups:
            # group is list of file rows (sqlite3.Row)
            ids = []
            for f in group:
                val = f['phash'] if f['phash'] else f['path']
                if val: ids.append(val)
            
            ids = sorted(list(set(ids))) # Unique identifiers
            if len(ids) < 2: continue
            
            # Star Topology: Connect first (hub) to all others
            hub = ids[0]
            for i in range(1, len(ids)):
                pairs.append((hub, ids[i], 'ai_match'))
                count += 1
        
        if pairs:
            # Do NOT overwrite existing classifications
            self.db_manager.add_ignored_pairs_batch(pairs, overwrite=False)
        
        if count > 0:
            logger.info(f"Persisted {count} AI match pairs to database (Optimized).")

    def find_connected_clusters(self, criteria):
        """
        Build connected clusters based on a unified graph approach.
        Nodes: File Paths
        Edges: Created by pHash collisions, AI engine matches, or manual 'Similar' marks.
        """
        # Use optimized method if roots are provided in criteria (or we can inject them)
        # We'll check if 'roots' key exists in criteria
        if 'roots' in criteria and criteria['roots']:
             files = self.db_manager.get_files_in_roots(criteria['roots'])
             logger.info(f"ProcessClusters: Loaded {len(files)} files from roots.")
        else:
             files = self.db_manager.get_all_files()
        file_map = {f['path']: f for f in files}
        
        # 1. Build Adjacency Graph
        logger.info("ProcessClusters: Starting logic...")
        logger.info(f"ProcessClusters: Loaded {len(files)} files.")
        adj = defaultdict(set)
        edge_counts = {'hash': 0, 'db': 0, 'ai': 0}
        
        # Source A: Exact Hash Collisions
        if criteria.get('exact_hash', True):
            files_by_hash = defaultdict(list)
            for f in files:
                if f['phash']:
                    files_by_hash[f['phash']].append(f['path'])
            
            for phash, paths in files_by_hash.items():
                if len(paths) > 1:
                    # Connect all-to-all (or star)
                    for i in range(len(paths)):
                        for j in range(i + 1, len(paths)):
                            adj[paths[i]].add(paths[j])
                            adj[paths[j]].add(paths[i])
                            edge_counts['hash'] += 1
                            
        # Source B: Database Relationships (The "ignored_pairs" table)
        # Treated equally: 'ai_match', 'similar', 'similar_crop', etc.
        ignored = self.db_manager.get_all_ignored_pairs()
        negative_edges = set()
        
        db_edges_count = 0
        for row in ignored:
            h1, h2, reason = row['hash1'], row['hash2'], row['reason']
            if not reason: reason = 'not_duplicate'
            
            # Resolve Identifiers (Hash vs Path)
            # Try as exact paths first (for MobileNet/No-Hash files)
            p1, p2 = h1, h2
            
            # Use a helper to resolve "identifier" to "paths"
            # To be robust: Check if identifier matches a file path. If yes, use it.
            # Else, assume it's a hash and look up files with that hash.
            
            def resolve_paths(ident):
                if ident in file_map: return [ident]
                return [f['path'] for f in files if f['phash'] == ident]

            set1 = resolve_paths(h1)
            set2 = resolve_paths(h2)
            
            if not set1 or not set2: continue
            
            if reason == 'not_duplicate':
                if criteria.get('not_duplicate', False):
                     pass 
                else:
                    for f1 in set1:
                        for f2 in set2:
                            negative_edges.add(tuple(sorted((f1, f2))))
            else:
                should_add = True
                if not criteria.get(reason, False):
                     should_add = False
                
                if should_add:
                    for f1 in set1:
                        for f2 in set2:
                            adj[f1].add(f2)
                            adj[f2].add(f1)
                            db_edges_count += 1
                            
        edge_counts['db'] = db_edges_count

        # Source C: On-the-fly AI
        if criteria.get('ai_similarity', False):
             thresh = criteria.get('ai_threshold', 0.1)
             ai_groups = self.engine.find_duplicates(files=files, threshold=thresh)
             for group in ai_groups:
                paths = [f['path'] for f in group]
                for i in range(len(paths)):
                    for j in range(i + 1, len(paths)):
                        adj[paths[i]].add(paths[j])
                        adj[paths[j]].add(paths[i])
                        edge_counts['ai'] += 1
                        
        logger.info(f"Graph Sources - Hash Edges: {edge_counts['hash']}, DB Edges: {edge_counts['db']}, AI Edges: {edge_counts['ai']}")
        logger.info(f"Negative Edges Found: {len(negative_edges)}")
                        
        # 4. Apply Negatives (Remove Edges)
        for (f1, f2) in negative_edges:
            if f2 in adj[f1]: adj[f1].remove(f2)
            if f1 in adj[f2]: adj[f2].remove(f1)
            
        # 5. BFS Components
        visited = set()
        clusters = []
        all_paths = list(file_map.keys())
        for start_node in all_paths:
            if start_node in visited: continue
            
            if start_node not in adj: 
                continue

            component = []
            queue = [start_node]
            visited.add(start_node)
            while queue:
                node = queue.pop(0)
                component.append(node)
                for neighbor in adj[node]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            
            if len(component) > 1:
                clusters.append(component)
                
        # 4. Result Formatting
        result = []
        for clust in clusters:
            result.append([file_map[p] for p in clust])
            
        logger.info(f"Connected Clusters found: {len(result)}")
        return result

    def process_clusters(self, criteria):
        """
        Orchestrate Cluster Persistence:
        1. Find fresh clusters via Graph.
        2. Reconcile with DB (Anchor & Expand).
        3. Return list of dicts: {'id': int, 'name': str, 'folder': str, 'files': [file_dicts]}
        """
        # 1. Fresh Detection (Graph Components)
        # Graph nodes are sqlite3.Row objects, we need paths (strings)
        # Scan scanned_paths to enforce strict scoping if desired/implied
        # But 'criteria' usually comes from UI. 
        # We can fetch scanned_paths and add to criteria if not present?
        # The user intent "onli for selected folders" implies we should use scanned_paths.
        
        scanned_roots = self.db_manager.get_scanned_paths()
        if scanned_roots:
            criteria['roots'] = scanned_roots

        raw_components = self.find_connected_clusters(criteria)
        fresh_components = []
        for comp in raw_components:
            paths_set = set()
            for item in comp:
                # Handle both Row objects and strings just in case
                if isinstance(item, str):
                    paths_set.add(item)
                else:
                    # Assume dict-like/Row
                    paths_set.add(item['path'])
            fresh_components.append(paths_set)

        logger.info(f"ProcessClusters: Graph analysis found {len(fresh_components)} components (converted to paths).")
        
        # 2. Load Existing Clusters (The "Sticky" ones)
        # We need a map: path -> cluster_id
        db_members = self.db_manager.get_all_cluster_members() # dict: path -> cluster_id
        
        # 3. Reconciliation
        # We want to form a final list of clusters.
        
        final_clusters = {} # id -> {'name': str, 'target_folder': str, 'files': set(paths)}
        new_clusters_list = [] # list of set(paths)
        
        # Pre-load existing cluster metadata
        rows = self.db_manager.get_clusters()
        for r in rows:
            final_clusters[r['id']] = {
                'name': r['name'],
                'target_folder': r['target_folder'],
                'files': set()
            }
            
        file_map = {f['path']: f for f in self.db_manager.get_all_files()}
        processed_paths = set()
        
        for comp_paths in fresh_components:
            # Find which clusters this component touches
            touched_ids = set()
            for p in comp_paths:
                if p in db_members:
                    touched_ids.add(db_members[p])
            
            if not touched_ids:
                # Totally new cluster
                new_clusters_list.append(set(comp_paths))
            else:
                # Touches existing cluster(s).
                # Strategy: Merge into the lowest ID (primary).
                if not touched_ids: continue
                primary_id = sorted(list(touched_ids))[0]
                
                # Add all paths to this Primary Cluster
                if primary_id in final_clusters:
                    # Check for new files to persist
                    new_files_for_db = []
                    for p in comp_paths:
                        if p not in db_members or db_members[p] != primary_id:
                            # It's a new file (or moved from other cluster)
                            final_clusters[primary_id]['files'].add(p)
                            if p not in db_members: # Only persist if completely new to clustering?
                                new_files_for_db.append(p)
                                
                    if new_files_for_db:
                        logger.info(f"Auto-adding {len(new_files_for_db)} new matches to Cluster {primary_id}")
                        self.db_manager.add_cluster_members(primary_id, new_files_for_db)
                        
                    # Also ensure we add the already-known members of this component
                    final_clusters[primary_id]['files'].update(comp_paths)
                
            processed_paths.update(comp_paths)

        # 4. Handle "Orphaned" DB Members
        # If a file is in DB Cluster X, but no longer connected in Graph (e.g. AI Match unchecked)?
        # User said "persist changes". So manual added files stay.
        for path, c_id in db_members.items():
            if path not in processed_paths:
                if c_id in final_clusters:
                    final_clusters[c_id]['files'].add(path)

        # 5. Format Output
        enriched_results = []
        
        # Existing Clusters
        for cid, data in final_clusters.items():
            if not data['files']: continue
            
            file_objs = []
            for p in data['files']:
                if p in file_map: file_objs.append(file_map[p])
            
            if not file_objs: continue
            
            enriched_results.append({
                'id': cid, # Real DB ID
                'name': data['name'],
                'target_folder': data['target_folder'],
                'files': file_objs
            })
            
        logger.info(f"ProcessClusters: {len(new_clusters_list)} new cluster candidates.")
        
        fake_id_counter = -1
        for comp_set in new_clusters_list:
            file_objs = []
            for p in comp_set:
                if p in file_map: 
                    file_objs.append(file_map[p])
                else:
                    logger.warning(f"File path not found in file_map: {p}")
            
            if len(file_objs) < 2: 
                logger.warning(f"Skipping candidate cluster, valid files: {len(file_objs)}/{len(comp_set)}")
                continue 
            
            enriched_results.append({
                'id': fake_id_counter, # Negative ID = Unsaved
                'name': f"New Cluster {abs(fake_id_counter)}",
                'target_folder': "",
                'files': file_objs
            })
            fake_id_counter -= 1
            
        logger.info(f"Returning {len(enriched_results)} clusters (Saved + New).")
        
        # 6. Apply Strict Folder Filtering
        # "find clasters onli with images contains in selected folders no load sticy clasters if eny image not contains in selected folders"
        
        # Get currently valid roots from DB (or passed in?)
        # Ideally passed in criteria, but for now we trust the DB 'scanned_paths' as the source of truth for "selected folders"
        allowed_roots = self.db_manager.get_scanned_paths()
        
        if not allowed_roots:
            # If no folders selected, return nothing (strict interpretation)
            logger.info("Strict Filtering: No allowed roots found. Returning empty list.")
            return []
            
        def is_within_roots(path, roots):
            # Normalize for comparison
            p = os.path.normpath(path).lower()
            for r in roots:
                r_norm = os.path.normpath(r).lower()
                # Check if p starts with r
                # Add sep to ensure we don't match C:\Folder2 against C:\Folder
                if p.startswith(r_norm + os.sep) or p == r_norm:
                    return True
            return False
            
        filtered_results = []
        for clust in enriched_results:
            files = clust['files']
            # Check if ALL files in this cluster are within allowed_roots
            all_in = True
            for f in files:
                if not is_within_roots(f['path'], allowed_roots):
                    all_in = False
                    break
            
            if all_in:
                filtered_results.append(clust)
        
        logger.info(f"Strict Filtering: {len(enriched_results)} -> {len(filtered_results)} clusters.")
        return filtered_results
