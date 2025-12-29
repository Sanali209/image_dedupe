"""
Database Diagnostic Script for Orphaned Relations

This script checks the database for orphaned relations and provides
statistics about data integrity issues.
"""

import sqlite3
import sys

def check_database_integrity(db_path="dedup_app.db"):
    """Run comprehensive integrity checks on the database."""
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("=" * 70)
    print("DATABASE INTEGRITY DIAGNOSTIC")
    print("=" * 70)
    print()
    
    # 1. Check if foreign keys are enabled
    print("1. Foreign Key Status:")
    cursor.execute("PRAGMA foreign_keys;")
    fk_status = cursor.fetchone()[0]
    if fk_status == 1:
        print("   ✅ Foreign keys are ENABLED")
    else:
        print("   ⚠️  Foreign keys are DISABLED")
    print()
    
    # 2. Count total files
    print("2. File Statistics:")
    cursor.execute("SELECT COUNT(*) FROM files")
    total_files = cursor.fetchone()[0]
    print(f"   Total files in database: {total_files:,}")
    print()
    
    # 3. Count total relations
    print("3. Relation Statistics:")
    cursor.execute("SELECT COUNT(*) FROM file_relations")
    total_relations = cursor.fetchone()[0]
    print(f"   Total relations in database: {total_relations:,}")
    print()
    
    # 4. Check for orphaned relations (CRITICAL)
    print("4. Orphaned Relations Check:")
    cursor.execute("""
        SELECT COUNT(*) FROM file_relations 
        WHERE id1 NOT IN (SELECT id FROM files) 
           OR id2 NOT IN (SELECT id FROM files)
    """)
    orphaned_count = cursor.fetchone()[0]
    
    if orphaned_count == 0:
        print("   ✅ No orphaned relations found")
    else:
        print(f"   ❌ FOUND {orphaned_count:,} ORPHANED RELATIONS")
        print(f"      These relations reference file IDs that no longer exist!")
        
        # Show some examples
        print("\n   Sample orphaned relations:")
        cursor.execute("""
            SELECT id1, id2, relation_type, distance
            FROM file_relations 
            WHERE id1 NOT IN (SELECT id FROM files) 
               OR id2 NOT IN (SELECT id FROM files)
            LIMIT 10
        """)
        for row in cursor.fetchall():
            print(f"      - Relation: {row['id1']} <-> {row['id2']} (type: {row['relation_type']})")
    print()
    
    # 5. Check for orphaned vector index entries
    print("5. Orphaned Vector Index Entries:")
    cursor.execute("""
        SELECT COUNT(*) FROM vector_index_status 
        WHERE path NOT IN (SELECT path FROM files)
    """)
    orphaned_vectors = cursor.fetchone()[0]
    if orphaned_vectors == 0:
        print("   ✅ No orphaned vector index entries")
    else:
        print(f"   ⚠️  Found {orphaned_vectors:,} orphaned vector index entries")
    print()
    
    # 6. Check for orphaned cluster members
    print("6. Orphaned Cluster Members:")
    cursor.execute("""
        SELECT COUNT(*) FROM cluster_members 
        WHERE file_path NOT IN (SELECT path FROM files)
    """)
    orphaned_clusters = cursor.fetchone()[0]
    if orphaned_clusters == 0:
        print("   ✅ No orphaned cluster members")
    else:
        print(f"   ⚠️  Found {orphaned_clusters:,} orphaned cluster members")
    print()
    
    # 7. Check table schema for FK constraints
    print("7. Schema Analysis:")
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='file_relations'")
    schema = cursor.fetchone()[0]
    
    if "FOREIGN KEY" in schema:
        print("   ✅ file_relations table HAS foreign key constraints")
    else:
        print("   ❌ file_relations table LACKS foreign key constraints")
        print("      This allows orphaned relations to be created!")
    print()
    
    # Summary
    print("=" * 70)
    print("SUMMARY:")
    print("=" * 70)
    
    issues_found = []
    if fk_status == 0:
        issues_found.append("Foreign keys are disabled")
    if orphaned_count > 0:
        issues_found.append(f"{orphaned_count:,} orphaned relations")
    if orphaned_vectors > 0:
        issues_found.append(f"{orphaned_vectors:,} orphaned vector entries")
    if orphaned_clusters > 0:
        issues_found.append(f"{orphaned_clusters:,} orphaned cluster members")
    if "FOREIGN KEY" not in schema:
        issues_found.append("Missing FK constraints in schema")
    
    if issues_found:
        print("❌ ISSUES DETECTED:")
        for issue in issues_found:
            print(f"   • {issue}")
        print("\n💡 RECOMMENDED ACTIONS:")
        print("   1. Review implementation_plan.md for fixing strategy")
        print("   2. Run database.cleanup_orphans() to remove orphaned data")
        print("   3. Apply schema migration to add FK constraints")
    else:
        print("✅ No integrity issues detected! Database is healthy.")
    
    print("=" * 70)
    
    conn.close()
    return orphaned_count

if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "dedup_app.db"
    orphaned = check_database_integrity(db_path)
    sys.exit(0 if orphaned == 0 else 1)
