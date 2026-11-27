# Tender Analysis API and Review Dashboard

The FastAPI application serves a local review dashboard that uploads one HVAC
tender PDF, runs the existing validated extraction/classification/source-tracing
pipeline, and displays document coverage and requirements. It does not make
compliance decisions or expose provider credentials to the browser.

## Local WSL setup and launch

From the repository root:

```bash
cd backend
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Choose one existing provider client. No endpoint, model, or key has a built-in
default.

Local Ollama example:

```bash
export LLM_PROVIDER="ollama"
export LLM_API_URL="http://127.0.0.1:11434/api/chat"
export LLM_MODEL="your-installed-model"
```

OpenAI-compatible example:

```bash
export LLM_PROVIDER="openai-compatible"
export LLM_API_URL="https://provider.example/v1/chat/completions"
export LLM_MODEL="your-configured-model"
export LLM_API_KEY="replace-locally-do-not-commit"
```

Start the server:

```bash
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open the dashboard at `http://127.0.0.1:8000/`. API documentation remains at
`http://127.0.0.1:8000/docs`.

## Example workflow

1. Open the dashboard and choose a PDF smaller than 20 MiB.
2. For a short document, leave the page range empty. For a long document, enter
   a start and end page (for example, pages 20–30).
3. Select **Analyze tender**.
4. Review coverage warnings before inspecting actionable requirements, the
   human-review queue, and the collapsed excluded-candidate diagnostics.
5. Expand **Source trace** to compare the original model page claim with the
   deterministic `verified_source_page`, then download the response JSON if
   needed.

The equivalent API request is multipart form data:

```bash
curl -X POST http://127.0.0.1:8000/tenders/analyze \
  -F 'file=@/path/to/small-tender.pdf;type=application/pdf' \
  -F 'page_start=20' \
  -F 'page_end=30'
```

Omit both page fields for full-document analysis.

## Coverage and resource boundaries

- The existing HTTP upload limit remains 20 MiB. Larger local documents belong
  in the separate Task 0 dataset audit workflow.
- A request may analyze at most 50 pages and 100,000 extracted text characters.
  The API rejects larger selections rather than silently truncating them.
- Original one-based PDF page numbers are preserved for selected ranges.
- Pages without extractable text are `unverified` and explicitly require OCR or
  manual review. A subset request or any unverified page produces incomplete
  document coverage.
- A document or selected range with no extractable text returns an actionable
  error and does not call the model.
- Provider configuration or connectivity failures return errors; the API never
  substitutes fabricated or mock output.

`source_trace.status="matched"` verifies only that the exact extracted quote
appears on one parser page. It does **not** mean the tender requirement is
satisfied, compliant, supported by evidence, or fully reviewed.

## Relevance response and review workflow

The API keeps the existing `TenderRequirement` shape and adds two top-level
collections:

- `requirements`: high-confidence actionable candidates;
- `review_queue`: potentially actionable candidates with explicit `reasons`;
- `excluded`: narrow diagnostics for clear background, history, definition,
  procurement-description, or marketing text.

Candidates with an existing review flag, uncertain mandatory status, unknown
category, ambiguous applicability, or missing/ambiguous source match remain in
`review_queue`. Explicit obligations and disqualification language are never
excluded by the deterministic relevance gate. Excluded candidates are not
counted in `summary.requirement_count`; additive summary fields report review
and exclusion counts. The extraction function and source-tracing models remain
unchanged, but API consumers should account for the new collections.

Readable-page coverage does not establish extraction recall. Likewise, a
matched source trace establishes quote provenance, not actionability or tender
compliance.

## Offline reviewed-label evaluation

Populate a local copy of `requirement_annotations_template.csv` with manually
confirmed labels, save an analysis response as JSON, then run from `backend`:

```bash
.venv/bin/python -m app.relevance_evaluation \
  --ground-truth "/mnt/c/path/to/requirement_annotations.csv" \
  --predictions "/mnt/c/path/to/tender-analysis.json" \
  --document-id "document_id_from_inventory" \
  --output "/mnt/c/path/to/relevance-evaluation.json"
```

Matching is exact on `document_id`, one-based source page, and the quote after
case-folding and whitespace normalization. The report includes actionable
precision/recall, mandatory requirement recall, false-positive/false-negative
counts, review-queue count, and unmatched-source count. Mandatory recall treats
mandatory candidates retained in either actionable results or the review queue
as recalled. The command refuses missing or invalid labels and never creates
annotations or inferred ground truth.

Use NWACC for development, Glendale for validation, and Worcester only as the
held-out test. Do not tune rules after inspecting Worcester results. Report no
metrics until the relevant rows have been manually reviewed.

## Known limitations

- OCR and scanned-page recovery are not implemented.
- Amendments and other document-family relationships are not reconciled.
- Evidence matching, technical compliance decisions, and final reports are not
  implemented.
- Page text quality and reading order depend on `pypdf` extraction.
- Relevance rules are deliberately narrow; novel background phrasing can remain
  actionable, while ambiguous and compound clauses are escalated for review.
- Exact quote matching does not align paraphrases or split/merged clauses.
- The deterministic synthetic tests are regression checks, not real-tender
  accuracy or performance measurements.
