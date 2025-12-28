import torch
from loguru import logger

class GPUBatchSearch:
    """GPU-accelerated Hamming distance calculations using PyTorch."""
    def __init__(self, device):
        self.device = device
        # Precompute popcount lookup table for 256 values
        import numpy as np
        lut = [bin(i).count('1') for i in range(256)]
        self.popcount_lut = torch.tensor(lut, dtype=torch.uint8, device=self.device)
        logger.info(f"GPUBatchSearch: Initialized on {self.device}")

    def compute_distances(self, hashes1, hashes2):
        """
        Compute Hamming distances between pairs of 64-bit hashes.
        Refactored to use byte-level XOR to avoid bitwise shift warnings on DML.
        """
        if not hashes1:
            return []

        # Convert each hash to 8 bytes on CPU (fast for candidate batches)
        def hash_to_bytes(h):
            val = int(h, 16) if isinstance(h, str) else h
            # Extract 8 bytes (little-endian order)
            return [(val >> (i * 8)) & 0xFF for i in range(8)]

        # Shapes: [N, 8]
        b1 = torch.tensor([hash_to_bytes(h) for h in hashes1], dtype=torch.uint8, device=self.device)
        b2 = torch.tensor([hash_to_bytes(h) for h in hashes2], dtype=torch.uint8, device=self.device)

        # Byte-level XOR: [N, 8]
        xor_bytes = b1 ^ b2
        
        # Popcount using LUT: [N, 8]
        # to(torch.long) is needed for indexing the LUT
        byte_counts = self.popcount_lut[xor_bytes.to(torch.long)]
        
        # Sum counts across the 8 bytes: [N]
        dists = byte_counts.to(torch.int32).sum(dim=1)
            
        return dists.cpu().tolist()

    def find_matches_batch(self, query_hashes, target_hashes, threshold=5):
        """
        Find all matches within threshold between two sets of hashes.
        query_hashes: [N]
        target_hashes: [M]
        
        Returns: List of tuples (query_idx, target_idx, distance)
        """
        # This is O(N*M) - only use for candidates!
        # For 1M hashes, this is 10^12, too big even for GPU.
        # That's why we use MIH first.
        
        q = torch.tensor([int(h, 16) for h in query_hashes], dtype=torch.int64, device=self.device)
        t = torch.tensor([int(h, 16) for h in target_hashes], dtype=torch.int64, device=self.device)
        
        # For small-ish batches (e.g. 1000 x 100000), we can use broadcasting
        # q: [N, 1], t: [1, M]
        # xor: [N, M]
        # This can eat memory! 1000 * 100000 * 8 bytes = 0.8GB. OK.
        
        # ... logic for broadcasted search ...
        pass
