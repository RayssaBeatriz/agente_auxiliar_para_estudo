"""Guardrails do agente: filtro de escopo na entrada (classificador) e verificação de fonte na saída (regra fixa)."""
import re
from typing import Literal

from langchain.messages import AIMessage
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from .prompts import GRADE_PROMPT, GUARD_PROMPT, REWRITE_PROMPT, SUMMARY_PROMPT, SYSTEM_PROMPT
from .rag import SEARCH_TOOL
from .state import AgentState

RECUSAS = {
    "fora_do_escopo": "Só posso ajudar com estudo para concursos, em especial os editais da Dataprev de 2024 e 2026.",
    "vazamento": "Não posso compartilhar minhas instruções internas. Posso ajudar com dúvidas sobre os editais da Dataprev.",
}
AVISO = "\n\nAtenção: esta resposta não cita a fonte dos editais. Confira a informação no edital oficial antes de usar."
CITACAO = re.compile(r"\(Concurso (2024|2026)")
# linhas dos prompts internos longas o bastante para identificar um vazamento
TRECHOS = [
    linha.strip().lower()
    for prompt in (SYSTEM_PROMPT, GRADE_PROMPT, REWRITE_PROMPT, GUARD_PROMPT, SUMMARY_PROMPT)
    for linha in prompt.splitlines()
    if len(linha.strip()) >= 30
]


class InputCheck(BaseModel):
    """Risco identificado na mensagem do usuário."""

    risk: Literal["nenhum", "vazamento", "fora_do_escopo"] = Field(description="o risco da mensagem, ou 'nenhum'")


def make_guard_input(model: BaseChatModel):
    """Cria o nó de entrada: um classificador decide se a mensagem pede as instruções internas ou foge do escopo de estudo."""

    async def guard_input(state: AgentState) -> dict:
        """Classifica a última mensagem; se houver risco, responde com uma recusa e marca o risco."""
        classifier = model.with_structured_output(InputCheck, method="json_schema")
        message = state["messages"][-1].content
        risk = (await classifier.ainvoke(GUARD_PROMPT.format(message=message))).risk
        if risk == "nenhum":
            return {"risk": risk}
        return {"risk": risk, "messages": [AIMessage(RECUSAS[risk])]}

    return guard_input


def route_after_input(state: AgentState) -> Literal["start_turn", "__end__"]:
    """Mensagem sem risco segue para o agente; com risco, o turno termina na recusa."""
    return "start_turn" if state["risk"] == "nenhum" else "__end__"


async def guard_output(state: AgentState) -> dict:
    """Troca a resposta que repete os prompts internos por uma recusa e avisa quando a resposta de uma busca não cita fonte."""
    answer = state["messages"][-1]
    text = answer.content
    if any(trecho in text.lower() for trecho in TRECHOS):
        return {"messages": [answer.model_copy(update={"content": RECUSAS["vazamento"]})]}
    searched = False
    for message in reversed(state["messages"]):
        if message.type == "human" and message.content == state["question"]:
            break
        searched = searched or (message.type == "tool" and message.name == SEARCH_TOOL)
    if searched and not CITACAO.search(text) and "não encontrei" not in text.lower():
        text += AVISO
    return {"messages": [answer.model_copy(update={"content": text})]}