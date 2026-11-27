"""High-value exact-passage diagnostics for candidates missed by extraction."""

import re

from app.requirement_schema import (
    RequirementCategory,
    RequirementExtractionResult,
    SourceEvidence,
    SourceTrace,
    TenderRequirement,
)


_CRITICAL_PASSAGE = re.compile(
    r"(?:"
    r"\b(?:approved|accepted)\s+(?:equal|substitute|alternative)\b|"
    r"\b(?:manufacturer|model|equipment)\b.{0,100}\b(?:compatible|"
    r"approved|substitut\w*|equal)\b|"
    r"\b(?:manufacturer|brand|make)\b.{0,80}\b(?:only|basis of design|"
    r"no substitutions?)\b|"
    r"\b(?:minimum|maximum|not less than|not exceed|at least|no more than)\b"
    r".{0,80}\b\d+(?:\.\d+)?\s*(?:%|cfm|btu(?:/h)?|tons?|seer2?|eer|"
    r"cop|kw|volts?|amps?|psi|inches?|feet|ft)\b|"
    r"\b(?:bidder|contractor)\b.{0,100}\b(?:licensed|certified|"
    r"license|qualification)\b|"
    r"\b(?:bids?|proposals?|responses?)\b.{0,100}\b(?:due|received|"
    r"submitted|delivered)\b|"
    r"\b(?:complete|completion|commence|commencement)\b.{0,80}"
    r"\b(?:by|before|deadline|date)\b|"
    r"\b(?:failure to|will be)\b.{0,80}\b(?:disqualif\w*|reject\w*)\b|"
    r"\bdo\s+not\s+(?:provide|submit|include|respond)\b|"
    r"\b(?:certificate|affidavit|bond|license|schedule|data sheet)\b"
    r".{0,80}\b(?:submit|provide|include|required)\b"
    r")",
    re.IGNORECASE,
)


def _normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def _passages(text: str):
    for match in re.finditer(r"[^\n.!?]+(?:[.!?](?=\s|$)|$)", text):
        raw = match.group(0)
        stripped = raw.strip()
        if stripped:
            leading = len(raw) - len(raw.lstrip())
            start = match.start() + leading
            yield stripped, start, start + len(stripped)


def find_uncovered_critical_passages(
    pages: list[dict],
    extraction: RequirementExtractionResult,
) -> list[TenderRequirement]:
    """Return exact, source-matched review candidates not covered by extraction."""

    covered: dict[int, set[str]] = {}
    for item in extraction.requirements:
        covered.setdefault(item.source_page, set()).add(
            _normalized(item.requirement_text)
        )
    diagnostics: list[TenderRequirement] = []
    for page in pages:
        for text, start, end in _passages(page["text"]):
            key = (page["page_number"], _normalized(text))
            normalized = key[1]
            already_covered = any(
                normalized in quote or quote in normalized
                for quote in covered.get(page["page_number"], set())
            )
            if already_covered or not _CRITICAL_PASSAGE.search(text):
                continue
            diagnostics.append(TenderRequirement(
                requirement_text=text,
                category=RequirementCategory.UNKNOWN,
                mandatory=None,
                source_page=page["page_number"],
                evidence_needed=None,
                needs_review=True,
                source_trace=SourceTrace(
                    original_source_page=page["page_number"],
                    status="matched",
                    verified_source_page=page["page_number"],
                    evidence=[SourceEvidence(
                        page_number=page["page_number"],
                        text=text,
                        start_char=start,
                        end_char=end,
                    )],
                ),
            ))
            covered.setdefault(page["page_number"], set()).add(normalized)
    return diagnostics
