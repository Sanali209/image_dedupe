import os
import sys
import time
from PySide6.QtCore import QCoreApplication

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from core.gpu_config import GPUConfig
from ui.utils import ThrottledSignal

def test_throttled_signal():
    print("Testing ThrottledSignal...")
    throttler = ThrottledSignal(interval_ms=100)
    counts = 0
    def on_emitted(val, total):
        nonlocal counts
        counts += 1
        print(f"Emitted: {val}/{total}")

    throttler.emitted.connect(on_emitted)
    
    start = time.time()
    for i in range(100):
        throttler.emit(i, 100)
        time.sleep(0.01) # 10ms * 100 = 1s
    
    throttler.flush()
    print(f"Total emissions: {counts} (Expected ~10-12)")
    assert 5 < counts < 20

def test_phash_config():
    print("\nTesting PHash Config Persistence...")
    config = GPUConfig()
    original_size = config.get_batch_size('phash')
    
    test_size = 123
    config.set_batch_size('phash', test_size)
    config.save_config()
    
    # Reload config
    # Singleton check: we can just check if get_batch_size returns test_size
    # but to be sure it persists, we check the _batch_sizes dict
    config._load_config()
    
    new_size = config.get_batch_size('phash')
    print(f"New size: {new_size} (Expected {test_size})")
    assert new_size == test_size
    
    # Restore original
    config.set_batch_size('phash', original_size)
    config.save_config()

if __name__ == "__main__":
    app = QCoreApplication(sys.argv)
    try:
        test_throttled_signal()
        test_phash_config()
        print("\nVerification Complete!")
    except Exception as e:
        print(f"\nVerification FAILED: {e}")
        sys.exit(1)
    sys.exit(0)
