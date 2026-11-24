import re
from collections.abc import Sequence
from typing import Literal
from uuid import uuid4

from langchain.messages import HumanMessage, RemoveMessage, SystemMessage, ToolMessage
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

from .guardrails import guard_output, make_guard_input, route_after_input
from .memory import intermediate, make_compact
from .prompts import GRADE_PROMPT, REWRITE_PROMPT, SKILLS_PROMPT, SYSTEM_PROMPT
from .rag import SEARCH_TOOL
from .skills import LOAD_SKILL, catalog, loaded_skills
from .state import AgentState
from .utils import text_of

MAX_REWRITES = 1
BUSCA_ANTIGA = 600  # caracteres que ficam de cada busca antiga do turno, para a requisição caber no limite de tokens
RECURSION_LIMIT = 60
PLANO = "plano-de-estudos"
GATED = {"simular_nota": "diagnostico-de-desempenho", "estimar_posicao": "diagnostico-de-desempenho", "montar_cronograma_estudo": "plano-de-estudos"}  # ferramenta -> skill que a conduz


def new_conversation() -> dict:
    """Configuração de uma conversa nova: thread própria e limite de passos que comporta as skills."""
    return {"configurable": {"thread_id": str(uuid4())}, "recursion_limit": RECURSION_LIMIT}


class GradeDocuments(BaseModel):
    """Veredito binário sobre a relevância dos trechos."""

    binary_score: Literal["sim", "nao"] = Field(description="'sim' se os trechos respondem à pergunta, 'nao' se não")


def build_graph(model: BaseChatModel, tools: Sequence[BaseTool] = ()):
    """Monta o grafo do agente: o modelo decide quando buscar, e trechos ruins levam a uma nova consulta.

    O checkpointer guarda cada conversa sob um thread_id, passado em config ao invocar o grafo.
    """
    model_with_tools = model.bind_tools(list(tools)) if tools else model
    base_prompt = SYSTEM_PROMPT + SKILLS_PROMPT.format(catalog=catalog())

    async def start_turn(state: AgentState) -> dict:
        """Guarda a pergunta do turno e zera o contador de reescritas."""
        return {"question": state["messages"][-1].content, "rewrites": 0}

    def trim_searches(messages: list) -> list:
        """Encurta os resultados de busca antigos e mantém o último inteiro."""
        last = max((i for i, m in enumerate(messages) if m.type == "tool" and m.name == SEARCH_TOOL), default=-1)
        return [
            m.model_copy(update={"content": text_of(m.content)[:BUSCA_ANTIGA]}) if m.type == "tool" and m.name == SEARCH_TOOL and i != last else m
            for i, m in enumerate(messages)
        ]

    def missing_step(state: AgentState, reply) -> str:
        """Lembrete para a resposta vazia ou para o plano que termina sem ter chamado montar_cronograma_estudo; vazio se estiver certo."""
        if reply.tool_calls:
            return ""
        text = text_of(reply.content).strip()
        if not text:
            return "Sua resposta veio vazia. Siga os passos da skill ou responda ao usuário."
        if PLANO not in loaded_skills(state["messages"]):
            return ""
        called = set()
        for message in reversed(state["messages"]):
            if message.type == "human" and message.content == state["question"]:
                break
            called.update(call["name"] for call in getattr(message, "tool_calls", None) or [])
        if "montar_cronograma_estudo" in called:
            return ""
        informed = re.search(r"\d{1,2}/\d{1,2}/\d{4}|\d+ semanas?", text_of(state["question"]))  # a data ou as semanas já vieram do usuário
        if "?" in text and not informed:
            if "data" in text.lower() and "prova" in text.lower() and "get_current_time" not in called:
                return "Não peça o prazo agora. Execute o passo 2 da skill: chame get_current_time e search_dataprev e só depois responda."
            return ""
        return "Você carregou a skill de plano de estudos, mas não chamou montar_cronograma_estudo. Chame-a com as horas por semana, a data da prova ou as semanas informadas e as dificuldades, e responda só com o que ela devolver."

    async def agent(state: AgentState) -> dict:
        """Chama o modelo com o prompt de sistema, o resumo dos turnos antigos e o histórico recente."""
        system = base_prompt
        if state.get("summary"):
            system += f"\n\n# Resumo da conversa anterior\n{state['summary']}"
        messages = [SystemMessage(system)] + trim_searches(state["messages"])
        reply = await model_with_tools.ainvoke(messages)
        reminder = missing_step(state, reply)
        if reminder:  # uma segunda chance, com o lembrete só nesta chamada
            reply = await model_with_tools.ainvoke(messages + ([reply] if text_of(reply.content).strip() else []) + [HumanMessage(reminder)])
        if any(call["name"] == LOAD_SKILL for call in reply.tool_calls):  # a skill vem sozinha, para a poda não deixar resultado órfão
            reply = reply.model_copy(update={"tool_calls": [call for call in reply.tool_calls if call["name"] == LOAD_SKILL]})
        return {"messages": [reply]}

    def route_after_agent(state: AgentState) -> Literal["skill_gate", "guard_output"]:
        """Se o modelo pediu ferramentas, confere as skills; senão a resposta passa pelo guardrail de saída."""
        return "skill_gate" if state["messages"][-1].tool_calls else "guard_output"

    async def skill_gate(state: AgentState) -> dict:
        """Barra as ferramentas de plano e posição enquanto a skill que as conduz não foi carregada, e manda o modelo carregá-la."""
        calls = state["messages"][-1].tool_calls
        loaded = loaded_skills(state["messages"])
        blocked = {call["id"]: GATED[call["name"]] for call in calls if GATED.get(call["name"]) not in (None, *loaded)}
        if not blocked:
            return {}
        return {"messages": [
            ToolMessage(
                f"Bloqueada: use esta ferramenta pela skill {blocked[call['id']]}. Chame load_skill com esse nome e siga os passos dela."
                if call["id"] in blocked else "Não executada neste passo: carregue a skill pedida e chame de novo.",
                tool_call_id=call["id"], name=call["name"],
            )
            for call in calls
        ]}

    def route_after_gate(state: AgentState) -> Literal["tools", "agent"]:
        """Sem bloqueio, as ferramentas rodam; com bloqueio, o modelo volta a decidir."""
        return "agent" if state["messages"][-1].type == "tool" else "tools"

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
        context = "\n\n".join(text_of(message.content) for message in searches)
        verdict = await grader.ainvoke(GRADE_PROMPT.format(context=context, question=state["question"]))
        return "agent" if verdict.binary_score == "sim" else "rewrite"

    async def rewrite(state: AgentState) -> dict:
        """Reescreve a consulta que falhou com outros termos, descarta essa busca e manda o agente buscar de novo."""
        steps = intermediate(state["messages"], state["question"])
        queries = [call["args"].get("query", "") for m in steps for call in getattr(m, "tool_calls", []) if call["name"] == SEARCH_TOOL]
        failed = queries[-1] if queries else state["question"]
        rewritten = (await model.ainvoke(REWRITE_PROMPT.format(question=state["question"], failed=failed))).content
        message = HumanMessage(
            f"Os trechos não responderam à pergunta. Busque de novo com esta consulta reformulada: {rewritten}",
            additional_kwargs={"rewrite": True, "query": rewritten},  # marca a mensagem para o resumo e a interface a distinguirem de uma pergunta
        )
        return {"messages": [*(RemoveMessage(id=m.id) for m in steps), message], "rewrites": state["rewrites"] + 1}  # a busca ruim sai do contexto

    builder = StateGraph(AgentState)

    # nós
    builder.add_node("guard_input", make_guard_input(model))
    builder.add_node("start_turn", start_turn)
    builder.add_node("agent", agent)
    builder.add_node("skill_gate", skill_gate)
    builder.add_node("tools", ToolNode(list(tools)))
    builder.add_node("rewrite", rewrite)
    builder.add_node("guard_output", guard_output)
    builder.add_node("compact", make_compact(model))

    # arestas
    builder.add_edge(START, "guard_input")
    builder.add_conditional_edges("guard_input", route_after_input)
    builder.add_edge("start_turn", "agent")
    builder.add_conditional_edges("agent", route_after_agent)
    builder.add_conditional_edges("skill_gate", route_after_gate)
    builder.add_edge("guard_output", "compact")
    builder.add_edge("compact", END)
    builder.add_conditional_edges("tools", route_after_tools)
    builder.add_edge("rewrite", "agent")

    return builder.compile(checkpointer=InMemorySaver())