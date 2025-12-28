"""
GPU Configuration Module.

Manages GPU device selection (DirectML, CUDA, CPU) and engine-specific settings.
Settings are persisted to a JSON config file.
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from loguru import logger

# Default batch sizes tuned for memory usage
DEFAULT_BATCH_SIZES = {
    "phash": 32,
    "clip": 8,
    "blip": 8,
    "mobilenet": 16
}

# Config file location
CONFIG_DIR = Path.home() / ".image_deduper"
CONFIG_FILE = CONFIG_DIR / "gpu_config.json"


class GPUConfig:
    """
    Singleton configuration for GPU device selection and batch sizes.
    """
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if GPUConfig._initialized:
            return
        GPUConfig._initialized = True
        
        self._device_id: str = "auto"  # "auto", "directml:0", "cuda:0", "cpu"
        self._batch_sizes: Dict[str, int] = DEFAULT_BATCH_SIZES.copy()
        self._available_devices: List[Dict[str, Any]] = []
        
        # Detect available devices
        self._detect_devices()
        
        # Load saved config
        self._load_config()
    
    def _detect_devices(self) -> None:
        """Detect all available GPU devices."""
        self._available_devices = []
        
        # DirectML devices (Intel, AMD integrated/discrete)
        try:
            import torch_directml
            count = torch_directml.device_count()
            for i in range(count):
                try:
                    name = torch_directml.device_name(i)
                except:
                    name = f"DirectML Device {i}"
                
                self._available_devices.append({
                    "id": f"directml:{i}",
                    "name": f"{name}",
                    "type": "directml",
                    "index": i
                })
                logger.debug(f"Found DirectML device {i}: {name}")
        except ImportError:
            logger.debug("torch-directml not available")
        except Exception as e:
            logger.warning(f"Error detecting DirectML devices: {e}")
        
        # CUDA devices (NVIDIA)
        try:
            import torch
            if torch.cuda.is_available():
                count = torch.cuda.device_count()
                for i in range(count):
                    try:
                        name = torch.cuda.get_device_name(i)
                    except:
                        name = f"CUDA Device {i}"
                    
                    self._available_devices.append({
                        "id": f"cuda:{i}",
                        "name": f"{name}",
                        "type": "cuda",
                        "index": i
                    })
                    logger.debug(f"Found CUDA device {i}: {name}")
        except ImportError:
            logger.debug("torch.cuda not available")
        except Exception as e:
            logger.warning(f"Error detecting CUDA devices: {e}")
        
        # CPU fallback
        self._available_devices.append({
            "id": "cpu",
            "name": "CPU (No GPU acceleration)",
            "type": "cpu",
            "index": 0
        })
        
        logger.info(f"Detected {len(self._available_devices)} compute devices")
    
    def _load_config(self) -> None:
        """Load configuration from file."""
        if not CONFIG_FILE.exists():
            return
        
        try:
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
            
            if 'device_id' in data:
                # Validate device still exists
                valid_ids = [d['id'] for d in self._available_devices]
                if data['device_id'] in valid_ids or data['device_id'] == 'auto':
                    self._device_id = data['device_id']
            
            if 'batch_sizes' in data:
                for engine, size in data['batch_sizes'].items():
                    if engine in self._batch_sizes:
                        self._batch_sizes[engine] = int(size)
            
            logger.info(f"Loaded GPU config: device={self._device_id}")
        except Exception as e:
            logger.warning(f"Error loading GPU config: {e}")
    
    def save_config(self) -> None:
        """Save configuration to file."""
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            
            data = {
                "device_id": self._device_id,
                "batch_sizes": self._batch_sizes
            }
            
            with open(CONFIG_FILE, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"Saved GPU config: device={self._device_id}")
        except Exception as e:
            logger.error(f"Error saving GPU config: {e}")
    
    def get_available_devices(self) -> List[Dict[str, Any]]:
        """Get list of available compute devices."""
        return self._available_devices.copy()
    
    def get_device_id(self) -> str:
        """Get currently selected device ID."""
        return self._device_id
    
    def set_device_id(self, device_id: str) -> None:
        """Set the device to use."""
        valid_ids = [d['id'] for d in self._available_devices] + ['auto']
        if device_id in valid_ids:
            self._device_id = device_id
            # Clear cached device so it's re-resolved on next get_device() call
            global _cached_device
            _cached_device = None
            logger.info(f"GPU device set to: {device_id}")
        else:
            logger.warning(f"Invalid device ID: {device_id}")
    
    def get_batch_size(self, engine: str) -> int:
        """Get batch size for an engine."""
        return self._batch_sizes.get(engine, DEFAULT_BATCH_SIZES.get(engine, 8))
    
    def set_batch_size(self, engine: str, size: int) -> None:
        """Set batch size for an engine."""
        if engine in self._batch_sizes:
            self._batch_sizes[engine] = max(1, min(256, size))
    
    def get_all_batch_sizes(self) -> Dict[str, int]:
        """Get all batch sizes."""
        return self._batch_sizes.copy()


# Cached device for performance
_cached_device = None


def get_device():
    """
    Get the configured torch device.
    
    Returns the device based on user configuration:
    - "auto": DirectML > CUDA > CPU (original behavior)
    - "directml:N": Specific DirectML device
    - "cuda:N": Specific CUDA device
    - "cpu": CPU only
    """
    global _cached_device
    
    if _cached_device is not None:
        return _cached_device
    
    import torch
    config = GPUConfig()
    device_id = config.get_device_id()
    
    if device_id == "auto":
        # Auto-select: DirectML > CUDA > CPU
        try:
            import torch_directml
            _cached_device = torch_directml.device()
            logger.info(f"Auto-selected DirectML device: {_cached_device}")
            return _cached_device
        except:
            pass
        
        if torch.cuda.is_available():
            _cached_device = torch.device("cuda")
            logger.info("Auto-selected CUDA device")
            return _cached_device
        
        _cached_device = torch.device("cpu")
        logger.info("Auto-selected CPU (no GPU available)")
        return _cached_device
    
    elif device_id.startswith("directml:"):
        try:
            import torch_directml
            idx = int(device_id.split(":")[1])
            _cached_device = torch_directml.device(idx)
            logger.info(f"Using DirectML device {idx}: {_cached_device}")
            return _cached_device
        except Exception as e:
            logger.error(f"Failed to use DirectML:{idx}, falling back to CPU: {e}")
            _cached_device = torch.device("cpu")
            return _cached_device
    
    elif device_id.startswith("cuda:"):
        try:
            idx = int(device_id.split(":")[1])
            if torch.cuda.is_available():
                _cached_device = torch.device(f"cuda:{idx}")
                logger.info(f"Using CUDA device {idx}")
                return _cached_device
            else:
                logger.warning("CUDA not available, falling back to CPU")
                _cached_device = torch.device("cpu")
                return _cached_device
        except Exception as e:
            logger.error(f"Failed to use CUDA:{idx}, falling back to CPU: {e}")
            _cached_device = torch.device("cpu")
            return _cached_device
    
    else:  # cpu
        _cached_device = torch.device("cpu")
        logger.info("Using CPU device")
        return _cached_device


def clear_device_cache():
    """Clear the cached device (call after changing settings)."""
    global _cached_device
    _cached_device = None


def is_gpu_available() -> bool:
    """Check if any GPU acceleration is available."""
    config = GPUConfig()
    devices = config.get_available_devices()
    return any(d['type'] != 'cpu' for d in devices)
