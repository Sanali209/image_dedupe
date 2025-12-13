import sqlite3
import os
from datetime import datetime

class DatabaseManager:
    def __init__(self, db_path="dedup_app.db"):
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        self.init_db()

    def connect(self):
        if not self.conn:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
            # Register bit_count function for Hamming distance if needed (Python 3.10+ has int.bit_count)
            # For SQLite < 3.35, we might need a custom function.
            self.conn.create_function("bit_count", 1, self._bit_count)

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def _bit_count(self, x):
        """Helper to count set bits in an integer."""
        if x is None: return 0
        return bin(x).count('1')

    def init_db(self):
        self.connect()
        cursor = self.conn.cursor()
        
        # Files table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                phash TEXT,
                file_size INTEGER,
                width INTEGER,
                height INTEGER,
                last_modified REAL
            )
        ''')
        
        # Ignored pairs (false positives)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ignored_pairs (
                hash1 TEXT NOT NULL,
                hash2 TEXT NOT NULL,
                UNIQUE(hash1, hash2)
            )
        ''')

        # Scanned paths (configuration)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scanned_paths (
                path TEXT PRIMARY KEY
            )
        ''')

        # Schema Migration: Add reason column if not exists
        try:
            cursor.execute("ALTER TABLE ignored_pairs ADD COLUMN reason TEXT")
        except sqlite3.OperationalError:
            # Column likely exists
            pass
            
        self.conn.commit()

    def upsert_file(self, path, phash, size, width, height, mtime):
        """Insert or update a file record."""
        self.connect()
        try:
            self.conn.execute('''
                INSERT INTO files (path, phash, file_size, width, height, last_modified)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    phash=excluded.phash,
                    file_size=excluded.file_size,
                    width=excluded.width,
                    height=excluded.height,
                    last_modified=excluded.last_modified
            ''', (path, phash, size, width, height, mtime))
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Database error: {e}")

    def get_file_by_path(self, path):
        self.connect()
        cursor = self.conn.execute("SELECT * FROM files WHERE path = ?", (path,))
        return cursor.fetchone()

    def get_all_files(self):
        self.connect()
        cursor = self.conn.execute("SELECT * FROM files WHERE phash IS NOT NULL")
        return cursor.fetchall()
    
    def add_ignored_pair(self, hash1, hash2, reason='not_duplicate'):
        """Add a pair of hashes to the ignore list."""
        # Ensure order to avoid duplicates (min, max)
        h1, h2 = sorted((hash1, hash2))
        self.connect()
        self.conn.execute('''
            INSERT INTO ignored_pairs (hash1, hash2, reason) VALUES (?, ?, ?)
            ON CONFLICT(hash1, hash2) DO UPDATE SET reason=excluded.reason
        ''', (h1, h2, reason))
        self.conn.commit()

    def is_ignored(self, hash1, hash2):
        h1, h2 = sorted((hash1, hash2))
        self.connect()
        cursor = self.conn.execute("SELECT 1 FROM ignored_pairs WHERE hash1 = ? AND hash2 = ?", (h1, h2))
        return cursor.fetchone() is not None

    def get_ignore_reason(self, hash1, hash2):
        h1, h2 = sorted((hash1, hash2))
        self.connect()
        cursor = self.conn.execute("SELECT reason FROM ignored_pairs WHERE hash1 = ? AND hash2 = ?", (h1, h2))
        row = cursor.fetchone()
        return row['reason'] if row else None

    def add_scanned_path(self, path):
        self.connect()
        self.conn.execute("INSERT OR IGNORE INTO scanned_paths (path) VALUES (?)", (path,))
        self.conn.commit()

    def get_scanned_paths(self):
        self.connect()
        cursor = self.conn.execute("SELECT path FROM scanned_paths")
        return [row['path'] for row in cursor.fetchall()]

    def remove_scanned_path(self, path):
        self.connect()
        self.conn.execute("DELETE FROM scanned_paths WHERE path = ?", (path,))
        self.conn.commit()

    def mark_deleted(self, path):
        """Remove file from DB (e.g. after deletion)."""
        self.connect()
        self.conn.execute("DELETE FROM files WHERE path = ?", (path,))
        self.conn.commit()

    def move_file(self, old_path, new_path):
        """Update file path in DB, handling collisions."""
        self.connect()
        # If new_path exists, remove it first (overwrite logic in FS implies overwrite in DB)
        self.conn.execute("DELETE FROM files WHERE path = ?", (new_path,))
        self.conn.execute("UPDATE files SET path = ? WHERE path = ?", (new_path, old_path))
        self.conn.commit()
