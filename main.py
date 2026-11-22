"""Chat de teste pelo terminal. Será substituído pela interface em Streamlit."""
import asyncio

from dotenv import load_dotenv
from langchain.messages import HumanMessage

from agente.graph import build_graph
from agente.model import get_model
from agente.rag import search_dataprev


def mostrar(node: str, update: dict) -> None:
    """Imprime o que cada nó produziu: chamadas de ferramenta, observações e respostas."""
    for message in update.get("messages", []):
        if message.type == "tool":
            print(f"  saída: {message.content[:80]!r}")
        elif getattr(message, "tool_calls", None):
            for call in message.tool_calls:
                print("  chamada:", call["name"], call["args"])
        elif node == "rewrite":
            print("  reescrita:", message.content)
        else:
            print("assistente:", message.content)


async def main() -> None:
    graph = build_graph(get_model(), [search_dataprev])
    while question := input("você: ").strip():
        async for step in graph.astream({"messages": [HumanMessage(question)]}, stream_mode="updates"):
            for node, update in step.items():
                mostrar(node, update)


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
