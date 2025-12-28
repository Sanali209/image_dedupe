import torch
import torch_directml
from core.engines.phash import GPUHasher
from PIL import Image
import numpy as np
import os

def test_gpu_hashing():
    print("Testing GPU Hashing...")
    device = torch_directml.device()
    hasher = GPUHasher(device)
    
    # Create dummy images
    img1 = Image.fromarray(np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8))
    img2 = Image.fromarray(np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8))
    
    hashes = hasher.calculate_hashes([img1, img2])
    print(f"Generated hashes: {hashes}")
    assert len(hashes) == 2
    assert len(hashes[0]) == 16
    print("GPU Hashing test passed!")

def test_gpu_search():
    print("\nTesting GPU Search (Hamming Distance)...")
    from core.engines.gpu_batch_search import GPUBatchSearch
    device = torch_directml.device()
    search = GPUBatchSearch(device)
    
    h1 = ["ffffffffffffffff", "0000000000000000"]
    h2 = ["0000000000000000", "0000000000000001"]
    
    dists = search.compute_distances(h1, h2)
    print(f"Distances: {dists}")
    assert dists[0] == 64
    assert dists[1] == 1
    print("GPU Search test passed!")

if __name__ == "__main__":
    try:
        test_gpu_hashing()
        test_gpu_search()
        print("\nAll verification tests passed!")
    except Exception as e:
        print(f"\nVerification failed: {e}")
        import traceback
        traceback.print_exc()
