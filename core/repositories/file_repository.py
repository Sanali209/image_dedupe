"""
File Repository Module.

This module handles all database interactions related to file metadata and storage.
It acts as the Data Access Layer (DAL) for the 'files' table and associated
relations tables.
"""
import os
import sqlite3
from typing import List, Optional, Tuple, Any, Union
from loguru import logger
from core.models import FileRelation, RelationType

class FileRepository:
    """
    Repository for managing File entities and their relationships.
    
    Provides methods for CRUD operations on files, efficient batch retrieval,
    and managing file relationships (duplicates, similarities).
    """
    def __init__(self, db_manager):
        self.db = db_manager

    def upsert_file(self, path: str, phash: Optional[str], size: int, width: int, height: int, mtime: float) -> None:
        """
        Insert or update a file record in the database.

        Args:
            path: Absolute file path.
            phash: Perceptual hash string (optional).
            size: File size in bytes.
            width: Image width.
            height: Image height.
            mtime: Last modified timestamp.

        Raises:
            sqlite3.Error: If database operation fails.
        """
        try:
            self.db.connect()
            self.db.conn.execute('''
                INSERT INTO files (path, phash, file_size, width, height, last_modified)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    phash=excluded.phash,
                    file_size=excluded.file_size,
                    width=excluded.width,
                    height=excluded.height,
                    last_modified=excluded.last_modified
            ''', (path, phash, size, width, height, mtime))
            self.db.conn.commit()
        except sqlite3.Error:
            logger.exception(f"Database error in upsert_file for path: {path}")
            # We might want to re-raise if critical, but for now we log appropriately
            # raise

    def get_file_by_path(self, path: str) -> Optional[Any]:
        """
        Retrieve a file record by its absolute path.
        
        Args:
            path: Absolute path to the file.
            
        Returns:
            sqlite3.Row or None if not found.
        """
        self.db.connect()
        cursor = self.db.conn.execute("SELECT * FROM files WHERE path = ?", (path,))
        return cursor.fetchone()

    def get_file_by_id(self, file_id: int) -> Optional[Any]:
        """
        Retrieve a file record by its DB ID.
        
        Args:
            file_id: The primary key ID of the file.
            
        Returns:
            sqlite3.Row or None if not found.
        """
        self.db.connect()
        cursor = self.db.conn.execute("SELECT * FROM files WHERE id = ?", (file_id,))
        return cursor.fetchone()

    def get_files_by_ids(self, file_ids: List[int]) -> List[Any]:
        """
        Batch retrieve files by a list of IDs.

        Args:
            file_ids: List of integer file IDs.

        Returns:
            List of sqlite3.Row objects.
            
        Raises:
            sqlite3.Error: If database query fails.
        """
        if not file_ids: return []
        self.db.connect()
        
        # Deduplicate IDs
        ids = list(set(file_ids))
        
        # Optimize: SELECT * FROM files WHERE id IN (...)
        placeholders = ','.join('?' for _ in ids)
        query = f"SELECT * FROM files WHERE id IN ({placeholders})"
        try:
            cursor = self.db.conn.execute(query, ids)
            results = cursor.fetchall()
            
            # Log if some IDs are missing (helps diagnose orphan issues)
            found_ids = {r['id'] for r in results}
            missing_ids = set(ids) - found_ids
            if missing_ids:
                logger.warning(
                    f"get_files_by_ids: {len(missing_ids)} IDs not found in database: "
                    f"{list(missing_ids)[:10]}{'...' if len(missing_ids) > 10 else ''}"
                )
            
            return results
        except sqlite3.Error as e:
            logger.error(f"Failed to batch retrieve {len(ids)} file IDs: {e}")
            raise

    def get_all_files(self) -> List[Any]:
        """
        Retrieve ALL file records from the database.
        
        Returns:
            List of search results (sqlite3.Row).
        """
        self.db.connect()
        cursor = self.db.conn.execute("SELECT * FROM files")
        return cursor.fetchall()

    def get_files_in_roots(self, roots):
        """Retrieve files that reside within the specified root directories."""
        self.db.connect()
        if not roots:
            return []
            
        points = []
        params = []
        
        for root in roots:
            norm_root = os.path.normpath(root)
            points.append("(path = ? OR path LIKE ?)")
            params.append(norm_root)
            params.append(norm_root + os.sep + '%')
            
        query = "SELECT * FROM files WHERE " + " OR ".join(points)
        cursor = self.db.conn.execute(query, params)
        return cursor.fetchall()

    def mark_deleted(self, path):
        """Remove file from DB (e.g. after deletion)."""
        self.db.connect()
        self.db.conn.execute("DELETE FROM files WHERE path = ?", (path,))
        self.db.conn.commit()

    def move_file(self, old_path, new_path):
        """Update file path in DB, handling collisions."""
        self.db.connect()
        # If new_path exists, remove it first (overwrite logic in FS implies overwrite in DB)
        self.db.conn.execute("DELETE FROM files WHERE path = ?", (new_path,))
        self.db.conn.execute("UPDATE files SET path = ? WHERE path = ?", (new_path, old_path))
        self.db.conn.commit()

    # --- Relations Logic (ID-based) ---

    def add_relations_batch(self, relations: list, overwrite=True):
        """
        Batch insert relations with FK validation.
        Accepts List[FileRelation] (Pydantic models).
        
        Returns:
            Dict with statistics: {'added': int, 'skipped': int, 'errors': int}
        """
        if not relations: 
            return {'added': 0, 'skipped': 0, 'errors': 0}
        
        # Check if input is Pydantic models (preferred)
        is_pydantic = hasattr(relations[0], 'relation_type') and hasattr(relations[0], 'id1')
        
        data = []
        if is_pydantic:
            from core.models import FileRelation
            for r in relations:
                 if isinstance(r, FileRelation):
                     # Enforce sorting
                     s1, s2 = sorted((r.id1, r.id2))
                     # Store enum value
                     rtype = r.relation_type.value if hasattr(r.relation_type, 'value') else r.relation_type
                     data.append((s1, s2, rtype, r.distance))
        else:
            # Legacy Fallback (during migration of engines)
            logger.warning("add_relations_batch called with legacy tuples. Please migrate to FileRelation.")
            # Assume 4-tuple (id1, id2, type, dist) or 3-tuple
            for item in relations:
                if len(item) == 4:
                    i1, i2, r, d = item
                elif len(item) == 3:
                    i1, i2, r = item
                    d = None
                else: continue
                s1, s2 = sorted((i1, i2))
                data.append((s1, s2, r, d))

        if not data: 
            return {'added': 0, 'skipped': 0, 'errors': 0}

        self.db.connect()
        
        # Pre-validate that all referenced file IDs exist (prevent FK violations)
        all_ids = set()
        for s1, s2, _, _ in data:
            all_ids.add(s1)
            all_ids.add(s2)
        
        # Batch check existence
        placeholders = ','.join('?' for _ in all_ids)
        cursor = self.db.conn.execute(
            f"SELECT id FROM files WHERE id IN ({placeholders})",
            list(all_ids)
        )
        existing_ids = {row['id'] for row in cursor.fetchall()}
        
        # Filter to valid data only
        valid_data = []
        skipped = 0
        for s1, s2, rtype, dist in data:
            if s1 in existing_ids and s2 in existing_ids:
                valid_data.append((s1, s2, rtype, dist))
            else:
                skipped += 1
                logger.warning(f"Skipping relation {s1}<->{s2}: Referenced file IDs don't exist (orphan prevented)")
        
        if skipped > 0:
            logger.warning(f"add_relations_batch: Skipped {skipped}/{len(data)} invalid relations due to missing file IDs")
        
        if not valid_data:
            return {'added': 0, 'skipped': skipped, 'errors': 0}
        
        try:
            if overwrite:
                self.db.conn.executemany('''
                    INSERT INTO file_relations (id1, id2, relation_type, distance) VALUES (?, ?, ?, ?)
                    ON CONFLICT(id1, id2) DO UPDATE SET relation_type=excluded.relation_type, distance=excluded.distance
                ''', valid_data)
            else:
                 self.db.conn.executemany('''
                    INSERT INTO file_relations (id1, id2, relation_type, distance) VALUES (?, ?, ?, ?)
                    ON CONFLICT(id1, id2) DO NOTHING
                ''', valid_data)
            self.db.conn.commit()
            return {'added': len(valid_data), 'skipped': skipped, 'errors': 0}
        except sqlite3.Error as e:
            logger.error(f"Batch DB Relation Insert Error: {e}")
            return {'added': 0, 'skipped': skipped, 'errors': 1}

    # Legacy Aliases / Transitions
    add_ignored_pairs_batch = add_relations_batch

    def is_ignored(self, id1, id2):
        """
        Check if pair is 'ignored' (i.e. has a USER decision that filters it out).
        Logic: Return True if relation exists AND value != 'new_match' (and != 'duplicate'?)
        Actually, existing logic was: if it is ignored, hide it.
        New logic: Check explicit visibility.
        """
        return self.db.is_ignored(id1, id2)

    def get_relation(self, id1, id2):
        """Get relation object or None."""
        # This could return Pydantic object
        # For now, simplistic
        reason = self.db.get_ignore_reason(id1, id2) # DB method needs update?
        return reason

    # Alias
    get_ignore_reason = get_relation

    def remove_relation(self, id1, id2):
        try:
            i1, i2 = int(id1), int(id2)
        except: return
        s1, s2 = sorted((i1, i2))
        self.db.connect()
        self.db.conn.execute("DELETE FROM file_relations WHERE id1 = ? AND id2 = ?", (s1, s2))
        self.db.conn.commit()
        
    remove_ignored_pair = remove_relation

    def get_ignore_reason(self, id1, id2):
        return self.db.get_ignore_reason(id1, id2)
    
        
    # --- Scanned Paths (Configuration) ---
    # Kept here for simplicity as requested
    
    def add_scanned_path(self, path):
        self.db.connect()
        self.db.conn.execute("INSERT OR IGNORE INTO scanned_paths (path) VALUES (?)", (path,))
        self.db.conn.commit()

    def get_scanned_paths(self):
        self.db.connect()
        cursor = self.db.conn.execute("SELECT path FROM scanned_paths")
        return [row['path'] for row in cursor.fetchall()]

    def remove_scanned_path(self, path):
        self.db.connect()
        self.db.conn.execute("DELETE FROM scanned_paths WHERE path = ?", (path,))
        self.db.conn.commit()

    def get_all_relations(self) -> List[FileRelation]:
        """
        Retrieve all file relations from the database (file_relations table).
        
        Returns:
            List of FileRelation objects.
        """
        self.db.connect()
        cursor = self.db.conn.execute("SELECT id1, id2, relation_type, distance FROM file_relations")
        rows = cursor.fetchall()
        
        relations = []
        for row in rows:
            r_type = row['relation_type']
            try:
                try:
                    rel_enum = RelationType(r_type)
                except ValueError:
                    rel_enum = RelationType.NEW_MATCH 
                    
                rel = FileRelation(
                    id1=row['id1'],
                    id2=row['id2'],
                    relation_type=rel_enum,
                    distance=row['distance'] if row['distance'] is not None else 0.0
                )
                relations.append(rel)
            except Exception as e:
                logger.warning(f"Error parsing relation {row['id1']}-{row['id2']}: {e}")
                
        return relations

    def get_relations_by_threshold(self, threshold: float) -> List[FileRelation]:
        """
        Retrieve file relations filtered by threshold (distance <= threshold).
        
        Args:
            threshold: Maximum distance value to include.
        
        Returns:
            List of FileRelation objects with distance <= threshold.
        """
        self.db.connect()
        cursor = self.db.conn.execute(
            "SELECT id1, id2, relation_type, distance FROM file_relations WHERE distance <= ? OR distance IS NULL",
            (threshold,)
        )
        rows = cursor.fetchall()
        
        relations = []
        for row in rows:
            r_type = row['relation_type']
            try:
                try:
                    rel_enum = RelationType(r_type)
                except ValueError:
                    rel_enum = RelationType.NEW_MATCH 
                    
                rel = FileRelation(
                    id1=row['id1'],
                    id2=row['id2'],
                    relation_type=rel_enum,
                    distance=row['distance'] if row['distance'] is not None else 0.0
                )
                relations.append(rel)
            except Exception as e:
                logger.warning(f"Error parsing relation {row['id1']}-{row['id2']}: {e}")
                
        return relations
