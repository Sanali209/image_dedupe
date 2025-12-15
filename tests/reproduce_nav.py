
class MockDB:
    def is_ignored(self, h1, h2):
        # MOCK: Pair (0, 3) is ignored
        if h2 == 'hash_3': return True
        return False

class MockResultsView:
    def __init__(self):
        self.include_ignored = False
        self.db = MockDB()
    
    def is_pair_visible(self, left, right):
        if self.include_ignored: return True
        h1 = left['phash']
        h2 = right['phash']
        return not self.db.is_ignored(h1, h2)

    def find_next_visible_index(self, group, start_index, direction=1):
        idx = start_index
        while 1 <= idx < len(group):
            if self.is_pair_visible(group[0], group[idx]):
                print(f"  Found visible at {idx}")
                return idx
            else:
                print(f"  Skipping hidden at {idx}")
            idx += direction
        print("  Reached end, no visible found.")
        return -1

def test_nav():
    view = MockResultsView()
    group = [
        {'phash': 'hash_0'}, # Left (Hub)
        {'phash': 'hash_1'},
        {'phash': 'hash_2'},
        {'phash': 'hash_3'}, # Ignored
        {'phash': 'hash_4'},
        {'phash': 'hash_5'}
    ] # Size 6. Indices 0..5. Valid right indices: 1..5.

    print("\nTest 1: Normal Next (1 -> 2)")
    # Current right=1. update_comparison checks find_next(group, 2, 1)
    res = view.find_next_visible_index(group, 2, 1)
    assert res == 2, f"Failed: Expected 2, got {res}"

    print("\nTest 2: Skip Ignored (2 -> 4)")
    # Current right=2. Next is 3 (Ignored). Should return 4.
    res = view.find_next_visible_index(group, 3, 1)
    assert res == 4, f"Failed: Expected 4, got {res}"

    print("\nTest 3: End of List (4 -> 5 -> End)")
    # Current right=4. Next is 5.
    res = view.find_next_visible_index(group, 5, 1)
    assert res == 5, f"Expected 5, got {res}"
    
    # Current right=5. Next is 6? (Out of bounds)
    res = view.find_next_visible_index(group, 6, 1)
    assert res == -1, f"Expected -1, got {res}"

    print("\nTest 4: Prev Skip Ignored (4 -> 2)")
    # Current right=4. Prev is 3 (Ignored). Should return 2.
    res = view.find_next_visible_index(group, 3, -1)
    assert res == 2, f"Expected 2, got {res}"

    print("\nPASS: Navigation logic seems correct.")

if __name__ == "__main__":
    test_nav()
