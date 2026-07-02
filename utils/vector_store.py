import time
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

COLLECTION_NAME = "prompt_cache"
VECTOR_SIZE = 384
DEFAULT_TTL_SECONDS = 60 * 60 * 24  # 24 hours


class VectorStore:
    def __init__(self, host: str = "localhost", port: int = 6333):
        self.client = QdrantClient(host=host, port=port)
        self._ensure_collection()

    def _ensure_collection(self):
        existing = [c.name for c in self.client.get_collections().collections]
        if COLLECTION_NAME not in existing:
            self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )

    def upsert(self, embedding: list[float], prompt: str, response: str, prompt_tokens: int, completion_tokens: int, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        point_id = str(uuid.uuid4())
        now = time.time()
        self.client.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={
                        "prompt": prompt,
                        "response": response,
                        "created_at": now,
                        "expires_at": now + ttl_seconds,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                    },
                )
            ],
        )

    def search(self, embedding: list[float], limit: int = 5):
        results = self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=embedding,
            limit=limit,
        ).points

        now = time.time()
        fresh_results = [r for r in results if r.payload.get("expires_at", 0) > now]
        return fresh_results