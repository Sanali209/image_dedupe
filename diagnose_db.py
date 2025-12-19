import sqlite3
import os

DB_PATH = "dedup_app.db"

def diagnose():
    if not os.path.exists(DB_PATH):
        print(f"DB not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("--- File Relations Summary ---")
    try:
        rows = cursor.execute("SELECT relation_type, COUNT(*) as cnt FROM file_relations GROUP BY relation_type").fetchall()
        for r in rows:
            print(f"Type '{r['relation_type']}': {r['cnt']}")
            
        print("\n--- Legacy Ignored Pairs Summary ---")
        rows = cursor.execute("SELECT reason, COUNT(*) as cnt FROM ignored_pairs GROUP BY reason").fetchall()
        for r in rows:
            print(f"Reason '{r['reason']}': {r['cnt']}")
            
    except Exception as e:
        print(f"Error querying DB: {e}")
        
    conn.close()

if __name__ == "__main__":
    diagnose()
