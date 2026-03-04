"""NEXUS configuration — constants, zone definitions, thresholds.

Single source of truth for all NEXUS-specific configuration values.
"""

from dataclasses import dataclass
from enum import StrEnum

# ---------------------------------------------------------------------------
# Zone Architecture
# ---------------------------------------------------------------------------


class Zone(StrEnum):
    """Zones aligned with the real platform intents (intent_definition_service.py).

    The platform routes to 4 intents: kunskap, skapande, jämförelse, konversation.
    NEXUS uses these same intents as its zone system so that metrics, calibration,
    and routing evaluation are directly comparable to live routing decisions.
    """

    KUNSKAP = "kunskap"
    SKAPANDE = "skapande"
    JAMFORELSE = "jämförelse"
    KONVERSATION = "konversation"


# Backward-compat aliases for old zone names used in tests/existing code
Zone.MYNDIGHETER = Zone.KUNSKAP  # type: ignore[attr-defined]
Zone.HANDLING = Zone.SKAPANDE  # type: ignore[attr-defined]


ZONE_PREFIXES: dict[str, str] = {
    Zone.KUNSKAP: "[KUNSK] ",
    Zone.SKAPANDE: "[SKAP] ",
    Zone.JAMFORELSE: "[JAMFR] ",
    Zone.KONVERSATION: "[KONV] ",
}

# Namespace prefix → zone mapping (aligned with platform routing)
NAMESPACE_ZONE_MAP: dict[str, Zone] = {
    "tools/knowledge": Zone.KUNSKAP,
    "tools/weather": Zone.KUNSKAP,
    "tools/politik": Zone.KUNSKAP,
    "tools/statistics": Zone.KUNSKAP,
    "tools/trafik": Zone.KUNSKAP,
    "tools/bolag": Zone.KUNSKAP,
    "tools/marketplace": Zone.KUNSKAP,
    "tools/action": Zone.SKAPANDE,
    "tools/code": Zone.SKAPANDE,
    "tools/kartor": Zone.SKAPANDE,
    "tools/compare": Zone.JAMFORELSE,
    "tools/general": Zone.KUNSKAP,
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

# Domain hints — keywords that suggest specific zones.
# Aligned with real intent_definition_service.py keywords.
DOMAIN_HINTS: dict[str, list[str]] = {
    Zone.KUNSKAP: [
        # From real intent_definition_service "kunskap" keywords
        "dokument",
        "docs",
        "kunskap",
        "sök",
        "search",
        "notion",
        "slack",
        "github",
        "sammanfatta",
        # Weather / SMHI
        "väder",
        "vädret",
        "vader",
        "vadret",
        "smhi",
        "temperatur",
        "regn",
        "prognos",
        # Traffic
        "trafik",
        "trafiken",
        "trafikverket",
        "tåg",
        "väg",
        # Statistics
        "statistik",
        "scb",
        "befolkning",
        "kolada",
        "nyckeltal",
        # Company
        "bolag",
        "bolagsverket",
        # Parliament
        "riksdagen",
        "proposition",
        "betänkande",
        "motion",
        # Marketplace
        "blocket",
        "tradera",
        "marknadsplats",
        "annons",
        "begagnat",
        # Web
        "webb",
        "länk",
        "nyheter",
        "nyheter",
        # General knowledge
        "vad är",
        "hur mycket",
        "hur många",
        "hitta",
        "information",
        # Education
        "skola",
        "utbildning",
        "kursplan",
        "skolverket",
        # Municipality
        "kommun",
        "region",
    ],
    Zone.SKAPANDE: [
        # From real intent_definition_service "skapande" keywords
        "skapa",
        "generera",
        "gör",
        "rita",
        "podcast",
        "bild",
        "karta",
        "kartbild",
        "kod",
        "script",
        "python",
        "sandbox",
        "fil",
        "skriv",
        "exekvera",
        "kör",
    ],
    Zone.JAMFORELSE: [
        # From real intent_definition_service "jämförelse" keywords
        "/compare",
        "compare",
        "jämför",
        "jamfor",
        "jämförelse",
        "modeller",
        "ai",
        "gpt",
        "claude",
        "grok",
        "gemini",
    ],
    Zone.KONVERSATION: [
        # From real intent_definition_service "konversation" keywords
        "hej",
        "tjena",
        "hallå",
        "hur mår du",
        "konversation",
        "smalltalk",
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
