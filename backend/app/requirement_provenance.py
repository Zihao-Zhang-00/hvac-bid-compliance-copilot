"""Conservatively reconcile LLM page references using exact supplied text.

This only corrects a positive integer page reference if the full requirement
quote occurs on exactly one *provided* page. Corrections are flagged for
human review and logged. Missing/invalid input remains invalid.
"""

import json
import logging

logger = logging.getLogger(__name__)


def reconcile_source_pages(raw_json: str, pages: list[dict]) -> str:
    """Return updated JSON if unique verbatim source evidence proves a page."""
    if not isinstance(raw_json, str):
        return raw_json

    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError:
        return raw_json

    if not isinstance(payload, dict):
        return raw_json
    requirements = payload.get("requirements")
    if not isinstance(requirements, list):
        return raw_json

    page_texts = {
        page["page_number"]: " ".join(page["text"].split())
        for page in pages
    }

    changed = False
    for index, item in enumerate(requirements):
        if not isinstance(item, dict):
            continue

        reported = item.get("source_page")
        quote = item.get("requirement_text")
        review = item.get("needs_review")

        # Leave invalid fields to strict Pydantic validation.
        if (
            type(reported) is not int
            or reported < 1
            or not isinstance(quote, str)
            or not quote.strip()
            or type(review) is not bool
        ):
            continue

        exact_quote = " ".join(quote.split())
        matches = [
            number for number, source in page_texts.items()
            if exact_quote in source
        ]
        if len(matches) != 1 or reported == matches[0]:
            continue

        verified_page = matches[0]
        logger.warning(
            "Corrected LLM source page at index %d: %d -> %d "
            "(unique exact quote match; human review required)",
            index,
            reported,
            verified_page,
        )
        item["source_page"] = verified_page
        item["needs_review"] = True
        changed = True

    return json.dumps(payload, ensure_ascii=False) if changed else raw_json
