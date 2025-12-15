import abc

class BaseEngine(abc.ABC):
    def __init__(self, db_manager):
        self.db_manager = db_manager

    @abc.abstractmethod
    def initialize(self):
        """Load models or prepare resources."""
        pass

    @abc.abstractmethod
    def index_files(self, files, progress_callback=None):
        """
        Process files to generate hashes/vectors.
        Args:
            files: List of file paths to process.
            progress_callback: function(current, total)
        """
        pass

    @abc.abstractmethod
    def find_duplicates(self, files, threshold=5, root_paths=None, include_ignored=False, progress_callback=None):
        """
        Find duplicate groups.
        Args:
            files: List of file dictionaries (or None to fetch from DB)
            threshold: Similarity threshold (int for pHash, float for AI)
            root_paths: Optional list of roots to filter scan
            include_ignored: Whether to include pairs marked as ignored
            progress_callback: function(current, total)
        Returns:
            List of groups (list of file dicts).
        """
        pass
