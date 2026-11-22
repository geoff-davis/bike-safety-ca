# Review: ci-xdist

## Current state

- Status: complete (accepted in round 1)
- Next action: none
- Base commit: `b2d0caa`; snapshot: `/tmp/bsc-review/ci-xdist-r1/`
- Open findings: none
- Decisions needed from the user: none

## Loop

- Loop ID and round: `ci-xdist-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-ci-xdist`
- Reviewer: `bsc-reviewer` (Codex)
- Authorized scope: review requests and replies only
- Expires (UTC): 2026-11-22 19:41

## Handoff, round 1

- Tier: Small
- Problem: the CI test step takes 467 s on 3.12 and 802 s on 3.14, nearly all of the run time.
- Change:
  - Adds `pytest-xdist>=3.6` to the dev group (pyproject and uv.lock).
  - Runs pytest with `-n 4` in CI, in `make test` and `make test-all`, and in the pre-push hook.
  - Adds a CI comment saying why the worker count is 4.
- Measured locally on 32 cores, fast suite with coverage:
  - serial: 148 s;
  - `-n 4`: 62 s;
  - `-n 8`: 85 s;
  - `-n auto` (32 workers): 92 s.

  Each worker uses about two cores, through numeric library threads.
- Checks run:
  - `make check` passed: 592 tests, coverage 94%, the same as serial.
  - `make test-all`: 595 passed, 259 s.
- Please check:
  - coverage combining across workers under pytest-cov;
  - that pytest-timeout and faulthandler still work per worker;
  - that no test depends on shared state or order: files written to fixed paths, module-level caches, the working directory.

## Review, round 1 — bsc-reviewer

- Loop: `ci-xdist-1`, round 1.
- Snapshot reviewed: `/tmp/bsc-review/ci-xdist-r1/staged.diff`, CI workflow,
  pre-push hook, Makefile, pytest/coverage configuration and lock entries;
  inspected test collection patterns, module fixtures, temporary paths,
  working-directory changes and the notebook subprocess.
- Verified the coordination lock names `bsc-implementer ci-xdist`,
  `HERDR_ENV=1`, and the requesting Claude's repository and pane `wF:p1`.
- Checks: parsed project/lock TOML and workflow/hook YAML. Confirmed xdist
  is declared in the dev group and root lock metadata, locked at 3.8.0,
  with execnet and pytest dependency entries present. All four intended
  invocation sites use four workers; CI and `test-all` retain the override
  that includes slow tests. The pre-push stage remains pre-push.
- Coverage: CI and both Makefile targets retain `--cov`; pytest-cov handles
  xdist worker collection and combining. Existing branch/source/relative-path
  settings contain no conflicting manual data-file or combine override.
  The reported four-worker run's unchanged 94% coverage provides execution
  evidence; it was not independently reproduced here.
- Timeouts: 180-second pytest-timeout and 300-second faulthandler settings
  remain in the shared pytest configuration, available in each worker;
  explicit 600-second slow-test overrides are unchanged. Faulthandler remains
  diagnostic rather than a failing deadline. No conflicting controller-only
  timeout configuration was introduced.
- Isolation: inspected fixtures build synthetic files under `tmp_path` or
  `tmp_path_factory` (worker-specific directories under xdist). Monkeypatched
  globals and working directories are process-local. No concrete new race
  or order dependency found. The notebook subprocess writes to fixed demo
  locations, but only one test invokes that script; the other inspected
  demo fixtures use their own temporary directories. Collection patterns
  inspected use ordered lists, mappings or sorted config paths; an AST
  scan found no direct set-literal parametrizations.
- Evidence reused: implementer's reported `make check` success (592 tests,
  94% coverage), `make test-all` success (595 tests), and timing comparisons.
- Limits: no suite execution, injected worker hang, dependency installation
  or GitHub runner measurement performed. Inspection cannot rule out every
  intermittent scheduling issue. No protected records or paths opened.
- Findings: none.
- Verdict: **accepted, round 1**. This completes the review loop; acceptance
  authorizes no commit, push or merge.
