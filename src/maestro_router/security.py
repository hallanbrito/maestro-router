"""MAESTRO-0800 Security Controls, Guardrails, Egress Validation, and Redaction.

This module implements offline-first security primitives for the MAESTRO-0800 track:
1. Credential scoping, redaction of secrets in text, errors, headers, and diff scanner.
2. Dual-gate activation and runtime consent (enforcing 'no credit card != spend authorization').
3. Official endpoint egress validation and SSRF mitigation.
4. No-cost fallback guardrails, anti-quota-bypass protection, and fail-closed uncertainty handling.
5. Error sanitization and negative response classification (401, 403, 429, indeterminate).
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class SecurityError(Exception):
    """Base class for all security guardrail violations."""

    pass


class SecretLeakError(SecurityError):
    """Raised when a secret leak is detected or exposed in output."""

    pass


class SSRFSecurityError(SecurityError):
    """Raised when an egress URL violates SSRF, HTTPS, or domain allowlist policies."""

    pass


class SecurityPolicyError(SecurityError):
    """Raised when an operation violates security policy or dual-gate invariant."""

    pass


class QuotaBypassAttemptError(SecurityError):
    """Raised when multiple keys are rotated to bypass provider quotas."""

    pass


class ConsentRevokedError(SecurityError):
    """Raised when an operation is attempted after consent was revoked."""

    pass


class UncertainExecutionError(SecurityError):
    """Raised when an execution failed in an indeterminate state and must not be retried."""

    pass


# ---------------------------------------------------------------------------
# 1. Secret Redaction & Scanner
# ---------------------------------------------------------------------------

_OPENAI_KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-]{20,}")
_GROQ_KEY_PATTERN = re.compile(r"gsk_[A-Za-z0-9_\-]{20,}")
_DASHSCOPE_KEY_PATTERN = re.compile(r"sk-[a-f0-9]{32}")
_GOOGLE_KEY_PATTERN = re.compile(r"AIza[0-9A-Za-z\-_]{30,}")
_BEARER_TOKEN_PATTERN = re.compile(r"Bearer\s+([A-Za-z0-9._~+/=\-]{16,})", re.IGNORECASE)

_SENSITIVE_HEADER_NAMES = frozenset(
    {
        "authorization",
        "api-key",
        "x-api-key",
        "x-goog-api-key",
        "dashscope-api-key",
        "proxy-authorization",
    }
)


@dataclass(frozen=True)
class SecretFinding:
    """Represents a potential secret identified by the security scanner."""

    secret_type: str
    line_number: int
    preview: str


def redact_sensitive_text(text: str, additional_secrets: tuple[str, ...] = ()) -> str:
    """Redact known API keys, bearer tokens, and explicit custom secrets from text."""
    if not isinstance(text, str):
        return text

    sanitized = text

    # Redact explicit custom secrets first if provided
    for secret in additional_secrets:
        if secret and isinstance(secret, str) and len(secret) >= 6:
            sanitized = sanitized.replace(secret, "[REDACTED]")

    # Redact known patterns
    sanitized = _OPENAI_KEY_PATTERN.sub("[REDACTED]", sanitized)
    sanitized = _GROQ_KEY_PATTERN.sub("[REDACTED]", sanitized)
    sanitized = _DASHSCOPE_KEY_PATTERN.sub("[REDACTED]", sanitized)
    sanitized = _GOOGLE_KEY_PATTERN.sub("[REDACTED]", sanitized)
    sanitized = _BEARER_TOKEN_PATTERN.sub("Bearer [REDACTED]", sanitized)

    return sanitized


def sanitize_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Return a copy of headers with sensitive authorization values redacted."""
    sanitized: dict[str, str] = {}
    for key, value in headers.items():
        key_lower = key.lower()
        if key_lower in _SENSITIVE_HEADER_NAMES:
            sanitized[key] = "[REDACTED]"
        else:
            sanitized[key] = redact_sensitive_text(value)
    return sanitized


def scan_text_for_secrets(text: str) -> list[SecretFinding]:
    """Scan arbitrary text and report any secret patterns detected."""
    findings: list[SecretFinding] = []
    lines = text.splitlines()

    for idx, line in enumerate(lines, start=1):
        for match in _OPENAI_KEY_PATTERN.finditer(line):
            val = match.group()
            findings.append(
                SecretFinding(
                    secret_type="openai_key",
                    line_number=idx,
                    preview=f"{val[:5]}...{val[-4:]}",
                )
            )
        for match in _GROQ_KEY_PATTERN.finditer(line):
            val = match.group()
            findings.append(
                SecretFinding(
                    secret_type="groq_key",
                    line_number=idx,
                    preview=f"{val[:6]}...{val[-4:]}",
                )
            )
        for match in _GOOGLE_KEY_PATTERN.finditer(line):
            val = match.group()
            findings.append(
                SecretFinding(
                    secret_type="google_key",
                    line_number=idx,
                    preview=f"{val[:6]}...{val[-4:]}",
                )
            )
        for match in _DASHSCOPE_KEY_PATTERN.finditer(line):
            val = match.group()
            findings.append(
                SecretFinding(
                    secret_type="dashscope_key",
                    line_number=idx,
                    preview=f"{val[:5]}...{val[-4:]}",
                )
            )
        for match in _BEARER_TOKEN_PATTERN.finditer(line):
            val = match.group(1)
            findings.append(
                SecretFinding(
                    secret_type="bearer_token",
                    line_number=idx,
                    preview=f"{val[:4]}...{val[-4:]}",
                )
            )

    return findings


def scan_diff_for_secrets(diff_text: str) -> list[SecretFinding]:
    """Scan unified diff text (only added lines starting with '+') for secret leaks."""
    added_lines: list[str] = []
    line_map: list[int] = []

    for idx, line in enumerate(diff_text.splitlines(), start=1):
        if line.startswith("+") and not line.startswith("+++"):
            added_lines.append(line[1:])
            line_map.append(idx)

    findings: list[SecretFinding] = []
    for line_idx, content in zip(line_map, added_lines):
        for finding in scan_text_for_secrets(content):
            findings.append(
                SecretFinding(
                    secret_type=finding.secret_type,
                    line_number=line_idx,
                    preview=finding.preview,
                )
            )
    return findings


# ---------------------------------------------------------------------------
# 2. Official Egress & SSRF Mitigation
# ---------------------------------------------------------------------------

_OFFICIAL_ENDPOINTS: dict[str, tuple[str, ...]] = {
    "openai": ("api.openai.com",),
    "groq": ("api.groq.com",),
    "google": ("generativelanguage.googleapis.com",),
    "alibaba": ("dashscope-intl.aliyuncs.com",),
}

_ALIBABA_SINGAPORE_DEDICATED_PATTERN = re.compile(
    r"^[a-zA-Z0-9\-]+\.ap-southeast-1\.maas\.aliyuncs\.com$"
)
_DOMESTIC_ALIBABA_HOST = "dashscope.aliyuncs.com"


def is_ip_address(host: str) -> bool:
    """Return True if host is a literal IPv4 or IPv6 address."""
    clean_host = host.strip("[]")
    try:
        ipaddress.ip_address(clean_host)
        return True
    except ValueError:
        return False


def validate_egress_endpoint(
    url: str,
    provider: str,
    *,
    allow_domestic_alibaba: bool = False,
) -> str:
    """Validate that an egress URL is HTTPS, strictly official, and not SSRF.

    Raises:
        SSRFSecurityError: If URL is non-HTTPS, targets IP/loopback, uses unapproved port,
            or uses a domain outside the provider's official allowlist.
    """
    if not isinstance(url, str) or not url.strip():
        raise SSRFSecurityError("Egress URL must be a non-blank string.")

    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise SSRFSecurityError(f"Malformed egress URL: {exc}") from exc

    # 1. Scheme must be strictly HTTPS
    if parsed.scheme.lower() != "https":
        raise SSRFSecurityError(
            f"Insecure scheme '{parsed.scheme}'. Only HTTPS is permitted for external egress."
        )

    host = parsed.hostname
    if not host:
        raise SSRFSecurityError("Egress URL has no valid hostname.")

    host_lower = host.lower()

    # 2. Reject any literal IP address (prevents 127.0.0.1, 169.254.169.254, 10.x, etc.)
    if is_ip_address(host_lower):
        raise SSRFSecurityError(
            f"IP address egress targets are forbidden: '{host_lower}'."
        )

    # 3. Reject local/private domain names
    if (
        host_lower == "localhost"
        or host_lower.endswith(".local")
        or host_lower.endswith(".internal")
        or host_lower.endswith(".corp")
    ):
        raise SSRFSecurityError(
            f"Local/internal egress targets are forbidden: '{host_lower}'."
        )

    # 4. Port must be 443 or default None
    if parsed.port is not None and parsed.port != 443:
        raise SSRFSecurityError(
            f"Non-standard HTTPS port {parsed.port} is forbidden."
        )

    # 5. Provider specific allowlist
    provider_key = provider.lower()
    if provider_key not in _OFFICIAL_ENDPOINTS:
        raise SSRFSecurityError(
            f"Provider '{provider}' has no recognized official egress policy."
        )

    # Special check for Alibaba: domestic vs Singapore international
    if provider_key == "alibaba":
        if host_lower == _DOMESTIC_ALIBABA_HOST:
            if not allow_domestic_alibaba:
                raise SSRFSecurityError(
                    "Domestic Alibaba Cloud endpoint 'dashscope.aliyuncs.com' is rejected. "
                    "Only Singapore International ('dashscope-intl.aliyuncs.com' or "
                    "'*.ap-southeast-1.maas.aliyuncs.com') is authorized."
                )
            return url

        if host_lower == "dashscope-intl.aliyuncs.com":
            return url

        if _ALIBABA_SINGAPORE_DEDICATED_PATTERN.match(host_lower):
            return url

        raise SSRFSecurityError(
            f"Host '{host_lower}' is not an authorized Alibaba Singapore International endpoint."
        )

    official_hosts = _OFFICIAL_ENDPOINTS[provider_key]
    if host_lower not in official_hosts:
        raise SSRFSecurityError(
            f"Host '{host_lower}' is not authorized for provider '{provider}'. "
            f"Allowed: {official_hosts}."
        )

    return url


def validate_tool_execution(
    tool_name: str,
    *,
    is_paid_tool: bool = False,
    is_web_browsing: bool = False,
    operator_authorized: bool = False,
) -> bool:
    """Enforce safe defaults: paid tools and browsing are blocked unless operator authorizes."""
    if (is_paid_tool or is_web_browsing) and not operator_authorized:
        raise SecurityPolicyError(
            f"Tool '{tool_name}' requires explicit operator authorization for paid/browsing execution."
        )
    return True


# ---------------------------------------------------------------------------
# 3. Dual Gate of Activation & Consent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Gate1OperatorApproval:
    """Gate 1: Operator administrative qualification in the lab.

    In accordance with ADR 0014: absence of a credit card ('no_credit_card_attached')
    does NOT prove free-tier availability or authorize execution.
    """

    provider_id: str
    model_id: str
    scope: str
    verified_free_tier: bool = False
    no_credit_card_attached: bool = False
    operator_approved: bool = False

    def __post_init__(self) -> None:
        if self.no_credit_card_attached and not self.verified_free_tier:
            raise SecurityPolicyError(
                "A ausência de cartão de crédito não comprova gratuidade nem autoriza execução."
            )

    def is_qualified(self) -> bool:
        """Return True only if explicitly approved and free tier is verified."""
        return self.operator_approved and self.verified_free_tier


@dataclass
class Gate2ExecutionConsent:
    """Gate 2: Dynamic runtime execution consent from the operator."""

    risk_acknowledged: bool = False
    allowed_route_ids: frozenset[str] = field(default_factory=frozenset)
    paid_fallback_authorized: bool = False
    max_estimated_brl: Decimal = Decimal("0")
    revoked: bool = False

    def __post_init__(self) -> None:
        if not self.max_estimated_brl.is_finite() or self.max_estimated_brl < 0:
            raise ValueError("O teto financeiro estimado deve ser um valor decimal não negativo.")

    def revoke(self) -> None:
        """Immediately revoke consent, invalidating in-flight and future executions."""
        self.revoked = True

    def validate_for_route(
        self,
        route_id: str,
        *,
        is_paid: bool = False,
        estimated_cost: Decimal = Decimal("0"),
    ) -> None:
        """Assert that this consent authorizes the requested route and economics."""
        if self.revoked:
            raise ConsentRevokedError("O consentimento de execução foi revogado pelo operador.")
        if not self.risk_acknowledged:
            raise SecurityPolicyError(
                "Execução bloqueada: o risco de cobrança deve ser expressamente reconhecido."
            )
        if route_id not in self.allowed_route_ids:
            raise SecurityPolicyError(
                f"Execução bloqueada: a rota '{route_id}' não consta na allowlist de consentimento."
            )
        if is_paid:
            if not self.paid_fallback_authorized:
                raise SecurityPolicyError(
                    f"Execução bloqueada: rota paga '{route_id}' requer autorização financeira explícita."
                )
            if estimated_cost > self.max_estimated_brl:
                raise SecurityPolicyError(
                    f"Execução bloqueada: custo estimado R$ {estimated_cost} excede o teto aprovado "
                    f"de R$ {self.max_estimated_brl}."
                )


# ---------------------------------------------------------------------------
# 4. Anti-Quota-Bypass & Fallback Guardrails
# ---------------------------------------------------------------------------


class QuotaBypassDetector:
    """Enforce that multiple keys under the same organization cannot be rotated to bypass quotas."""

    def __init__(self) -> None:
        # org_id -> set of registered key hashes
        self._org_keys: dict[str, set[str]] = {}

    def register_key(self, org_id: str, key: str) -> None:
        """Register a key under an organization scope."""
        if not org_id or not key:
            return
        if org_id not in self._org_keys:
            self._org_keys[org_id] = set()
        self._org_keys[org_id].add(key)

    def assert_no_bypass_rotation(
        self,
        org_id: str,
        current_key: str,
        attempted_new_key: str,
    ) -> None:
        """Reject key rotation for the same organization after a quota/rate-limit failure."""
        if org_id and current_key and attempted_new_key and current_key != attempted_new_key:
            raise QuotaBypassAttemptError(
                f"Tentativa de contornar cota detectada: rotação de chave proibida "
                f"para a organização '{org_id}'."
            )


# ---------------------------------------------------------------------------
# 5. Error Sanitization & Negative Scenario Classification
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SanitizedSecurityOutcome:
    """Normalized, sanitized error outcome containing zero secrets."""

    classification: str  # 'auth_failure', 'quota_exhausted', 'rate_limit', 'indeterminate', 'forbidden'
    sanitized_message: str
    retryable_in_0800: bool
    status_code: int | None = None


def classify_and_sanitize_provider_error(
    error: Exception | int,
    provider: str,
    raw_error_text: str = "",
    *,
    content_started: bool = False,
    side_effect_uncertain: bool = False,
    additional_secrets: tuple[str, ...] = (),
) -> SanitizedSecurityOutcome:
    """Sanitize and classify provider errors to ensure fail-closed and zero leaks."""
    status_code: int | None = None
    if isinstance(error, int):
        status_code = error
        error_name = str(error)
    else:
        status_code = getattr(error, "status_code", getattr(error, "code", None))
        error_name = type(error).__name__

    cleaned_text = redact_sensitive_text(
        f"{error_name} {raw_error_text}".strip(), additional_secrets
    )

    # 1. Uncertainty / Partial generation fail-closed
    if content_started or side_effect_uncertain:
        return SanitizedSecurityOutcome(
            classification="indeterminate",
            sanitized_message="A execução externa falhou com estado indeterminado ou parcial; não será retentada.",
            retryable_in_0800=False,
            status_code=status_code,
        )

    # 2. HTTP 401 Unauthorized
    if status_code == 401:
        return SanitizedSecurityOutcome(
            classification="auth_failure",
            sanitized_message=f"Falha de autenticação no provedor '{provider}'. Credencial inválida ou revogada.",
            retryable_in_0800=False,
            status_code=401,
        )

    # 3. HTTP 403 Forbidden / Quota Exhaustion
    if status_code == 403:
        if "allocationquota.freetieronaly" in cleaned_text.lower() or "freetieronly" in cleaned_text.lower():
            return SanitizedSecurityOutcome(
                classification="quota_exhausted",
                sanitized_message=(
                    f"Franquia gratuita esgotada no provedor '{provider}' "
                    f"(AllocationQuota.FreeTierOnly). Execução bloqueada sem fallback pago."
                ),
                retryable_in_0800=False,
                status_code=403,
            )
        return SanitizedSecurityOutcome(
            classification="forbidden",
            sanitized_message=f"Acesso negado no provedor '{provider}'. Verifique escopo e permissões.",
            retryable_in_0800=False,
            status_code=403,
        )

    # 4. HTTP 429 Rate Limit
    if status_code == 429 or "rate limit" in cleaned_text.lower() or "too many requests" in cleaned_text.lower():
        return SanitizedSecurityOutcome(
            classification="rate_limit",
            sanitized_message=f"Limite de taxa (rate limit) atingido no provedor '{provider}'.",
            retryable_in_0800=True,
            status_code=429,
        )

    # 5. Default / Unknown
    return SanitizedSecurityOutcome(
        classification="indeterminate",
        sanitized_message=f"A execução externa no provedor '{provider}' falhou.",
        retryable_in_0800=False,
        status_code=status_code,
    )


# ---------------------------------------------------------------------------
# 6. Input Security Validation
# ---------------------------------------------------------------------------


def validate_secure_inputs(task: str, context: str | None = None) -> tuple[str, str | None]:
    """Validate task and context inputs, preventing lone surrogates and control escapes."""
    if not isinstance(task, str) or not task.strip():
        raise ValueError("A tarefa (task) é obrigatória e deve conter texto válido.")

    # Check for Unicode lone surrogates (0xD800 to 0xDFFF)
    for c in task:
        if 0xD800 <= ord(c) <= 0xDFFF:
            raise ValueError("A tarefa contém caracteres Unicode inválidos (surrogates isolados).")

    cleaned_context: str | None = None
    if context is not None:
        if not isinstance(context, str) or not context.strip():
            raise ValueError("O contexto (context), quando informado, deve conter texto válido.")
        for c in context:
            if 0xD800 <= ord(c) <= 0xDFFF:
                raise ValueError("O contexto contém caracteres Unicode inválidos (surrogates isolados).")
        cleaned_context = context

    return task, cleaned_context
