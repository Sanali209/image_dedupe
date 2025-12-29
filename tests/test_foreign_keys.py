"""
Test Foreign Key Constraints

Tests to verify that foreign key constraints are properly enforced
and CASCADE delete works as expected.
"""

import pytest
import sqlite3
import os
import sys

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import DatabaseManager
from core.repositories.file_repository import FileRepository
from core.models import FileRelation, RelationType


class TestForeignKeyConstraints:
    
    @pytest.fixture
    def db_manager(self, tmp_path):
        """Create a temporary database for testing."""
        db_path = tmp_path / "test_fk.db"
        db = DatabaseManager(str(db_path))
        yield db
        db.close()
        if db_path.exists():
            os.remove(db_path)
    
    @pytest.fixture
    def file_repo(self, db_manager):
        """Create file repository."""
        return FileRepository(db_manager)
    
    def test_foreign_keys_enabled(self, db_manager):
        """Verify that foreign keys are enabled on connection."""
        db_manager.connect()
        cursor = db_manager.conn.execute("PRAGMA foreign_keys;")
        fk_status = cursor.fetchone()[0]
        assert fk_status == 1, "Foreign keys should be enabled"
    
    def test_fk_constraint_prevents_invalid_insert(self, db_manager):
        """Test that FK constraint prevents inserting relation with non-existent file IDs."""
        db_manager.connect()
        
        # Try to insert a relation with IDs that don't exist
        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            db_manager.conn.execute(
                "INSERT INTO file_relations (id1, id2, relation_type) VALUES (?, ?, ?)",
                (999, 1000, 'new_match')
            )
            db_manager.conn.commit()
        
        assert "FOREIGN KEY constraint failed" in str(exc_info.value)
    
    def test_cascade_delete(self, db_manager, file_repo):
        """Test that deleting a file cascades to delete its relations."""
        db_manager.connect()
        
        # Insert two files
        file_repo.upsert_file('/test/file1.jpg', 'abc123', 1024, 100, 100, 1.0)
        file_repo.upsert_file('/test/file2.jpg', 'def456', 2048, 200, 200, 2.0)
        
        # Get file IDs
        f1 = db_manager.get_file_by_path('/test/file1.jpg')
        f2 = db_manager.get_file_by_path('/test/file2.jpg')
        
        assert f1 is not None
        assert f2 is not None
        
        id1, id2 = f1['id'], f2['id']
        
        # Add relation between them
        rel = FileRelation(
            id1=min(id1, id2),
            id2=max(id1, id2),
            relation_type=RelationType.NEW_MATCH,
            distance=5.0
        )
        file_repo.add_relations_batch([rel], overwrite=True)
        
        # Verify relation exists
        cursor = db_manager.conn.execute(
            "SELECT * FROM file_relations WHERE id1 = ? AND id2 = ?",
            (min(id1, id2), max(id1, id2))
        )
        assert cursor.fetchone() is not None
        
        # Delete one file
        file_repo.mark_deleted('/test/file1.jpg')
        
        # Verify relation was CASCADE deleted
        cursor = db_manager.conn.execute(
            "SELECT * FROM file_relations WHERE id1 = ? AND id2 = ?",
            (min(id1, id2), max(id1, id2))
        )
        assert cursor.fetchone() is None, "Relation should have been CASCADE deleted"
    
    def test_add_relations_batch_validation(self, db_manager, file_repo):
        """Test that add_relations_batch validates file IDs before inserting."""
        # Insert one file
        file_repo.upsert_file('/test/valid.jpg', 'abc123', 1024, 100, 100, 1.0)
        f1 = db_manager.get_file_by_path('/test/valid.jpg')
        valid_id = f1['id']
        
        # Try to add relations with one valid and one invalid ID
        invalid_relations = [
            FileRelation(
                id1=valid_id,
                id2=99999,  # Doesn't exist
                relation_type=RelationType.NEW_MATCH,
                distance=0.0
            ),
            FileRelation(
                id1=88888,  # Doesn't exist
                id2=99999,  # Doesn't exist
                relation_type=RelationType.NEW_MATCH,
                distance=0.0
            )
        ]
        
        result = file_repo.add_relations_batch(invalid_relations, overwrite=False)
        
        # Should report all as skipped
        assert result['added'] == 0
        assert result['skipped'] == 2
        
        # Verify no relations were inserted
        cursor = db_manager.conn.execute("SELECT COUNT(*) FROM file_relations")
        count = cursor.fetchone()[0]
        assert count == 0
    
    def test_schema_has_fk_constraints(self, db_manager):
        """Verify that the schema contains FOREIGN KEY definitions."""
        db_manager.connect()
        cursor = db_manager.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='file_relations'"
        )
        schema = cursor.fetchone()[0]
        
        assert "FOREIGN KEY" in schema, "Schema should contain FOREIGN KEY constraints"
        assert "ON DELETE CASCADE" in schema, "Schema should have ON DELETE CASCADE"
        assert "REFERENCES files(id)" in schema, "Should reference files(id)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
