from __future__ import annotations

import re


def clean_transcript(value: object) -> str:
    text = str(value).strip()
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text


_HESITATION = re.compile(
    r"(?<![\w-])(?:э+(?:[\s-]+э+)*|эм+|м-м+|а-а+)(?![\w-])[,;:]?\s*",
    re.IGNORECASE,
)
_SAFE_FILLER_PHRASES = (
    "как бы",
    "грубо говоря",
    "так сказать",
    "короче говоря",
    "в общем-то",
    "в общем",
    "скажем так",
)
_FULL_FILLER_WORDS = (
    "ну",
    "значит",
    "типа",
    "соответственно",
    "короче",
)


def remove_filler_words(value: object, mode: str = "soft") -> str:
    """Remove conversational fillers without changing meaningful uses."""
    text = clean_transcript(value)
    if mode == "off" or not text:
        return text

    text = _HESITATION.sub("", text)
    text = _remove_opening_markers(text, ("ну",))
    text = re.sub(
        r"\b([\wёЁ]+)\b(?:\s+\1\b)+",
        r"\1",
        text,
        flags=re.IGNORECASE,
    )

    if mode == "full":
        phrases = "|".join(
            re.escape(phrase).replace(r"\ ", r"\s+")
            for phrase in _SAFE_FILLER_PHRASES
        )
        text = re.sub(
            rf"\s*,?\s*(?<!\w)(?:{phrases})(?!\w)\s*,?\s*",
            " ",
            text,
            flags=re.IGNORECASE,
        )
        text = _remove_opening_markers(text, _FULL_FILLER_WORDS + ("так", "вот"))
        words = "|".join(map(re.escape, _FULL_FILLER_WORDS))
        text = re.sub(
            rf",\s*(?:{words})\s*,",
            " ",
            text,
            flags=re.IGNORECASE,
        )

    text = _repair_punctuation(text)
    return _capitalize_sentences(text)


def _remove_opening_markers(text: str, markers: tuple[str, ...]) -> str:
    alternatives = "|".join(map(re.escape, markers))
    pattern = re.compile(
        rf"(^|(?<=[.!?])\s+)(?:{alternatives})\s*(?:[,;:]\s*|\s+)",
        re.IGNORECASE,
    )
    previous = None
    while previous != text:
        previous = text
        text = pattern.sub(r"\1", text)
    return text


def _repair_punctuation(text: str) -> str:
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r",\s*,+", ",", text)
    text = re.sub(r"(^|[.!?]\s+)[,;:]\s*", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" ,;:")


def _capitalize_sentences(text: str) -> str:
    return re.sub(
        r"(^|[.!?]\s+)([а-яёa-z])",
        lambda match: match.group(1) + match.group(2).upper(),
        text,
        flags=re.IGNORECASE,
    )


def merge_transcripts(parts: list[str], max_overlap_words: int = 64) -> str:
    """Join adjacent audio chunks while removing their exact shared passage.

    A one-second audio overlap can cause the recognizer to repeat more than a
    short phrase. Comparing up to 64 normalized words removes that duplicated
    boundary without deleting intentional repetition inside a single chunk.
    """
    merged: list[str] = []
    for part in parts:
        words = clean_transcript(part).split()
        if not words:
            continue
        if not merged:
            merged.extend(words)
            continue
        overlap = 0
        max_size = min(max_overlap_words, len(merged), len(words))
        for size in range(max_size, 0, -1):
            left = [word.casefold().strip(",.;:!?") for word in merged[-size:]]
            right = [word.casefold().strip(",.;:!?") for word in words[:size]]
            if left == right:
                overlap = size
                break
        merged.extend(words[overlap:])
    return clean_transcript(" ".join(merged))


def common_prefix_length(a: str, b: str) -> int:
    """Length of the shared leading text between two strings.

    Used to type only the delta between what is already on screen and a
    revised transcript, instead of retyping everything on every update.
    """
    limit = min(len(a), len(b))
    for index in range(limit):
        if a[index] != b[index]:
            return index
    return limit


def split_audio(
    audio,
    sample_rate: int = 16_000,
    chunk_seconds: int = 20,
    overlap_seconds: int = 1,
):
    chunk_size = chunk_seconds * sample_rate
    overlap = overlap_seconds * sample_rate
    if len(audio) <= chunk_size:
        return [audio]
    chunks = []
    start = 0
    while start < len(audio):
        end = min(len(audio), start + chunk_size)
        chunks.append(audio[start:end])
        if end == len(audio):
            break
        start = end - overlap
    return chunks
