from collections import defaultdict
from loguru import logger
import os

class GraphBuilder:
    def __init__(self, db_manager, file_repo=None):
        self.db_manager = db_manager
        self.file_repo = file_repo

    def build_graph_and_find_components(self, files, criteria):
        """
        Builds the adjacency graph and returns connected components.
        """
        file_map = {f['path']: f for f in files}
        # ID map for faster lookups. Safe extraction from sqlite3.Row or dict
        id_map = {}
        for f in files:
            # sqlite3.Row behaves like tuple for 'in' check (checks values), so use key access
            try:
                fid = f['id']
                id_map[fid] = f['path']
            except (IndexError, KeyError):
                pass
        
        all_paths = list(file_map.keys())
        adj = defaultdict(set)
        
        logger.info("GraphBuilder: Starting graph construction...")
        edge_stats = {'hash': 0, 'db': 0, 'ai': 0}

        # 1. Exact Hash Collisions
        if criteria.get('exact_hash', True):
            files_by_hash = defaultdict(list)
            for f in files:
                if f['phash']:
                    files_by_hash[f['phash']].append(f['path'])
            
            for phash, paths in files_by_hash.items():
                if len(paths) > 1:
                    for i in range(len(paths)):
                        for j in range(i + 1, len(paths)):
                            adj[paths[i]].add(paths[j])
                            adj[paths[j]].add(paths[i])
                            edge_stats['hash'] += 1

        # 2. Database Relationships
        negative_edges = set()
        
        # New Logic: Use FileRepository and IDs if available
        if self.file_repo:
            relations = self.file_repo.get_all_relations()
            for rel in relations:
                # Check negative first
                # Handle Enum or string
                r_val = rel.relation_type.value if hasattr(rel.relation_type, 'value') else rel.relation_type
                
                if r_val == 'not_duplicate':
                    if not criteria.get('not_duplicate', False):
                         p1 = id_map.get(rel.id1)
                         p2 = id_map.get(rel.id2)
                         if p1 and p2:
                             negative_edges.add(tuple(sorted((p1, p2))))
                    continue

                # Check configured positive types
                # e.g. criteria['duplicate'], criteria['near_duplicate']
                if criteria.get(r_val, False):
                    p1 = id_map.get(rel.id1)
                    p2 = id_map.get(rel.id2)
                    
                    if p1 and p2:
                        adj[p1].add(p2)
                        adj[p2].add(p1)
                        edge_stats['db'] += 1
                        
        else:
            # Legacy Fallback (Hash-based)
            ignored = self.db_manager.get_all_ignored_pairs()

            for row in ignored:
                h1, h2, reason = row['hash1'], row['hash2'], row['reason']
                if not reason: reason = 'not_duplicate'
                
                # Resolve Identifiers (Hash vs Path)
                set1 = self._resolve_paths(h1, file_map, files)
                set2 = self._resolve_paths(h2, file_map, files)
                
                if not set1 or not set2: continue
                
                if reason == 'not_duplicate':
                    # Treat as negative constraint unless ignored
                    if not criteria.get('not_duplicate', False):
                        for f1 in set1:
                            for f2 in set2:
                                negative_edges.add(tuple(sorted((f1, f2))))
                else:
                    # Positive relationship (e.g. ai_match, similar)
                    should_add = True
                    if not criteria.get(reason, False):
                         should_add = False
                    
                    if should_add:
                        for f1 in set1:
                            for f2 in set2:
                                adj[f1].add(f2)
                                adj[f2].add(f1)
                                edge_stats['db'] += 1
        
        # 3. On-the-fly AI (passed via engine if needed, but usually we persist AI matches first)
        # Deduper handles calling engine.find_duplicates separately or we pass it here.
        # Ideally, Deduper should persist AI matches to DB *before* calling this, 
        # so GraphBuilder only looks at DB 'ai_match' edges.
        # BUT, the original code had an 'on-the-fly' option 'ai_similarity'.
        # We will assume Deduper handles the engine call and passing known edges or we skip on-the-fly here 
        # to keep this pure. 
        # Actually, let's keep it simple: GraphBuilder builds from static data. 
        # If Deduper wants AI, it should run AI, save to DB, then call this.
        # Wait, the original code ran AI inside `find_connected_clusters`.
        # We will remove that dependency. Deduper should run AI -> Save to DB -> Build Graph.
        
        logger.info(f"GraphBuilder Stats: {edge_stats}")
        logger.info(f"Negative Edges: {len(negative_edges)}")

        # 4. Apply Negatives
        for (f1, f2) in negative_edges:
            if f2 in adj[f1]: adj[f1].remove(f2)
            if f1 in adj[f2]: adj[f2].remove(f1)

        # 5. BFS Components
        visited = set()
        components = []
        for start_node in all_paths:
            if start_node in visited: continue
            if start_node not in adj: continue

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
                components.append(component)

        return components

    def _resolve_paths(self, ident, file_map, all_files):
        if ident in file_map: return [ident]
        # Fallback: find by hash (slower linear scan if not indexed, but acceptable for now)
        return [f['path'] for f in all_files if f['phash'] == ident]


class ClusterReconciler:
    def __init__(self, db_manager):
        self.db_manager = db_manager

    def reconcile(self, fresh_components, global_file_map, allowed_roots=None):
        """
        Reconciles fresh graph components with existing DB clusters (Sticky Clusters).
        """
        # 1. Load Existing Cluster Data
        db_members = self.db_manager.get_all_cluster_members() # path -> cluster_id
        
        final_clusters = {} # id -> {'name', 'target_folder', 'files': set(paths)}
        new_clusters_list = [] # list of set(paths)
        
        rows = self.db_manager.get_clusters()
        for r in rows:
            final_clusters[r['id']] = {
                'name': r['name'],
                'target_folder': r['target_folder'],
                'files': set()
            }
            
        processed_paths = set()
        
        # 2. Match Components to Clusters
        for comp_paths_list in fresh_components:
            comp_paths = set(comp_paths_list)
            
            # Find touched clusters
            touched_ids = set()
            for p in comp_paths:
                if p in db_members:
                    touched_ids.add(db_members[p])
            
            if not touched_ids:
                # Totally new
                new_clusters_list.append(comp_paths)
            else:
                # Merge into Primary (Lowest ID)
                primary_id = sorted(list(touched_ids))[0]
                
                if primary_id in final_clusters:
                    # Detect new members that need persisting
                    new_files_for_db = []
                    for p in comp_paths:
                        if p not in db_members or db_members[p] != primary_id:
                            final_clusters[primary_id]['files'].add(p)
                            if p not in db_members:
                                new_files_for_db.append(p)
                    
                    if new_files_for_db:
                         self.db_manager.add_cluster_members(primary_id, new_files_for_db)
                    
                    # Ensure component is added
                    final_clusters[primary_id]['files'].update(comp_paths)
                    
            processed_paths.update(comp_paths)

        # 3. Handle Orphans (Sticky Behavior)
        for path, c_id in db_members.items():
            if path not in processed_paths:
                if c_id in final_clusters:
                     # If file still exists (it's in global_file_map), keep it
                     if path in global_file_map:
                        final_clusters[c_id]['files'].add(path)

        # 4. Format Results
        enriched_results = []
        
        # Existing
        for cid, data in final_clusters.items():
            if not data['files']: continue
            file_objs = [global_file_map[p] for p in data['files'] if p in global_file_map]
            if not file_objs: continue
            
            enriched_results.append({
                'id': cid,
                'name': data['name'],
                'target_folder': data['target_folder'],
                'files': file_objs
            })
            
        # New
        fake_id = -1
        for comp_set in new_clusters_list:
            file_objs = [global_file_map[p] for p in comp_set if p in global_file_map]
            if len(file_objs) < 2: continue
            
            enriched_results.append({
                'id': fake_id,
                'name': f"New Cluster {abs(fake_id)}",
                'target_folder': "",
                'files': file_objs
            })
            fake_id -= 1

        # 5. Root Filtering
        if allowed_roots:
             return self._filter_roots(enriched_results, allowed_roots)
        
        return enriched_results

    def _filter_roots(self, clusters, roots):
        if not roots: return []
        
        filtered = []
        for clust in clusters:
            files = clust['files']
            all_in = True
            for f in files:
                p = os.path.normpath(f['path']).lower()
                matched = False
                for r in roots:
                    r_norm = os.path.normpath(r).lower()
                    if p == r_norm or p.startswith(r_norm + os.sep):
                        matched = True
                        break
                if not matched:
                    all_in = False
                    break
            if all_in:
                filtered.append(clust)
        return filtered
