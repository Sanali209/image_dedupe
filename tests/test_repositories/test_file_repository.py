import pytest
import os
import tempfile
from core.database import DatabaseManager
from core.repositories.file_repository import FileRepository

@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    db = DatabaseManager(path)
    yield db
    db.close()
    if os.path.exists(path):
        os.remove(path)

@pytest.fixture
def file_repo(temp_db):
    """Create a FileRepository instance with temp database."""
    return FileRepository(temp_db)

class TestFileRepository:
    def test_upsert_file_insert(self, file_repo):
        """Test inserting a new file."""
        file_repo.upsert_file('/test/path.jpg', 'hash123', 1024, 100, 100, 123456)
        
        result = file_repo.get_file_by_path('/test/path.jpg')
        assert result is not None
        assert result['path'] == '/test/path.jpg'
        assert result['phash'] == 'hash123'
        assert result['file_size'] == 1024
        
    def test_upsert_file_update(self, file_repo):
        """Test updating an existing file."""
        file_repo.upsert_file('/test/path.jpg', 'hash123', 1024, 100, 100, 123456)
        file_repo.upsert_file('/test/path.jpg', 'hash456', 2048, 200, 200, 234567)
        
        result = file_repo.get_file_by_path('/test/path.jpg')
        assert result['phash'] == 'hash456'
        assert result['file_size'] == 2048
        
    def test_get_file_by_path_not_found(self, file_repo):
        """Test getting a non-existent file."""
        result = file_repo.get_file_by_path('/nonexistent.jpg')
        assert result is None
        
    def test_get_all_files(self, file_repo):
        """Test retrieving all files."""
        file_repo.upsert_file('/test/1.jpg', 'hash1', 100, 10, 10, 1)
        file_repo.upsert_file('/test/2.jpg', 'hash2', 200, 20, 20, 2)
        
        files = file_repo.get_all_files()
        assert len(files) == 2
        
    def test_mark_deleted(self, file_repo):
        """Test marking a file as deleted."""
        file_repo.upsert_file('/test/delete.jpg', 'hash1', 100, 10, 10, 1)
        file_repo.mark_deleted('/test/delete.jpg')
        
        result = file_repo.get_file_by_path('/test/delete.jpg')
        assert result is None
        
    def test_move_file(self, file_repo):
        """Test moving a file."""
        file_repo.upsert_file('/old/path.jpg', 'hash1', 100, 10, 10, 1)
        file_repo.move_file('/old/path.jpg', '/new/path.jpg')
        
        old = file_repo.get_file_by_path('/old/path.jpg')
        new = file_repo.get_file_by_path('/new/path.jpg')
        
        assert old is None
        assert new is not None
        assert new['phash'] == 'hash1'
        
    def test_add_ignored_pair(self, file_repo):
        """Test adding an ignored pair."""
        file_repo.add_ignored_pair('hash1', 'hash2', 'not_duplicate')
        
        assert file_repo.is_ignored('hash1', 'hash2') is True
        assert file_repo.is_ignored('hash2', 'hash1') is True  # Order shouldn't matter
        
    def test_is_ignored_false(self, file_repo):
        """Test checking non-ignored pair."""
        assert file_repo.is_ignored('hash1', 'hash2') is False
        
    def test_remove_ignored_pair(self, file_repo):
        """Test removing an ignored pair."""
        file_repo.add_ignored_pair('hash1', 'hash2', 'test')
        assert file_repo.is_ignored('hash1', 'hash2') is True
        
        file_repo.remove_ignored_pair('hash1', 'hash2')
        assert file_repo.is_ignored('hash1', 'hash2') is False
        
    def test_get_ignore_reason(self, file_repo):
        """Test retrieving ignore reason."""
        file_repo.add_ignored_pair('hash1', 'hash2', 'similar_but_different')
        
        reason = file_repo.get_ignore_reason('hash1', 'hash2')
        assert reason == 'similar_but_different'
        
    def test_scanned_paths(self, file_repo):
        """Test scanned path management."""
        file_repo.add_scanned_path('/test/folder1')
        file_repo.add_scanned_path('/test/folder2')
        
        paths = file_repo.get_scanned_paths()
        assert len(paths) == 2
        assert '/test/folder1' in paths
        
        file_repo.remove_scanned_path('/test/folder1')
        paths = file_repo.get_scanned_paths()
        assert len(paths) == 1
        assert '/test/folder1' not in paths
        
    def test_get_files_in_roots(self, file_repo):
        """Test retrieving files within specified roots."""
        # Use os.path.normpath for cross-platform compatibility
        root1 = os.path.normpath('/root1')
        root2 = os.path.normpath('/root2')
        other = os.path.normpath('/other')
        
        file1 = os.path.normpath('/root1/file1.jpg')
        file2 = os.path.normpath('/root1/sub/file2.jpg')
        file3 = os.path.normpath('/root2/file3.jpg')
        file4 = os.path.normpath('/other/file4.jpg')
        
        file_repo.upsert_file(file1, 'h1', 100, 10, 10, 1)
        file_repo.upsert_file(file2, 'h2', 100, 10, 10, 1)
        file_repo.upsert_file(file3, 'h3', 100, 10, 10, 1)
        file_repo.upsert_file(file4, 'h4', 100, 10, 10, 1)
        
        files = file_repo.get_files_in_roots([root1, root2])
        paths = [f['path'] for f in files]
        
        assert len(files) == 3
        assert file1 in paths
        assert file2 in paths
        assert file3 in paths
        assert file4 not in paths

