"""Bounded orchestration and response models for tender analysis."""

from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.document_structure import build_extraction_view
from app.requirement_extractor import CompletionClient, extract_requirements
from app.requirement_recall import find_uncovered_critical_passages
from app.requirement_relevance import (
    ExcludedCandidate,
    NoticeCandidate,
    ReviewQueueItem,
    partition_requirements,
)
from app.requirement_schema import (
    RequirementCategory,
    RequirementExtractionResult,
    TenderRequirement,
)
from app.tender_date_conflicts import DateConflict, detect_date_conflicts


MAX_ANALYSIS_PAGES = 50
MAX_ANALYSIS_TEXT_CHARS = 100_000
UNVERIFIED_REASON = "OCR or manual review required"


class AnalysisInputError(ValueError):
    """Actionable request error raised before any model call."""

    def __init__(self, detail: str, status_code: int = 422):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class UnverifiedPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int
    status: Literal["unverified"] = "unverified"
    reason: Literal["OCR or manual review required"] = UNVERIFIED_REASON


class DocumentCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["complete", "incomplete"]
    full_document_requested: bool
    unverified_pages: list[UnverifiedPage]
    unanalyzed_pages: list[int]
    warnings: list[str]


class AnalysisSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_count: int
    needs_review_count: int
    review_queue_count: int
    notice_count: int
    excluded_count: int
    date_conflict_count: int
    mandatory_count: int
    optional_count: int
    unknown_mandatory_count: int
    category_counts: dict[str, int]
    source_trace_status_counts: dict[str, int]
    input_text_characters: int


class TenderAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str
    total_page_count: int
    requested_pages: list[int]
    analyzed_pages: list[int]
    pages_with_extractable_text: list[int]
    pages_without_extractable_text: list[int]
    coverage: DocumentCoverage
    requirements: list[TenderRequirement]
    review_queue: list[ReviewQueueItem]
    notices: list[NoticeCandidate]
    excluded: list[ExcludedCandidate]
    date_conflicts: list[DateConflict]
    summary: AnalysisSummary


def _requested_pages(
    total_page_count: int,
    page_start: int | None,
    page_end: int | None,
) -> list[int]:
    if (page_start is None) != (page_end is None):
        raise AnalysisInputError(
            "page_start and page_end must be provided together"
        )

    if page_start is None:
        if total_page_count > MAX_ANALYSIS_PAGES:
            raise AnalysisInputError(
                f"Document has {total_page_count} pages; select a range of at most "
                f"{MAX_ANALYSIS_PAGES} pages"
            )
        return list(range(1, total_page_count + 1))

    if page_start < 1 or page_end < 1:
        raise AnalysisInputError("Page range values must be positive")
    if page_start > page_end:
        raise AnalysisInputError("page_start must not exceed page_end")
    if page_end > total_page_count:
        raise AnalysisInputError(
            f"page_end exceeds the document page count ({total_page_count})"
        )
    if page_end - page_start + 1 > MAX_ANALYSIS_PAGES:
        raise AnalysisInputError(
            f"Select at most {MAX_ANALYSIS_PAGES} pages per analysis"
        )
    return list(range(page_start, page_end + 1))


def _summary(
    requirements: list[TenderRequirement],
    review_queue: list[ReviewQueueItem],
    notices: list[NoticeCandidate],
    excluded: list[ExcludedCandidate],
    date_conflicts: list[DateConflict],
    input_text_characters: int,
) -> AnalysisSummary:
    categories = Counter(requirement.category.value for requirement in requirements)
    retained = requirements + [item.requirement for item in review_queue]
    trace_values = [item.source_trace for item in retained]
    trace_values.extend(item.source_trace for item in notices)
    trace_values.extend(item.source_trace for item in excluded)
    traces = Counter(
        trace.status if trace is not None else "unverified"
        for trace in trace_values
    )
    return AnalysisSummary(
        requirement_count=len(requirements),
        needs_review_count=len(review_queue),
        review_queue_count=len(review_queue),
        notice_count=len(notices),
        excluded_count=len(excluded),
        date_conflict_count=len(date_conflicts),
        mandatory_count=sum(item.mandatory is True for item in requirements),
        optional_count=sum(item.mandatory is False for item in requirements),
        unknown_mandatory_count=sum(item.mandatory is None for item in requirements),
        category_counts={
            category.value: categories.get(category.value, 0)
            for category in RequirementCategory
        },
        source_trace_status_counts=dict(sorted(traces.items())),
        input_text_characters=input_text_characters,
    )


def analyze_parsed_tender(
    *,
    filename: str,
    parsed: dict,
    client: CompletionClient,
    page_start: int | None = None,
    page_end: int | None = None,
) -> TenderAnalysisResponse:
    """Analyze a validated parser result without obscuring missing coverage."""

    total_page_count = parsed["page_count"]
    pages = parsed["pages"]
    requested_pages = _requested_pages(total_page_count, page_start, page_end)
    requested_set = set(requested_pages)

    pages_with_text = [
        page["page_number"] for page in pages if page["text"].strip()
    ]
    pages_without_text = [
        page["page_number"] for page in pages if not page["text"].strip()
    ]
    selected_pages = [
        page
        for page in pages
        if page["page_number"] in requested_set and page["text"].strip()
    ]
    analyzed_pages = [page["page_number"] for page in selected_pages]

    if not selected_pages:
        raise AnalysisInputError(
            "Selected pages contain no extractable text; OCR or manual review is "
            "required, or choose a different page range"
        )

    input_text_characters = sum(len(page["text"]) for page in selected_pages)
    if input_text_characters > MAX_ANALYSIS_TEXT_CHARS:
        raise AnalysisInputError(
            f"Selected pages contain {input_text_characters} text characters, "
            f"exceeding the {MAX_ANALYSIS_TEXT_CHARS} character model-call limit; "
            "choose a smaller page range",
            status_code=413,
        )

    extraction_pages = build_extraction_view(selected_pages)
    if any(page["text"].strip() for page in extraction_pages):
        extraction = extract_requirements(
            extraction_pages,
            client,
            source_pages=selected_pages,
        )
    else:
        extraction = RequirementExtractionResult(requirements=[])
    extraction.requirements.extend(
        find_uncovered_critical_passages(selected_pages, extraction)
    )
    relevance = partition_requirements(extraction)
    date_conflicts = detect_date_conflicts(selected_pages)
    all_pages = list(range(1, total_page_count + 1))
    full_document_requested = requested_pages == all_pages
    unanalyzed_pages = [page for page in all_pages if page not in analyzed_pages]
    complete = full_document_requested and not pages_without_text
    warnings: list[str] = []

    if not full_document_requested:
        warnings.append(
            "Only selected pages were analyzed; full-document analysis has not "
            "been completed."
        )
    if pages_without_text:
        page_list = ", ".join(str(page) for page in pages_without_text)
        warnings.append(
            f"PDF page(s) {page_list} contain no extractable text and are "
            f"unverified; {UNVERIFIED_REASON}."
        )

    return TenderAnalysisResponse(
        filename=filename,
        total_page_count=total_page_count,
        requested_pages=requested_pages,
        analyzed_pages=analyzed_pages,
        pages_with_extractable_text=pages_with_text,
        pages_without_extractable_text=pages_without_text,
        coverage=DocumentCoverage(
            status="complete" if complete else "incomplete",
            full_document_requested=full_document_requested,
            unverified_pages=[
                UnverifiedPage(page_number=page) for page in pages_without_text
            ],
            unanalyzed_pages=unanalyzed_pages,
            warnings=warnings,
        ),
        requirements=relevance.requirements,
        review_queue=relevance.review_queue,
        notices=relevance.notices,
        excluded=relevance.excluded,
        date_conflicts=date_conflicts,
        summary=_summary(
            relevance.requirements,
            relevance.review_queue,
            relevance.notices,
            relevance.excluded,
            date_conflicts,
            input_text_characters,
        ),
    )
