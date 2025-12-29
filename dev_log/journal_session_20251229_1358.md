# Session Journal: 2025-12-29 13:58

## Problem Statement
**WARNING**: `Missing file data for relation 257835 <-> 257836` appearing for each pair during scan/persist operations.

## Investigation Findings

### Root Cause Analysis

#### 1. Missing Foreign Key Constraints **(CRITICAL)**
The `file_relations` table (line 87-96 in database.py) has **NO foreign key constraints**:
```sql
CREATE TABLE IF NOT EXISTS file_relations (
    id1 INTEGER NOT NULL,
    id2 INTEGER NOT NULL,
    relation_type TEXT NOT NULL,
    distance REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id1, id2),
    CHECK (id1 < id2)
)
```

**Problem**: This allows relations to reference file IDs that don't exist in the `files` table (orphaned records).

**Comparison**: The `cluster_members` table (line 77) properly uses foreign keys:
```sql
FOREIGN KEY(cluster_id) REFERENCES clusters(id) ON DELETE CASCADE
```

#### 2. Data Flow Gap
When files are deleted via:
- `mark_deleted()` (line 404-408)
- `cleanup_missing_files()` (line 487-526)
- Manual deletion from file system

The corresponding relations in `file_relations` are NOT automatically removed, creating orphans.

#### 3. Cleanup Logic Exists BUT...
`cleanup_orphans()` (line 539-569) DOES remove orphaned relations:
```python
DELETE FROM file_relations 
WHERE id1 NOT IN (SELECT id FROM files) 
   OR id2 NOT IN (SELECT id FROM files)
```

**However**: This is a MANUAL maintenance operation, not enforced automatically.

#### 4. Race Conditions Possible
If a scan persists relations while files are being deleted elsewhere, timing issues can create orphans.

### Transaction Isolation Issues
- File deletion and relation persistence are not wrapped in the same transaction
- No FOREIGN KEY enforcement means SQLite won't prevent orphans

## Research: SQLite Best Practices 2024

### Foreign Keys 101:
1. **MUST enable per connection**: `PRAGMA foreign_keys = ON;` (NOT currently done!)
2. **Cascading Delete**: Use `ON DELETE CASCADE` to auto-remove dependent records
3. **Index Foreign Keys**: Improves JOIN and constraint check performance
4. **Define at CREATE TIME**: Adding FK constraints later requires table recreation

### Recommended Actions:
- ✅ Enable foreign keys pragma on connection
- ✅ Add `FOREIGN KEY` constraints to `file_relations`
- ✅ Use `ON DELETE CASCADE` to auto-cleanup orphans
- ✅ Add indexes on `id1`, `id2` columns
- ✅ Validate data integrity with `PRAGMA foreign_key_check;`

## Error Weak Points Identified

1. **Schema Design**: Missing FK constraints
2. **Pragma Missing**: Foreign keys not enabled
3. **Transaction Atomicity**: No guarantee of atomic file+relation operations
4. **Index Coverage**: Relations table lacks indexes on FK columns
5. **Error Handling**: `get_files_by_ids()` silently returns [] on SQL errors
6. **Data Validation**: No pre-insert validation that IDs exist
7. **Migration Path**: Need to handle existing orphaned data

## Next Steps
See `implementation_plan.md` for detailed fixing strategy.
