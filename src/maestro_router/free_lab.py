"""Opt-in local HTTP composition for FREE-LAB. No changes to public v1."""
from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .free_fallback import (
    FreeOrchestrator, FreeRoute, Limits, RejectedBeforeGeneration, SlidingQuota,
)


class PromptBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    task: str = Field(min_length=1, max_length=6000)


def _enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() == "yes"


def _limits(prefix: str) -> Limits | None:
    names = [f"MAESTRO_{prefix}_{key}" for key in ("RPM", "RPD", "TPM", "TPD")]
    if not all(os.environ.get(name) for name in names):
        return None
    try:
        return Limits(*(int(os.environ[name]) for name in names))
    except ValueError:
        return None


class OpenAIChatAdapter:
    """OpenAI-compatible non-streaming Chat, used only by Groq/Cerebras."""
    def __init__(self, api_key: str, endpoint: str):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key=api_key, base_url=endpoint,
                                  max_retries=0, timeout=20)

    async def execute(self, route: FreeRoute, prompt: str, max_output_tokens: int) -> str:
        from openai import RateLimitError
        try:
            result = await self.client.chat.completions.create(
                model=route.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_output_tokens,
                stream=False,
            )
            return result.choices[0].message.content or ""
        except RateLimitError as exc:
            raise RejectedBeforeGeneration from exc
        # Any other error is ambiguous and stops auto-fallback.


class GeminiTextAdapter:
    """Gemini Interactions: stateless, bounded, no automatic continuation."""
    def __init__(self, api_key: str):
        from google import genai
        self.client = genai.Client(api_key=api_key)

    async def execute(self, route: FreeRoute, prompt: str, max_output_tokens: int) -> str:
        # No retries and no fallback after ambiguous Gemini errors.
        try:
            response = await self.client.aio.interactions.create(
                model=route.model,
                input=[{"type": "text", "text": prompt}],
                store=False, automatic_continuation=False,
                generation_config={"max_output_tokens": max_output_tokens},
            )
        except Exception as exc:
            if getattr(exc, "status_code", None) == 429:
                raise RejectedBeforeGeneration from exc
            raise
        if getattr(response, "status", None) != "completed":
            raise ValueError("Incomplete or blocked response")
        answer = getattr(response, "output_text", None)
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("Invalid Gemini output")
        return answer


def _build() -> FreeOrchestrator:
    routes: list[FreeRoute] = []
    adapters: dict[str, Any] = {}

    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key and _enabled("MAESTRO_GROQ_FREE_CONFIRMED"):
        adapters["groq"] = OpenAIChatAdapter(groq_key, "https://api.groq.com/openai/v1")
        # Values supplied by operator's Nov 11, 2026 organization limits.
        # These are LOCAL caps, not proof of free-tier eligibility or real balance.
        for model, suffix in (
            ("openai/gpt-oss-20b", "20b"),
            ("openai/gpt-oss-120b", "120b"),
        ):
            routes.append(FreeRoute(
                id="groq-" + suffix, provider="groq", model=model,
                scope="groq-org-" + suffix, limits=Limits(30, 1000, 8000, 200000),
                verified_free_by_operator=True,
            ))

    gemini_key = os.environ.get("GEMINI_API_KEY")
    gemini_limits = _limits("GEMINI")
    gemini_model = os.environ.get("MAESTRO_GEMINI_MODEL")
    if (gemini_key and gemini_limits and gemini_model
            and _enabled("MAESTRO_GEMINI_FREE_CONFIRMED")):
        adapters["gemini"] = GeminiTextAdapter(gemini_key)
        routes.append(FreeRoute(
            "gemini-free", "gemini", gemini_model,
            "gemini-project", gemini_limits, True,
        ))

    cerebras_key = os.environ.get("CEREBRAS_API_KEY")
    cerebras_limits = _limits("CEREBRAS")
    cerebras_model = os.environ.get("MAESTRO_CEREBRAS_MODEL")
    if (cerebras_key and cerebras_limits and cerebras_model
            and _enabled("MAESTRO_CEREBRAS_FREE_CONFIRMED")):
        adapters["cerebras"] = OpenAIChatAdapter(
            cerebras_key, "https://api.cerebras.ai/v1"
        )
        routes.append(FreeRoute(
            "cerebras-free", "cerebras", cerebras_model,
            "cerebras-org", cerebras_limits, True,
        ))

    # Try one route per provider before a second Groq model, where possible.
    routes.sort(key=lambda route: route.id == "groq-120b")
    return FreeOrchestrator(tuple(routes), adapters, SlidingQuota())


def create_free_lab_app() -> FastAPI:
    """Separate experimental app; requires two explicit runtime permissions."""
    app = FastAPI(title="Maestro 0800 LAB", docs_url=None, redoc_url=None)
    runner = _build()
    enabled = _enabled("MAESTRO_FREE_LAB_LIVE") and _enabled("MAESTRO_FREE_LAB_RISK_ACK")

    @app.get("/lab/status")
    async def status():
        return {
            "live_enabled": enabled,
            "routes": [
                {"id": r.id, "provider": r.provider, "model": r.model}
                for r in runner.routes
            ],
            "quota_kind": "in_memory_local_reservations_not_provider_balance",
        }

    @app.post("/lab/execute")
    async def execute(body: PromptBody):
        outcome = await runner.run(body.task, live_allowed=enabled)
        status = {
            "completed": 200, "invalid_request": 400, "disabled": 403,
            "blocked": 429, "indeterminate": 502,
        }[outcome.status]
        return JSONResponse(status_code=status, content={
            "status": outcome.status,
            "route": outcome.route,
            "answer": outcome.answer,
            "attempts": [
                {"route": route, "status": state}
                for route, state in outcome.attempts
            ],
            "real_billing": "unknown",
        })

    return app
