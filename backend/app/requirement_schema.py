
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RequirementCategory(str, Enum):
    QUALIFICATION = "qualification"
    PERSONNEL = "personnel"
    SCORING = "scoring"
    TECHNICAL = "technical"
    DOCUMENTATION = "documentation"
    UNKNOWN = "unknown"


class SourceEvidence(BaseModel):
    """Exact slice of parser page text; offsets are zero-based, end-exclusive."""

    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(ge=1, strict=True)
    text: str = Field(min_length=1)
    start_char: int = Field(ge=0, strict=True)
    end_char: int = Field(gt=0, strict=True)


class SourceTrace(BaseModel):
    """Computed lexical provenance, never a model assertion of verification."""

    model_config = ConfigDict(extra="forbid")

    original_source_page: int = Field(ge=1, strict=True)
    status: Literal["matched", "missing", "ambiguous"]
    verified_source_page: int | None = Field(default=None, ge=1, strict=True)
    match_method: Literal["casefold_whitespace_exact"] = "casefold_whitespace_exact"
    evidence: list[SourceEvidence] = Field(default_factory=list)


class TenderRequirement(BaseModel):
    """One requirement extracted from a tender document."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    requirement_text: str = Field(min_length=1)
    category: RequirementCategory
    mandatory: bool | None = Field(..., strict=True)
    source_page: int = Field(ge=1, strict=True)
    evidence_needed: str | None = None
    needs_review: bool = Field(strict=True)
    source_trace: SourceTrace | None = Field(default=None, exclude_if=lambda value: value is None)


class RequirementExtractionResult(BaseModel):
    """A collection of requirements extracted from a document."""

    model_config = ConfigDict(extra="forbid")

    requirements: list[TenderRequirement]
