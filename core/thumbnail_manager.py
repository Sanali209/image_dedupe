import os
import hashlib
from PIL import Image, ImageOps
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QBrush
from PySide6.QtCore import QObject, Signal, QThread, Qt, QStandardPaths
from loguru import logger

class ThumbnailWorker(QThread):
    finished = Signal(str, QPixmap) # path, pixmap
    
    def __init__(self, path, size, cache_dir):
        super().__init__()
        self.path = path
        self.size = size
        self.cache_dir = cache_dir
        
    def run(self):
        try:
            # Check cache
            if not self.path or not os.path.exists(self.path):
                self.finished.emit(self.path, QPixmap())
                return

            # Hash path for cache filename
            path_hash = hashlib.md5(self.path.encode('utf-8')).hexdigest()
            cache_path = os.path.join(self.cache_dir, f"{path_hash}_{self.size}.png")
            
            if os.path.exists(cache_path):
                # Load from cache
                pix = QPixmap(cache_path)
                if not pix.isNull():
                    self.finished.emit(self.path, pix)
                    return
            
            # Generate
            img = Image.open(self.path).convert('RGBA')
            img = ImageOps.fit(img, (self.size, self.size), Image.Resampling.LANCZOS)
            
            # Save to cache
            img.save(cache_path, "PNG")
            
            # Convert to QPixmap (RGBA is always 4-byte aligned, safe for QImage)
            qim = QImage(img.tobytes("raw", "RGBA"), img.width, img.height, QImage.Format_RGBA8888)
            pix = QPixmap.fromImage(qim)
            self.finished.emit(self.path, pix)
            
        except Exception as e:
            logger.error(f"Thumbnail generation error for {self.path}: {e}")
            self.finished.emit(self.path, QPixmap())

class ThumbnailManager(QObject):
    thumbnail_ready = Signal(str, QPixmap) # path, pixmap
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cache_dir = os.path.join(os.path.expanduser("~"), ".gemini", "thumbnails")
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir, exist_ok=True)
            
        self.mem_cache = {} # path -> QPixmap
        self.workers = {} # path -> key
        
    def get_thumbnail(self, path, size=150):
        if not path: return QPixmap()
        
        key = f"{path}_{size}"
        if key in self.mem_cache:
            return self.mem_cache[key]
            
        # Check disk cache synchronously for immediate return if possible?
        # For smooth scrolling, async is better. But we can check disk quickly.
        path_hash = hashlib.md5(path.encode('utf-8')).hexdigest()
        cache_path = os.path.join(self.cache_dir, f"{path_hash}_{size}.png")
        if os.path.exists(cache_path):
            pix = QPixmap(cache_path)
            if not pix.isNull():
                self.mem_cache[key] = pix
                return pix
        
        # Start async generation
        if key not in self.workers:
            worker = ThumbnailWorker(path, size, self.cache_dir)
            worker.finished.connect(self.on_worker_finished)
            # Pass custom data? no, just use path map
            self.workers[key] = worker
            worker.start()
            
        return QPixmap() # Return empty for now
        
    def on_worker_finished(self, path, pix):
        # We need to recover the size or just store by path if size assumed constant?
        # Let's assume standard size for list, grid size for grid.
        # Worker doesn't pass back size.
        # Find which worker this was
        keys_to_remove = []
        for key, worker in self.workers.items():
            if worker.path == path and worker.isFinished():
                self.mem_cache[key] = pix
                keys_to_remove.append(key)
                self.thumbnail_ready.emit(path, pix)
        
        for k in keys_to_remove:
            self.workers.pop(k, None)

    def generate_grid_preview(self, paths, size=150):
        # Generate a composition synchronously (or cache it too!)
        # Key for grid is hash of sorted paths
        if not paths: return QPixmap()
        
        comp_key = hashlib.md5("".join(sorted(paths)).encode('utf-8')).hexdigest()
        cache_path = os.path.join(self.cache_dir, f"cluster_{comp_key}_{size}.png")
        
        if os.path.exists(cache_path):
            return QPixmap(cache_path)
            
        # Generate
        base = QImage(size, size, QImage.Format_ARGB32)
        base.fill(Qt.transparent)
        painter = QPainter(base)
        
        # Draw up to 4 images
        limit = min(4, len(paths))
        # 1 image: full
        # 2 images: split vertical?
        # 3 images: ?
        # 4 images: 2x2
        
        # Force 2x2 grid logic for 2-4 images
        grid_map = [
            (0, 0, size, size), # 1
            (0, 0, size/2, size), (size/2, 0, size/2, size), # 2 (Vertical split)
            (0, 0, size/2, size/2), (size/2, 0, size/2, size/2), (0, size/2, size, size/2), # 3 (2 top, 1 bot)
            (0, 0, size/2, size/2), (size/2, 0, size/2, size/2), (0, size/2, size/2, size/2), (size/2, size/2, size/2, size/2) # 4
        ]
        
        rects = []
        if limit == 1: rects = [(0, 0, size, size)]
        elif limit == 2: rects = [(0, 0, int(size/2), size), (int(size/2), 0, int(size/2), size)]
        elif limit == 3: rects = [(0, 0, int(size/2), int(size/2)), (int(size/2), 0, int(size/2), int(size/2)), (0, int(size/2), size, int(size/2))]
        elif limit == 4: rects = [(0, 0, int(size/2), int(size/2)), (int(size/2), 0, int(size/2), int(size/2)), (0, int(size/2), int(size/2), int(size/2)), (int(size/2), int(size/2), int(size/2), int(size/2))]
        
        for i, path in enumerate(paths[:limit]):
            try:
                # Load small thumb for composition
                img = Image.open(path).convert('RGBA')
                rect = rects[i]
                w, h = rect[2], rect[3]
                img = ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS)
                
                qim = QImage(img.tobytes("raw", "RGBA"), img.width, img.height, QImage.Format_RGBA8888)
                painter.drawImage(rect[0], rect[1], qim)
            except:
                # fill grey
                painter.fillRect(rect[0], rect[1], rect[2], rect[3], QColor("#333"))
        
        painter.end()
        base.save(cache_path, "PNG")
        return QPixmap.fromImage(base)
