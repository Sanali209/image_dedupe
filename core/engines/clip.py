from loguru import logger
import os
from PIL import Image
from .base import BaseEngine
from ..vector_db import VectorStore

class CLIPEngine(BaseEngine):
    def __init__(self, db_manager):
        super().__init__(db_manager)
        self.model = None
        self.vector_db = VectorStore()
        
    def initialize(self):
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer('clip-ViT-B-32')
            logger.info("CLIP Model loaded successfully.")
        except ImportError:
            logger.error("sentence-transformers not installed. CLIP engine unavailable.")
        except Exception as e:
            logger.error(f"Failed to load CLIP model: {e}")

    def index_files(self, files, progress_callback=None):
        if not self.model or not self.vector_db.client:
            logger.error("CLIP Engine not ready.")
            return

        logger.info(f"CLIP: Indexing {len(files)} files...")
        
        updates_ids = []
        updates_vecs = []
        updates_metas = []
        
        count = 0
        total = len(files)
        
        chunk_size = 1000
        for i in range(0, total, chunk_size):
            chunk = files[i:i+chunk_size]
            
            # Batch check Chroma for existing
            # We must verify if paths exist in Chroma
            try:
                # Chroma get ids
                # It might throw error if list is empty? No.
                existing_docs = self.vector_db.collections['clip_embeddings'].get(ids=chunk, include=[])
                existing_ids = set(existing_docs['ids']) if existing_docs else set()
            except Exception as e:
                logger.error(f"Chroma batch check error: {e}")
                existing_ids = set()

            for path in chunk:
                # 1. Skip if missing file
                if not os.path.exists(path):
                    count += 1
                    if progress_callback: progress_callback(count, total)
                    continue

                # 2. Check if already indexed
                if path in existing_ids:
                    # Check SQLite only if missing
                    row = self.db_manager.get_file_by_path(path)
                    if not row:
                         try:
                            # Must open for dims :(
                            with Image.open(path) as img:
                                img = img.convert('RGB')
                                w, h = img.size
                                stat = os.stat(path)
                                self.db_manager.upsert_file(path, None, stat.st_size, w, h, stat.st_mtime)
                         except: pass

                    count += 1
                    if progress_callback: progress_callback(count, total)
                    continue
                
                # 3. New File -> Index
                try:
                    stat = os.stat(path)
                    img = Image.open(path).convert('RGB')
                    w, h = img.size
                    self.db_manager.upsert_file(path, None, stat.st_size, w, h, stat.st_mtime)
                    
                    emb = self.model.encode(img).tolist()
                    updates_ids.append(path)
                    updates_vecs.append(emb)
                    updates_metas.append({"engine": "clip"})
                    
                except Exception as e:
                    logger.warning(f"Error processing {path}: {e}")
                    
                count += 1
                if progress_callback: progress_callback(count, total)
                
                if len(updates_ids) >= 50:
                    self.vector_db.upsert('clip_embeddings', updates_ids, updates_vecs, updates_metas)
                    updates_ids, updates_vecs, updates_metas = [], [], []

        if updates_ids:
            self.vector_db.upsert('clip_embeddings', updates_ids, updates_vecs, updates_metas)


    def find_duplicates(self, files=None, threshold=0.1, root_paths=None, include_ignored=False, progress_callback=None):
        if not self.model or not self.vector_db.client:
            return []

        if files is None:
            if root_paths:
                files = self.db_manager.get_files_in_roots(root_paths)
            else:
                files = self.db_manager.get_all_files()

        # Filter roots
        if root_paths:
            norm_roots = [os.path.normpath(r) for r in root_paths]
            files = [f for f in files if any(os.path.normpath(f['path']).startswith(r) for r in norm_roots)]
        
        valid_files = [f['path'] for f in files]
        # Create a quick lookup for pHashes to check ignored pairs
        # files is a list of dicts (Rows)
        path_to_hash = {f['path']: f['phash'] for f in files}
        
        logger.info(f"CLIP: Querying matches for {len(valid_files)} files...")
        
        # Build Groups (Union-Find)
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

        for i, path in enumerate(valid_files):
            # Fetch embedding
            data = self.vector_db.collections['clip_embeddings'].get(ids=[path], include=['embeddings'])
            if not data or data['embeddings'] is None or len(data['embeddings']) == 0: continue
            
            vec = data['embeddings'][0]
            
            # Query
            results = self.vector_db.query('clip_embeddings', query_embeddings=[vec], n_results=20)
            
            if not results: continue
            
            ids = results['ids'][0]
            dists = results['distances'][0]
            
            for match_path, dist in zip(ids, dists):
                if match_path == path: continue
                # dist is Cosine Distance
                if dist <= float(threshold):
                     # Check ignored
                    if include_ignored:
                        if match_path in parent:
                            union(path, match_path)
                    else:
                        # Check ignored status using pHashes or Paths (fallback)
                        h1 = path_to_hash.get(path)
                        h2 = path_to_hash.get(match_path)
                        
                        id1 = h1 if h1 else path
                        id2 = h2 if h2 else match_path
                        
                        if self.db_manager.is_ignored(id1, id2):
                            continue
                        
                        if match_path in parent:
                            union(path, match_path)
                    
            if i % log_interval == 0:
                logger.info(f"CLIP Matching Progress: {i}/{total}")
                if progress_callback: progress_callback(i, total)

        # Reconstruct
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
