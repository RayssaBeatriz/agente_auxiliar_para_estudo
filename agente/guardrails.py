"""Guardrails do agente: filtro de entrada (regras fixas e classificador) e verificação de fonte e vazamento na saída (regras fixas)."""
import re
from typing import Literal

from langchain.messages import AIMessage
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from .prompts import GRADE_PROMPT, GUARD_PROMPT, REWRITE_PROMPT, SKILLS_PROMPT, SUMMARY_PROMPT, SYSTEM_PROMPT
from .rag import SEARCH_TOOL
from .state import AgentState
from .utils import text_of

RECUSAS = {
    "fora_do_escopo": "Só posso ajudar com estudo para concursos, em especial os editais da Dataprev de 2024 e 2026.",
    "vazamento": "Não posso compartilhar minhas instruções internas. Posso ajudar com dúvidas sobre os editais da Dataprev.",
    "erro": "Não consegui verificar sua mensagem agora. Tente novamente em instantes.",
    "vazia": "Não consegui montar a resposta agora. Tente reformular a pergunta.",
}
AVISO = "\n\nAtenção: esta resposta não cita a fonte dos editais. Confira a informação no edital oficial antes de usar."
ESPACOS = str.maketrans({"\u00a0": " ", "\u202f": " ", "\u2009": " ", "\u2011": "-"})  # o modelo troca espaços e hífens por versões sem quebra
CITACAO = re.compile(r"\(Concurso (2024|2026)")
CABECALHO = re.compile(r"\[(Concurso (?:2024|2026)) \| ([^|\]]+?) \| (p\. ?\d+)\]")  # fonte no formato dos trechos recuperados

# pedidos de revelar as instruções do assistente, que valem mesmo escondidos dentro de uma pergunta legítima
VAZAMENTO = re.compile(
    r"system prompt|prompt (de|do) sistema|prompt (inicial|interno|oculto)|\b(seu|teu) prompt|mensagem de sistema|developer message"
    r"|\b(suas|tuas) instru[cç][õo]es|instru[cç][õo]es (internas|iniciais|ocultas|do sistema|de sistema)"
    r"|\b(suas|tuas) regras (internas|iniciais|ocultas|do sistema|de sistema)"
    r"|ignore (todas |as |suas |as suas )?(instru[cç][õo]es|regras)|ignore (all|previous|the above) (instructions|rules)",
    re.IGNORECASE,
)
# palavras que mostram que a mensagem trata do domínio, ou pede a data e a hora, que o assistente informa
ESCOPO = re.compile(
    r"concurs|edital|dataprev|\bprovas?\b|simulad|\bacert(ei|os|amos)\b|cronograma|plano de estudo|\bestud(ar|o|os)\b|\bvagas?\b|inscri|candidat"
    r"|\bcargos?\b|\bcotas?\b|gabarito|habilit|classifica|aprovad|reprovad|desempate|\b20(24|26)\b|conhecimentos|portugu[eê]s|ingl[eê]s"
    r"|racioc[ií]nio|atualidades|legisla[cç]|espec[ií]fic|disciplina|que dia|que horas|data de hoje|hor[aá]rio atual",
    re.IGNORECASE,
)
# linhas dos prompts internos longas o bastante para identificar um vazamento, sem as descrições das ferramentas
TRECHOS = [
    linha.strip().lower()
    for prompt in (SYSTEM_PROMPT, SKILLS_PROMPT, GRADE_PROMPT, REWRITE_PROMPT, GUARD_PROMPT, SUMMARY_PROMPT)
    for linha in prompt.splitlines()
    if len(linha.strip()) >= 30 and not re.match(r"[a-z_]+: ", linha.strip())
]


class InputCheck(BaseModel):
    """Risco identificado na mensagem do usuário."""

    risk: Literal["nenhum", "vazamento", "fora_do_escopo"] = Field(description="o risco da mensagem, ou 'nenhum'")


def previous_question(messages: list) -> str:
    """Última pergunta anterior do usuário, que dá contexto a mensagens curtas como 'sim, pode salvar'."""
    for message in reversed(messages[:-1]):
        if message.type == "human" and not message.additional_kwargs.get("rewrite"):
            return text_of(message.content)
    return "(nenhuma)"


def make_guard_input(model: BaseChatModel):
    """Cria o nó de entrada: regras fixas pegam os casos claros e um classificador decide os demais."""
    async def classify(message: str, previous: str) -> str:
        """Pergunta ao classificador, com uma segunda tentativa se a saída vier malformada ou a chamada falhar."""
        classifier = model.with_structured_output(InputCheck, method="json_schema")
        for _ in range(2):
            try:
                return (await classifier.ainvoke(GUARD_PROMPT.format(message=message, previous=previous))).risk
            except Exception:
                continue
        return "erro"

    async def guard_input(state: AgentState) -> dict:
        """Classifica a última mensagem; se houver risco, responde com uma recusa e marca o risco."""
        message = text_of(state["messages"][-1].content)
        if VAZAMENTO.search(message):
            risk = "vazamento"
        else:
            risk = await classify(message, previous_question(state["messages"]))
            if risk in ("fora_do_escopo", "erro") and ESCOPO.search(message):
                risk = "nenhum"  # palavras do domínio vencem o veredito do modelo, que erra em mensagens legítimas
        if risk == "nenhum":
            return {"risk": risk}
        return {"risk": risk, "messages": [AIMessage(RECUSAS[risk])]}

    return guard_input


def route_after_input(state: AgentState) -> Literal["start_turn", "__end__"]:
    """Mensagem sem risco segue para o agente; com risco, o turno termina na recusa."""
    return "start_turn" if state["risk"] == "nenhum" else "__end__"


async def guard_output(state: AgentState) -> dict:
    """Troca a resposta que repete os prompts internos por uma recusa, padroniza as fontes e avisa quando a resposta de uma busca não cita fonte."""
    answer = state["messages"][-1]
    text = text_of(answer.content).translate(ESPACOS).strip()
    if not text:
        return {"messages": [answer.model_copy(update={"content": RECUSAS["vazia"]})]}
    if any(trecho in text.lower() for trecho in TRECHOS):
        return {"messages": [answer.model_copy(update={"content": RECUSAS["vazamento"]})]}
    text = CABECALHO.sub(r"(\1, \2, \3)", text)
    searched = False
    for message in reversed(state["messages"]):
        if message.type == "human" and message.content == state["question"]:
            break
        searched = searched or (message.type == "tool" and message.name == SEARCH_TOOL)
    if searched and not CITACAO.search(text) and "não encontrei" not in text.lower():
        text += AVISO
    return {"messages": [answer.model_copy(update={"content": text})]}
