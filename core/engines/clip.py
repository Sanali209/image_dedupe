from loguru import logger
from PIL import Image
from .base import BaseAIEngine

class CLIPEngine(BaseAIEngine):
    def __init__(self, db_manager):
        super().__init__(db_manager)
        self.collection_name = 'clip_embeddings'
        self.engine_name = 'CLIP'
        
    def load_model(self):
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer('clip-ViT-B-32')
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

