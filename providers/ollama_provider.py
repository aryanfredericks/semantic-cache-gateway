from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama

from providers.base import LLMProvider


class OllamaProvider(LLMProvider):
    def __init__(self, model: str = "qwen2.5:7b", base_url: str = "http://localhost:11434"):
        self.model = ChatOllama(model=model, base_url=base_url)
        print("Ollama fallback model has been initialised.")

    async def call(self, query: str) -> tuple[str, dict | None]:
        output = await self.model.ainvoke([HumanMessage(content=query)])
        # Ollama doesn't populate usage_metadata the same way Groq does —
        # token counts may be unavailable or approximate here.
        usage = getattr(output, "usage_metadata", None)
        return output.content, usage