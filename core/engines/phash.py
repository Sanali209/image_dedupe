import torch
import torch.nn.functional as F
from torchvision import transforms
from .base import BaseEngine
from ..bktree import BKTree
from ..gpu_config import get_device
from .gpu_batch_search import GPUBatchSearch
import os
import multiprocessing
import imagehash
from loguru import logger
from collections import defaultdict
from PIL import Image, ImageFile
from PySide6.QtCore import QCoreApplication

# Allow loading of truncated images to prevent crashing on slightly corrupt files
ImageFile.LOAD_TRUNCATED_IMAGES = True

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

class GPUHasher:
    """GPU-accelerated PHash (DCT) calculation using PyTorch."""
    def __init__(self, device):
        self.device = device
        self.size = 32
        self.hash_size = 8
        self.transform = transforms.Compose([
            transforms.Resize((self.size, self.size)),
            transforms.Grayscale(),
            transforms.ToTensor(),
        ])
        
        # Precompute DCT matrix for 32x32
        self.dct_matrix = self._get_dct_matrix(self.size).to(self.device)

    def _get_dct_matrix(self, n):
        """Standard DCT-II matrix."""
        import numpy as np
        matrix = np.zeros((n, n))
        for k in range(n):
            for i in range(n):
                matrix[k, i] = np.cos(np.pi * k * (2 * i + 1) / (2 * n))
        matrix[0, :] *= np.sqrt(1 / n)
        matrix[1:, :] *= np.sqrt(2 / n)
        return torch.from_numpy(matrix).float()

    def calculate_hashes(self, image_batch):
        """
        Process a batch of PIL images on GPU.
        Returns: List of hex hash strings.
        """
        if not image_batch:
            return []
            
        # 1. Transform batch to tensor [B, 1, 32, 32]
        tensors = []
        for img in image_batch:
            tensors.append(self.transform(img))
        x = torch.stack(tensors).to(self.device)
        
        # 2. Apply 2D DCT: Y = C * X * C^T
        # x is [B, 1, 32, 32]
        # We want to multiply each 32x32 slice by dct_matrix and dct_matrix.T
        y = torch.matmul(torch.matmul(self.dct_matrix, x), self.dct_matrix.t())
        
        # 3. Extract top-left 8x8 (excluding DC component if desired? 
        # imagehash.phash includes DC but it usually doesn't matter much)
        # imagehash takes [:hash_size, :hash_size]
        dct_low = y[:, 0, :self.hash_size, :self.hash_size]
        
        # 4. Compare to median
        # Flatten [B, 64]
        dct_flat = dct_low.reshape(-1, self.hash_size * self.hash_size)
        
        # Using sort to find median is more robust than torch.median across backends
        sorted_dct, _ = torch.sort(dct_flat, dim=1)
        # For hash_size=8 (64 bits), median is around index 31-32
        medians = sorted_dct[:, 31:32]
        bits = (dct_flat > medians).int()
        
        # 5. Convert bits to hex strings
        hex_hashes = []
        for i in range(bits.shape[0]):
            b = bits[i].cpu().numpy()
            # Convert bit array to hex
            val = 0
            for bit in b:
                val = (val << 1) | int(bit)
            hex_hashes.append(f"{val:016x}")
            
        return hex_hashes

class PHashEngine(BaseEngine):
    def initialize(self):
        self.device = get_device()
        self.use_gpu = str(self.device) != 'cpu'
        if self.use_gpu:
            logger.info(f"PHashEngine: Initializing GPUHasher on {self.device}")
            self.gpu_hasher = GPUHasher(self.device)
        else:
            self.gpu_hasher = None

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

        if self.use_gpu:
            self._index_files_gpu(tasks, total, skipped, progress_callback)
        else:
            self._index_files_cpu(tasks, total, skipped, progress_callback)

    def _index_files_gpu(self, tasks, total_count, skipped_count, progress_callback):
        """Batch processing images on GPU."""
        from core.gpu_config import GPUConfig
        config = GPUConfig()
        batch_size = config.get_batch_size('phash') or 32
        
        count = skipped_count
        batch_tasks = []
        batch_images = []
        
        total_tasks = len(tasks)
        for i, path in enumerate(tasks):
            try:
                # Use a context manager to ensure the file is closed if loading fails
                with Image.open(path) as img:
                    # We must load the image into memory (convert to RGB/Grayscale) 
                    # before closing the file handle, or passing it to the batch.
                    # Since transforms.ToTensor() will be called later, 
                    # we should at least ensure it's loaded.
                    img.load() 
                    batch_tasks.append(path)
                    batch_images.append(img.copy()) # Copy to keep in memory
            except Exception as e:
                logger.warning(f"Could not load {path}: {e}")
                count += 1
                continue

            if len(batch_images) >= batch_size or i == total_tasks - 1:
                if not batch_images:
                    continue
                try:
                    hashes = self.gpu_hasher.calculate_hashes(batch_images)
                    
                    db_batch = []
                    for p, h, img_obj in zip(batch_tasks, hashes, batch_images):
                        try:
                            stat = os.stat(p)
                            w, h_dim = img_obj.size
                            db_batch.append((p, h, stat.st_size, w, h_dim, stat.st_mtime))
                        except Exception as e:
                            logger.error(f"Error processing {p} after hashing: {e}")
                        finally:
                            img_obj.close()
                    
                    if db_batch:
                        self.db_manager.upsert_files_batch(db_batch)
                        count += len(db_batch)
                except Exception as e:
                    logger.error(f"GPU Hashing batch error: {e}")
                    # If the whole batch fails (e.g. VRAM), we might want to skip or retry
                    # For now, we move on to keep the process alive
                    # Fallback for this batch? 
                    # For now just log and continue
                
                batch_tasks.clear()
                batch_images.clear()
                
                if progress_callback:
                    progress_callback(count, total_count)
                QCoreApplication.processEvents()

    def _index_files_cpu(self, tasks, total_count, skipped_count, progress_callback):
        """Legacy multiprocessing CPU hashing."""
        cpu_count = max(1, multiprocessing.cpu_count() - 1)
        count = skipped_count
        batch_results = []
        batch_size = 1000
        chunk_size = max(1, len(tasks) // (cpu_count * 4))
        
        with multiprocessing.Pool(processes=cpu_count) as pool:
            for result in pool.imap_unordered(calculate_hash, tasks, chunksize=chunk_size):
                path, hash_val, size, w, h, mtime, err = result
                if hash_val is not None:
                    batch_results.append((path, hash_val, size, w, h, mtime))
                    if len(batch_results) >= batch_size:
                        self.db_manager.upsert_files_batch(batch_results)
                        batch_results.clear()
                elif err:
                    logger.error(f"Error hashing {path}: {err}")
                
                count += 1
                if count % 1000 == 0 and progress_callback:
                    progress_callback(count, total_count)
                    QCoreApplication.processEvents()
        
        if batch_results:
            self.db_manager.upsert_files_batch(batch_results)
        
        if progress_callback:
            progress_callback(total_count, total_count)

    def find_duplicates(self, files=None, threshold=5, root_paths=None, include_ignored=False, progress_callback=None):
        if self.use_gpu:
            return self._find_duplicates_gpu(threshold, root_paths, include_ignored, progress_callback)
        else:
            return self._find_duplicates_cpu(files, threshold, root_paths, include_ignored, progress_callback)

    def _find_duplicates_gpu(self, threshold=5, root_paths=None, include_ignored=False, progress_callback=None):
        """Accelerated search using MIH + GPU Refinement."""
        logger.info("PHashEngine: Using GPU-accelerated MIH search")
        
        # 1. Fetch MIH Candidates from DB
        logger.info("PHashEngine: Fetching candidates using MIH...")
        candidates = self.db_manager.get_phash_candidates()
        logger.info(f"PHashEngine: Found {len(candidates)} potential pairs")
        
        if not candidates:
            return []
            
        # 2. GPU Verification
        gpu_search = GPUBatchSearch(self.device)
        total = len(candidates)
        batch_size = 50000 # Large batches for Hamming distance are fine
        
        found_matches = []
        
        for i in range(0, total, batch_size):
            batch = candidates[i:i+batch_size]
            h1_list = [c[2] for c in batch]
            h2_list = [c[3] for c in batch]
            
            dists = gpu_search.compute_distances(h1_list, h2_list)
            
            for (cid1, cid2, ph1, ph2), dist in zip(batch, dists):
                if dist <= threshold:
                    # Check ignored if needed
                    # Note: candidates are ID-based (cid1, cid2)
                    if not include_ignored:
                        if self.db_manager.is_ignored(cid1, cid2):
                            continue
                            
                    from ..models import FileRelation, RelationType
                    found_matches.append(FileRelation(
                        id1=min(cid1, cid2),
                        id2=max(cid1, cid2),
                        relation_type=RelationType.NEW_MATCH,
                        distance=float(dist)
                    ))
            
            if progress_callback:
                progress_callback(i, total)
            QCoreApplication.processEvents()
            
        # 3. Persistence and Grouping
        if found_matches:
            logger.info(f"PHashEngine: Found {len(found_matches)} confirmed matches. Saving...")
            self.file_repo.add_relations_batch(found_matches, overwrite=False)
            
        # Union-Find for grouping
        # We need the full file dicts for final output
        # Fetching only necessary ones might be better, but get_all_files is simple
        all_files = self.db_manager.get_all_files()
        id_to_file = {f['id']: f for f in all_files}
        
        parent = {f['id']: f['id'] for f in all_files}
        def find(i):
            if parent[i] != i:
                parent[i] = find(parent[i])
            return parent[i]
        def union(i1, i2):
            r1 = find(i1)
            r2 = find(i2)
            if r1 != r2:
                parent[r1] = r2

        for rel in found_matches:
            union(rel.id1, rel.id2)
            
        groups = defaultdict(list)
        for fid in id_to_file:
            root = find(fid)
            groups[root].append(id_to_file[fid])
            
        final_groups = [g for g in groups.values() if len(g) > 1]
        final_groups.sort(key=len, reverse=True)
        return final_groups

    def _find_duplicates_cpu(self, files=None, threshold=5, root_paths=None, include_ignored=False, progress_callback=None):
        """Legacy CPU search logic (BK-Tree)."""
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
