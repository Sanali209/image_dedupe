import pytest
import os
import tempfile
import shutil
from core.database import DatabaseManager
from core.repositories.file_repository import FileRepository
from core.commands.actions import DeleteFileCommand, IgnorePairCommand, ReplaceFileCommand

@pytest.fixture
def temp_db():
    """Create a temporary database."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    db = DatabaseManager(path)
    yield db
    db.close()
    if os.path.exists(path):
        os.remove(path)

@pytest.fixture
def file_repo(temp_db):
    """Create FileRepository."""
    return FileRepository(temp_db)

@pytest.fixture
def temp_dir():
    """Create a temporary directory for file operations."""
    dirpath = tempfile.mkdtemp()
    yield dirpath
    if os.path.exists(dirpath):
        shutil.rmtree(dirpath)

class TestDeleteFileCommand:
    def test_execute_deletes_file(self, file_repo, temp_dir):
        """Test that execute deletes file and marks in DB."""
        file_path = os.path.join(temp_dir, 'test.txt')
        with open(file_path, 'w') as f:
            f.write('content')
        file_repo.upsert_file(file_path, 'hash1', 100, 10, 10, 1)
        
        cmd = DeleteFileCommand(file_repo, file_path)
        cmd.execute()
        
        assert not os.path.exists(file_path)
        assert file_repo.get_file_by_path(file_path) is None
        
    def test_undo_restores_file(self, file_repo, temp_dir):
        """Test that undo restores file."""
        file_path = os.path.join(temp_dir, 'test.txt')
        with open(file_path, 'w') as f:
            f.write('content')
        file_repo.upsert_file(file_path, 'hash1', 100, 10, 10, 1)
        
        cmd = DeleteFileCommand(file_repo, file_path)
        cmd.execute()
        cmd.undo()
        
        assert os.path.exists(file_path)
        assert file_repo.get_file_by_path(file_path) is not None
        
    def test_execute_nonexistent_file(self, file_repo, temp_dir):
        """Test executing delete on non-existent file."""
        file_path = os.path.join(temp_dir, 'nonexistent.txt')
        
        cmd = DeleteFileCommand(file_repo, file_path)
        # Should not raise exception
        cmd.execute()

class TestIgnorePairCommand:
    def test_execute_adds_ignored_pair(self, file_repo):
        """Test that execute adds ignored pair."""
        cmd = IgnorePairCommand(file_repo, 'hash1', 'hash2', 'not_duplicate')
        cmd.execute()
        
        assert file_repo.is_ignored('hash1', 'hash2') is True
        assert file_repo.get_ignore_reason('hash1', 'hash2') == 'not_duplicate'
        
    def test_undo_removes_ignored_pair(self, file_repo):
        """Test that undo removes ignored pair."""
        cmd = IgnorePairCommand(file_repo, 'hash1', 'hash2', 'test')
        cmd.execute()
        cmd.undo()
        
        assert file_repo.is_ignored('hash1', 'hash2') is False
        
    def test_multiple_execute_idempotent(self, file_repo):
        """Test that multiple executes are idempotent."""
        cmd = IgnorePairCommand(file_repo, 'hash1', 'hash2', 'reason1')
        cmd.execute()
        cmd.execute()
        
        assert file_repo.is_ignored('hash1', 'hash2') is True

class TestReplaceFileCommand:
    def test_execute_replaces_content(self, file_repo, temp_dir):
        """Test that execute replaces file content."""
        target = os.path.join(temp_dir, 'target.txt')
        source = os.path.join(temp_dir, 'source.txt')
        
        with open(target, 'w') as f:
            f.write('target content')
        with open(source, 'w') as f:
            f.write('source content')
            
        file_repo.upsert_file(target, 'h1', 100, 10, 10, 1)
        
        cmd = ReplaceFileCommand(file_repo, target, source)
        cmd.execute()
        
        with open(target, 'r') as f:
            content = f.read()
        assert content == 'source content'
        
    def test_undo_restores_original(self, file_repo, temp_dir):
        """Test that undo restores original content."""
        target = os.path.join(temp_dir, 'target.txt')
        source = os.path.join(temp_dir, 'source.txt')
        
        with open(target, 'w') as f:
            f.write('original')
        with open(source, 'w') as f:
            f.write('new')
            
        file_repo.upsert_file(target, 'h1', 100, 10, 10, 1)
        
        cmd = ReplaceFileCommand(file_repo, target, source)
        cmd.execute()
        cmd.undo()
        
        with open(target, 'r') as f:
            content = f.read()
        assert content == 'original'
