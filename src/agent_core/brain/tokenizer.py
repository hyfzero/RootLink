"""Tokenizer routing and token estimation utilities."""

from __future__ import annotations

import logging
import math
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal, Optional, Protocol

logger = logging.getLogger(__name__)

TokenEstimator = Literal["hybrid_v1", "legacy_char_div4"]
TokenizerMode = Literal["auto", "provider", "heuristic"]
TokenSource = Literal["provider_tokenizer", "heuristic_fallback"]


def normalize_token_estimator(estimator: Optional[str]) -> TokenEstimator:
    """Normalize estimator name and fallback to default for unknown values."""
    if estimator == "legacy_char_div4":
        return "legacy_char_div4"
    return "hybrid_v1"


def normalize_tokenizer_mode(mode: Optional[str]) -> TokenizerMode:
    """Normalize tokenizer mode and fallback to auto for unknown values."""
    if mode == "provider":
        return "provider"
    if mode == "heuristic":
        return "heuristic"
    return "auto"


def _is_cjk_char(ch: str) -> bool:
    codepoint = ord(ch)
    return (
        0x4E00 <= codepoint <= 0x9FFF
        or 0x3400 <= codepoint <= 0x4DBF
        or 0xF900 <= codepoint <= 0xFAFF
        or 0x3040 <= codepoint <= 0x30FF
        or 0xAC00 <= codepoint <= 0xD7AF
    )


def _estimate_tokens_legacy_char_div4(text: str) -> int:
    return max(1, len(text) // 4)


def _estimate_tokens_hybrid_v1(text: str) -> int:
    cjk_chars = 0
    latin_letters = 0
    digits = 0
    punctuation = 0
    others = 0

    for ch in text:
        if ch.isspace():
            continue

        if _is_cjk_char(ch):
            cjk_chars += 1
            continue

        if ch.isascii():
            if ch.isalpha():
                latin_letters += 1
            elif ch.isdigit():
                digits += 1
            elif unicodedata.category(ch).startswith("P"):
                punctuation += 1
            else:
                others += 1
            continue

        category = unicodedata.category(ch)
        if ch.isdigit():
            digits += 1
        elif category.startswith("P"):
            punctuation += 1
        else:
            others += 1

    estimate = math.ceil(
        cjk_chars * 1.35
        + (latin_letters / 4.0)
        + (digits / 2.5)
        + (punctuation / 3.0)
        + (others * 0.8)
    )
    return max(1, estimate)


def estimate_tokens(text: str, estimator: TokenEstimator = "hybrid_v1") -> int:
    """Estimate token count with the configured heuristic estimator."""
    if not text:
        return 0
    normalized = normalize_token_estimator(estimator)
    if normalized == "legacy_char_div4":
        return _estimate_tokens_legacy_char_div4(text)
    return _estimate_tokens_hybrid_v1(text)


@dataclass
class TokenCountResult:
    """Token counting result."""

    tokens: int
    source: TokenSource


class TokenCounter(Protocol):
    """Token counter protocol."""

    source: TokenSource

    def count_text(self, text: str) -> int: ...

    def count_messages(self, messages: list[Any]) -> int: ...


class HeuristicTokenCounter:
    """Heuristic token counter."""

    source: TokenSource = "heuristic_fallback"

    def __init__(self, estimator: TokenEstimator = "hybrid_v1"):
        self.estimator = normalize_token_estimator(estimator)

    def count_text(self, text: str) -> int:
        return estimate_tokens(text, estimator=self.estimator)

    def count_messages(self, messages: list[Any]) -> int:
        return sum(self.count_text(_extract_message_text(m)) for m in messages)


class OpenAITiktokenCounter:
    """OpenAI tokenizer-backed counter. Requires optional tiktoken."""

    source: TokenSource = "provider_tokenizer"

    def __init__(self, model_name: str):
        import tiktoken  # optional dependency

        try:
            self._encoding = tiktoken.encoding_for_model(model_name)
        except Exception:
            self._encoding = tiktoken.get_encoding("cl100k_base")

    @classmethod
    def maybe_create(cls, model_name: str) -> Optional["OpenAITiktokenCounter"]:
        try:
            return cls(model_name)
        except Exception:
            return None

    def count_text(self, text: str) -> int:
        if not text:
            return 0
        return len(self._encoding.encode(text))

    def count_messages(self, messages: list[Any]) -> int:
        # OpenAI chat message framing adds overhead beyond raw content.
        # We keep this conservative and stable for budgeting.
        total = 0
        for message in messages:
            role = _extract_message_role(message)
            content = _extract_message_text(message)
            total += 4  # per-message framing overhead
            total += self.count_text(role)
            total += self.count_text(content)
        total += 2  # assistant priming overhead
        return max(total, 0)


class TokenizerResolver:
    """Resolve provider/model tokenizer or fallback estimator."""

    def __init__(
        self,
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        mode: TokenizerMode = "auto",
        fallback_estimator: TokenEstimator = "hybrid_v1",
    ):
        self.provider = (provider or "").lower()
        self.model = model or ""
        self.mode = normalize_tokenizer_mode(mode)
        self.fallback_estimator = normalize_token_estimator(fallback_estimator)
        self._counter: Optional[TokenCounter] = None

    def count_text(self, text: str) -> TokenCountResult:
        counter = self._resolve_counter()
        return TokenCountResult(tokens=counter.count_text(text), source=counter.source)

    def count_messages(self, messages: list[Any]) -> TokenCountResult:
        counter = self._resolve_counter()
        return TokenCountResult(tokens=counter.count_messages(messages), source=counter.source)

    def _resolve_counter(self) -> TokenCounter:
        if self._counter is not None:
            return self._counter

        fallback_counter = HeuristicTokenCounter(self.fallback_estimator)
        if self.mode == "heuristic":
            self._counter = fallback_counter
            return self._counter

        provider_counter = self._build_provider_counter()
        if provider_counter is not None:
            self._counter = provider_counter
            return self._counter

        if self.mode == "provider":
            logger.warning(
                "Tokenizer mode is 'provider' but provider tokenizer is unavailable for %s/%s; fallback to %s.",
                self.provider or "unknown",
                self.model or "unknown",
                self.fallback_estimator,
            )

        self._counter = fallback_counter
        return self._counter

    def _build_provider_counter(self) -> Optional[TokenCounter]:
        if self.provider == "openai":
            return OpenAITiktokenCounter.maybe_create(self.model)
        return None


def build_tokenizer_resolver(
    *,
    token_estimator: TokenEstimator = "hybrid_v1",
    model_config: Optional[Any] = None,
    tokenizer_mode: Optional[str] = None,
) -> TokenizerResolver:
    """Build resolver from estimator + optional model config."""
    fallback = normalize_token_estimator(token_estimator)
    provider = None
    model = None
    mode_value = tokenizer_mode

    if model_config is not None:
        provider = getattr(model_config, "provider", None)
        model = getattr(model_config, "name", None)
        if mode_value is None:
            mode_value = getattr(model_config, "tokenizer_mode", None)
        fallback = normalize_token_estimator(
            getattr(model_config, "tokenizer_fallback", fallback)
        )

    return TokenizerResolver(
        provider=provider,
        model=model,
        mode=normalize_tokenizer_mode(mode_value),
        fallback_estimator=fallback,
    )


def _extract_message_role(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("role", ""))

    role = getattr(message, "role", "")
    if hasattr(role, "value"):
        return str(role.value)
    return str(role)


def _extract_message_text(message: Any) -> str:
    if isinstance(message, dict):
        return _extract_content_text(message.get("content", ""))

    content = getattr(message, "content", "")
    return _extract_content_text(content)


def _extract_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        if "text" in content and isinstance(content["text"], str):
            return content["text"]
        return str(content.get("content", ""))
    if hasattr(content, "text") and isinstance(getattr(content, "text"), str):
        return getattr(content, "text")
    return str(content or "")
