"""AI response validation, reference resolution, and each detection stage.

These run against a fake LLM so the decision logic is tested deterministically,
without network access or provider spend.
"""

from __future__ import annotations

import pytest

from app.ai.ai_service import AIService, format_pairs_block, format_requirements_block
from app.ai.llm_client import extract_json_object
from app.core.config import get_settings
from app.core.errors import AIResponseInvalid, AIServiceError
from app.schemas.ai_outputs import AmbiguityResult, DuplicateResult
from app.services.ambiguity_service import AmbiguityService, MissingInfoService
from app.services.contradiction_service import ContradictionService
from app.services.dependency_service import DependencyService
from app.services.duplicate_service import DuplicateService
from app.services.requirement_service import RequirementRecord
from app.utils.resolve import RequirementResolver


def make_record(code: str, text: str, vector: list[float] | None = None) -> RequirementRecord:
    return RequirementRecord(
        code=code,
        original_text=text,
        normalized_text=text.lower(),
        requirement_type="functional",
        section=None,
        page_number=1,
        embedding=vector or [0.0] * 4,
        db_id=f"id-{code}",
    )


# --- JSON recovery ---------------------------------------------------------
def test_parses_plain_json() -> None:
    assert extract_json_object('{"a": 1}') == {"a": 1}


def test_parses_fenced_json() -> None:
    assert extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}


def test_parses_json_with_surrounding_prose() -> None:
    assert extract_json_object('Here you go:\n{"a": 1}\nHope that helps.') == {"a": 1}


def test_rejects_unparseable_response() -> None:
    with pytest.raises(ValueError):
        extract_json_object("no json here at all")


# --- schema validation -----------------------------------------------------
def test_confidence_is_clamped() -> None:
    result = AmbiguityResult.model_validate(
        {"findings": [{"requirement_code": "R001", "ambiguous": True, "confidence": 4.2}]}
    )
    assert result.findings[0].confidence == 1.0


def test_unknown_classification_is_rejected() -> None:
    with pytest.raises(Exception):
        DuplicateResult.model_validate(
            {"verdicts": [{"requirement_a": "R1", "requirement_b": "R2", "classification": "banana"}]}
        )


# --- retry / failure behaviour ---------------------------------------------
@pytest.mark.asyncio
async def test_retries_once_then_succeeds(fake_llm) -> None:
    class FlakyLLM(fake_llm):
        def __init__(self) -> None:
            super().__init__()
            self.attempts = 0

        async def complete(self, system: str, user: str, *, temperature: float) -> str:
            self.attempts += 1
            if self.attempts == 1:
                return "sorry, I cannot do that"
            return '{"findings": [{"requirement_code": "R001", "ambiguous": true, "confidence": 0.9}]}'

    client = FlakyLLM()
    service = AIService(client=client, settings=get_settings())
    result = await service.detect_ambiguity("R001: something vague")
    assert client.attempts == 2
    assert result.findings[0].requirement_code == "R001"


@pytest.mark.asyncio
async def test_raises_rather_than_fabricating(fake_llm) -> None:
    """Invalid JSON twice must fail the stage, never invent findings."""

    class BrokenLLM(fake_llm):
        async def complete(self, system: str, user: str, *, temperature: float) -> str:
            return "still not json"

    service = AIService(client=BrokenLLM(), settings=get_settings())
    with pytest.raises(AIResponseInvalid):
        await service.detect_ambiguity("R001: something vague")


# --- provider rate limits ---------------------------------------------------
def _rate_limit_error(headers: dict[str, str]):
    import httpx
    from groq import RateLimitError

    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(429, headers=headers, request=request)
    return RateLimitError("rate limited", response=response, body=None)


def _groq_client_with(create, monkeypatch, budget: float = 180.0, effort: str = ""):
    """A GroqClient whose transport is `create`, with sleeps recorded, not taken."""
    from types import SimpleNamespace

    from app.ai import llm_client

    settings = get_settings().model_copy(
        update={
            "groq_api_key": "test-key",
            "llm_rate_limit_wait_seconds": budget,
            "groq_reasoning_effort": effort,
        }
    )
    client = llm_client.GroqClient(settings)
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(llm_client.asyncio, "sleep", fake_sleep)
    return client, sleeps


def _ok_response(content: str):
    from types import SimpleNamespace

    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


@pytest.mark.asyncio
async def test_groq_waits_out_per_minute_limit(monkeypatch) -> None:
    attempts = 0

    async def create(**_: object):
        nonlocal attempts
        attempts += 1
        if attempts <= 2:
            raise _rate_limit_error({"retry-after": "3"})
        return _ok_response('{"ok": true}')

    client, sleeps = _groq_client_with(create, monkeypatch)
    result = await client.complete("system", "user", temperature=0.0)

    assert result == '{"ok": true}'
    assert attempts == 3
    assert sleeps == [3.5, 3.5]  # the provider's retry-after, plus padding


@pytest.mark.asyncio
async def test_groq_fails_fast_when_quota_outlasts_budget(monkeypatch) -> None:
    """A daily quota (long retry-after) must fail clearly, not hang the run."""

    async def create(**_: object):
        raise _rate_limit_error({"retry-after": "3600"})

    client, sleeps = _groq_client_with(create, monkeypatch)
    with pytest.raises(AIServiceError, match="usage limit"):
        await client.complete("system", "user", temperature=0.0)
    assert sleeps == []


@pytest.mark.asyncio
async def test_groq_backs_off_without_retry_after(monkeypatch) -> None:
    async def create(**_: object):
        raise _rate_limit_error({})

    client, sleeps = _groq_client_with(create, monkeypatch, budget=40.0)
    with pytest.raises(AIServiceError):
        await client.complete("system", "user", temperature=0.0)
    assert sleeps == [5.5, 10.5, 20.5]  # exponential, stopped before the budget


def _bad_request(body: object):
    import httpx
    from groq import BadRequestError

    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    return BadRequestError("bad request", response=httpx.Response(400, request=request), body=body)


@pytest.mark.asyncio
async def test_groq_json_rejection_becomes_invalid_response(monkeypatch) -> None:
    """Groq's json_validate_failed is a bad generation: return it for the correction retry."""

    async def create(**_: object):
        raise _bad_request(
            {"error": {"code": "json_validate_failed", "failed_generation": '{"findings": ['}}
        )

    client, _ = _groq_client_with(create, monkeypatch)
    assert await client.complete("system", "user", temperature=0.0) == '{"findings": ['


@pytest.mark.asyncio
async def test_groq_json_rejection_then_valid_passes_through_ai_service(monkeypatch) -> None:
    """End to end through AIService: rejected once, corrected on the retry."""
    attempts = 0

    async def create(**_: object):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _bad_request({"error": {"code": "json_validate_failed", "failed_generation": ""}})
        return _ok_response(
            '{"findings": [{"requirement_code": "R001", "ambiguous": true, "confidence": 0.9}]}'
        )

    client, _ = _groq_client_with(create, monkeypatch)
    service = AIService(client=client, settings=get_settings())
    result = await service.detect_ambiguity("R001: something vague")
    assert attempts == 2
    assert result.findings[0].requirement_code == "R001"


@pytest.mark.asyncio
async def test_groq_other_bad_requests_still_fail(monkeypatch) -> None:
    async def create(**_: object):
        raise _bad_request({"error": {"code": "context_length_exceeded", "message": "too long"}})

    client, _ = _groq_client_with(create, monkeypatch)
    with pytest.raises(AIServiceError, match="returned an error"):
        await client.complete("system", "user", temperature=0.0)


@pytest.mark.asyncio
@pytest.mark.parametrize("effort, expected", [("low", "low"), (" LOW ", "low"), ("", None)])
async def test_groq_reasoning_effort_only_sent_when_set(monkeypatch, effort, expected) -> None:
    sent: dict[str, object] = {}

    async def create(**kwargs: object):
        sent.update(kwargs)
        return _ok_response("{}")

    client, _ = _groq_client_with(create, monkeypatch, effort=effort)
    await client.complete("system", "user", temperature=0.0)
    assert sent.get("reasoning_effort") == expected
    assert ("reasoning_effort" in sent) == (expected is not None)


def test_retry_after_header_parsing() -> None:
    from app.ai.llm_client import _retry_after_seconds

    assert _retry_after_seconds(_rate_limit_error({"retry-after": "7"})) == 7.0
    assert _retry_after_seconds(_rate_limit_error({"retry-after-ms": "1500"})) == 1.5
    assert _retry_after_seconds(_rate_limit_error({"retry-after": "soon"})) is None
    assert _retry_after_seconds(_rate_limit_error({})) is None


# --- reference resolution ---------------------------------------------------
def test_resolver_matches_exact_code(rec) -> None:
    resolver = RequirementResolver([rec("R001", "The system shall log in.")])
    assert resolver.resolve("R001").code == "R001"


def test_resolver_matches_embedded_code(rec) -> None:
    resolver = RequirementResolver([rec("R007", "The system shall log in.")])
    assert resolver.resolve("Requirement R007").code == "R007"


def test_resolver_matches_echoed_requirement_text(rec) -> None:
    """Models often answer with the sentence instead of the code."""
    text = "The system shall allow customers to register for an account."
    resolver = RequirementResolver([rec("R017", text)])
    assert resolver.resolve(text).code == "R017"


def test_resolver_matches_truncated_quote(rec) -> None:
    text = "The system shall allow customers to register for an account."
    resolver = RequirementResolver([rec("R017", text)])
    assert resolver.resolve("The system shall allow customers to register").code == "R017"


def test_resolver_returns_none_for_unknown(rec) -> None:
    resolver = RequirementResolver([rec("R001", "The system shall log in.")])
    assert resolver.resolve("R999") is None
    assert resolver.resolve("") is None


# --- duplicate detection ----------------------------------------------------
@pytest.mark.asyncio
async def test_duplicate_stage_keeps_confirmed_pairs(fake_llm) -> None:
    records = [
        make_record("R001", "Users can create an account.", [1.0, 0.0, 0.0, 0.0]),
        make_record("R017", "Customers can register for an account.", [0.99, 0.1, 0.0, 0.0]),
    ]
    llm = fake_llm(
        {
            "DUPLICATES": {
                "verdicts": [
                    {
                        "requirement_a": "R001",
                        "requirement_b": "R017",
                        "classification": "duplicate",
                        "reason": "same action",
                        "confidence": 0.95,
                        "recommendation": "merge",
                    }
                ]
            }
        }
    )
    service = DuplicateService(AIService(client=llm, settings=get_settings()), _Embed(), get_settings())
    findings = await service.run(records)
    assert len(findings) == 1
    assert findings[0].record_a.code == "R001"


@pytest.mark.asyncio
async def test_duplicate_stage_drops_not_duplicate(fake_llm) -> None:
    records = [
        make_record("R001", "Users can create an account.", [1.0, 0.0, 0.0, 0.0]),
        make_record("R004", "Users can reset a password.", [0.99, 0.1, 0.0, 0.0]),
    ]
    llm = fake_llm(
        {
            "DUPLICATES": {
                "verdicts": [
                    {
                        "requirement_a": "R001",
                        "requirement_b": "R004",
                        "classification": "not_duplicate",
                        "confidence": 0.9,
                    }
                ]
            }
        }
    )
    service = DuplicateService(AIService(client=llm, settings=get_settings()), _Embed(), get_settings())
    assert await service.run(records) == []


@pytest.mark.asyncio
async def test_duplicate_stage_drops_low_confidence(fake_llm) -> None:
    records = [
        make_record("R001", "Users can create an account.", [1.0, 0.0, 0.0, 0.0]),
        make_record("R017", "Customers can register.", [0.99, 0.1, 0.0, 0.0]),
    ]
    llm = fake_llm(
        {
            "DUPLICATES": {
                "verdicts": [
                    {
                        "requirement_a": "R001",
                        "requirement_b": "R017",
                        "classification": "duplicate",
                        "confidence": 0.2,
                    }
                ]
            }
        }
    )
    service = DuplicateService(AIService(client=llm, settings=get_settings()), _Embed(), get_settings())
    assert await service.run(records) == []


# --- contradiction detection ------------------------------------------------
@pytest.mark.asyncio
async def test_contradiction_stage_keeps_real_conflict(fake_llm) -> None:
    records = [
        make_record("R002", "Users log in with email.", [1.0, 0.0, 0.0, 0.0]),
        make_record("R003", "Users log in with mobile only.", [0.9, 0.2, 0.0, 0.0]),
    ]
    llm = fake_llm(
        {
            "CONTRADICTIONS": {
                "verdicts": [
                    {
                        "requirement_a": "R002",
                        "requirement_b": "R003",
                        "classification": "contradiction",
                        "conflict_type": "mutually exclusive auth",
                        "confidence": 1.0,
                    }
                ]
            }
        }
    )
    service = ContradictionService(AIService(client=llm, settings=get_settings()), _Embed(), get_settings())
    findings = await service.run(records)
    assert len(findings) == 1


@pytest.mark.asyncio
async def test_contradiction_stage_drops_compatible(fake_llm) -> None:
    """Same topic is not a contradiction."""
    records = [
        make_record("R002", "Users log in with email.", [1.0, 0.0, 0.0, 0.0]),
        make_record("R004", "Users reset a password.", [0.9, 0.2, 0.0, 0.0]),
    ]
    llm = fake_llm(
        {
            "CONTRADICTIONS": {
                "verdicts": [
                    {
                        "requirement_a": "R002",
                        "requirement_b": "R004",
                        "classification": "compatible",
                        "confidence": 0.95,
                    }
                ]
            }
        }
    )
    service = ContradictionService(AIService(client=llm, settings=get_settings()), _Embed(), get_settings())
    assert await service.run(records) == []


# --- ambiguity --------------------------------------------------------------
@pytest.mark.asyncio
async def test_ambiguity_keeps_only_flagged(fake_llm) -> None:
    records = [
        make_record("R026", "The application shall respond quickly."),
        make_record("R042", "Checkout shall complete within 3 seconds for 95% of transactions."),
    ]
    llm = fake_llm(
        {
            "AMBIGUITY": {
                "findings": [
                    {
                        "requirement_code": "R026",
                        "ambiguous": True,
                        "ambiguous_terms": ["quickly"],
                        "evidence": "respond quickly",
                        "severity": "high",
                        "confidence": 0.95,
                    },
                    {"requirement_code": "R042", "ambiguous": False, "confidence": 0.9},
                ]
            }
        }
    )
    service = AmbiguityService(AIService(client=llm, settings=get_settings()), get_settings())
    issues = await service.run(records)
    assert [issue.record.code for issue in issues] == ["R026"]


@pytest.mark.asyncio
async def test_missing_info_requires_specifics(fake_llm) -> None:
    records = [make_record("R006", "The system shall send notifications.")]
    llm = fake_llm(
        {
            "MISSING INFORMATION": {
                "findings": [
                    {
                        "requirement_code": "R006",
                        "has_missing_information": True,
                        "missing_information": ["channel", "trigger"],
                        "confidence": 0.9,
                    }
                ]
            }
        }
    )
    service = MissingInfoService(AIService(client=llm, settings=get_settings()), get_settings())
    issues = await service.run(records)
    assert issues[0].finding.missing_information == ["channel", "trigger"]


@pytest.mark.asyncio
async def test_missing_info_drops_empty_list(fake_llm) -> None:
    records = [make_record("R006", "The system shall send notifications.")]
    llm = fake_llm(
        {
            "MISSING INFORMATION": {
                "findings": [
                    {"requirement_code": "R006", "has_missing_information": True, "missing_information": []}
                ]
            }
        }
    )
    service = MissingInfoService(AIService(client=llm, settings=get_settings()), get_settings())
    assert await service.run(records) == []


# --- dependencies -----------------------------------------------------------
@pytest.mark.asyncio
async def test_dependency_stage_dedupes_and_filters(fake_llm) -> None:
    records = [
        make_record("R001", "Users create an account."),
        make_record("R002", "Users log in."),
        make_record("R003", "Users place an order."),
    ]
    llm = fake_llm(
        {
            "DEPENDENCIES": {
                "dependencies": [
                    {"source_requirement": "R002", "target_requirement": "R001",
                     "relationship": "depends_on", "reason": "login needs an account", "confidence": 0.95},
                    # reverse of the same edge -> must be dropped
                    {"source_requirement": "R001", "target_requirement": "R002",
                     "relationship": "enables", "reason": "duplicate edge", "confidence": 0.9},
                    # self loop -> must be dropped
                    {"source_requirement": "R003", "target_requirement": "R003",
                     "relationship": "requires", "reason": "self", "confidence": 0.9},
                    # below the confidence floor -> must be dropped
                    {"source_requirement": "R003", "target_requirement": "R002",
                     "relationship": "depends_on", "reason": "weak", "confidence": 0.1},
                ]
            }
        }
    )
    service = DependencyService(AIService(client=llm, settings=get_settings()), get_settings())
    findings = await service.run(records)
    assert len(findings) == 1
    assert (findings[0].source.code, findings[0].target.code) == ("R002", "R001")


# --- prompt block builders ---------------------------------------------------
def test_requirements_block_includes_codes() -> None:
    block = format_requirements_block([("R001", "first"), ("R002", "second")])
    assert "R001: first" in block and "R002: second" in block


def test_pairs_block_includes_similarity() -> None:
    block = format_pairs_block([("R001", "a", "R002", "b", 0.87)])
    assert "0.870" in block and "R001" in block and "R002" in block


class _Embed:
    """Candidate selection stub: always offers the single available pair."""

    @staticmethod
    def candidate_pairs(vectors, *, threshold, max_pairs, upper=1.01):
        from app.services.embedding_service import CandidatePair

        pairs = []
        for i in range(len(vectors)):
            for j in range(i + 1, len(vectors)):
                pairs.append(CandidatePair(index_a=i, index_b=j, similarity=0.9))
        return pairs[:max_pairs]
