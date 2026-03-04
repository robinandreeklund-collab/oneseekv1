"""NEXUS Celery tasks — background jobs for forge and auto-loop.

These tasks run asynchronously via the Celery worker.
They use synchronous DB sessions since Celery workers are sync.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _forge_generate_async(
    tool_ids: list[str] | None = None,
    difficulties: list[str] | None = None,
    questions_per_difficulty: int = 4,
) -> dict:
    """Async implementation of forge generation."""
    from app.db import async_session_factory
    from app.nexus.llm import nexus_llm_call
    from app.nexus.models import NexusSyntheticCase
    from app.nexus.platform_bridge import get_platform_tools

    # Build tool metadata from REAL platform tool registry
    platform_tools = get_platform_tools()
    tools: list[dict] = []
    for pt in platform_tools:
        tools.append(
            {
                "tool_id": pt.tool_id,
                "name": pt.name,
                "description": pt.description,
                "namespace": "/".join(pt.namespace),
                "keywords": pt.keywords,
                "excludes": pt.excludes,
                "geographic_scope": pt.geographic_scope,
            }
        )

    if not tools:
        return {"status": "error", "message": "No tools found in platform registry"}

    from app.nexus.layers.synth_forge import SynthForge

    forge = SynthForge(
        difficulties=difficulties,
        questions_per_difficulty=questions_per_difficulty,
    )

    result = await forge.run(
        tools,
        llm_call=nexus_llm_call,
        tool_ids=tool_ids,
    )

    # Persist to DB
    persisted = 0
    try:
        async with async_session_factory() as session:
            for case in result.cases:
                db_case = NexusSyntheticCase(
                    tool_id=case.tool_id,
                    namespace=case.namespace,
                    question=case.question,
                    difficulty=case.difficulty,
                    expected_tool=case.expected_tool,
                    roundtrip_verified=case.roundtrip_verified,
                    quality_score=case.quality_score,
                    generation_run_id=result.run_id,
                    generation_model=_get_llm_model_name(),
                )
                session.add(db_case)
                persisted += 1
            if persisted > 0:
                await session.commit()
    except Exception as e:
        logger.error("Failed to persist forge results: %s", e)
        return {
            "status": "partial",
            "run_id": str(result.run_id),
            "total_generated": result.total_generated,
            "persisted_to_db": 0,
            "error": str(e),
        }

    return {
        "status": "completed",
        "run_id": str(result.run_id),
        "total_generated": result.total_generated,
        "total_verified": result.total_verified,
        "persisted_to_db": persisted,
        "by_difficulty": result.by_difficulty,
    }


async def _auto_loop_async() -> dict:
    """Async implementation of auto-loop."""
    from sqlalchemy import func, select

    from app.db import async_session_factory
    from app.nexus.models import NexusAutoLoopRun, NexusSyntheticCase
    from app.nexus.service import NexusService

    service = NexusService()
    run_id = uuid.uuid4()

    try:
        async with async_session_factory() as session:
            # Step 1: Count existing runs for loop_number
            run_count = (
                await session.scalar(select(func.count()).select_from(NexusAutoLoopRun))
                or 0
            )
            loop_number = run_count + 1

            # Create the loop run record
            db_run = NexusAutoLoopRun(
                id=run_id,
                loop_number=loop_number,
                started_at=datetime.now(tz=UTC),
                status="running",
            )
            session.add(db_run)
            await session.flush()

            # Step 2: Load synthetic test cases
            result = await session.execute(select(NexusSyntheticCase).limit(200))
            cases = result.scalars().all()

            if not cases:
                db_run.status = "failed"
                db_run.completed_at = datetime.now(tz=UTC)
                await session.commit()
                return {
                    "status": "failed",
                    "run_id": str(run_id),
                    "message": "No synthetic test cases found. Run forge/generate first.",
                }

            # Step 3: Run each case through routing and compare
            total_tests = 0
            failures = 0
            failed_queries: list[dict] = []

            for case in cases:
                total_tests += 1
                try:
                    decision = await service.route_query(case.question, session)
                    got_tool = decision.selected_tool
                    expected = case.expected_tool

                    if expected and got_tool != expected:
                        failures += 1
                        failed_queries.append(
                            {
                                "query": case.question,
                                "expected_tool": expected,
                                "got_tool": got_tool or "(none)",
                            }
                        )
                except Exception as e:
                    failures += 1
                    logger.warning("Loop eval error for '%s': %s", case.question, e)

            # Step 4: Cluster failures
            cluster_data = service.auto_loop.cluster_failures(failed_queries)

            # Step 5: Create proposals
            proposals = service.auto_loop.create_proposals(cluster_data)

            # Step 6: Update run record
            db_run.total_tests = total_tests
            db_run.failures = failures
            db_run.metadata_proposals = {
                "proposals": [
                    {
                        "tool_id": p.tool_id,
                        "field": p.field_name,
                        "reason": p.reason,
                    }
                    for p in proposals
                ]
            }
            db_run.approved_proposals = 0
            db_run.status = "review" if proposals else "approved"
            db_run.completed_at = datetime.now(tz=UTC)

            await session.commit()

            return {
                "status": "completed",
                "run_id": str(run_id),
                "loop_number": loop_number,
                "total_tests": total_tests,
                "failures": failures,
                "proposals": len(proposals),
            }

    except Exception as e:
        logger.error("Auto-loop task failed: %s", e)
        return {
            "status": "failed",
            "run_id": str(run_id),
            "error": str(e),
        }


def _get_llm_model_name() -> str | None:
    """Get the configured LLM model name for tracking."""
    try:
        from app.nexus.llm import get_nexus_llm_info

        info = get_nexus_llm_info()
        return info.get("model")
    except Exception:
        return None


def forge_generate_task(
    tool_ids: list[str] | None = None,
    difficulties: list[str] | None = None,
    questions_per_difficulty: int = 4,
) -> dict:
    """Background task: generate synthetic test cases via Synth Forge.

    Calls the configured LLM to generate test questions, then persists
    results to the nexus_synthetic_cases table.
    """
    logger.info(
        "Forge generation task started: tools=%s, difficulties=%s",
        tool_ids or "all",
        difficulties or "all",
    )
    return _run_async(
        _forge_generate_async(tool_ids, difficulties, questions_per_difficulty)
    )


def auto_loop_task() -> dict:
    """Background task: run the auto-improvement loop.

    Loads synthetic test cases, runs them through routing, clusters
    failures, creates proposals, and stores results for human review.
    """
    logger.info("Auto-loop task started")
    return _run_async(_auto_loop_async())
