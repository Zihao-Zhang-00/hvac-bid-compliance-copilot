"""Deterministic evaluation for page-linked requirement extraction."""

from collections import Counter

from app.requirement_schema import RequirementExtractionResult


def _key(requirement):
    return (requirement.source_page, requirement.requirement_text.strip())


def _rows(counts):
    return [
        {"source_page": page, "requirement_text": text}
        for (page, text), count in sorted(counts.items())
        for _ in range(count)
    ]


def evaluate_extraction(
    actual: RequirementExtractionResult,
    expected: RequirementExtractionResult,
    pages: list[dict],
) -> dict:
    """Evaluate exact clause+page matches and matched-record fields.

    This is lexical evaluation, not semantic equivalence or verified provenance.
    Input records must already conform to the requirement schema.
    """
    actual_counts = Counter(_key(item) for item in actual.requirements)
    expected_counts = Counter(_key(item) for item in expected.requirements)
    matched = actual_counts & expected_counts
    unexpected = actual_counts - expected_counts
    missing = expected_counts - actual_counts
    matched_keys = list(matched.elements())

    tp = len(matched_keys)
    fp = sum(unexpected.values())
    fn = sum(missing.values())
    if not actual.requirements and not expected.requirements:
        precision = recall = f1 = 1.0
    else:
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    actual_by_key = {_key(item): item for item in actual.requirements}
    expected_by_key = {_key(item): item for item in expected.requirements}
    field_accuracy = {}
    field_mismatches = {}
    for field in ("category", "mandatory", "needs_review"):
        errors = []
        for key in matched_keys:
            actual_value = getattr(actual_by_key[key], field)
            expected_value = getattr(expected_by_key[key], field)
            if actual_value != expected_value:
                errors.append({
                    "source_page": key[0],
                    "requirement_text": key[1],
                    "expected": expected_value.value if field == "category" else expected_value,
                    "actual": actual_value.value if field == "category" else actual_value,
                })
        correct = tp - len(errors)
        field_accuracy[field] = {
            "correct": correct,
            "total": tp,
            "accuracy": round(correct / tp, 4) if tp else None,
        }
        field_mismatches[field] = errors

    missing_evidence = [
        {"source_page": key[0], "requirement_text": key[1]}
        for key in matched_keys
        if expected_by_key[key].evidence_needed is not None
        and actual_by_key[key].evidence_needed is None
    ]

    page_text_by_number = {
        page["page_number"]: " ".join(page["text"].split())
        for page in pages
    }
    unsupported_quotes = [
        {"source_page": item.source_page, "requirement_text": item.requirement_text}
        for item in actual.requirements
        if " ".join(item.requirement_text.split())
        not in page_text_by_number.get(item.source_page, "")
    ]

    return {
        "counts": {
            "expected": len(expected.requirements),
            "predicted": len(actual.requirements),
            "matched": tp,
            "false_positive": fp,
            "false_negative": fn,
        },
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "field_accuracy": field_accuracy,
        "missing": _rows(missing),
        "unexpected": _rows(unexpected),
        "field_mismatches": field_mismatches,
        "missing_evidence_suggestions": missing_evidence,
        "unsupported_source_quotes": unsupported_quotes,
    }
