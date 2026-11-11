"""Tests for the Groq 10-model allowlist catalog and modality rules (AGY-02 / Issue #55)."""
import pytest

from maestro_router.groq_catalog import (
    GROQ_AUTHORIZED_MODEL_IDS,
    GROQ_EXCLUDED_MODEL_IDS,
    GroqCatalog,
    GroqModelDefinition,
    GroqModelNotAllowedError,
    GroqQuotaLimits,
    IncompatibleModalityError,
    ModelModality,
    QuotaUnit,
)


def test_groq_catalog_contains_exactly_10_models():
    catalog = GroqCatalog()
    all_models = catalog.list_all()
    assert len(all_models) == 10
    assert len(GROQ_AUTHORIZED_MODEL_IDS) == 10
    assert {m.model_id for m in all_models} == GROQ_AUTHORIZED_MODEL_IDS


def test_groq_catalog_modality_distribution():
    catalog = GroqCatalog()
    chat_models = catalog.list_by_modality(ModelModality.TEXT_CHAT)
    safety_models = catalog.list_by_modality(ModelModality.SAFETY)
    asr_models = catalog.list_by_modality(ModelModality.AUDIO_TRANSCRIPTION)
    tts_models = catalog.list_by_modality(ModelModality.AUDIO_SYNTHESIS)

    assert len(chat_models) == 3
    assert len(safety_models) == 3
    assert len(asr_models) == 2
    assert len(tts_models) == 2

    assert {m.model_id for m in chat_models} == {
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "qwen/qwen3.8-27b",
    }
    assert {m.model_id for m in safety_models} == {
        "meta-llama/llama-prompt-guard-2-22m",
        "meta-llama/llama-prompt-guard-2-86m",
        "openai/gpt-oss-safeguard-20b",
    }
    assert {m.model_id for m in asr_models} == {
        "whisper-large-v3",
        "whisper-large-v3-turbo",
    }
    assert {m.model_id for m in tts_models} == {
        "canopylabs/orpheus-arabic-saudi",
        "canopylabs/orpheus-v1-english",
    }


def test_groq_chat_models_quota_limits():
    catalog = GroqCatalog()
    for model_id in ("openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"):
        model = catalog.get(model_id)
        assert model.limits.requests_per_minute == 30
        assert model.limits.requests_per_day == 1000
        assert model.limits.tokens_per_minute == 8000
        assert model.limits.tokens_per_day == 200000
        assert model.limits.quota_unit == QuotaUnit.TOKENS
        assert model.limits.seconds_per_hour is None
        assert model.limits.seconds_per_day is None
        assert model.organization_scope == "groq-org"
        assert model.enabled is True
        assert model.source_allowlist_date == "2026-11-11"
        assert model.proof_of_permission == "allowlist_po_2026_11_11"


def test_groq_safety_models_quota_limits():
    catalog = GroqCatalog()
    for model_id in ("meta-llama/llama-prompt-guard-2-22m", "meta-llama/llama-prompt-guard-2-86m"):
        model = catalog.get(model_id)
        assert model.limits.requests_per_minute == 30
        assert model.limits.requests_per_day == 14400
        assert model.limits.tokens_per_minute == 15000
        assert model.limits.tokens_per_day == 500000
        assert model.limits.quota_unit == QuotaUnit.TOKENS

    safeguard = catalog.get("openai/gpt-oss-safeguard-20b")
    assert safeguard.limits.requests_per_minute == 3
    assert safeguard.limits.requests_per_day == 1000
    assert safeguard.limits.tokens_per_minute == 2000
    assert safeguard.limits.tokens_per_day == 200000


def test_groq_audio_asr_heterogeneous_quota_limits():
    catalog = GroqCatalog()
    for model_id in ("whisper-large-v3", "whisper-large-v3-turbo"):
        model = catalog.get(model_id)
        assert model.limits.quota_unit == QuotaUnit.AUDIO_SECONDS
        assert model.limits.requests_per_minute == 20
        assert model.limits.requests_per_day == 2000
        assert model.limits.seconds_per_hour == 7200
        assert model.limits.seconds_per_day == 28800
        assert model.limits.tokens_per_minute is None
        assert model.limits.tokens_per_day is None


def test_groq_audio_tts_quota_limits():
    catalog = GroqCatalog()
    for model_id in ("canopylabs/orpheus-arabic-saudi", "canopylabs/orpheus-v1-english"):
        model = catalog.get(model_id)
        assert model.limits.quota_unit == QuotaUnit.TOKENS
        assert model.limits.requests_per_minute == 10
        assert model.limits.requests_per_day == 100
        assert model.limits.tokens_per_minute == 1200
        assert model.limits.tokens_per_day == 3600


def test_excluded_allam_2_7b_is_rejected():
    catalog = GroqCatalog()
    assert "allam-2-7b" in GROQ_EXCLUDED_MODEL_IDS
    assert not catalog.is_allowed("allam-2-7b")
    with pytest.raises(GroqModelNotAllowedError, match="not in the Groq allowlist"):
        catalog.get("allam-2-7b")


def test_arbitrary_unauthorized_model_is_rejected():
    catalog = GroqCatalog()
    with pytest.raises(GroqModelNotAllowedError):
        catalog.get("meta-llama/llama-3.3-70b-versatile")
    with pytest.raises(GroqModelNotAllowedError):
        GroqModelDefinition(
            model_id="unauthorized-model",
            modality=ModelModality.TEXT_CHAT,
            capabilities=frozenset({"text"}),
            limits=GroqQuotaLimits(10, 100, QuotaUnit.TOKENS, 1000, 10000),
        )


def test_non_chat_models_cannot_be_invoked_as_chat():
    catalog = GroqCatalog()
    # ASR cannot chat
    whisper = catalog.get("whisper-large-v3")
    with pytest.raises(IncompatibleModalityError, match="cannot be invoked as a general text/chat route"):
        whisper.assert_supports_chat()

    # TTS cannot chat
    orpheus = catalog.get("canopylabs/orpheus-v1-english")
    with pytest.raises(IncompatibleModalityError, match="cannot be invoked as a general text/chat route"):
        orpheus.assert_supports_chat()

    # Safety cannot chat
    guard = catalog.get("meta-llama/llama-prompt-guard-2-22m")
    with pytest.raises(IncompatibleModalityError, match="cannot be invoked as a general text/chat route"):
        guard.assert_supports_chat()

    # Chat model succeeds
    chat = catalog.get("openai/gpt-oss-120b")
    chat.assert_supports_chat()  # does not raise


def test_quota_limits_validation_errors():
    # Non-positive RPM
    with pytest.raises(ValueError, match="Request limits"):
        GroqQuotaLimits(0, 100, QuotaUnit.TOKENS, 100, 1000)

    # Missing tokens for token-based unit
    with pytest.raises(ValueError, match="tokens_per_minute"):
        GroqQuotaLimits(10, 100, QuotaUnit.TOKENS, tokens_per_minute=None, tokens_per_day=1000)

    # Audio seconds passed to token quota
    with pytest.raises(ValueError, match="cannot specify audio second limits"):
        GroqQuotaLimits(10, 100, QuotaUnit.TOKENS, tokens_per_minute=100, tokens_per_day=1000, seconds_per_hour=100)

    # Missing seconds for audio-based unit
    with pytest.raises(ValueError, match="seconds_per_hour"):
        GroqQuotaLimits(10, 100, QuotaUnit.AUDIO_SECONDS, seconds_per_hour=None, seconds_per_day=1000)

    # Tokens passed to audio quota
    with pytest.raises(ValueError, match="cannot specify token limits"):
        GroqQuotaLimits(10, 100, QuotaUnit.AUDIO_SECONDS, seconds_per_hour=100, seconds_per_day=1000, tokens_per_minute=100)


def test_shared_organization_scope():
    catalog = GroqCatalog()
    for model in catalog.list_all():
        assert model.organization_scope == "groq-org"
        assert model.provider == "groq"
