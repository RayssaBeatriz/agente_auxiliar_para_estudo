"""Conexão com os servidores MCP: o próprio (HTTP) e o da comunidade (stdio)."""
import os

from langchain_mcp_adapters.client import MultiServerMCPClient

ESTUDOS_URL = os.getenv("MCP_ESTUDOS_URL", "http://127.0.0.1:8765/mcp")
FUSO = os.getenv("TIMEZONE", "America/Sao_Paulo")


def servers() -> dict:
    return {
        # servidor próprio, iniciado à parte
        "estudos": {"transport": "streamable_http", "url": ESTUDOS_URL},
        # servidor da comunidade: hora atual e conversão de fusos
        "time": {"transport": "stdio", "command": "uvx", "args": ["mcp-server-time", "--local-timezone", FUSO]},
    }


async def load_mcp_tools(config: dict | None = None) -> list:
    """Descobre as ferramentas dos servidores. Sem o servidor próprio no ar, explica como iniciá-lo."""
    client = MultiServerMCPClient(config or servers(), tool_name_prefix=False)
    try:
        return await client.get_tools()
    except Exception as error:  # a conexão recusada chega como ExceptionGroup
        raise RuntimeError(
            "Não consegui conectar aos servidores MCP. Inicie o servidor próprio em outro terminal com "
            f"`python -m agente.mcp_server.estudos_server` (esperado em {ESTUDOS_URL}) e confira se o `uvx` está instalado. "
            f"Detalhe: {error!r}"
        ) from error