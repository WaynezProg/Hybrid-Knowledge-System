"""Question wrappers that carry no retrieval subject."""

from __future__ import annotations

import re

_QUESTION_WORDS_EN = frozenset(
    """
    an the is are was were be been am do does did has have had what when where which who
    whom whose why how of to in on at for from by with about as and or but if it its this
    that these those there their they we you my our your me us can could should would will
    shall may might not no any some all so than then
    """.split()
)
_QUESTION_PHRASES_ZH = tuple(
    sorted(
        """
        為什麼 为什么 做了什麼 做了什么 是什麼 是什么 有什麼 有什么 什麼時候 什么时候 什麼 什么
        做了 有哪些 哪些 哪個 哪个 哪裡 哪里 如何 怎麼 怎么 怎樣 怎样 是否 是誰 是谁 多少 幾個
        几个 有沒有 有没有 請問 请问 嗎 吗 呢
        """.split(),
        key=len,
        reverse=True,
    )
)
_WORD_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]+(?![A-Za-z0-9])")


def query_subject_text(question: str) -> str:
    """Leave names/codes intact, including uppercase IT/US, and remove question words."""
    for phrase in _QUESTION_PHRASES_ZH:
        question = question.replace(phrase, " ")
    return _WORD_RE.sub(
        lambda match: " "
        if match.group().lower() in _QUESTION_WORDS_EN
        and not (match.group().isupper() and len(match.group()) >= 2)
        else match.group(),
        question,
    )
