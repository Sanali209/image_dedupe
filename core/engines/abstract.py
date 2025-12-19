from abc import ABC, abstractmethod
from typing import List, Dict, Any

class AbstractDedupeEngine(ABC):
    """
    Strategy Interface for Deduplication Engines.
    Each engine (pHash, CLIP, etc.) must implement this interface.
    """

    @abstractmethod
    def initialize(self):
        """Perform any one-time setup (loading models, etc)."""
        pass

    @abstractmethod
    def index_files(self, files: List[str], progress_callback=None):
        """
        Scan and index the provided files.
        :param files: List of absolute file paths to process.
        :param progress_callback: Optional callable(current, total).
        """
        pass

    @abstractmethod
    def find_duplicates(self, 
                       files: List[Any] = None, 
                       threshold: float = 0.0, 
                       root_paths: List[str] = None, 
                       include_ignored: bool = False, 
                       progress_callback=None) -> List[List[Dict]]:
        """
        Identify duplicate groups.
        :return: List of groups, where each group is a list of file row dicts.
        """
        pass
