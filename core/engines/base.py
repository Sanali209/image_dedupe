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

    def get_batch_embeddings(self, image_paths, batch_size=8):
        """
        Generate embeddings for multiple images in batches.
        Override in subclass for GPU-optimized batch processing.
        
        Default implementation falls back to sequential get_embedding() calls.
        
        Args:
            image_paths: List of image file paths
            batch_size: Number of images to process at once
            
        Returns:
            Dict mapping path -> embedding list
        """
        results = {}
        for path in image_paths:
            emb = self.get_embedding(path)
            if emb:
                results[path] = emb
        return results

    def index_files(self, files, progress_callback=None, batch_size=None):
        """
        Index files using batch embedding extraction for optimal GPU utilization.
        
        Args:
            files: List of file paths to process
            progress_callback: function(current, total)
            batch_size: Number of images to process in each GPU batch (uses config if None)
        """
        if not self.model or not self.vector_db.client or not self.collection_name:
            logger.error(f"{self.engine_name or 'AI'} Engine not ready or configured.")
            return

        # Get batch size from config if not specified
        if batch_size is None:
            from core.gpu_config import GPUConfig
            config = GPUConfig()
            # Map engine name to config key
            engine_key = self.engine_name.lower().replace('-directml', '').replace('v3 (small)', '').strip()
            if 'mobilenet' in engine_key.lower():
                engine_key = 'mobilenet'
            elif 'clip' in engine_key.lower():
                engine_key = 'clip'
            elif 'blip' in engine_key.lower():
                engine_key = 'blip'
            batch_size = config.get_batch_size(engine_key)

        logger.info(f"{self.engine_name}: Indexing {len(files)} files with batch_size={batch_size}...")
        
        # Pre-fetch all DB records to avoid N+1 queries
        logger.info(f"{self.engine_name}: Fetching existing DB records...")
        all_db_files = self.db_manager.get_all_files()
        db_file_map = {row['path']: row for row in all_db_files}
        logger.info(f"{self.engine_name}: Found {len(db_file_map)} existing records")
        
        total = len(files)
        processed = 0
        
        # Process in larger chunks for ChromaDB existence check
        chunk_size = 1000
        
        for chunk_start in range(0, total, chunk_size):
            chunk = files[chunk_start:chunk_start + chunk_size]
            
            # Batch check Chroma for existing embeddings
            try:
                existing_docs = self.vector_db.collections[self.collection_name].get(ids=chunk, include=[])
                existing_ids = set(existing_docs['ids']) if existing_docs else set()
            except Exception as e:
                logger.error(f"Chroma batch check error: {e}")
                existing_ids = set()

            # Identify files that need processing
            paths_to_process = []
            for path in chunk:
                if not os.path.exists(path):
                    processed += 1
                    continue
                    
                if path in existing_ids:
                    # Already has embedding, ensure SQLite record exists
                    if path not in db_file_map:
                        try:
                            with Image.open(path) as img:
                                w, h = img.size
                                stat = os.stat(path)
                                self.db_manager.upsert_file(path, None, stat.st_size, w, h, stat.st_mtime)
                        except:
                            pass
                    processed += 1
                    continue
                
                paths_to_process.append(path)
            
            # Process new files in batches for GPU efficiency
            for batch_start in range(0, len(paths_to_process), batch_size):
                batch_paths = paths_to_process[batch_start:batch_start + batch_size]
                
                # Update SQLite records first
                for path in batch_paths:
                    try:
                        stat = os.stat(path)
                        with Image.open(path) as img:
                            w, h = img.size
                            self.db_manager.upsert_file(path, None, stat.st_size, w, h, stat.st_mtime)
                    except Exception as e:
                        logger.warning(f"Error updating DB for {path}: {e}")
                
                # Batch extract embeddings (GPU-optimized)
                try:
                    batch_embeddings = self.get_batch_embeddings(batch_paths, batch_size=batch_size)
                except Exception as e:
                    logger.warning(f"Batch embedding error: {e}, falling back to sequential")
                    batch_embeddings = {}
                    for p in batch_paths:
                        emb = self.get_embedding(p)
                        if emb:
                            batch_embeddings[p] = emb
                
                # Prepare ChromaDB upsert
                if batch_embeddings:
                    ids = list(batch_embeddings.keys())
                    vecs = list(batch_embeddings.values())
                    metas = [{"engine": self.engine_name} for _ in ids]
                    
                    self.vector_db.upsert(self.collection_name, ids, vecs, metas)
                
                processed += len(batch_paths)
                
                # Progress callback
                if progress_callback:
                    progress_callback(processed, total)
            
            # Handle remaining files in chunk that were skipped
            if progress_callback:
                progress_callback(processed, total)

        logger.info(f"{self.engine_name}: Indexing complete. Processed {processed}/{total} files.")


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
        log_interval = 1000

        found_pairs = []

        # Retrieve all IDs for efficient lookup
        # We need to map path -> ID
        # This is slow if we do it one by one.
        # Ideally we pre-fetch map of all files in roots?
        # Or assume file_repo scan populated them.
        
        # Since we are iterating valid_files (paths), let's build a map
        path_to_id = {}
        
        all_files_in_roots = self.file_repo.get_files_in_roots(root_paths)
        path_to_id = {f['path']: f['id'] for f in all_files_in_roots}
        
        # Batch fetch all embeddings upfront (avoid N+1 queries)
        logger.info(f"{self.engine_name}: Pre-fetching embeddings for {len(valid_files)} files...")
        all_embeddings = self.vector_db.batch_get(self.collection_name, valid_files)
        logger.info(f"{self.engine_name}: Fetched {len(all_embeddings)} embeddings")
        
        for i, path in enumerate(valid_files):
            vec = all_embeddings.get(path)
            if vec is None:
                continue
            
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
            try:
                result = self.file_repo.add_relations_batch(unique_pairs, overwrite=False)
                logger.info(f"{self.engine_name}: Persisted {result.get('added', 0)} relations, skipped {result.get('skipped', 0)}")
                if result.get('skipped', 0) > 0:
                    logger.warning(f"{self.engine_name}: {result['skipped']} relations skipped (invalid file IDs)")
            except Exception as e:
                logger.error(f"{self.engine_name}: Failed to persist relations: {e}")

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
