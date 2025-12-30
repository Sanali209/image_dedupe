# Critical Fix: Annotation Persistence Bug

## Problem
Annotations were being lost every time the application started, causing previously annotated pairs to reappear as "new matches" on subsequent scans.

## Root Cause
In `database.py` line 98, there was a `DROP TABLE IF EXISTS file_relations` statement that was **destroying the entire table** (and all annotations) every time `init_db()` was called at app startup.

This was apparently added during a migration to add foreign key constraints, but it should have been removed after the migration was complete.

## Impact
- First scan: User annotates 100 pairs as "duplicate"
- Restart app
- Second scan: **All 100 annotated pairs reappear as "new matches"** ❌
- User's work lost!

## Fix Applied

**File**: `database.py` lines 96-101

**Before**:
```python
# File Relations Table (ID-based, primary storage for duplicates)
# DROP existing table to recreate with FK constraints (BREAKING CHANGE)
cursor.execute("DROP TABLE IF EXISTS file_relations")

cursor.execute('''
    CREATE TABLE file_relations (
```

**After**:
```python
# File Relations Table (ID-based, primary storage for duplicates)
# NOTE: Table created with foreign key constraints. Annotations persist across app restarts.

cursor.execute('''
    CREATE TABLE IF NOT EXISTS file_relations (
```

## Changes
1. **Removed**: `DROP TABLE IF EXISTS file_relations`
2. **Changed**: `CREATE TABLE` → `CREATE TABLE IF NOT EXISTS`

## Result
- ✅ Annotations now persist across app restarts
- ✅ Rescanning the same folder shows only NEW pairs (previously annotated pairs stay hidden)
- ✅ Database reconciliation works correctly

## Important Note
If you already have a database without foreign keys and need to add them, you'll need to migrate manually:

```sql
-- Save existing relations
CREATE TABLE file_relations_backup AS SELECT * FROM file_relations;

-- Drop old table
DROP TABLE file_relations;

-- Create new table with FK constraints
CREATE TABLE file_relations ( ... with FOREIGN KEY ... );

-- Restore data
INSERT INTO file_relations SELECT * FROM file_relations_backup 
  WHERE id1 IN (SELECT id FROM files) AND id2 IN (SELECT id FROM files);

-- Clean up
DROP TABLE file_relations_backup;
```

But for the user's case, the table already has FK constraints (was created after the DROP), so this fix is safe.
