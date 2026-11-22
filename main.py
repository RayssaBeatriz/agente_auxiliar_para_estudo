"""Teste rápido do esqueleto. Será substituído pela interface em Streamlit."""
import asyncio

from dotenv import load_dotenv
from langchain.messages import HumanMessage

from agente.graph import build_graph
from agente.model import get_model


async def main() -> None:
    graph = build_graph(get_model())
    result = await graph.ainvoke({"messages": [HumanMessage("Olá! O que você faz?")]})
    print(result["messages"][-1].content)


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
