
import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from app.llm_client import OpenAICompatibleLLM
from app.requirement_extractor import extract_requirements


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


def test_invalid_model_json():
    with pytest.raises(ValidationError):
        extract_requirements(
            [{"page_number": 1, "text": "Valid text"}],
            FakeLLM("invalid json"),
        )


def test_hallucinated_page_is_rejected():
    response = json.dumps({
        "requirements": [{
            "requirement_text": "Required permit.",
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
