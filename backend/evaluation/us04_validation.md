# US-04 Classification Validation

## Scope

US-04 adds a conservative deterministic classification pass after the US-03
validation, uncertainty, provenance, and quote-review stages. It supports the
predefined categories `qualification`, `personnel`, `scoring`, `technical`,
`documentation`, and the review fallback `unknown`.

The classifier only corrects narrow, high-confidence signals. Conflicting
signals become `unknown` with `needs_review=true`. Existing review flags are
combined with the classification result and are never cleared. Requirement
text, mandatory status, source page, and evidence suggestions are preserved.

## Automated Validation

Run from `backend`:

```text
.venv/bin/python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=90
```

Final result on 2026-11-22: 183 tests passed in 12.36 seconds with 98.89%
statement coverage (359 statements, 4 missed). The coverage gate passed.

The regression suite covers:

- all five supported categories;
- unsupported, ambiguous, and conflicting classifications;
- preservation of existing review flags and non-category fields through the
  complete US-03 pipeline;
- scoring precedence for technical properties;
- compound-clause review handling and classifier idempotence;
- the annotated synthetic HVAC tender, including the three category errors
  recorded in the US-03 Qwen baseline; and
- existing US-03 extraction, validation, recovery, provenance, and uncertainty
  behavior.

## Manually Checked Examples

An earlier human audit reviewed 24 requirements from the Oxford and Southmoore
documents. The deliberately difficult sample contained:

- 7 actionable category matches;
- 12 actionable category mismatches; and
- 5 non-actionable extraction errors.

These counts are recorded as audit context only. They are not an overall model
accuracy estimate, and the available evidence does not support additional
precision, recall, or accuracy claims. No private tender text or derived tender
content is included in this repository.

## Known MVP Limitations

- The rules intentionally recognize a narrow vocabulary. Unmatched clauses
  retain the model-provided category, so a plausible but wrong model category
  may remain undetected.
- Ambiguity is not fully machine-detectable. Only explicit uncertainty patterns,
  an existing `unknown` category, or competing rule signals reliably trigger
  review.
- Compound clauses are not split into separate obligations. When distinct
  category signals appear in one extracted clause, the classifier generally
  returns `unknown`; a reviewer must decide whether the clause should be split.
- A scoring clause that mentions a technical property is categorized as
  `scoring` by design. Other overlapping categories are conservatively flagged
  instead of applying a broad precedence hierarchy.
- Classification cannot repair upstream extraction mistakes such as missing
  requirements, non-actionable text extracted as a requirement, or incorrect
  clause boundaries. US-03 review flags and provenance checks remain the
  safeguards for those cases.
- The synthetic fixture verifies deterministic regression behavior, not
  production accuracy. The Oxford/Southmoore audit is too small and deliberately
  difficult, and its private examples are not committed.
- OCR, live Ollama evaluation, and broader LLM accuracy optimization are outside
  the US-04 MVP scope.

## Acceptance Criteria Status

### Issue #4

- Every structured requirement has one schema-validated category.
- All five required categories use consistent predefined enum values.
- Conflicts and uncertain cases use `unknown` and require review.
- Classification is present in the structured extraction output.

### Issue #26

- `classify_requirements()` runs after the latest US-03 review safeguards.
- Existing review flags and all non-category fields are preserved.
- Integration remains compatible with `RequirementExtractionResult`.
- Clear category corrections are narrow and reusable; uncertain inputs are not
  silently forced into a category.

### Issue #27

- Automated regressions cover categories, uncertainty, conflicts, field
  preservation, pipeline compatibility, and the synthetic fixture.
- The full backend suite enforces at least 90% coverage.
- The manually checked audit counts and known limitations are documented
  without treating the difficult sample as a model accuracy estimate.
- The MVP does not require 100% LLM classification accuracy; uncertain cases
  remain reviewable by design.
