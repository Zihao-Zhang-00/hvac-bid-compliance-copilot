import json
from io import BytesIO

import httpx
import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

import app.main as main_module
import app.tender_analysis as analysis_module
from app.llm_client import LLMConfigurationError, completion_client_from_env


client = TestClient(main_module.app)
CLAUSE = "The units must use R-32 refrigerant."


def make_pdf(page_texts):
    stream = BytesIO()
    document = canvas.Canvas(stream)
    for text in page_texts:
        if text:
            document.drawString(72, 700, text)
        document.showPage()
    document.save()
    return stream.getvalue()


class ReplayLLM:
    def __init__(self, requirement=None, error=None):
        self.requirement = requirement
        self.error = error
        self.calls = []

    def complete(self, system_prompt, user_prompt):
        self.calls.append(json.loads(user_prompt))
        if self.error:
            raise self.error
        requirements = [] if self.requirement is None else [self.requirement]
        return json.dumps({"requirements": requirements})


def requirement(page=1, text=CLAUSE):
    return {
        "requirement_text": text,
        "category": "technical",
        "mandatory": True,
        "source_page": page,
        "evidence_needed": "Manufacturer data sheet",
        "needs_review": False,
    }


def configure(monkeypatch, llm):
    monkeypatch.setattr(main_module, "completion_client_from_env", lambda: llm)


def post_pdf(pdf, *, data=None, filename="tender.pdf"):
    return client.post(
        "/tenders/analyze",
        files={"file": (filename, pdf, "application/pdf")},
        data=data or {},
    )


def test_successful_analysis_uses_existing_pipeline_and_source_trace(monkeypatch):
    llm = ReplayLLM(requirement())
    configure(monkeypatch, llm)

    response = post_pdf(make_pdf([CLAUSE]))

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "tender.pdf"
    assert body["coverage"]["status"] == "complete"
    assert body["requested_pages"] == body["analyzed_pages"] == [1]
    assert body["summary"]["requirement_count"] == 1
    item = body["requirements"][0]
    assert item["category"] == "technical"
    assert item["source_trace"]["status"] == "matched"
    assert item["source_trace"]["verified_source_page"] == 1
    assert llm.calls[0]["pages"][0]["page_number"] == 1


def test_selected_page_preserves_pdf_number_and_never_claims_full_coverage(monkeypatch):
    llm = ReplayLLM(requirement(page=3))
    configure(monkeypatch, llm)

    response = post_pdf(
        make_pdf(["Cover", "Instructions", CLAUSE]),
        data={"page_start": "3", "page_end": "3"},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["requested_pages"] == body["analyzed_pages"] == [3]
    assert body["coverage"]["status"] == "incomplete"
    assert body["coverage"]["full_document_requested"] is False
    assert body["coverage"]["unanalyzed_pages"] == [1, 2]
    assert body["requirements"][0]["source_trace"]["verified_source_page"] == 3
    assert llm.calls[0]["pages"] == [{"page_number": 3, "text": CLAUSE}]


def test_partial_text_coverage_marks_exact_unverified_pages(monkeypatch):
    configure(monkeypatch, ReplayLLM())

    response = post_pdf(make_pdf(["Readable page", "", "Also readable"]))

    body = response.json()
    assert response.status_code == 200
    assert body["pages_with_extractable_text"] == [1, 3]
    assert body["pages_without_extractable_text"] == [2]
    assert body["coverage"]["status"] == "incomplete"
    assert body["coverage"]["unverified_pages"] == [{
        "page_number": 2,
        "status": "unverified",
        "reason": "OCR or manual review required",
    }]
    assert body["coverage"]["full_document_requested"] is True


def test_fully_image_only_pdf_returns_actionable_error_without_model_call(monkeypatch):
    llm = ReplayLLM()
    configure(monkeypatch, llm)

    response = post_pdf(make_pdf(["", ""]))

    assert response.status_code == 422
    assert "No extractable text" in response.json()["detail"]
    assert "OCR" in response.json()["detail"]
    assert llm.calls == []


def test_missing_llm_configuration_is_clear(monkeypatch):
    def missing():
        raise LLMConfigurationError("LLM_PROVIDER must be configured")

    monkeypatch.setattr(main_module, "completion_client_from_env", missing)
    response = post_pdf(make_pdf(["Readable page"]))
    assert response.status_code == 503
    assert response.json()["detail"] == "LLM_PROVIDER must be configured"


def test_unavailable_llm_is_not_replaced_with_mock_results(monkeypatch):
    error = httpx.ConnectError("offline")
    configure(monkeypatch, ReplayLLM(error=error))

    response = post_pdf(make_pdf(["Readable page"]))

    assert response.status_code == 502
    assert "provider request failed" in response.json()["detail"]


@pytest.mark.parametrize(
    ("pdf", "data", "status_code", "detail"),
    [
        (b"not pdf", {}, 415, "Invalid PDF"),
        (make_pdf(["text"]), {"page_start": "2", "page_end": "1"}, 422, "must not exceed"),
        (make_pdf(["text"]), {"page_start": "1"}, 422, "provided together"),
        (make_pdf(["text"]), {"page_start": "1", "page_end": "2"}, 422, "page count"),
    ],
)
def test_invalid_pdf_and_page_ranges(monkeypatch, pdf, data, status_code, detail):
    configure(monkeypatch, ReplayLLM())
    response = post_pdf(pdf, data=data)
    assert response.status_code == status_code
    assert detail in response.json()["detail"]


def test_oversized_pdf_is_rejected_before_parsing_or_model_call(monkeypatch):
    llm = ReplayLLM()
    configure(monkeypatch, llm)
    response = post_pdf(b"%PDF-" + b"x" * main_module.MAX_PDF_SIZE)
    assert response.status_code == 413
    assert "20 MiB" in response.json()["detail"]
    assert llm.calls == []


def test_page_and_text_budgets_are_actionable(monkeypatch):
    llm = ReplayLLM()
    configure(monkeypatch, llm)
    monkeypatch.setattr(analysis_module, "MAX_ANALYSIS_PAGES", 1)
    response = post_pdf(make_pdf(["First", "Second"]))
    assert response.status_code == 422
    assert "select a range" in response.json()["detail"]
    assert llm.calls == []

    monkeypatch.setattr(analysis_module, "MAX_ANALYSIS_PAGES", 50)
    monkeypatch.setattr(analysis_module, "MAX_ANALYSIS_TEXT_CHARS", 5)
    response = post_pdf(make_pdf(["More than five characters"]))
    assert response.status_code == 413
    assert "character model-call limit" in response.json()["detail"]
    assert llm.calls == []


def test_missing_source_is_never_presented_as_verified(monkeypatch):
    configure(monkeypatch, ReplayLLM(requirement(text="Invented requirement.")))

    response = post_pdf(make_pdf(["Different readable source text."]))

    body = response.json()
    item = body["requirements"][0]
    assert response.status_code == 200
    assert item["source_trace"]["status"] == "missing"
    assert item["source_trace"]["verified_source_page"] is None
    assert item["needs_review"] is True
    assert "compliant" not in json.dumps(body).casefold()


def test_environment_factory_supports_existing_clients_without_defaults():
    ollama = completion_client_from_env({
        "LLM_PROVIDER": "ollama",
        "LLM_API_URL": "http://localhost/ollama",
        "LLM_MODEL": "local-model",
    })
    assert ollama.endpoint == "http://localhost/ollama"
    assert ollama.model == "local-model"

    compatible = completion_client_from_env({
        "LLM_PROVIDER": "openai_compatible",
        "LLM_API_URL": "https://example.invalid/chat/completions",
        "LLM_MODEL": "configured-model",
        "LLM_API_KEY": "placeholder",
    })
    assert compatible.model == "configured-model"
    with pytest.raises(LLMConfigurationError, match="LLM_PROVIDER"):
        completion_client_from_env({})


def test_dashboard_route_is_available_and_targets_analysis_api():
    response = client.get("/")
    assert response.status_code == 200
    assert "/tenders/analyze" in response.text
    assert "Source trace" in response.text
    assert "Download JSON" in response.text
