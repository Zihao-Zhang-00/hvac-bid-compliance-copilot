"""Evaluation remains deterministic and requires no live model calls."""

from app.requirement_evaluation import evaluate_extraction
from app.requirement_schema import RequirementExtractionResult, TenderRequirement


def req(text="Valid HVAC license required.", page=1, **changes):
    data = {
        "requirement_text": text,
        "category": "qualification",
        "mandatory": True,
        "source_page": page,
        "evidence_needed": "Valid contractor license",
        "needs_review": False,
    }
    data.update(changes)
    return TenderRequirement.model_validate(data)


def evaluate(predicted, gold, pages=None):
    if pages is None:
        pages = [{"page_number": 1, "text": "Valid HVAC license required."}]
    return evaluate_extraction(
        RequirementExtractionResult(requirements=predicted),
        RequirementExtractionResult(requirements=gold),
        pages,
    )


def test_perfect_match():
    item = req()
    report = evaluate([item], [item])
    assert report["counts"]["matched"] == 1
    assert (report["precision"], report["recall"], report["f1"]) == (1.0, 1.0, 1.0)
    assert report["field_accuracy"]["category"]["accuracy"] == 1.0
    assert report["unsupported_source_quotes"] == []


def test_missing_requirement():
    report = evaluate([], [req()])
    assert report["counts"]["false_negative"] == 1
    assert report["recall"] == 0.0
    assert report["missing"][0]["source_page"] == 1
    assert report["field_accuracy"]["category"]["accuracy"] is None


def test_hallucinated_clause_is_unexpected_and_unsupported():
    report = evaluate([req(text="Imaginary tender requirement.")], [req()])
    assert report["counts"]["false_positive"] == 1
    assert report["counts"]["false_negative"] == 1
    assert report["precision"] == 0.0
    assert len(report["unsupported_source_quotes"]) == 1


def test_wrong_source_page_is_unmatched_and_not_supported():
    report = evaluate(
        [req(page=2)], [req()],
        pages=[
            {"page_number": 1, "text": "Valid HVAC license required."},
            {"page_number": 2, "text": "A project introduction."},
        ],
    )
    assert report["counts"]["matched"] == 0
    assert len(report["unsupported_source_quotes"]) == 1


def test_field_mismatches_and_missing_evidence_are_reported():
    gold = req()
    wrong = req(category="documentation", mandatory=False, needs_review=True, evidence_needed=None)
    report = evaluate([wrong], [gold])
    assert report["counts"]["matched"] == 1
    for field in ("category", "mandatory", "needs_review"):
        assert report["field_accuracy"][field]["correct"] == 0
        assert len(report["field_mismatches"][field]) == 1
    assert len(report["missing_evidence_suggestions"]) == 1


def test_missing_one_and_extra_one_give_half_precision_recall():
    a = req()
    b = req("Signed form required.")
    c = req("Technical datasheet required.")
    report = evaluate([a, c], [a, b])
    assert (report["precision"], report["recall"], report["f1"]) == (0.5, 0.5, 0.5)


def test_quote_whitespace_normalization():
    report = evaluate(
        [req()], [req()],
        pages=[{"page_number": 1, "text": "Valid  HVAC\nlicense required."}],
    )
    assert report["unsupported_source_quotes"] == []


def test_unexpected_clause_in_source_is_not_necessarily_unsupported():
    report = evaluate(
        [req("A project introduction.")], [],
        pages=[{"page_number": 1, "text": "A project introduction."}],
    )
    assert report["counts"]["false_positive"] == 1
    assert report["unsupported_source_quotes"] == []


def test_duplicate_predictions_are_counted_not_silently_ignored():
    item = req()
    report = evaluate([item, item], [item])
    assert report["counts"]["false_positive"] == 1
    assert report["precision"] == 0.5


def test_both_empty_is_an_explicit_vacuous_perfect_result():
    report = evaluate([], [])
    assert report["counts"]["matched"] == 0
    assert (report["precision"], report["recall"], report["f1"]) == (1.0, 1.0, 1.0)
    assert report["field_accuracy"]["category"]["accuracy"] is None
    assert report["missing"] == report["unexpected"] == []


def test_mocked_pipeline_evaluates_annotated_tender_fixture():
    """No network call: a fake completion supplies the annotated records."""
    import json
    from pathlib import Path

    from app.requirement_extractor import extract_requirements

    fixture_dir = Path(__file__).parent / "fixtures"
    tender = json.loads((fixture_dir / "sample_tender_pages.json").read_text(encoding="utf-8"))
    expected_json = (fixture_dir / "expected_requirements.json").read_text(encoding="utf-8")
    expected = RequirementExtractionResult.model_validate_json(expected_json)

    class FakeLLM:
        def complete(self, system_prompt, user_prompt):
            assert "requirements" in system_prompt
            assert json.loads(user_prompt)["pages"] == tender["pages"]
            return expected_json

    actual = extract_requirements(tender["pages"], FakeLLM())
    evaluation = evaluate_extraction(actual, expected, tender["pages"])
    assert evaluation["counts"]["matched"] == 10
    assert evaluation["f1"] == 1.0
    assert evaluation["field_accuracy"]["mandatory"]["correct"] == 10
    assert evaluation["field_accuracy"]["needs_review"]["correct"] == 10
    assert evaluation["unsupported_source_quotes"] == []