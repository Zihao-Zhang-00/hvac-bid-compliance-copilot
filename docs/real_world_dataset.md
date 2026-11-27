# Real-World HVAC Dataset Foundation

This repository includes a local-only audit tool for inventorying HVAC tender
and manufacturer source files without committing document content. It scans PDF
and XLSX files recursively, streams SHA-256 calculation, and reads PDFs directly
from disk so it is not subject to the API upload-size limit.

The tool does not run OCR, call an LLM, download files, or retain extracted page
text. It records only file metadata, hashes, page-level text availability, and
conservative filename/path-based document roles.

## Local WSL execution

From the repository root in WSL:

```bash
cd backend
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m app.dataset_audit \
  --dataset-root "/mnt/c/Users/Aestival/Desktop/HVAC-Real-Dataset"
```

The default output directory is:

```text
/mnt/c/Users/Aestival/Desktop/HVAC-Real-Dataset/dataset-audit-output/
```

To write elsewhere or change the low-text threshold:

```bash
.venv/bin/python -m app.dataset_audit \
  --dataset-root "/mnt/c/Users/Aestival/Desktop/HVAC-Real-Dataset" \
  --output-dir "/mnt/c/Users/Aestival/Desktop/HVAC-audit-output" \
  --low-text-threshold 50
```

Each run produces:

- `inventory.json`: versioned structured inventory plus aggregate counts;
- `inventory.csv`: one row per PDF or XLSX file;
- `audit_summary.txt`: concise counts for documents, pages, roles, and failures;
- `requirement_annotations_template.csv`: header-only human annotation template.

The annotation columns are `requirement_id`, `document_id`, `exact_quote`,
`source_page`, `relevance_label`, `obligation_status`, `category`,
`evidence_required`, and `reviewer_notes`. Use `actionable`, `excluded`,
`review_required`, or `notice` for `relevance_label`; use `mandatory`, `optional`,
`conditional`, or `uncertain` for `obligation_status`. Enter exact quotes and
labels manually; the audit command never exports document text.

## Proposed document-level split

Keep every document, addendum, drawing, and related artifact for a procurement
in the same split to avoid document-family leakage:

| Procurement | Split |
|---|---|
| NWACC 2026 | Development |
| Glendale 2026 | Validation |
| Worcester 2026 | Held-out test |

Inventory records encode these as `development`, `validation`, and `held_out`.
The `project_group` values are `nwacc_2026`, `glendale_2026`, and
`worcester_2026`. Manufacturer catalogs use `manufacturer_catalogs` with a null
`dataset_split`; unrecognized projects use `unknown` with a null split.

Manufacturer catalogs should be treated as shared reference material, not
randomly split pages. Record any later benchmark policy for shared catalogs
before reporting evaluation results.

## Inventory semantics

- `document_id` is a stable prefix plus a SHA-256 digest of the Unicode-normalized
  relative path. It is not fabricated document metadata.
- SHA-256 file hashes are streamed in 1 MiB chunks.
- An extractable-text page contains at least one non-whitespace character.
- A low-text page is non-empty but contains fewer than the configured number of
  non-whitespace characters (50 by default).
- Empty and low-text pages are reported by one-based PDF page number.
- XLSX files are inventoried and hashed but their workbook contents are not
  parsed.
- Roles are inferred conservatively from declared directory structure and clear
  filename markers. Worcester filenames containing `Permit Set` or `Redesign`
  are treated as drawings only within the Worcester project. Ambiguous files
  remain `unknown`.

## Privacy and Git hygiene

The real dataset, generated inventories, audit summaries, and completed
annotation files must remain local. The repository `.gitignore` excludes common
dataset and `dataset-audit-output` directory names, but always inspect
`git status` before committing. Do not commit raw tenders, catalogs, document
text, private filenames, completed annotations, or locally generated reports.

The checked-in tests create only temporary synthetic PDFs and placeholder XLSX
bytes. They do not contain downloaded or private tender data.

## Limitations

- Text availability uses `pypdf` extraction only; image-only pages are reported
  as empty because OCR is intentionally out of scope.
- Page text quality and reading order are not assessed.
- Filename role inference is deliberately narrow and may return `unknown`.
- Encrypted or malformed PDFs are recorded as parsing failures and processing
  continues for other files.
- XLSX sheet counts, formulas, and cell contents are not inspected.
- Inventory statistics are dataset diagnostics, not extraction or classification
  accuracy results.
