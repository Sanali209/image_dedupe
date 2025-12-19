from abc import ABC, abstractmethod
from loguru import logger
from PySide6.QtCore import QObject, Signal

class ScannerContext(QObject):
    state_changed = Signal(str)
    progress_updated = Signal(int, int) # current, total
    finished = Signal()
    error_occurred = Signal(str)
    results_ready = Signal(object) # Can be list of groups

    def __init__(self, engine, roots, db_manager, threshold=5, file_repo=None):
        super().__init__()
        self.engine = engine
        self.roots = roots
        self.db = db_manager
        self.threshold = threshold
        self.file_repo = file_repo
        self._state = None
        self.should_stop = False
        
        # Clear old AI matches before starting new scan
        if self.file_repo:
            self.file_repo.clear_ai_matches()
        
        # Initial State
        self.transition_to(IdleState())

    def transition_to(self, state):
        logger.info(f"Scanner Transition: {type(self._state).__name__ if self._state else 'None'} -> {type(state).__name__}")
        self._state = state
        self._state.context = self
        self.state_changed.emit(type(state).__name__)

    def request_start(self):
        self._state.handle_start()

    def request_stop(self):
        self.should_stop = True
        self._state.handle_stop()

class ScannerState(ABC):
    def __init__(self):
        self.context = None

    @abstractmethod
    def handle_start(self): pass

    @abstractmethod
    def handle_stop(self): pass

class IdleState(ScannerState):
    def handle_start(self):
        self.context.should_stop = False
        self.context.transition_to(DiscoveryState())
        # Begin discovery
        self.context._state.execute()

    def handle_stop(self):
        pass # Already idle

class DiscoveryState(ScannerState):
    def handle_start(self): pass # Already running
    
    def handle_stop(self):
        logger.info("Stopping during Discovery...")
        self.context.transition_to(IdleState())
        self.context.finished.emit()

    def execute(self):
        logger.info("State: Discovery Started")
        files = []
        for root in self.context.roots:
            for dirpath, _, filenames in os.walk(root):
                if self.context.should_stop: 
                    self.handle_stop()
                    return
                for f in filenames:
                    if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')):
                        files.append(os.path.abspath(os.path.join(dirpath, f)))
        
        logger.info(f"State: Discovery Found {len(files)} files")
        
        if not files:
            self.context.transition_to(IdleState())
            self.context.finished.emit()
            return

        self.context.files_to_scan = files
        self.context.transition_to(IndexingState())
        self.context._state.execute()

import os # Needed above

class IndexingState(ScannerState):
    def handle_start(self): pass
    
    def handle_stop(self):
        logger.info("Stopping during Indexing...")
        self.context.transition_to(IdleState())
        self.context.finished.emit()

    def execute(self):
        logger.info("State: Indexing Started")
        
        def on_progress(curr, total):
            if self.context.should_stop: return 
            self.context.progress_updated.emit(curr, total)
        
        # Engine does the heavy lifting
        # Note: Engines run synchronously in the thread this context is driven by.
        # Ideally, we call check stop inside callback.
        
        self.context.engine.index_files(self.context.files_to_scan, progress_callback=on_progress)
        
        if self.context.should_stop:
            self.handle_stop()
            return
            
        self.context.transition_to(MatchingState())
        self.context._state.execute()

class MatchingState(ScannerState):
    def handle_start(self): pass
    
    def handle_stop(self):
        logger.info("Stopping during Matching...")
        self.context.transition_to(IdleState())
        self.context.finished.emit()

    def execute(self):
        logger.info("State: Matching Started")
        
        def on_progress(curr, total):
            pass # Matching might not always report progress depending on engine
        
        results = self.context.engine.find_duplicates(
            root_paths=self.context.roots,
            threshold=self.context.threshold,  # Use threshold from context
            progress_callback=on_progress
        )
        
        if self.context.should_stop:
            self.handle_stop()
            return

        self.context.results_ready.emit(results)
        self.context.transition_to(IdleState())
        self.context.finished.emit()
