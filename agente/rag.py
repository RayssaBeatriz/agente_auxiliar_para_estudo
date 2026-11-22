"""RAG sobre os editais e outros documentos do concurso da Dataprev."""
import os
import re
from functools import cache
from pathlib import Path
from typing import Literal

from langchain_chroma import Chroma
from langchain_community.document_loaders import PDFPlumberLoader
from langchain_core.tools import tool
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

DATA_DIR = Path("data")
INDEX_DIR = "chroma_dataprev"
SEARCH_TOOL = "search_dataprev"
K = 3

# arquivo: (concurso, nome do documento)
DOCS = {
    "edital-retificado-dataprev.pdf": ("2026", "Edital 001/2026 (retificado)"),
    "demanda-de-candidatos-por-vaga_0.pdf": ("2026", "Demanda de candidatos por vaga 2026"),
    "dataprev_edital_0.pdf": ("2024", "Edital nº 1/2024"),
    "cronograma_1_1.pdf": ("2024", "Cronograma previsto 2024"),
    "demanda_de_candidato_por_vaga_2_1.pdf": ("2024", "Demanda de candidatos por vaga 2024"),
}


@cache
def get_embeddings():
    model_name = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    return HuggingFaceEmbeddings(model_name=model_name, encode_kwargs={"normalize_embeddings": True})


def load_chunks() -> list:
    """Carrega os PDFs, corta em trechos e põe a fonte no começo de cada um."""
    pages = []
    for file, (ano, nome) in DOCS.items():
        for page in PDFPlumberLoader(DATA_DIR / file).load():
            page.page_content = re.sub(r"DATAPREV \| CONCURSO PÚBLICO 20\d\d\s*\d*\s*", "", page.page_content)
            page.metadata = {"edital": ano, "documento": nome, "pagina": page.metadata["page"] + 1}
            pages.append(page)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1200,
        chunk_overlap=200,
        separators=[r"\n\d+\.\d+(?:\.\d+)?\s", "\n\n", "\n", " ", ""],
        is_separator_regex=True,
    )
    chunks = splitter.split_documents(pages)
    for chunk in chunks:
        m = chunk.metadata
        chunk.page_content = f"[Concurso {m['edital']} | {m['documento']} | p. {m['pagina']}] {chunk.page_content}"
    return chunks


@cache
def get_vector_store() -> Chroma:
    """Abre o índice em disco e, se estiver vazio, cria a partir dos PDFs."""
    store = Chroma(
        collection_name="dataprev",
        embedding_function=get_embeddings(),
        persist_directory=INDEX_DIR,
        collection_metadata={"hnsw:space": "cosine"},
    )
    if not store.get()["ids"]:
        chunks = load_chunks()
        store.add_documents(chunks, ids=[f"dataprev-{i}" for i in range(len(chunks))])
    return store


def buscar(query: str, edital: str = "todos", k: int = K) -> list:
    """Devolve os k trechos mais próximos de cada concurso pedido."""
    anos = ["2024", "2026"] if edital == "todos" else [edital]
    store = get_vector_store()
    return [doc for ano in anos for doc in store.similarity_search(query, k=k, filter={"edital": ano})]


@tool
def search_dataprev(query: str, edital: Literal["2024", "2026", "todos"] = "todos") -> str:
    """Busca trechos dos editais e documentos do concurso da Dataprev. Use edital '2024' ou '2026' quando a pergunta citar um deles, e 'todos' para comparar ou quando não citar."""
    return "\n\n".join(doc.page_content for doc in buscar(query, edital))


if __name__ == "__main__":
    print("trechos indexados:", len(get_vector_store().get()["ids"]))