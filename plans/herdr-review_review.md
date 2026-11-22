# Review: herdr-review

## Current state

- Status: complete (accepted in round 3)
- Next action: none
- Base commit: `491ec48`; snapshot: `/tmp/bsc-review/herdr-review-r3/`
- Open findings: none (HR-001 fixed in round 3)
- Decisions needed from the user: none

## Loop

- Loop ID and round: `herdr-review-1`, round 3 of at most 3
- Implementer: `bsc-implementer` (Claude), pane `wF:p1`
- Reviewer: `bsc-reviewer` (Codex), pane `wF:p2`
- Authorized scope: review requests and replies only
- Expires (UTC): 2026-11-22 17:31 (loop clock from round 1)

## Handoff, round 1

- Tier: Standard (agent instructions are shared policy)
- Intended behavior and acceptance criteria: replace the one-shot
  `codex exec` review in `AGENTS.md` with a Herdr loop between
  `bsc-implementer` and `bsc-reviewer`, keeping two existing rules intact:
  the reviewer sees only a snapshot of the staged files (never `data/`,
  `output/`, `.env` or records), and nothing is committed, pushed or merged
  without the user's word. Adds `plans/review-handoff.md`, the record
  template, adapted from the shared best-practices template.
- Changed areas: `AGENTS.md` ("Before every commit" steps 2 and 3, the new
  "Review" section replacing "What may be sent for review"),
  `plans/review-handoff.md` (new). The staged diff is
  `/tmp/bsc-review/herdr-review-r1/staged.diff`; the staged tree is under
  `tree/` beside it.
- Verification: markdownlint on both files | staged | 0 errors |
  implementer. The snapshot was checked to hold no `data/`, `output/` or
  `.env`. This round is itself the first run of the protocol.
- Settled decisions (do not re-report): review is of staged changes, not
  commits, because commits wait for the user; the handoff record is
  committed with the change; the exempt list includes `docs/**`.
- Known limitations: the reviewer's pane runs in the repository, so the
  rule against reading `data/` and `output/` is kept by the reviewer, not
  enforced by a sandbox.

Please check: is anything in the new section contradictory, unworkable for
you as reviewer (paths, commands, the reply step), or a weakening of the data
rule? Report correctness problems only.

## Review, round 1 — bsc-reviewer

- Loop: `herdr-review-1`, round 1.
- Snapshot reviewed: `/tmp/bsc-review/herdr-review-r1/staged.diff` and
  `tree/AGENTS.md`, `tree/plans/review-handoff.md`.
- Checks run by the reviewer: read the entire staged diff and both changed
  files; traced the request, polling, findings, verdict and cleanup sequence;
  verified `HERDR_ENV=1` and the live Herdr identities. `bsc-implementer` is
  Claude in this repository, pane `wF:p1`; `bsc-reviewer` is Codex in pane
  `wF:p2`. Agent listing required sandbox escalation and then succeeded.
- Evidence reused from the implementer: reported markdownlint success and
  the check that the snapshot contains no prohibited paths.
- Verification gaps: no application tests run for this instructions-only
  change; future rounds, expiry and restart behavior were reviewed by
  inspection, not exercised. The explicit handoff read/append instruction
  is treated as the narrow exception to snapshot-only, read-only review;
  no other implementer files were opened or changed.
- Findings: none. The stated exclusions for sensitive data and requirement
  for user authorization before commit, push or merge are retained.
- Verdict: **accepted, round 1**. Review acceptance authorizes no commit,
  push or merge.

## Handoff, round 2

- Asked for by the user after round 1: the protocol must work with several
  Claude implementers in this Herdr workspace sharing the one reviewer.
- Changes since round 1 (`/tmp/bsc-review/herdr-review-r2/staged.diff` is the
  whole staged change against `491ec48`; diff it against round 1's to see
  only the new part):
  - implementer names `bsc-implementer`, `bsc-implementer-2`, ... and the
    lowest-free-number rule;
  - one worktree and branch per implementer; unique task names; the reviewer
    takes one request at a time, implementers wait until it is idle or done;
  - the handoff names the requesting implementer, and the reviewer replies
    to that name only (template line updated);
  - round 1's note made explicit: the handoff file is the one file the
    reviewer writes outside the snapshot, append only.
- Verification: markdownlint on both files | staged | 0 errors | implementer.
- Please check the multi-implementer rules for races or gaps (two requests
  at once, a reply going to the wrong Claude, worktrees and the
  git-ignored data folders) and anything contradictory.

## Review, round 2 — bsc-reviewer

- Loop: `herdr-review-1`, round 2.
- Snapshot reviewed: `/tmp/bsc-review/herdr-review-r2/staged.diff` and
  `tree/AGENTS.md`, `tree/plans/review-handoff.md`.
- Checks: read the full staged diff and changed files; traced concurrent
  request submission and reply routing. Read `herdr agent prompt --help`:
  it explicitly discusses submissions while the target is already working;
  only blocked agents are documented as rejecting submission. Verified
  `HERDR_ENV=1` and both named agents' repository, kind and pane; the
  requesting Claude is still `bsc-implementer`, pane `wF:p1`.
- Evidence reused: implementer's reported markdownlint success.
- Verification gaps: no application tests for this instructions-only
  change; no competing prompts sent to live agents. The race below is
  confirmed by the protocol's permitted interleaving and CLI help, rather
  than by interrupting a live review.
- Verdict: **changes required, round 2**.

### HR-001 — P2, blocking, confirmed: polling does not serialize requests

- Location: snapshot `AGENTS.md:54–56`, also the submission rule at
  `AGENTS.md:87–89`.
- Concrete failing case: implementer A lists agents and sees the reviewer
  idle; implementer B also lists agents and sees it idle before A sends.
  A sends its request and starts a review. B then sends based on its idle
  observation. Both followed the prescribed check, but the reviewer receives
  B's prompt during A's active review. Herdr accepts prompts to working
  agents, so the command does not close this check/send race. There is no
  reservation or queue rule that ensures the second request waits for A's
  verdict and snapshot cleanup. Task-specific paths and reply names do not
  serialize access to the single reviewer.
- Impact: the new promise of one review request at a time is not enforced;
  concurrent implementers can interrupt an active review and leave a
  handoff waiting for its verdict. This blocks the round-2 requirement to
  support several implementers sharing one reviewer.
- Required correction: define an atomic shared reservation or a single
  dispatcher/queue before checking and submitting. Specify who owns and
  releases it, including failure recovery, and keep ownership until the
  reviewer has completed the request. Verify the two-contender interleaving
  without sending competing prompts to production agents.
- Status: open. No other correctness findings.

## Handoff, round 3

- HR-001 (fixed): requests are serialized by a lock file,
  `/tmp/bsc-review/reviewer.lock`, created with `noclobber` (O_EXCL). The
  implementer takes it before checking the reviewer's state and sending,
  holds it until the round's verdict is appended, and releases it only if
  it names them; a stale lock (over 60 minutes, or holder not in
  `herdr agent list`) goes to the user, never removed by another agent.
  The reviewer checks the lock names the requester before starting and
  otherwise replies that the requester does not hold it.
- Two-contender check, run in the implementer's sandbox without live
  agents (script: 4 background contenders per trial, each on a fresh lock
  path, counting successes):
  - `mkdir` lock: 47/300, 91/300 and 11+2/200 trials had more than one
    winner. This is why `mkdir` is not used, and is now noted in the text.
  - `noclobber` file: 0/300 and 0/1500 trials with other than one winner.
  - `flock`: 0/300, but a flock lasts only as long as its process, which
    does not fit a lock held across many separate agent commands.
  - zsh check: second take refused and shows the holder; a non-holder's
    release is refused; the holder's release succeeds.
- Snapshot: `/tmp/bsc-review/herdr-review-r3/`. This round's request was
  sent holding the lock (`bsc-implementer herdr-review ...`).

## Review, round 3 — bsc-reviewer

- Loop: `herdr-review-1`, round 3 (final round); reviewed before the
  recorded expiry.
- Snapshot reviewed: `/tmp/bsc-review/herdr-review-r3/staged.diff` and
  `tree/AGENTS.md`, `tree/plans/review-handoff.md`.
- Checks: read the entire staged change and traced lock acquisition,
  competing acquisition, submission, verdict, release, expiry and stale
  ownership handling. Read the explicitly designated coordination lock;
  it names `bsc-implementer herdr-review`. Verified `HERDR_ENV=1` and live
  identities: requesting Claude `bsc-implementer` remains in this repository,
  pane `wF:p1`; reviewer Codex is `bsc-reviewer`, pane `wF:p2`.
- Evidence reused: implementer's reported noclobber contention trials
  (300 and 1500 trials, exactly one winner per trial), and the zsh ownership
  and release checks. These were not independently rerun.
- Verification gaps: no application tests or competing live prompts run;
  process termination and stale-lock recovery reviewed by inspection.
- HR-001 assessment: fixed in the staged snapshot. Exclusive creation of
  the shared lock precedes the state check and send. A second contender
  cannot submit while the first holds it. Release after a verdict is also
  guarded by the next holder checking that the reviewer is idle or done,
  so the previous review's reply and cleanup can finish first. Expiry or
  abandonment does not waive that state check. Stale locks go to the user
  rather than being stolen by another implementer.
- Findings: no new correctness findings. Sensitive-data exclusions and
  user authorization before commit, push or merge remain intact.
- Verdict: **accepted, round 3**. This is the final round of this loop;
  review acceptance authorizes no commit, push or merge.

## Finding ledger — final round

| ID | Severity | Blocking | Location | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| HR-001 | P2 | Resolved | Snapshot `AGENTS.md:89–120` | fixed | Atomic noclobber acquisition before submission, holder-only release, reviewer ownership check; contention and zsh checks reported in round-3 handoff; control flow reviewed independently. Fix is staged, not committed. |
