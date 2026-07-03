## Key Abstractions

| Abstraction | File | Role | Usage Count |
|---|---|---|---|
| `DatabaseManager` | `core/database.py:6` | SQLite: 6 tables, WAL, batch upsert, MIH chunks, FK constraints | 1 instance, 30+ methods [HIGH] |
| `AbstractDedupeEngine` | `core/engines/abstract.py:4` | Strategy interface: `index_files()` + `find_duplicates()` | 4 implementations [HIGH] |
| `PHashEngine` | `core/engines/phash.py:105` | GPU DCT hashing + MIH (SQL) + BKTree (CPU fallback) | Primary engine [HIGH] |
| `MobileNetEngine` | `core/engines/mobilenet.py:1` | MobileNetV3 embeddings (576 dim) | Fast AI engine [HIGH] |
| `CLIPEngine` | `core/engines/clip.py:1` | CLIP ViT-B/32 (512 dim) | Semantic matching [HIGH] |
| `BLIPEngine` | `core/engines/blip.py:1` | BLIP caption encoder (768 dim) | Deep semantic [HIGH] |
| `Deduper` | `core/deduper.py:22` | Facade: engine + GraphBuilder + ClusterReconciler | 1 per session [HIGH] |
| `ScanWorker` | `core/scanner.py:8` | QThread: discovery → indexing → matching | 1 per scan [HIGH] |
| `ScanSession` | `core/scan_session.py:4` | SSOT: config, state, signal emission | 1 instance [HIGH] |
| `FileRelation` | `core/models.py:58` | Pydantic: pair + RelationType + distance | 100K+ in DB [HIGH] |
| `File` | `core/models.py:33` | Pydantic: path, phash, file_size, dimensions | 1M+ in DB [HIGH] |
| `BKTree` | `core/bktree.py:11` | In-memory Hamming distance index, pickle cache | 1 instance [HIGH] |
| `GraphBuilder` | `core/cluster_services.py:5` | Adjacency graph + BFS components | 1 per clustering [HIGH] |
| `ClusterReconciler` | `core/cluster_services.py:158` | Sticky clusters merge + orphans | 1 per clustering [HIGH] |
| `FileRepository` | `core/repositories/file_repository.py:14` | DAL: CRUD files + relations with FK validation | 1 instance [HIGH] |
| `EventBus` | `core/event_bus.py:3` | Qt Signals singleton: scan, file, status | 1 instance [MEDIUM] |
| `ServiceContainer` | `core/di.py:3` | Dict-based singleton DI | 4 registrations [MEDIUM] |
| `GPUBatchSearch` | `core/engines/gpu_batch_search.py:1` | Batch Hamming distance on GPU | Used by PHashEngine [MEDIUM] |

**Design patterns in use:**
- **Strategy** — `AbstractDedupeEngine`: 4 engines (pHash, MobileNet, CLIP, BLIP), switchable at runtime [HIGH]
- **Facade** — `Deduper`: simplifies engine + graph + reconciliation [HIGH]
- **Worker Thread** — `ScanWorker(QThread)`: background scan with signals [HIGH]
- **Observer (Qt Signals)** — `ScanSession.config_changed`, `EventBus` singleton, `ComparisonWidget` signals [HIGH]
- **Repository** — `FileRepository` + `ClusterRepository`: DAL with batch FK validation [HIGH]
- **Singleton** — `EventBus._instance`, `ServiceContainer._instances` [MEDIUM]
- **Template Method** — `BaseEngine.__init__` → subclass engines [MEDIUM]
- **Graph Traversal (BFS)** — `GraphBuilder.build_graph_and_find_components()` [MEDIUM]
- **Virtual Proxy** — `QAbstractListModel` + `QListView` for 1M+ pairs virtualized [HIGH]
- **Memento (Command History)** — `core/commands/base.py`: Undo/Redo for actions [LOW]
- **Dual Implementation** — PHash CPU (BKTree) vs GPU (MIH + DCT) [HIGH]
