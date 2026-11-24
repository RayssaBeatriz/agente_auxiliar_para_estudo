"""RAG sobre os editais e outros documentos do concurso da Dataprev."""
import math
import os
import re
import unicodedata
from collections import Counter
from functools import cache
from pathlib import Path
from typing import Literal

from langchain_chroma import Chroma
from langchain_community.document_loaders import PDFPlumberLoader
from langchain_core.documents import Document
from langchain_core.tools import tool
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

DATA_DIR = Path("data")
INDEX_DIR = "chroma_dataprev"
SEARCH_TOOL = "search_dataprev"
K = 5
STOPWORDS = {"de", "da", "do", "das", "dos", "a", "o", "as", "os", "e", "em", "na", "no", "nas", "nos", "para", "por", "com", "que", "um", "uma", "qual", "quais", "ou", "se", "ao", "aos"}

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


def tokenize(text: str) -> list[str]:
    """Palavras sem acento, cortadas nas cinco primeiras letras (aprovado e aprovação se igualam) e números como 57,5 inteiros."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return [w[:5] if w[0].isalpha() else w for w in re.findall(r"\d+[.,]\d+|\w+", text) if w not in STOPWORDS]


def bm25(query: str, docs: list[Document], k1: float = 1.5, b: float = 0.75) -> list[Document]:
    """Ordena os trechos pela coincidência de palavras com a consulta (BM25), o que acha números e termos exatos da regra."""
    counts = [Counter(tokenize(doc.page_content)) for doc in docs]
    sizes = [sum(c.values()) for c in counts]
    average = sum(sizes) / len(sizes)
    frequency = Counter(word for c in counts for word in c)
    terms = set(tokenize(query))

    def score(c: Counter, size: int) -> float:
        return sum(
            math.log(1 + (len(docs) - frequency[w] + 0.5) / (frequency[w] + 0.5)) * c[w] * (k1 + 1) / (c[w] + k1 * (1 - b + b * size / average))
            for w in terms if c[w]
        )

    order = sorted(range(len(docs)), key=lambda i: -score(counts[i], sizes[i]))
    return [docs[i] for i in order]


@cache
def get_corpus(ano: str) -> list[Document]:
    """Todos os trechos de um concurso, lidos do índice, para a busca por palavras."""
    data = get_vector_store().get(where={"edital": ano})
    return [Document(page_content=text, metadata=meta) for text, meta in zip(data["documents"], data["metadatas"])]


def fuse(*rankings: list[Document], k: int) -> list[Document]:
    """Junta as listas por posição (reciprocal rank fusion): trechos bem colocados em mais de uma lista sobem."""
    score, docs = {}, {}
    for ranking in rankings:
        for position, doc in enumerate(ranking):
            score[doc.page_content] = score.get(doc.page_content, 0) + 1 / (60 + position + 1)
            docs[doc.page_content] = doc
    return [docs[text] for text in sorted(score, key=score.get, reverse=True)[:k]]


def buscar(query: str, edital: str = "todos", k: int = K) -> list:
    """Devolve os k trechos mais próximos de cada concurso pedido, juntando a busca por significado e a por palavras."""
    anos = ["2024", "2026"] if edital == "todos" else [edital]
    store = get_vector_store()
    return [
        doc for ano in anos
        for doc in fuse(store.similarity_search(query, k=k, filter={"edital": ano}), bm25(query, get_corpus(ano))[:k], k=k)
    ]


@tool
def search_dataprev(query: str, edital: Literal["2024", "2026", "todos"] = "todos") -> str:
    """Busca trechos dos editais e documentos do concurso da Dataprev. Use edital '2024' ou '2026' quando a pergunta citar um deles, e 'todos' para comparar ou quando não citar."""
    return "\n\n".join(doc.page_content for doc in buscar(query, edital))


if __name__ == "__main__":
    print("trechos indexados:", len(get_vector_store().get()["ids"]))