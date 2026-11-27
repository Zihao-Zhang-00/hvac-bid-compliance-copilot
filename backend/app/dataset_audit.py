"""Local, text-free inventory tooling for real-world HVAC source documents."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from pypdf import PdfReader


SUPPORTED_SUFFIXES = {".pdf", ".xlsx"}
DEFAULT_LOW_TEXT_THRESHOLD = 50
OUTPUT_DIRECTORY_NAME = "dataset-audit-output"

INVENTORY_FIELDS = (
    "document_id",
    "relative_path",
    "file_type",
    "size_bytes",
    "sha256",
    "document_role",
    "pdf_page_count",
    "extractable_text_page_count",
    "extractable_text_pages",
    "empty_pages",
    "low_text_pages",
    "parsing_failure",
)

ANNOTATION_FIELDS = (
    "document_id",
    "exact_quote",
    "pdf_page",
    "category",
    "mandatory",
    "actionable",
    "evidence_required",
    "reviewer_notes",
)


def _normalized_relative_path(path: Path) -> str:
    return unicodedata.normalize("NFC", path.as_posix())


def make_document_id(relative_path: str) -> str:
    """Return a stable ID derived only from the normalized relative path."""

    normalized = unicodedata.normalize("NFC", relative_path)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"doc_{digest[:16]}"


def infer_document_role(relative_path: str, file_type: str) -> str:
    """Infer a conservative role from path and filename signals."""

    if file_type == "xlsx":
        return "spreadsheet"

    normalized = unicodedata.normalize("NFC", relative_path).casefold()
    path = Path(normalized)
    parts = set(path.parts)
    searchable = " ".join(path.parts).replace("_", "-")

    if "厂家技术手册" in parts or any(
        marker in searchable
        for marker in ("manufacturer-catalog", "product-catalog", "technical-manual")
    ):
        return "manufacturer catalog"

    if any(marker in searchable for marker in ("addendum", "addenda")):
        return "addendum"

    if any(
        marker in searchable
        for marker in (
            "bid-result",
            "bid result",
            "bid-tabulation",
            "bid tabulation",
            "notice-of-award",
            "notice of award",
        )
    ):
        return "bid result"

    if any(
        marker in searchable
        for marker in (
            "drawing",
            "blueprint",
            "plan-set",
            "plan set",
            "mechanical-plans",
            "mechanical plans",
        )
    ):
        return "drawing"

    if path.parts and path.parts[0] == "tenders":
        return "tender"

    if any(marker in searchable for marker in ("catalog", "brochure")):
        return "manufacturer catalog"

    return "unknown"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pdf_statistics(path: Path, low_text_threshold: int) -> dict[str, Any]:
    statistics: dict[str, Any] = {
        "pdf_page_count": None,
        "extractable_text_page_count": 0,
        "extractable_text_pages": [],
        "empty_pages": [],
        "low_text_pages": [],
        "parsing_failure": None,
    }

    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            statistics["parsing_failure"] = "Encrypted PDF is not supported"
            return statistics

        statistics["pdf_page_count"] = len(reader.pages)
        failed_pages: list[int] = []

        for page_number, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:  # pypdf exposes several backend-specific errors
                failed_pages.append(page_number)
                continue

            character_count = len("".join(text.split()))
            if character_count == 0:
                statistics["empty_pages"].append(page_number)
                continue

            statistics["extractable_text_pages"].append(page_number)
            if character_count < low_text_threshold:
                statistics["low_text_pages"].append(page_number)

        statistics["extractable_text_page_count"] = len(
            statistics["extractable_text_pages"]
        )
        if failed_pages:
            pages = ", ".join(str(page) for page in failed_pages)
            statistics["parsing_failure"] = (
                f"Text extraction failed on page(s): {pages}"
            )
    except Exception as exc:
        statistics["parsing_failure"] = (
            f"Unable to parse PDF ({type(exc).__name__})"
        )

    return statistics


def _inventory_file(
    path: Path,
    dataset_root: Path,
    low_text_threshold: int,
) -> dict[str, Any]:
    relative_path = _normalized_relative_path(path.relative_to(dataset_root))
    file_type = path.suffix.casefold().lstrip(".")
    record: dict[str, Any] = {
        "document_id": make_document_id(relative_path),
        "relative_path": relative_path,
        "file_type": file_type,
        "size_bytes": None,
        "sha256": None,
        "document_role": infer_document_role(relative_path, file_type),
        "pdf_page_count": None,
        "extractable_text_page_count": 0,
        "extractable_text_pages": [],
        "empty_pages": [],
        "low_text_pages": [],
        "parsing_failure": None,
    }

    try:
        record["size_bytes"] = path.stat().st_size
        record["sha256"] = _sha256(path)
    except OSError as exc:
        record["parsing_failure"] = (
            f"Unable to read file ({type(exc).__name__})"
        )
        return record

    if file_type == "pdf":
        record.update(_pdf_statistics(path, low_text_threshold))

    return record


def inventory_dataset(
    dataset_root: Path,
    low_text_threshold: int = DEFAULT_LOW_TEXT_THRESHOLD,
) -> list[dict[str, Any]]:
    """Recursively inventory supported files without retaining document text."""

    root = dataset_root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Dataset root is not a directory: {dataset_root}")
    if low_text_threshold < 1:
        raise ValueError("Low-text threshold must be at least 1")

    supported_files = sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.casefold() in SUPPORTED_SUFFIXES
        ),
        key=lambda path: (
            _normalized_relative_path(path.relative_to(root)).casefold(),
            _normalized_relative_path(path.relative_to(root)),
        ),
    )

    return [
        _inventory_file(path, root, low_text_threshold)
        for path in supported_files
    ]


def summarize_inventory(documents: Iterable[dict[str, Any]]) -> dict[str, Any]:
    records = list(documents)
    roles = Counter(record["document_role"] for record in records)
    pdfs = [record for record in records if record["file_type"] == "pdf"]

    return {
        "document_count": len(records),
        "pdf_count": len(pdfs),
        "xlsx_count": sum(
            record["file_type"] == "xlsx" for record in records
        ),
        "total_size_bytes": sum(
            record["size_bytes"] or 0 for record in records
        ),
        "pdf_page_count": sum(record["pdf_page_count"] or 0 for record in pdfs),
        "extractable_text_page_count": sum(
            record["extractable_text_page_count"] for record in pdfs
        ),
        "empty_page_count": sum(len(record["empty_pages"]) for record in pdfs),
        "low_text_page_count": sum(
            len(record["low_text_pages"]) for record in pdfs
        ),
        "parsing_failure_count": sum(
            bool(record["parsing_failure"]) for record in records
        ),
        "roles": dict(sorted(roles.items())),
    }


def _page_list_for_csv(pages: list[int]) -> str:
    return ";".join(str(page) for page in pages)


def _write_inventory_csv(
    path: Path,
    documents: list[dict[str, Any]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=INVENTORY_FIELDS,
            lineterminator="\n",
        )
        writer.writeheader()
        for document in documents:
            row = dict(document)
            for field in (
                "extractable_text_pages",
                "empty_pages",
                "low_text_pages",
            ):
                row[field] = _page_list_for_csv(row[field])
            writer.writerow(row)


def _format_summary(summary: dict[str, Any], low_text_threshold: int) -> str:
    role_lines = [
        f"  - {role}: {count}" for role, count in summary["roles"].items()
    ] or ["  - none: 0"]
    lines = [
        "HVAC dataset audit summary",
        "==========================",
        f"Documents: {summary['document_count']}",
        f"PDFs: {summary['pdf_count']}",
        f"XLSX files: {summary['xlsx_count']}",
        f"Total bytes: {summary['total_size_bytes']}",
        f"PDF pages: {summary['pdf_page_count']}",
        f"Pages with extractable text: {summary['extractable_text_page_count']}",
        f"Empty pages: {summary['empty_page_count']}",
        (
            "Low-text pages "
            f"(1-{low_text_threshold - 1} non-whitespace characters): "
            f"{summary['low_text_page_count']}"
        ),
        f"Files with parsing failures: {summary['parsing_failure_count']}",
        "Document roles:",
        *role_lines,
        "",
    ]
    return "\n".join(lines)


def write_audit_outputs(
    documents: list[dict[str, Any]],
    output_dir: Path,
    low_text_threshold: int = DEFAULT_LOW_TEXT_THRESHOLD,
) -> dict[str, Path]:
    """Write deterministic inventory, summary, and blank annotation template."""

    destination = output_dir.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    summary = summarize_inventory(documents)

    paths = {
        "json": destination / "inventory.json",
        "csv": destination / "inventory.csv",
        "summary": destination / "audit_summary.txt",
        "annotations": destination / "requirement_annotations_template.csv",
    }

    payload = {
        "schema_version": 1,
        "low_text_threshold_characters": low_text_threshold,
        "summary": summary,
        "documents": documents,
    }
    paths["json"].write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_inventory_csv(paths["csv"], documents)
    paths["summary"].write_text(
        _format_summary(summary, low_text_threshold),
        encoding="utf-8",
    )
    with paths["annotations"].open(
        "w", encoding="utf-8", newline=""
    ) as output:
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(ANNOTATION_FIELDS)

    return paths


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory local HVAC PDF/XLSX files without storing document text."
        )
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        required=True,
        help="Root directory containing the local HVAC dataset.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help=(
            "Output directory (default: <dataset-root>/dataset-audit-output)."
        ),
    )
    parser.add_argument(
        "--low-text-threshold",
        type=int,
        default=DEFAULT_LOW_TEXT_THRESHOLD,
        help="Non-whitespace characters below which a non-empty page is low text.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    output_dir = args.output_dir or args.dataset_root / OUTPUT_DIRECTORY_NAME

    try:
        documents = inventory_dataset(
            args.dataset_root,
            low_text_threshold=args.low_text_threshold,
        )
        paths = write_audit_outputs(
            documents,
            output_dir,
            low_text_threshold=args.low_text_threshold,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    print(paths["summary"].read_text(encoding="utf-8"), end="")
    print(f"Outputs: {paths['json'].parent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
