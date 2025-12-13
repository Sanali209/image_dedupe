from PySide6.QtCore import QObject, Signal
from loguru import logger

class LogHandler(QObject):
    log_signal = Signal(str)

    def write(self, message):
        self.log_signal.emit(message.strip())

# Global instance to be used by UI to connect
qt_log_handler = LogHandler()
