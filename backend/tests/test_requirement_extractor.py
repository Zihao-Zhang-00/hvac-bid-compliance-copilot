
import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from app.llm_client import OpenAICompatibleLLM
from app.requirement_extractor import SYSTEM_PROMPT, extract_requirements


FIXTURES = Path(__file__).parent / "fixtures"


class FakeLLM:
    def __init__(self, response: str):
        self.response = response
        self.user_prompt = None

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        assert "requirements" in system_prompt
        self.user_prompt = user_prompt
        return self.response


def test_extracts_fixture_requirements():
    tender = json.loads(
        (FIXTURES / "sample_tender_pages.json").read_text(
            encoding="utf-8"
        )
    )
    expected = (
        FIXTURES / "expected_requirements.json"
    ).read_text(encoding="utf-8")

    fake = FakeLLM(expected)
    result = extract_requirements(tender["pages"], fake)

    assert len(result.requirements) == 10
    assert result.requirements[4].source_page == 3
    assert json.loads(fake.user_prompt)["pages"] == tender["pages"]


def test_empty_extraction():
    result = extract_requirements(
        [{"page_number": 1, "text": "A project introduction."}],
        FakeLLM('{"requirements": []}'),
    )

    assert result.requirements == []


def test_prompt_calls_out_critical_constraints_without_requiring_modal_verbs():
    prompt = SYSTEM_PROMPT.casefold()

    assert "approved-equal" in prompt
    assert "manufacturer or model restrictions" in prompt
    assert "prohibitive bid-response" in prompt
    assert "instructions" in prompt


@pytest.mark.parametrize(
    "pages",
    [
        [],
        "bad",
        ["bad"],
        [{"page_number": 0, "text": "Something"}],
        [{"page_number": True, "text": "Something"}],
        [{"page_number": 1, "text": 123}],
        [{"page_number": 1, "text": "  "}],
        [
            {"page_number": 1, "text": "A"},
            {"page_number": 1, "text": "B"},
        ],
    ],
)
def test_invalid_input(pages):
    with pytest.raises(ValueError):
        extract_requirements(
            pages,
            FakeLLM('{"requirements": []}'),
        )


def test_blank_page_among_readable_pages():
    pages = [
        {"page_number": 1, "text": "Required permit."},
        {"page_number": 2, "text": ""},
    ]

    result = extract_requirements(
        pages,
        FakeLLM('{"requirements": []}'),
    )

    assert result.requirements == []


def test_extraction_view_uses_original_pages_for_source_trace():
    quote = "The bidder shall submit a bond."
    response = json.dumps({"requirements": [{
        "requirement_text": quote,
        "category": "documentation",
        "mandatory": True,
        "source_page": 1,
        "evidence_needed": "Bid bond",
        "needs_review": False,
    }]})
    extraction_pages = [{"page_number": 1, "text": f"{' ' * 12}\n{quote}"}]
    source_pages = [{"page_number": 1, "text": f"RFP No. 123\n{quote}"}]

    result = extract_requirements(
        extraction_pages,
        FakeLLM(response),
        source_pages=source_pages,
    )

    evidence = result.requirements[0].source_trace.evidence[0]
    assert evidence.start_char == source_pages[0]["text"].index(quote)
    assert evidence.text == quote


def test_invalid_model_json():
    with pytest.raises(ValidationError):
        extract_requirements(
            [{"page_number": 1, "text": "Valid text"}],
            FakeLLM("invalid json"),
        )


def test_hallucinated_page_is_rejected():
    response = json.dumps({
        "requirements": [{
            "requirement_text": "Nonexistent HVAC permit requirement.",
            "category": "qualification",
            "mandatory": True,
            "source_page": 99,
            "evidence_needed": None,
            "needs_review": False,
        }]
    })

    with pytest.raises(ValueError, match="source page"):
        extract_requirements(
            [{"page_number": 1, "text": "Required permit."}],
            FakeLLM(response),
        )


def test_http_client(monkeypatch):
    url = "https://example.test/chat/completions"

    def fake_post(request_url, *, headers, json, timeout):
        assert request_url == url
        assert headers["Authorization"] == "Bearer demo-key"
        assert json["messages"][0]["role"] == "system"
        assert json["response_format"] == {"type": "json_object"}

        return httpx.Response(
            200,
            json={
                "choices": [{
                    "message": {
                        "content": '{"requirements": []}'
                    }
                }]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    client = OpenAICompatibleLLM(url, "demo-key", "demo-model")

    assert client.complete("system", "user") == '{"requirements": []}'


def test_http_client_rejects_bad_shape(monkeypatch):
    url = "https://example.test/chat/completions"

    monkeypatch.setattr(
        httpx,
        "post",
        lambda *a, **kw: httpx.Response(
            200,
            json={"choices": []},
            request=httpx.Request("POST", url),
        ),
    )

    with pytest.raises(ValueError, match="Unexpected"):
        OpenAICompatibleLLM(
            url, "key", "model"
        ).complete("system", "user")

def test_http_client_rejects_empty_content(monkeypatch):
    url = "https://example.test/chat/completions"

    def fake_post(*args, **kwargs):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": ""}}
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    client = OpenAICompatibleLLM(
        endpoint=url,
        api_key="demo-key",
        model="demo-model",
    )

    with pytest.raises(ValueError, match="empty or non-text"):
        client.complete("system", "user")
