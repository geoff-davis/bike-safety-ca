# Notes for coding agents

## Before every commit

1. Run `ruff format` on every touched Python file and restage it, then
   `make check` (lint, types, tests).
2. Get an independent review of the staged change from the Codex CLI, run
   read-only on a copy of the staged files:

   ```
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
