"""
Deduper Module.

Orchestrates the duplicate detection process by coordinating:
1.  Engines (Comparison Logic) - e.g., PHash, CLIP.
2.  Database (Persistence) - Storing results.
3.  Cluster Services (Graph Logic) - Grouping related files.
"""
import os
from collections import defaultdict
from typing import List, Optional, Any, Dict, Union, Callable

from loguru import logger
from .database import DatabaseManager
from .engines.phash import PHashEngine
from .engines.directml_clip import DirectMLCLIPEngine as CLIPEngine
from .engines.blip import BLIPEngine
from .engines.mobilenet import MobileNetEngine
from .cluster_services import GraphBuilder, ClusterReconciler
from core.models import FileRelation, RelationType

class Deduper:
    """
    Main entry point for duplicate detection and clustering.
    Facade that simplifies interaction with underlying engines and services.
    """
    def __init__(self, db_manager: DatabaseManager, file_repo: Optional[Any] = None):
        self.db_manager = db_manager
        # Allow injection, fallback to db_manager.file_repo if older code (though that fails)
        # Ideally we require it.
        self.file_repo = file_repo
        
        self.engine = PHashEngine(db_manager, self.file_repo)
        self.graph_builder = GraphBuilder(db_manager, self.file_repo)
        self.reconciler = ClusterReconciler(db_manager)
        
    def set_engine(self, engine_type: str) -> None:
        """Switch the active comparison engine."""
        if engine_type == 'phash':
            self.engine = PHashEngine(self.db_manager, self.file_repo)
        elif engine_type == 'clip':
            self.engine = CLIPEngine(self.db_manager, self.file_repo)
        elif engine_type == 'blip':
            self.engine = BLIPEngine(self.db_manager, self.file_repo)
        elif engine_type == 'mobilenet':
            self.engine = MobileNetEngine(self.db_manager, self.file_repo)
        else:
            logger.warning(f"Unknown engine type: {engine_type}, defaulting to pHash")
            self.engine = PHashEngine(self.db_manager, self.file_repo)
            
        self.engine.initialize()

    def find_duplicates(self, threshold: float = 5, include_ignored: bool = False, 
                       roots: Optional[List[str]] = None, 
                       progress_callback: Optional[Callable] = None) -> List[FileRelation]:
        """
        Execute duplicate detection using the active engine.
        
        Args:
            threshold: Similarity threshold (distance).
            include_ignored: Whether to include previously ignored pairs.
            roots: List of root directories to scan (None = all).
            progress_callback: Function to report progress.
            
        Returns:
            List of FileRelation objects representing matches.
        """
        if roots is None: roots = []
        
        # Engine execution
        results = self.engine.find_duplicates(
            files=None, 
            threshold=threshold, 
            root_paths=roots, 
            include_ignored=include_ignored,
            progress_callback=progress_callback
        )
        
        final_relations: List[FileRelation] = []
        
        # Normalize Output to List[FileRelation]
        if isinstance(results, list):
             if not results: return []
             
             first = results[0]
             if isinstance(first, FileRelation):
                 final_relations = results
             elif isinstance(first, list) or isinstance(first, set):
                 # Legacy Group Handling (Convert Groups to Relations)
                 import itertools
                 import sqlite3
                 
                 def get_id(item):
                     """Helper to extract ID from dict, Row, or Object."""
                     if isinstance(item, (dict, sqlite3.Row)):
                         return item['id']
                     return getattr(item, 'id', None)

                 for group in results:
                     if len(group) < 2: continue
                     # Generate full mesh of relations for the group
                     for left, right in itertools.combinations(group, 2):
                         id1 = get_id(left)
                         id2 = get_id(right)
                         
                         if id1 is None or id2 is None:
                             logger.warning(f"Could not extract IDs from group items: {left}, {right}")
                             continue
                         
                         rel = FileRelation(
                             id1=id1,
                             id2=id2,
                             relation_type=RelationType.NEW_MATCH,
                             distance=0.0 
                         )
                         final_relations.append(rel)
        
        
        # Persist all found 'new_match' relations (overwrite=False protects existing)
        self.save_relations(final_relations)
        
        # Reconcile memory objects with DB state to reflect user decisions
        # This fixes the issue where pairs reappear as 'New Match' after scan even if annotated
        reconciled = []
        for rel in final_relations:
            # Check DB for actual status
            # We can use file_repo to get relation (or verify via db_manager)
            # Efficiently we should have bulk fetched, but loop is okay for typical result counts
            # or we assume 'is_ignored' check logic
            
            # Using low-level check
            # If DB has a specific relation, we prefer that over "NEW_MATCH"
            existing_type = self.db_manager.get_ignore_reason(rel.id1, rel.id2)
            
            if existing_type:
                # Update the object to match DB
                try:
                    rel.relation_type = RelationType(existing_type)
                except:
                    pass
            
            # Filter if needed
            if not include_ignored:
                # If handled (non-new_match), skip
                # Note: 'new_match' is considered 'pending' (visible)
                if rel.relation_type != RelationType.NEW_MATCH:
                    continue
            
            reconciled.append(rel)
        
        final_relations = reconciled
            
        return final_relations

    def save_relations(self, relations: List[FileRelation]) -> None:
        """
        Persist relations to DB.
        
        Args:
            relations: List of FileRelation objects.
        """
        if not relations: return
        
        if not self.file_repo:
             logger.error("Deduper.save_relations: file_repo is not initialized.")
             return

        logger.info(f"Persisting {len(relations)} relations to database...")
        self.file_repo.add_relations_batch(relations, overwrite=False)
        
    # Legacy alias
    save_ai_matches = save_relations

    def process_clusters(self, criteria: Dict[str, Any]) -> List[Any]:
        """
        Orchestrate Cluster Persistence via Services.
        
        Args:
            criteria: Dictionary of clustering options (roots, threshold, etc).
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
             logger.info("Running On-The-Fly AI for clustering...")
             thresh = criteria.get('ai_threshold', 0.1)
             self.find_duplicates(threshold=thresh, roots=criteria.get('roots'))
        
        # 3. Build Graph
        # GraphBuilder picks up edges from DB
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

