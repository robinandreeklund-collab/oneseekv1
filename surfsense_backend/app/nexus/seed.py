"""NEXUS Seed Data — populate base tables with realistic infrastructure data.

Endpoint: POST /api/v1/nexus/seed
Inserts zone configs, routing events, space snapshots, loop runs,
pipeline metrics, dark matter queries, and calibration params.

Synthetic test cases are NOT seeded here — use POST /nexus/forge/generate
to generate real test cases via the configured LLM.
"""

from __future__ import annotations

import logging
import random
import uuid
from datetime import UTC, datetime, timedelta

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

# ---------------------------------------------------------------------------
# Tool catalog — realistic Swedish tools
# ---------------------------------------------------------------------------

TOOL_CATALOG = [
    {
        "tool_id": "smhi_weather",
        "namespace": "tools/weather/smhi",
        "zone": "myndigheter",
    },
    {"tool_id": "yr_forecast", "namespace": "tools/weather/yr", "zone": "myndigheter"},
    {
        "tool_id": "scb_statistics",
        "namespace": "tools/statistik/scb",
        "zone": "myndigheter",
    },
    {
        "tool_id": "kolada_kpi",
        "namespace": "tools/statistik/kolada",
        "zone": "myndigheter",
    },
    {
        "tool_id": "riksdag_documents",
        "namespace": "tools/politik/riksdag",
        "zone": "myndigheter",
    },
    {
        "tool_id": "trafiklab_transit",
        "namespace": "tools/transport/trafiklab",
        "zone": "myndigheter",
    },
    {
        "tool_id": "skolverket_grades",
        "namespace": "tools/utbildning/skolverket",
        "zone": "myndigheter",
    },
    {"tool_id": "web_search", "namespace": "tools/knowledge/search", "zone": "kunskap"},
    {
        "tool_id": "document_search",
        "namespace": "tools/knowledge/docs",
        "zone": "kunskap",
    },
    {
        "tool_id": "marketplace_search",
        "namespace": "tools/marketplace/blocket",
        "zone": "kunskap",
    },
    {"tool_id": "code_sandbox", "namespace": "tools/code/sandbox", "zone": "handling"},
    {
        "tool_id": "podcast_generator",
        "namespace": "tools/action/podcast",
        "zone": "handling",
    },
    {
        "tool_id": "image_generator",
        "namespace": "tools/action/image",
        "zone": "handling",
    },
    {
        "tool_id": "compare_models",
        "namespace": "tools/compare/models",
        "zone": "jämförelse",
    },
    {
        "tool_id": "compare_products",
        "namespace": "tools/compare/products",
        "zone": "jämförelse",
    },
]

# Sample queries for routing events
SAMPLE_QUERIES = [
    ("Vad blir vädret i Stockholm imorgon?", "smhi_weather", "myndigheter", 0, 0.96),
    ("Hur många bor i Göteborg?", "scb_statistics", "myndigheter", 0, 0.93),
    (
        "Visa senaste riksdagsbeslut om klimat",
        "riksdag_documents",
        "myndigheter",
        1,
        0.85,
    ),
    ("Hur långt har buss 55 kvar?", "trafiklab_transit", "myndigheter", 1, 0.82),
    ("Betygsresultat i Malmö kommun", "skolverket_grades", "myndigheter", 0, 0.91),
    ("Kolada nyckeltal för äldreomsorgen", "kolada_kpi", "myndigheter", 1, 0.88),
    ("Sök efter python tutorials", "web_search", "kunskap", 0, 0.94),
    ("Hitta dokumentet om Q3 budget", "document_search", "kunskap", 1, 0.79),
    ("Köpa begagnad cykel i Uppsala", "marketplace_search", "kunskap", 0, 0.92),
    ("Kör min Python-kod", "code_sandbox", "handling", 0, 0.97),
    ("Skapa en podcast om AI", "podcast_generator", "handling", 1, 0.86),
    ("Generera en bild av en katt", "image_generator", "handling", 0, 0.95),
    ("Jämför GPT-4 och Claude", "compare_models", "jämförelse", 0, 0.93),
    (
        "Vilken telefon är bäst under 5000 kr?",
        "compare_products",
        "jämförelse",
        2,
        0.68,
    ),
    ("Vad är meningen med livet?", None, None, 4, 0.15),
    ("Boka tandläkartid", None, None, 4, 0.22),
    ("Regnar det i Oslo idag?", "yr_forecast", "myndigheter", 2, 0.62),
    ("Medellöner per kommun", "scb_statistics", "myndigheter", 1, 0.84),
    ("Hur gör jag en PR i GitHub?", "web_search", "kunskap", 2, 0.71),
    ("Skriv en haiku om programmering", None, None, 3, 0.45),
]

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

    Does NOT insert synthetic test cases — those are generated live via
    POST /nexus/forge/generate using the configured LLM.

    Returns summary of what was inserted.
    """
    now = datetime.now(tz=UTC)
    counts: dict[str, int] = {}

    # 1. Zone configs
    from app.nexus.config import ZONE_PREFIXES

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

    # 2. Routing events
    for i in range(40):
        q_text, tool, zone, band, conf = SAMPLE_QUERIES[i % len(SAMPLE_QUERIES)]
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
    counts["routing_events"] = 40

    # 3. Space snapshots (UMAP coordinates per tool)
    zone_centers = {
        "myndigheter": (2.0, 1.0),
        "kunskap": (-2.0, 1.5),
        "handling": (0.0, -2.0),
        "jämförelse": (3.0, -1.0),
    }
    for tool in TOOL_CATALOG:
        cx, cy = zone_centers.get(tool["zone"], (0, 0))
        snap = NexusSpaceSnapshot(
            snapshot_at=now - timedelta(hours=1),
            tool_id=tool["tool_id"],
            namespace=tool["namespace"],
            embedding_model="all-MiniLM-L6-v2",
            umap_x=cx + random.uniform(-0.8, 0.8),
            umap_y=cy + random.uniform(-0.8, 0.8),
            cluster_label=list(zone_centers.keys()).index(tool["zone"]),
            silhouette_score=round(random.uniform(0.45, 0.85), 3),
            nearest_neighbor_tool=random.choice(
                [t["tool_id"] for t in TOOL_CATALOG if t["tool_id"] != tool["tool_id"]]
            ),
            nearest_neighbor_distance=round(random.uniform(0.15, 0.60), 3),
        )
        session.add(snap)
    counts["space_snapshots"] = len(TOOL_CATALOG)

    # 4. Auto-loop runs
    for i in range(3):
        run = NexusAutoLoopRun(
            loop_number=i + 1,
            started_at=now - timedelta(hours=24 * (3 - i)),
            completed_at=now - timedelta(hours=24 * (3 - i) - 2),
            total_tests=random.randint(40, 80),
            failures=random.randint(3, 12),
            metadata_proposals={
                "proposals": [{"tool_id": "smhi_weather", "field": "description"}]
            },
            approved_proposals=random.randint(0, 3),
            embedding_delta=round(random.uniform(0.01, 0.05), 4),
            status=random.choice(["approved", "deployed", "review"]),
        )
        session.add(run)
    counts["auto_loop_runs"] = 3

    # 5. Pipeline metrics
    run_id = uuid.uuid4()
    stages = [
        (1, "intent", 0.88, 0.95, 0.91, 0.89, None, None),
        (2, "route", 0.82, 0.93, 0.87, 0.85, None, None),
        (3, "bigtool", 0.78, 0.90, 0.83, 0.81, 0.86, None),
        (4, "rerank", 0.85, 0.94, 0.89, 0.87, 0.90, 0.07),
        (5, "e2e", 0.85, None, None, None, None, None),
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

    # 6. Calibration params
    for zone in ["kunskap", "myndigheter", "handling", "jämförelse"]:
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
    counts["calibration_params"] = 4

    # 7. Dark matter queries
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

    # Include model info in response
    from app.nexus.embeddings import get_embedding_info, get_reranker_info
    from app.nexus.llm import get_nexus_llm_info

    return {
        "status": "seeded",
        "total_rows": total,
        "details": counts,
        "models": {
            "llm": get_nexus_llm_info(),
            "embedding": get_embedding_info(),
            "reranker": get_reranker_info(),
        },
        "next_steps": [
            "POST /api/v1/nexus/forge/generate — generera testfall via LLM",
            "POST /api/v1/nexus/routing/route — kör routing-pipeline",
        ],
    }
