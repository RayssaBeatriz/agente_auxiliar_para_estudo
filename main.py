"""Chat de teste pelo terminal. Será substituído pela interface em Streamlit."""
import asyncio
import re

from dotenv import load_dotenv
from langchain.messages import HumanMessage

from agente.graph import build_graph, new_conversation
from agente.mcp_tools import load_mcp_tools
from agente.model import get_model
from agente.rag import SEARCH_TOOL
from agente.skills import LOAD_SKILL, load_skill
from agente.utils import text_of


def mostrar(node: str, update: dict | None) -> None:
    """Imprime o que cada nó produziu: chamadas de ferramenta, fontes recuperadas, reescritas e respostas."""
    update = update or {}  # nós que não alteram o estado devolvem None
    if update.get("summary"):
        print("  resumo:", update["summary"])
    for message in update.get("messages", []):
        if message.type == "remove":  # mensagens apagadas do histórico não interessam aqui
            continue
        if message.type == "tool":
            fontes = re.findall(r"\[(Concurso [^\]]+)\]", text_of(message.content))
            print("  trechos:", "; ".join(fontes) or text_of(message.content)[:80])
        elif getattr(message, "tool_calls", None):
            for call in message.tool_calls:
                if call["name"] == SEARCH_TOOL:
                    print(f"  busca: {call['args'].get('query')!r} (edital {call['args'].get('edital', 'todos')})")
                elif call["name"] == LOAD_SKILL:
                    print(f"  skill: {call['args'].get('name')}")
                else:
                    print(f"  ferramenta: {call['name']} {call['args']}")
        elif node == "rewrite":
            print("  reescrita:", message.additional_kwargs["query"])
        elif node in ("guard_input", "guard_output"):  # a resposta final sai sempre por um guardrail
            print("assistente:", message.content)


async def main() -> None:
    graph = build_graph(get_model(), [*await load_mcp_tools(), load_skill])
    config = new_conversation()
    while question := input("\nvocê: ").strip():
        if question == "/nova":  # nova conversa: outra thread, sem o histórico da anterior
            config = new_conversation()
            print("nova conversa")
            continue
        async for step in graph.astream({"messages": [HumanMessage(question)]}, config, stream_mode="updates"):
            for node, update in step.items():
                mostrar(node, update)


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())