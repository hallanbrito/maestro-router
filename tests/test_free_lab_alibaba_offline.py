"""Offline safety and fallback tests for the opt-in Alibaba FREE-LAB route."""
import asyncio
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from maestro_router import free_lab
from maestro_router.free_fallback import RejectedBeforeGeneration


class Fake:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    async def execute(self, route, prompt, max_output_tokens):
        self.calls.append((route.id, prompt, max_output_tokens))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def settings():
    return {
        "GROQ_API_KEY": "synthetic-groq",
        "MAESTRO_GROQ_FREE_CONFIRMED": "yes",
        "ALIBABA_API_KEY": "synthetic-alibaba",
        "MAESTRO_ALIBABA_FREE_CONFIRMED": "yes",
        "MAESTRO_ALIBABA_FREE_QUOTA_ONLY_CONFIRMED": "yes",
        "MAESTRO_ALIBABA_SCOPE_INTERNATIONAL_CONFIRMED": "yes",
        "MAESTRO_ALIBABA_WORKSPACE_ID": "wksp-1234",
        "MAESTRO_ALIBABA_MODEL": "qwen-plus",
        "MAESTRO_ALIBABA_FREE_EXPIRES_UTC": (
            datetime.now(timezone.utc) + timedelta(days=30)
        ).strftime("%Y-%m-%d"),
        "MAESTRO_ALIBABA_RPM": "30",
        "MAESTRO_ALIBABA_RPD": "1000",
        "MAESTRO_ALIBABA_TPM": "8000",
        "MAESTRO_ALIBABA_TPD": "200000",
        "GEMINI_API_KEY": "synthetic-gemini",
        "MAESTRO_GEMINI_FREE_CONFIRMED": "yes",
        "MAESTRO_GEMINI_MODEL": "gemini-test-fake",
        "MAESTRO_GEMINI_RPM": "30",
        "MAESTRO_GEMINI_RPD": "1000",
        "MAESTRO_GEMINI_TPM": "8000",
        "MAESTRO_GEMINI_TPD": "200000",
    }


def test_alibaba_route_fail_closed_without_each_required_confirmation():
    cfg = settings()
    for flag in (
        "MAESTRO_ALIBABA_FREE_CONFIRMED",
        "MAESTRO_ALIBABA_FREE_QUOTA_ONLY_CONFIRMED",
        "MAESTRO_ALIBABA_SCOPE_INTERNATIONAL_CONFIRMED",
        "MAESTRO_ALIBABA_FREE_EXPIRES_UTC",
        "ALIBABA_API_KEY",
        "MAESTRO_ALIBABA_TPM",
    ):
        bad = dict(cfg)
        bad.pop(flag)
        with patch.dict(os.environ, bad, clear=True):
            assert free_lab._alibaba_free_route() is None


def test_alibaba_route_rejects_expired_quota_and_unsafe_hostname():
    cfg = settings()
    cfg["MAESTRO_ALIBABA_FREE_EXPIRES_UTC"] = "2020-01-01"
    with patch.dict(os.environ, cfg, clear=True):
        assert free_lab._alibaba_free_route() is None
    cfg = settings()
    for unsafe in ("foo.example.com", "https://evil.test", "-bad", "a/b"):
        cfg["MAESTRO_ALIBABA_WORKSPACE_ID"] = unsafe
        with patch.dict(os.environ, cfg, clear=True):
            assert free_lab._alibaba_free_route() is None


def test_offline_groq_alibaba_gemini_429_handoff_max_three():
    groq = Fake(RejectedBeforeGeneration())
    alibaba = Fake(RejectedBeforeGeneration())
    gemini = Fake("OK")

    def chat_adapter(api_key, endpoint):
        if "aliyuncs.com" in endpoint:
            assert endpoint == (
                "https://wksp-1234.ap-southeast-1.maas.aliyuncs.com/"
                "compatible-mode/v1"
            )
            return alibaba
        return groq

    with (patch.dict(os.environ, settings(), clear=True),
          patch.object(free_lab, "OpenAIChatAdapter", side_effect=chat_adapter),
          patch.object(free_lab, "GeminiTextAdapter", return_value=gemini)):
        engine = free_lab._build()
        assert [r.provider for r in engine.routes][:3] == [
            "groq", "alibaba", "gemini"
        ]
        result = asyncio.run(engine.run("tarefa pequena", live_allowed=True))

    assert result.status == "completed" and result.route == "gemini-free"
    assert result.answer == "OK"
    assert result.attempts == (
        ("groq-20b", "http_429"),
        ("alibaba-free", "http_429"),
        ("gemini-free", "success"),
    )
    assert len(groq.calls) == len(alibaba.calls) == len(gemini.calls) == 1
    assert {c.calls[0][1] for c in (groq, alibaba, gemini)} == {"tarefa pequena"}


def test_alibaba_403_stops_without_replaying_or_billing_claim():
    groq = Fake(RejectedBeforeGeneration())
    alibaba = Fake(PermissionError("403 AllocationQuota.FreeTierOnly"))
    gemini = Fake("must not be called")
    with (patch.dict(os.environ, settings(), clear=True),
          patch.object(free_lab, "OpenAIChatAdapter",
                       side_effect=lambda key, endpoint: (
                           alibaba if "aliyuncs.com" in endpoint else groq
                       )),
          patch.object(free_lab, "GeminiTextAdapter", return_value=gemini)):
        engine = free_lab._build()
        result = asyncio.run(engine.run("tarefa", live_allowed=True))
    assert result.status == "indeterminate"
    assert not gemini.calls
    assert "FreeTierOnly" not in repr(result)


def test_live_disabled_never_dispatches():
    fake = Fake("never")
    with (patch.dict(os.environ, settings(), clear=True),
          patch.object(free_lab, "OpenAIChatAdapter", return_value=fake),
          patch.object(free_lab, "GeminiTextAdapter", return_value=fake)):
        engine = free_lab._build()
        result = asyncio.run(engine.run("tarefa", live_allowed=False))
    assert result.status == "disabled" and not fake.calls
