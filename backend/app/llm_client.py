
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class OpenAICompatibleLLM:
    endpoint: str
    api_key: str
    model: str

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Call a compatible Chat Completions endpoint."""

        response = httpx.post(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {self.api_key}",
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
            },
            timeout=60.0,
        )

        response.raise_for_status()

        payload = response.json()

        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("Unexpected LLM response format") from exc

        if not isinstance(content, str) or not content.strip():
            raise ValueError("LLM returned empty or non-text content")

        return content

from app.requirement_schema import RequirementExtractionResult


@dataclass(frozen=True)
class OllamaStructuredLLM:
    """Local Ollama chat client constrained by the requirement JSON Schema."""

    endpoint: str
    model: str
    timeout: float = 300.0

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Return raw JSON; the extraction pipeline validates its contents."""
        response = httpx.post(
            self.endpoint,
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "format": RequirementExtractionResult.model_json_schema(),
                "stream": False,
                "options": {"temperature": 0},
            },
            timeout=self.timeout,
        )
        response.raise_for_status()

        try:
            content = response.json()["message"]["content"]
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            raise ValueError("Unexpected Ollama response format") from exc

        if not isinstance(content, str) or not content.strip():
            raise ValueError("Ollama returned empty or non-text content")

        return content
