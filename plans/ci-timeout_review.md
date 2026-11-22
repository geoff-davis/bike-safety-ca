# Review: ci-timeout

## Current state

- Status: complete (accepted in round 1)
- Next action: none
- Base commit: `c87bd4e`; snapshot: `/tmp/bsc-review/ci-timeout-r1/`
- Open findings: none
- Decisions needed from the user: none

## Loop

- Loop ID and round: `ci-timeout-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca`
- Reviewer: `bsc-reviewer` (Codex), pane `wF:p2`
- Authorized scope: review requests and replies only
- Expires (UTC): 2026-11-22 18:47

## Handoff, round 1

- Tier: Small
- Problem: CI on PR #8 failed: `tests/test_demo.py::test_the_sensitivity_tables_run_on_the_demo_city` hit pytest-timeout's 60 s on the 3.12 runner (18 s locally). CI ran the suite in 1026 s against 318 s locally (about 3.2x).
- Change: global `timeout` 60 -> 180 s, `faulthandler_timeout` 120 -> 300 s (above the global timeout and above the slow tests' CI time, about 3.2 x 59 s = 190 s; they keep their own 600 s timeout). AGENTS.md test note updated.
- Local durations (top): 18.0 s, 13.4 s, 9.5 s, 8.7 s; everything else under 8 s.
- Verification: markdownlint AGENTS.md 0 errors; make check running.
- Please check: that the values do what the comments say with pytest-timeout and faulthandler, and nothing else is affected.

## Review, round 1 — bsc-reviewer

- Loop: `ci-timeout-1`, round 1; reviewed before expiry.
- Snapshot reviewed: `/tmp/bsc-review/ci-timeout-r1/staged.diff`,
  `tree/AGENTS.md`, `tree/pyproject.toml`, `tree/Makefile`,
  `tree/.github/workflows/ci.yml`, and relevant synthetic test code.
- Checks: parsed the staged TOML with Python's `tomllib`; confirmed
  `timeout=180`, `faulthandler_timeout=300`, and the unchanged default slow
  exclusion. Searched test/config timeout settings and inspected the slow
  decorator's explicit `pytest.mark.timeout(600)`. Verified the coordination
  lock names `bsc-implementer ci-timeout`, `HERDR_ENV=1`, and the requesting
  Claude's repository and pane `wF:p1` through Herdr.
- Assessment: the default pytest-timeout deadline becomes 180 seconds;
  explicit 600-second slow-test marks retain precedence. The separate
  faulthandler timer dumps diagnostic stacks at 300 seconds and does not
  itself fail a test. Ordinary timeouts still occur first; slow tests may
  produce diagnostic stacks before their 600-second deadline. CI's
  25-minute job cap, test selection, and subprocess timeout are unchanged.
- Evidence reused: CI/local timing measurements and markdownlint result
  reported by the implementer. `make check` was still running at handoff;
  its success is not assumed by this review.
- Verification gaps: did not rerun the suite or reproduce GitHub runner
  timings; no live timeout probe. Inspection and TOML parsing establish the
  configuration change, not that all future CI runs finish within 180 s.
- Findings: none.
- Verdict: **accepted, round 1**. Complete the required checks before any
  commit; this verdict authorizes no commit, push or merge.
