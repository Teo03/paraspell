"""Pydantic schemas for the spell-check API (NFR-12).

SpellCheckRequest  – inbound payload for /check/text
Suggestion         – a single ranked correction candidate (UC-03, §5.2.4)
Correction         – one misspelled word + its ranked suggestions
SpellCheckResponse – full response envelope
"""

from pydantic import BaseModel, Field


class SpellCheckRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Plain text to spell-check.")


class Suggestion(BaseModel):
    word: str = Field(..., description="Candidate correction.")
    score: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0–1).")


class Correction(BaseModel):
    original: str = Field(..., description="The misspelled word as it appears in the input.")
    offset: int = Field(..., ge=0, description="Character offset in the original text.")
    suggestions: list[Suggestion] = Field(
        default_factory=list,
        max_length=5,          # UC-03: up to 5 ranked suggestions
        description="Ranked correction candidates (up to MAX_SUGGESTIONS).",
    )


class SpellCheckResponse(BaseModel):
    word_count: int = Field(..., ge=0, description="Total words processed.")
    error_count: int = Field(..., ge=0, description="Number of misspelled words found.")
    corrections: list[Correction] = Field(
        default_factory=list,
        description="One entry per misspelled word.",
    )
