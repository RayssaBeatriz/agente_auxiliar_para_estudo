"""Lógica do servidor MCP próprio, sem dependência do MCP (para poder ser testada direto).

Tudo aqui vem dos documentos da pasta `data/`: a estrutura da prova (item 9 dos editais) e
as tabelas de demanda de candidatos por vaga, lidas dos PDFs.
"""
import csv
import math
import re
import statistics
from datetime import date
from functools import cache
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "data"
PLANOS_DIR = Path(__import__("os").environ.get("PLANOS_DIR", ROOT / "planos"))

NOTA_MINIMA = 57.5  # mínimo de pontos, sem zerar nenhuma disciplina
PESO_GERAIS = 1.0
PESO_ESPECIFICOS = 2.5

# Estrutura da prova objetiva: disciplina -> nº de questões
PROVA = {
    "2024": {"lingua_portuguesa": 12, "lingua_inglesa": 12, "raciocinio_logico": 6,
             "atualidades": 5, "legislacao_seguranca": 5, "conhecimentos_especificos": 30},
    "2026": {"lingua_portuguesa": 12, "lingua_inglesa": 12, "raciocinio_logico": 5,
             "atualidades": 6, "legislacao_seguranca": 5, "conhecimentos_especificos": 30},
}
NOMES = {
    "lingua_portuguesa": "Língua Portuguesa",
    "lingua_inglesa": "Língua Inglesa",
    "raciocinio_logico": "Raciocínio Lógico Matemático",
    "atualidades": "Atualidades (2026: Atualidades e Inteligência Artificial)",
    "legislacao_seguranca": "Legislação de Segurança da Informação e Proteção de Dados",
    "conhecimentos_especificos": "Conhecimentos Específicos",
}


def _peso(disciplina: str) -> float:
    return PESO_ESPECIFICOS if disciplina == "conhecimentos_especificos" else PESO_GERAIS


def _edital_valido(edital: str) -> str | None:
    if edital not in PROVA:
        return f"Edital inválido: {edital!r}. Use '2024' ou '2026'."
    return None


# - simulação de nota
def simular_nota(edital: str, acertos: dict[str, int]) -> dict:
    """Calcula a nota da prova objetiva e confere os critérios de aprovação do edital."""
    if erro := _edital_valido(edital):
        return {"erro": erro}
    estrutura = PROVA[edital]
    desconhecidas = [d for d in acertos if d not in estrutura]
    if desconhecidas:
        return {"erro": f"Disciplina(s) desconhecida(s): {desconhecidas}. Válidas: {list(estrutura)}"}

    detalhe, total = {}, 0.0
    for disciplina, questoes in estrutura.items():
        certas = acertos.get(disciplina, 0)
        if certas < 0 or certas > questoes:
            return {"erro": f"{NOMES[disciplina]}: {certas} acertos é impossível, a prova tem {questoes} questões."}
        pontos = certas * _peso(disciplina)
        total += pontos
        detalhe[disciplina] = {"acertos": certas, "questoes": questoes, "pontos": pontos}

    zeradas = [NOMES[d] for d, v in detalhe.items() if v["acertos"] == 0]
    motivos = []
    if total < NOTA_MINIMA:
        motivos.append(f"nota {total:g} abaixo do mínimo de {NOTA_MINIMA:g} pontos")
    if zeradas:
        motivos.append(f"disciplina(s) zerada(s): {', '.join(zeradas)}")

    gerais = total - detalhe["conhecimentos_especificos"]["pontos"]
    faltam = max(NOTA_MINIMA - total, 0.0)
    return {
        "edital": edital,
        "nota_total": total,
        "nota_maxima": 115.0,
        "nota_minima_aprovacao": NOTA_MINIMA,
        "aprovado_na_prova_objetiva": not motivos,
        "motivos_reprovacao": motivos,
        "pontos_que_faltam": faltam,
        "acertos_especificos_necessarios_com_essa_nota_de_gerais": math.ceil((NOTA_MINIMA - gerais) / PESO_ESPECIFICOS),
        "detalhe": detalhe,
    }


# - concorrência
_LOCAL = r"[A-ZÀ-Ý][a-zà-ÿ]+(?:\s+(?:(?:de|do|da)\s+)?[A-ZÀ-Ý][a-zà-ÿ]+)*"
_LINHA = re.compile(
    rf"^(?P<perfil>.+?)\s+(?P<local>{_LOCAL})\s*/\s*(?P<uf>[A-Z]{{2}})\s+"
    r"(?P<vagas>\d[\d.]*)\s+(?P<cand>\d[\d.]*)\s+(?P<razao>\d[\d.]*,\d+)$"
)
ARQUIVO_DEMANDA = {
    "2026": "demanda-de-candidatos-por-vaga_0.pdf",
    "2024": "demanda_de_candidato_por_vaga_2_1.pdf",
}


def _num(texto: str) -> int:
    return int(texto.replace(".", ""))


@cache
def carregar_demanda(edital: str) -> tuple[dict, ...]:
    """Lê a tabela 'Demanda de candidatos por vaga' do PDF do concurso."""
    with pdfplumber.open(DATA_DIR / ARQUIVO_DEMANDA[edital]) as pdf:
        linhas = [l.strip() for page in pdf.pages for l in (page.extract_text() or "").splitlines()]
    registros = []
    for linha in linhas:
        if achado := _LINHA.match(linha):
            perfil = re.sub(r"^ANALISTA DE TECNOLOGIA DA INFORMAÇÃO - ", "", achado["perfil"])
            perfil = re.sub(r"\s+TOTAL$", "", perfil)
            registros.append({
                "perfil": perfil,
                "localidade": f"{achado['local']}/{achado['uf']}",
                "vagas": _num(achado["vagas"]),
                "candidatos": _num(achado["cand"]),
                "candidatos_por_vaga": float(achado["razao"].replace(".", "").replace(",", ".")),
            })
    return tuple(registros)


def _sem_acento(texto: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


OBSERVACAO_VAGAS = ("'vagas' é o TOTAL da tabela oficial de demanda: vagas imediatas somadas ao cadastro de reserva. "
                    "O edital (item 3.1) detalha quantas são imediatas.")


def consultar_concorrencia(edital: str, perfil: str = "", localidade: str = "", limite: int = 10) -> dict:
    """Filtra a demanda por perfil e/ou localidade (trecho do nome, sem diferenciar acentos) e ordena pela menor concorrência."""
    if erro := _edital_valido(edital):
        return {"erro": erro}
    linhas = [
        r for r in carregar_demanda(edital)
        if _sem_acento(perfil) in _sem_acento(r["perfil"]) and _sem_acento(localidade) in _sem_acento(r["localidade"])
    ]
    if not linhas:
        return {"edital": edital, "encontrados": 0, "resultados": [],
                "aviso": "Nenhuma combinação de perfil e localidade encontrada neste concurso."}
    linhas = sorted(linhas, key=lambda r: r["candidatos_por_vaga"])
    return {
        "edital": edital,
        "encontrados": len(linhas),
        "total_vagas": sum(r["vagas"] for r in linhas),
        "total_candidatos": sum(r["candidatos"] for r in linhas),
        "ordenado_por": "menor candidatos_por_vaga",
        "observacao": OBSERVACAO_VAGAS,
        "resultados": linhas[:limite],
    }


# - cronograma de estudo
def _data(texto: str) -> date:
    return date.fromisoformat(texto)


FATOR_DIFICULDADE = 1.5   # +50% de peso para disciplinas em que o aluno tem dificuldade
FATOR_FACILIDADE = 0.7    # -30% para as que ele domina
MINIMO_DISCIPLINA = 0.05  # nenhuma disciplina fica abaixo de 5% das horas (não se pode zerar nenhuma)

_APELIDOS = {
    "lingua_portuguesa": ("portugues",),
    "lingua_inglesa": ("ingles",),
    "raciocinio_logico": ("raciocinio", "logico", "matematica"),
    "atualidades": ("atualidades", "inteligencia artificial"),
    "legislacao_seguranca": ("legislacao", "seguranca", "protecao de dados", "lgpd"),
    "conhecimentos_especificos": ("especifico",),
}


def _disciplinas_citadas(itens: list[str] | None) -> tuple[set[str], list[str]]:
    """Converte nomes livres ('português', 'inglês', 'raciocínio lógico') nas chaves de PROVA."""
    achadas, ignoradas = set(), []
    for item in itens or []:
        texto = _sem_acento(item).lower().strip()
        chave = next((k for k in NOMES if texto == k or texto.replace(" ", "_") == k
                      or any(p and p in texto for p in _APELIDOS[k])), None)
        (achadas.add(chave) if chave else ignoradas.append(item))
    return achadas, ignoradas


def montar_cronograma(edital: str, data_inicio: str | None, data_prova: str | None, horas_por_semana: float,
                      dificuldades: list[str] | None = None, facilidades: list[str] | None = None,
                      semanas: int | None = None) -> dict:
    """Distribui as horas de estudo até a prova em fases e por disciplina, na proporção dos pontos da prova,
    ajustada pelas disciplinas em que o aluno tem dificuldade ou facilidade. O prazo vem da data da prova
    (com a data de início) ou do número de semanas; se vierem os dois, vale a data."""
    if erro := _edital_valido(edital):
        return {"erro": erro}
    if horas_por_semana <= 0 or horas_por_semana > 80:
        return {"erro": "horas_por_semana deve estar entre 0 e 80."}
    if data_prova:
        try:
            inicio, prova = _data(data_inicio), _data(data_prova)
        except (ValueError, TypeError):
            return {"erro": "Informe data_inicio e data_prova no formato AAAA-MM-DD."}
        dias = (prova - inicio).days
        if dias <= 0:
            return {"erro": f"A data da prova ({prova.isoformat()}) não é posterior ao início ({inicio.isoformat()}): "
                            "não há tempo de estudo a distribuir. Informe a data prevista da próxima prova ou quantas semanas há para estudar."}
        semanas = max(math.ceil(dias / 7), 1)
        total_horas = round(horas_por_semana * dias / 7, 1)
    elif semanas:
        if not 1 <= semanas <= 104:
            return {"erro": "semanas deve estar entre 1 e 104."}
        total_horas = round(horas_por_semana * semanas, 1)
    else:
        return {"erro": "Informe a data da prova (AAAA-MM-DD) ou o número de semanas até a prova."}
    # fases: base (conteúdo), revisão com questões e simulados; poucas semanas encolhem as fases finais
    divisao = [("base: estudo do conteúdo programático", 0.60), ("revisão e resolução de questões", 0.25),
               ("simulados e revisão final", 0.15)]
    fases, cursor = [], 0
    for i, (nome, parcela) in enumerate(divisao):
        n = semanas - cursor if i == len(divisao) - 1 else max(round(semanas * parcela), 1 if semanas >= 3 else 0)
        n = min(n, semanas - cursor)
        if n <= 0:
            continue
        fases.append({"fase": nome, "semanas": n, "horas": round(n * horas_por_semana, 1)})
        cursor += n

    estrutura = PROVA[edital]
    pontos = {d: q * _peso(d) for d, q in estrutura.items()}
    dif, ign1 = _disciplinas_citadas(dificuldades)
    fac, ign2 = _disciplinas_citadas(facilidades)
    dif_e_fac = dif & fac
    dif, fac = dif - dif_e_fac, fac - dif_e_fac  
    pesos = {d: p * (FATOR_DIFICULDADE if d in dif else FATOR_FACILIDADE if d in fac else 1.0) for d, p in pontos.items()}
    soma = sum(pesos.values())
    fracao = {d: max(p / soma, MINIMO_DISCIPLINA) for d, p in pesos.items()}
    total_frac = sum(fracao.values())
    por_disciplina = {NOMES[d]: round(total_horas * f / total_frac, 1) for d, f in fracao.items()}
    ajuste = {}
    if dif or fac:
        ajuste = {"mais_tempo": [NOMES[d] for d in sorted(dif)], "menos_tempo": [NOMES[d] for d in sorted(fac)]}
    if ign1 or ign2 or dif_e_fac:
        ajuste["nao_reconhecidas"] = ign1 + ign2 + [NOMES[d] for d in sorted(dif_e_fac)]
    return {
        "edital_de_referencia": edital,
        **({"data_inicio": inicio.isoformat(), "data_prova": prova.isoformat(), "dias_ate_a_prova": dias} if data_prova
           else {"prazo": "número de semanas informado pelo usuário, sem datas de calendário"}),
        "semanas": semanas,
        "horas_totais": total_horas,
        "fases": fases,
        "horas_por_disciplina": por_disciplina,
        "criterio": "horas proporcionais aos pontos de cada disciplina na prova (Conhecimentos Específicos vale 75 de 115)"
                    + ("; ajustadas por dificuldade (+50%) e facilidade (-30%), com mínimo de 5% por disciplina" if dif or fac else ""),
        **({"ajuste_do_aluno": ajuste} if ajuste else {}),
        "simulados_recomendados": max(semanas // 3, 1),
    }


# - posição entre os habilitados
RESULTADOS_DIR = DATA_DIR / "resultados"
FONTE_RESULTADO = {
    "2024": "resultado da prova objetiva do concurso de 2024 (FGV, 12/12/2024)",
    "2026": "resultado PROVISÓRIO da prova objetiva do concurso de 2026 (18/11/2026), sujeito a mudanças após recursos",
}
PREFIXO_PERFIL = "analista de tecnologia da informacao - "


def _chave_perfil(perfil: str) -> str:
    return _sem_acento(perfil).replace(PREFIXO_PERFIL, "").strip()


@cache
def carregar_notas(edital: str) -> dict[tuple[str, str], tuple[float, ...]]:
    """Notas dos habilitados por (perfil, localidade), da maior para a menor, lidas do CSV sem nomes."""
    grupos: dict[tuple[str, str], list[float]] = {}
    with (RESULTADOS_DIR / f"notas_{edital}.csv").open(encoding="utf-8") as arquivo:
        for linha in csv.DictReader(arquivo):
            grupos.setdefault((linha["perfil"], linha["localidade"]), []).append(float(linha["nota"]))
    return {chave: tuple(sorted(notas, reverse=True)) for chave, notas in grupos.items()}


def estimar_posicao(edital: str, perfil: str, localidade: str, nota: float) -> dict:
    """Se a nota habilita, estima a posição entre os habilitados do perfil/localidade e compara com as vagas.
    Abaixo do mínimo do edital, não estima posição."""
    if erro := _edital_valido(edital):
        return {"erro": erro}
    if nota < 0 or nota > 115:
        return {"erro": "A nota deve estar entre 0 e 115."}
    if nota < NOTA_MINIMA:
        return {"edital": edital, "nota_informada": nota, "habilitado": False,
                "mensagem": f"Nota {nota:g} abaixo do mínimo de {NOTA_MINIMA:g} pontos: abaixo do limiar de habilitação "
                            "na prova objetiva, então não há posição a estimar."}

    grupos = {c: n for c, n in carregar_notas(edital).items()
              if _chave_perfil(perfil) in _chave_perfil(c[0]) and _sem_acento(localidade) in _sem_acento(c[1])}
    if not grupos:
        return {"erro": "Nenhum perfil/localidade encontrado nos resultados deste concurso.", "edital": edital}
    if len(grupos) > 1:
        return {"erro": "Perfil e localidade correspondem a mais de um grupo; seja mais específico.",
                "opcoes": [f"{p} - {l}" for p, l in sorted(grupos)][:15]}
    (nome_perfil, nome_local), notas = next(iter(grupos.items()))

    acima = sum(n > nota for n in notas)
    empatados = sum(n == nota for n in notas)
    resultado = {
        "edital": edital, "perfil": nome_perfil, "localidade": nome_local, "nota_informada": nota,
        "habilitado": True, "fonte": FONTE_RESULTADO[edital],
        "habilitados_no_grupo": len(notas),
        "posicao_estimada": acima + 1,
        "empatados_com_voce": empatados,
        "melhores_que_voce_percentual": round(100 * acima / len(notas), 1),
        "nota_maxima": notas[0], "nota_mediana": statistics.median(notas), "nota_minima": notas[-1],
    }
    demanda = next((r for r in carregar_demanda(edital)
                    if _chave_perfil(r["perfil"]) == _chave_perfil(nome_perfil)
                    and _sem_acento(r["localidade"]) == _sem_acento(nome_local)), None)
    if demanda:
        vagas = demanda["vagas"]
        resultado["vagas_total"] = vagas
        if len(notas) >= vagas:
            resultado["nota_na_ultima_vaga"] = notas[vagas - 1]
        resultado["situacao_frente_as_vagas"] = (
            "dentro das vagas" if acima + empatados < vagas
            else "no limite: depende do desempate" if acima < vagas
            else "fora das vagas")
    resultado["observacao"] = ("Posição entre os habilitados na prova objetiva, sem separar cotas. " + OBSERVACAO_VAGAS +
                               " Reprovados não aparecem nas listas; este resultado não substitui a classificação final.")
    return resultado


# - salvar plano
def salvar_plano(nome_arquivo: str, conteudo: str) -> dict:
    """Grava o plano de estudos em Markdown na pasta de planos, aceitando só nomes simples de arquivo."""
    nome = nome_arquivo.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,60}(\.md)?", nome):
        return {"erro": "Nome inválido. Use só letras, números, '-' e '_' (sem pastas), por exemplo plano-dev-natal."}
    if not nome.endswith(".md"):
        nome += ".md"
    if not conteudo.strip() or len(conteudo) > 20_000:
        return {"erro": "O conteúdo deve ter entre 1 e 20.000 caracteres."}
    PLANOS_DIR.mkdir(parents=True, exist_ok=True)
    destino = (PLANOS_DIR / nome).resolve()
    if destino.parent != PLANOS_DIR.resolve():  
        return {"erro": "Caminho fora da pasta de planos."}
    destino.write_text(conteudo, encoding="utf-8")
    return {"salvo": True, "arquivo": f"planos/{nome}", "caracteres": len(conteudo)}