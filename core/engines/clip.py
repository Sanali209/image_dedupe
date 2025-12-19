from loguru import logger
from PIL import Image
from .base import BaseAIEngine

class CLIPEngine(BaseAIEngine):
    _cached_model = None

    def __init__(self, db_manager, file_repo=None):
        super().__init__(db_manager, file_repo)
        self.collection_name = 'clip_embeddings'
        self.engine_name = 'CLIP'
        
    def load_model(self):
        # Check Cache
        if CLIPEngine._cached_model is not None:
             self.model = CLIPEngine._cached_model
             logger.info("CLIP Model loaded from cache (Instant).")
             return

        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer('clip-ViT-B-32')
            
            # Populate Cache
            CLIPEngine._cached_model = self.model
            
            logger.info("CLIP Model loaded successfully.")
        except ImportError:
            logger.error("sentence-transformers not installed. CLIP engine unavailable.")
        except Exception as e:
            logger.error(f"Failed to load CLIP model: {e}")

    def get_embedding(self, image_path):
        try:
            # Check file? Base engine checks existence.
            img = Image.open(image_path).convert('RGB')
            # SentenceTransformer accepts PIL Image directly
            emb = self.model.encode(img).tolist()
            return emb
        except Exception as e:
            logger.warning(f"CLIP Error {image_path}: {e}")
            return None

