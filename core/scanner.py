import os
from PySide6.QtCore import QObject, Signal, QThread
from .database import DatabaseManager
from .deduper import Deduper
from .scanner_state import ScannerContext
from loguru import logger

class ScanWorker(QThread):
    progress = Signal(int, int) # current, total
    file_processed = Signal(str) # path (unused but kept for API compat)
    finished_scan = Signal()
    error_occurred = Signal(str)

    scan_results_ready = Signal(list) 

    def __init__(self, roots, db_path, engine_type='phash', threshold=5):
        super().__init__()
        self.roots = roots
        self.db_path = db_path
        self.engine_type = engine_type
        self.threshold = threshold
        self.db_manager = None
        self.deduper = None
        self.stop_requested = False

    def run(self):
        # Create a thread-local DB manager
        # Create a thread-local DB manager
        self.db_manager = DatabaseManager(self.db_path)
        
        # Create file_repo if not provided (for thread-local DB access)
        if not hasattr(self, 'file_repo') or self.file_repo is None:
            from core.repositories.file_repository import FileRepository
            self.file_repo = FileRepository(self.db_manager)

        self.deduper = Deduper(self.db_manager, self.file_repo)
        
        # Set threshold
        threshold = getattr(self, 'threshold', 5)
        
        # Initialize Engine with threshold
        try:
            self.deduper.set_engine(self.engine_type)
            
            # 1. Discovery
            logger.info("ScanWorker: Starting Discovery...")
            files = []
            for root in self.roots:
                for dirpath, _, filenames in os.walk(root):
                    if self.stop_requested: break
                    for f in filenames:
                        if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')):
                            files.append(os.path.abspath(os.path.join(dirpath, f)))
            
            logger.info(f"ScanWorker: Found {len(files)} files.")
            self.progress.emit(0, len(files))
            
            if self.stop_requested: return

            # 2. Indexing
            logger.info("ScanWorker: Starting Indexing...")
            def on_progress(curr, total):
                if self.stop_requested: return
                self.progress.emit(curr, total)
                
            self.deduper.engine.index_files(files, progress_callback=on_progress)
            
            if self.stop_requested: return

            # 3. Matching
            logger.info("ScanWorker: Starting Matching...")
            results = self.deduper.find_duplicates(
                threshold=threshold,
                roots=self.roots
            )
            
            self.scan_results_ready.emit(results)
            
        except Exception as e:
            logger.error(f"Scan error: {e}")
            self.error_occurred.emit(str(e))
        finally:
            self.finished_scan.emit()
        
        # State Machine usage attempted to be removed/bypassed in previous steps
        # self.context.request_start()
        # But we need event loop for signals? 
        # Actually our State Machine is currently synchronous in `execute` calls for this demo refactor,
        # but `ScannerContext` is designed to be event driven.
        # However, `execute` calls are blocking in the current implementation of `ScannerState`.
        # So `request_start()` will run until finished.
        
        self.db_manager.close()
        
    def on_context_finished(self):
        # Signal already emitted?
        self.finished_scan.emit()

    def stop(self):
        self.stop_requested = True
        if hasattr(self, 'context'):
             self.context.request_stop()
        self.wait()
