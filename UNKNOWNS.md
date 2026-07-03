## Known Unknowns

- `core/engines/mobilenet.py` — Не прочитан. Предположительно MobileNetV3 embedding engine [MEDIUM]
- `core/engines/clip.py` — Не прочитан. CLIP ViT-B/32 engine [MEDIUM]
- `core/engines/directml_clip.py` — Не прочитан. DirectML variant для Windows [LOW]
- `core/engines/blip.py` — Не прочитан. BLIP caption encoder [MEDIUM]
- `core/engines/gpu_batch_search.py` — Не прочитан. Batch Hamming distance on GPU [MEDIUM]
- `core/repositories/cluster_repository.py` — Не прочитан. Cluster-specific DAL [LOW]
- `core/commands/base.py` — Не прочитан. Command History для undo/redo [LOW]
- `core/vector_db.py` — Не прочитан. ChromaDB optional integration [LOW]
- `core/thumbnail_manager.py` — Не прочитан. Background thumbnail scaling [LOW]
- `core/gpu_config.py` — Не прочитан. GPU detection (CUDA/MPS/CPU) [MEDIUM]
- `core/scanner_state.py` — Не прочитан. ScannerContext state machine [LOW]
- `core/logger.py` — Не прочитан. Qt log handler [LOW]
- `ui/scan_setup.py` — Не прочитан детально. Folder selection + engine config UI [MEDIUM]
- `ui/progress_view.py` — Не прочитан. Scan progress + log view [LOW]
- `ui/cluster_view.py` — Не прочитан. Cluster organizer UI [MEDIUM]
- `ui/settings_dialog.py` — Не прочитан. Settings dialog [LOW]
- `ui/utils.py` — Не прочитан. ThrottledSignal [LOW]
- `tests/` — verify_engines.py, test_repositories, test_commands — не прочитаны [LOW]

## Questions for the User

1. `Deduper.save_relations()` + `add_relations_batch(overwrite=False)` вызывается после каждого `find_duplicates()` — не дублируются ли `NEW_MATCH` записи при повторных сканах?
2. PHash GPU path использует `phash_c1..c4` (MIH) для candidate generation, а CPU path — BKTree. Есть ли синхронизация между двумя кэшами при переключении режимов?
3. `EventBus` — Qt Signals singleton. Почему не используется Signal/Slot от ScanSession напрямую, а дублируется в EventBus?
4. `ScanWorker` создаёт свой thread-local `DatabaseManager`. Есть ли race condition между worker и main thread при записи в SQLite? (WAL mode решает?)
