import os

from langchain.chat_models import init_chat_model


def get_model():
    """Cria o modelo de chat a partir das variáveis de ambiente MODEL e REASONING_EFFORT."""
    kwargs = {"temperature": 0.0, "max_retries": 6}
    if effort := os.getenv("REASONING_EFFORT"):
        kwargs["reasoning_effort"] = effort
    return init_chat_model(os.getenv("MODEL", "groq:openai/gpt-oss-120b"), **kwargs)
