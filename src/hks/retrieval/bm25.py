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
# space (or several, or a tab, but not a line break), so "Budget 135" answers a question
# about "Budget-135".
_COMPOUND = r"(?<![a-z0-9])([a-z]{2,})%s(\d+(?:[-_]\d+)*)(?![a-z0-9])"
_QUESTION_COMPOUND_RE = re.compile(_COMPOUND % "[-_]?")
_CONTENT_COMPOUND_RE = re.compile(_COMPOUND % "(?:[-_]|[ \\t\u00a0\u3000]+)?")


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


def _codes_in(text: str) -> set[str]:
    return {_compound(match) for match in _CONTENT_COMPOUND_RE.finditer(text.lower())}


def _holds_code(wanted: str, present: set[str]) -> bool:
    return any(code == wanted or code.startswith(f"{wanted}-") for code in present)


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
    present = _codes_in(text)
    return all(_holds_code(wanted, present) for wanted in compounds)


def _code_spellings(query: str) -> list[tuple[str, list[str]]]:
    """For each compound code in ``query``: its joined spelling ("vid236") and the terms
    the separated spelling is made of (["vid", "236"])."""
    spellings: list[tuple[str, list[str]]] = []
    for match in _QUESTION_COMPOUND_RE.finditer(query.lower()):
        pieces = [match.group(1), *re.split(r"[-_]", match.group(2))]
        spellings.append(("".join(pieces), [piece for piece in pieces if len(piece) >= 2]))
    return spellings


def bm25_rank(
    query: str,
    documents: Sequence[str],
    *,
    top_k: int,
    required: set[str] | None = None,
) -> list[tuple[int, float]]:
    """``(document index, score)`` of the best matches, best first; no match, no entry.

    With ``required``, only documents that hold every one of those identifiers are ranked:
    content that merely has the pieces of a code apart ("VID status 236") cannot take the
    places of the content that names it.
    """
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
    if not required:
        return ranked[:top_k]
    kept: list[tuple[int, float]] = []
    for index, score in ranked:
        if holds_identifiers(required, documents[index]):
            kept.append((index, score))
            if len(kept) == top_k:
                break
    return kept


class CoverageScorer:
    """``query_coverage`` for many documents of one corpus. The corpus is read once, when
    the scorer is made; scoring a document then only reads that document."""

    def __init__(self, query: str, documents: Sequence[str]) -> None:
        lowered = query.lower()
        # code -> how many terms it would be if written apart ("vid-236": 2)
        codes: dict[str, int] = {}
        for match in _QUESTION_COMPOUND_RE.finditer(lowered):
            pieces = [match.group(1), *re.split(r"[-_]", match.group(2))]
            codes[_compound(match)] = max(1, sum(len(piece) >= 2 for piece in pieces))
        terms = set(lexical_tokens(_QUESTION_COMPOUND_RE.sub(" ", lowered)))
        total = len(documents)
        term_count = dict.fromkeys(terms, 0)
        code_count = dict.fromkeys(codes, 0)
        for text in documents:
            held = set(lexical_tokens(text))
            for term in terms:
                if term in held:
                    term_count[term] += 1
            if codes:
                named = _codes_in(text)
                for code in codes:
                    if _holds_code(code, named):
                        code_count[code] += 1

        def rarity(containing: int) -> float:
            return math.log(1.0 + (total - containing + 0.5) / (containing + 0.5))

        self._terms = {term: rarity(count) for term, count in term_count.items()}
        # A code weighs as much as the terms it stands for, however it is spelled.
        self._codes = {code: codes[code] * rarity(count) for code, count in code_count.items()}
        self._weight = sum(self._terms.values()) + sum(self._codes.values())

    @property
    def measurable(self) -> bool:
        """False when the query has nothing to look for (one CJK character, punctuation):
        a coverage of 0 would then say nothing about the document."""
        return bool(self._terms or self._codes)

    def score(self, document: str) -> float:
        if not self._weight:
            return 0.0
        present = set(lexical_tokens(document))
        matched = sum(idf for term, idf in self._terms.items() if term in present)
        if self._codes:
            here = _codes_in(document)
            matched += sum(idf for code, idf in self._codes.items() if _holds_code(code, here))
        return matched / self._weight


def query_coverage(query: str, document: str, documents: Sequence[str]) -> float:
    """Share (0..1) of the query's terms found in ``document``, each weighted by its rarity
    in ``documents``. A term no document holds counts as the rarest.

    A compound code in the query is one term, whichever way it is spelled there or in the
    content: it is found where the content names that code, and it is as rare as the
    content naming it is. Its pieces ("vid", "236") are not looked up on their own, but
    it weighs as much as that many terms, as it did when it was written apart.
    """
    return CoverageScorer(query, documents).score(document)
