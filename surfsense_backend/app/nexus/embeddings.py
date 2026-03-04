"""NEXUS Embeddings & Reranker — connects to the app's real models.

Uses the configured embedding model (KBLab/sentence-bert-swedish-cased)
and reranker (flashrank ms-marco-MultiBERT-L-12) from the global app config.
"""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)

# Cached instances
_embedding_model = None
_reranker_service = None


def _get_embedding_model():
    """Get the configured embedding model instance from app config."""
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model

    try:
        from app.config import config

        if (
            hasattr(config, "embedding_model_instance")
            and config.embedding_model_instance
        ):
            _embedding_model = config.embedding_model_instance
            logger.info(
                "NEXUS: Using embedding model: %s",
                getattr(config, "EMBEDDING_MODEL", "unknown"),
            )
            return _embedding_model
    except Exception as e:
        logger.warning("NEXUS: Could not load embedding model from config: %s", e)

    return None


def _get_reranker_service():
    """Get the configured reranker service from app config."""
    global _reranker_service
    if _reranker_service is not None:
        return _reranker_service

    try:
        from app.services.reranker_service import RerankerService

        svc = RerankerService.get_reranker_instance()
        if svc:
            _reranker_service = svc
            logger.info("NEXUS: Reranker service loaded")
            return _reranker_service
    except Exception as e:
        logger.warning("NEXUS: Could not load reranker service: %s", e)

    return None


def nexus_embed(text: str) -> list[float] | None:
    """Embed a text string using the configured embedding model.

    Args:
        text: Text to embed.

    Returns:
        Embedding vector as list of floats, or None if model not available.
    """
    model = _get_embedding_model()
    if model is None:
        return None

    try:
        embedding = model.embed(text)
        if isinstance(embedding, np.ndarray):
            return embedding.tolist()
        return list(embedding)
    except Exception as e:
        logger.error("NEXUS: Embedding failed: %s", e)
        return None


def nexus_embed_score(query: str, document: str) -> float | None:
    """Compute cosine similarity between query and document embeddings.

    Returns a similarity score in [0, 1], or None if embedding model
    is not available.
    """
    q_emb = nexus_embed(query)
    d_emb = nexus_embed(document)
    if q_emb is None or d_emb is None:
        return None

    q = np.array(q_emb)
    d = np.array(d_emb)
    norm_q = np.linalg.norm(q)
    norm_d = np.linalg.norm(d)
    if norm_q == 0 or norm_d == 0:
        return 0.0
    return float(np.dot(q, d) / (norm_q * norm_d))


def nexus_embed_batch(texts: list[str]) -> list[list[float]] | None:
    """Embed multiple texts using the configured embedding model.

    Args:
        texts: List of texts to embed.

    Returns:
        List of embedding vectors, or None if model not available.
    """
    model = _get_embedding_model()
    if model is None:
        return None

    try:
        results = []
        for text in texts:
            emb = model.embed(text)
            if isinstance(emb, np.ndarray):
                results.append(emb.tolist())
            else:
                results.append(list(emb))
        return results
    except Exception as e:
        logger.error("NEXUS: Batch embedding failed: %s", e)
        return None


def nexus_rerank(
    query: str,
    documents: list[dict],
) -> list[dict]:
    """Rerank documents using the configured reranker.

    Args:
        query: The query text.
        documents: List of dicts with at least 'document_id' and 'content' keys.

    Returns:
        Reranked documents with updated scores, or original docs if reranker unavailable.
    """
    svc = _get_reranker_service()
    if svc is None:
        return documents

    try:
        return svc.rerank_documents(query, documents)
    except Exception as e:
        logger.warning("NEXUS: Reranking failed, returning original order: %s", e)
        return documents


def get_embedding_info() -> dict:
    """Return info about the configured embedding model."""
    model = _get_embedding_model()
    if model is None:
        return {"status": "not_available", "model": None}

    try:
        from app.config import config

        return {
            "status": "available",
            "model": getattr(config, "EMBEDDING_MODEL", "unknown"),
            "dimension": getattr(model, "dimension", None),
        }
    except Exception:
        return {"status": "available", "model": "unknown"}


def get_reranker_info() -> dict:
    """Return info about the configured reranker."""
    svc = _get_reranker_service()
    if svc is None:
        return {"status": "not_available"}

    try:
        from app.config import config

        return {
            "status": "available",
            "model": getattr(config, "RERANKERS_MODEL_NAME", "unknown"),
            "type": getattr(config, "RERANKERS_MODEL_TYPE", "unknown"),
        }
    except Exception:
        return {"status": "available"}
