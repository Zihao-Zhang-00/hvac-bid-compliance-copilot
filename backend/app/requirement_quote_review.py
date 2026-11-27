"""Backward-compatible quote review entry point using US-05 provenance."""

from app.requirement_provenance import trace_source_pages
from app.requirement_schema import RequirementExtractionResult


def flag_unmatched_source_quotes(
    result: RequirementExtractionResult,
    pages: list[dict],
) -> RequirementExtractionResult:
    """Trace all supplied pages and preserve any existing review decision."""
    return trace_source_pages(result, pages)
