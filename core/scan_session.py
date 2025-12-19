from PySide6.QtCore import QObject, Signal
from loguru import logger

class ScanSession(QObject):
    """
    Single Source of Truth for the application's scan configuration and state.
    Signals allow UI components to react to changes.
    """
    config_changed = Signal() # Emitted when any config changes

    def __init__(self, file_repository):
        super().__init__()
        self.file_repo = file_repository
        
        # Core State
        self._roots = []
        self._engine = 'phash'
        self._threshold = 5
        self._include_ignored = False
        
        # Advanced Filtering / Criteria (for clustering)
        self._criteria = {
            'exact_hash': True,
            'ai_match': True,
            'similar': True,
            'same_set': False,
            'not_duplicate': False,
            'similar_crop': False,
            'similar_style': False,
            'other': False,
            'ai_similarity': False,
            'ai_threshold': 0.1,
            'ai_engine': 'clip'
        }
        
        self.load_defaults()

    def load_defaults(self):
        """Load persisted state from DB (like scanned paths)."""
        self._roots = self.file_repo.get_scanned_paths()

    # --- Properties with Signals ---

    @property
    def roots(self):
        return self._roots

    @roots.setter
    def roots(self, paths):
        if self._roots != paths:
            self._roots = paths
            # Sync to DB immediately as per original behavior
            current = set(paths)
            existing = set(self.file_repo.get_scanned_paths())
            
            for p in existing - current:
                self.file_repo.remove_scanned_path(p)
            for p in current - existing:
                self.file_repo.add_scanned_path(p)
                
            self.config_changed.emit()

    @property
    def engine(self):
        return self._engine

    @engine.setter
    def engine(self, value):
        if self._engine != value:
            self._engine = value
            self.config_changed.emit()

    @property
    def threshold(self):
        return self._threshold

    @threshold.setter
    def threshold(self, value):
        if self._threshold != value:
            self._threshold = value
            self.config_changed.emit()

    @property
    def include_ignored(self):
        return self._include_ignored

    @include_ignored.setter
    def include_ignored(self, value):
        if self._include_ignored != value:
            self._include_ignored = value
            self.config_changed.emit()
            
    # --- Criteria Management ---
    
    def set_criterion(self, key, value):
        if key in self._criteria and self._criteria[key] != value:
            self._criteria[key] = value
            self.config_changed.emit()
            
    def get_criteria(self):
        # Merge basic settings into criteria for Deduper consumption if needed
        c = self._criteria.copy()
        # Add 'roots' if we want scoping
        if self._roots:
            c['roots'] = self._roots
        return c

    def get_engine_threshold_defaults(self, engine_type):
        """Helper for UI to get ranges."""
        if engine_type == 'phash':
            return {'label': 'Similarity Threshold (0-50, int):', 'min': 0, 'max': 50, 'step': 1, 'decimals': 0, 'default': 5}
        else:
            return {'label': 'Cosine Distance (0.0 - 1.0, lower is stricter):', 'min': 0.0, 'max': 1.0, 'step': 0.05, 'decimals': 2, 'default': 0.1}
