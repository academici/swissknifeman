"""How a line answers a research query: the words of the query and the score of a line."""
from __future__ import annotations

import re

STOPWORDS = frozenset({"the", "and", "for", "are", "how", "what", "why", "who", "when", "where", "does", "with", "that",
                       "this", "from", "not", "you", "can", "use", "has", "have", "was", "were", "which", "into", "about"})


def terms_of(text: str) -> list:
    """The words of a question that can find something: three letters or more, no stop words, once each, in order."""
    return list(dict.fromkeys(word for word in re.findall(r"\w+", text.lower()) if len(word) >= 3 and word not in STOPWORDS))


def line_score(line: str, needle: str, terms: list) -> int:
    """How well a line answers the query: the whole text as a phrase scores highest; else the number of its words
    that the line holds, counted only when the line holds enough of them (all of two, 60% of more)."""
    low = line.lower()
    if needle and needle in low:
        return len(terms) + 1
    if not terms:
        return 0
    found = sum(1 for term in terms if term in low)
    need = len(terms) if len(terms) <= 2 else -(-len(terms) * 3 // 5)
    return found if found >= need else 0
