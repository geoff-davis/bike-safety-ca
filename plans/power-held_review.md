# Review: power-held

## Current state

- Status: complete (round 1 accepted)
- Next action: none
- Base commit: `17e7e9c`; snapshot: `/tmp/bsc-review/power-held-r1/`
- Open findings: none
- Decisions needed from the user: none

## Loop

- Loop ID and round: `power-held-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-model-review`
- Reviewer: `bsc-reviewer` (Codex), pane `wF:p2`
- Authorized scope: review requests and replies only
- Expires (UTC): `2026-11-24T01:28:36Z`

## Handoff, round 1

- Tier: Standard
- Intended behavior and acceptance criteria:
  - `fit_street_model` and `rank_intersections` accept a pair `(low, high)` as `spread_power`: the power is fitted by the same bounded search, within that pair, and counted as a fitted parameter in the AIC. `None` still searches `POWER_BOUNDS = (0.5, 2.5)` (the range that was written inline); a float still fixes it. No default changes: the rankings still use `SPREAD_POWER = 1.0`.
  - `checks.candidates` gains the version "Spread power fitted, 1 to 2" (`(1.0, 2.0)`), compared with the reference like the others. The user asked for this comparison.
- Changed areas and affected producers and consumers: `model/crash_history.py` (`fit_street_model`, `rank_intersections`, new `POWER_BOUNDS`), `checks/candidates.py` (`VERSIONS`, the `Power` alias). Other callers of `rank_intersections` (`model/ranking.py`, `model/corridors.py`, `checks/holdout.py`, `checks/attainable.py`, `checks/bike_routes.py`) pass a float, `None` or nothing, so they are unchanged.
- Pattern inventory: the only place the power is searched is the `minimize_scalar` call in `fit_street_model`.
- Verification: `make check` | working tree on 17e7e9c | 667 passed | slow tests deselected | bsc-implementer.
- Condition inventory:

  | Condition | Test or probe | Caught / survived / not exercised | Note |
  | --- | --- | --- | --- |
  | pair given: search inside it | `test_a_pair_of_bounds_holds_the_fitted_spread_power_between_them` | caught | bounds set above the free fit's power; the held power stops at the lower bound |
  | pair counts as a fitted parameter | same test (AIC is the fixed-power AIC + 2) | caught | |
  | `None`: unchanged range | existing tests of the free fit | caught | |
  | new version reaches the fit | `test_each_version_is_fitted_with_its_own_spread_power` | caught | powers of the held version lie in [1, 2] |
  | a pair with low >= high, or non-finite | none | not exercised | scipy raises ValueError, which `rank_intersections` turns into the labelled fallback; no caller passes one |

- Settled decisions (do not re-report): measures and summary statistics of the command; the default of 1.
- Known limitations and out of scope: no validation of the pair beyond scipy's; the ranking CLI has no option for it.

## Review, round 1 — power-held-1

Verdict: **accepted** (round 1). No correctness findings.

The tuple path forwards the supplied bounds to the existing bounded search and counts the selected power as a fitted AIC parameter. None preserves the previous (0.5, 2.5) search, and scalar powers bypass it. `rank_intersections` forwards the expanded argument unchanged; its default remains power 1. The candidate version supplies (1.0, 2.0) explicitly, and existing float/None callers retain their behavior.

Validation: executed the exact fitted-power flag, search branch and AIC expression with a controlled minimizer for None, (1.0, 2.0), 1.0 and 2.0. Both search paths received the expected bounds and fitted-parameter flag; scalar paths made no search call and retained their power; the fitted-power AIC penalty was two higher for equal coefficients/likelihood. Reviewed the new numerical regression, candidate-version checks and defaults. Real numerical optimization and full `make check` were not rerun; the handoff reports 667 passing tests. Invalid bounds were not independently exercised; validation remains delegated to SciPy as documented in the handoff. No protected files or records were opened.

Ledger: no open findings. Loop power-held-1 complete. Implementer releases the reviewer lock. Acceptance does not authorize commit, push or merge.
