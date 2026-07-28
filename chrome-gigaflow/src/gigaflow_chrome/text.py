from __future__ import annotations

import re


def clean_transcript(value: object) -> str:
    text = str(value).strip()
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return re.sub(r"\s{2,}", " ", text)


_HESITATION = re.compile(
    r"(?<![\w-])(?:э+(?:[\s-]+э+)*|эм+|м-м+|а-а+)(?![\w-])[,;:]?\s*",
    re.IGNORECASE,
)
_SAFE_PHRASES = (
    "как бы",
    "грубо говоря",
    "так сказать",
    "короче говоря",
    "в общем-то",
    "в общем",
    "скажем так",
)
_FULL_WORDS = ("ну", "значит", "типа", "соответственно", "короче")


def remove_filler_words(value: object, mode: str = "soft") -> str:
    text = clean_transcript(value)
    if mode == "off" or not text:
        return text
    text = _HESITATION.sub("", text)
    text = _remove_opening(text, ("ну",))
    text = re.sub(
        r"\b([\wёЁ]+)\b(?:\s+\1\b)+",
        r"\1",
        text,
        flags=re.IGNORECASE,
    )
    if mode == "full":
        phrases = "|".join(
            re.escape(phrase).replace(r"\ ", r"\s+") for phrase in _SAFE_PHRASES
        )
        text = re.sub(
            rf"\s*,?\s*(?<!\w)(?:{phrases})(?!\w)\s*,?\s*",
            " ",
            text,
            flags=re.IGNORECASE,
        )
        text = _remove_opening(text, _FULL_WORDS + ("так", "вот"))
        words = "|".join(map(re.escape, _FULL_WORDS))
        text = re.sub(
            rf",\s*(?:{words})\s*,",
            " ",
            text,
            flags=re.IGNORECASE,
        )
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r",\s*,+", ",", text)
    text = re.sub(r"(^|[.!?]\s+)[,;:]\s*", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" ,;:")
    return re.sub(
        r"(^|[.!?]\s+)([а-яёa-z])",
        lambda match: match.group(1) + match.group(2).upper(),
        text,
        flags=re.IGNORECASE,
    )


def _remove_opening(text: str, markers: tuple[str, ...]) -> str:
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


def merge_transcripts(parts: list[str], max_overlap_words: int = 12) -> str:
    merged: list[str] = []
    for part in parts:
        words = clean_transcript(part).split()
        if not words:
            continue
        if not merged:
            merged.extend(words)
            continue
        overlap = 0
        for size in range(min(max_overlap_words, len(merged), len(words)), 0, -1):
            left = [word.casefold().strip(",.;:!?") for word in merged[-size:]]
            right = [word.casefold().strip(",.;:!?") for word in words[:size]]
            if left == right:
                overlap = size
                break
        merged.extend(words[overlap:])
    return clean_transcript(" ".join(merged))


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
