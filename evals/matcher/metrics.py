"""Pure metric functions for the matcher eval (Layer 2).

No I/O, no network, no randomness: each function maps hand-labeled expectations
plus the model's ``MatchResult`` to a number. This is the part of the eval
harness that is unit-tested (the runner's real-LLM call is not gated). A tiny
corpus makes these numbers directional, not robust (MATCH-18).
"""

from jobpilot.models import MatchResult


def precision_recall_strong(
    pairs: list[tuple[str, MatchResult]],
) -> tuple[float, float]:
    """Precision and recall of the "strong fit" decision.

    Positive = verdict ``strong``. ``pairs`` is a list of
    ``(expected_band, result)``. Zero denominators return ``0.0`` rather than
    dividing by zero (MATCH-16).
    """
    tp = fp = fn = 0
    for expected, result in pairs:
        predicted_strong = result.verdict == "strong"
        actual_strong = expected == "strong"
        if predicted_strong and actual_strong:
            tp += 1
        elif predicted_strong and not actual_strong:
            fp += 1
        elif not predicted_strong and actual_strong:
            fn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return precision, recall


def fabrication_rate(probes: list[tuple[str, MatchResult]]) -> float:
    """Fraction of fabrication probes the model got wrong.

    Each probe is ``(expected_gap, result)`` for a job that requires a skill the
    profile lacks. A probe "leaks" (fabricates) if the model scored it ``strong``
    or failed to name the missing skill among its gaps. Lower is better
    (MATCH-17).
    """
    if not probes:
        return 0.0
    leaks = 0
    for expected_gap, result in probes:
        named = any(expected_gap.casefold() in g.casefold() for g in result.gaps)
        if result.verdict == "strong" or not named:
            leaks += 1
    return leaks / len(probes)


def cannot_assess_accuracy(pairs: list[tuple[str, MatchResult]]) -> float:
    """Fraction of cases where the abstain decision matched the label.

    A case is correct when ``expected_band == "cannot_assess"`` iff the model
    returned ``cannot_assess`` — catching both under-abstaining (a fit claimed on
    no basis) and over-abstaining (MATCH-15/18).
    """
    if not pairs:
        return 0.0
    correct = 0
    for expected, result in pairs:
        if (expected == "cannot_assess") == (result.verdict == "cannot_assess"):
            correct += 1
    return correct / len(pairs)
