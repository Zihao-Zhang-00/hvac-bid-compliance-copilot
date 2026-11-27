"""Conservative, offset-preserving masking for extraction-only page views."""

from collections import Counter
import re


_PAGE_LABEL = re.compile(
    r"^(?:page\s+)?\d+\s*(?:of|/)\s*\d+$|^page\s+\d+$|^\d+$",
    re.IGNORECASE,
)
_DOCUMENT_ID = re.compile(
    r"^(?:(?:rfp|rfq|ifb|solicitation|project)\s*"
    r"(?:no\.?|number|#)\s*)[A-Z0-9][A-Z0-9._/-]*$",
    re.IGNORECASE,
)
_TOC_ENTRY = re.compile(r"^.{2,100}\.{3,}\s*\d+$")
_NAVIGATION_TITLE = re.compile(
    r"^(?:table of contents|contents|index|appendix|section\s+\d+|"
    r"\d+(?:\.\d+)*\s+[A-Z][A-Z\s/&-]{2,60})$",
    re.IGNORECASE,
)
_SUBSTANTIVE_SIGNAL = re.compile(
    r"\b(?:must|shall|required|submit|provide|include|due|deadline|"
    r"complete|licensed|certified|disqualif\w*|approved\s+"
    r"(?:equal|substitute|alternative)|compatible|do\s+not)\b",
    re.IGNORECASE,
)


def _normalized(line: str) -> str:
    return " ".join(line.casefold().split())


def _boundary_lines(text: str) -> set[str]:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return set()
    return {_normalized(line) for line in lines[:2] + lines[-2:]}


def _is_clear_navigation(line: str) -> bool:
    stripped = " ".join(line.split())
    if not stripped or _SUBSTANTIVE_SIGNAL.search(stripped):
        return False
    return bool(
        _PAGE_LABEL.fullmatch(stripped)
        or _DOCUMENT_ID.fullmatch(stripped)
        or _TOC_ENTRY.fullmatch(stripped)
        or _NAVIGATION_TITLE.fullmatch(stripped)
    )


def _mask_line(line: str) -> str:
    return "".join(char if char in "\r\n" else " " for char in line)


def build_extraction_view(pages: list[dict]) -> list[dict]:
    """Mask clear navigation while preserving page numbers and character offsets."""

    boundary_counts = Counter(
        boundary
        for page in pages
        for boundary in _boundary_lines(page["text"])
        if boundary
    )
    repeated_boundaries = {
        text for text, count in boundary_counts.items() if count >= 2
    }

    extraction_pages: list[dict] = []
    for page in pages:
        masked_lines: list[str] = []
        for line in page["text"].splitlines(keepends=True):
            normalized = _normalized(line)
            repeated_metadata = (
                normalized in repeated_boundaries
                and len(normalized) <= 120
                and not _SUBSTANTIVE_SIGNAL.search(line)
            )
            masked_lines.append(
                _mask_line(line)
                if repeated_metadata or _is_clear_navigation(line)
                else line
            )
        extraction_pages.append({
            "page_number": page["page_number"],
            "text": "".join(masked_lines),
        })
    return extraction_pages
