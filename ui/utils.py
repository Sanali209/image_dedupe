import time
from PySide6.QtCore import QObject, Signal

class ThrottledSignal(QObject):
    """
    Limits the rate at which a signal is emitted.
    Useful for high-frequency progress updates.
    """
    emitted = Signal(int, int)

    def __init__(self, interval_ms=50):
        super().__init__()
        self.interval = interval_ms / 1000.0
        self.last_emit_time = 0
        self.last_val = 0
        self.last_total = 0

    def emit(self, val, total):
        self.last_val = val
        self.last_total = total
        now = time.time()
        if now - self.last_emit_time >= self.interval:
            self.emitted.emit(val, total)
            self.last_emit_time = now

    def flush(self):
        """Ensure final values are emitted."""
        self.emitted.emit(self.last_val, self.last_total)
        self.last_emit_time = time.time()
