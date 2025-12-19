import abc
import os
from loguru import logger
from PIL import Image
from ..vector_db import VectorStore
from .abstract import AbstractDedupeEngine

class BaseEngine(AbstractDedupeEngine):
    def __init__(self, db_manager, file_repo=None):
        self.db_manager = db_manager
        self.file_repo = file_repo

    @abc.abstractmethod
    def initialize(self):
        """Load models or prepare resources."""
        pass

    @abc.abstractmethod
    def index_files(self, files, progress_callback=None):
        """
        Process files to generate hashes/vectors.
        Args:
            files: List of file paths to process.
            progress_callback: function(current, total)
        """
        pass

    @abc.abstractmethod
    def find_duplicates(self, files, threshold=5, root_paths=None, include_ignored=False, progress_callback=None):
        """
        Find duplicate groups.
        Args:
            files: List of file dictionaries (or None to fetch from DB)
            threshold: Similarity threshold (int for pHash, float for AI)
            root_paths: Optional list of roots to filter scan
            include_ignored: Whether to include pairs marked as ignored
            progress_callback: function(current, total)
        Returns:
            List of groups (list of file dicts).
        """
        pass

class BaseAIEngine(BaseEngine):
    """
    Base class for AI-based engines (BLIP, CLIP, MobileNet) to reduce duplication.
    """
    def __init__(self, db_manager, file_repo=None):
        super().__init__(db_manager, file_repo)
        self.model = None
        self.vector_db = VectorStore()
        self.collection_name = None  # Must be set by subclass (e.g. 'blip_embeddings')
        self.engine_name = None      # Must be set by subclass (e.g. 'blip')

    @abc.abstractmethod
    def load_model(self):
        """Load the specific model backend."""
        pass

    @abc.abstractmethod
    def get_embedding(self, image_path):
        """
        Generate embedding for a single image. 
        Returns a list of floats.
        Should handle loading image + preprocessing.
        """
        pass

    def initialize(self):
        self.load_model()

    def index_files(self, files, progress_callback=None):
        if not self.model or not self.vector_db.client or not self.collection_name:
            logger.error(f"{self.engine_name or 'AI'} Engine not ready or configured.")
            return

        logger.info(f"{self.engine_name}: Indexing {len(files)} files...")
        
        updates_ids = []
        updates_vecs = []
        updates_metas = []
        
        count = 0
        total = len(files)
        
        chunk_size = 1000
        for i in range(0, total, chunk_size):
            chunk = files[i:i+chunk_size]
            
            # Batch check Chroma for existing
            try:
                existing_docs = self.vector_db.collections[self.collection_name].get(ids=chunk, include=[])
                existing_ids = set(existing_docs['ids']) if existing_docs else set()
            except Exception as e:
                logger.error(f"Chroma batch check error: {e}")
                existing_ids = set()

            for path in chunk:
                if not os.path.exists(path): 
                    count += 1
                    if progress_callback: progress_callback(count, total)
                    continue
                
                # Check ChromaDB
                if path in existing_ids:
                    # Ensure in SQLite if missing
                    # We do this to ensure the file table is populated even if vector exists
                    row = self.db_manager.get_file_by_path(path)
                    if not row:
                         try:
                            with Image.open(path) as img:
                                img = img.convert('RGB')
                                w, h = img.size
                                stat = os.stat(path)
                                self.db_manager.upsert_file(path, None, stat.st_size, w, h, stat.st_mtime)
                         except: pass
                         
                    count += 1
                    if progress_callback: progress_callback(count, total)
                    continue
                
                # Process New File
                try:
                    # Update SQLite first
                    stat = os.stat(path)
                    # We might open image twice (here and in get_embedding), but get_embedding usually needs specific preprocessing
                    # so we'll leave it to get_embedding or just open here for metadata.
                    # Optimization: create a helper to get metadata without full read if possible, but Image.open is lazy.
                    with Image.open(path) as img:
                        w, h = img.size
                        self.db_manager.upsert_file(path, None, stat.st_size, w, h, stat.st_mtime)
                    
                    emb = self.get_embedding(path)
                    
                    if emb:
                        updates_ids.append(path)
                        updates_vecs.append(emb)
                        updates_metas.append({"engine": self.engine_name})
                    
                except Exception as e:
                    logger.warning(f"Error processing {path}: {e}")
                
                count += 1
                if progress_callback: progress_callback(count, total)
                
                if len(updates_ids) >= 50:
                    self.vector_db.upsert(self.collection_name, updates_ids, updates_vecs, updates_metas)
                    updates_ids, updates_vecs, updates_metas = [], [], []
                
            # Flush remaining in chunk loop if needed? No, logic above handles 50 batch. 
            # But we need to handle leftovers at end of outer loop.
            pass

        if updates_ids:
            self.vector_db.upsert(self.collection_name, updates_ids, updates_vecs, updates_metas)


    def find_duplicates(self, files=None, threshold=0.1, root_paths=None, include_ignored=False, progress_callback=None):
        if not self.model or not self.vector_db.client or not self.collection_name:
            return []

        if files is None:
            if root_paths:
                files = self.db_manager.get_files_in_roots(root_paths)
            else:
                files = self.db_manager.get_all_files()

        if root_paths:
            norm_roots = [os.path.normpath(r) for r in root_paths]
            files = [f for f in files if any(os.path.normpath(f['path']).startswith(r) for r in norm_roots)]
        
        valid_files = [f['path'] for f in files]
        # Create a quick lookup for pHashes to check ignored pairs
        path_to_hash = {f['path']: f['phash'] for f in files}
        
        logger.info(f"{self.engine_name}: Querying matches for {len(valid_files)} files...")
        
        parent = {p: p for p in valid_files}
        def find(p):
            if parent[p] != p:
                parent[p] = find(parent[p])
            return parent[p]
        def union(p1, p2):
            r1 = find(p1)
            r2 = find(p2)
            if r1 != r2:
                parent[r1] = r2

        total = len(valid_files)
        log_interval = max(1, total // 20)

        found_pairs = []

        # Retrieve all IDs for efficient lookup
        # We need to map path -> ID
        # This is slow if we do it one by one.
        # Ideally we pre-fetch map of all files in roots?
        # Or assume file_repo scan populated them.
        
        # Since we are iterating valid_files (paths), let's build a map
        path_to_id = {}
        # TODO: Improve this N+1 query performance later or batch fetch
        # For now, let's fetch ID for the current batch or just use slow lookup?
        # Actually, valid_files matches 'roots'.
        # Let's fetch all IDs in roots once.
        
        all_files_in_roots = self.file_repo.get_files_in_roots(root_paths)
        path_to_id = {f['path']: f['id'] for f in all_files_in_roots}
        
        for i, path in enumerate(valid_files):
            data = self.vector_db.collections[self.collection_name].get(ids=[path], include=['embeddings'])
            if not data or data['embeddings'] is None or len(data['embeddings']) == 0: continue
            
            vec = data['embeddings'][0]
            
            results = self.vector_db.query(self.collection_name, query_embeddings=[vec], n_results=20)
            
            if not results: continue
            
            ids = results['ids'][0]
            dists = results['distances'][0]
            
            left_id = path_to_id.get(path)
            if not left_id: continue 

            for match_path, dist in zip(ids, dists):
                if match_path == path: continue
                
                right_id = path_to_id.get(match_path)
                if not right_id: continue
                
                # Check threshold
                if dist <= float(threshold):
                    
                    # Use Pydantic Model
                    from core.models import FileRelation, RelationType
                    
                    # Store pair
                    rel = FileRelation(
                        id1=left_id,
                        id2=right_id,
                        relation_type=RelationType.NEW_MATCH,
                        distance=float(dist)
                    )
                    found_pairs.append(rel)
                
                    if include_ignored:
                        if match_path in parent:
                            union(path, match_path)
                    else:
                        if self.db_manager.is_ignored(left_id, right_id):
                            continue
                        
                        if match_path in parent:
                            union(path, match_path)
                
            if i % log_interval == 0:
                logger.info(f"{self.engine_name} Matching Progress: {i}/{total}")
                if progress_callback: progress_callback(i, total)

        # Persist found pairs
        if found_pairs:
             # Efficiently: unique-ify the list using a dict keyed by IDs
            unique_map = {}
            for r in found_pairs:
                key = (r.id1, r.id2)
                if key not in unique_map:
                    unique_map[key] = r
            
            unique_pairs = list(unique_map.values())
            logger.info(f"{self.engine_name}: Persisting {len(unique_pairs)} match pairs to DB...")
            self.file_repo.add_relations_batch(unique_pairs, overwrite=False)

        from collections import defaultdict
        groups = defaultdict(list)
        path_map = {f['path']: f for f in files}
        
        for path in valid_files:
            root = find(path)
            if path in path_map:
                groups[root].append(path_map[path])
                
        final_groups = [g for g in groups.values() if len(g) > 1]
        final_groups.sort(key=len, reverse=True)
        return final_groups
