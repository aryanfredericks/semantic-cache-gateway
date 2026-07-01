from sentence_transformers import SentenceTransformer

_MODEL_NAME = "BAAI/bge-small-en-v1.5"


class Embedder:
    def __init__(self):
        print("Loading embedding model...")
        self.model = SentenceTransformer(_MODEL_NAME)
        print("Embedding model loaded.")

    def embed(self, text: str) -> list[float]:
        vector = self.model.encode(text, normalize_embeddings=True)
        return vector.tolist()