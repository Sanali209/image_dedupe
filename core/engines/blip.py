"""
BLIP Engine with configurable GPU acceleration and CPU fallback.
"""
from loguru import logger
from PIL import Image
from .base import BaseAIEngine
from core.gpu_config import get_device, GPUConfig


class BLIPEngine(BaseAIEngine):
    _cached_model = None
    _cached_processor = None

    def __init__(self, db_manager, file_repo=None):
        super().__init__(db_manager, file_repo)
        self.processor = None
        self.collection_name = 'blip_embeddings'
        self.engine_name = 'BLIP'
        
    def load_model(self):
        # Check Cache
        if BLIPEngine._cached_model is not None:
            self.model = BLIPEngine._cached_model
            self.processor = BLIPEngine._cached_processor
            logger.info("BLIP Model loaded from cache (Instant).")
            return

        try:
            import torch
            from transformers import BlipProcessor, BlipModel
            
            device = get_device()
            
            model_name = "Salesforce/blip-image-captioning-base"
            logger.info(f"Loading BLIP model '{model_name}'...")
            
            self.processor = BlipProcessor.from_pretrained(model_name)
            self.model = BlipModel.from_pretrained(model_name)
            
            # Move to configured device
            self.model = self.model.to(device)
            self.model.eval()
            
            # Populate Cache
            BLIPEngine._cached_model = self.model
            BLIPEngine._cached_processor = self.processor
            
            logger.info(f"BLIP Model loaded on {device}.")
            
        except ImportError:
            logger.error("transformers not installed. BLIP engine unavailable.")
        except Exception as e:
            logger.error(f"Failed to load BLIP model: {e}")

    def get_embedding(self, image_path):
        if self.model is None or self.processor is None:
            return None
            
        try:
            import torch
            
            device = get_device()
            
            raw_image = Image.open(image_path).convert('RGB')
            inputs = self.processor(images=raw_image, return_tensors="pt")
            
            # Move inputs to device
            inputs = {k: v.to(device) for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = self.model.get_image_features(**inputs)
            
            # Normalize for better similarity matching
            embedding = outputs / outputs.norm(dim=-1, keepdim=True)
            
            return embedding.cpu().squeeze().tolist()
            
        except Exception as e:
            logger.warning(f"BLIP Error {image_path}: {e}")
            return None

    def get_batch_embeddings(self, image_paths, batch_size=None):
        """
        Generate embeddings for multiple images in batches.
        BLIP is heavier than MobileNet, so uses smaller batches.
        """
        if self.model is None or self.processor is None:
            return {}
        
        # Use configured batch size if not specified
        if batch_size is None:
            batch_size = GPUConfig().get_batch_size('blip')
            
        import torch
        
        device = get_device()
        results = {}
        
        for i in range(0, len(image_paths), batch_size):
            batch_paths = image_paths[i:i + batch_size]
            batch_images = []
            valid_paths = []
            
            for path in batch_paths:
                try:
                    img = Image.open(path).convert('RGB')
                    batch_images.append(img)
                    valid_paths.append(path)
                except Exception as e:
                    logger.warning(f"Failed to load {path}: {e}")
            
            if not batch_images:
                continue
                
            try:
                inputs = self.processor(images=batch_images, return_tensors="pt", padding=True)
                inputs = {k: v.to(device) for k, v in inputs.items()}
                
                with torch.no_grad():
                    outputs = self.model.get_image_features(**inputs)
                
                # Normalize
                embeddings = outputs / outputs.norm(dim=-1, keepdim=True)
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
