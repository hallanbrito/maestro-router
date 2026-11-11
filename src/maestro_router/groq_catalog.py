"""Groq 10-model organization allowlist and modality catalog.

Defines the exact 10 models permitted by the Product Owner on Nov 11, 2026,
with typed modalities, heterogeneous quota units (tokens vs audio seconds),
organization scopes, and non-chat execution guardrails.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class ModelModality(str, Enum):
    """Supported model modalities under the Groq organization allowlist."""
    TEXT_CHAT = "text/chat"
    SAFETY = "safety"
    AUDIO_TRANSCRIPTION = "audio-transcription"
    AUDIO_SYNTHESIS = "audio-synthesis"


class QuotaUnit(str, Enum):
    """Quota measurement units used across distinct modalities."""
    TOKENS = "tokens"
    AUDIO_SECONDS = "audio_seconds"


class GroqModelNotAllowedError(ValueError):
    """Raised when attempting to configure or register a model outside the allowlist."""


class IncompatibleModalityError(TypeError):
    """Raised when attempting to execute a non-chat modality as a general chat route."""


@dataclass(frozen=True, slots=True)
class GroqQuotaLimits:
    """Heterogeneous rate and quota limits for a Groq model or organization scope."""
    requests_per_minute: int
    requests_per_day: int
    quota_unit: QuotaUnit = QuotaUnit.TOKENS
    tokens_per_minute: int | None = None
    tokens_per_day: int | None = None
    seconds_per_hour: int | None = None
    seconds_per_day: int | None = None

    def __post_init__(self) -> None:
        if self.requests_per_minute <= 0 or self.requests_per_day <= 0:
            raise ValueError("Request limits must be positive integers.")
        if self.quota_unit == QuotaUnit.TOKENS:
            if self.tokens_per_minute is None or self.tokens_per_minute <= 0:
                raise ValueError("Token-based quotas require positive tokens_per_minute.")
            if self.tokens_per_day is None or self.tokens_per_day <= 0:
                raise ValueError("Token-based quotas require positive tokens_per_day.")
            if self.seconds_per_hour is not None or self.seconds_per_day is not None:
                raise ValueError("Token-based quotas cannot specify audio second limits.")
        elif self.quota_unit == QuotaUnit.AUDIO_SECONDS:
            if self.seconds_per_hour is None or self.seconds_per_hour <= 0:
                raise ValueError("Audio quotas require positive seconds_per_hour.")
            if self.seconds_per_day is None or self.seconds_per_day <= 0:
                raise ValueError("Audio quotas require positive seconds_per_day.")
            if self.tokens_per_minute is not None or self.tokens_per_day is not None:
                raise ValueError("Audio quotas cannot specify token limits.")


@dataclass(frozen=True, slots=True)
class GroqModelDefinition:
    """Immutable specification of an authorized model from the Groq allowlist."""
    model_id: str
    modality: ModelModality
    capabilities: frozenset[str]
    limits: GroqQuotaLimits
    enabled: bool = True
    provider: str = "groq"
    organization_scope: str = "groq-org"
    source_allowlist_date: str = "2026-11-11"
    proof_of_permission: str = "allowlist_po_2026_11_11"

    def __post_init__(self) -> None:
        if not self.model_id or not self.model_id.strip():
            raise ValueError("Model ID must be a non-empty string.")
        if self.model_id not in GROQ_AUTHORIZED_MODEL_IDS:
            raise GroqModelNotAllowedError(
                f"Model '{self.model_id}' is not in the authorized Groq allowlist."
            )

    def assert_supports_chat(self) -> None:
        """Verify that the model supports general text chat, raising otherwise."""
        if self.modality != ModelModality.TEXT_CHAT:
            raise IncompatibleModalityError(
                f"Model '{self.model_id}' has modality '{self.modality.value}' "
                f"and cannot be invoked as a general text/chat route."
            )


# Canonical 10-model allowlist authorized by PO on 2026-11-11
GROQ_AUTHORIZED_MODEL_IDS: frozenset[str] = frozenset({
    # Chat geral (3)
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
    # Moderação / safety (3)
    "meta-llama/llama-prompt-guard-2-22m",
    "meta-llama/llama-prompt-guard-2-86m",
    "openai/gpt-oss-safeguard-20b",
    # Áudio ASR (2)
    "whisper-large-v3",
    "whisper-large-v3-turbo",
    # Áudio TTS (2)
    "canopylabs/orpheus-arabic-saudi",
    "canopylabs/orpheus-v1-english",
})

# Explicitly excluded / unverified models (present in public tables but not on organization allowlist)
GROQ_EXCLUDED_MODEL_IDS: frozenset[str] = frozenset({
    "allam-2-7b",
})


def _build_groq_catalog() -> Mapping[str, GroqModelDefinition]:
    """Construct the frozen 10/10 model catalog."""
    catalog: dict[str, GroqModelDefinition] = {}

    # 1. Chat Geral (3) - 30 RPM / 1k RPD / 8k TPM / 200k TPD
    chat_limits = GroqQuotaLimits(
        requests_per_minute=30,
        requests_per_day=1000,
        quota_unit=QuotaUnit.TOKENS,
        tokens_per_minute=8000,
        tokens_per_day=200000,
    )
    for model_id in ("openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"):
        catalog[model_id] = GroqModelDefinition(
            model_id=model_id,
            modality=ModelModality.TEXT_CHAT,
            capabilities=frozenset({"text", "chat", "text_generation"}),
            limits=chat_limits,
        )

    # 2. Moderação / Safety (3)
    # Llama Prompt Guard 2: 30 RPM / 14.4k RPD / 15k TPM / 500k TPD
    guard_limits = GroqQuotaLimits(
        requests_per_minute=30,
        requests_per_day=14400,
        quota_unit=QuotaUnit.TOKENS,
        tokens_per_minute=15000,
        tokens_per_day=500000,
    )
    for model_id in ("meta-llama/llama-prompt-guard-2-22m", "meta-llama/llama-prompt-guard-2-86m"):
        catalog[model_id] = GroqModelDefinition(
            model_id=model_id,
            modality=ModelModality.SAFETY,
            capabilities=frozenset({"safety", "prompt_guard"}),
            limits=guard_limits,
        )

    # GPT-OSS Safeguard: 3 RPM / 1k RPD / 2k TPM / 200k TPD
    safeguard_limits = GroqQuotaLimits(
        requests_per_minute=3,
        requests_per_day=1000,
        quota_unit=QuotaUnit.TOKENS,
        tokens_per_minute=2000,
        tokens_per_day=200000,
    )
    catalog["openai/gpt-oss-safeguard-20b"] = GroqModelDefinition(
        model_id="openai/gpt-oss-safeguard-20b",
        modality=ModelModality.SAFETY,
        capabilities=frozenset({"safety", "safeguard"}),
        limits=safeguard_limits,
    )

    # 3. Áudio ASR (2) - 20 RPM / 2k RPD / 7.2k s/h / 28.8k s/d
    asr_limits = GroqQuotaLimits(
        requests_per_minute=20,
        requests_per_day=2000,
        quota_unit=QuotaUnit.AUDIO_SECONDS,
        seconds_per_hour=7200,
        seconds_per_day=28800,
    )
    for model_id in ("whisper-large-v3", "whisper-large-v3-turbo"):
        catalog[model_id] = GroqModelDefinition(
            model_id=model_id,
            modality=ModelModality.AUDIO_TRANSCRIPTION,
            capabilities=frozenset({"audio", "transcription"}),
            limits=asr_limits,
        )

    # 4. Áudio TTS (2) - 10 RPM / 100 RPD / 1.2k TPM / 3.6k TPD
    tts_limits = GroqQuotaLimits(
        requests_per_minute=10,
        requests_per_day=100,
        quota_unit=QuotaUnit.TOKENS,
        tokens_per_minute=1200,
        tokens_per_day=3600,
    )
    for model_id in ("canopylabs/orpheus-arabic-saudi", "canopylabs/orpheus-v1-english"):
        catalog[model_id] = GroqModelDefinition(
            model_id=model_id,
            modality=ModelModality.AUDIO_SYNTHESIS,
            capabilities=frozenset({"audio", "synthesis"}),
            limits=tts_limits,
        )

    return catalog


GROQ_MODELS: Mapping[str, GroqModelDefinition] = _build_groq_catalog()


class GroqCatalog:
    """Catalog holding and validating the Groq 10-model allowlist."""

    def __init__(self, models: Mapping[str, GroqModelDefinition] | None = None) -> None:
        self._models = dict(models) if models is not None else dict(GROQ_MODELS)
        self._validate()

    def _validate(self) -> None:
        if len(self._models) != len(GROQ_AUTHORIZED_MODEL_IDS):
            raise ValueError(
                f"Groq catalog must contain exactly {len(GROQ_AUTHORIZED_MODEL_IDS)} authorized models. "
                f"Found {len(self._models)}."
            )
        for model_id, model_def in self._models.items():
            if model_id != model_def.model_id:
                raise ValueError(f"Key mismatch: '{model_id}' != '{model_def.model_id}'.")
            if model_id in GROQ_EXCLUDED_MODEL_IDS or model_id not in GROQ_AUTHORIZED_MODEL_IDS:
                raise GroqModelNotAllowedError(f"Unauthorized model '{model_id}' in catalog.")

    def get(self, model_id: str) -> GroqModelDefinition:
        """Retrieve model definition or raise GroqModelNotAllowedError."""
        if model_id in self._models:
            return self._models[model_id]
        raise GroqModelNotAllowedError(f"Model '{model_id}' is not in the Groq allowlist.")

    def is_allowed(self, model_id: str) -> bool:
        """Check whether a model ID is allowed."""
        return model_id in self._models

    def list_all(self) -> tuple[GroqModelDefinition, ...]:
        """Return all 10 authorized models."""
        return tuple(self._models.values())

    def list_by_modality(self, modality: ModelModality) -> tuple[GroqModelDefinition, ...]:
        """Filter authorized models by modality."""
        return tuple(m for m in self._models.values() if m.modality == modality)

    def list_chat_models(self) -> tuple[GroqModelDefinition, ...]:
        """Convenience accessor for general text/chat models."""
        return self.list_by_modality(ModelModality.TEXT_CHAT)
