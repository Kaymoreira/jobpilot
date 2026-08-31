"""Offline eval runner for the matcher (Layer 2 — non-gating).

Loads the human-labeled corpus, runs the REAL AnthropicMatcher on each case
through the same fail-closed path the API uses, and prints precision/recall,
fabrication rate, and cannot_assess accuracy against the labels. This calls the
live model, so it needs ANTHROPIC_API_KEY and is never run by the test suite or
the coverage gate — a flaky, real-LLM gate would be a fail-open gate (AD-019).

Run it by hand:  python -m evals.matcher.run_eval
"""

import json
import os
import sys
from pathlib import Path

from evals.matcher import metrics
from jobpilot.matching import AnthropicMatcher, match_job
from jobpilot.models import Job, JobCreate, Profile, ProfileCreate

CORPUS_PATH = Path(__file__).parent / "corpus.json"


def _build_job(data: dict) -> Job:
    return Job.new_from(JobCreate(**data))


def _build_profile(data: dict) -> Profile:
    return Profile.new_from(ProfileCreate(**data))


def run(matcher=None) -> None:
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    cases = corpus["cases"]
    matcher = matcher or AnthropicMatcher()

    graded = []
    for case in cases:
        job = _build_job(case["job"])
        profile = _build_profile(case["profile"])
        result = match_job(job, profile, matcher)
        graded.append((case, result))

    band_pairs = [(c["expected_band"], r) for c, r in graded]
    probes = [
        (c["expected_gap"], r)
        for c, r in graded
        if c.get("is_fabrication_probe") and "expected_gap" in c
    ]
    precision, recall = metrics.precision_recall_strong(band_pairs)

    print("=" * 60)
    print("Matcher eval report (Layer 2, offline)")
    print("=" * 60)
    print(f"cases: {len(cases)}")
    print(f"strong-fit precision: {precision:.2f}")
    print(f"strong-fit recall:    {recall:.2f}")
    print(f"fabrication rate:     {metrics.fabrication_rate(probes):.2f}  (lower is better)")
    print(f"cannot_assess accuracy: {metrics.cannot_assess_accuracy(band_pairs):.2f}")
    print("-" * 60)
    for case, result in graded:
        print(
            f"  {case['name']:32s} expected={case['expected_band']:13s} "
            f"got={result.verdict} (score={result.score})"
        )
    print("-" * 60)
    print(
        "CAVEAT: this corpus is tiny and hand-labeled. The numbers are\n"
        "DIRECTIONAL, not robust. A single case swings them by >10%. Treat\n"
        "them as a smoke signal, never as a release gate."
    )


if __name__ == "__main__":  # pragma: no cover
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "ANTHROPIC_API_KEY is not set. This harness calls the real model; "
            "export a key and re-run.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    run()
