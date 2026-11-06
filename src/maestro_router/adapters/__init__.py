"""Adaptadores concretos dos provedores externos suportados."""

from .google import GoogleGeminiInteractionsAdapter
from .openai import OpenAIResponsesAdapter

__all__ = [
    "GoogleGeminiInteractionsAdapter",
    "OpenAIResponsesAdapter",
]
