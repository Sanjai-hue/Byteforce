"""LLM transport.

Groq is the documented provider. An OpenRouter-compatible client is included so
the same pipeline can run against the InsForge AI gateway when no Groq key is
provisioned; both speak the same chat-completions shape and are selected by the
LLM_PROVIDER setting. Nothing above this module knows which one is active.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import AIServiceError, ConfigurationError

logger = logging.getLogger("reqguard.llm")

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class LLMClient(ABC):
    """Chat-completions transport returning raw assistant text."""

    model: str

    @abstractmethod
    async def complete(self, system: str, user: str, *, temperature: float) -> str: ...

    @abstractmethod
    async def close(self) -> None: ...


class GroqClient(LLMClient):
    def __init__(self, settings: Settings) -> None:
        if not settings.groq_api_key:
            raise ConfigurationError(
                "GROQ_API_KEY is not set. Add it to the backend environment to run analysis."
            )
        # Imported lazily so the package is only required when Groq is selected.
        from groq import AsyncGroq

        self.model = settings.groq_model
        self._rate_limit_budget = settings.llm_rate_limit_wait_seconds
        self._extra: dict[str, Any] = {}
        if settings.groq_reasoning_effort.strip():
            self._extra["reasoning_effort"] = settings.groq_reasoning_effort.strip().lower()
        self._client = AsyncGroq(
            api_key=settings.groq_api_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )

    async def complete(self, system: str, user: str, *, temperature: float) -> str:
        from groq import APIError, APIConnectionError, RateLimitError

        # Free-tier keys have a per-minute token limit that a full analysis
        # exceeds. That window resets within a minute, so a 429 is waited out
        # rather than failing the run. A daily quota answers with a much longer
        # retry-after, which overruns the budget and fails fast instead.
        waited = 0.0
        attempt = 0
        while True:
            try:
                response = await self._client.chat.completions.create(
                    model=self.model,
                    temperature=temperature,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    **self._extra,
                )
                break
            except RateLimitError as exc:
                attempt += 1
                delay = _retry_after_seconds(exc)
                if delay is None:
                    delay = min(60.0, 5.0 * 2 ** (attempt - 1))
                delay += 0.5  # land just after the window resets, not on it
                if waited + delay > self._rate_limit_budget:
                    raise AIServiceError(
                        "The AI provider's usage limit has been reached. Try again later.",
                        detail=f"waited {waited:.0f}s, next retry-after {delay:.0f}s: {exc}",
                    ) from exc
                logger.warning(
                    "groq rate limited; waiting %.1fs before retry %d (%.0fs waited so far)",
                    delay, attempt, waited,
                )
                await asyncio.sleep(delay)
                waited += delay
            except APIConnectionError as exc:
                raise AIServiceError(
                    "Could not reach the AI provider.", detail=str(exc)
                ) from exc
            except APIError as exc:
                # In JSON mode Groq validates the output itself and answers a
                # malformed generation with a 400 rather than returning it. That
                # is an invalid model response, not a provider failure: hand the
                # text back so AIService runs its correction retry as usual.
                failed = _json_validation_failure(exc)
                if failed is not None:
                    logger.warning(
                        "groq rejected the model's JSON (%d chars); passing it to the correction retry",
                        len(failed),
                    )
                    return failed
                raise AIServiceError("The AI provider returned an error.", detail=str(exc)) from exc

        usage = getattr(response, "usage", None)
        if usage is not None:
            logger.info(
                "llm usage: prompt=%s completion=%s total=%s",
                usage.prompt_tokens, usage.completion_tokens, usage.total_tokens,
            )
        content = response.choices[0].message.content if response.choices else ""
        return content or ""

    async def close(self) -> None:
        await self._client.close()


class OpenRouterClient(LLMClient):
    """OpenAI-compatible chat completions (used with the InsForge AI gateway key)."""

    def __init__(self, settings: Settings) -> None:
        if not settings.openrouter_api_key:
            raise ConfigurationError(
                "OPENROUTER_API_KEY is not set. Add it, or set LLM_PROVIDER=groq with a Groq key."
            )
        self.model = settings.openrouter_model
        self._timeout = settings.llm_timeout_seconds
        self._client = httpx.AsyncClient(
            base_url=settings.openrouter_base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
                "X-Title": "ReqGuard AI",
            },
            timeout=httpx.Timeout(self._timeout, connect=15.0),
        )

    async def complete(self, system: str, user: str, *, temperature: float) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            response = await self._client.post("/chat/completions", json=payload)
        except httpx.HTTPError as exc:
            raise AIServiceError("Could not reach the AI provider.", detail=str(exc)) from exc

        if response.status_code >= 400:
            logger.error("openrouter error %s: %s", response.status_code, response.text[:500])
            raise AIServiceError(
                "The AI provider returned an error.",
                detail=f"{response.status_code}: {response.text[:300]}",
            )

        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise AIServiceError("The AI provider returned an empty response.")
        return choices[0].get("message", {}).get("content") or ""

    async def close(self) -> None:
        await self._client.aclose()


def _retry_after_seconds(exc: Exception) -> float | None:
    """Seconds the provider asked us to wait, from the 429 response headers."""
    headers = getattr(getattr(exc, "response", None), "headers", None) or {}
    for name, scale in (("retry-after-ms", 0.001), ("retry-after", 1.0)):
        value = headers.get(name)
        if value:
            try:
                return float(value) * scale
            except ValueError:
                continue
    return None


def _json_validation_failure(exc: Exception) -> str | None:
    """The rejected text when Groq refused a JSON-mode generation, else None."""
    body = getattr(exc, "body", None)
    if not isinstance(body, dict):
        return None
    error = body.get("error", body)
    if isinstance(error, dict) and error.get("code") == "json_validate_failed":
        return str(error.get("failed_generation") or "")
    return None


def build_llm_client(settings: Settings | None = None) -> LLMClient:
    settings = settings or get_settings()
    if settings.llm_provider == "groq":
        return GroqClient(settings)
    return OpenRouterClient(settings)


def extract_json_object(raw: str) -> dict[str, Any]:
    """Best-effort recovery of a JSON object from an assistant message.

    Handles clean JSON, fenced code blocks, and leading/trailing prose. Raises
    ValueError when nothing parseable is present — callers turn that into a
    correction retry, never into a fabricated result.
    """
    if not raw or not raw.strip():
        raise ValueError("empty response")

    text = raw.strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            return {"items": parsed}
    except json.JSONDecodeError:
        pass

    fenced = _JSON_BLOCK.search(text)
    if fenced:
        candidate = fenced.group(1).strip()
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list):
                return {"items": parsed}
        except json.JSONDecodeError:
            pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    raise ValueError("no JSON object found in response")
