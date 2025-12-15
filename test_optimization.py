
from core.database import DatabaseManager
from core.deduper import Deduper
import os

def test_optimization():
    if os.path.exists("test_opt.db"): os.remove("test_opt.db")
    db = DatabaseManager("test_opt.db")
    deduper = Deduper(db)
    
    # Create a group of 5 items
    group = [
        {'path': 'a', 'phash': None},
        {'path': 'b', 'phash': None},
        {'path': 'c', 'phash': None},
        {'path': 'd', 'phash': None},
        {'path': 'e', 'phash': None}
    ]
    
    # Old logic: 5*4/2 = 10 pairs
    # New logic: 4 pairs (a-b, a-c, a-d, a-e)
    
    deduper.save_ai_matches([group])
    
    rows = db.conn.execute("SELECT * FROM ignored_pairs").fetchall()
    print(f"Pairs persisted: {len(rows)}")
    
    if len(rows) == 4:
        print("PASS: Optimized Star Topology confirmed (4 pairs).")
    else:
        print(f"FAIL: Expected 4 pairs, got {len(rows)}.")

    db.close()
    if os.path.exists("test_opt.db"): os.remove("test_opt.db")

if __name__ == "__main__":
    test_optimization()
