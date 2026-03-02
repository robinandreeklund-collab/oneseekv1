#!/usr/bin/env python
"""
Re-embed all vector embeddings in the database after an embedding model change.

This script reads every row that has an ``embedding`` column, computes a fresh
embedding with the currently configured model, and writes it back.  It is
designed to be run **once** after changing ``EMBEDDING_MODEL`` in ``.env`` and
running the corresponding Alembic migration (106_resize_embedding_columns).

Usage
-----
1.  Stop the backend server.
2.  Make sure ``.env`` has the new ``EMBEDDING_MODEL`` value.
3.  Run the Alembic migration:
        alembic upgrade head
4.  Run this script:
        python scripts/reembed_all.py
5.  Start the backend server again.

Options
-------
    --batch-size N    Number of rows to process per commit (default 100).
    --dry-run         Print counts without writing anything.
    --table TABLE     Only re-embed a specific table.
                      Valid: documents, chunks, user_memories,
                             surfsense_docs_documents, surfsense_docs_chunks

Examples
--------
    # Full re-embed
    python scripts/reembed_all.py

    # Re-embed only chunks with larger batches
    python scripts/reembed_all.py --table chunks --batch-size 500

    # Preview what would be done
    python scripts/reembed_all.py --dry-run
"""

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

# Ensure app modules are importable when running from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import config
from app.db import (
    Chunk,
    Document,
    SurfsenseDocsChunk,
    SurfsenseDocsDocument,
    UserMemory,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger("reembed_all")

# Map of table name → (ORM model, text column name)
TABLE_REGISTRY: dict[str, tuple[type, str]] = {
    "documents": (Document, "content"),
    "chunks": (Chunk, "content"),
    "user_memories": (UserMemory, "memory_text"),
    "surfsense_docs_documents": (SurfsenseDocsDocument, "content"),
    "surfsense_docs_chunks": (SurfsenseDocsChunk, "content"),
}


async def count_rows(session, model) -> int:
    result = await session.execute(select(func.count(model.id)))
    return result.scalar_one()


async def reembed_table(
    session,
    table_name: str,
    model,
    text_column: str,
    embed_fn,
    batch_size: int,
    dry_run: bool,
) -> tuple[int, int]:
    """Re-embed all rows in a single table.

    Returns (processed, skipped) counts.
    """
    total = await count_rows(session, model)
    if total == 0:
        logger.info("  %s: no rows — skipping", table_name)
        return 0, 0

    if dry_run:
        logger.info("  %s: %d rows would be re-embedded (dry-run)", table_name, total)
        return total, 0

    logger.info("  %s: %d rows to re-embed", table_name, total)

    processed = 0
    skipped = 0
    offset = 0

    while True:
        result = await session.execute(
            select(model).order_by(model.id).offset(offset).limit(batch_size)
        )
        rows = result.scalars().all()
        if not rows:
            break

        for row in rows:
            text = getattr(row, text_column, None)
            if not text or not str(text).strip():
                skipped += 1
                continue
            row.embedding = embed_fn(str(text).strip())
            processed += 1

        await session.commit()
        offset += batch_size
        logger.info(
            "  %s: %d / %d processed (%d skipped)",
            table_name,
            processed,
            total,
            skipped,
        )

    return processed, skipped


async def main(args: argparse.Namespace) -> None:
    embed_fn = config.embedding_model_instance.embed
    dim = getattr(config.embedding_model_instance, "dimension", "?")

    logger.info("=" * 60)
    logger.info("  Embedding model : %s", config.EMBEDDING_MODEL)
    logger.info("  Dimension       : %s", dim)
    logger.info("  Batch size      : %d", args.batch_size)
    logger.info("  Dry run         : %s", args.dry_run)
    logger.info("=" * 60)

    # Quick smoke-test: embed a single string to make sure the model loads.
    try:
        test_vec = embed_fn("test")
        logger.info("  Smoke test OK — produced %d-dim vector", len(test_vec))
    except Exception as exc:
        logger.error("  Smoke test FAILED: %s", exc)
        logger.error("  Is EMBEDDING_MODEL set correctly in .env?")
        sys.exit(1)

    engine = create_async_engine(config.DATABASE_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    tables_to_process = (
        {args.table: TABLE_REGISTRY[args.table]}
        if args.table
        else TABLE_REGISTRY
    )

    start = time.monotonic()
    totals = {"processed": 0, "skipped": 0}

    async with session_factory() as session:
        for table_name, (model, text_col) in tables_to_process.items():
            processed, skipped = await reembed_table(
                session,
                table_name,
                model,
                text_col,
                embed_fn,
                args.batch_size,
                args.dry_run,
            )
            totals["processed"] += processed
            totals["skipped"] += skipped

    await engine.dispose()
    elapsed = time.monotonic() - start

    logger.info("-" * 60)
    logger.info(
        "Done in %.1fs — %d re-embedded, %d skipped",
        elapsed,
        totals["processed"],
        totals["skipped"],
    )
    if not args.dry_run and totals["processed"] > 0:
        logger.info("All embeddings updated to %s-dim vectors.", dim)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Re-embed all vector columns after an embedding model change.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Rows per commit batch (default: 100)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print counts without writing",
    )
    parser.add_argument(
        "--table",
        choices=list(TABLE_REGISTRY.keys()),
        default=None,
        help="Only re-embed a specific table",
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
