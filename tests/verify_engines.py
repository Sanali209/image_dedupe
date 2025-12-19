
from core.engines.clip import CLIPEngine
from core.engines.blip import BLIPEngine
from unittest.mock import MagicMock

def test_init():
    db = MagicMock()
    repo = MagicMock()
    
    print("Testing CLIP init...")
    try:
        c = CLIPEngine(db, repo)
        print("CLIP init SUCCESS")
    except TypeError as e:
        print(f"CLIP init FAILED: {e}")
        
    print("Testing BLIP init...")
    try:
        b = BLIPEngine(db, repo)
        print("BLIP init SUCCESS")
    except TypeError as e:
        print(f"BLIP init FAILED: {e}")

if __name__ == "__main__":
    test_init()
