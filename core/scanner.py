import os
from PySide6.QtCore import QObject, Signal, QThread
from .database import DatabaseManager
from .deduper import Deduper
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
        self.db_manager = DatabaseManager(self.db_path)
        self.deduper = Deduper(self.db_manager)
        
        # Initialize Engine
        try:
            self.deduper.set_engine(self.engine_type)
        except Exception as e:
            logger.error(f"Failed to initialize engine {self.engine_type}: {e}")
            self.finished_scan.emit()
            return
        
        files_to_scan = []
        
        # 1. Discovery Phase
        logger.info("ScanWorker: Discovering files...")
        for root in self.roots:
            for dirpath, _, filenames in os.walk(root):
                if self.stop_requested: break
                for f in filenames:
                    if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')):
                        full_path = os.path.abspath(os.path.join(dirpath, f))
                        files_to_scan.append(full_path)
        
        total_files = len(files_to_scan)
        logger.info(f"ScanWorker: Found {total_files} files.")
        
        if total_files == 0:
            self.finished_scan.emit()
            self.db_manager.close()
            return

        # 2. Indexing Phase (Delegate to Engine)
        if not self.stop_requested:
            # We pass a lambda for progress
            def on_progress(current, total):
                if self.stop_requested: 
                    # Engines should check a flag or we force thread termination (bad)
                    # Engines run in this thread, so we accept they might finish the current batch.
                    pass
                self.progress.emit(current, total)
                
            self.deduper.engine.index_files(files_to_scan, progress_callback=on_progress)
            
            # 3. Matching Phase (Generate and Save Matches)
            if not self.stop_requested:
                 logger.info("ScanWorker: Running match detection...")
                 # We need file objects with paths. The Engine.find_duplicates expects list of files (dicts/rows)
                 # But we only have paths here.
                 # Actually, Deduper.find_duplicates handles this? 
                 # No, Deduper.find_duplicates takes `files`.
                 # We should reload files from DB to ensure format is correct.
                 # We rely on the Engine to load files if None is passed (which Deduper passes)
                 
                 # Optimization: Return results to avoid re-calculation in UI
                 results = self.deduper.find_duplicates(threshold=self.threshold, root_paths=self.roots, progress_callback=on_progress)
                 self.scan_results_ready.emit(results)
                 logger.info("ScanWorker: Match detection complete.")
            
        self.db_manager.close()
        self.finished_scan.emit()

    def stop(self):
        self.stop_requested = True
        self.wait()
