from utils.embedder import Embedder

embedder = Embedder()
vec = embedder.embed("Hello, can you help me?")
print("Vector length:", len(vec))
print("First 5 values:", vec[:5])