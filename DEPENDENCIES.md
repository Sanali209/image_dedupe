## Dependency Graph

| Module | Imports From | Externals |
|---|---|---|
| `core/database.py` | — | `sqlite3`, `loguru` |
| `core/models.py` | — | `pydantic`, `os`, `datetime` |
| `core/bktree.py` | — | `loguru`, `pickle` |
| `core/di.py` | — | `loguru` |
| `core/event_bus.py` | — | `PySide6.QtCore` |
| `core/scanner.py` | `core.database`, `core.deduper`, `core.scanner_state` | `PySide6.QtCore`, `loguru` |
| `core/deduper.py` | `core.database`, `core.engines.*`, `core.cluster_services`, `core.models` | `loguru`, `collections` |
| `core/engines/` | `core.database`, `core.bktree`, `core.gpu_config`, `core.models` | `torch`, `torchvision`, `PIL`, `imagehash`, `numpy`, `transformers`, `sentence-transformers`, `multiprocessing` |
| `core/repositories/` | `core.database`, `core.models` | `sqlite3`, `loguru` |
| `core/cluster_services.py` | `core.database`, `core.models` | `loguru`, `collections` |
| `ui/` | `core.*` | `PySide6`, `PIL`, `numpy`, `loguru` |
| `tests/` | `core.*`, `ui.*` | `pytest` |

**Cross-module direct imports (violations):**
- `core/deduper.py` импортирует напрямую конкретные engine-классы (PHashEngine, CLIPEngine, etc.) вместо использования фабрики — нарушение OCP [MEDIUM]
- `ui/results_view.py` импортирует `Deduper` напрямую, создаёт его инстанс — UI знает о бизнес-логике [MEDIUM]
- `core/scanner.py` создаёт `Deduper` внутри QThread — дублирование логики main.py [MEDIUM]
- `core/engines/phash.py` использует `QCoreApplication.processEvents()` — engine зависит от Qt [MEDIUM]

**Cycles:** None detected [HIGH]

**DI Wiring:** `main.py:19-27` — ручное `ServiceContainer.register()` 4 сервисов → constructor injection в `MainWindow` [HIGH]
