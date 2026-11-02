"""Mock tests for local Ollama JSON Schema transport: no live server needed."""
import json

import httpx
import pytest
from pydantic import ValidationError

from app.llm_client import OllamaStructuredLLM
from app.requirement_schema import RequirementExtractionResult

URL = "http://127.0.0.1:11434/api/chat"
VALID = json.dumps({"requirements": [{
    "requirement_text": "Contractor must have an HVAC license.",
    "category": "qualification",
    "mandatory": True,
    "source_page": 1,
    "evidence_needed": None,
    "needs_review": False,
}]})


def reply(content=VALID, *, status=200, body=None):
    return httpx.Response(
        status,
        json=body if body is not None else {"message": {"content": content}},
        request=httpx.Request("POST", URL),
    )


def test_ollama_request_uses_schema_temperature_zero_and_nonstreaming(monkeypatch):
    def fake_post(url, *, json, timeout):
        assert url == URL
        assert timeout == 300.0
        assert json["model"] == "qwen3:4b-instruct"
        assert json["stream"] is False
        assert json["options"] == {"temperature": 0}
        assert json["messages"] == [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "user"},
        ]
        assert json["format"] == RequirementExtractionResult.model_json_schema()
        return reply()

    monkeypatch.setattr(httpx, "post", fake_post)
    raw = OllamaStructuredLLM(URL, "qwen3:4b-instruct").complete("system", "user")
    assert len(RequirementExtractionResult.model_validate_json(raw).requirements) == 1


def test_custom_timeout(monkeypatch):
    def fake_post(url, *, json, timeout):
        assert timeout == 45.0
        return reply()
    monkeypatch.setattr(httpx, "post", fake_post)
    assert OllamaStructuredLLM(URL, "model", 45.0).complete("s", "u") == VALID


def test_http_error_is_not_masked(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: reply(status=503))
    with pytest.raises(httpx.HTTPStatusError):
        OllamaStructuredLLM(URL, "model").complete("s", "u")


@pytest.mark.parametrize("body", [{}, {"message": {}}, {"message": []}, [1, 2]])
def test_bad_response_shape_fails_loudly(monkeypatch, body):
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: reply(body=body))
    with pytest.raises(ValueError, match="Unexpected Ollama response"):
        OllamaStructuredLLM(URL, "model").complete("s", "u")


@pytest.mark.parametrize("content", ["", "  ", None, 123])
def test_empty_or_nontext_content_fails_loudly(monkeypatch, content):
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: reply(content))
    with pytest.raises(ValueError, match="empty or non-text"):
        OllamaStructuredLLM(URL, "model").complete("s", "u")


def test_structured_transport_does_not_replace_pydantic_validation(monkeypatch):
    invalid = json.loads(VALID)
    invalid["requirements"][0]["category"] = "liability"
    raw = json.dumps(invalid)
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: reply(raw))
    output = OllamaStructuredLLM(URL, "model").complete("s", "u")
    with pytest.raises(ValidationError):
        RequirementExtractionResult.model_validate_json(output)
