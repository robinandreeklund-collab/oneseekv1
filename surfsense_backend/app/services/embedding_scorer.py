"""Embedding-based scoring for intent/agent/tool resolution.

Uses the same KBLab/sentence-bert-swedish-cased model as NEXUS, with
the same in-process cache.  Tool/agent/intent descriptions are static
and get cached after the first query — subsequent queries only embed
the query text itself.

Graceful degradation: returns empty dict when embedding model is
unavailable (lexical scoring continues to work).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _build_document_text(
    *,
    label: str,
    description: str,
    keywords: list[str] | None = None,
) -> str:
    """Build a single text representation of a candidate for embedding."""
    parts: list[str] = []
    if label:
        parts.append(label)
    if description:
        parts.append(description)
    if keywords:
        parts.append(", ".join(keywords[:20]))
    return " — ".join(parts) if parts else ""


def compute_embedding_scores(
    query: str,
    candidates: list[dict[str, Any]],
    *,
    id_key: str = "id",
    label_key: str = "label",
    description_key: str = "description",
    keywords_key: str = "keywords",
) -> dict[str, float]:
    """Score candidates against query using cosine similarity.

    Returns ``{candidate_id: cosine_score}`` for each candidate.
    Returns empty dict if embedding model is unavailable (graceful fallback).

    The embedding model and cache are shared with the NEXUS pipeline so
    tool descriptions only get embedded once across both systems.
    """
    text = str(query or "").strip()
    if not text or not candidates:
        return {}

    try:
        from app.nexus.embeddings import nexus_batch_score
    except Exception:
        return {}

    # Build document texts for each candidate
    doc_ids: list[str] = []
    doc_texts: list[str] = []
    for candidate in candidates:
        cid = str(candidate.get(id_key) or "").strip()
        if not cid:
            continue
        doc_text = _build_document_text(
            label=str(candidate.get(label_key) or "").strip(),
            description=str(candidate.get(description_key) or "").strip(),
            keywords=candidate.get(keywords_key) or [],
        )
        if not doc_text:
            continue
        doc_ids.append(cid)
        doc_texts.append(doc_text)

    if not doc_texts:
        return {}

    scores = nexus_batch_score(text, doc_texts)
    if scores is None:
        return {}

    result: dict[str, float] = {}
    for cid, score in zip(doc_ids, scores, strict=False):
        result[cid] = round(float(score), 6)
    return result
