# Matcher eval harness (Layer 2)

Layer 1 (the unit suite under `tests/`) fakes the LLM and proves the plumbing
fails closed. This is **Layer 2**: it runs the *real* model against a small,
hand-labeled corpus to measure judgment quality. It is **offline and
non-gating** — never wired into CI or the coverage gate. A flaky, real-LLM gate
would be a fail-open gate.

## Run it

```bash
export ANTHROPIC_API_KEY=...        # calls the live model
python -m evals.matcher.run_eval
```

## The corpus labels are YOURS

`corpus.json` ships with **placeholder** `expected_band` / `expected_gap`
values so the harness runs out of the box. They are **not authoritative**.
Before trusting any number:

1. Read each case and set `expected_band` (`weak` / `possible` / `strong` /
   `cannot_assess`) from **your own** judgment as a QA.
2. **Never let an AI label these cases** — the whole point is to check the model
   against a human, so an AI-authored label defeats the eval.
3. Keep the probe kinds: at least one `is_fabrication_probe` (job needs a skill
   the profile lacks — set its `expected_gap`), one `is_thin_job_probe`
   (title/company only), and one `is_core_fit_probe` (strong on the core with a
   few peripheral gaps — should still score reasonably, not `weak`/`cannot_assess`).

## What it reports

- **strong-fit precision / recall** — how well the model's `strong` verdict
  matches your `strong` labels.
- **fabrication rate** — of the fabrication probes, the fraction where the model
  scored `strong` or failed to name the missing skill. Lower is better.
- **cannot_assess accuracy** — how often the abstain decision matched your label
  (catches both under- and over-abstaining).

## The stats are directional, not robust

The corpus is tiny (~8 cases). One case swings a metric by more than 10%. Treat
the output as a smoke signal for prompt/model regressions, never as a pass/fail
gate. The metric math itself is unit-tested in `tests/test_eval_metrics.py`.
