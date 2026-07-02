from providers.base import LLMProvider


class FallbackProvider(LLMProvider):
    async def call(self, query: str) -> tuple[str, dict | None]:
        return (
            "I'm currently unable to reach the primary model provider. "
            "This is a fallback response — please try again shortly."
        ,None)