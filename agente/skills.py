"""Skills: pastas com SKILL.md. Só o catálogo (nome e descrição) vai na mensagem de sistema;
o corpo entra no contexto quando o modelo chama `load_skill`."""
from pathlib import Path

import yaml
from langchain_core.tools import tool

from .utils import text_of

SKILLS_DIR = Path(__file__).resolve().parent / "skills_md"
LOAD_SKILL = "load_skill"


def _split(texto: str) -> tuple[dict, str]:
    _, frontmatter, corpo = texto.split("---", 2)
    return yaml.safe_load(frontmatter), corpo.strip()


def list_skills() -> list[dict]:
    """Metadados (name, description) de cada skill encontrada."""
    return [_split(path.read_text(encoding="utf-8"))[0] for path in sorted(SKILLS_DIR.glob("*/SKILL.md"))]


def catalog() -> str:
    return "\n".join(f"- {meta['name']}: {meta['description']}" for meta in list_skills())


@tool
def load_skill(name: str) -> str:
    """Carrega as instruções completas de uma skill pelo nome, como aparece no catálogo da mensagem de sistema."""
    validos = {meta["name"] for meta in list_skills()}
    if name not in validos:  # só nomes do catálogo
        return f"Erro: skill {name!r} não existe. Skills disponíveis: {sorted(validos)}"
    return (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")


def loaded_skills(messages: list) -> set[str]:
    """Nomes das skills já carregadas com sucesso na conversa."""
    chamadas = {c["id"]: c["args"].get("name") for m in messages for c in getattr(m, "tool_calls", None) or [] if c["name"] == LOAD_SKILL}
    return {chamadas[m.tool_call_id] for m in messages if m.type == "tool" and m.name == LOAD_SKILL and m.tool_call_id in chamadas
            and not text_of(m.content).startswith("Erro")}
