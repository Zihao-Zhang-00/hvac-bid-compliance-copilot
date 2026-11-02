"""Run a live-model extraction evaluation against synthetic ground truth."""

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from app.llm_client import OpenAICompatibleLLM
from app.requirement_evaluation import evaluate_extraction
from app.requirement_extractor import SYSTEM_PROMPT, extract_requirements
from app.requirement_schema import RequirementExtractionResult

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/hvac_requirement_evaluation.json"),
        help="Path for a JSON report (default: /tmp/hvac_requirement_evaluation.json)",
    )
    args = parser.parse_args()

    tender = json.loads(
        (FIXTURES / "sample_tender_pages.json").read_text(encoding="utf-8")
    )
    expected = RequirementExtractionResult.model_validate_json(
        (FIXTURES / "expected_requirements.json").read_text(encoding="utf-8")
    )
    model = os.environ["LLM_MODEL"]
    client = OpenAICompatibleLLM(
        endpoint=os.environ["LLM_API_URL"],
        api_key=os.environ["LLM_API_KEY"],
        model=model,
    )

    print(f"Calling model: {model}", flush=True)
    started = time.perf_counter()
    actual = extract_requirements(tender["pages"], client)
    elapsed = time.perf_counter() - started
    evaluation = evaluate_extraction(actual, expected, tender["pages"])

    counts = evaluation["counts"]
    print("\n=== Clause Extraction Evaluation ===")
    print(f"Expected: {counts['expected']}, Predicted: {counts['predicted']}")
    print(f"TP: {counts['matched']}, FP: {counts['false_positive']}, FN: {counts['false_negative']}")
    print(f"Precision: {evaluation['precision']:.2%}")
    print(f"Recall:    {evaluation['recall']:.2%}")
    print(f"F1:        {evaluation['f1']:.2%}")

    print("\n=== Field Accuracy (Exact-Matched Clauses Only) ===")
    for field, stat in evaluation["field_accuracy"].items():
        percent = f"{stat['accuracy']:.2%}" if stat["accuracy"] is not None else "N/A"
        print(f"{field}: {stat['correct']}/{stat['total']} ({percent})")

    print("\n=== Error Counts ===")
    for field in (
        "missing", "unexpected", "missing_evidence_suggestions",
        "unsupported_source_quotes",
    ):
        print(f"{field}: {len(evaluation[field])}")
    for field, errors in evaluation["field_mismatches"].items():
        for error in errors:
            print(f"{field} mismatch, page {error['source_page']}: "
                  f"expected={error['expected']!r}, actual={error['actual']!r}")

    artifact = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "document_id": tender.get("document_id"),
        "model": model,
        "prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
        "elapsed_seconds": round(elapsed, 3),
        "evaluation": evaluation,
        "extracted_requirements": actual.model_dump(mode="json"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\nReport saved to: {args.output}")
    print("Note: exact synthetic-fixture matching is not a production accuracy estimate.")


if __name__ == "__main__":
    main()
