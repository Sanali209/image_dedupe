from loguru import logger
import pickle
import os

class BKNode:
    def __init__(self, item, hash_val):
        self.item = item
        self.hash_val = hash_val
        self.children = {} # distance -> BKNode

class BKTree:
    def __init__(self, distance_func):
        self.root = None
        self.distance_func = distance_func
        self._size = 0

    def add(self, item, hash_val):
        if self.root is None:
            self.root = BKNode(item, hash_val)
            self._size = 1
            return

        node = self.root
        while True:
            dist = self.distance_func(node.hash_val, hash_val)
            if dist in node.children:
                node = node.children[dist]
            else:
                node.children[dist] = BKNode(item, hash_val)
                self._size += 1
                break

    def query(self, hash_val, threshold):
        """Returns list of (item, distance)"""
        results = []
        if self.root is None:
            return results

        # Iterative search using stack to avoid recursion depth issues
        stack = [self.root]
        
        while stack:
            node = stack.pop()
            dist = self.distance_func(node.hash_val, hash_val)
            
            if dist <= threshold:
                results.append((node.item, dist))
            
            # Optimization: Triangle inequality
            # We only need to check children with edge weight d_child
            # such that: dist - threshold <= d_child <= dist + threshold
            start = dist - threshold
            end = dist + threshold
            
            for d_child, child_node in node.children.items():
                if start <= d_child <= end:
                    stack.append(child_node)
                    
        return results

    def size(self):
        """Return number of items in tree."""
        return self._size

    def save(self, filepath):
        """Save tree to disk using pickle."""
        try:
            with open(filepath, 'wb') as f:
                pickle.dump((self.root, self._size), f)
            logger.info(f"BKTree saved to {filepath} ({self._size} items)")
        except Exception as e:
            logger.error(f"Failed to save BKTree: {e}")

    def load(self, filepath):
        """Load tree from disk. Returns True if successful."""
        if not os.path.exists(filepath):
            return False
        try:
            with open(filepath, 'rb') as f:
                self.root, self._size = pickle.load(f)
            logger.info(f"BKTree loaded from {filepath} ({self._size} items)")
            return True
        except Exception as e:
            logger.warning(f"Failed to load BKTree: {e}")
            return False
