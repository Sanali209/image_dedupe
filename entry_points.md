## Entry Points

- `main.py:1` — App entry: DI setup → `ServiceContainer.register()` 4 services → `MainWindow(session, file_repo, cluster_repo, db)` → `app.exec()` [HIGH]
  → `core/di.py:3` — `ServiceContainer`: простой dict-based singleton DI [HIGH]
  → `core/database.py:6` — `DatabaseManager`: SQLite init with WAL, 6 tables, indexes [HIGH]

- `core/deduper.py:22` — `Deduper`: facade, `set_engine()` Strategy switch, `find_duplicates()` orchestration [HIGH]
  → `core/engines/abstract.py:4` — `AbstractDedupeEngine`: Strategy interface [HIGH]
  → `core/engines/phash.py:105` — `PHashEngine`: GPU DCT + MIH (SQL chunks) + BKTree fallback [HIGH]
  → `core/engines/mobilenet.py:1` — `MobileNetEngine`: MobileNetV3 embeddings (576 dim) [HIGH]
  → `core/cluster_services.py:5` — `GraphBuilder`: exact hash + DB relations + BFS components [HIGH]
  → `core/cluster_services.py:158` — `ClusterReconciler`: sticky clusters merge [HIGH]

- `core/scanner.py:8` — `ScanWorker(QThread)`: 3-phase pipeline in background thread [HIGH]
  → Discovery: `os.walk()` collect files [HIGH]
  → Indexing: `engine.index_files()` → hash/embedding + DB upsert [HIGH]
  → Matching: `engine.find_duplicates()` → `FileRelation` list [HIGH]

- `core/models.py:33` — `File`: Pydantic model for DB row [HIGH]
  → `core/models.py:58` — `FileRelation`: pair + `RelationType` enum (12 types) [HIGH]
  → `core/models.py:84` — `Cluster`: sticky group [HIGH]

- `core/bktree.py:11` — `BKTree`: in-memory Hamming distance tree, pickle persist [HIGH]
  → `bktree_cache.pkl` — serialized cache on disk [MEDIUM]

- `ui/mainwindow.py:10` — `MainWindow`: QStackedWidget (4 screens), toolbar, menus [HIGH]
  → `ui/scan_setup.py:1` — `ScanSetupWidget`: folder picker + engine selector + threshold [HIGH]
  → `ui/progress_view.py:1` — `ProgressWidget`: scan progress + log view [HIGH]
  → `ui/results_view.py:459` — `ResultsWidget`: virtualized QListView + ComparisonWidget + Visual Diff [HIGH]
  → `ui/cluster_view.py:1` — `ClusterViewWidget`: sticky clusters management [HIGH]

- `core/event_bus.py:3` — `EventBus(QObject)`: singleton Qt Signals (scan_started, file_deleted, status_message) [MEDIUM]

- `core/scan_session.py:4` — `ScanSession(QObject)`: SSOT config: roots, engine, threshold, criteria [HIGH]
