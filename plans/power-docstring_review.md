# Review: power-docstring

## Current state

- Status: complete (round 1 accepted)
- Next action: none
- Base commit: `da752de`; snapshot: `/tmp/bsc-review/power-docstring-r1/`
- Open findings: none
- Decisions needed from the user: none

## Loop

- Loop ID and round: `power-docstring-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-model-review`
- Reviewer: `bsc-reviewer` (Codex), pane `wF:p2`
- Authorized scope: review requests and replies only
- Expires (UTC): `2026-11-24T01:23:54Z`

## Handoff, round 1

- Tier: Small
- Intended behavior and acceptance criteria: docstring only, no behaviour change. The docstring of `fit_street_model` said "a smaller power lets a corner's own record count for more where little is expected", which is wrong: for a power between 1 and 2 the weight on the corner's own count still rises with the expectation (the outside review's D01). It now gives the weight at 2, `alpha * expected / (1 + alpha * expected)`, and at 1, `alpha / (1 + alpha)`. Check the two formulas against the code: `prior_shape = predicted ** (2 - spread_power) / alpha`, and `gamma_blend` gives the own count the weight `predicted / (prior_shape + predicted)`.
- Changed areas and affected producers and consumers: one docstring in `src/bike_safety_ca/model/crash_history.py`.
- Pattern inventory: `grep -n -i power src/bike_safety_ca/model/crash_history.py` shows no other statement about how the weight varies; the comment at `SPREAD_POWER` already gives `alpha / (1 + alpha)`.
- Verification: `make check` | working tree on da752de | 666 passed | slow tests deselected | bsc-implementer.
- Condition inventory: not required (Small).
- Settled decisions (do not re-report): the spread power of 1 and the documents (committed, exempt).
- Known limitations and out of scope: none.

## Review, round 1 — power-docstring-1

Verdict: **accepted** (round 1). No correctness findings.

The revised formulas match the implementation. With expected count mu and prior shape mu**(2-p)/alpha, the weight on the observed count in `gamma_blend` is mu/(shape+mu) = alpha*mu**(p-1)/(1+alpha*mu**(p-1)). At p=2 this is alpha*mu/(1+alpha*mu), increasing with mu for positive alpha; at p=1 it is alpha/(1+alpha), independent of the corner's expectation. The statement that rankings use power 1 matches SPREAD_POWER and the rank function's default.

Validation: reviewed the staged docstring-only source change against `gamma_blend`, prior-shape construction and ranking defaults, and checked the algebra above. No runtime test was needed for this documentation correction. Full `make check` was not rerun; the handoff reports 666 passing tests. No protected files or records were opened.

Ledger: no open findings. Loop power-docstring-1 complete. Implementer releases the reviewer lock. Acceptance does not authorize commit, push or merge.
