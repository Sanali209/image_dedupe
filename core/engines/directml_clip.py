"""
CLIP Engine using configurable GPU acceleration with CPU fallback.
Supports DirectML (Intel, AMD) and CUDA (NVIDIA) based on user settings.
"""
from loguru import logger
from PIL import Image
from .base import BaseAIEngine
from core.gpu_config import get_device, GPUConfig


class DirectMLCLIPEngine(BaseAIEngine):
    """
    CLIP-based embedding engine with configurable GPU acceleration.
    Uses the device specified in GPUConfig settings.
    """
    _cached_model = None
    _cached_processor = None

    def __init__(self, db_manager, file_repo=None):
        super().__init__(db_manager, file_repo)
        self.collection_name = 'clip_embeddings'
        self.engine_name = 'CLIP-DirectML'
        self.processor = None

    def load_model(self):
        # Check cache first
        if DirectMLCLIPEngine._cached_model is not None:
            self.model = DirectMLCLIPEngine._cached_model
            self.processor = DirectMLCLIPEngine._cached_processor
            logger.info("CLIP model loaded from cache (instant).")
            return

        try:
            import torch
            from transformers import CLIPModel, CLIPProcessor
            
            device = get_device()
            
            # Load CLIP model and processor
            model_name = "openai/clip-vit-base-patch32"
            
            logger.info(f"Loading CLIP model '{model_name}'...")
            self.processor = CLIPProcessor.from_pretrained(model_name)
            self.model = CLIPModel.from_pretrained(model_name)
            
            # Move model to device
            self.model = self.model.to(device)
            self.model.eval()
            
            # Cache for reuse
            DirectMLCLIPEngine._cached_model = self.model
            DirectMLCLIPEngine._cached_processor = self.processor
            
            logger.info(f"CLIP model loaded on {device}.")
            
        except ImportError as e:
            logger.error(f"Missing dependencies for CLIP: {e}")
            logger.error("Install with: pip install transformers")
        except Exception as e:
            logger.error(f"Failed to load CLIP model: {e}")

    def get_embedding(self, image_path):
        """Generate CLIP embedding for an image."""
        if self.model is None or self.processor is None:
            logger.warning("Model not loaded. Call load_model() first.")
            return None
            
        try:
            import torch
            
            device = get_device()
            
            # Load and preprocess image
            img = Image.open(image_path).convert('RGB')
            inputs = self.processor(images=img, return_tensors="pt")
            
            # Move inputs to device
            inputs = {k: v.to(device) for k, v in inputs.items()}
            
            # Generate embedding
            with torch.no_grad():
                outputs = self.model.get_image_features(**inputs)
                
            # Normalize embedding (CLIP embeddings work best normalized)
            embedding = outputs / outputs.norm(dim=-1, keepdim=True)
            
            # Convert to list and return
            return embedding.cpu().squeeze().tolist()
            
        except Exception as e:
            logger.warning(f"CLIP embedding error for {image_path}: {e}")
            return None

    def get_batch_embeddings(self, image_paths, batch_size=None):
        """
        Generate embeddings for multiple images in batches.
        More efficient than calling get_embedding() repeatedly.
        
        Args:
            image_paths: List of image file paths
            batch_size: Number of images to process at once (uses config if None)
            
        Returns:
            Dict mapping path -> embedding list
        """
        if self.model is None or self.processor is None:
            logger.warning("Model not loaded. Call load_model() first.")
            return {}
        
        # Use configured batch size if not specified
        if batch_size is None:
            batch_size = GPUConfig().get_batch_size('clip')
            
        import torch
        
        device = get_device()
        results = {}
        
        for i in range(0, len(image_paths), batch_size):
            batch_paths = image_paths[i:i + batch_size]
            batch_images = []
            valid_paths = []
            
            # Load images for this batch
            for path in batch_paths:
                try:
                    img = Image.open(path).convert('RGB')
                    batch_images.append(img)
                    valid_paths.append(path)
                except Exception as e:
                    logger.warning(f"Failed to load image {path}: {e}")
            
            if not batch_images:
                continue
                
            try:
                # Process batch
                inputs = self.processor(images=batch_images, return_tensors="pt", padding=True)
                inputs = {k: v.to(device) for k, v in inputs.items()}
                
                with torch.no_grad():
                    outputs = self.model.get_image_features(**inputs)
                
                # Normalize
                embeddings = outputs / outputs.norm(dim=-1, keepdim=True)
                embeddings = embeddings.cpu()
                
                # Map results
                for path, emb in zip(valid_paths, embeddings):
                    results[path] = emb.squeeze().tolist()
                    
            except Exception as e:
                logger.warning(f"Batch embedding error: {e}")
                # Fallback to individual processing
                for path in valid_paths:
                    emb = self.get_embedding(path)
                    if emb:
                        results[path] = emb
        
        return results
