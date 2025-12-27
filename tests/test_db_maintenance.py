import unittest
import sqlite3
import os
import tempfile
import shutil
from core.database import DatabaseManager

class TestDatabaseMaintenance(unittest.TestCase):
    def setUp(self):
        # Create a temp directory for DB and fake files
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test.db")
        self.db = DatabaseManager(self.db_path)
        
        # Create some fake files
        self.file1 = os.path.join(self.test_dir, "file1.jpg")
        self.file2 = os.path.join(self.test_dir, "file2.jpg")
        self.file3 = os.path.join(self.test_dir, "file3.jpg")
        
        for f in [self.file1, self.file2, self.file3]:
            with open(f, "w") as fh:
                fh.write("test")

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.test_dir)

    def test_cleanup_missing_files(self):
        # Insert all files
        self.db.upsert_file(self.file1, "hash1", 100, 100, 100, 1.0)
        self.db.upsert_file(self.file2, "hash2", 100, 100, 100, 1.0)
        self.db.upsert_file(self.file3, "hash3", 100, 100, 100, 1.0)
        
        # Verify count
        self.assertEqual(self.db.get_file_count(), 3)
        
        # Delete file2 from disk
        os.remove(self.file2)
        
        # Run cleanup
        removed = self.db.cleanup_missing_files()
        
        # Verify
        self.assertEqual(removed, 1)
        self.assertEqual(self.db.get_file_count(), 2)
        
        # Verify file2 is gone
        file2_rec = self.db.get_file_by_path(self.file2)
        self.assertIsNone(file2_rec)
        
        # Verify file1 exists
        file1_rec = self.db.get_file_by_path(self.file1)
        self.assertIsNotNone(file1_rec)

    def test_cleanup_orphans(self):
        # Insert files and relations
        self.db.upsert_file(self.file1, "hash1", 100, 100, 100, 1.0)
        file1_id = self.db.get_file_by_path(self.file1)['id']
        
        # Insert orphan relation (id 999 not in files)
        self.db.connect()
        self.db.conn.execute(
            "INSERT INTO file_relations (id1, id2, relation_type) VALUES (?, ?, ?)",
            (file1_id, 999, "duplicate")
        )
        self.db.conn.commit()
        
        # Insert orphan vector status
        self.db.conn.execute(
            "INSERT INTO vector_index_status (path, engine) VALUES (?, ?)",
            ("non_existent_path", "mobilenet")
        )
        self.db.conn.commit()
        
        # Run orphan cleanup
        stats = self.db.cleanup_orphans()
        
        self.assertEqual(stats['relations_removed'], 1)
        self.assertEqual(stats['vector_status_removed'], 1)
        
        # Verify relation is gone
        c = self.db.conn.execute("SELECT * FROM file_relations WHERE id2 = 999")
        self.assertIsNone(c.fetchone())

    def test_optimize(self):
        # Just run it to ensure no errors
        self.db.optimize_database()

if __name__ == '__main__':
    unittest.main()
