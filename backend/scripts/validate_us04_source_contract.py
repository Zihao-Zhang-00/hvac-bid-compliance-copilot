"""Read-only contract check against an external US-04 classifier checkout.

No classifier code is copied or merged. Run from backend with:
python -m scripts.validate_us04_source_contract --classifier /path/to/requirement_classifier.py
"""

import argparse
import importlib.util
from pathlib import Path

from app.requirement_provenance import trace_source_pages
from app.requirement_schema import RequirementExtractionResult, TenderRequirement


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--classifier", required=True, type=Path)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("external_us04_classifier", args.classifier)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    quote = "All proposed units must use R-32 refrigerant."
    count = 0
    for pages in [
        [{"page_number": 1, "text": quote}],
        [{"page_number": 2, "text": quote}],
        [{"page_number": 1, "text": "Unrelated source"}],
        [{"page_number": n, "text": quote} for n in [1, 2]],
    ]:
        for review in [False, True]:
            original = RequirementExtractionResult(requirements=[TenderRequirement(
                requirement_text=quote, category="documentation", mandatory=True,
                source_page=1, evidence_needed="Datasheet", needs_review=review,
            )])
            before = original.model_dump()
            classified = module.classify_requirements(original)
            # US-05 can consume the US-04 output without changing classification.
            traced = trace_source_pages(classified, pages)
            assert traced.requirements[0].category == classified.requirements[0].category
            assert classified.requirements[0].category.value == "technical"
            assert original.model_dump() == before
            # Current PR puts classification last; provenance survives that order too.
            source_first = trace_source_pages(original, pages)
            source_before = source_first.model_dump()
            final = module.classify_requirements(source_first)
            assert final == traced
            assert source_first.model_dump() == source_before
            assert final.requirements[0].source_trace == source_first.requirements[0].source_trace
            assert module.classify_requirements(final) == final
            assert trace_source_pages(final, pages) == final
            count += 1
    print(f"US-04 / US-05 contract: {count} cases passed (both stage orders).")


if __name__ == "__main__":
    main()
