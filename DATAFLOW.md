## Data Flow: Scan → Dedup → Review (pHash GPU path)

1. `main.py:19` — `DatabaseManager()` → SQLite init: 6 tables, WAL, indexes, MIH chunks [HIGH]
   → `core/database.py:42` — `init_db()`: `CREATE TABLE files (id, path, phash, phash_c1..c4, file_size, width, height, last_modified)` [HIGH]

2. `ui/scan_setup.py:1` — User selects folders + engine type + threshold → `ScanSession.roots`, `ScanSession.engine`, `ScanSession.threshold` [HIGH]
   → Signal `start_scan` → `MainWindow.start_scan_process()` → `ProgressWidget.start_scan()` [HIGH]

3. `core/scanner.py:8` — `ScanWorker.run()`: создаёт thread-local `DatabaseManager` + `Deduper` [HIGH]
   → Phase 1 Discovery: `os.walk(roots)` → список `.png/.jpg/.jpeg/.bmp/.gif/.webp` файлов [HIGH]

4. `core/scanner.py:70` — Phase 2 Indexing: `PHashEngine.index_files(files)` [HIGH]
   → `core/engines/phash.py:115` — Сравнивает mtime с DB → только новые/изменённые [HIGH]
   → GPU: `GPUHasher.calculate_hashes(batch)` → PyTorch DCT → 64-bit phash [HIGH]
   → CPU: `multiprocessing.Pool.imap_unordered(calculate_hash)` → `imagehash.phash()` [HIGH]
   → `DatabaseManager.upsert_files_batch()` → SQLite batch INSERT/UPDATE [HIGH]

5. `core/scanner.py:77` — Phase 3 Matching: `Deduper.find_duplicates(threshold, roots)` [HIGH]
   → `PHashEngine.find_duplicates()` → GPU path [HIGH]

6. `core/engines/phash.py:261` — `_find_duplicates_gpu()` [HIGH]
   → `DatabaseManager.get_phash_candidates()`: SQL self-join on `phash_c1..c4` (MIH) → кандидаты [HIGH]
   → `GPUBatchSearch.compute_distances(hex_hashes)`: GPU batch Hamming distance [HIGH]
   → Фильтр `distance <= threshold` + `is_ignored()` check [HIGH]

7. `core/engines/phash.py:322` — Persistence: `FileRepository.add_relations_batch(matches, overwrite=False)` → `file_relations` table [HIGH]
   → Union-Find grouping → groups → return groups of file dicts [HIGH]

8. `core/scanner.py:84` — `scan_results_ready.emit(results)` → `ResultsWidget.load_results()` [HIGH]
   → `core/repositories/file_repository.py:348` — `get_relations_by_threshold(threshold)` → `FileRelation[]` [HIGH]
   → `PairsModel(QAbstractListModel)`: virtualized list for 1M+ pairs [HIGH]

9. `ui/results_view.py:459` — User reviews pairs in `ComparisonWidget` [HIGH]
   → Annotation: `add_ignored_pair_id(id1, id2, reason)` → `file_relations` UPDATE [HIGH]
   → Diff: `ImageChops.difference()` + autocontrast + magenta highlight [HIGH]

10. `ui/cluster_view.py:1` — Cluster Organizer tab [HIGH]
    → `GraphBuilder.build_graph_and_find_components()`: exact hash + DB relations + BFS [HIGH]
    → `ClusterReconciler.reconcile()`: sticky merge с существующими кластерами [HIGH]

**Events published:** `scan_started`, `scan_finished`, `scan_progress(current, total)`, `config_changed`, `file_deleted(path)` [HIGH]

**Causality trace:** User Setup → ScanWorker(QThread) → Discovery → Indexing → Matching → Relations DB → UI Virtualized List → User Review → Sticky Clusters [HIGH]

**Data model:** `files (SQLite)` → `file_relations (SQLite)` → `clusters + cluster_members (SQLite)` [HIGH]
