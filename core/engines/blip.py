from loguru import logger
from PIL import Image
from .base import BaseAIEngine

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
            from transformers import BlipProcessor, BlipModel
            self.processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
            self.model = BlipModel.from_pretrained("Salesforce/blip-image-captioning-base")
            
            # Populate Cache
            BLIPEngine._cached_model = self.model
            BLIPEngine._cached_processor = self.processor
            
            logger.info("BLIP Model loaded successfully.")
        except ImportError:
            logger.error("transformers not installed. BLIP engine unavailable.")
        except Exception as e:
            logger.error(f"Failed to load BLIP model: {e}")

    def get_embedding(self, image_path):
        try:
            raw_image = Image.open(image_path).convert('RGB')
            # Processor handles resizing/normalization usually
            inputs = self.processor(images=raw_image, return_tensors="pt")
            
            # We want features, not caption. 
            # BlipModel returns: last_hidden_state, pooler_output (optional), etc.
            # actually blip-image-captioning-base model might be BlipForConditionalGeneration which is different from BlipModel.
            # Original code used: self.model.get_image_features(**inputs)
            # Let's verify what the original code did. 
            # Original: self.model = BlipModel.from_pretrained(...)
            # Original used: outputs = self.model.get_image_features(**inputs) which is valid for BlipModel.
            
            outputs = self.model.get_image_features(**inputs)
            
            # Normalize?
            # Original code said "Normalize?" but didn't do it explicitly other than what model does.
            # outputs[0] is the vector (batch size 1)
            
            return outputs[0].tolist() 
            
        except Exception as e:
            logger.warning(f"Error processing {image_path}: {e}")
            return None

