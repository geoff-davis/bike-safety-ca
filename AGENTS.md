# Notes for coding agents

`CLAUDE.md` imports this file; edit here only.

## Setup and branches

`uv sync --locked`, then `make hooks` once per clone (commit and push hooks).
Work on a branch and merge through a pull request: the hooks refuse commits to
`main`, and `main` on GitHub requires the CI checks `quality`, `test (3.12)`
and `test (3.14)`. Those are matched by job name, so renaming a CI job or
changing the Python matrix needs a branch-protection update too.

| Task | Command |
| --- | --- |
| Format the files you touched | `make format FILES="path ..."` |
| Lint, format check, notebook check | `make lint` |
| Type check | `make typecheck` |
| Tests without the slow ones | `make test` |
| Every test (as CI runs them) | `make test-all` |
| Everything before a commit | `make check` |

## Before every commit

1. Run `make format FILES="..."` on every touched Python file and restage
   it, then `make check` (lint, types, tests). Do not commit while the hooks
   fail, and do not use `--no-verify`.
2. Get an independent review of the staged change from the Codex CLI, run
   read-only on a copy of the staged files:

   ```bash
   git diff --cached > "$SCRATCH/staged.diff"
   git checkout-index --all --prefix="$SCRATCH/tree/"   # the staged files, not HEAD
   codex exec --sandbox read-only --skip-git-repo-check -C "$SCRATCH" \
       -o "$SCRATCH/review.md" - < "$SCRATCH/prompt.txt"
   ```

   `$SCRATCH` is a temporary folder outside the repository. The prompt asks
   for correctness bugs in the diff, with a concrete failing case for each.
3. Test each finding before acting on it. The reviewer cannot run the code.
   Fix what is confirmed, or say in the commit report what was left and why.
4. Then commit.

## What may be sent for review

Staged files and the staged diff only. Never anything under `data/` or
`output/`, never a crash, party or victim record, and never `.env`. If a diff
quotes text from a real record, replace it with a made-up example first.

## Data

No crash records, City of Los Altos map files or state school lists are
committed here. The only map data in the repository is the demo city's, in
`demo/claremont/`, from OpenStreetMap and the Census Bureau with their
licences. Tests use made-up data. See "Crash records" in `docs/guide.md`.

## Tests

- Tests that take most of a minute carry `@slow` (see
  `tests/test_hospital_rates.py`): deselected locally and at push, run in CI.
  Every other test fails after 60 seconds.
- A `Pandas4Warning` is an error: pandas 4 turns these into failures.
- Do not change an expected value to make a failing test pass without saying
  why the new value is right.

## Context window

A full context window is compacted and the session continues. Running low is
not a reason to stop, rush or hand work to a subagent; reach a clean state
first (tree committed or described).
