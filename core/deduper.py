import os
from collections import defaultdict
from .database import DatabaseManager
from loguru import logger
from .engines.phash import PHashEngine
from .engines.clip import CLIPEngine
from .engines.blip import BLIPEngine
from .engines.mobilenet import MobileNetEngine
from .cluster_services import GraphBuilder, ClusterReconciler

class Deduper:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.engine = PHashEngine(db_manager)
        self.graph_builder = GraphBuilder(db_manager)
        self.reconciler = ClusterReconciler(db_manager)
        
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

    def process_clusters(self, criteria):
        """
        Orchestrate Cluster Persistence via Services.
        """
        # 1. Prepare Data
        scanned_roots = self.db_manager.get_scanned_paths()
        if scanned_roots:
            # Enforce scoping if folders are selected
            criteria['roots'] = scanned_roots
        
        # Load files (scoped if possible)
        if 'roots' in criteria:
             files = self.db_manager.get_files_in_roots(criteria['roots'])
        else:
             files = self.db_manager.get_all_files()
             
        # 2. Run On-The-Fly AI if requested (Pre-processing step)
        if criteria.get('ai_similarity', False):
             # We should run AI and save matches first
             # This essentially calls find_duplicates and save_ai_matches
             logger.info("Running On-The-Fly AI for clustering...")
             thresh = criteria.get('ai_threshold', 0.1)
             # Note: find_duplicates automatically calls save_ai_matches if it's an AI engine
             self.find_duplicates(threshold=thresh, root_paths=criteria.get('roots'))
        
        # 3. Build Graph
        # Note: GraphBuilder logic was slightly simplified regarding on-the-fly 'ai_similarity'.
        # By calling find_duplicates above, we persisted the edges to DB.
        # Now GraphBuilder will pick them up from DB (edge_stats['db']).
        
        fresh_components = self.graph_builder.build_graph_and_find_components(files, criteria)
        
        # 4. Reconcile
        global_file_map = {f['path']: f for f in files}
        final_results = self.reconciler.reconcile(
            fresh_components, 
            global_file_map, 
            allowed_roots=scanned_roots
        )
        
        logger.info(f"Deduper: Returning {len(final_results)} clusters.")
        return final_results

