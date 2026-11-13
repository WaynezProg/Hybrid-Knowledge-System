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
# Letters, then a number: "ERR-4012", "CVE-2031-7781", "vid236". In a question only "-",
# "_" or nothing may join the two ("top 10 risks" names no code); content may also use a
# space, so "Budget 135" answers a question about "Budget-135".
_COMPOUND = r"(?<![a-z0-9])([a-z]{2,})%s(\d+(?:[-_]\d+)*)(?![a-z0-9])"
_QUESTION_COMPOUND_RE = re.compile(_COMPOUND % "[-_]?")
_CONTENT_COMPOUND_RE = re.compile(_COMPOUND % "[-_ ]?")


def lexical_tokens(text: str) -> list[str]:
    """ASCII words and CJK bigrams, with repeats (the same units as ``lexical_terms``)."""
    tokens = _ASCII_TERM_RE.findall(text.lower())
    for run in _CJK_RUN_RE.findall(text):
        tokens.extend(run[index : index + 2] for index in range(len(run) - 1))
    return tokens


def _compound(match: re.Match[str]) -> str:
    return f"{match.group(1)}-{re.sub(r'[-_]', '-', match.group(2))}"


def _plain_identifier(term: str) -> bool:
    digits = sum(char.isdigit() for char in term)
    if not digits:
        return False
    if term.isdigit():
        return len(term) >= 3 and not (len(term) == 4 and term[:2] in {"19", "20"})
    # A name that only carries a digit inside it ("session2memory", "k8s", "i18n") is a
    # word, not a code. A code ends in its number ("v17r2") or is mostly digits ("8c5487a").
    return term[-1].isdigit() or digits >= 3


def identifier_terms(text: str) -> set[str]:
    """Terms that name one specific thing: ticket numbers, versions, codes, file names.

    Three kinds count:

    - a compound code, letters followed by a number with ``-``, ``_`` or nothing between
      them (``ERR-4012``, ``Atlas-10``, ``CVE-2031-7781``, ``vid236``). It is returned in one
      spelling, ``err-4012``, so ``VID236`` and ``VID-236`` are the same identifier, and a
      short number counts here because the letters make it specific;
    - another term that mixes letters and digits, when it ends in a digit or holds three
      or more (``v17r2``, ``8c5487a``), but not a name with a digit inside it
      (``session2memory``, ``k8s``);
    - a run of three or more digits that is not a plain year (``4012``, ``00001``).

    Short numbers and years on their own are left out: "top 10 risks" or "2026 roadmap"
    ask about a topic, and an answer need not repeat the number.
    """
    lowered = text.lower()
    found = {_compound(match) for match in _QUESTION_COMPOUND_RE.finditer(lowered)}
    rest = _QUESTION_COMPOUND_RE.sub(" ", lowered)
    found.update(term for term in lexical_tokens(rest) if _plain_identifier(term))
    return found


def holds_identifiers(required: set[str], text: str) -> bool:
    """Whether ``text`` mentions every identifier. A compound code is also found when the
    text writes it with a space ("Budget 135") or carries it further ("RFC-0193-2")."""
    if not required:
        return True
    plain = {term for term in required if "-" not in term}
    if plain and not plain <= set(lexical_tokens(text)):
        return False
    compounds = required - plain
    if not compounds:
        return True
    present = {_compound(match) for match in _CONTENT_COMPOUND_RE.finditer(text.lower())}
    return all(
        any(code == wanted or code.startswith(f"{wanted}-") for code in present)
        for wanted in compounds
    )


def _code_spellings(query: str) -> list[tuple[str, list[str]]]:
    """For each compound code in ``query``: its joined spelling ("vid236") and the terms
    the separated spelling is made of (["vid", "236"])."""
    spellings: list[tuple[str, list[str]]] = []
    for match in _QUESTION_COMPOUND_RE.finditer(query.lower()):
        pieces = [match.group(1), *re.split(r"[-_]", match.group(2))]
        spellings.append(("".join(pieces), [piece for piece in pieces if len(piece) >= 2]))
    return spellings


def bm25_rank(query: str, documents: Sequence[str], *, top_k: int) -> list[tuple[int, float]]:
    """``(document index, score)`` of the best matches, best first; no match, no entry."""
    query_terms = set(lexical_tokens(query))
    # A code is looked up in both spellings: "VID236" also finds content that says "VID-236".
    for joined, pieces in _code_spellings(query):
        query_terms.update([joined, *pieces])
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


def query_coverage(query: str, document: str, documents: Sequence[str]) -> float:
    """Share (0..1) of the query's terms found in ``document``, each weighted by its rarity
    in ``documents``. A term no document holds counts as the rarest."""
    query_terms = set(lexical_tokens(query))
    if not query_terms:
        return 0.0
    total = len(documents)
    document_sets = [set(lexical_tokens(text)) for text in documents]
    known = set().union(*document_sets) if document_sets else set()
    # The spelling of a code the corpus uses is the one that is weighed, so a question that
    # writes "VID236" is not marked down for a term no content could hold. A code the
    # corpus does not know keeps its own term and stays unmatched.
    for joined, pieces in _code_spellings(query):
        query_terms.update(pieces)
        if joined in known:
            query_terms.add(joined)
        elif all(piece in known for piece in pieces):
            query_terms.discard(joined)
    present = set(lexical_tokens(document))
    matched = weight = 0.0
    for term in query_terms:
        containing = sum(1 for terms in document_sets if term in terms)
        idf = math.log(1.0 + (total - containing + 0.5) / (containing + 0.5))
        weight += idf
        if term in present:
            matched += idf
    return matched / weight if weight else 0.0
