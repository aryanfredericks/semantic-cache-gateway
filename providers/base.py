from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    async def call(self, query: str) -> str:
        ...