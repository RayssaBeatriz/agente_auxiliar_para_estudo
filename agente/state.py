from langgraph.graph import MessagesState


class AgentState(MessagesState):
    """Estado do grafo: as mensagens, a pergunta do turno, quantas vezes ela foi reescrita e o risco da entrada."""

    question: str
    rewrites: int
    risk: str
