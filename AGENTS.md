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
2. Get a review from Codex (see "Review" below) of the staged change, unless
   every staged file is on the exempt list there.
3. Test each finding before acting on it. Fix what is confirmed, or say in
   the commit report what was left and why.
4. Then commit.

## Review: Claude implements, Codex reviews

The user authorizes direct review requests and replies through Herdr; no
manual relay is needed. This covers message delivery only: a review verdict
does not authorize a commit, push or merge, which still wait for the user.

Live agent names, in the bike-safety-ca workspace: one reviewer,
`bsc-reviewer` (Codex), and any number of implementers (Claude),
`bsc-implementer`, `bsc-implementer-2`, `bsc-implementer-3` and so on. A new
Claude takes the lowest free number (`herdr agent rename <pane> <name>`).
Before each send check `HERDR_ENV=1` and `herdr agent list` (name, agent kind,
repository, pane); names are cleared when an agent exits, so rename after a
restart. If identity is unclear, ask.

Several implementers at once:

- Each works in its own worktree and branch
  (`git worktree add ../bike-safety-ca-<task> -b <task> origin/main`), never
  in another's checkout, so staged changes do not mix. `data/` and `output/`
  stay in the main checkout; point commands at them by path.
- Task names are unique, so handoff files and snapshot paths never collide.
- The reviewer takes one request at a time, enforced by a lock file. Seeing
  the reviewer idle is not enough: two implementers can both see it idle,
  and Herdr accepts prompts to a working agent. The 60-minute loop clock
  starts when the request is sent.
- The handoff names the requesting implementer and pane, and the reviewer
  replies to that name only.

Exempt from review, decided by the paths and not by how the change feels:
`docs/**` and `*.md` other than `AGENTS.md` and `CLAUDE.md`, `uv.lock` alone,
and Dependabot pull requests with green CI.

### What the reviewer may see

Only the snapshot of the staged files the implementer prepares, and the
staged diff. Never anything under `data/` or `output/`, never `.env`, never a
crash, party or victim record, and nothing from `../gis` or the archive
clone. If a diff quotes text from a real record, replace it with a made-up
example first. The reviewer's pane runs in this repository, so this is a
rule the reviewer keeps: it does not open files outside the snapshot.

### When implementing

- Make the snapshot outside the repository:

  ```bash
  R=/tmp/bsc-review/<task>-r<round>   # <task> is unique across implementers
  mkdir -p "$R" && git diff --cached > "$R/staged.diff"
  git checkout-index --all --prefix="$R/tree/"   # the staged files, not HEAD
  ```

- Write the handoff to `plans/<task>_review.md` in your worktree from
  `plans/review-handoff.md`, naming yourself as the implementer: base
  commit, snapshot path, what the change is meant to do, checks run,
  settled decisions. The record is committed with
  the change, so it holds no record data either.
- Take the reviewer lock. Creating the file with `noclobber` (O_EXCL)
  succeeds for exactly one implementer; `mkdir` is not used because it let
  several contenders win inside the agent sandbox (tested 2026-11-22).

  ```bash
  L=/tmp/bsc-review/reviewer.lock; mkdir -p /tmp/bsc-review
  ( set -o noclobber; echo "<your name> <task> $(date -u +%FT%TZ)" > "$L" ) 2>/dev/null \
      && echo taken || echo "held: $(cat "$L")"
  ```

  If it is held, try again every minute or two. Never remove another
  implementer's lock; if it is more than 60 minutes old or its holder is not
  in `herdr agent list`, tell the user.
- Holding the lock, check that the reviewer is idle or done, then
  `herdr agent prompt bsc-reviewer "<absolute handoff path, snapshot path,
  round, your name>"`, without `--wait`.
- Poll the handoff file about once a minute for a verdict naming this
  round, until the loop's expiry. Agent states are hints only. If the
  reviewer is blocked or settles with no verdict, look with
  `herdr agent read bsc-reviewer`; do not resend. At expiry tell the user.
- Keep the lock until the reviewer has appended its verdict for your round,
  then release it, also at expiry or if you abandon the request:
  `[ "$(cut -d' ' -f1 "$L")" = "<your name>" ] && rm "$L"`. Take it again
  for the next round.
- Answer findings by changing the staged files and sending the next round
  with a new snapshot.

### When reviewing

- Before starting, check that `/tmp/bsc-review/reviewer.lock` names the
  requesting implementer. If it names someone else or is missing, reply to
  the requester that it does not hold the lock, and do nothing more.
- Work only in the snapshot named in the prompt. Read-only: never edit,
  stage, stash or reset the implementer's tree. The one file written outside
  the snapshot is the handoff file named in the prompt, appended to only.
- Report correctness bugs, each with a stable ID, location, the concrete
  failing case and whether it is confirmed or suspected. A finding blocks
  only if it breaks the change's stated purpose or causes a regression.
- Append the round and a verdict (accepted or changes required, naming the
  round) to the handoff file, send one prompt to the implementer the handoff
  names (not whichever Claude is focused), then delete the snapshot.

### Limits

Three rounds per loop and 60 minutes, both written in the handoff. No
acknowledgement messages. A blocked approval dialog goes to the user. Stop and
tell the user on acceptance, the third round, expiry or a stall.

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
