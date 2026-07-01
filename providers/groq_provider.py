from langchain_core.messages import HumanMessage
from langchain_groq import ChatGroq

from configs import groq_configs
from providers.base import LLMProvider


class GroqProvider(LLMProvider):
    def __init__(self, api_key: str):
        self.conf = groq_configs
        self.model = ChatGroq(model=self.conf.model_name, api_key=api_key)
        print("Groq model has been initialised.")

    async def call(self, query: str) -> str:
        output = await self.model.ainvoke([HumanMessage(content=query)])
        return output.content