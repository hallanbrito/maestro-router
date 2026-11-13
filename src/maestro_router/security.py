"""MAESTRO-0800 Security Controls, Guardrails, Egress Validation, and Redaction.

This module implements offline-first security primitives for the MAESTRO-0800 track:
1. Credential scoping, redaction of secrets in text, errors, headers, and diff scanner.
2. Dual-gate activation and runtime consent (enforcing 'no credit card != spend authorization').
3. Official endpoint static egress validation and SSRF mitigation.
4. No-cost fallback guardrails, anti-quota-bypass protection, and fail-closed uncertainty handling.
5. Error sanitization and negative response classification (401, 403, 429, indeterminate).
6. Unicode input integrity and boundary payload encapsulation.
7. Deterministic offline 0800 safe fallback executor.

NOTICE: These guardrails are currently offline architectural primitives and are not yet
coupled to the production runtime. Real-time provider quota verification depends on AGY-01.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Mapping
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


class ScopeMismatchError(SecurityPolicyError):
    """Raised when route parameters mismatch Gate 1 approved provider, model, or scope."""

    pass


class QuotaBypassAttemptError(SecurityError):
    """Raised when multiple keys are rotated within the same shared quota scope to bypass limits."""

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
    """Represents a potential secret identified by the offline security scanner.

    Does NOT expose or store plaintext secret fragments or previews.
    Uses SHA-256 fingerprint for correlation without credential leakage.
    """

    secret_type: str
    line_number: int
    fingerprint: str
    match_length: int


def _compute_secret_fingerprint(secret: str) -> str:
    """Return a truncated SHA-256 hex digest of the secret for safe correlation."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:16]


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
    """Scan arbitrary text and report any secret patterns detected.

    Produces non-leaking metadata with cryptographic fingerprints, never raw fragments.
    """
    findings: list[SecretFinding] = []
    lines = text.splitlines()

    for idx, line in enumerate(lines, start=1):
        for match in _OPENAI_KEY_PATTERN.finditer(line):
            val = match.group()
            findings.append(
                SecretFinding(
                    secret_type="openai_key",
                    line_number=idx,
                    fingerprint=_compute_secret_fingerprint(val),
                    match_length=len(val),
                )
            )
        for match in _GROQ_KEY_PATTERN.finditer(line):
            val = match.group()
            findings.append(
                SecretFinding(
                    secret_type="groq_key",
                    line_number=idx,
                    fingerprint=_compute_secret_fingerprint(val),
                    match_length=len(val),
                )
            )
        for match in _GOOGLE_KEY_PATTERN.finditer(line):
            val = match.group()
            findings.append(
                SecretFinding(
                    secret_type="google_key",
                    line_number=idx,
                    fingerprint=_compute_secret_fingerprint(val),
                    match_length=len(val),
                )
            )
        for match in _DASHSCOPE_KEY_PATTERN.finditer(line):
            val = match.group()
            findings.append(
                SecretFinding(
                    secret_type="dashscope_key",
                    line_number=idx,
                    fingerprint=_compute_secret_fingerprint(val),
                    match_length=len(val),
                )
            )
        for match in _BEARER_TOKEN_PATTERN.finditer(line):
            val = match.group(1)
            findings.append(
                SecretFinding(
                    secret_type="bearer_token",
                    line_number=idx,
                    fingerprint=_compute_secret_fingerprint(val),
                    match_length=len(val),
                )
            )

    return findings


def scan_diff_for_secrets(diff_text: str) -> list[SecretFinding]:
    """Scan unified diff text (only added lines starting with '+') for secret leaks.

    This is an offline static helper, not an automatic mandatory CI step.
    """
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
                    fingerprint=finding.fingerprint,
                    match_length=finding.match_length,
                )
            )
    return findings


# ---------------------------------------------------------------------------
# 2. Official Egress & Static SSRF Validation
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
    """Return True if host is a literal IPv4 or IPv6 address or numeric representation."""
    clean_host = host.strip("[]")
    try:
        ipaddress.ip_address(clean_host)
        return True
    except ValueError:
        pass

    # Check for integer/hex/octal representations (e.g., 2130706433 or 0177.0.0.1)
    if clean_host.isdigit():
        return True
    parts = clean_host.split(".")
    if len(parts) == 4 and all(p.isdigit() or p.startswith(("0x", "0X")) for p in parts):
        return True

    return False


def validate_egress_endpoint(url: str, provider: str) -> str:
    """Perform STATIC URL and host validation for provider egress.

    IMPORTANT: This is a static URL/hostname validation only. It does NOT perform
    real DNS resolution, TLS handshake verification, SNI inspection, or HTTP
    redirect tracing, which require live external network I/O.

    Strict rules:
    - Scheme must be strictly HTTPS.
    - Userinfo (username/password in URL) is rejected.
    - IP addresses and loopback/private hosts are rejected.
    - Ports other than 443 (or default) are rejected.
    - Domestic Alibaba endpoint ('dashscope.aliyuncs.com') is unconditionally rejected.
    - Domain must match provider official allowlist.

    Raises:
        SSRFSecurityError: If URL violates any static security constraint.
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

    # 2. Reject URLs containing userinfo (credentials embedded in URL)
    if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
        raise SSRFSecurityError("Egress URL with userinfo credentials is forbidden.")

    # 3. Host validation
    host = parsed.hostname
    if not host:
        raise SSRFSecurityError("Egress URL has no valid hostname.")

    host_lower = host.lower()

    # 4. Reject any literal IP address
    if is_ip_address(host_lower):
        raise SSRFSecurityError(
            f"IP address egress targets are forbidden: '{host_lower}'."
        )

    # 5. Reject local/private domain names
    if (
        host_lower == "localhost"
        or host_lower.endswith(".local")
        or host_lower.endswith(".internal")
        or host_lower.endswith(".corp")
        or host_lower.endswith(".lan")
        or host_lower.endswith(".home")
    ):
        raise SSRFSecurityError(
            f"Local/internal egress targets are forbidden: '{host_lower}'."
        )

    # 6. Port must be 443 or default None
    try:
        port = parsed.port
    except ValueError as exc:
        raise SSRFSecurityError(f"Malformed port in egress URL: {exc}") from exc

    if port is not None and port != 443:
        raise SSRFSecurityError(
            f"Non-standard HTTPS port {port} is forbidden. Only port 443 is permitted."
        )

    # 7. Provider specific allowlist
    provider_key = provider.lower()
    if provider_key not in _OFFICIAL_ENDPOINTS:
        raise SSRFSecurityError(
            f"Provider '{provider}' has no recognized official egress policy."
        )

    # Alibaba: domestic China endpoint is unconditionally rejected
    if provider_key == "alibaba":
        if host_lower == _DOMESTIC_ALIBABA_HOST:
            raise SSRFSecurityError(
                "Domestic Alibaba Cloud endpoint 'dashscope.aliyuncs.com' is rejected. "
                "Only Singapore International ('dashscope-intl.aliyuncs.com' or "
                "'*.ap-southeast-1.maas.aliyuncs.com') is authorized."
            )

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
# 3. Dual Gate of Activation & Consent with Evidence Contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FreeTierEvidence:
    """Contractual offline evidence proving legitimate free tier entitlement.

    Real-time online verification with provider quota APIs is blocked pending
    homologation of the AGY-01 specification (PR #67).
    """

    evidence_type: str  # e.g., 'official_documentation', 'console_proof', 'terms_of_service'
    source_reference: str  # URL or document path
    account_or_project_id: str
    is_verified: bool = False

    def __post_init__(self) -> None:
        if not self.evidence_type or not self.source_reference or not self.account_or_project_id:
            raise ValueError("Campos obrigatórios de evidência não podem ser vazios.")


@dataclass(frozen=True)
class Gate1OperatorApproval:
    """Gate 1: Operator administrative qualification in the lab.

    In accordance with ADR 0014: absence of a credit card ('no_credit_card_attached')
    does NOT prove free-tier availability or authorize execution.
    Requires verified FreeTierEvidence.
    """

    provider_id: str
    model_id: str
    scope: str
    evidence: FreeTierEvidence | None = None
    no_credit_card_attached: bool = False
    operator_approved: bool = False

    def __post_init__(self) -> None:
        if self.no_credit_card_attached and not self.is_qualified():
            raise SecurityPolicyError(
                "A ausência de cartão de crédito não comprova gratuidade nem autoriza execução."
            )
        if self.evidence is not None and self.evidence.account_or_project_id != self.scope:
            raise SecurityPolicyError(
                f"Incompatibilidade de escopo na evidência: escopo da aprovação '{self.scope}' "
                f"não coincide com o escopo da evidência '{self.evidence.account_or_project_id}'."
            )

    def is_qualified(self) -> bool:
        """Return True only if explicitly approved and evidence is verified."""
        return (
            self.operator_approved
            and self.evidence is not None
            and self.evidence.is_verified
        )


@dataclass
class Gate2ExecutionConsent:
    """Gate 2: Dynamic runtime execution consent from the operator.

    Under ADR 0014 for Trilha 0800:
    - Zero fallback pago is permitted (no paid routes or budget ceilings in 0800 gate).
    - Defaults that omit economic classification are strictly forbidden.
    - Revocation marks consent as invalid; subsequent evaluations and retries fail closed.
      (Does not cancel in-flight network sockets already dispatched).
    """

    risk_acknowledged: bool = False
    allowed_route_ids: frozenset[str] = field(default_factory=frozenset)
    revoked: bool = False

    def revoke(self) -> None:
        """Immediately revoke consent in memory.

        Subsequent validations and retry attempts fail closed immediately.
        """
        self.revoked = True

    def validate_for_route(
        self,
        route_id: str,
        *,
        economic_tier: str,
        estimated_cost: Decimal,
    ) -> None:
        """Assert that this consent authorizes the requested route under strict 0800 economics.

        No defaults: caller MUST supply economic_tier and estimated_cost explicitly.
        """
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

        # R1-02: Strict economic validation - zero fallback pago in 0800
        if (
            not isinstance(economic_tier, str)
            or economic_tier.strip().lower() not in {"free", "free_tier", "0800"}
        ):
            raise SecurityPolicyError(
                f"Execução bloqueada: classificação econômica desconhecida ou não gratuita ('{economic_tier}'). "
                f"Trilha 0800 exige gratuidade comprovada sem fallback pago."
            )

        if (
            not isinstance(estimated_cost, Decimal)
            or not estimated_cost.is_finite()
            or estimated_cost != Decimal("0")
        ):
            raise SecurityPolicyError(
                f"Execução bloqueada: custo estimado '{estimated_cost}' inválido ou diferente de zero. "
                f"Trilha 0800 proíbe rotas com custo previsto superior a R$ 0,00."
            )


@dataclass(frozen=True)
class RouteDescriptor:
    """Specification of an operational route candidate for dual-gate verification."""

    route_id: str
    provider_id: str
    model_id: str
    scope: str
    economic_tier: str
    estimated_cost: Decimal


def validate_route_dual_gate(
    route: RouteDescriptor,
    gate1: Gate1OperatorApproval,
    consent: Gate2ExecutionConsent,
) -> None:
    """Validate binding between Route, Gate 1 qualification, and Gate 2 runtime consent.

    Raises:
        ConsentRevokedError: If consent is revoked.
        ScopeMismatchError: If route parameters mismatch Gate 1 approval.
        SecurityPolicyError: If Gate 1 is unqualified or Gate 2 rejects route.
    """
    # 1. Gate 2 checks (revocation, allowlist, economics)
    consent.validate_for_route(
        route.route_id,
        economic_tier=route.economic_tier,
        estimated_cost=route.estimated_cost,
    )

    # 2. Gate 1 qualification check
    if not gate1.is_qualified():
        raise SecurityPolicyError(
            f"Execução bloqueada: rota '{route.route_id}' não possui qualificação válida de Gate 1."
        )

    # 3. Scope binding checks (provider, model, scope)
    if route.provider_id.lower() != gate1.provider_id.lower():
        raise ScopeMismatchError(
            f"Mismatch de provedor: rota '{route.route_id}' tem provedor '{route.provider_id}', "
            f"mas Gate 1 aprovou '{gate1.provider_id}'."
        )
    if route.model_id != gate1.model_id:
        raise ScopeMismatchError(
            f"Mismatch de modelo: rota '{route.route_id}' tem modelo '{route.model_id}', "
            f"mas Gate 1 aprovou '{gate1.model_id}'."
        )
    if route.scope != gate1.scope:
        raise ScopeMismatchError(
            f"Mismatch de escopo: rota '{route.route_id}' tem escopo '{route.scope}', "
            f"mas Gate 1 aprovou '{gate1.scope}'."
        )


# ---------------------------------------------------------------------------
# 4. Anti-Quota-Bypass Protection & Key Fingerprinting
# ---------------------------------------------------------------------------


class QuotaBypassDetector:
    """Enforce that multiple keys under the same shared quota scope cannot be rotated to bypass quotas.

    Stores cryptographic SHA-256 fingerprints, never plaintext keys.
    Distinguishes shared quota scopes from proven independent scopes.
    """

    def __init__(self) -> None:
        # (provider_id, quota_scope) -> set of registered key fingerprints (SHA-256)
        self._scope_key_fingerprints: dict[tuple[str, str], set[str]] = {}

    def register_key(self, provider_id: str, quota_scope: str, key: str) -> str:
        """Register a key fingerprint under an explicit provider and quota scope."""
        if not key or not provider_id or not quota_scope:
            return ""
        fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()
        scope_key = (provider_id.lower(), quota_scope)
        if scope_key not in self._scope_key_fingerprints:
            self._scope_key_fingerprints[scope_key] = set()
        self._scope_key_fingerprints[scope_key].add(fingerprint)
        return fingerprint

    def assert_no_bypass_rotation(
        self,
        provider_id: str,
        quota_scope: str,
        current_key_fingerprint: str,
        attempted_key_fingerprint: str,
        *,
        is_independent_scope: bool = False,
    ) -> None:
        """Reject rotating keys under the same shared quota scope after an exhaustion event.

        Proven independent quota scopes (is_independent_scope=True) are permitted
        and not treated as a bypass attempt.
        """
        if is_independent_scope:
            return
        if (
            current_key_fingerprint
            and attempted_key_fingerprint
            and current_key_fingerprint != attempted_key_fingerprint
        ):
            raise QuotaBypassAttemptError(
                f"Tentativa de contornar cota detectada: rotação de chave proibida "
                f"para o escopo compartilhado '{quota_scope}' do provedor '{provider_id}'."
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
        if "allocationquota.freetieronly" in cleaned_text.lower() or "freetieronly" in cleaned_text.lower():
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
# 6. Unicode Input Integrity & Boundary Payload Encapsulation
# ---------------------------------------------------------------------------


def validate_unicode_input_safety(task: str, context: str | None = None) -> tuple[str, str | None]:
    """Validate Unicode integrity and type constraints on inputs.

    LIMITATION NOTICE: This function performs Unicode surrogate validation and string type
    checking only. It does NOT constitute a semantic defense against prompt injection or jailbreaks.
    Architectural boundary isolation relies on treating user inputs as inert data fields.
    """
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


# Backwards compatibility alias
validate_secure_inputs = validate_unicode_input_safety


def encapsulate_user_payload(task: str, context: str | None = None) -> dict[str, Any]:
    """Encapsulate user inputs as inert data payload, isolating them from system router instructions."""
    validated_task, validated_context = validate_unicode_input_safety(task, context)
    return {
        "role": "user",
        "content": validated_task,
        "context": validated_context,
        "is_inert_data": True,
    }


# ---------------------------------------------------------------------------
# 7. Deterministic Offline Safe Fallback Executor (R1-01, R1-03, R1-07)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OfflineDispatchAttempt:
    """Record of an attempt made during deterministic offline execution."""

    route_id: str
    provider_id: str
    model_id: str
    scope: str
    status: str  # 'dispatched', 'blocked_unauthorized', 'blocked_revoked', 'failed_retryable', 'failed_fatal'
    error_message: str | None = None


@dataclass(frozen=True)
class OfflineExecutionResult:
    """Result of deterministic offline 0800 execution."""

    state: str  # 'completed', 'blocked', 'exhausted', 'indeterminate'
    selected_route_id: str | None
    response_text: str | None
    attempts: tuple[OfflineDispatchAttempt, ...]


class DeterministicOffline0800Executor:
    """Deterministic offline executor demonstrating zero dispatches without valid authorization.

    Validates Gate 1 and Gate 2 before EVERY attempt and retry.
    Aborts immediately upon revocation without dispatching to subsequent candidate routes.
    """

    def __init__(
        self,
        gate1_approvals: Mapping[str, Gate1OperatorApproval],
        consent: Gate2ExecutionConsent,
    ) -> None:
        self._gate1_approvals = dict(gate1_approvals)
        self._consent = consent

    def execute(
        self,
        candidate_routes: tuple[RouteDescriptor, ...],
        dispatch_fn: Callable[[RouteDescriptor, dict[str, Any]], str],
        payload: dict[str, Any],
    ) -> OfflineExecutionResult:
        """Execute candidate routes deterministically under dual-gate guardrails.

        Returns OfflineExecutionResult detailing attempts and final state.
        """
        attempts: list[OfflineDispatchAttempt] = []

        for route in candidate_routes:
            # 1. Check revocation immediately before touching this route
            if self._consent.revoked:
                attempts.append(
                    OfflineDispatchAttempt(
                        route_id=route.route_id,
                        provider_id=route.provider_id,
                        model_id=route.model_id,
                        scope=route.scope,
                        status="blocked_revoked",
                        error_message="Consent revoked prior to dispatch attempt.",
                    )
                )
                return OfflineExecutionResult(
                    state="blocked",
                    selected_route_id=None,
                    response_text=None,
                    attempts=tuple(attempts),
                )

            # 2. Check Gate 1 existence
            gate1 = self._gate1_approvals.get(route.route_id)
            if gate1 is None:
                attempts.append(
                    OfflineDispatchAttempt(
                        route_id=route.route_id,
                        provider_id=route.provider_id,
                        model_id=route.model_id,
                        scope=route.scope,
                        status="blocked_unauthorized",
                        error_message="Gate 1 qualification missing for route.",
                    )
                )
                continue

            # 3. Validate dual gate (Gate 2 + Gate 1 + Scope binding)
            try:
                validate_route_dual_gate(route, gate1, self._consent)
            except ConsentRevokedError as exc:
                attempts.append(
                    OfflineDispatchAttempt(
                        route_id=route.route_id,
                        provider_id=route.provider_id,
                        model_id=route.model_id,
                        scope=route.scope,
                        status="blocked_revoked",
                        error_message=str(exc),
                    )
                )
                return OfflineExecutionResult(
                    state="blocked",
                    selected_route_id=None,
                    response_text=None,
                    attempts=tuple(attempts),
                )
            except SecurityPolicyError as exc:
                attempts.append(
                    OfflineDispatchAttempt(
                        route_id=route.route_id,
                        provider_id=route.provider_id,
                        model_id=route.model_id,
                        scope=route.scope,
                        status="blocked_unauthorized",
                        error_message=str(exc),
                    )
                )
                continue

            # 4. Dispatch to fake adapter
            try:
                response = dispatch_fn(route, payload)
                attempts.append(
                    OfflineDispatchAttempt(
                        route_id=route.route_id,
                        provider_id=route.provider_id,
                        model_id=route.model_id,
                        scope=route.scope,
                        status="dispatched",
                    )
                )
                return OfflineExecutionResult(
                    state="completed",
                    selected_route_id=route.route_id,
                    response_text=response,
                    attempts=tuple(attempts),
                )
            except Exception as exc:
                outcome = classify_and_sanitize_provider_error(exc, route.provider_id)
                if outcome.retryable_in_0800:
                    attempts.append(
                        OfflineDispatchAttempt(
                            route_id=route.route_id,
                            provider_id=route.provider_id,
                            model_id=route.model_id,
                            scope=route.scope,
                            status="failed_retryable",
                            error_message=outcome.sanitized_message,
                        )
                    )
                    continue  # Fallback to next candidate
                else:
                    attempts.append(
                        OfflineDispatchAttempt(
                            route_id=route.route_id,
                            provider_id=route.provider_id,
                            model_id=route.model_id,
                            scope=route.scope,
                            status="failed_fatal",
                            error_message=outcome.sanitized_message,
                        )
                    )
                    return OfflineExecutionResult(
                        state="indeterminate" if outcome.classification == "indeterminate" else "blocked",
                        selected_route_id=None,
                        response_text=None,
                        attempts=tuple(attempts),
                    )

        # All candidate routes exhausted or blocked
        return OfflineExecutionResult(
            state="exhausted",
            selected_route_id=None,
            response_text=None,
            attempts=tuple(attempts),
        )
