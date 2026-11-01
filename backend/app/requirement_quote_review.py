"""Conservative lexical source-quote checks for an MVP extraction pipeline.

This is NOT semantic verification or US-05 traceability. A requirement whose
full text cannot be found contiguously on its assigned input page is flagged
for human review, without inventing new text, sources or categories.
"""

import logging

from app.requirement_schema import RequirementExtractionResult

logger = logging.getLogger(__name__)


def flag_unmatched_source_quotes(
    result: RequirementExtractionResult,
    pages: list[dict],
) -> RequirementExtractionResult:
    """Flag non-verbatim requirements while preserving original records."""
    page_texts = {
        page["page_number"]: " ".join(page["text"].split())
        for page in pages
    }
    reviewed = []
    for index, requirement in enumerate(result.requirements):
        quote = " ".join(requirement.requirement_text.split())
        source = page_texts.get(requirement.source_page, "")
        unmatched = quote not in source
        if unmatched:
            logger.warning(
                "Non-verbatim requirement at index %d, page %d; "
                "human review required (lexical check only)",
                index,
                requirement.source_page,
            )
        reviewed.append(
            requirement.model_copy(
                update={"needs_review": requirement.needs_review or unmatched}
            )
        )
    return RequirementExtractionResult(requirements=reviewed)
