from loguru import logger

class BKNode:
    def __init__(self, item, hash_val):
        self.item = item
        self.hash_val = hash_val
        self.children = {} # distance -> BKNode

class BKTree:
    def __init__(self, distance_func):
        self.root = None
        self.distance_func = distance_func

    def add(self, item, hash_val):
        if self.root is None:
            self.root = BKNode(item, hash_val)
            return

        node = self.root
        while True:
            dist = self.distance_func(node.hash_val, hash_val)
            if dist in node.children:
                node = node.children[dist]
            else:
                node.children[dist] = BKNode(item, hash_val)
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
