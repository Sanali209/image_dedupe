# Analysis: Annotated Pairs Re-appearing Bug

## Problem Statement
User annotates a pair (e.g., marks as "duplicate" or "similar"), but when they run a second scan, the **same pair appears again** as if it were new, instead of staying hidden.

## Root Cause Analysis

### Data Flow on First Scan
1. Engine finds pair (1, 2) with distance=5
2. Engine calls `file_repo.add_relations_batch([FileRelation(id1=1, id2=2, type=NEW_MATCH)])` 
3. Repo inserts: `INSERT ... VALUES (1, 2, 'new_match', 5) ON CONFLICT DO NOTHING`
4. User sees pair in UI
5. User clicks "Duplicate" button
6. UI calls `db.add_ignored_pair_id(1, 2, 'duplicate')`
7. DB updates: `INSERT ... VALUES (1, 2, 'duplicate', 5) ON CONFLICT DO UPDATE ...`
8. Relation now stored as `(1, 2, 'duplicate', 5)` ✅

### Data Flow on Second Scan
1. Engine **re-discovers** same pair (1, 2) with distance=5
2. Engine calls `file_repo.add_relations_batch([FileRelation(id1=1, id2=2, type=NEW_MATCH)])`
3. Repo tries: `INSERT ... VALUES (1, 2, 'new_match', 5) ON CONFLICT DO NOTHING` ❌
4. **ON CONFLICT DO NOTHING** = Database keeps existing `'duplicate'` status! No update!
5. Deduper reads from DB: `get_ignore_reason(1, 2)` returns `'duplicate'`
6. Deduper reconciliation (line 133-140) updates the in-memory relation type to 'duplicate'
7. Deduper filtering (line 143-147): if include_ignored=False, skip non-NEW_MATCH
8. **BUT** - the relation is still being returned because...

Wait, let me check the deduper logic more carefully...

Actually, looking at lines 143-147:
```python
if not include_ignored:
    if rel.relation_type != RelationType.NEW_MATCH:
        continue
```

This SHOULD filter it out. So why is it showing?

Let me check if the reconciliation is even happening...

## Wait - I Found It!

Looking at the logs:
```
INFO PHashEngine: Persisted 34 relations, skipped 0
INFO Persisting 34 relations to database...
INFO Persist complete: 34 added, 0 skipped
```

It says **"34 added, 0 skipped"** - this means the INSERT with ON CONFLICT succeeded!

But if the relation already exists with type='duplicate', how did it "add" 34?

**AH! The issue is `overwrite=False` logic!**

Looking at file_repository.py line 211:
```python
else:
     self.db.conn.executemany('''
        INSERT INTO file_relations (id1, id2, relation_type, distance) VALUES (?, ?, ?, ?)
        ON CONFLICT(id1, id2) DO NOTHING
    ''', valid_data)
```

With `ON CONFLICT DO NOTHING`, SQLite:
- Does NOT insert if the pair already exists
- Does NOT update the existing record
- Returns SUCCESS (no error)
- **executemany reports success even though nothing changed!**

So the "34 added" is MISLEADING - it's just that executemany didn't fail. The actual DB state didn't change.

## The Real Bug

The reconciliation in deduper.py (lines 122-150) is CORRECT - it reads from DB and updates the relation type. But there's a timing issue:

1. **Engines call `save_relations()` BEFORE the deduper returns** (line 120)
2. Deduper then reconciles and filters (lines 122-150)
3. **But engines ALSO persist during find_duplicates()!**

Let me check the engine code... Yes! In phash.py line 308:
```python
self.file_repo.add_relations_batch(found_matches, overwrite=False)
```

And in base.py line 327:
```python
self.file_repo.add_relations_batch(unique_pairs, overwrite=False)
```

So the engine persists, then returns the relations, then deduper ALSO calls save_relations()!

**DOUBLE PERSISTENCE!**

But the real issue is: the engines persist with `overwrite=False`, which uses `DO NOTHING`, so annotated pairs keep their annotation.

Then the deduper's reconciliation reads the DB and SHOULD filter them out... but let me check if that's actually happening...

## Testing the Reconciliation

Looking at deduper.py line 133:
```python
existing_type = self.db_manager.get_ignore_reason(rel.id1, rel.id2)
```

This reads the DB. If the pair was annotated as 'duplicate', this should return 'duplicate'.

Then line 138:
```python
rel.relation_type = RelationType(existing_type)
```

Updates the relation object to 'duplicate'.

Then line 146:
```python
if rel.relation_type != RelationType.NEW_MATCH:
    continue
```

Should skip it!

**So why is it still appearing?**

## Hypothesis: The reconciliation isn't working

Possible reasons:
1. `get_ignore_reason` is failing
2. The relation objects from engines aren't being passed through reconciliation
3. The UI is bypassing the deduper's filtering

Let me check the UI... results_view.py line 514:
```python
if existing_results is not None:
     relations = existing_results
```

If `existing_results` is passed (from a previous scan), it bypasses the deduper entirely!

Let me check where load_results is called with existing_results...

Looking at mainwindow.py or scan logic... I need to find where load_results(existing_results=...) is called.

Actually, the user said "on second scan" - so it's running a full scan, not loading previous results. So line 521 should execute:
```python
relations = self.deduper.find_duplicates(...)
```

Which goes through reconciliation.

## New Theory: Batch Fetching Issue

Wait! I see it now. Looking at results_view.py lines 557-561:

```python
for rel in valid_relations:
    is_visible = rel.is_visible
    
    if not self.include_ignored and not is_visible:
        continue
```

It's checking `rel.is_visible`, which comes from the FileRelation object's property:

```python
@property
def is_visible(self) -> bool:
    return self.relation_type == RelationType.NEW_MATCH
```

So if the deduper's reconciliation updated the relation_type to 'duplicate', is_visible should be False, and it should be skipped!

**Unless... the deduper is NOT returning the reconciled relations!**

Let me check line 151:
```python
final_relations = reconciled
return final_relations
```

It DOES return the reconciled list.

## FOUND IT!

Looking at phash.py line 308 again:
```python
self.file_repo.add_relations_batch(found_matches, overwrite=False)
```

The engine persists the relations DURING find_duplicates(), BEFORE returning!

Then look at what the engine returns - line 337 in phash.py GPU path:
```python
return final_groups  # THIS IS GROUPS, NOT RELATIONS!
```

The GPU path returns GROUPS (list of file lists), not FileRelation objects!

And in deduper.py lines 82-116, there's legacy code to convert groups to relations!

**So the reconciliation logic (lines 122-150) is iterating over freshly-created relations from the groups, NOT the relations that were persisted!**

## The ACTUAL Bug

The deduper creates NEW FileRelation objects from the groups (lines 110-116), with relation_type=NEW_MATCH hardcoded!

These new objects don't reflect the DB state - they're always NEW_MATCH.

The reconciliation (line 133) reads the DB and updates the NEW relation objects... but wait, that should still work!

Unless... let me check if reconciliation is even running...

Actually, looking at the flow again:
1. Engine returns groups
2. Deduper converts groups to FileRelation objects (all NEW_MATCH)
3. Deduper calls save_relations() - which tries to INSERT with DO NOTHING
4. Deduper reconciliation reads DB and updates relation types
5. Deduper filters based on updated types
6. Should return empty list if all are annotated!

But the user says they're seeing them... so either:
- Reconciliation isn't running
- OR the UI is getting the results before reconciliation
- OR there's a bug in the filter logic

Let me check if include_ignored is being set correctly...

The logs say: "Built 34 pairs for display (Visible only: True)"

"Visible only: True" means it's filtering (not include_ignored=True).

So it SHOULD be filtering... but it's not.

## FINAL DIAGNOSIS

I need to add debug logging to see:
1. What relation_type the relations have after reconciliation
2. Whether the filter is actually running

But I suspect the issue is that the **engine's double-persistence is the problem** - engines shouldn't be persisting at all, only the deduper should persist.

Or,  alternatively, engines should use `overwrite=True` so that re-discovered pairs reset to NEW_MATCH (which might be the desired behavior?).

Actually, thinking about it logically:
- If a pair was marked "not duplicate" and the engine finds it again, should it:
  A) Stay marked as "not duplicate" (current behavior)
  B) Reset to "new match" for re-review (maybe better UX?)

I think option B makes more sense - if the algorithm keeps finding it, maybe the user made a mistake or conditions changed.

But for now, the immediate fix is to ensure reconciliation works and annotated pairs don't appear when include_ignored=False.
