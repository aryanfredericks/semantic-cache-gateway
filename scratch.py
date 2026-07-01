from utils.embedder import Embedder
from utils.vector_store import VectorStore

embedder = Embedder()
store = VectorStore()

# Upsert one entry
prompt1 = "Hello, can you help me?"
response1 = "Sure, what do you need help with?"
store.upsert(embedder.embed(prompt1), prompt1, response1)

# Query with a near-duplicate
near_dup = "Hi, could you help me out?"
results = store.search(embedder.embed(near_dup))
for r in results:
    print("Score:", r.score, "| Matched prompt:", r.payload["prompt"])

# Query with something unrelated
unrelated = "What's the boiling point of water?"
results = store.search(embedder.embed(unrelated))
for r in results:
    print("Score:", r.score, "| Matched prompt:", r.payload["prompt"])