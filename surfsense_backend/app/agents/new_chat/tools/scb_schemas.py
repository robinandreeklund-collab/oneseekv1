"""Strict Pydantic input schemas for SCB LLM tools.

These models give the tool-calling LLM (Nemotron 3 nano) an explicit JSON Schema
so it can produce structured output directly — no coercion guesswork needed.

Each model maps 1-to-1 to a tool's ``args_schema`` parameter on the
``@tool(...)`` decorator.
"""

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------

# Selection values: each variable maps to either a single string or a list
# of strings.  Strings can be literal codes ("0180"), v2 expressions
# ("TOP(3)", "RANGE(2018,2024)", "*"), or year-range shorthands ("2015-2020").
#
# Using ``str | list[str]`` (instead of the old ``Any``) makes the schema
# unambiguous for structured-output models.


# ---------------------------------------------------------------------------
# Tool 1: scb_search
# ---------------------------------------------------------------------------


class ScbSearchInput(BaseModel):
    """Input for ``scb_search`` — fulltext search across SCB tables."""

    query: str = Field(
        ...,
        min_length=1,
        description="Search terms, preferably in Swedish (e.g. 'befolkning', 'arbetslöshet').",
    )
    max_results: int = Field(
        15,
        ge=1,
        le=50,
        description="Maximum number of results to return.",
    )
    past_days: int | None = Field(
        None,
        ge=1,
        description="Only include tables updated in the last N days.",
    )


# ---------------------------------------------------------------------------
# Tool 2: scb_browse
# ---------------------------------------------------------------------------


class ScbBrowseInput(BaseModel):
    """Input for ``scb_browse`` — navigate the SCB topic tree."""

    path: str = Field(
        "",
        description=(
            "SCB path to browse.  Empty string = top level.  "
            "Examples: 'AM' (labour market), 'BE/BE0101' (population stats)."
        ),
    )


# ---------------------------------------------------------------------------
# Tool 3: scb_inspect
# ---------------------------------------------------------------------------


class ScbInspectInput(BaseModel):
    """Input for ``scb_inspect`` — full metadata for a table."""

    table_id: str = Field(
        ...,
        min_length=1,
        description="SCB table ID (e.g. 'TAB638', 'BefolkningNy').",
    )


# ---------------------------------------------------------------------------
# Tool 4: scb_codelist
# ---------------------------------------------------------------------------


class ScbCodelistInput(BaseModel):
    """Input for ``scb_codelist`` — fetch a codelist."""

    codelist_id: str = Field(
        ...,
        min_length=1,
        description="Codelist ID (e.g. 'vs_RegionLän', 'vs_RegionKommun07').",
    )


# ---------------------------------------------------------------------------
# Tool 5: scb_preview
# ---------------------------------------------------------------------------


class ScbPreviewInput(BaseModel):
    """Input for ``scb_preview`` — auto-limited data preview (~20 rows)."""

    table_id: str = Field(
        ...,
        min_length=1,
        description="SCB table ID.",
    )
    selection: dict[str, str | list[str]] | None = Field(
        None,
        description=(
            "Optional partial selection.  Dict mapping variable code to value "
            "codes.  Unspecified variables are auto-limited.  "
            'Example: {"Region": ["0180"], "Tid": ["TOP(1)"]}'
        ),
    )


# ---------------------------------------------------------------------------
# Tool 6: scb_validate
# ---------------------------------------------------------------------------


class ScbValidateInput(BaseModel):
    """Input for ``scb_validate`` — dry-run validation with auto-complete."""

    table_id: str = Field(
        ...,
        min_length=1,
        description="SCB table ID.",
    )
    selection: dict[str, str | list[str]] = Field(
        ...,
        description=(
            "Dict mapping variable code to value codes.  "
            "Values can be strings or lists of strings.  "
            "Supports v2 expressions: TOP(n), FROM(x), RANGE(x,y), *.  "
            'Example: {"Region": ["0180"], "Tid": ["TOP(3)"], '
            '"ContentsCode": ["BE0101N1"]}'
        ),
    )


# ---------------------------------------------------------------------------
# Tool 7: scb_fetch
# ---------------------------------------------------------------------------


class ScbFetchInput(BaseModel):
    """Input for ``scb_fetch`` — fetch data as a markdown table."""

    table_id: str = Field(
        ...,
        min_length=1,
        description="SCB table ID (e.g. 'TAB638').",
    )
    selection: dict[str, str | list[str]] = Field(
        ...,
        description=(
            "Dict mapping variable codes to value codes.  "
            "Values can be strings or lists of strings.  "
            "Supports v2 expressions: TOP(n), FROM(x), RANGE(x,y), *.  "
            "Missing eliminable variables are auto-filled with defaults.  "
            'Example: {"Region": ["0180","1480"], "Tid": ["TOP(3)"], '
            '"ContentsCode": ["BE0101N1"]}'
        ),
    )
    codelist: dict[str, str] | None = Field(
        None,
        description=(
            "Optional dict mapping variable code to codelist ID.  "
            'Example: {"Region": "vs_RegionLän"} to use counties only.'
        ),
    )
    max_rows: int = Field(
        100,
        ge=1,
        le=500,
        description="Maximum rows in the returned markdown table.",
    )
