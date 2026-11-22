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

## Loop ci-xdist-2, round 1

- Implementer: `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-ci-xdist`. Reviewer: `bsc-reviewer`.
- Base commit: `dd5e8e7`; snapshot: `/tmp/bsc-review/ci-xdist-2-r1/`. Round 1 of at most 3; expires (UTC): 2026-11-22 21:13.
- Why: on CI the first run with four workers was slower, not faster (3.12 took 1,145 s and two tests hit the 180 s timeout). Locally, pinned to four cores: four workers took 213 s with default threading and 64 s with OMP/OpenBLAS/MKL limited to one thread each. Each worker's BLAS/OpenMP started a thread per core, oversubscribing the machine.
- Change: a new root `conftest.py` uses `os.environ.setdefault` to set OMP_NUM_THREADS, OPENBLAS_NUM_THREADS and MKL_NUM_THREADS to 1, plus a comment in `ci.yml`.
- Settled: a plugin already imports numpy in the controller before `conftest.py` runs (an assert to that effect failed), so a serial run keeps the default. The xdist workers start after the initial conftests load and inherit the environment: measured 63.6 s with the conftest, the same as with the variables exported by hand.
- Checks: `make check` passed (592 tests, 60 s).
- Please check: that workers inherit the environment for every way the tests are run (Makefile, pre-push hook, CI), and that `setdefault` leaves a caller's own setting alone.

## Review — loop ci-xdist-2, round 1 — bsc-reviewer

- Snapshot reviewed: `/tmp/bsc-review/ci-xdist-2-r1/staged.diff`, root
  `conftest.py`, Makefile test targets, pre-push pytest hook, CI test step
  and pytest configuration.
- Verified the coordination lock names `bsc-implementer ci-xdist-2`,
  `HERDR_ENV=1`, and the requesting Claude's repository and pane `wF:p1`.
- Independent checks: parsed the staged Python file and executed that exact
  file via `runpy` in isolated Python subprocesses. With the three variables
  absent, a subsequently launched child inherited all three as `1`. With
  caller values OMP=3, OpenBLAS=2 and MKL=5, the child retained those values.
  These probes wrote no files and did not load numerical libraries.
- Invocation paths: Makefile `test`/`test-all`, the pre-push hook and CI all
  invoke pytest from the project checkout with local `-n 4` workers. None
  disables conftest loading or narrows discovery away from the root file.
  The controller loads the root conftest before starting the local workers;
  its environment settings therefore reach fresh worker interpreters before
  their plugin/numerical-library imports. Worker-local conftest loading is
  not relied on to reset an already loaded numerical runtime.
- `setdefault` preserves an existing caller setting intentionally. The
  serial-controller import-order limitation is already stated in the file
  and handoff; the patch does not claim to reconfigure an initialized BLAS.
- Evidence reused: implementer's pinned-four-core comparison, measured
  63.6-second run with this conftest, and reported `make check` success
  (592 tests, 60 seconds).
- Limits: did not independently execute pytest-xdist, inspect BLAS thread
  pools or reproduce CI timings. The subprocess probe verifies environment
  defaults, preservation and inheritance, not actual BLAS thread counts.
  No protected data or implementer files beyond the handoff were opened.
- Findings: none.
- Verdict: **accepted, ci-xdist-2 round 1**. This completes this review loop;
  acceptance authorizes no commit, push or merge.
