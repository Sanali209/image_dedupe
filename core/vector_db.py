import os
try:
    import chromadb
    from chromadb.config import Settings
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False

from loguru import logger

class VectorStore:
    def __init__(self, persistence_path="chroma_db"):
        self.client = None
        self.collections = {}
        if not HAS_CHROMA:
            logger.warning("ChromaDB not installed. Vector features will be disabled.")
            return

        # Ensure persistence directory exists
        if not os.path.exists(persistence_path):
            os.makedirs(persistence_path)
            
        self.client = chromadb.PersistentClient(path=persistence_path)
        
        # Initialize Collections
        self._get_or_create_collection("clip_embeddings")
        self._get_or_create_collection("blip_embeddings")
        self._get_or_create_collection("mobilenet_embeddings")

    def _get_or_create_collection(self, name):
        if not self.client: return
        try:
            # metadata={"hnsw:space": "cosine"} for cosine similarity
            # default is l2 (euclidean) which is fine if vectors are normalized?
            # CLIP usually works best with Cosine.
            self.collections[name] = self.client.get_or_create_collection(
                name=name, 
                metadata={"hnsw:space": "cosine"}
            )
        except Exception as e:
            logger.error(f"Failed to create collection {name}: {e}")

    def upsert(self, collection_name, ids, embeddings, metadatas=None):
        """
        Upsert vectors.
        ids: list of file paths (unique strings)
        embeddings: list of vectors (lists of floats)
        metadatas: list of dicts
        """
        if not self.client: return
        col = self.collections.get(collection_name)
        if not col: return
        
        try:
            col.upsert(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas
            )
        except Exception as e:
            logger.error(f"ChromaDB Upsert Error: {e}")

    def query(self, collection_name, query_embeddings, n_results=10, include_distances=True):
        """
        Query for nearest neighbors.
        Returns:
            dict with 'ids', 'distances', 'metadatas'
        """
        if not self.client: return None
        col = self.collections.get(collection_name)
        if not col: return None
        
        try:
            results = col.query(
                query_embeddings=query_embeddings,
                n_results=n_results,
                include=['metadatas', 'distances'] if include_distances else ['metadatas']
            )
            return results
        except Exception as e:
            logger.error(f"ChromaDB Query Error: {e}")
            return None
            
    def count(self, collection_name):
        if not self.client: return 0
        col = self.collections.get(collection_name)
        return col.count() if col else 0

    def batch_get(self, collection_name, ids, batch_size=10000):
        """
        Batch retrieve embeddings for multiple IDs.
        More efficient than individual get() calls.
        
        Args:
            collection_name: Name of the collection
            ids: List of IDs to retrieve
            batch_size: Size of each batch
            
        Returns:
            Dict mapping id -> embedding
        """
        if not self.client: return {}
        col = self.collections.get(collection_name)
        if not col: return {}
        
        result = {}
        try:
            for i in range(0, len(ids), batch_size):
                batch = ids[i:i+batch_size]
                data = col.get(ids=batch, include=['embeddings'])
                # Use explicit length checks to avoid numpy array truth value issues
                if data and len(data.get('ids', [])) > 0 and len(data.get('embeddings', [])) > 0:
                    for doc_id, emb in zip(data['ids'], data['embeddings']):
                        result[doc_id] = emb
        except Exception as e:
            logger.error(f"ChromaDB batch_get error: {e}")
            
        return result
