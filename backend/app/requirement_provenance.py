"""Deterministic source tracing shared by recovery and quote review.

Only case and whitespace are normalized. Evidence always refers to original
parser text. Unique matching pages are confirmed; multiple occurrences on one
page are retained without inventing page ambiguity. No fuzzy/semantic match.
"""

import json
import logging

from app.requirement_schema import (
    RequirementExtractionResult, SourceEvidence, SourceTrace,
)

logger = logging.getLogger(__name__)


def _normalize(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Map each normalized character back to its exact original span."""
    chars = []
    spans = []
    for index, char in enumerate(text):
        if char.isspace():
            if chars and chars[-1] == " ":
                spans[-1] = (spans[-1][0], index + 1)
            else:
                chars.append(" ")
                spans.append((index, index + 1))
        else:
            folded = char.casefold()
            chars.extend(folded)
            spans.extend([(index, index + 1)] * len(folded))
    return "".join(chars), spans


def _page_index(pages: list[dict]) -> list[tuple]:
    indexed = []
    seen = set()
    for page in pages:
        number, text = page["page_number"], page["text"]
        if type(number) is not int or number < 1 or number in seen:
            raise ValueError("Page numbers must be unique positive integers")
        if not isinstance(text, str):
            raise ValueError("Page text must be a string")
        seen.add(number)
        normalized, spans = _normalize(text)
        indexed.append((number, text, normalized, spans))
    return sorted(indexed)


def _word(char: str) -> bool:
    return char.isalnum() or char == "_"


def _trace(quote: str, reported: int, indexed: list[tuple]) -> SourceTrace:
    needle = _normalize(quote.strip())[0]
    evidence = []
    for number, text, normalized, spans in indexed:
        start = normalized.find(needle)
        while needle and start != -1:
            end = start + len(needle)
            # Do not confirm partial words/numbers or half a casefold expansion.
            left_ok = start == 0 or not (_word(normalized[start - 1]) and _word(needle[0]))
            right_ok = end == len(normalized) or not (_word(normalized[end]) and _word(needle[-1]))
            whole_chars = (
                (start == 0 or spans[start - 1] != spans[start])
                and (end == len(spans) or spans[end - 1] != spans[end])
            )
            # A trailing numeric token must not be a prefix of a decimal.
            numeric_prefix = (
                needle[-1].isdigit() and end + 1 < len(normalized)
                and normalized[end] in ".," and normalized[end + 1].isdigit()
            )
            numeric_suffix = (
                needle[0].isdigit() and start > 1
                and normalized[start - 1] in ".," and normalized[start - 2].isdigit()
            )
            decimal_cut = (
                len(needle) > 1 and needle[-1] in ".," and needle[-2].isdigit()
                and end < len(normalized) and normalized[end].isdigit()
            )
            if left_ok and right_ok and whole_chars and not (numeric_prefix or numeric_suffix or decimal_cut):
                lo, hi = spans[start][0], spans[end - 1][1]
                evidence.append(SourceEvidence(
                    page_number=number, text=text[lo:hi], start_char=lo, end_char=hi,
                ))
            start = normalized.find(needle, start + 1)
    matched_pages = sorted({item.page_number for item in evidence})
    return SourceTrace(
        original_source_page=reported,
        status="matched" if len(matched_pages) == 1 else "ambiguous" if matched_pages else "missing",
        verified_source_page=matched_pages[0] if len(matched_pages) == 1 else None,
        evidence=evidence,
    )


def trace_source_pages(
    result: RequirementExtractionResult, pages: list[dict],
) -> RequirementExtractionResult:
    """Recompute provenance, preserving original page and existing review flags.

    source_page stays backward compatible; consumers must use source_trace's
    verified_source_page for a confirmed location. Missing/ambiguous records
    retain their original, explicitly unverified model page.
    """
    indexed = _page_index(pages)
    traced = []
    for index, requirement in enumerate(result.requirements):
        original = (
            requirement.source_trace.original_source_page
            if requirement.source_trace is not None else requirement.source_page
        )
        trace = _trace(requirement.requirement_text, original, indexed)
        corrected = trace.verified_source_page is not None and trace.verified_source_page != original
        if trace.status == "missing":
            logger.warning("Non-verbatim requirement at index %d; human review required", index)
        traced.append(requirement.model_copy(deep=True, update={
            "source_page": trace.verified_source_page or original,
            "source_trace": trace,
            "needs_review": requirement.needs_review or trace.status != "matched" or corrected,
        }))
    return RequirementExtractionResult(requirements=traced)


def reconcile_source_pages(raw_json: str, pages: list[dict], *, include_trace: bool = False) -> str:
    """Recover valid model page fields before strict US-03 validation.

    The legacy two-argument API is preserved. The extractor requests traces;
    any model-supplied trace is discarded and recomputed from supplied pages.
    Invalid fields remain invalid for Pydantic to reject.
    """
    if not isinstance(raw_json, str):
        return raw_json
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError:
        return raw_json
    if not isinstance(payload, dict) or not isinstance(payload.get("requirements"), list):
        return raw_json

    indexed = _page_index(pages)
    changed = False
    for index, item in enumerate(payload["requirements"]):
        if not isinstance(item, dict):
            continue
        if include_trace and "source_trace" in item:
            del item["source_trace"]
            changed = True
        reported, quote, review = item.get("source_page"), item.get("requirement_text"), item.get("needs_review")
        if (type(reported) is not int or reported < 1 or not isinstance(quote, str)
                or not quote.strip() or type(review) is not bool):
            continue
        trace = _trace(quote, reported, indexed)
        verified = trace.verified_source_page
        if verified is not None and reported != verified:
            logger.warning(
                "Corrected LLM source page at index %d: %d -> %d "
                "(unique normalized quote match; human review required)", index, reported, verified,
            )
            item["source_page"] = verified
            item["needs_review"] = True
            changed = True
        if include_trace:
            item["source_trace"] = trace.model_dump(mode="json")
            item["needs_review"] = item["needs_review"] or trace.status != "matched"
            changed = True
    return json.dumps(payload, ensure_ascii=False) if changed else raw_json
