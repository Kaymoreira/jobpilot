# Generator eval harness (Layer 2)

Layer 1 (the unit suite under `tests/`) fakes the LLM and proves the plumbing
fails closed. This is **Layer 2**: it runs the *real* match + generation against a
small, hand-labeled corpus to measure the letter's honesty. It is **offline and
non-gating** — never wired into CI or the coverage gate. A flaky, real-LLM gate
would be a fail-open gate.

## Run it

```bash
export ANTHROPIC_API_KEY=...        # calls the live model (two calls per case)
python -m evals.generator.run_eval
```

## The corpus labels are YOURS

`corpus.json` ships with **placeholder** `forbidden_facts` / `gap_label` /
`expected_language` values so the harness runs out of the box. They are **not
authoritative**. Before trusting any number:

1. Read each case and set, from **your own** judgment as a QA:
   - `forbidden_facts` — concrete things the profile does NOT state (a skill,
     employer, degree, certification, number of years) that the letter must never
     assert.
   - `gap_label` — a real gap (a job requirement with no profile evidence) that
     must be framed honestly, never claimed as possessed.
   - `expected_language` — the Job posting's language (`en` / `pt`).
2. **Never let an AI label these cases** — the whole point is to check the model
   against a human, so an AI-authored label defeats the eval.
3. Keep the probe kinds: at least one **fabrication probe** (a `forbidden_fact`
   the letter must not assert), one **gap-honesty probe** (a `gap_label` that
   must not be claimed), and one `is_thin_job_probe` (title/company only, so the
   letter must not pad with invented specifics).

## What it reports

- **fabrication rate** — fraction of cases whose letter asserts a
  `forbidden_fact`. Lower is better (GEN-22).
- **gap-claim rate** — fraction of cases whose letter claims a `gap_label` as
  already possessed (gap term sharing a sentence with a possession phrase). Lower
  is better (GEN-23).
- **language match rate** — fraction written in the expected language. Higher is
  better (GEN-24).
- **thin-job padding rate** — of the thin-job probes, the fraction that invents
  concrete specifics. Lower is better (GEN-25).

## The metrics are heuristics, and the stats are directional

The matching is simple case-insensitive string checks. It **cannot prove** a
letter is honest — it flags observable tells. The corpus is tiny (a few cases),
so one case swings a metric by more than 10%. Treat the output as a smoke signal
for prompt/model regressions, never as a pass/fail gate. The metric math itself
is unit-tested in `tests/test_generator_eval_metrics.py`.
