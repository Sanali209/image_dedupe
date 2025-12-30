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
            
            # CRITICAL: Enable foreign key constraints (disabled by default in SQLite)
            self.conn.execute("PRAGMA foreign_keys = ON;")
            
            # Verify FK status and log
            fk_status = self.conn.execute("PRAGMA foreign_keys;").fetchone()[0]
            if fk_status:
                logger.debug("Foreign keys enabled successfully")
            else:
                logger.warning("Foreign keys could not be enabled!")
            
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
        
        # Performance Pragmas for large datasets
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache
        cursor.execute("PRAGMA temp_store=MEMORY")
        
        # Files table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                phash TEXT,
                phash_c1 INTEGER, -- 16-bit chunk 1
                phash_c2 INTEGER, -- 16-bit chunk 2
                phash_c3 INTEGER, -- 16-bit chunk 3
                phash_c4 INTEGER, -- 16-bit chunk 4
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
        # NOTE: Table created with foreign key constraints. Annotations persist across app restarts.
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS file_relations (
                id1 INTEGER NOT NULL,
                id2 INTEGER NOT NULL,
                relation_type TEXT NOT NULL,
                distance REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id1, id2),
                CHECK (id1 < id2),
                FOREIGN KEY (id1) REFERENCES files(id) ON DELETE CASCADE,
                FOREIGN KEY (id2) REFERENCES files(id) ON DELETE CASCADE
            )
        ''')
        
        # Vector Index Status Table (tracks which files have AI embeddings)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vector_index_status (
                path TEXT NOT NULL,
                engine TEXT NOT NULL,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (path, engine)
            )
        ''')
        
        # Performance Indexes for 1M+ scale
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_phash ON files(phash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_phash_c1 ON files(phash_c1)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_phash_c2 ON files(phash_c2)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_phash_c3 ON files(phash_c3)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_phash_c4 ON files(phash_c4)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_last_modified ON files(last_modified)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_relations_type ON file_relations(relation_type)')
        # Foreign key indexes for better JOIN and CASCADE performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_relations_id1 ON file_relations(id1)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_relations_id2 ON file_relations(id2)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cluster_members_path ON cluster_members(file_path)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_vector_status_engine ON vector_index_status(engine)')
        
        self.conn.commit()


    def upsert_file(self, path, phash, size, width, height, mtime):
        """Insert or update a file record."""
        self.connect()
        try:
            # Extract chunks for MIH if phash is present
            c1, c2, c3, c4 = self._extract_phash_chunks(phash)
            
            self.conn.execute('''
                INSERT INTO files (path, phash, phash_c1, phash_c2, phash_c3, phash_c4, file_size, width, height, last_modified)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    phash=excluded.phash,
                    phash_c1=excluded.phash_c1,
                    phash_c2=excluded.phash_c2,
                    phash_c3=excluded.phash_c3,
                    phash_c4=excluded.phash_c4,
                    file_size=excluded.file_size,
                    width=excluded.width,
                    height=excluded.height,
                    last_modified=excluded.last_modified
            ''', (path, phash, c1, c2, c3, c4, size, width, height, mtime))
            self.conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")

    def _extract_phash_chunks(self, phash_str):
        """Split 64-bit phash (hex string) into four 16-bit integer chunks."""
        if not phash_str or len(phash_str) != 16:
            return None, None, None, None
        try:
            val = int(phash_str, 16)
            c1 = (val >> 48) & 0xFFFF
            c2 = (val >> 32) & 0xFFFF
            c3 = (val >> 16) & 0xFFFF
            c4 = val & 0xFFFF
            return c1, c2, c3, c4
        except ValueError:
            return None, None, None, None

    def upsert_files_batch(self, file_data, batch_size=5000):
        """
        Batch insert/update file records for better performance.
        
        Args:
            file_data: List of tuples (path, phash, size, width, height, mtime)
        """
        if not file_data:
            return
            
        self.connect()
        try:
            prepared_data = []
            for item in file_data:
                path, phash, size, width, height, mtime = item
                c1, c2, c3, c4 = self._extract_phash_chunks(phash)
                prepared_data.append((path, phash, c1, c2, c3, c4, size, width, height, mtime))

            for i in range(0, len(prepared_data), batch_size):
                batch = prepared_data[i:i+batch_size]
                self.conn.executemany('''
                    INSERT INTO files (path, phash, phash_c1, phash_c2, phash_c3, phash_c4, file_size, width, height, last_modified)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(path) DO UPDATE SET
                        phash=excluded.phash,
                        phash_c1=excluded.phash_c1,
                        phash_c2=excluded.phash_c2,
                        phash_c3=excluded.phash_c3,
                        phash_c4=excluded.phash_c4,
                        file_size=excluded.file_size,
                        width=excluded.width,
                        height=excluded.height,
                        last_modified=excluded.last_modified
                ''', batch)
                self.conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Batch upsert error: {e}")

    def get_file_by_path(self, path):
        self.connect()
        cursor = self.conn.execute("SELECT * FROM files WHERE path = ?", (path,))
        return cursor.fetchone()

    def get_all_files(self):
        self.connect()
        self.conn.row_factory = sqlite3.Row
        return self.conn.execute('SELECT * FROM files').fetchall()

    def get_phash_candidates(self, id_list=None):
        """
        Find candidate pairs sharing at least one 16-bit phash chunk (MIH).
        
        Args:
            id_list: Optional list of IDs to restrict search (not implemented yet).
            
        Returns:
            List of tuples (id1, id2, phash1, phash2)
        """
        self.connect()
        # self.conn.row_factory = None  # Faster for many results
        
        # A full self-join on 1M files with OR can be slow.
        # It's better to use 4 separate joins or a UNION if needed, 
        # but SQLite handles small ORs okay if indexed.
        # We also filter f1.id < f2.id to get each pair once.
        
        query = '''
            SELECT f1.id, f2.id, f1.phash, f2.phash
            FROM files f1
            JOIN files f2 ON (
                f1.phash_c1 = f2.phash_c1 OR 
                f1.phash_c2 = f2.phash_c2 OR 
                f1.phash_c3 = f2.phash_c3 OR 
                f1.phash_c4 = f2.phash_c4
            )
            WHERE f1.id < f2.id
        '''
        
        try:
            return self.conn.execute(query).fetchall()
        except sqlite3.Error as e:
            logger.error(f"Candidate retrieval error: {e}")
            return []
        return cursor.fetchall()

    def iter_files_chunked(self, chunk_size=50000):
        """
        Yield files in chunks for memory-efficient processing.
        Use this for 1M+ file collections to avoid loading all into RAM.
        
        Args:
            chunk_size: Number of files per chunk
            
        Yields:
            List of sqlite3.Row objects
        """
        self.connect()
        offset = 0
        while True:
            cursor = self.conn.execute(
                "SELECT * FROM files LIMIT ? OFFSET ?", 
                (chunk_size, offset)
            )
            rows = cursor.fetchall()
            if not rows:
                break
            yield rows
            offset += chunk_size

    def get_file_count(self):
        """Return total file count without loading all data."""
        self.connect()
        cursor = self.conn.execute("SELECT COUNT(*) FROM files")
        return cursor.fetchone()[0]

    # --- Vector Index Status Methods ---
    
    def get_indexed_paths(self, engine):
        """Get set of paths already indexed by this engine."""
        self.connect()
        cursor = self.conn.execute(
            "SELECT path FROM vector_index_status WHERE engine = ?",
            (engine,)
        )
        return {row[0] for row in cursor.fetchall()}
    
    def mark_paths_indexed(self, paths, engine):
        """Mark paths as indexed by engine (batch operation)."""
        if not paths:
            return
        self.connect()
        data = [(p, engine) for p in paths]
        self.conn.executemany(
            "INSERT OR REPLACE INTO vector_index_status (path, engine) VALUES (?, ?)",
            data
        )
        self.conn.commit()
    
    def clear_vector_index_status(self, engine=None):
        """Clear index status for an engine or all engines."""
        self.connect()
        if engine:
            self.conn.execute("DELETE FROM vector_index_status WHERE engine = ?", (engine,))
        else:
            self.conn.execute("DELETE FROM vector_index_status")
        self.conn.commit()

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

    # --- Maintenance Methods ---

    def cleanup_missing_files(self, progress_callback=None):
        """
        Check all files in DB and remove those that no longer exist on disk.
        Returns number of removed files.
        """
        self.connect()
        # count total for progress
        total_files = self.get_file_count()
        if total_files == 0:
            return 0
            
        removed_count = 0
        processed = 0
        
        # Use existing chunk iterator
        chunk_iter = self.iter_files_chunked(chunk_size=5000)
        paths_to_remove = []
        
        for chunk in chunk_iter:
            for row in chunk:
                path = row['path']
                if not os.path.exists(path):
                    paths_to_remove.append(path)
            
            processed += len(chunk)
            if progress_callback:
                progress_callback(processed, total_files)
                
            # Batch removal to keep list size manageable
            if len(paths_to_remove) > 1000:
                self._remove_files_batch(paths_to_remove)
                removed_count += len(paths_to_remove)
                paths_to_remove = []
        
        # Remove remaining
        if paths_to_remove:
            self._remove_files_batch(paths_to_remove)
            removed_count += len(paths_to_remove)
            
        return removed_count

    def _remove_files_batch(self, paths):
        if not paths: return
        self.connect()
        # chunk the deletions too because sqlite has variable limit
        chunk_size = 900
        for i in range(0, len(paths), chunk_size):
            batch = paths[i:i+chunk_size]
            placeholders = ','.join(['?'] * len(batch))
            self.conn.execute(f"DELETE FROM files WHERE path IN ({placeholders})", batch)
        self.conn.commit()

    def cleanup_orphans(self):
        """Remove records in other tables that reference non-existent files."""
        self.connect()
        stats = {}
        
        # 1. Vector Index Status
        c = self.conn.execute("DELETE FROM vector_index_status WHERE path NOT IN (SELECT path FROM files)")
        stats['vector_status_removed'] = c.rowcount
        
        # 2. Cluster Members
        c = self.conn.execute("DELETE FROM cluster_members WHERE file_path NOT IN (SELECT path FROM files)")
        stats['cluster_members_removed'] = c.rowcount
        
        # 3. File Relations
        # This is ID based.
        c = self.conn.execute('''
            DELETE FROM file_relations 
            WHERE id1 NOT IN (SELECT id FROM files) 
               OR id2 NOT IN (SELECT id FROM files)
        ''')
        stats['relations_removed'] = c.rowcount
        
        # 4. Empty Clusters
        c = self.conn.execute('''
            DELETE FROM clusters 
            WHERE id NOT IN (SELECT DISTINCT cluster_id FROM cluster_members)
        ''')
        stats['empty_clusters_removed'] = c.rowcount
        
        self.conn.commit()
        return stats

    def optimize_database(self):
        """Run VACUUM and ANALYZE."""
        self.connect()
        # VACUUM cannot be run from within a transaction usually, autocommit needed?
        # sqlite3 api handles this generally if isolation_level is correct, but let's try.
        try:
            self.conn.execute("VACUUM")
            self.conn.execute("ANALYZE")
        except sqlite3.Error as e:
            logger.error(f"Optimization error: {e}")

