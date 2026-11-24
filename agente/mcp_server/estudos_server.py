"""Servidor MCP próprio: ferramentas de apoio ao estudo para os concursos da Dataprev.

Sobe em HTTP (padrão http://127.0.0.1:8765/mcp):  python -m agente.mcp_server.estudos_server
"""
import os
from typing import Literal

from fastmcp import FastMCP

from agente import rag

from . import estudos_core as core

mcp = FastMCP("dataprev-estudos")

Edital = Literal["2024", "2026"]


@mcp.tool()
def simular_nota(
    lingua_portuguesa: int,
    lingua_inglesa: int,
    raciocinio_logico: int,
    atualidades: int,
    legislacao_seguranca: int,
    conhecimentos_especificos: int,
    edital: Edital = "2026",
) -> dict:
    """Calcula a nota da prova objetiva da Dataprev a partir do número de ACERTOS em cada disciplina
    e diz se o candidato seria aprovado (mínimo de 57,5 pontos e nenhuma disciplina zerada).
    Questões gerais valem 1 ponto e Conhecimentos Específicos valem 2,5. Devolve também quantos
    acertos específicos faltam para chegar ao mínimo. Use sempre esta ferramenta em vez de fazer a conta."""
    return core.simular_nota(edital, {
        "lingua_portuguesa": lingua_portuguesa, "lingua_inglesa": lingua_inglesa,
        "raciocinio_logico": raciocinio_logico, "atualidades": atualidades,
        "legislacao_seguranca": legislacao_seguranca, "conhecimentos_especificos": conhecimentos_especificos,
    })


@mcp.tool()
def consultar_concorrencia(edital: Edital, perfil: str = "", localidade: str = "", limite: int = 10) -> dict:
    """Consulta a demanda de candidatos por vaga (vagas, candidatos inscritos e candidatos por vaga)
    nos documentos oficiais da Dataprev. ATENÇÃO: 'vagas' soma vagas imediatas e cadastro de reserva; para as vagas
    imediatas, consulte o item 3.1 do edital com search_dataprev. `perfil` e `localidade` são trechos do nome, como
    'desenvolvimento' e 'natal'; vazios, não filtram. Devolve as linhas ordenadas da menor para a maior concorrência."""
    return core.consultar_concorrencia(edital, perfil, localidade, limite)


@mcp.tool()
def search_dataprev(query: str, edital: Literal["2024", "2026", "todos"] = "todos") -> str:
    """Busca trechos dos editais e documentos do concurso da Dataprev. Use edital '2024' ou '2026' quando a pergunta citar um deles, e 'todos' para comparar ou quando não citar. Para vagas, candidatos ou candidatos por vaga, use consultar_concorrencia."""
    return rag.search_dataprev.invoke({"query": query, "edital": edital})


@mcp.tool()
def estimar_posicao(edital: Literal["2024", "2026", "todos"], perfil: str, localidade: str, nota: float) -> dict:
    """Estima a posição de uma nota (0 a 115) entre os habilitados na prova objetiva de um perfil e localidade,
    usando os resultados reais do concurso, e compara com o total de vagas. Se a nota estiver abaixo de 57,5,
    informa que está abaixo do limiar e não estima posição. Use a nota devolvida por simular_nota, e só chame
    esta ferramenta se aprovado_na_prova_objetiva for verdadeiro. `perfil` e `localidade` são trechos do nome.
    Com edital 'todos', devolve a estimativa dos dois concursos de uma vez."""
    if edital == "todos":
        return {ano: core.estimar_posicao(ano, perfil, localidade, nota) for ano in ("2026", "2024")}
    return core.estimar_posicao(edital, perfil, localidade, nota)


@mcp.tool()
def montar_cronograma_estudo(data_inicio: str, data_prova: str, horas_por_semana: float, edital: Edital = "2026",
                             dificuldades: list[str] | None = None, facilidades: list[str] | None = None) -> dict:
    """Monta um cronograma de estudo entre duas datas (formato AAAA-MM-DD): número de semanas, fases
    (base, revisão, simulados) e horas por disciplina, proporcionais aos pontos da prova do edital de referência.
    `dificuldades` e `facilidades` são listas opcionais de disciplinas (ex.: ["inglês"]); as primeiras ganham mais
    horas e as segundas menos, sem nunca zerar nenhuma. Faz o cálculo de dias, então não calcule datas à mão.
    Devolve erro se a prova não for posterior ao início."""
    return core.montar_cronograma(edital, data_inicio, data_prova, horas_por_semana, dificuldades, facilidades)


@mcp.tool()
def salvar_plano(nome_arquivo: str, conteudo: str) -> dict:
    """Salva o plano de estudos em um arquivo Markdown na pasta de planos. `nome_arquivo` é um nome simples,
    sem pastas, como 'plano-dev-natal'. Só chame depois que o usuário aceitar salvar."""
    return core.salvar_plano(nome_arquivo, conteudo)


def main() -> None:
    mcp.run(transport="http", host=os.getenv("MCP_HOST", "127.0.0.1"), port=int(os.getenv("MCP_PORT", "8765")), show_banner=False)


if __name__ == "__main__":
    main()