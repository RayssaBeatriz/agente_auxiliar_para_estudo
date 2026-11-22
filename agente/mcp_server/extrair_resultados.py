"""Extrai dos PDFs de 'Resultado da prova objetiva' só perfil, localidade, nota e cota, sem nome nem inscrição.

Uso (uma vez, com os PDFs fora do repositório):
    python -m agente.mcp_server.extrair_resultados 2024 caminho/resultado-2024.pdf
    python -m agente.mcp_server.extrair_resultados 2026 caminho/resultado-2026.pdf
Gera data/resultados/notas_<edital>.csv.
"""
import csv
import re
import sys
from pathlib import Path

import pdfplumber

SAIDA = Path(__file__).resolve().parent.parent.parent / "data" / "resultados"
NUM = r"\d+(?:,5)?"
DATA = r"\d{2}/\d{2}/\d{4}"
# 2026: gerais e específicos em colunas únicas. 2024: cinco colunas de gerais, depois específicos.
LINHA = {
    "2026": re.compile(rf"^\d{{12}}\s+.+?\s+{DATA}\s+(?P<gerais>{NUM})\s+(?P<especificos>{NUM})\s+(?P<nota>{NUM})\s+(?P<situacao>Aprovado.*)$"),
    "2024": re.compile(rf"^\d{{9}}\s+.+?\s+{DATA}\s+(?P<g1>\d+)\s+(?P<g2>\d+)\s+(?P<g3>\d+)\s+(?P<g4>\d+)\s+(?P<g5>\d+)\s+"
                       rf"(?P<especificos>{NUM})\s+(?P<nota>{NUM})\s+(?P<situacao>Aprovado.*)$"),
}
INICIO_CABECALHO = ("Conhecimentos Conhecimentos", "Língua Língua")


def _numero(texto: str) -> float:
    return float(texto.replace(",", "."))


def _perfil_e_local(linhas: list[str]) -> tuple[str, str] | None:
    """Perfil e localidade ficam entre a linha 'EDITAL' e o cabeçalho da tabela."""
    try:
        edital = next(i for i, l in enumerate(linhas) if l.startswith("EDITAL"))
        cabecalho = next(i for i, l in enumerate(linhas) if l.startswith(INICIO_CABECALHO))
    except StopIteration:
        return None
    meio = linhas[edital + 1:cabecalho]
    if len(meio) < 2:
        return None
    local = re.sub(r"\s*\((\w{2})\)$", r"/\1", meio[-1].replace(" / ", "/")).strip()
    return " ".join(meio[:-1]).strip(), local


def extrair(edital: str, pdf: Path) -> tuple[list[dict], list[int]]:
    registros, paginas_sem_cabecalho = [], []
    anterior = None  # linha que sobra no topo de uma página vem sem cabeçalho: pertence ao grupo anterior
    with pdfplumber.open(pdf) as arquivo:
        for numero, pagina in enumerate(arquivo.pages, start=1):
            linhas = [l.strip() for l in (pagina.extract_text() or "").splitlines()]
            achados = [m for l in linhas if (m := LINHA[edital].match(l))]
            if not achados:
                continue
            cabecalho = _perfil_e_local(linhas) or anterior
            if not cabecalho:
                paginas_sem_cabecalho.append(numero)
                continue
            anterior = cabecalho
            for m in achados:
                dados = m.groupdict()
                gerais = _numero(dados["gerais"]) if edital == "2026" else float(sum(int(dados[f"g{i}"]) for i in range(1, 6)))
                especificos, nota = _numero(dados["especificos"]), _numero(dados["nota"])
                if abs(gerais + especificos - nota) > 0.01:  # linha lida errada: melhor descartar que gravar
                    paginas_sem_cabecalho.append(numero)
                    continue
                situacao = dados["situacao"]
                registros.append({
                    "perfil": cabecalho[0], "localidade": cabecalho[1], "gerais": gerais,
                    "especificos": especificos, "nota": nota,
                    "cota_negro": "Negro" in situacao, "cota_pcd": "PcD" in situacao,
                })
    return registros, paginas_sem_cabecalho


def main() -> None:
    if len(sys.argv) != 3 or sys.argv[1] not in LINHA:
        sys.exit("Uso: python -m agente.mcp_server.extrair_resultados <2024|2026> <arquivo.pdf>")
    edital, pdf = sys.argv[1], Path(sys.argv[2])
    registros, problemas = extrair(edital, pdf)
    SAIDA.mkdir(parents=True, exist_ok=True)
    destino = SAIDA / f"notas_{edital}.csv"
    with destino.open("w", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=list(registros[0]))
        escritor.writeheader()
        escritor.writerows(registros)
    grupos = {(r["perfil"], r["localidade"]) for r in registros}
    print(f"{len(registros)} linhas, {len(grupos)} grupos perfil/localidade -> {destino}")
    if problemas:
        print(f"Atenção: páginas com linhas descartadas ou sem cabeçalho: {sorted(set(problemas))}")


if __name__ == "__main__":
    main()