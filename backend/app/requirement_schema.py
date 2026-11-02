
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class RequirementCategory(str, Enum):
    QUALIFICATION = "qualification"
    PERSONNEL = "personnel"
    SCORING = "scoring"
    TECHNICAL = "technical"
    DOCUMENTATION = "documentation"
    UNKNOWN = "unknown"


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


class RequirementExtractionResult(BaseModel):
    """A collection of requirements extracted from a document."""

    model_config = ConfigDict(extra="forbid")

    requirements: list[TenderRequirement]
