"""
Data Models Module.

Defines the core domain entities using Pydantic for validation and type safety.
Includes models for Files, Relations, and Clusters.
"""
from enum import Enum
from typing import Optional, List
import os
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

class RelationType(str, Enum):
    """
    Enumeration of all possible relationship types between two files.
    """
    # System Types
    NEW_MATCH = 'new_match'           # Unreviewed match
    
    # User Decision Types
    DUPLICATE = 'duplicate'           # Confirmed exact duplicate
    NEAR_DUPLICATE = 'near_duplicate' # very close, maybe compression artifacts
    CROP_DUPLICATE = 'crop_duplicate' # one is crop of another
    SIMILAR = 'similar'               # generic similar
    SIMILAR_STYLE = 'similar_style'   # style match
    SAME_PERSON = 'same_person'       # face match
    SAME_IMAGE_SET = 'same_image_set' # burst mode, etc.
    OTHER = 'other'                   # miscellaneous
    
    # Negative Types
    NOT_DUPLICATE = 'not_duplicate'   # Explicitly rejected

class File(BaseModel):
    """
    Represents a file on disk.
    
    Attributes:
        id: Database ID.
        path: Absolute file path.
        phash: Perceptual Hash string.
        file_size: Size in bytes.
        width: Image width.
        height: Image height.
        last_modified: Timestamp.
    """
    id: int
    path: str
    phash: Optional[str] = None
    file_size: int = 0
    width: int = 0
    height: int = 0
    last_modified: float = 0.0

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

class FileRelation(BaseModel):
    """
    Represents a relationship between two files.
    
    Attributes:
        id1: ID of the first file (usually smaller ID).
        id2: ID of the second file (usually larger ID).
        relation_type: The nature of the relationship.
        distance: Similarity distance (0.0 = identical).
        created_at: Timestamp of creation.
    """
    id1: int
    id2: int
    relation_type: RelationType
    distance: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.now)
    
    @property
    def is_visible(self) -> bool:
        """
        Visibility Logic:
        - NEW_MATCH: Visible when 'Show Annotated' is FALSE (User has not acted yet).
        - OTHERS: Visible ONLY when 'Show Annotated' is TRUE (User has acted).
        """
        return self.relation_type == RelationType.NEW_MATCH

class Cluster(BaseModel):
    """
    Represents a user-defined group of files (sticky cluster).
    
    Attributes:
        id: Cluster ID.
        name: User-friendly name.
        target_folder: Optional target directory.
    """
    id: Optional[int] = None
    name: str
    target_folder: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    
class ClusterMember(BaseModel):
    """
    Association between a Cluster and a File.
    
    Attributes:
        cluster_id: ID of the parent cluster.
        file_path: Path of the member file.
    """
    cluster_id: int
    file_path: str
    added_at: datetime = Field(default_factory=datetime.now)

    @field_validator('file_path')
    @classmethod
    def normalize_path(cls, v: str) -> str:
        return os.path.normpath(v)
