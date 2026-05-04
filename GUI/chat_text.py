"""Shared chat text helpers for sentence-sized display chunks."""

from __future__ import annotations

SENTENCE_DELIMITERS = "。！？!?\n"
NORMAL_SENTENCE_DELAY_SECONDS = 0.28
NORMAL_CHARACTER_DELAY_SECONDS = 0.035


def consume_complete_sentence(value: str) -> tuple[str | None, str]:
    """Return the first complete sentence and the remaining text."""
    for index, char in enumerate(value):
        if char in SENTENCE_DELIMITERS:
            sentence = value[: index + 1].strip()
            rest = value[index + 1 :].lstrip()
            return sentence, rest
    return None, value


def split_display_sentences(value: str) -> list[str]:
    """Split text into display sentences without changing stored content."""
    pending = value.strip()
    if not pending:
        return []

    sentences: list[str] = []
    while pending:
        sentence, pending = consume_complete_sentence(pending)
        if sentence is None:
            tail = pending.strip()
            if tail:
                sentences.append(tail)
            break
        if sentence:
            sentences.append(sentence)
    return sentences
