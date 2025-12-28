# Project Roadmap

This roadmap outlines the planned optimizations for the image deduplication system, focusing on 1M+ file performance.

## Phase 1: Search Acceleration (Current)
- [ ] Research and integrate external GPU acceleration library (FAISS, etc.).
- [ ] Implement batch-based PHash matching.
- [ ] Optimize database retrieval for search candidates.

## Phase 2: Indexing and Storage
- [ ] Implement persistent vector index for CLIP/BLIP.
- [ ] Add support for Multi-Index Hashing (MIH) in SQLite.

## Phase 3: UI and Experience
- [ ] Progressive UI updates for very large result sets.
- [ ] Advanced clustering visualization.

## Completed
- [x] BK-Tree integration for fuzzy matching.
- [x] Memory-efficient file loading from DB.
- [x] Multiprocessing hash calculation.
