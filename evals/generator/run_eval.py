"""Offline eval runner for the generator (Layer 2 — non-gating).

Loads the human-labeled corpus, runs the REAL match_job + AnthropicGenerator on
each case through the same fail-closed path the API uses, and prints fabrication
rate, gap-honesty, language appropriateness, and thin-job padding against the
labels. This calls the live model, so it needs ANTHROPIC_API_KEY and is never run
by the test suite or the coverage gate — a flaky, real-LLM gate would be a
fail-open gate (AD-019/AD-028).

Run it by hand:  python -m evals.generator.run_eval
"""

import json
import os
import sys
from pathlib import Path

from evals.generator import metrics
from jobpilot.generation import AnthropicGenerator, generate_letter
from jobpilot.matching import AnthropicMatcher
from jobpilot.models import Job, JobCreate, Profile, ProfileCreate

CORPUS_PATH = Path(__file__).parent / "corpus.json"


def _build_job(data: dict) -> Job:
    return Job.new_from(JobCreate(**data))


def _build_profile(data: dict) -> Profile:
    return Profile.new_from(ProfileCreate(**data))


def run(matcher=None, generator=None) -> None:
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    cases = corpus["cases"]
    matcher = matcher or AnthropicMatcher()
    generator = generator or AnthropicGenerator()

    graded = []
    for case in cases:
        job = _build_job(case["job"])
        profile = _build_profile(case["profile"])
        result = generate_letter(job, profile, matcher, generator)
        letter = result.draft or ""
        graded.append((case, result, letter))

    fabrication_items = [
        (c.get("forbidden_facts", []), letter) for c, _, letter in graded
    ]
    gap_items = [
        (c["gap_label"], letter) for c, _, letter in graded if c.get("gap_label")
    ]
    language_items = [
        (c["expected_language"], letter)
        for c, _, letter in graded
        if c.get("expected_language")
    ]
    thin_items = [
        (c.get("forbidden_facts", []), letter)
        for c, _, letter in graded
        if c.get("is_thin_job_probe")
    ]

    print("=" * 60)
    print("Generator eval report (Layer 2, offline)")
    print("=" * 60)
    print(f"cases: {len(cases)}")
    print(
        f"fabrication rate:       {metrics.fabrication_rate(fabrication_items):.2f}  (lower is better)"
    )
    print(
        f"gap-claim rate:         {metrics.gap_claim_rate(gap_items):.2f}  (lower is better)"
    )
    print(
        f"language match rate:    {metrics.language_match_rate(language_items):.2f}  (higher is better)"
    )
    print(
        f"thin-job padding rate:  {metrics.thin_job_padding_rate(thin_items):.2f}  (lower is better)"
    )
    print("-" * 60)
    for case, result, _ in graded:
        print(f"  {case['name']:32s} status={result.status}")
    print("-" * 60)
    print(
        "CAVEAT: this corpus is tiny and hand-labeled, and the metrics are\n"
        "simple string heuristics that cannot prove honesty. The numbers are\n"
        "DIRECTIONAL, not robust. A single case swings them by >10%. Treat them\n"
        "as a smoke signal, never as a release gate."
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
