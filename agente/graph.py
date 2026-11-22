from collections.abc import Sequence

from langchain.messages import SystemMessage
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from .prompts import SYSTEM_PROMPT
from .state import AgentState


def build_graph(model: BaseChatModel, tools: Sequence[BaseTool] = ()):
    """Monta o grafo do agente: o modelo decide entre pedir uma ferramenta e responder."""
    model_with_tools = model.bind_tools(list(tools)) if tools else model

    async def agent(state: AgentState) -> dict:
        """Chama o modelo com o prompt de sistema e o histórico da conversa."""
        reply = await model_with_tools.ainvoke([SystemMessage(SYSTEM_PROMPT)] + state["messages"])
        return {"messages": [reply]}

    builder = StateGraph(AgentState)

    # nós
    builder.add_node("agent", agent)
    builder.add_node("tools", ToolNode(list(tools)))

    # arestas
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")

    return builder.compile()
