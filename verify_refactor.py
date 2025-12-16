import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

try:
    from core.engines.blip import BLIPEngine
    from core.engines.clip import CLIPEngine
    from core.engines.mobilenet import MobileNetEngine
    from core.engines.phash import PHashEngine
    from core.database import DatabaseManager

    print("Imports successful.")

    db = DatabaseManager(":memory:")
    
    # Instantiate to check init logic
    blip = BLIPEngine(db)
    clip = CLIPEngine(db)
    mobilenet = MobileNetEngine(db)
    phash = PHashEngine(db)
    
    print("Instantiation successful.")
    
    # Check inheritance
    from core.engines.base import BaseAIEngine
    assert isinstance(blip, BaseAIEngine)
    assert isinstance(clip, BaseAIEngine)
    assert isinstance(mobilenet, BaseAIEngine)
    print("Inheritance check successful.")

except Exception as e:
    print(f"Verification Failed: {e}")
    sys.exit(1)
