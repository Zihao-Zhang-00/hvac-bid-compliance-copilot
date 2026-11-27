"""Offline exact-match evaluation for manually reviewed relevance labels."""

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from app.requirement_schema import RequirementCategory


RELEVANCE_LABELS = {"actionable", "excluded", "review_required"}
OBLIGATION_STATUSES = {"mandatory", "optional", "conditional", "uncertain"}


def _normalize_quote(text: str) -> str:
    return " ".join(text.casefold().split())


def _key(document_id: str, source_page: int, quote: str) -> tuple[str, int, str]:
    return document_id, source_page, _normalize_quote(quote)


def _prediction_requirement(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("requirement", item)


def _prediction_key(
    document_id: str,
    item: dict[str, Any],
) -> tuple[str, int, str]:
    requirement = _prediction_requirement(item)
    trace = requirement.get("source_trace") or {}
    page = trace.get("verified_source_page") or requirement["source_page"]
    return _key(document_id, int(page), requirement["requirement_text"])


def load_ground_truth(path: Path, document_id: str) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as source:
        rows = [
            row for row in csv.DictReader(source)
            if row.get("document_id", "").strip() == document_id
        ]
    if not rows:
        raise ValueError(f"No ground-truth rows found for document ID {document_id}")

    required = {
        "requirement_id",
        "document_id",
        "exact_quote",
        "source_page",
        "relevance_label",
        "obligation_status",
        "category",
    }
    for row_number, row in enumerate(rows, start=2):
        missing = sorted(name for name in required if not row.get(name, "").strip())
        if missing:
            raise ValueError(
                f"Ground-truth row {row_number} is missing: {', '.join(missing)}"
            )
        if row["relevance_label"] not in RELEVANCE_LABELS:
            raise ValueError(f"Invalid relevance_label on row {row_number}")
        if row["obligation_status"] not in OBLIGATION_STATUSES:
            raise ValueError(f"Invalid obligation_status on row {row_number}")
        if row["category"] not in {category.value for category in RequirementCategory}:
            raise ValueError(f"Invalid category on row {row_number}")
        try:
            row["source_page"] = int(row["source_page"])
        except ValueError as exc:
            raise ValueError(f"Invalid source_page on row {row_number}") from exc
        if row["source_page"] < 1:
            raise ValueError(f"Invalid source_page on row {row_number}")

    keys = [_key(row["document_id"], row["source_page"], row["exact_quote"]) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("Ground truth contains duplicate document/page/quote keys")
    return rows


def evaluate_predictions(
    ground_truth: list[dict[str, Any]],
    predictions: dict[str, Any],
    document_id: str,
) -> dict[str, Any]:
    """Evaluate exact normalized quote + source-page matches only."""

    actionable_items = predictions.get("requirements", [])
    review_items = predictions.get("review_queue", [])
    excluded_items = predictions.get("excluded", [])

    actionable_keys = {
        _prediction_key(document_id, item) for item in actionable_items
    }
    review_keys = {_prediction_key(document_id, item) for item in review_items}
    excluded_keys = {_prediction_key(document_id, item) for item in excluded_items}
    retained_keys = actionable_keys | review_keys
    mandatory_true_keys = {
        _prediction_key(document_id, item)
        for item in actionable_items + review_items
        if _prediction_requirement(item).get("mandatory") is True
    }

    truth_actionable = {
        _key(row["document_id"], row["source_page"], row["exact_quote"])
        for row in ground_truth
        if row["relevance_label"] == "actionable"
    }
    truth_mandatory = {
        _key(row["document_id"], row["source_page"], row["exact_quote"])
        for row in ground_truth
        if row["obligation_status"] == "mandatory"
    }

    true_positives = len(actionable_keys & truth_actionable)
    false_positives = len(actionable_keys - truth_actionable)
    false_negatives = len(truth_actionable - actionable_keys)
    precision_denominator = true_positives + false_positives
    recall_denominator = true_positives + false_negatives
    mandatory_matches = len(truth_mandatory & retained_keys)
    mandatory_classification_matches = len(truth_mandatory & mandatory_true_keys)

    all_items = actionable_items + review_items + excluded_items
    unmatched_source_count = 0
    for item in all_items:
        requirement = _prediction_requirement(item)
        trace = requirement.get("source_trace") or item.get("source_trace") or {}
        if trace.get("status") != "matched":
            unmatched_source_count += 1

    return {
        "matching_rule": "document_id + source_page + casefolded whitespace-normalized exact quote",
        "ground_truth_count": len(ground_truth),
        "actionable_precision": (
            true_positives / precision_denominator if precision_denominator else None
        ),
        "actionable_recall": (
            true_positives / recall_denominator if recall_denominator else None
        ),
        "mandatory_retention_recall": (
            mandatory_matches / len(truth_mandatory) if truth_mandatory else None
        ),
        "mandatory_classification_recall": (
            mandatory_classification_matches / len(truth_mandatory)
            if truth_mandatory
            else None
        ),
        "true_positive_count": true_positives,
        "false_positive_count": false_positives,
        "false_negative_count": false_negatives,
        "review_queue_count": len(review_items),
        "excluded_prediction_count": len(excluded_items),
        "unmatched_source_count": unmatched_source_count,
        "matched_prediction_count": len(
            (actionable_keys | review_keys | excluded_keys)
            & {
                _key(row["document_id"], row["source_page"], row["exact_quote"])
                for row in ground_truth
            }
        ),
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate one tender analysis JSON against reviewed CSV labels."
    )
    parser.add_argument("--ground-truth", required=True, type=Path)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    ground_truth = load_ground_truth(args.ground_truth, args.document_id)
    predictions = json.loads(args.predictions.read_text(encoding="utf-8"))
    metrics = evaluate_predictions(ground_truth, predictions, args.document_id)
    output = json.dumps(metrics, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
