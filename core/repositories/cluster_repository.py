"""
Cluster Repository Module.

Manages the persistence of 'Clusters' (sticky groups) and their members.
Handles CRUD operations for clusters and association of files to them.
"""
from loguru import logger
import sqlite3
from typing import List, Optional, Union, Dict, Any
from core.models import ClusterMember

class ClusterRepository:
    """
    Repository for managing User-Defined Clusters.
    
    Clusters are persistent groups of files that 'stick' together across scans.
    """
    def __init__(self, db_manager):
        self.db = db_manager

    def create_cluster(self, name: str, target_folder: str = "") -> int:
        """
        Create a new cluster.

        Args:
            name: Display name of the cluster.
            target_folder: Optional path where files should be moved.

        Returns:
            The new Cluster ID.

        Raises:
            sqlite3.Error: If DB insertion fails.
        """
        try:
            self.db.connect()
            cursor = self.db.conn.execute("INSERT INTO clusters (name, target_folder) VALUES (?, ?)", (name, target_folder))
            self.db.conn.commit()
            return cursor.lastrowid
        except sqlite3.Error:
            logger.exception(f"Failed to create cluster '{name}'")
            return -1

    def update_cluster(self, cluster_id: int, name: Optional[str] = None, target_folder: Optional[str] = None) -> None:
        """
        Update cluster metadata.

        Args:
            cluster_id: ID of the cluster to update.
            name: New name (optional).
            target_folder: New target folder (optional).
        """
        try:
            self.db.connect()
            if name is not None:
                self.db.conn.execute("UPDATE clusters SET name = ? WHERE id = ?", (name, cluster_id))
            if target_folder is not None:
                self.db.conn.execute("UPDATE clusters SET target_folder = ? WHERE id = ?", (target_folder, cluster_id))
            self.db.conn.commit()
        except sqlite3.Error:
            logger.exception(f"Failed to update cluster {cluster_id}")

    def delete_cluster(self, cluster_id):
        self.db.connect()
        self.db.conn.execute("DELETE FROM clusters WHERE id = ?", (cluster_id,))
        self.db.conn.commit()

    def add_cluster_members(self, cluster_id: int, files: Union[List[ClusterMember], List[Any]]) -> None:
        """
        Add files to a cluster.

        Args:
            cluster_id: Target cluster ID.
            files: List of ClusterMember objects (preferred) or legacy dicts/paths.
        """
        if not files: return
        
        self.db.connect()
        data = []
        
        # Check if input is Pydantic models (preferred)
        # We check the first item to guess type
        first = files[0]
        is_pydantic = hasattr(first, 'cluster_id')
        
        if is_pydantic:
             from core.models import ClusterMember
             for f in files:
                 if isinstance(f, ClusterMember):
                     data.append((f.cluster_id, f.file_path))
        else:
            # Legacy Fallback
            for f in files:
                path = f if isinstance(f, str) else f['path']
                data.append((cluster_id, path))
        
        if not data: return
        
        try:
            self.db.conn.executemany("INSERT OR IGNORE INTO cluster_members (cluster_id, file_path) VALUES (?, ?)", data)
            self.db.conn.commit()
        except sqlite3.Error:
            logger.exception(f"Failed to add {len(data)} members to cluster {cluster_id}")

    def remove_cluster_member(self, cluster_id, path):
        self.db.connect()
        self.db.conn.execute("DELETE FROM cluster_members WHERE cluster_id = ? AND file_path = ?", (cluster_id, path))
        self.db.conn.commit()

    def remove_all_cluster_members(self, cluster_id):
        self.db.connect()
        self.db.conn.execute("DELETE FROM cluster_members WHERE cluster_id = ?", (cluster_id,))
        self.db.conn.commit()

    def delete_all_clusters(self):
        self.db.connect()
        self.db.conn.execute("DELETE FROM cluster_members")
        self.db.conn.execute("DELETE FROM clusters")
        self.db.conn.commit()

    def get_clusters(self):
        self.db.connect()
        cursor = self.db.conn.execute("SELECT * FROM clusters ORDER BY id")
        return cursor.fetchall()
        
    def get_all_cluster_members(self):
        """Return dict: path -> cluster_id"""
        self.db.connect()
        cursor = self.db.conn.execute("SELECT cluster_id, file_path FROM cluster_members")
        return {row['file_path']: row['cluster_id'] for row in cursor.fetchall()}
        
    def get_cluster_members(self, cluster_id):
        self.db.connect()
        cursor = self.db.conn.execute("SELECT file_path FROM cluster_members WHERE cluster_id = ?", (cluster_id,))
        return [row['file_path'] for row in cursor.fetchall()]
