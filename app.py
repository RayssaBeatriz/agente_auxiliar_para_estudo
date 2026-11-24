"""Interface em Streamlit: chat, nova conversa e, em cada resposta, as ferramentas chamadas e as skills carregadas."""
import asyncio
import queue
import threading

import streamlit as st
from dotenv import load_dotenv
from langchain.messages import HumanMessage

from agente.graph import build_graph, new_conversation
from agente.mcp_tools import load_mcp_tools
from agente.model import get_model
from agente.rag import SEARCH_TOOL
from agente.skills import LOAD_SKILL, load_skill
from agente.utils import text_of

load_dotenv()

STEPS = {
    "guard_input": "Verificando a mensagem",
    "start_turn": "Lendo a pergunta",
    "agent": "Pensando",
    "tools": "Executando ferramentas",
    "rewrite": "Reformulando a busca",
    "guard_output": "Verificando a resposta",
    "compact": "Atualizando a memória",
}


@st.cache_resource
def start():
    """Cria uma vez o laço de eventos e o grafo, para a memória sobreviver às reexecuções do script."""
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()

    async def build():
        return build_graph(get_model(), [*await load_mcp_tools(), load_skill])

    return loop, asyncio.run_coroutine_threadsafe(build(), loop).result()


def stream_turn(loop, graph, question: str, config: dict):
    """Roda o turno no laço de fundo e entrega cada atualização dos nós."""
    events = queue.Queue()

    async def pump():
        try:
            async for step in graph.astream({"messages": [HumanMessage(question)]}, config, stream_mode="updates"):
                for node, update in step.items():
                    events.put((node, update or {}))
        except Exception as error:
            events.put(("error", error))
        events.put(None)

    asyncio.run_coroutine_threadsafe(pump(), loop)
    while (event := events.get()) is not None:
        yield event


def run_turn(loop, graph, question: str, config: dict) -> tuple[str, list[str], list[str]]:
    """Devolve a resposta, as ferramentas chamadas e as skills carregadas, lidas durante o turno porque a memória apaga as chamadas do estado."""
    answer, tools, skills = "", [], []
    with st.status("Processando...") as status:
        for node, update in stream_turn(loop, graph, question, config):
            if node == "error":
                answer = f"Não consegui responder: {update}"
                status.update(label="Erro", state="error")
                break
            status.update(label=STEPS.get(node, node))
            for message in update.get("messages", []):
                if message.type == "remove":
                    continue
                for call in getattr(message, "tool_calls", None) or []:
                    if call["name"] == LOAD_SKILL:
                        skills.append(call["args"].get("name", ""))
                    elif call["name"] == SEARCH_TOOL:
                        tools.append(f"{call['name']}: {call['args'].get('query', '')}")
                    else:
                        tools.append(call["name"])
                if node in ("guard_input", "guard_output"):
                    answer = text_of(message.content)
        else:
            status.update(label="Pronto", state="complete")
    return answer, tools, skills


def show(content: str, tools: list[str], skills: list[str]) -> None:
    st.markdown(content)
    if tools:
        st.caption("Ferramentas: " + "; ".join(tools))
    if skills:
        st.caption("Skills: " + ", ".join(skills))


st.title("Guia de estudos para os concursos da Dataprev")

try:
    loop, graph = start()
except Exception as error:
    st.error(str(error))
    st.stop()

if "config" not in st.session_state:
    st.session_state.config = new_conversation()
    st.session_state.history = []

if st.sidebar.button("Nova conversa"):
    st.session_state.config = new_conversation()
    st.session_state.history = []

for item in st.session_state.history:
    with st.chat_message(item["role"]):
        show(item["content"], item.get("tools", []), item.get("skills", []))

if question := st.chat_input("Pergunte sobre os concursos da Dataprev"):
    st.session_state.history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        answer, tools, skills = run_turn(loop, graph, question, st.session_state.config)
        show(answer, tools, skills)
    st.session_state.history.append({"role": "assistant", "content": answer, "tools": tools, "skills": skills})
