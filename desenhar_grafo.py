"""Gera docs/grafo.mmd e docs/grafo.png a partir do grafo montado em agente/graph.py."""
from pathlib import Path

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

from agente.graph import build_graph

graph = build_graph(GenericFakeChatModel(messages=iter([]))).get_graph()  # só a estrutura importa, o modelo não é chamado

Path("docs").mkdir(exist_ok=True)
Path("docs/grafo.mmd").write_text(graph.draw_mermaid())
Path("docs/grafo.png").write_bytes(graph.draw_mermaid_png())
print("gerado: docs/grafo.mmd e docs/grafo.png")