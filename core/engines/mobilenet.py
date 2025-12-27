"""
MobileNet Engine with configurable GPU acceleration and CPU fallback.
"""
from loguru import logger
from PIL import Image
from .base import BaseAIEngine
from core.gpu_config import get_device, GPUConfig


class MobileNetEngine(BaseAIEngine):
    _cached_model = None
    _cached_preprocess = None

    def __init__(self, db_manager, file_repo=None):
        super().__init__(db_manager, file_repo)
        self.preprocess = None
        self.collection_name = 'mobilenet_embeddings'
        self.engine_name = 'MobileNet'
        
    def load_model(self):
        # Check Cache
        if MobileNetEngine._cached_model is not None:
            self.model = MobileNetEngine._cached_model
            self.preprocess = MobileNetEngine._cached_preprocess
            logger.info("MobileNetV3 Model loaded from cache (Instant).")
            return

        try:
            import torch
            import torchvision.models as models
            
            device = get_device()
            
            # Use MobileNetV3 Small for speed
            weights = models.MobileNet_V3_Small_Weights.DEFAULT
            self.model = models.mobilenet_v3_small(weights=weights)
            self.model.classifier = torch.nn.Identity()  # Remove classification head
            
            # Move to configured device
            self.model = self.model.to(device)
            self.model.eval()
            
            self.preprocess = weights.transforms()
            
            # Populate Cache
            MobileNetEngine._cached_model = self.model
            MobileNetEngine._cached_preprocess = self.preprocess
            
            logger.info(f"MobileNetV3 (Small) loaded on {device}.")
            
        except ImportError:
            logger.error("torchvision not installed. MobileNet engine unavailable.")
        except Exception as e:
            logger.error(f"Failed to load MobileNet model: {e}")

    def get_embedding(self, image_path):
        if self.model is None or self.preprocess is None:
            return None
            
        try:
            import torch
            
            device = get_device()
            
            img = Image.open(image_path).convert('RGB')
            batch = self.preprocess(img).unsqueeze(0).to(device)
            
            with torch.no_grad():
                emb = self.model(batch)
            
            return emb.cpu().squeeze().tolist()
            
        except Exception as e:
            logger.warning(f"MobileNet Error {image_path}: {e}")
            return None

    def get_batch_embeddings(self, image_paths, batch_size=None):
        """
        Generate embeddings for multiple images in batches.
        MobileNet is lightweight so can use larger batches.
        """
        if self.model is None or self.preprocess is None:
            return {}
        
        # Use configured batch size if not specified
        if batch_size is None:
            batch_size = GPUConfig().get_batch_size('mobilenet')
            
        import torch
        
        device = get_device()
        results = {}
        
        for i in range(0, len(image_paths), batch_size):
            batch_paths = image_paths[i:i + batch_size]
            batch_tensors = []
            valid_paths = []
            
            for path in batch_paths:
                try:
                    img = Image.open(path).convert('RGB')
                    tensor = self.preprocess(img)
                    batch_tensors.append(tensor)
                    valid_paths.append(path)
                except Exception as e:
                    logger.warning(f"Failed to load {path}: {e}")
            
            if not batch_tensors:
                continue
                
            try:
                batch = torch.stack(batch_tensors).to(device)
                
                with torch.no_grad():
                    embeddings = self.model(batch)
                
                embeddings = embeddings.cpu()
                
                for path, emb in zip(valid_paths, embeddings):
                    results[path] = emb.squeeze().tolist()
                    
            except Exception as e:
                logger.warning(f"Batch error: {e}")
                for path in valid_paths:
                    emb = self.get_embedding(path)
                    if emb:
                        results[path] = emb
        
        return results
