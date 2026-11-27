import csv
import json

import pytest

from app.relevance_evaluation import evaluate_predictions, load_ground_truth, main


FIELDS = [
    "requirement_id",
    "document_id",
    "exact_quote",
    "source_page",
    "relevance_label",
    "obligation_status",
    "category",
    "evidence_required",
    "reviewer_notes",
]


def write_labels(path, rows):
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def label(identifier, quote, relevance, obligation, page=1):
    return {
        "requirement_id": identifier,
        "document_id": "doc-1",
        "exact_quote": quote,
        "source_page": page,
        "relevance_label": relevance,
        "obligation_status": obligation,
        "category": "technical",
        "evidence_required": "",
        "reviewer_notes": "",
    }


def prediction(quote, *, page=1, status="matched", mandatory=True):
    return {
        "requirement_text": quote,
        "mandatory": mandatory,
        "source_page": page,
        "source_trace": {
            "status": status,
            "verified_source_page": page if status == "matched" else None,
        },
    }


def test_exact_normalized_matching_and_metrics():
    truth = [
        label("r1", "Submit equipment data.", "actionable", "mandatory"),
        label("r2", "Attend the meeting.", "actionable", "optional", page=2),
        label("r3", "The building was built in 1998.", "excluded", "uncertain"),
        label("r4", "Testing may be required.", "review_required", "conditional"),
    ]
    predictions = {
        "requirements": [
            prediction("  SUBMIT   equipment data. "),
            prediction("The building was built in 1998.", mandatory=False),
        ],
        "review_queue": [{
            "requirement": prediction("Testing may be required.", mandatory=None)
        }],
        "excluded": [prediction(
            "Attend the meeting.", page=2, status="missing", mandatory=False
        )],
    }

    metrics = evaluate_predictions(truth, predictions, "doc-1")

    assert metrics["actionable_precision"] == 0.5
    assert metrics["actionable_recall"] == 0.5
    assert metrics["mandatory_retention_recall"] == 1.0
    assert metrics["mandatory_classification_recall"] == 1.0
    assert metrics["true_positive_count"] == 1
    assert metrics["false_positive_count"] == 1
    assert metrics["false_negative_count"] == 1
    assert metrics["review_queue_count"] == 1
    assert metrics["unmatched_source_count"] == 1
    assert metrics["matched_prediction_count"] == 4


def test_mandatory_retention_and_classification_are_distinct():
    truth = [
        label("r1", "Submit data.", "actionable", "mandatory"),
        label("r2", "Provide schedule.", "actionable", "mandatory"),
        label("r3", "Testing applies.", "review_required", "mandatory"),
    ]
    predictions = {
        "requirements": [
            prediction("Submit data.", mandatory=True),
            prediction("Provide schedule.", mandatory=False),
        ],
        "review_queue": [{
            "requirement": prediction("Testing applies.", mandatory=None)
        }],
        "excluded": [],
    }

    metrics = evaluate_predictions(truth, predictions, "doc-1")

    assert metrics["mandatory_retention_recall"] == 1.0
    assert metrics["mandatory_classification_recall"] == pytest.approx(1 / 3)


def test_notice_predictions_are_counted_without_becoming_actionable():
    truth = [label("n1", "Optional pre-bid meeting.", "notice", "optional")]
    predictions = {
        "requirements": [],
        "review_queue": [],
        "notices": [prediction("Optional pre-bid meeting.", mandatory=False)],
        "excluded": [],
    }

    metrics = evaluate_predictions(truth, predictions, "doc-1")

    assert metrics["notice_prediction_count"] == 1
    assert metrics["matched_prediction_count"] == 1
    assert metrics["actionable_precision"] is None


def test_load_ground_truth_rejects_duplicates_and_invalid_labels(tmp_path):
    labels = tmp_path / "labels.csv"
    duplicate = label("r1", "Same quote", "actionable", "mandatory")
    write_labels(labels, [duplicate, {**duplicate, "requirement_id": "r2"}])
    with pytest.raises(ValueError, match="duplicate"):
        load_ground_truth(labels, "doc-1")

    write_labels(labels, [{**duplicate, "relevance_label": "maybe"}])
    with pytest.raises(ValueError, match="Invalid relevance_label"):
        load_ground_truth(labels, "doc-1")


def test_cli_writes_metrics_without_fabricating_labels(tmp_path, capsys):
    labels = tmp_path / "labels.csv"
    predictions = tmp_path / "predictions.json"
    output = tmp_path / "metrics.json"
    write_labels(labels, [label("r1", "Submit data.", "actionable", "mandatory")])
    predictions.write_text(
        json.dumps({"requirements": [prediction("Submit data.")]}),
        encoding="utf-8",
    )

    assert main([
        "--ground-truth", str(labels),
        "--predictions", str(predictions),
        "--document-id", "doc-1",
        "--output", str(output),
    ]) == 0

    metrics = json.loads(output.read_text(encoding="utf-8"))
    assert metrics["actionable_precision"] == 1.0
    assert json.loads(capsys.readouterr().out) == metrics
