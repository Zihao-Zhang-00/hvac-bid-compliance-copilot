import json
import os
import time
from pathlib import Path

from app.llm_client import OpenAICompatibleLLM
from app.requirement_extractor import extract_requirements

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def main():
    tender = json.loads(
        (FIXTURES / "sample_tender_pages.json").read_text(
            encoding="utf-8"
        )
    )
    expected = json.loads(
        (FIXTURES / "expected_requirements.json").read_text(
            encoding="utf-8"
        )
    )

    client = OpenAICompatibleLLM(
        endpoint=os.environ["LLM_API_URL"],
        api_key=os.environ["LLM_API_KEY"],
        model=os.environ["LLM_MODEL"],
    )

    print(f"Model: {os.environ['LLM_MODEL']}", flush=True)
    print(f"Input pages: {len(tender['pages'])}", flush=True)
    print("Calling Ollama...", flush=True)

    start = time.perf_counter()
    result = extract_requirements(
        pages=tender["pages"],
        client=client,
    )
    elapsed = time.perf_counter() - start

    expected_by_key = {
        (r["source_page"], r["requirement_text"].strip()): r
        for r in expected["requirements"]
    }
    actual_by_key = {
        (r.source_page, r.requirement_text.strip()): r
        for r in result.requirements
    }

    expected_keys = set(expected_by_key)
    actual_keys = set(actual_by_key)
    matched_keys = expected_keys & actual_keys

    print("\n=== Extraction Summary ===")
    print(f"Elapsed time: {elapsed:.2f}s")
    print(f"Expected requirements: {len(expected_keys)}")
    print(f"Extracted requirements: {len(result.requirements)}")
    print(f"Exact text + page matches: {len(matched_keys)}")
    print(f"Missing matches: {len(expected_keys - actual_keys)}")
    print(f"Unexpected matches: {len(actual_keys - expected_keys)}")

    category_matches = sum(
        actual_by_key[key].category.value
        == expected_by_key[key]["category"]
        for key in matched_keys
    )
    mandatory_matches = sum(
        actual_by_key[key].mandatory
        == expected_by_key[key]["mandatory"]
        for key in matched_keys
    )

    print("\n=== Field Evaluation (Matched Clauses Only) ===")
    print(f"Category matches: {category_matches}/{len(matched_keys)}")
    print(f"Mandatory matches: {mandatory_matches}/{len(matched_keys)}")

    print("\n=== Category Mismatches ===")
    for key in sorted(matched_keys):
        actual = actual_by_key[key]
        expected_item = expected_by_key[key]
        if actual.category.value != expected_item["category"]:
            print(f"Page {key[0]}: {key[1]}")
            print(f"  Expected: {expected_item['category']}")
            print(f"  Actual:   {actual.category.value}")

    print("\n=== Missing Evidence Suggestions ===")
    for key in sorted(matched_keys):
        actual = actual_by_key[key]
        expected_item = expected_by_key[key]
        if expected_item["evidence_needed"] and not actual.evidence_needed:
            print(f"Page {key[0]}: {key[1]}")

    print("\n=== Missing or Unexpected Requirements ===")
    for key in sorted(expected_keys - actual_keys):
        print(f"MISSING Page {key[0]}: {key[1]}")
    for key in sorted(actual_keys - expected_keys):
        print(f"UNEXPECTED Page {key[0]}: {key[1]}")

    print("\n=== Complete Extracted JSON ===")
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
