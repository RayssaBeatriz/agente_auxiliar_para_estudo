from collections.abc import Sequence
from typing import Literal

from langchain.messages import HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

from .guardrails import guard_output, make_guard_input, route_after_input
from .prompts import GRADE_PROMPT, REWRITE_PROMPT, SYSTEM_PROMPT
from .rag import SEARCH_TOOL
from .state import AgentState

MAX_REWRITES = 2


class GradeDocuments(BaseModel):
    """Veredito binário sobre a relevância dos trechos."""

    binary_score: Literal["sim", "nao"] = Field(description="'sim' se os trechos respondem à pergunta, 'nao' se não")


def build_graph(model: BaseChatModel, tools: Sequence[BaseTool] = ()):
    """Monta o grafo do agente: o modelo decide quando buscar, e trechos ruins levam a uma nova consulta."""
    model_with_tools = model.bind_tools(list(tools)) if tools else model

    async def start_turn(state: AgentState) -> dict:
        """Guarda a pergunta do turno e zera o contador de reescritas."""
        return {"question": state["messages"][-1].content, "rewrites": 0}

    async def agent(state: AgentState) -> dict:
        """Chama o modelo com o prompt de sistema e o histórico da conversa."""
        reply = await model_with_tools.ainvoke([SystemMessage(SYSTEM_PROMPT)] + state["messages"])
        return {"messages": [reply]}

    def route_after_agent(state: AgentState) -> Literal["tools", "guard_output"]:
        """Se o modelo pediu ferramentas, executa-as; senão a resposta passa pelo guardrail de saída."""
        return "tools" if state["messages"][-1].tool_calls else "guard_output"

    async def route_after_tools(state: AgentState) -> Literal["agent", "rewrite"]:
        """Se a última ferramenta foi a busca, avalia os trechos; trechos ruins pedem uma reescrita."""
        observed = []
        for message in reversed(state["messages"]):
            if message.type != "tool":
                break
            observed.append(message)
        searches = [message for message in observed if message.name == SEARCH_TOOL]
        if not searches or state["rewrites"] >= MAX_REWRITES:
            return "agent"
        grader = model.with_structured_output(GradeDocuments, method="json_schema")
        context = "\n\n".join(message.content for message in searches)
        verdict = await grader.ainvoke(GRADE_PROMPT.format(context=context, question=state["question"]))
        return "agent" if verdict.binary_score == "sim" else "rewrite"

    async def rewrite(state: AgentState) -> dict:
        """Reescreve a pergunta com os termos do edital e manda o agente buscar de novo."""
        rewritten = (await model.ainvoke(REWRITE_PROMPT.format(question=state["question"]))).content
        message = HumanMessage(f"Os trechos não responderam à pergunta. Busque de novo com esta consulta reformulada: {rewritten}")
        return {"messages": [message], "rewrites": state["rewrites"] + 1}

    builder = StateGraph(AgentState)

    # nós
    builder.add_node("guard_input", make_guard_input(model))
    builder.add_node("start_turn", start_turn)
    builder.add_node("agent", agent)
    builder.add_node("tools", ToolNode(list(tools)))
    builder.add_node("rewrite", rewrite)
    builder.add_node("guard_output", guard_output)

    # arestas
    builder.add_edge(START, "guard_input")
    builder.add_conditional_edges("guard_input", route_after_input)
    builder.add_edge("start_turn", "agent")
    builder.add_conditional_edges("agent", route_after_agent)
    builder.add_edge("guard_output", END)
    builder.add_conditional_edges("tools", route_after_tools)
    builder.add_edge("rewrite", "agent")

    return builder.compile()
