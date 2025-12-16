from loguru import logger
from PIL import Image
from .base import BaseAIEngine

class MobileNetEngine(BaseAIEngine):
    def __init__(self, db_manager):
        super().__init__(db_manager)
        self.preprocess = None
        self.collection_name = 'mobilenet_embeddings'
        self.engine_name = 'MobileNet'
        
    def load_model(self):
        try:
            import torch
            import torchvision.models as models
            # import torchvision.transforms as transforms
            
            # Use MobileNetV3 Small for speed
            # We want the features, not classification. 
            # We can use the backbone or just remove the classifier.
            weights = models.MobileNet_V3_Small_Weights.DEFAULT
            self.model = models.mobilenet_v3_small(weights=weights)
            self.model.classifier = torch.nn.Identity() # Remove classification head
            self.model.eval()
            
            self.preprocess = weights.transforms()
            
            logger.info("MobileNetV3 (Small) Model loaded successfully.")
        except ImportError:
            logger.error("torchvision not installed. MobileNet engine unavailable.")
        except Exception as e:
            logger.error(f"Failed to load MobileNet model: {e}")

    def get_embedding(self, image_path):
        try:
            img = Image.open(image_path).convert('RGB')
            # Inference
            batch = self.preprocess(img).unsqueeze(0)
            emb = self.model(batch).detach().numpy().flatten().tolist()
            return emb
        except Exception as e:
            logger.warning(f"MobileNet Error {image_path}: {e}")
            return None

