"""Deterministic detection of conflicts between clearly labelled tender dates."""

from collections import defaultdict
from datetime import datetime
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict


EventType = Literal[
    "bid_submission_deadline",
    "bid_opening",
    "question_deadline",
    "contract_commencement",
    "contract_completion",
]

_EVENTS: tuple[tuple[EventType, re.Pattern], ...] = (
    ("bid_submission_deadline", re.compile(
        r"\b(?:bid|proposal)\s+(?:submission\s+)?(?:deadline|due(?:\s+date)?)\b|"
        r"\b(?:bids|proposals)\s+(?:must be\s+)?(?:received|submitted)\s+by\b",
        re.IGNORECASE,
    )),
    ("bid_opening", re.compile(r"\bbid\s+opening(?:\s+date|\s+time)?\b", re.IGNORECASE)),
    ("question_deadline", re.compile(
        r"\b(?:question|inquir(?:y|ies))\s+(?:submission\s+)?(?:deadline|due)\b|"
        r"\bquestions\s+(?:must be\s+)?(?:received|submitted)\s+by\b",
        re.IGNORECASE,
    )),
    ("contract_commencement", re.compile(
        r"\b(?:contract|work)\s+(?:commencement|start)(?:\s+date)?\b|"
        r"\bnotice to proceed\b",
        re.IGNORECASE,
    )),
    ("contract_completion", re.compile(
        r"\b(?:contract|work|project)\s+(?:completion|complete)(?:\s+date)?\b|"
        r"\bsubstantial completion\b",
        re.IGNORECASE,
    )),
)
_MONTH_DATE = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?"
    r"(?:,|\s)\s*\d{4}\b",
    re.IGNORECASE,
)
_NUMERIC_DATE = re.compile(r"\b(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b")
_TIME = re.compile(r"\b\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)\b", re.IGNORECASE)
_TENTATIVE = re.compile(
    r"\b(?:tentative|anticipated|expected|proposed|amended|revised|"
    r"subject to change)\b",
    re.IGNORECASE,
)


class DateEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    source_page: int
    exact_text: str
    tentative: bool


class DateConflict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: EventType
    conflicting_values: list[str]
    source_pages: list[int]
    evidence: list[DateEvidence]
    status: Literal["review_required"] = "review_required"
    reason: Literal["conflicting_values", "tentative_or_amended_values"]


def _normalize_date(raw: str) -> str | None:
    cleaned = re.sub(r"(\d)(?:st|nd|rd|th)\b", r"\1", raw, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned.replace(",", " ")).strip()
    for pattern in ("%B %d %Y", "%b %d %Y", "%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%m-%d-%y"):
        try:
            return datetime.strptime(cleaned, pattern).date().isoformat()
        except ValueError:
            continue
    return None


def _normalize_time(raw: str | None) -> str | None:
    if raw is None:
        return None
    cleaned = raw.casefold().replace(".", "").replace(" ", "")
    for pattern in ("%I:%M%p", "%I%p"):
        try:
            return datetime.strptime(cleaned, pattern).time().strftime("%H:%M")
        except ValueError:
            continue
    return None


def _event_for(text: str) -> EventType | None:
    matches = [event for event, pattern in _EVENTS if pattern.search(text)]
    return matches[0] if len(matches) == 1 else None


def _values_conflict(values: list[str]) -> bool:
    dates = {value.split()[0] for value in values}
    if len(dates) > 1:
        return True
    specified_times = {
        value.split()[1] for value in values if len(value.split()) == 2
    }
    return len(specified_times) > 1


def detect_date_conflicts(pages: list[dict]) -> list[DateConflict]:
    findings: dict[EventType, list[DateEvidence]] = defaultdict(list)
    normalized: dict[EventType, list[str]] = defaultdict(list)
    for page in pages:
        for raw_line in page["text"].splitlines():
            text = " ".join(raw_line.split())
            event = _event_for(text)
            date_match = _MONTH_DATE.search(text) or _NUMERIC_DATE.search(text)
            if event is None or date_match is None:
                continue
            date_value = _normalize_date(date_match.group(0))
            if date_value is None:
                continue
            time_match = _TIME.search(text)
            time_value = _normalize_time(time_match.group(0) if time_match else None)
            value = date_value + (f" {time_value}" if time_value else "")
            findings[event].append(DateEvidence(
                value=value,
                source_page=page["page_number"],
                exact_text=raw_line.strip(),
                tentative=bool(_TENTATIVE.search(text)),
            ))
            normalized[event].append(value)

    conflicts: list[DateConflict] = []
    for event, evidence in findings.items():
        values = sorted(set(normalized[event]))
        if not _values_conflict(values):
            continue
        tentative = any(item.tentative for item in evidence)
        conflicts.append(DateConflict(
            event_type=event,
            conflicting_values=values,
            source_pages=sorted({item.source_page for item in evidence}),
            evidence=evidence,
            reason=(
                "tentative_or_amended_values" if tentative else "conflicting_values"
            ),
        ))
    return conflicts
