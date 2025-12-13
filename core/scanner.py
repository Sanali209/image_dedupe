import os
import imagehash
from PIL import Image
import multiprocessing
from PySide6.QtCore import QObject, Signal, QThread
from .database import DatabaseManager
from loguru import logger

def calculate_hash(file_path):
    """Worker function to calculate hash."""
    try:
        # Use simple phash
        with Image.open(file_path) as img:
            # Handle EXIF rotation if necessary, but imagehash might not strictly need it for comparison?
            # Actually, rotation affects hash.
            # For speed, we might skip full exif handling if not critical, but let's be safe.
             # pHash is robust to some scaling/minor edits, but rotation is a major change.
            hash_val = imagehash.phash(img)
            # Store hash as hex string to avoid SQLite integer overflow
            hash_str = str(hash_val)
            
            # Get metadata
            stat = os.stat(file_path)
            size = stat.st_size
            mtime = stat.st_mtime
            width, height = img.size
            
            return file_path, hash_str, size, width, height, mtime, None
    except Exception as e:
        return file_path, None, 0, 0, 0, 0, str(e)

class ScanWorker(QThread):
    progress = Signal(int, int) # current, total
    file_processed = Signal(str) # path
    finished_scan = Signal()
    error_occurred = Signal(str)

    def __init__(self, roots, db_path):
        super().__init__()
        self.roots = roots
        self.db_path = db_path
        self.db_manager = None
        self.stop_requested = False

    def run(self):
        # Create a thread-local DB manager
        self.db_manager = DatabaseManager(self.db_path)
        
        files_to_scan = []
        
        # 1. Discovery Phase
        for root in self.roots:
            for dirpath, _, filenames in os.walk(root):
                if self.stop_requested: break
                for f in filenames:
                    if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')):
                        full_path = os.path.abspath(os.path.join(dirpath, f))
                        files_to_scan.append(full_path)
        
        total_files = len(files_to_scan)
        logger.info(f"Found {total_files} files to check.")
        
        if total_files == 0:
            self.finished_scan.emit()
            return

        # 2. Filter Phase (Check DB)
        # We process in chunks to check DB efficiently? Or just check one by one?
        # A batch query would be better, but for simplicity let's check individually or rely on worker result.
        # Actually better to check DB before spawning worker to save CPU.
        
        # Optimization: Get all known files in a dict {path: (mtime, hash)}
        # This might be heavy for memory if 100k files
        # Let's iterate.
        
        tasks_files = []
        
        processed_count = 0
        
        # Need to know which files need hashing
        for idx, path in enumerate(files_to_scan):
            if self.stop_requested: break
            
            try:
                stat = os.stat(path)
                mtime = stat.st_mtime
                row = self.db_manager.get_file_by_path(path)
                
                if row and row['last_modified'] == mtime and row['phash'] is not None:
                    # Current
                    processed_count += 1
                    self.progress.emit(processed_count, total_files)
                else:
                    # Needs hashing
                    tasks_files.append(path)
            except OSError:
                processed_count += 1 # Skip files we can't stat
        
        # 3. Processing Phase
        if tasks_files:
            logger.info(f"Hashing {len(tasks_files)} new files...")
            # Use fewer than CPU count to keep UI responsive
            cpu_count = max(1, multiprocessing.cpu_count() - 1)
            
            with multiprocessing.Pool(processes=cpu_count) as pool:
                # Use imap_unordered for responsiveness
                for result in pool.imap_unordered(calculate_hash, tasks_files):
                    if self.stop_requested: 
                        pool.terminate()
                        break
                        
                    path, hash_val, size, w, h, mtime, err = result
                    
                    if hash_val is not None:
                        self.db_manager.upsert_file(path, hash_val, size, w, h, mtime)
                    elif err:
                        logger.error(f"Error hashing {path}: {err}")
                    
                    processed_count += 1
                    self.progress.emit(processed_count, total_files)
                    self.file_processed.emit(path)


        self.db_manager.close()
        self.finished_scan.emit()

    def stop(self):
        self.stop_requested = True
        self.wait()
