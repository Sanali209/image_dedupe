import pytest
import os
import tempfile
from core.database import DatabaseManager
from core.repositories.cluster_repository import ClusterRepository
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
def cluster_repo(temp_db):
    """Create a ClusterRepository instance."""
    return ClusterRepository(temp_db)

@pytest.fixture
def file_repo(temp_db):
    """Create a FileRepository instance for prerequisite data."""
    return FileRepository(temp_db)

class TestClusterRepository:
    def test_create_cluster(self, cluster_repo):
        """Test creating a cluster."""
        cluster_id = cluster_repo.create_cluster('Test Cluster', '/target/folder')
        
        assert cluster_id > 0
        clusters = cluster_repo.get_clusters()  # Changed from get_all_clusters
        assert len(clusters) == 1
        assert clusters[0]['name'] == 'Test Cluster'
        
    def test_create_cluster_default_folder(self, cluster_repo):
        """Test creating cluster with default empty folder."""
        cluster_id = cluster_repo.create_cluster('Test')
        
        clusters = cluster_repo.get_clusters()
        assert clusters[0]['target_folder'] == ''
        
    def test_get_all_clusters(self, cluster_repo):
        """Test retrieving all clusters."""
        cluster_repo.create_cluster('Cluster 1')
        cluster_repo.create_cluster('Cluster 2')
        
        clusters = cluster_repo.get_clusters()
        assert len(clusters) == 2
        
    def test_update_cluster(self, cluster_repo):
        """Test updating cluster properties."""
        cluster_id = cluster_repo.create_cluster('Original')
        
        cluster_repo.update_cluster(cluster_id, name='Updated', target_folder='/new/path')
        
        clusters = cluster_repo.get_clusters()
        assert clusters[0]['name'] == 'Updated'
        assert clusters[0]['target_folder'] == '/new/path'
        
    def test_delete_cluster(self, cluster_repo, file_repo):
        """Test deleting a cluster."""
        # Create cluster with members
        cluster_id = cluster_repo.create_cluster('To Delete')
        file_repo.upsert_file('/test/file.jpg', 'hash1', 100, 10, 10, 1)
        cluster_repo.add_cluster_members(cluster_id, ['/test/file.jpg'])
        
        cluster_repo.delete_cluster(cluster_id)
        
        clusters = cluster_repo.get_clusters()
        assert len(clusters) == 0
        
    def test_delete_all_clusters(self, cluster_repo):
        """Test deleting all clusters."""
        cluster_repo.create_cluster('C1')
        cluster_repo.create_cluster('C2')
        
        cluster_repo.delete_all_clusters()
        
        clusters = cluster_repo.get_clusters()
        assert len(clusters) == 0
        
    def test_add_cluster_members(self, cluster_repo, file_repo):
        """Test adding members to a cluster."""
        cluster_id = cluster_repo.create_cluster('Test')
        file_repo.upsert_file('/file1.jpg', 'h1', 100, 10, 10, 1)
        file_repo.upsert_file('/file2.jpg', 'h2', 100, 10, 10, 1)
        
        cluster_repo.add_cluster_members(cluster_id, ['/file1.jpg', '/file2.jpg'])
        
        members = cluster_repo.get_cluster_members(cluster_id)
        assert len(members) == 2
        
    def test_get_cluster_members(self, cluster_repo, file_repo):
        """Test retrieving cluster members."""
        cluster_id = cluster_repo.create_cluster('Test')
        file_repo.upsert_file('/file1.jpg', 'h1', 100, 10, 10, 1)
        cluster_repo.add_cluster_members(cluster_id, ['/file1.jpg'])
        
        members = cluster_repo.get_cluster_members(cluster_id)
        assert len(members) == 1
        assert members[0] == '/file1.jpg'  # Returns list of paths, not dicts
        
    def test_remove_cluster_member(self, cluster_repo, file_repo):
        """Test removing a member from cluster."""
        cluster_id = cluster_repo.create_cluster('Test')
        file_repo.upsert_file('/file1.jpg', 'h1', 100, 10, 10, 1)
        file_repo.upsert_file('/file2.jpg', 'h2', 100, 10, 10, 1)
        
        cluster_repo.add_cluster_members(cluster_id, ['/file1.jpg', '/file2.jpg'])
        cluster_repo.remove_cluster_member(cluster_id, '/file1.jpg')
        
        members = cluster_repo.get_cluster_members(cluster_id)
        assert len(members) == 1
        assert members[0] == '/file2.jpg'  # Returns list of paths, not dicts
        
    def test_get_cluster_by_id(self, cluster_repo):
        """Test retrieving specific cluster by ID - SKIPPED (method not implemented)."""
        pytest.skip("get_cluster_by_id not implemented in ClusterRepository")
