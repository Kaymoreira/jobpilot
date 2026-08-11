# Contributing & Engineering Standards

This repo follows a small set of deliberate practices. They exist so the code
stays reviewable, the history stays readable, and quality gates fail *closed*
(a gate that approves on the unexpected input is worse than no gate).

## Development setup

```bash
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# bash/macOS/Linux:    source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Branching & pull requests

- `main` is always releasable and always green.
- Work happens on short-lived branches: `feat/<slug>`, `fix/<slug>`,
  `chore/<slug>`, `docs/<slug>`.
- Every change lands through a pull request, even solo. The PR description
  links the milestone (or spec) it implements.

## Commits — Conventional Commits

Format: `type(scope): summary` in the imperative mood.

- Types: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`, `perf`, `ci`.
- One logical change per commit. If the summary needs an "and", split it.
- History is in English, no exceptions (portfolio for international roles).

Examples:

```
feat(matcher): score job fit against the candidate profile
test(normalizer): cover malformed-posting edge cases
```

## Versioning & changelog

- [Semantic Versioning](https://semver.org): `MAJOR.MINOR.PATCH`.
- Every user-visible change gets an entry in `CHANGELOG.md`, which follows
  [Keep a Changelog](https://keepachangelog.com).

## Testing philosophy

This is a QE-authored project; testing is the point, not an afterthought.

1. **Test-first.** Write the failing test, watch it fail, then implement.
2. **Exercise the failing path, not only the happy path.** Prove a gate
   *blocks* before trusting that it passes. Coverage is enforced by a gate
   (`--cov-fail-under=80`), not by good intentions.
3. **Acceptance criteria are testable by construction** — written as
   `WHEN ... THEN the system SHALL ...` in the feature spec.
4. **Non-deterministic components** (LLM-backed matching and generation) are
   validated with an evaluation harness, not brittle equality asserts.

## Quality gates (CI)

Enforced in CI as the project grows. Each is a small, independent check:

| Gate            | Tool                 | Blocking |
| --------------- | -------------------- | -------- |
| Coverage        | pytest-cov (80%)     | yes      |
| Type check      | mypy                 | yes      |
| Lint            | ruff                 | yes      |
| Dependency audit| pip-audit            | report   |
| Secret scan     | gitleaks             | yes      |

## Definition of Done

- [ ] Tests written first, happy path **and** failing path covered
- [ ] All quality gates green
- [ ] `CHANGELOG.md` updated
- [ ] Public content (code, docs, commits) in English
