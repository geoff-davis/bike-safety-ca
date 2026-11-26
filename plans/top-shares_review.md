# Review: top-shares

## Current state

- Status: complete (round 1 accepted)
- Next action: none
- Base commit: `db316a2`; snapshot: `/tmp/bsc-review/top-shares-r1/`
- Open findings: none
- Decisions needed from the user: none

## Loop

- Loop ID and round: `top-shares-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-model-review`
- Reviewer: `bsc-reviewer` (Codex), pane `wF:p2`
- Authorized scope: review requests and replies only
- Expires (UTC): `2026-11-24T01:13:17Z`

## Handoff, round 1

- Tier: Small
- Intended behavior and acceptance criteria:
  - `python -m bike_safety_ca.checks.candidates` already wrote `found in top 25/50/100` per window but summarised only the top 50 and the top 5% as shares. It now writes `top 25 share`, `top 50 share` and `top 100 share` (100 x found / later crashes; missing when there are no later crashes) and summarises all of them, so the paired summary shows the top of the list too.
  - `top 50 share` and `top 5% share` are computed as before; no other column changes.
- Changed areas and affected producers and consumers: `MEASURES` and the row dictionary in `score_windows` (`src/bike_safety_ca/checks/candidates.py`); `paired` and `summarise` iterate `MEASURES`, so they pick the new ones up. Nothing else reads these columns.
- Pattern inventory: the only places that name a share column are the row dictionary and `MEASURES`; both now derive the top-k names from `TOPS`.
- Verification: `make check` | working tree on db316a2 | 666 passed | slow tests deselected | bsc-implementer.
- Condition inventory: not required (Small).
- Settled decisions (do not re-report): the measures, margins and summary statistics of the command (accepted in power-one-1); the docs changes in the working tree are not staged and are exempt.
- Known limitations and out of scope: the margins written down before the comparison named the top 50 and the top 5% only; the top 25 and top 100 are reported without a margin of their own.

## Review, round 1 — top-shares-1

Verdict: **accepted** (round 1). No correctness findings.

Both the produced top-k share columns and MEASURES derive from TOPS, so the new top 25 and top 100 shares reach pairing and summaries alongside top 50. The denominator remains later crashes, fractional tie-adjusted counts are retained, and zero later crashes produce missing shares. The existing top 50 expression is equivalent and the top 5% calculation is unchanged.

Validation: executed the exact new dictionary comprehension and MEASURES assignment from the snapshot. Checked fractional found counts (2.5/20, 7.5/20 and 20/20), zero found counts with a positive denominator, and zero later crashes; all returned the expected percentages or NaNs. Verified each requested share appears exactly once in MEASURES and reviewed its consumers in `paired`/`summarise` plus the updated fixtures/assertions. Full pandas/numpy integration and `make check` were not rerun; the handoff reports 666 passing tests. No protected files or records were opened.

Ledger: no open findings. Loop top-shares-1 complete. Implementer releases the reviewer lock. Acceptance does not authorize commit, push or merge.
