import sqlite3
import os
from datetime import datetime
from loguru import logger

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

        # Scanned paths (configuration)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scanned_paths (
                path TEXT PRIMARY KEY
            )
        ''')

        # Clusters Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clusters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                target_folder TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Cluster Members Table (no phash column - cleaned up)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cluster_members (
                cluster_id INTEGER,
                file_path TEXT NOT NULL,
                FOREIGN KEY(cluster_id) REFERENCES clusters(id) ON DELETE CASCADE,
                UNIQUE(cluster_id, file_path)
            )
        ''')
        
        # File Relations Table (ID-based, primary storage for duplicates)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS file_relations (
                id1 INTEGER NOT NULL,
                id2 INTEGER NOT NULL,
                relation_type TEXT NOT NULL,
                distance REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id1, id2),
                CHECK (id1 < id2)
            )
        ''')
        
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
        cursor = self.conn.execute("SELECT * FROM files")
        return cursor.fetchall()

    def get_files_in_roots(self, roots):
        """Retrieve files that reside within the specified root directories."""
        self.connect()
        if not roots:
            return []
            
        # Build query dynamically
        query = "SELECT * FROM files WHERE "
        conditions = []
        params = []
        
        for root in roots:
            # Normalize root to ensure consistency
            norm_root = os.path.normpath(root)
            # Use LIKE for "startswith" logic. 
            # We append wildcards: path = root OR path LIKE root + os.sep + %
            # Note: os.sep might vary, but we assume local OS consistency or handle both.
            # SQLite LIKE is case-insensitive usually, but strictness helps.
            
            # Condition 1: Exact match (file IS the root - unlikely but possible)
            # Condition 2: Inside root
            conditions.append("(path = ? OR path LIKE ?)")
            params.append(norm_root)
            params.append(norm_root + os.sep + '%')
            
        query += " OR ".join(conditions)
        cursor = self.conn.execute(query, params)
        return cursor.fetchall()
    

    def is_ignored(self, id1, id2):
        """Check if pair of IDs is ignored."""
        try:
            i1, i2 = int(id1), int(id2)
        except (ValueError, TypeError):
            return False
            
        s1, s2 = sorted((i1, i2))
        self.connect()
        # 'new_match' is visible (pending). System types are visible.
        # Everything else is considered "Handled" (Hidden by default unless Show Annotated is on).
        # Wait, user logic: "types new_mach - shown not on show anotated image" -> Show Annotated=False shows new_match.
        # Show Annotated=True shows everything? Or shows Not-New-Match?
        # Usually: Default view = Pending (new_match). History view = All or filter.
        # "is_ignored" usually means "Should I hide this from the Pending view?"
        # So if relation exists AND type != 'new_match', it is ignored (handled).
        
        cursor = self.conn.execute(
            "SELECT 1 FROM file_relations WHERE id1 = ? AND id2 = ? AND relation_type != 'new_match'", 
            (s1, s2)
        )
        return cursor.fetchone() is not None

    def get_ignore_reason(self, id1, id2):
        try:
            i1, i2 = int(id1), int(id2)
        except: return None
        
        s1, s2 = sorted((i1, i2))
        self.connect()
        cursor = self.conn.execute("SELECT relation_type FROM file_relations WHERE id1 = ? AND id2 = ?", (s1, s2))
        row = cursor.fetchone()
        return row['relation_type'] if row else None
        
    def add_ignored_pair_id(self, id1, id2, reason='not_duplicate', distance=None):
        try:
            i1, i2 = int(id1), int(id2)
        except: return
        
        s1, s2 = sorted((i1, i2))
        self.connect()
        try:
            self.conn.execute(
                "INSERT INTO file_relations (id1, id2, relation_type, distance) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id1, id2) DO UPDATE SET relation_type=excluded.relation_type, distance=excluded.distance",
                (s1, s2, reason, distance)
            )
            self.conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Error adding relation ID: {e}")

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



    # --- Cluster Persistence Methods ---
    def create_cluster(self, name, target_folder=""):
        self.connect()
        cursor = self.conn.execute("INSERT INTO clusters (name, target_folder) VALUES (?, ?)", (name, target_folder))
        self.conn.commit()
        return cursor.lastrowid

    def update_cluster(self, cluster_id, name=None, target_folder=None):
        self.connect()
        if name is not None:
            self.conn.execute("UPDATE clusters SET name = ? WHERE id = ?", (name, cluster_id))
        if target_folder is not None:
            self.conn.execute("UPDATE clusters SET target_folder = ? WHERE id = ?", (target_folder, cluster_id))
        self.conn.commit()

    def delete_cluster(self, cluster_id):
        self.connect()
        self.conn.execute("DELETE FROM clusters WHERE id = ?", (cluster_id,))
        self.conn.commit()

    def add_cluster_members(self, cluster_id, files):
        """files: list of dicts or paths. We store path."""
        self.connect()
        data = []
        for f in files:
            path = f if isinstance(f, str) else f['path']
            # phash? optional
            data.append((cluster_id, path))
        
        self.conn.executemany("INSERT OR IGNORE INTO cluster_members (cluster_id, file_path) VALUES (?, ?)", data)
        self.conn.commit()

    def remove_cluster_member(self, cluster_id, path):
        self.connect()
        self.conn.execute("DELETE FROM cluster_members WHERE cluster_id = ? AND file_path = ?", (cluster_id, path))
        self.conn.commit()

    def remove_all_cluster_members(self, cluster_id):
        self.connect()
        self.conn.execute("DELETE FROM cluster_members WHERE cluster_id = ?", (cluster_id,))
        self.conn.commit()

    def delete_all_clusters(self):
        self.connect()
        # Delete members first (or cascade if set up, but safer explicit)
        self.conn.execute("DELETE FROM cluster_members")
        self.conn.execute("DELETE FROM clusters")
        self.conn.commit()

    def get_clusters(self):
        self.connect()
        cursor = self.conn.execute("SELECT * FROM clusters ORDER BY id")
        return cursor.fetchall()
        
    def get_all_cluster_members(self):
        """Return dict: path -> cluster_id"""
        self.connect()
        cursor = self.conn.execute("SELECT cluster_id, file_path FROM cluster_members")
        return {row['file_path']: row['cluster_id'] for row in cursor.fetchall()}
        
    def get_cluster_members(self, cluster_id):
        self.connect()
        cursor = self.conn.execute("SELECT file_path FROM cluster_members WHERE cluster_id = ?", (cluster_id,))
        return [row['file_path'] for row in cursor.fetchall()]
