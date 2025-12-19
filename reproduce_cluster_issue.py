import sqlite3
import os
from core.models import RelationType
from core.repositories.file_repository import FileRepository
from core.cluster_services import GraphBuilder
from core.database import DatabaseManager

def test_clustering():
    # Setup In-Memory DB for speed/safety
    db = DatabaseManager(":memory:")
    db.init_db()
    
    # Insert Files
    db.connect()
    db.conn.execute("INSERT INTO files (path, phash, file_size, width, height, last_modified) VALUES (?, ?, ?, ?, ?, ?)", 
                    ("C:/test/a.jpg", "hash1", 1000, 100, 100, 0))
    db.conn.execute("INSERT INTO files (path, phash, file_size, width, height, last_modified) VALUES (?, ?, ?, ?, ?, ?)", 
                    ("C:/test/b.jpg", "hash2", 1000, 100, 100, 0))
    
    # Get IDs
    cur = db.conn.execute("SELECT id FROM files")
    ids = [r[0] for r in cur.fetchall()]
    id1, id2 = ids[0], ids[1]
    db.conn.commit()
    
    repo = FileRepository(db)
    
    # Insert 'duplicate' relation (simulate User Annotation)
    print(f"Adding relation: {id1} <-> {id2} as 'duplicate'")
    # Note: add_relations_batch expects objects, but we can use db direct for test or mock objects
    # Let's use db direct to simulate what ResultsView calls
    db.add_ignored_pair_id(id1, id2, reason='duplicate')
    
    # Verify DB content
    rels = repo.get_all_relations()
    print(f"Relations in DB: {len(rels)}")
    print(f"Type: {rels[0].relation_type} (Type: {type(rels[0].relation_type)})")
    
    # Configure Criteria
    criteria = {
        'exact_hash': False,
        'duplicate': True,  # TARGET
        'new_match': False,
        'near_duplicate': False,
        'similar': False,
        'not_duplicate': False
    }
    
    # Build Graph
    files = repo.get_all_files() # dicts/rows
    builder = GraphBuilder(db, repo)
    
    components = builder.build_graph_and_find_components(files, criteria)
    
    print(f"Components found: {len(components)}")
    if components:
        print(f"Cluster 1: {components[0]}")
    else:
        print("FAIL: No clusters found for 'duplicate'.")

if __name__ == "__main__":
    test_clustering()
