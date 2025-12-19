from PySide6.QtCore import QObject, Signal

class EventBus(QObject):
    """
    Central Event Bus for application-wide signals.
    Singleton pattern.
    """
    _instance = None

    # Define signals here
    scan_started = Signal()
    scan_finished = Signal()
    scan_progress = Signal(int, int) # current, total
    
    file_deleted = Signal(str) # path
    
    # Generic message
    status_message = Signal(str)

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EventBus, cls).__new__(cls)
        return cls._instance

# Global Accessor
bus = EventBus()
