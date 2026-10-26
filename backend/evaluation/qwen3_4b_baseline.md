# US-03 Requirement Extraction — Evaluation Baseline

## Configuration

- Model: qwen3:4b-instruct
- Inference: Ollama (local)
- Dataset: synthetic-hvac-tender-001
- Pages: 6
- Manually annotated requirements: 10
- Matching method: exact requirement text + source page

## Extraction Metrics

| Metric | Result |
|---|---:|
| True Positives | 10 |
| False Positives | 0 |
| False Negatives | 0 |
| Precision | 100% |
| Recall | 100% |
| F1 | 100% |
| Category Accuracy | 7/10 (70%) |
| Mandatory Accuracy | 10/10 (100%) |
| Needs Review Accuracy | 10/10 (100%) |
| Missing Evidence Suggestions | 5 |
| Unsupported Source Quotes | 0 |

## Known Classification Errors

1. Page 1: Completed HVAC project references
   - Expected: qualification
   - Actual: documentation

2. Page 2: Project manager engineering license
   - Expected: personnel
   - Actual: qualification

3. Page 5: Conditional compliance information
   - Expected: unknown
   - Actual: documentation

## Testing

- 97 automated backend tests passed.
- 100% statement and branch coverage.
- LLM integration tests use mocked responses.
- Real inference was evaluated separately using Ollama.

## Reproduction

Run from backend:

    python -m scripts.evaluate_extraction --output /tmp/hvac_evaluation.json

## Limitations

- Results come from one six-page synthetic tender.
- Exact matching does not measure semantic equivalence.
- Results may vary across inference runs.
- This is not a production accuracy estimate.
- Source quote matching does not replace US-05 provenance verification.
- Category errors remain for US-04.
- Further evaluation on diverse and unseen tenders is needed.
