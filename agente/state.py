from langgraph.graph import MessagesState


class AgentState(MessagesState):
    """Estado do grafo: as mensagens, a pergunta do turno, quantas vezes ela foi reescrita, o risco da entrada e o resumo dos turnos antigos."""

    question: str
    rewrites: int
    risk: str
    summary: str
