"""Pydantic schemas for debate mode."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DebateVote(BaseModel):
    """A single participant's vote in round 4."""

    voter: str = Field(..., description="Name of the voter")
    voter_key: str = Field(default="", description="Model key of the voter")
    voted_for: str = Field(..., description="Name of the participant voted for")
    short_motivation: str = Field(
        ..., max_length=200, description="Short motivation for the vote"
    )
    three_bullets: list[str] = Field(
        ..., min_length=3, max_length=3, description="Three bullet points"
    )


class DebateParticipant(BaseModel):
    """A debate participant."""

    key: str = Field(..., description="Model key (e.g. 'grok', 'claude')")
    display: str = Field(..., description="Display name (e.g. 'Grok', 'Claude')")
    tool_name: str = Field(..., description="Tool name (e.g. 'call_grok')")
    config_id: int = Field(default=-1, description="LLM config ID")
    is_oneseek: bool = Field(default=False, description="Whether this is OneSeek")


class DebateRoundResult(BaseModel):
    """Results from a single debate round."""

    round_number: int = Field(..., ge=1, le=4)
    round_type: str = Field(..., description="introduction|argument|deepening|voting")
    participant_order: list[str] = Field(default_factory=list)
    responses: dict[str, str] = Field(
        default_factory=dict, description="participant_name → response_text"
    )
    word_counts: dict[str, int] = Field(
        default_factory=dict, description="participant_name → word_count"
    )


class DebateResult(BaseModel):
    """Complete debate result after all rounds."""

    topic: str = Field(..., description="The debate topic")
    participants: list[DebateParticipant] = Field(default_factory=list)
    rounds: list[DebateRoundResult] = Field(default_factory=list)
    votes: list[DebateVote] = Field(default_factory=list)
    vote_counts: dict[str, int] = Field(
        default_factory=dict, description="participant_name → total_votes"
    )
    word_counts: dict[str, int] = Field(
        default_factory=dict, description="participant_name → total_words"
    )
    winner: str = Field(default="", description="Name of the debate winner")
    tiebreaker_used: bool = Field(default=False)
    self_votes_filtered: int = Field(default=0)


class DebateSSEEvent(BaseModel):
    """SSE event payload for debate mode streaming."""

    event_type: str = Field(..., description="Event type identifier")
    data: dict[str, object] = Field(default_factory=dict)
    timestamp: float = Field(default=0.0)
