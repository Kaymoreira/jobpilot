# LESSONS - auto-maintained by scripts/lessons.py

> Machine-owned. Do NOT hand-edit. Changes are overwritten on the next `lessons.py` write.
> Canonical state lives in `.specs/lessons.json`. Edit lessons only via the script.
> promote_threshold=2 distinct features · window_days=45 · quarantine_threshold=2

## Confirmed (load these at Specify/Design)

Corroborated across multiple features. Safe to apply as guidance.

_none_

## Candidates (under observation - do NOT load as guidance yet)

Seen once or not yet corroborated. Tracked, not trusted.

### L-001 - Pydantic v2 skips field validators on default values, so a default-None branch inside a validator only runs when the field is passed explicitly; test with an explicit value (e.g. link=None), not by omitting the field, or a fabricating mutation on that branch ships green.
- signal: `surviving_mutant` · recurrence: 1 feature(s) · scope: `models/validators` · harmful: 0
- features: pasted-job-source
- evidence: src/jobpilot/models.py:61 (models/validators)
- last seen: 2026-08-11T15:42:42Z

## Quarantined (failed when applied - ignore)

A confirmed lesson that recurred alongside failure. Kept for the maintainer to review.

_none_
