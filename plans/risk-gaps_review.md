# Review: risk-gaps

## Current state

- Status: complete (round 1 accepted)
- Base commit: `7932e56`; snapshot: `/tmp/bsc-review/risk-gaps-r1/`
- Decisions needed from the user: none

## Loop

- Loop ID and round: `risk-gaps-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-risk-gaps`
- Reviewer: `bsc-reviewer` (Codex)
- Authorized scope: review requests and replies only
- Expires (UTC): 2026-11-23 03:49

## Handoff, round 1

- Tier: Small.
- Purpose: the printed risk-view key and the top-corners one-pager both said "the gaps are corners outside the city". That is wrong where the ranking covers only the city (San Francisco, Mountain View), because there the ranks run 1 to N. They now say it only when the listed ranks are not exactly 1..N.
- Changes:
  - `ranking.markdown` compares the ranks with `range(1, n + 1)`;
  - `RISKKEY` in `movement_map.html` tests `RANKED.some((k,i)=>k.r!==i+1)`; RANKED arrives sorted by rank from `ranking.top`.
- Tests: the one-pager test covers both cases. `make check` passed (628 tests). Real-data print check (counts only): the Los Altos key and one-pager show the line; San Francisco's show neither.
- Status: ready for reviewer

## Review, round 1 — risk-gaps-1

Verdict: **accepted** (round 1). No correctness findings.

The one-pager and printed risk key now omit the gaps explanation for ranks exactly 1..N, and retain it when ranks skip an entry, including a missing initial rank. Both predicates agree for the sorted integer ranks produced by `top()` and `markers()`. The staged change preserves the rest of the explanation and credits.

Validation: executed the exact snapshot `markdown()` function with minimal table/row stand-ins and made-up text, and the exact `RISKKEY` declaration in Node. Both correctly handled six cases: empty ranks, [1], [1,2,3], [1,3,4], [2,3,4], and [5]. Checked that `top()` sorts ranks and `markers()` emits integer rank values. Reviewed the regression assertions for both one-pager outcomes. Full `make check` was not rerun; the handoff reports 628 passing tests. No protected files or records were opened.

Ledger: no open findings. Loop risk-gaps-1 complete. Implementer releases the reviewer lock. Acceptance does not authorize commit, push or merge.
