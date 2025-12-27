from collections import defaultdict
from loguru import logger
import os
import multiprocessing
import imagehash
from PIL import Image
from PySide6.QtCore import QCoreApplication
from .base import BaseEngine
from ..bktree import BKTree

def calculate_hash(file_path):
    """Worker function to calculate hash."""
    try:
        with Image.open(file_path) as img:
            hash_val = imagehash.phash(img)
            hash_str = str(hash_val)
            stat = os.stat(file_path)
            size = stat.st_size
            mtime = stat.st_mtime
            width, height = img.size
            return file_path, hash_str, size, width, height, mtime, None
    except Exception as e:
        return file_path, None, 0, 0, 0, 0, str(e)

class PHashEngine(BaseEngine):
    def initialize(self):
        pass 

    def index_files(self, files, progress_callback=None):
        """
        Multiprocess hashing of files.
        Checks DB to skip already hashed files equal to mtime.
        """
        if not files: return
        
        # Filter files that need hashing
        tasks = []
        skipped = 0
        total = len(files)
        
        logger.info(f"PHashEngine: Checking {total} files against DB...")
        
        # Batch fetch all existing files from DB (1 query instead of N)
        logger.info("PHashEngine: Fetching existing file records...")
        all_db_files = self.db_manager.get_all_files()
        db_file_map = {row['path']: row for row in all_db_files}
        logger.info(f"PHashEngine: Found {len(db_file_map)} existing records")
        
        for i, path in enumerate(files):
            try:
                stat = os.stat(path)
                mtime = stat.st_mtime
                row = db_file_map.get(path)
                if row and row['last_modified'] == mtime and row['phash']:
                    skipped += 1
                else:
                    tasks.append(path)
            except OSError:
                skipped += 1 # Skip missing/locked
                
            if i % 1000 == 0 and progress_callback:
                progress_callback(i, total)
                
        if progress_callback: progress_callback(total, total)
        logger.info(f"PHashEngine: {skipped} files up-to-date, {len(tasks)} need hashing")
        
        if not tasks:
            logger.info("PHashEngine: All files up to date.")
            return

        logger.info(f"PHashEngine: Hashing {len(tasks)} new files...")
        
        cpu_count = max(1, multiprocessing.cpu_count() - 1)
        count = skipped
        
        # Batch collection for efficient DB writes
        batch_results = []
        batch_size = 1000
        
        # Optimize IPC with larger chunksize
        chunk_size = max(1, len(tasks) // (cpu_count * 4))
        
        with multiprocessing.Pool(processes=cpu_count) as pool:
            for result in pool.imap_unordered(calculate_hash, tasks, chunksize=chunk_size):
                path, hash_val, size, w, h, mtime, err = result
                
                if hash_val is not None:
                    batch_results.append((path, hash_val, size, w, h, mtime))
                    
                    # Flush batch to DB
                    if len(batch_results) >= batch_size:
                        self.db_manager.upsert_files_batch(batch_results)
                        batch_results.clear()
                elif err:
                    logger.error(f"Error hashing {path}: {err}")
                
                count += 1
                if count % 1000 == 0 and progress_callback:
                    progress_callback(count, total)
        
        # Flush remaining
        if batch_results:
            self.db_manager.upsert_files_batch(batch_results)
        
        if progress_callback:
            progress_callback(total, total)

    def find_duplicates(self, files=None, threshold=5, root_paths=None, include_ignored=False, progress_callback=None):
        if files is None:
            if root_paths:
                files = self.db_manager.get_files_in_roots(root_paths)
                logger.info(f"PHashEngine: Loaded {len(files)} files from {len(root_paths)} roots.")
            else:
                files = self.db_manager.get_all_files()
        
        logger.info(f"PHashEngine: Processing {len(files)} files.")

        # Filter by roots
        if root_paths:
            norm_roots = [os.path.normpath(r) for r in root_paths]
            def is_in_roots(f_path):
                norm_path = os.path.normpath(f_path)
                for r in norm_roots:
                    if norm_path == r or norm_path.startswith(r + os.sep):
                        return True
                return False
            files = [f for f in files if is_in_roots(f['path'])]
            logger.info(f"PHashEngine: Filtered to {len(files)} files within roots.")

        # 1. Exact Match Grouping
        buckets = defaultdict(list)
        for f in files:
            if f['phash']: 
                buckets[f['phash']].append(f)

        hash_groups = list(buckets.items())
        
        # 2. Fuzzy Matching with BK-Tree (with caching)
        def hamming(h1, h2):
            val1 = int(h1, 16)
            val2 = int(h2, 16)
            return bin(val1 ^ val2).count('1')

        tree = BKTree(hamming)
        
        # Try to load cached tree
        cache_path = "bktree_cache.pkl"
        cache_valid = False
        if tree.load(cache_path):
            # Validate cache - check if hash count matches
            if tree.size() == len(hash_groups):
                cache_valid = True
                logger.info(f"BKTree cache valid ({tree.size()} hashes)")
            else:
                logger.info(f"BKTree cache stale: {tree.size()} vs {len(hash_groups)} hashes, rebuilding...")
                tree = BKTree(hamming)
        
        if not cache_valid:
            logger.info(f"Building BKTree with {len(hash_groups)} hashes...")
            for h, _ in hash_groups:
                tree.add(h, h)
            tree.save(cache_path)


        # Union-Find
        parent = {h: h for h, _ in hash_groups}
        def find(h):
            if parent[h] != h:
                parent[h] = find(parent[h])
            return parent[h]
        def union(h1, h2):
            root1 = find(h1)
            root2 = find(h2)
            if root1 != root2:
                parent[root1] = root2

        # Query
        total = len(hash_groups)
        log_interval = 1000
        
        found_pairs = []

        for i, (h, _) in enumerate(hash_groups):
            matches = tree.query(h, int(threshold))
            for match_h, dist in matches:
                if dist > 0:
                    # Check if ignored before grouping
                    is_ignored = self.db_manager.is_ignored(h, match_h)
                    
                    if include_ignored or not is_ignored:
                        union(h, match_h)
                    
                    # Store pair for persistence (if not already ignored/handled)
                    # We want to capture it even if ignored, to update distance if needed?
                    # But add_ignored_pairs_batch(overwrite=False) won't update if exists.
                    # That's fine.
                    h1, h2 = sorted((h, match_h))
                    found_pairs.append((h1, h2, 'phash_match', dist))
            
            if i % log_interval == 0:
                logger.info(f"PHash Matching Progress: {i}/{total}")
                if progress_callback:
                    progress_callback(i, total)
                QCoreApplication.processEvents()
        
        
        # Persist found pairs to DB (convert hash-based to ID-based)
        if found_pairs:
            # Build hash->ID mapping
            hash_to_ids = defaultdict(list)
            for f in files:
                if f['phash']:
                    hash_to_ids[f['phash']].append(f['id'])
            
            # Convert hash pairs to ID pairs
            from ..models import FileRelation, RelationType
            id_relations = []
            for h1, h2, rel_type, dist in found_pairs:
                ids1 = hash_to_ids.get(h1, [])
                ids2 = hash_to_ids.get(h2, [])
                
                # Create relations for all combinations of IDs
                for id1 in ids1:
                    for id2 in ids2:
                        if id1 != id2:
                            s1, s2 = sorted((id1, id2))
                            id_relations.append(FileRelation(
                                id1=s1,
                                id2=s2,
                                relation_type=RelationType.NEW_MATCH,
                                distance=float(dist)
                            ))
            
            if id_relations:
                # Remove duplicates
                unique_relations = list({(r.id1, r.id2): r for r in id_relations}.values())
                logger.info(f"PHashEngine: Persisting {len(unique_relations)} ID-based pairs to DB...")
                
                # Use file_repo instead of db_manager
                if self.file_repo:
                    self.file_repo.add_relations_batch(unique_relations, overwrite=False)
                else:
                    logger.warning("PHashEngine: file_repo not available, cannot persist relations")

        # Reconstruct
        groups = defaultdict(list)
        for h, file_list in hash_groups:
            root_h = find(h)
            groups[root_h].extend(file_list)

        final_groups = [g for g in groups.values() if len(g) > 1]
        
        if not include_ignored:
            filtered_groups = []
            for group in final_groups:
                hashes = set(f['phash'] for f in group)
                if len(hashes) == 1:
                    h = list(hashes)[0]
                    if self.db_manager.is_ignored(h, h):
                        continue
                filtered_groups.append(group)
            final_groups = filtered_groups

        final_groups.sort(key=len, reverse=True)
        return final_groups
