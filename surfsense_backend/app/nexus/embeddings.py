"""NEXUS Embeddings & Reranker — connects to the app's real models.

Uses the configured embedding model (KBLab/sentence-bert-swedish-cased)
and reranker (flashrank ms-marco-MultiBERT-L-12) from the global app config.

Performance: embeddings are cached in-process so repeated texts (e.g. tool
descriptions across hundreds of test-case evaluations) only hit the GPU once.
Batch helpers use `model.embed_batch()` for efficient GPU utilisation.
"""

from __future__ import annotations

import logging
import threading

import numpy as np

logger = logging.getLogger(__name__)

# Cached instances
_embedding_model = None
_reranker_service = None

# ---------------------------------------------------------------------------
# Embedding cache — text → np.ndarray.  Tool descriptions are identical across
# all queries in a loop run, so caching avoids redundant GPU work.
# Max 50 000 entries ≈ ~200 MB for 768-dim float32 vectors.
# ---------------------------------------------------------------------------
_EMBED_CACHE: dict[str, np.ndarray] = {}
_EMBED_CACHE_MAX = 50_000
_cache_lock = threading.Lock()


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


# ---------------------------------------------------------------------------
# Core embed functions (with caching)
# ---------------------------------------------------------------------------


def _raw_embed(model, text: str) -> np.ndarray:
    """Embed a single text, checking cache first."""
    cached = _EMBED_CACHE.get(text)
    if cached is not None:
        return cached

    emb = model.embed(text)
    if not isinstance(emb, np.ndarray):
        emb = np.array(emb)

    with _cache_lock:
        if len(_EMBED_CACHE) < _EMBED_CACHE_MAX:
            _EMBED_CACHE[text] = emb
    return emb


def _raw_embed_many(model, texts: list[str]) -> list[np.ndarray]:
    """Batch-embed texts, using cache for already-seen texts.

    Only sends uncached texts to the GPU in a single batch call.
    """
    results: list[np.ndarray | None] = [None] * len(texts)
    uncached_indices: list[int] = []
    uncached_texts: list[str] = []

    for i, t in enumerate(texts):
        cached = _EMBED_CACHE.get(t)
        if cached is not None:
            results[i] = cached
        else:
            uncached_indices.append(i)
            uncached_texts.append(t)

    if uncached_texts:
        # Use model.embed_batch for real GPU batching
        raw = model.embed_batch(uncached_texts)
        with _cache_lock:
            for idx, emb in zip(uncached_indices, raw, strict=False):
                if not isinstance(emb, np.ndarray):
                    emb = np.array(emb)
                results[idx] = emb
                if len(_EMBED_CACHE) < _EMBED_CACHE_MAX:
                    _EMBED_CACHE[uncached_texts[uncached_indices.index(idx)]] = emb

    return results  # type: ignore[return-value]


def nexus_embed(text: str) -> list[float] | None:
    """Embed a text string using the configured embedding model.

    Results are cached so repeated calls with the same text are free.
    """
    model = _get_embedding_model()
    if model is None:
        return None

    try:
        emb = _raw_embed(model, text)
        return emb.tolist()
    except Exception as e:
        logger.error("NEXUS: Embedding failed: %s", e)
        return None


def nexus_embed_np(text: str) -> np.ndarray | None:
    """Embed text and return as numpy array (avoids list conversion overhead)."""
    model = _get_embedding_model()
    if model is None:
        return None

    try:
        return _raw_embed(model, text)
    except Exception as e:
        logger.error("NEXUS: Embedding failed: %s", e)
        return None


def nexus_embed_score(query: str, document: str) -> float | None:
    """Compute cosine similarity between query and document embeddings.

    Both embeddings are cached, so scoring the same query against many
    documents only embeds the query once.
    """
    model = _get_embedding_model()
    if model is None:
        return None

    try:
        q = _raw_embed(model, query)
        d = _raw_embed(model, document)
        norm_q = np.linalg.norm(q)
        norm_d = np.linalg.norm(d)
        if norm_q == 0 or norm_d == 0:
            return 0.0
        return float(np.dot(q, d) / (norm_q * norm_d))
    except Exception as e:
        logger.error("NEXUS: Embed score failed: %s", e)
        return None


def nexus_embed_batch(texts: list[str]) -> list[list[float]] | None:
    """Embed multiple texts in a single GPU batch call.

    Uses model.embed_batch() for efficient GPU utilisation instead of
    looping over individual embed() calls.
    """
    model = _get_embedding_model()
    if model is None:
        return None

    try:
        embeddings = _raw_embed_many(model, texts)
        return [emb.tolist() for emb in embeddings]
    except Exception as e:
        logger.error("NEXUS: Batch embedding failed: %s", e)
        return None


def nexus_batch_score(query: str, documents: list[str]) -> list[float] | None:
    """Score one query against many documents efficiently.

    Embeds query once, batch-embeds all documents, then computes
    cosine similarity via matrix multiply — a single vectorized operation.
    """
    model = _get_embedding_model()
    if model is None:
        return None

    try:
        q_emb = _raw_embed(model, query)
        doc_embs = _raw_embed_many(model, documents)

        # Stack into matrix for vectorized cosine similarity
        q = q_emb / (np.linalg.norm(q_emb) or 1.0)
        doc_matrix = np.stack(doc_embs)
        norms = np.linalg.norm(doc_matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        doc_matrix = doc_matrix / norms

        scores = doc_matrix @ q  # shape: (n_docs,)
        return scores.tolist()
    except Exception as e:
        logger.error("NEXUS: Batch score failed: %s", e)
        return None


def nexus_precompute(texts: list[str]) -> int:
    """Pre-embed a list of texts into the cache using GPU batching.

    Call this before a loop evaluation to warm the cache in one efficient
    GPU pass instead of embedding texts one-by-one during scoring.

    Returns the number of newly computed embeddings.
    """
    model = _get_embedding_model()
    if model is None:
        return 0

    # Filter out already-cached texts
    new_texts = [t for t in texts if t not in _EMBED_CACHE]
    if not new_texts:
        return 0

    try:
        embeddings = model.embed_batch(new_texts)
        with _cache_lock:
            for text, emb in zip(new_texts, embeddings, strict=False):
                if not isinstance(emb, np.ndarray):
                    emb = np.array(emb)
                if len(_EMBED_CACHE) < _EMBED_CACHE_MAX:
                    _EMBED_CACHE[text] = emb
        logger.info(
            "NEXUS: Pre-computed %d embeddings (cache size: %d)",
            len(new_texts),
            len(_EMBED_CACHE),
        )
        return len(new_texts)
    except Exception as e:
        logger.error("NEXUS: Precompute failed: %s", e)
        return 0


def nexus_clear_embed_cache() -> int:
    """Clear the embedding cache. Returns number of evicted entries."""
    with _cache_lock:
        n = len(_EMBED_CACHE)
        _EMBED_CACHE.clear()
    return n


def nexus_embed_cache_stats() -> dict:
    """Return embedding cache statistics."""
    return {
        "size": len(_EMBED_CACHE),
        "max_size": _EMBED_CACHE_MAX,
    }


# ---------------------------------------------------------------------------
# Reranker
# ---------------------------------------------------------------------------


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
