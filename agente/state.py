from langgraph.graph import MessagesState


class AgentState(MessagesState):
    """Estado do grafo: as mensagens, a pergunta do turno e quantas vezes ela foi reescrita."""

    question: str
    rewrites: int
