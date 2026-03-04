"""NEXUS configuration — constants, zone definitions, thresholds.

Single source of truth for all NEXUS-specific configuration values.
"""

from dataclasses import dataclass
from enum import StrEnum

# ---------------------------------------------------------------------------
# Zone Architecture
# ---------------------------------------------------------------------------


class Zone(StrEnum):
    """The four embedding zones that structure the vector space."""

    KUNSKAP = "kunskap"
    MYNDIGHETER = "myndigheter"
    HANDLING = "handling"
    JAMFORELSE = "jämförelse"


ZONE_PREFIXES: dict[str, str] = {
    Zone.KUNSKAP: "[KUNSK] ",
    Zone.MYNDIGHETER: "[MYNDG] ",
    Zone.HANDLING: "[HANDL] ",
    Zone.JAMFORELSE: "[JAMFR] ",
}

# Namespace prefix → zone mapping
NAMESPACE_ZONE_MAP: dict[str, Zone] = {
    "tools/knowledge": Zone.KUNSKAP,
    "tools/weather": Zone.MYNDIGHETER,
    "tools/politik": Zone.MYNDIGHETER,
    "tools/statistik": Zone.MYNDIGHETER,
    "tools/utbildning": Zone.MYNDIGHETER,
    "tools/transport": Zone.MYNDIGHETER,
    "tools/action": Zone.HANDLING,
    "tools/code": Zone.HANDLING,
    "tools/marketplace": Zone.KUNSKAP,
    "tools/compare": Zone.JAMFORELSE,
}


# ---------------------------------------------------------------------------
# Confidence Band Cascade
# ---------------------------------------------------------------------------


class Band(StrEnum):
    """Confidence bands — determines routing behavior."""

    BAND_0 = "band_0"  # Direct route, no LLM
    BAND_1 = "band_1"  # Namespace verify, minimal LLM
    BAND_2 = "band_2"  # Top-3 candidates, LLM chooses
    BAND_3 = "band_3"  # Decompose / reformulate
    BAND_4 = "band_4"  # OOD detection → fallback


@dataclass(frozen=True)
class BandThresholds:
    """Thresholds for confidence band classification."""

    band_0_min_score: float = 0.95
    band_0_min_margin: float = 0.20
    band_1_min_score: float = 0.80
    band_1_min_margin: float = 0.10
    band_2_min_score: float = 0.60
    band_3_min_score: float = 0.40
    # Below band_3_min_score → Band 4 (OOD)


BAND_THRESHOLDS = BandThresholds()


# ---------------------------------------------------------------------------
# OOD Detection
# ---------------------------------------------------------------------------

OOD_ENERGY_THRESHOLD: float = -5.0
OOD_KNN_K: int = 5
OOD_KNN_THRESHOLD: float = 2.5
OOD_ENERGY_BORDERLINE_FACTOR: float = 0.8


# ---------------------------------------------------------------------------
# QUL — Query Understanding Layer
# ---------------------------------------------------------------------------

MULTI_INTENT_MARGIN_THRESHOLD: float = 0.15
SPACY_MODEL: str = "sv_core_news_lg"
MIN_ENTITY_CONFIDENCE: float = 0.70

# Swedish normalization bank — common abbreviations → canonical forms
SWEDISH_NORMALIZATION_BANK: dict[str, str] = {
    "sl": "Storstockholms Lokaltrafik",
    "smhi": "Sveriges meteorologiska och hydrologiska institut",
    "scb": "Statistiska centralbyrån",
    "sj": "Statens Järnvägar",
    "svt": "Sveriges Television",
    "sr": "Sveriges Radio",
    "msb": "Myndigheten för samhällsskydd och beredskap",
    "skv": "Skatteverket",
    "fk": "Försäkringskassan",
    "af": "Arbetsförmedlingen",
    "tvårumma": "tvårumslägenhet",
    "trerumma": "trerumslägenhet",
    "fyrarumma": "fyrarumslägenhet",
    "dagis": "förskola",
    "gympa": "idrott",
    "moms": "mervärdesskatt",
    "sthlm": "Stockholm",
    "gbg": "Göteborg",
    "cph": "Köpenhamn",
}

# Domain hints — keywords that suggest specific zones
DOMAIN_HINTS: dict[str, list[str]] = {
    Zone.MYNDIGHETER: [
        "väder",
        "klimat",
        "vind",
        "regn",
        "snö",
        "temperatur",
        "trafik",
        "väg",
        "järnväg",
        "tåg",
        "riksdag",
        "proposition",
        "betänkande",
        "motion",
        "befolkning",
        "statistik",
        "kommun",
        "region",
        "skola",
        "utbildning",
        "kursplan",
        "kolada",
        "nyckeltal",
    ],
    Zone.KUNSKAP: [
        "sök",
        "hitta",
        "information",
        "dokument",
        "artikel",
        "köpa",
        "sälja",
        "pris",
        "marknad",
        "annons",
    ],
    Zone.HANDLING: [
        "skapa",
        "generera",
        "kör",
        "exekvera",
        "kod",
        "podcast",
        "bild",
        "sandbox",
    ],
    Zone.JAMFORELSE: [
        "jämför",
        "olika",
        "modeller",
        "ai",
        "gpt",
        "claude",
        "grok",
        "gemini",
    ],
}


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

# ECE targets per band range
ECE_TARGET_BAND_01: float = 0.05
ECE_TARGET_BAND_2: float = 0.10

# Platt scaling defaults
PLATT_DEFAULT_A: float = 1.0
PLATT_DEFAULT_B: float = 0.0


# ---------------------------------------------------------------------------
# Zone Health Targets
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ZoneHealthTargets:
    """Target metrics for zone health monitoring."""

    intra_zone_silhouette_min: float = 0.45
    intra_zone_silhouette_target: float = 0.60
    inter_zone_distance_min: float = 0.40
    inter_zone_distance_target: float = 0.55
    confusion_risk_max: float = 0.40
    confusion_risk_target: float = 0.25
    zone_purity_min: float = 0.80
    zone_purity_target: float = 0.90
    hubness_max: float = 0.08
    hubness_target: float = 0.03


ZONE_HEALTH_TARGETS = ZoneHealthTargets()


# ---------------------------------------------------------------------------
# Pipeline Stages (Eval Ledger)
# ---------------------------------------------------------------------------


class PipelineStage(StrEnum):
    """The 5 stages of the precision routing pipeline."""

    INTENT = "intent"
    ROUTE = "route"
    BIGTOOL = "bigtool"
    RERANK = "rerank"
    E2E = "e2e"


PIPELINE_STAGES: list[tuple[int, str]] = [
    (1, PipelineStage.INTENT),
    (2, PipelineStage.ROUTE),
    (3, PipelineStage.BIGTOOL),
    (4, PipelineStage.RERANK),
    (5, PipelineStage.E2E),
]


# ---------------------------------------------------------------------------
# Deploy Control — Triple Gate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeployGateThresholds:
    """Thresholds for the triple-gate deployment system."""

    # Gate 1: Separation
    min_separation_score: float = 0.65

    # Gate 2: Eval
    min_success_rate: float = 0.80
    min_hard_negative_rate: float = 0.85
    min_adversarial_rate: float = 0.80

    # Gate 3: LLM Judge
    min_description_clarity: float = 4.0
    min_keyword_relevance: float = 4.0
    min_disambiguation_quality: float = 4.0


DEPLOY_GATE_THRESHOLDS = DeployGateThresholds()


# ---------------------------------------------------------------------------
# Synth Forge
# ---------------------------------------------------------------------------

SYNTH_DIFFICULTIES: list[str] = ["easy", "medium", "hard", "adversarial"]
SYNTH_QUESTIONS_PER_DIFFICULTY: int = 4
SYNTH_ROUNDTRIP_TOP_K: int = 3
