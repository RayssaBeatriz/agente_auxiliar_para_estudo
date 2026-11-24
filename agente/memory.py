"""Memória de curto prazo: o checkpointer guarda a conversa por thread, e a poda e o resumo mantêm o histórico pequeno."""
from langchain.messages import AnyMessage, RemoveMessage
from langchain_core.language_models import BaseChatModel

from .prompts import SUMMARY_PROMPT
from .skills import LOAD_SKILL
from .state import AgentState

MAX_TURNS = 4  # acima disso, os turnos mais antigos viram resumo
KEEP_TURNS = 2  # turnos recentes mantidos por inteiro


def is_question(message: AnyMessage) -> bool:
    """Diz se a mensagem é uma pergunta do usuário, e não uma instrução de reformulação do grafo."""
    return message.type == "human" and not message.additional_kwargs.get("rewrite")


def is_skill(message: AnyMessage) -> bool:
    """Diz se a mensagem é uma chamada de load_skill ou o texto da skill carregada."""
    if message.type == "tool":
        return message.name == LOAD_SKILL
    calls = getattr(message, "tool_calls", None)
    return bool(calls) and all(call["name"] == LOAD_SKILL for call in calls)


def intermediate(messages: list[AnyMessage], question: str) -> list[AnyMessage]:
    """Devolve, no turno atual, as chamadas de ferramenta, os trechos recuperados e as instruções de reformulação, menos as skills carregadas."""
    start = max((i for i, m in enumerate(messages) if is_question(m) and m.content == question), default=0)
    return [m for m in messages[start + 1 :] if not is_skill(m) and (m.type == "tool" or getattr(m, "tool_calls", None) or not is_question(m) and m.type == "human")]


def make_compact(model: BaseChatModel):
    """Cria o nó que poda o turno que acabou e resume os turnos antigos."""

    async def compact(state: AgentState) -> dict:
        """Remove os trechos do turno, que já estão na resposta, e resume os turnos antigos quando passam de MAX_TURNS."""
        messages = state["messages"]
        drop = {m.id for m in intermediate(messages, state["question"])}
        update = {}
        starts = [i for i, m in enumerate(messages) if is_question(m)]
        if len(starts) > MAX_TURNS:
            old = messages[: starts[-KEEP_TURNS]]
            conversation = "\n".join(f"{m.type}: {m.content}" for m in old if m.type in ("human", "ai") and m.content and not m.additional_kwargs.get("rewrite"))
            reply = await model.ainvoke(SUMMARY_PROMPT.format(summary=state.get("summary") or "(nenhum)", conversation=conversation))
            update["summary"] = reply.content
            drop |= {m.id for m in old}
        update["messages"] = [RemoveMessage(id=message_id) for message_id in drop]
        return update

    return compact