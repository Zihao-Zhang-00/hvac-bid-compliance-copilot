# US-04 Classification Evaluation

## Configuration

- Model: qwen3:4b-instruct
- Inference: local Ollama
- Dataset: synthetic-hvac-tender-001
- Annotated requirements: 10
- Baseline: US-03 evaluation

## Results

| Metric | US-03 Baseline | US-04 |
|---|---:|---:|
| Precision | 100% | 100% |
| Recall | 100% | 100% |
| F1 | 100% | 100% |
| Category Accuracy | 70% | 100% |
| Mandatory Accuracy | 100% | 100% |
| Needs Review Accuracy | 100% | 100% |
| Missing Evidence Suggestions | 5 | 5 |
| Unsupported Source Quotes | 0 | 0 |

## Changes

A conservative classification layer corrected the three known
category mismatches involving company project references,
project manager qualifications, and conditional compliance material.

Conflicting category signals are marked as unknown and flagged
for human review. Non-category fields are preserved.

## Limitations

- Results are based on one six-page synthetic tender.
- The classifier was developed with knowledge of this dataset.
- Handcrafted regression cases do not replace independent evaluation.
- Improvements on unseen real tenders have not yet been established.
- Evidence extraction is unchanged and remains future work.
