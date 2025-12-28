# DESIGN_DOC

Context:
- Problem: Slow PHash retrieval and search for large collections (1M+ images).
- Constraints: 
    - Maintain high accuracy while significantly reducing search time.
    - **Backward Compatibility**: Do not break current CPU/BK-Tree implementation.
- Non-goals: Replacing the entire GUI or database structure.

Architecture:
- Components:
    - **PHashEngine**: Orchestrator for both indexing and search.
    - **GPU Hasher**: PyTorch-based module for converting image batches to 64-bit bits on GPU (Resize -> Grayscale -> DCT -> Median Threshold).
    - **MIH Indexer**: CPU/SQLite based pre-filtering.
    - **GPU Refiner**: PyTorch-based exact Hamming distance calculation.
- Data flow: DB (MIH Candidates) -> Torch Tensor (GPU) -> Exact Hamming -> Results.
- External dependencies: PyTorch (existing), `faiss-cpu` (for fast candidate searching if MIH is too slow).

Key Decisions:
- [D1] Accelerate PHash using GPU – Rationale: Both hashing (DCT) and comparison (Hamming) are highly parallelizable.
- [D2] Implement Multi-Index Hashing (MIH) – Rationale: Avoids $O(N^2)$ complexity by splitting 64-bit hashes into four 16-bit buckets.
- [D3] Use PyTorch for GPU Operations – Rationale: Already in project, provides all necessary primitives (Resize, Grayscale, FFT/DCT) and matches existing AI infra.

Interfaces:
- `PHashEngine.find_duplicates`: Main API for search.
- `GPUBatchSearch`: Internal interface for batch processing on GPU.

Assumptions & TODOs:
- Assumptions: GPU with CUDA or DirectML support is available.
- Open questions: Which library provides the best balance of speed and "binary" support for Windows?
- TODOs (with priority):
    - [High] Research FAISS binary index support on Windows.
    - [High] Implement prototype with FAISS or PyTorch.
