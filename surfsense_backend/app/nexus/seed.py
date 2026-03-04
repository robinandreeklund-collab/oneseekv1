"""NEXUS Seed Data — populate base tables with realistic infrastructure data.

Endpoint: POST /api/v1/nexus/seed
Inserts zone configs, routing events, space snapshots, loop runs,
pipeline metrics, dark matter queries, and calibration params.

Uses REAL tool IDs from the platform_bridge — not made-up tool names.
"""

from __future__ import annotations

import logging
import random
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.nexus.models import (
    NexusAutoLoopRun,
    NexusCalibrationParam,
    NexusDarkMatterQuery,
    NexusPipelineMetric,
    NexusRoutingEvent,
    NexusSpaceSnapshot,
    NexusZoneConfig,
)

logger = logging.getLogger(__name__)


def _get_tool_catalog() -> list[dict]:
    """Build tool catalog from the real platform tool registry."""
    try:
        from app.nexus.platform_bridge import get_platform_tools

        platform_tools = get_platform_tools()
        return [
            {
                "tool_id": t.tool_id,
                "namespace": "/".join(t.namespace),
                "zone": t.zone,
                "category": t.category,
            }
            for t in platform_tools
        ]
    except Exception:
        logger.warning("Could not load platform tools for seed — using fallback")
        return [
            {
                "tool_id": "search_knowledge_base",
                "namespace": "tools/knowledge/kb",
                "zone": "kunskap",
                "category": "builtin",
            },
            {
                "tool_id": "search_tavily",
                "namespace": "tools/knowledge/web",
                "zone": "kunskap",
                "category": "builtin",
            },
            {
                "tool_id": "smhi_vaderprognoser_metfcst",
                "namespace": "tools/weather/smhi",
                "zone": "kunskap",
                "category": "smhi",
            },
        ]


def _get_sample_queries(catalog: list[dict]) -> list[tuple]:
    """Build sample queries using real tool IDs from the catalog."""
    by_cat: dict[str, list[dict]] = {}
    for t in catalog:
        by_cat.setdefault(t["category"], []).append(t)

    queries: list[tuple] = []

    # SMHI weather queries
    smhi_tools = by_cat.get("smhi", [])
    if smhi_tools:
        metfcst = next(
            (t for t in smhi_tools if "metfcst" in t["tool_id"]), smhi_tools[0]
        )
        metobs = next(
            (t for t in smhi_tools if "metobs" in t["tool_id"]), smhi_tools[0]
        )
        brandrisk = next(
            (t for t in smhi_tools if "brandrisk" in t["tool_id"]), smhi_tools[0]
        )
        queries.extend(
            [
                (
                    "Vad blir vädret i Stockholm imorgon?",
                    metfcst["tool_id"],
                    metfcst["zone"],
                    0,
                    0.96,
                ),
                (
                    "Regnade det i Göteborg igår?",
                    metobs["tool_id"],
                    metobs["zone"],
                    1,
                    0.85,
                ),
                (
                    "Hur stor är brandrisken i Kalmar?",
                    brandrisk["tool_id"],
                    brandrisk["zone"],
                    1,
                    0.88,
                ),
            ]
        )

    # SCB queries
    scb_tools = by_cat.get("scb", [])
    if scb_tools:
        bef = next(
            (t for t in scb_tools if t["tool_id"].split("_")[-1] == "befolkning"),
            scb_tools[0],
        )
        arb = next(
            (t for t in scb_tools if "arbetsmarknad" in t["tool_id"]), scb_tools[0]
        )
        queries.extend(
            [
                ("Hur många bor i Sverige?", bef["tool_id"], bef["zone"], 0, 0.93),
                (
                    "Arbetslöshetsstatistik per kommun",
                    arb["tool_id"],
                    arb["zone"],
                    1,
                    0.84,
                ),
            ]
        )

    # Kolada queries
    kolada_tools = by_cat.get("kolada", [])
    if kolada_tools:
        aldr = next(
            (t for t in kolada_tools if "aldreomsorg" in t["tool_id"]), kolada_tools[0]
        )
        queries.append(
            (
                "Kolada nyckeltal för äldreomsorgen i Malmö",
                aldr["tool_id"],
                aldr["zone"],
                1,
                0.88,
            )
        )

    # Riksdagen queries
    riks_tools = by_cat.get("riksdagen", [])
    if riks_tools:
        dok = next(
            (t for t in riks_tools if t["tool_id"] == "riksdag_dokument"), riks_tools[0]
        )
        queries.append(
            (
                "Visa senaste riksdagsbeslut om klimat",
                dok["tool_id"],
                dok["zone"],
                1,
                0.85,
            )
        )

    # Trafikverket queries
    trafik_tools = by_cat.get("trafikverket", [])
    if trafik_tools:
        storn = next(
            (t for t in trafik_tools if "storningar" in t["tool_id"]), trafik_tools[0]
        )
        queries.append(
            (
                "Finns det trafikstörningar på E4?",
                storn["tool_id"],
                storn["zone"],
                0,
                0.92,
            )
        )

    # Bolagsverket queries
    bolag_tools = by_cat.get("bolagsverket", [])
    if bolag_tools:
        info = next(
            (t for t in bolag_tools if "info_basic" in t["tool_id"]), bolag_tools[0]
        )
        queries.append(
            (
                "Vad gör företaget med orgnr 5566778899?",
                info["tool_id"],
                info["zone"],
                0,
                0.91,
            )
        )

    # Marketplace queries
    market_tools = by_cat.get("marketplace", [])
    if market_tools:
        unified = next(
            (t for t in market_tools if "unified" in t["tool_id"]), market_tools[0]
        )
        queries.append(
            (
                "Köpa begagnad cykel i Uppsala",
                unified["tool_id"],
                unified["zone"],
                0,
                0.92,
            )
        )

    # Builtin knowledge queries
    builtin_tools = by_cat.get("builtin", [])
    if builtin_tools:
        kb = next(
            (t for t in builtin_tools if "knowledge_base" in t["tool_id"]),
            builtin_tools[0],
        )
        tavily = next(
            (t for t in builtin_tools if "tavily" in t["tool_id"]), builtin_tools[0]
        )
        podcast = next((t for t in builtin_tools if "podcast" in t["tool_id"]), None)
        sandbox = next(
            (t for t in builtin_tools if "sandbox_execute" in t["tool_id"]), None
        )
        queries.extend(
            [
                ("Hitta dokumentet om Q3 budget", kb["tool_id"], kb["zone"], 1, 0.79),
                (
                    "Sök efter python tutorials",
                    tavily["tool_id"],
                    tavily["zone"],
                    0,
                    0.94,
                ),
            ]
        )
        if podcast:
            queries.append(
                ("Skapa en podcast om AI", podcast["tool_id"], podcast["zone"], 1, 0.86)
            )
        if sandbox:
            queries.append(
                ("Kör min Python-kod", sandbox["tool_id"], sandbox["zone"], 0, 0.97)
            )

    # External model queries
    ext_tools = by_cat.get("external_model", [])
    if ext_tools:
        gpt = next((t for t in ext_tools if "gpt" in t["tool_id"]), ext_tools[0])
        queries.append(
            ("Jämför GPT-4 och Claude", gpt["tool_id"], gpt["zone"], 0, 0.93)
        )

    # OOD / band 4 queries (no tool match)
    queries.extend(
        [
            ("Vad är meningen med livet?", None, None, 4, 0.15),
            ("Boka tandläkartid", None, None, 4, 0.22),
            ("Skriv en haiku om programmering", None, None, 3, 0.45),
        ]
    )

    return queries


# OOD queries for dark matter
OOD_QUERIES = [
    ("Boka flygbiljett till Mallorca", -6.2),
    ("Beställ pizza online", -7.1),
    ("Vad kostar en Tesla Model 3?", -5.8),
    ("Hitta veterinär nära mig", -6.5),
    ("Spela Wordle", -8.0),
    ("Översätt till kinesiska", -5.5),
    ("Ring min mamma", -9.1),
    ("Sätt på musiken", -7.3),
    ("Boka hotell i Paris", -6.0),
    ("Vad är mitt lösenord?", -8.5),
    ("Skicka ett mejl till chefen", -5.9),
    ("Vad är klockan i Tokyo?", -5.3),
]


async def seed_nexus_data(session: AsyncSession) -> dict:
    """Insert infrastructure data into NEXUS tables.

    Uses REAL tool IDs from the platform bridge.
    """
    now = datetime.now(tz=UTC)
    counts: dict[str, int] = {}

    # 1. Zone configs (aligned with real platform intents)
    # Remove old/stale zone configs that don't match current ZONE_PREFIXES

    from app.nexus.config import ZONE_PREFIXES

    old_zones = await session.execute(select(NexusZoneConfig))
    for old_zone in old_zones.scalars().all():
        if old_zone.zone not in ZONE_PREFIXES:
            await session.delete(old_zone)

    for zone, prefix in ZONE_PREFIXES.items():
        zc = NexusZoneConfig(
            zone=zone,
            prefix_token=prefix,
            silhouette_score=round(random.uniform(0.55, 0.82), 3),
            inter_zone_min_distance=round(random.uniform(0.35, 0.65), 3),
            ood_energy_threshold=-5.0,
            band0_rate=round(random.uniform(0.40, 0.70), 3),
            ece_score=round(random.uniform(0.02, 0.08), 4),
            last_reindexed=now - timedelta(hours=random.randint(1, 48)),
        )
        await session.merge(zc)
    counts["zone_configs"] = len(ZONE_PREFIXES)

    # 2. Load real tool catalog
    tool_catalog = _get_tool_catalog()
    sample_queries = _get_sample_queries(tool_catalog)

    # 3. Routing events (using real tool IDs)
    n_events = 40
    for i in range(n_events):
        q_text, tool, zone, band, conf = sample_queries[i % len(sample_queries)]
        conf_var = max(0.0, min(1.0, conf + random.uniform(-0.05, 0.05)))
        event = NexusRoutingEvent(
            query_text=q_text,
            query_hash=f"hash_{i:04d}",
            band=band,
            resolved_zone=zone,
            selected_tool=tool,
            raw_reranker_score=conf_var + random.uniform(-0.02, 0.02),
            calibrated_confidence=conf_var,
            is_multi_intent=random.random() < 0.1,
            sub_query_count=1 if random.random() > 0.15 else 2,
            schema_verified=band <= 1,
            is_ood=band == 4,
            routed_at=now - timedelta(minutes=random.randint(1, 2880)),
        )
        session.add(event)
    counts["routing_events"] = n_events

    # 4. Space snapshots — ALL real tools (not just a sample)
    zone_centers = {
        "kunskap": (-1.0, 1.5),
        "skapande": (2.0, -1.0),
        "jämförelse": (3.0, 2.0),
        "konversation": (-3.0, -2.0),
    }
    # Exclude external_model tools from space snapshots
    snapshot_tools = [t for t in tool_catalog if t.get("category") != "external_model"]
    for tool in snapshot_tools:
        cx, cy = zone_centers.get(tool["zone"], (0, 0))
        snap = NexusSpaceSnapshot(
            snapshot_at=now - timedelta(hours=1),
            tool_id=tool["tool_id"],
            namespace=tool["namespace"],
            embedding_model="KBLab/sentence-bert-swedish-cased",
            umap_x=cx + random.uniform(-0.8, 0.8),
            umap_y=cy + random.uniform(-0.8, 0.8),
            cluster_label=list(zone_centers.keys()).index(tool["zone"])
            if tool["zone"] in zone_centers
            else 0,
            silhouette_score=round(random.uniform(0.45, 0.85), 3),
            nearest_neighbor_tool=random.choice(
                [
                    t["tool_id"]
                    for t in snapshot_tools
                    if t["tool_id"] != tool["tool_id"]
                ]
            )
            if len(snapshot_tools) > 1
            else tool["tool_id"],
            nearest_neighbor_distance=round(random.uniform(0.15, 0.60), 3),
        )
        session.add(snap)
    counts["space_snapshots"] = len(snapshot_tools)

    # 5. Auto-loop runs
    for i in range(3):
        run = NexusAutoLoopRun(
            loop_number=i + 1,
            started_at=now - timedelta(hours=24 * (3 - i)),
            completed_at=now - timedelta(hours=24 * (3 - i) - 2),
            total_tests=random.randint(40, 80),
            failures=random.randint(3, 12),
            metadata_proposals={
                "proposals": [
                    {"tool_id": snapshot_tools[0]["tool_id"], "field": "description"}
                ]
            }
            if snapshot_tools
            else {},
            approved_proposals=random.randint(0, 3),
            embedding_delta=round(random.uniform(0.01, 0.05), 4),
            status=random.choice(["approved", "deployed", "review"]),
        )
        session.add(run)
    counts["auto_loop_runs"] = 3

    # 6. Pipeline metrics
    run_id = uuid.uuid4()
    stages = [
        (1, "intent", 0.88, 0.95, 0.91, 0.89, None, None),
        (2, "route", 0.82, 0.93, 0.87, 0.85, None, None),
        (3, "bigtool", 0.78, 0.90, 0.83, 0.81, 0.86, None),
        (4, "rerank", 0.85, 0.94, 0.89, 0.87, 0.90, 0.07),
        (5, "e2e", 0.85, 0.95, 0.90, 0.88, None, None),
    ]
    for stage, name, p1, p5, mrr, ndcg, hn_p, delta in stages:
        metric = NexusPipelineMetric(
            run_id=run_id,
            stage=stage,
            stage_name=name,
            precision_at_1=p1,
            precision_at_5=p5,
            mrr_at_10=mrr,
            ndcg_at_5=ndcg,
            hard_negative_precision=hn_p,
            reranker_delta=delta,
            recorded_at=now - timedelta(hours=2),
        )
        session.add(metric)
    counts["pipeline_metrics"] = len(stages)

    # 7. Calibration params (per real zone/intent)
    for zone in ZONE_PREFIXES:
        cal = NexusCalibrationParam(
            zone=zone,
            calibration_method="platt",
            param_a=round(random.uniform(0.8, 1.2), 4),
            param_b=round(random.uniform(-0.3, 0.1), 4),
            temperature=round(random.uniform(0.9, 1.3), 4),
            ece_score=round(random.uniform(0.02, 0.07), 4),
            fitted_on_samples=random.randint(200, 500),
            fitted_at=now - timedelta(hours=6),
            is_active=True,
        )
        session.add(cal)
    counts["calibration_params"] = len(ZONE_PREFIXES)

    # 8. Dark matter queries
    for q_text, energy in OOD_QUERIES:
        dm = NexusDarkMatterQuery(
            query_text=q_text,
            energy_score=energy,
            knn_distance=round(abs(energy) * 0.4 + random.uniform(0, 1), 3),
            reviewed=False,
            created_at=now - timedelta(minutes=random.randint(1, 4320)),
        )
        session.add(dm)
    counts["dark_matter_queries"] = len(OOD_QUERIES)

    await session.commit()

    total = sum(counts.values())
    logger.info(
        "NEXUS seed complete: %d total rows across %d tables", total, len(counts)
    )

    # Include model info and tool registry summary in response
    from app.nexus.embeddings import get_embedding_info, get_reranker_info
    from app.nexus.llm import get_nexus_llm_info

    return {
        "status": "seeded",
        "total_rows": total,
        "details": counts,
        "platform_tools_loaded": len(tool_catalog),
        "models": {
            "llm": get_nexus_llm_info(),
            "embedding": get_embedding_info(),
            "reranker": get_reranker_info(),
        },
        "next_steps": [
            "GET /api/v1/nexus/tools — se alla verktyg som NEXUS känner till",
            "POST /api/v1/nexus/forge/generate — generera testfall (valfritt: category=smhi)",
            "POST /api/v1/nexus/routing/route — kör routing-pipeline",
        ],
    }
