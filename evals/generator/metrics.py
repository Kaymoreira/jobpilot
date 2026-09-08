"""Pure metric functions for the generator eval (Layer 2).

No I/O, no network, no randomness: each function maps a hand-labeled case plus
the model's generated letter text to a number. This is the part of the eval
harness that is unit-tested (the runner's real-LLM call is not gated, AD-028).

The matching is deliberately simple string heuristics. It CANNOT prove a letter
is honest; it measures observable tells (a forbidden fact asserted, a gap claimed
as possessed, the wrong language). A tiny corpus makes these numbers
DIRECTIONAL, not robust (GEN-26).
"""

import re

# Small stopword markers per language. Crude by design: enough to tell an
# English letter from a Portuguese one on a short cover letter, honestly
# caveated. Extend the corpus/markers before trusting the number.
LANG_MARKERS: dict[str, set[str]] = {
    "en": {"the", "and", "would", "with", "to", "team", "work", "i", "your"},
    "pt": {"de", "da", "com", "para", "equipe", "trabalho", "eu", "gostaria", "e"},
}

# Phrases that assert possession of a skill. If one shares a sentence with a
# gap term, the letter is claiming the gap as already-held.
POSSESSION_MARKERS: tuple[str, ...] = (
    "experience with",
    "experienced in",
    "expert in",
    "proficient in",
    "proficiency in",
    "skilled in",
    "years on",
    "years of",
    "years with",
    "background in",
    "mastery of",
    "specialist in",
    "at scale",
)


def _mentions(term: str, text: str) -> bool:
    return term.casefold() in text.casefold()


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"[.!?\n]+", text) if s.strip()]


def fabrication_rate(items: list[tuple[list[str], str]]) -> float:
    """Fraction of cases whose letter asserts a forbidden fact.

    Each item is ``(forbidden_facts, letter)`` where ``forbidden_facts`` are
    things absent from the Profile that must never appear. A case "leaks" if the
    letter mentions any of them. Lower is better (GEN-22).
    """
    if not items:
        return 0.0
    leaks = sum(
        1 for facts, letter in items if any(_mentions(f, letter) for f in facts)
    )
    return leaks / len(items)


def gap_claim_rate(items: list[tuple[str, str]]) -> float:
    """Fraction of cases whose letter claims a gap as already possessed.

    Each item is ``(gap_label, letter)``. A violation is a sentence that mentions
    the gap term alongside a possession marker (e.g. "expert in Kubernetes").
    Framing a gap as an area to grow is NOT a violation. Lower is better
    (GEN-23).
    """
    if not items:
        return 0.0
    violations = 0
    for gap, letter in items:
        for sentence in _sentences(letter):
            if _mentions(gap, sentence) and any(
                _mentions(m, sentence) for m in POSSESSION_MARKERS
            ):
                violations += 1
                break
    return violations / len(items)


def language_matches(expected: str, letter: str) -> bool:
    """Whether the letter's dominant language matches ``expected`` (GEN-24).

    Counts language-marker hits and picks the argmax. Crude but deterministic;
    honestly caveated in the report.
    """
    words = re.findall(r"[a-zA-Zà-úÀ-Ú]+", letter.casefold())
    counts = {
        lang: sum(1 for w in words if w in markers)
        for lang, markers in LANG_MARKERS.items()
    }
    if not any(counts.values()):
        return False
    predicted = max(counts, key=counts.get)
    return predicted == expected


def language_match_rate(items: list[tuple[str, str]]) -> float:
    """Fraction of cases written in the expected language. Higher is better."""
    if not items:
        return 0.0
    hits = sum(1 for expected, letter in items if language_matches(expected, letter))
    return hits / len(items)


def thin_job_padding_rate(items: list[tuple[list[str], str]]) -> float:
    """Fraction of thin-job cases whose letter invents concrete specifics.

    A thin job (title/company only) gives little to tailor on; the letter must
    not pad the gap with fabricated specifics. Each item is
    ``(forbidden_specifics, letter)``; a case is flagged if the letter mentions
    any of them. Same shape as ``fabrication_rate`` but scoped to thin-job probes
    and reported separately (GEN-25). Lower is better.
    """
    return fabrication_rate(items)
