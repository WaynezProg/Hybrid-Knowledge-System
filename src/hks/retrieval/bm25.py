"""BM25 keyword ranking over chunk texts (query-time, no persisted index)."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence

_K1 = 1.2
_B = 0.75
_ASCII_TERM_RE = re.compile(r"[a-z0-9]{2,}")
_CJK_RUN_RE = re.compile(r"[一-鿿]{2,}")


def lexical_tokens(text: str) -> list[str]:
    """ASCII words and CJK bigrams, with repeats (the same units as ``lexical_terms``)."""
    tokens = _ASCII_TERM_RE.findall(text.lower())
    for run in _CJK_RUN_RE.findall(text):
        tokens.extend(run[index : index + 2] for index in range(len(run) - 1))
    return tokens


def bm25_rank(query: str, documents: Sequence[str], *, top_k: int) -> list[tuple[int, float]]:
    """``(document index, score)`` of the best matches, best first; no match, no entry."""
    query_terms = set(lexical_tokens(query))
    if not query_terms or not documents:
        return []

    frequencies = [Counter(lexical_tokens(document)) for document in documents]
    lengths = [sum(counts.values()) for counts in frequencies]
    average_length = sum(lengths) / len(lengths) or 1.0
    total = len(documents)

    scores = [0.0] * total
    for term in query_terms:
        containing = sum(1 for counts in frequencies if term in counts)
        if not containing:
            continue
        idf = math.log(1.0 + (total - containing + 0.5) / (containing + 0.5))
        for index, counts in enumerate(frequencies):
            frequency = counts.get(term, 0)
            if not frequency:
                continue
            norm = _K1 * (1.0 - _B + _B * lengths[index] / average_length)
            scores[index] += idf * frequency * (_K1 + 1.0) / (frequency + norm)

    ranked = sorted(
        ((index, score) for index, score in enumerate(scores) if score > 0.0),
        key=lambda item: (-item[1], item[0]),
    )
    return ranked[:top_k]
