"""Conservative post-extraction relevance partitioning.

Only narrow, high-confidence background patterns are excluded. Any uncertainty
or provenance problem is retained in the human review queue.
"""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.requirement_schema import (
    RequirementCategory,
    RequirementExtractionResult,
    SourceTrace,
    TenderRequirement,
)


_OBLIGATION_SIGNAL = re.compile(
    r"\b(?:must|shall|required|submit|provide|include|comply|responsible|"
    r"failure to|disqualif\w*|reject\w*|no later than|within \d+|deadline|"
    r"attend|optional|encouraged|condition of award)\b",
    re.IGNORECASE,
)
_AMBIGUOUS_SIGNAL = re.compile(
    r"\b(?:may be required|as necessary|as applicable|where appropriate|"
    r"to be determined|anticipated requirement|could be required)\b",
    re.IGNORECASE,
)
_EXCLUSION_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    (
        "definition_or_explanation",
        re.compile(
            r"^(?:for (?:the )?purposes of .{0,80},?\s*)?"
            r"(?:the\s+)?(?:term|word|phrase)\s+.{1,100}\s+"
            r"(?:means|refers to|is defined as)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "background_or_history",
        re.compile(
            r"^(?:the|this)\s+(?:project|facility|building|campus)\s+"
            r"(?:was|is located|was constructed|has served|currently serves|"
            r"consists of|includes)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "procurement_description",
        re.compile(
            r"^(?:the\s+)?(?:owner|district|college|city)\s+"
            r"(?:is seeking|seeks|intends to procure|has issued)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "definition_or_explanation",
        re.compile(
            r"^(?:this|the)\s+(?:section|document|rfp|request for proposals)\s+"
            r"(?:describes|provides|summarizes|explains)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "marketing_description",
        re.compile(
            r"^.{1,80}\s+(?:is|are)\s+(?:a\s+)?"
            r"(?:leading|innovative|state-of-the-art)\b",
            re.IGNORECASE,
        ),
    ),
)


class ReviewQueueItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement: TenderRequirement
    reasons: list[str]


class ExcludedCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_text: str
    source_page: int
    source_trace: SourceTrace | None = None
    reason: Literal[
        "background_or_history",
        "definition_or_explanation",
        "procurement_description",
        "marketing_description",
    ]


class NoticeCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_text: str
    mandatory: bool | None
    source_page: int
    source_trace: SourceTrace | None = None
    reason: Literal[
        "optional_prebid_event",
        "contact_information",
        "optional_communication",
        "interpretation_definition",
    ]


class RelevanceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirements: list[TenderRequirement]
    review_queue: list[ReviewQueueItem]
    notices: list[NoticeCandidate]
    excluded: list[ExcludedCandidate]


def _review_reasons(
    requirement: TenderRequirement,
    exclusion_reason: str | None,
    notice_reason: str | None,
) -> list[str]:
    reasons: list[str] = []
    if requirement.needs_review:
        reasons.append("existing review flag")
    if requirement.mandatory is None:
        reasons.append("mandatory status is uncertain")
    if requirement.category == RequirementCategory.UNKNOWN and notice_reason is None:
        reasons.append("category is unknown")
    if requirement.source_trace is None:
        reasons.append("source trace is unavailable")
    elif requirement.source_trace.status != "matched":
        reasons.append(f"source quote is {requirement.source_trace.status}")
    if _AMBIGUOUS_SIGNAL.search(requirement.requirement_text):
        reasons.append("potentially ambiguous applicability")
    if (exclusion_reason is not None or notice_reason is not None) and requirement.mandatory is True:
        reasons.append(
            "mandatory flag conflicts with apparently non-actionable context"
        )
    return list(dict.fromkeys(reasons))


def _exclusion_reason(requirement: TenderRequirement) -> str | None:
    if _OBLIGATION_SIGNAL.search(requirement.requirement_text):
        return None
    text = " ".join(requirement.requirement_text.split())
    for reason, pattern in _EXCLUSION_PATTERNS:
        if pattern.search(text):
            return reason
    return None


_HARD_OBLIGATION_SIGNAL = re.compile(
    r"\b(?:must|shall|required|failure to|disqualif\w*|condition of award)\b",
    re.IGNORECASE,
)
_OPTIONAL_PREBID = re.compile(
    r"\b(?:optional|not mandatory|non[- ]mandatory)\b.{0,100}"
    r"\b(?:pre[- ]?bid|site visit|walkthrough|conference|meeting)\b|"
    r"\b(?:pre[- ]?bid|site visit|walkthrough|conference|meeting)\b.{0,100}"
    r"\b(?:optional|not mandatory|non[- ]mandatory)\b",
    re.IGNORECASE,
)
_CONTACT_INFORMATION = re.compile(
    r"\b(?:contact|questions? (?:may be )?directed to|inquiries? (?:may be )?sent to)\b"
    r".{0,160}(?:[\w.+-]+@[\w.-]+\.\w+|\(?\d{3}\)?[- .]\d{3}[- .]\d{4})",
    re.IGNORECASE,
)
_OPTIONAL_COMMUNICATION = re.compile(
    r"\b(?:may|can)\s+(?:contact|email|call|direct|send)\b|"
    r"\b(?:questions|inquiries)\s+may\s+be\s+(?:sent|directed)\b",
    re.IGNORECASE,
)
_INTERPRETATION_DEFINITION = re.compile(
    r"^(?:the\s+)?(?:term|word|phrase)\s+[\"']?(?:must|shall|required)[\"']?"
    r"\s+(?:means|refers to|is defined as)\b",
    re.IGNORECASE,
)


def _notice_reason(requirement: TenderRequirement) -> str | None:
    text = " ".join(requirement.requirement_text.split())
    if _HARD_OBLIGATION_SIGNAL.search(text) and not _INTERPRETATION_DEFINITION.search(text):
        return None
    for reason, pattern in (
        ("optional_prebid_event", _OPTIONAL_PREBID),
        ("contact_information", _CONTACT_INFORMATION),
        ("optional_communication", _OPTIONAL_COMMUNICATION),
        ("interpretation_definition", _INTERPRETATION_DEFINITION),
    ):
        if pattern.search(text):
            return reason
    return None


def partition_requirements(
    result: RequirementExtractionResult,
) -> RelevanceResult:
    """Partition candidates without mutating or silently dropping uncertainty."""

    requirements: list[TenderRequirement] = []
    review_queue: list[ReviewQueueItem] = []
    notices: list[NoticeCandidate] = []
    excluded: list[ExcludedCandidate] = []

    for candidate in result.requirements:
        exclusion_reason = _exclusion_reason(candidate)
        notice_reason = _notice_reason(candidate)
        reasons = _review_reasons(candidate, exclusion_reason, notice_reason)
        if reasons:
            review_queue.append(
                ReviewQueueItem(
                    requirement=candidate.model_copy(
                        deep=True,
                        update={"needs_review": True},
                    ),
                    reasons=reasons,
                )
            )
            continue

        if notice_reason is not None:
            notices.append(NoticeCandidate(
                requirement_text=candidate.requirement_text,
                mandatory=candidate.mandatory,
                source_page=candidate.source_page,
                source_trace=candidate.source_trace,
                reason=notice_reason,
            ))
            continue

        if exclusion_reason is not None:
            excluded.append(
                ExcludedCandidate(
                    requirement_text=candidate.requirement_text,
                    source_page=candidate.source_page,
                    source_trace=candidate.source_trace,
                    reason=exclusion_reason,
                )
            )
            continue

        requirements.append(candidate.model_copy(deep=True))

    return RelevanceResult(
        requirements=requirements,
        review_queue=review_queue,
        notices=notices,
        excluded=excluded,
    )
