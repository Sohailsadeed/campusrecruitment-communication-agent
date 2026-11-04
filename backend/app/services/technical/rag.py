"""RAG pipeline for resume ingestion and semantic retrieval using HuggingFace & ChromaDB."""
import logging
from pathlib import Path
from typing import Optional

import chromadb
from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import settings

logger = logging.getLogger(__name__)

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50,
)

_embeddings: Optional[HuggingFaceEmbeddings] = None


def _get_embeddings() -> HuggingFaceEmbeddings:
    """Load local HuggingFace embedding model (all-MiniLM-L6-v2). Zero API cost, runs locally on CPU."""
    global _embeddings
    if _embeddings is None:
        logger.info("Initializing HuggingFace embedding model: sentence-transformers/all-MiniLM-L6-v2")
        _embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
    return _embeddings


def _get_vector_store(user_id: int | str) -> Chroma:
    """Connect to ChromaDB vector store for candidate resume context."""
    collection_name = f"user_{user_id}"
    try:
        client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
        )
        return Chroma(
            client=client,
            collection_name=collection_name,
            embedding_function=_get_embeddings(),
        )
    except Exception as exc:
        logger.warning("ChromaDB HTTP client failed at %s:%s (%s). Using local persistent directory.", settings.chroma_host, settings.chroma_port, exc)
        local_dir = settings.upload_dir / "chroma_db"
        local_dir.mkdir(parents=True, exist_ok=True)
        return Chroma(
            persist_directory=str(local_dir),
            collection_name=collection_name,
            embedding_function=_get_embeddings(),
        )


async def process_resume(user_id: int | str, resume_path: str) -> None:
    """Parse candidate resume PDF, chunk it, and index into ChromaDB."""
    logger.info("Processing resume for candidate %s at %s", user_id, resume_path)
    resume_docs = PyPDFLoader(resume_path).load()

    for doc in resume_docs:
        doc.metadata["source"] = "resume"
        doc.metadata["user_id"] = str(user_id)

    chunks = text_splitter.split_documents(resume_docs)
    logger.info("Generated %d semantic chunks for candidate %s", len(chunks), user_id)

    # Re-initialize collection cleanly
    vector_store = _get_vector_store(user_id)
    try:
        vector_store.delete_collection()
    except Exception:
        pass

    vector_store = _get_vector_store(user_id)
    vector_store.add_documents(chunks)
    logger.info("Successfully indexed candidate %s resume in ChromaDB", user_id)


async def retrieve_context(user_id: int | str, query: str, k: int = 4) -> str:
    """Retrieve top-k relevant chunks from candidate resume to ground technical questions."""
    try:
        vector_store = _get_vector_store(user_id)
        docs = vector_store.similarity_search(query, k=k)
        if not docs:
            return ""
        return "\n\n".join(doc.page_content for doc in docs)
    except Exception as exc:
        logger.warning("Resume context retrieval failed for user %s: %s", user_id, exc)
        return ""
