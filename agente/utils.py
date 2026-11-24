def text_of(content) -> str:
    """Texto de uma mensagem, seja string ou lista de blocos (como as ferramentas MCP devolvem)."""
    if isinstance(content, str):
        return content
    return "\n".join(block.get("text", "") if isinstance(block, dict) else str(block) for block in content)
