from collections import defaultdict
from .database import DatabaseManager
from loguru import logger
from PySide6.QtCore import QCoreApplication
from .bktree import BKTree

class Deduper:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def find_duplicates(self, threshold=5, include_ignored=False, root_paths=None):
        """
        Find duplicate groups using Hamming distance.
        Returns a list of lists: [[dict(file_row), ...], group2, ...]
        """
        files = self.db_manager.get_all_files()
        logger.info(f"Loaded {len(files)} files from database.")
        
        # Filter files by root_paths if provided
        if root_paths:
            import os
            # Normalize roots to ensure correct matching
            norm_roots = [os.path.normpath(r) for r in root_paths]
            
            def is_in_roots(f_path):
                # Simple string startswith might flag 'C:\foo' matches 'C:\foobar', so ensure separator
                # or use os.path.commonpath but that is slow.
                # startswith is usually 'good enough' if we append separator but let's be careful.
                # Actually, if we just use normalized strings and startswith, it covers 99%.
                # For strictness: check if path starts with root + os.sep OR path == root
                norm_path = os.path.normpath(f_path)
                for r in norm_roots:
                    if norm_path == r or norm_path.startswith(r + os.sep):
                        return True
                return False
                
            filtered_files = [f for f in files if is_in_roots(f['path'])]
            logger.info(f"Filtered to {len(filtered_files)} files within scanned roots.")
            files = filtered_files
        # file rows are sqlite3.Row objects
        
        # 1. Exact Match Grouping (Optimization)
        logger.info("Grouping by exact hash...")
        # Group by hash first. This handles distance=0 instantly.
        buckets = defaultdict(list)
        for f in files:
            buckets[f['phash']].append(f)
            
        # 2. Fuzzy Matching
        # We need to compare buckets.
        # If threshold is small, we can compare keys.
        
        # Flattened list of (hash, [files])
        hash_groups = list(buckets.items())
        n = len(hash_groups)
        logger.info(f"Unique hashes to compare: {n}")
        
        # Union-Find (Disjoint Set) to group relevant hashes
        parent = list(range(len(hash_groups)))
        def find(i):
            if parent[i] != i:
                parent[i] = find(parent[i])
            return parent[i]
        
        def union(i, j):
            root_i = find(i)
            root_j = find(j)
            if root_i != root_j:
                parent[root_i] = root_j

        # This defines bit_count for hamming distance
        def hamming(h1, h2):
            # h1 and h2 are hex strings
            val1 = int(h1, 16)
            val2 = int(h2, 16)
            return bin(val1 ^ val2).count('1')

        # Compare hashes using BK-Tree
        logger.info("Building BK-Tree for fuzzy matching...")
        


        tree = BKTree(hamming)
        
        # Add all unique hashes to tree
        for h, _ in hash_groups:
            tree.add(h, h)
            
        logger.info("Querying BK-Tree...")
        
        # Keep track of unions to avoid redundant work?
        # Union-Find is fast enough.
        
        processed = 0
        total_unique = len(hash_groups)
        log_interval = max(1, total_unique // 20)

 

        # Optimization: Map hash to index for fast union
        hash_to_idx = {h[0]: idx for idx, h in enumerate(hash_groups)}
        
        # Re-run loop with direct union
        for i in range(total_unique):
            if i % 10 == 0: QCoreApplication.processEvents()
            if i % log_interval == 0: 
                logger.info(f"Query progress: {i}/{total_unique} ({int(i/total_unique*100)}%)")

            current_hash = hash_groups[i][0]
            neighbors = tree.query(current_hash, threshold)
            
            for matched_hash, dist in neighbors:
                if dist == 0: continue
                
                # If including ignored, we simply group everything within threshold
                # If NOT including ignored, we check the DB
                if include_ignored or not self.db_manager.is_ignored(current_hash, matched_hash):
                    j = hash_to_idx[matched_hash]
                    union(i, j)

        # 3. Collect Results
        # dictionary: root_index -> list of file objects
        results = defaultdict(list)
        for i in range(n):
            root = find(i)
            # Add all files from this hash bucket
            results[root].extend(hash_groups[i][1])
            
        # Filter for groups with > 1 item
        final_groups = [group for group in results.values() if len(group) > 1]
        
        if not include_ignored:
            # Filter out exact match groups that are explicitly ignored in DB (e.g. marked as "Not Duplicate" or "Similar")
            # Fuzzy matches are already filtered during the union step.
            filtered_groups = []
            for group in final_groups:
                # Check uniqueness of hashes
                hashes = set(f['phash'] for f in group)
                if len(hashes) == 1:
                    # Single hash group (Exact matches)
                    h = list(hashes)[0]
                    # Check if this hash pair (h, h) is ignored
                    if self.db_manager.is_ignored(h, h):
                        continue
                filtered_groups.append(group)
            final_groups = filtered_groups

        logger.info(f"Deduplication complete. Found {len(final_groups)} groups of duplicates.")
        return final_groups
