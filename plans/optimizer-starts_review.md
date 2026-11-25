# Review: optimizer-starts

## Current state

- Status: complete (round 1 accepted)
- Next action: none
- Base commit: `b2cd08a`; snapshot: `/tmp/bsc-review/optimizer-starts-r1/`
- Open findings: none
- Decisions needed from the user: none

## Loop

- Loop ID and round: `optimizer-starts-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-model-review`
- Reviewer: `bsc-reviewer` (Codex), pane `wF:p2`
- Authorized scope: review requests and replies only
- Expires (UTC): `2026-11-23T21:54:07Z`

## Handoff, round 1

- Tier: Small
- Intended behavior and acceptance criteria: `_fit_spread` in `model/crash_history.py` runs the optimiser from two starts. It took the start with the lowest value and only then checked that it had converged. A failed start with a NaN value (kept by `min` when it comes first) or with a lower value therefore threw away a start that converged, and the fit raised "did not converge". Now the fit is chosen among starts that converged with finite value and parameters; if there is none, it raises the same error as before, so `rank_intersections` still falls back with its reason.
- Changed areas and affected producers and consumers: `_fit_spread` only. Callers: `fit_street_model` (fixed power, and the profile search over the power), and through it `rank_intersections`, the corridor and bike-route checks.
- Pattern inventory: the only other "pick then check" is not present; `fit_history_model` (statsmodels) has a single fit and checks its convergence flag.
- Verification: `make check` | staged tree on b2cd08a | 654 passed | slow tests deselected | bsc-implementer.
- Condition inventory:

  | Condition | Test or probe | Caught / survived / not exercised | Note |
  | --- | --- | --- | --- |
  | Failed start with NaN first, converged start second | `test_the_fit_is_chosen_among_the_starts_that_converged` case 1; `test_a_failed_start_does_not_discard_one_that_converged` (real optimiser, 120 corners on one street, fixed power) | Caught: both failed before the fix | |
  | Failed start with a lower finite value | case 2 | Caught: failed before the fix | |
  | Both converged | case 3 | Survived (passed before and after) | keeps the lower |
  | Converged flag but infinite value | case 4 | Survived | |
  | No usable start | case 5 | Survived | raises as before |

- Settled decisions (do not re-report): the objective, the two starts and the bounds on the power are unchanged on purpose.
- Known limitations and out of scope: with the power fitted, the same one-street case still raises, because a later candidate power has both starts fail; that is a rank-deficient made-up case (one street) and it falls back with its reason. No real city window was affected: every blend row in the cross-city hold-out tables has under 100 training crashes. The fixture and the defect come from an outside review of the model; its documentation points are handled separately.

## Review, round 1 — optimizer-starts-1

Verdict: **accepted** (round 1). No correctness findings.

The change filters optimizer results before comparing objectives, requiring convergence and finite objective/parameter values. Failed or nonfinite starts therefore cannot discard an available usable result. The minimum-objective choice among usable starts and the existing RuntimeError text when none qualify are preserved. The objective, starts, optimizer settings and profile-power behavior remain as described in the settled scope.

Validation: executed the exact extracted selection/return block with controlled fit results and minimal numeric stand-ins for nine cases: failed NaN first, failed lower finite objective, both converged, infinite objective, success-flagged NaN objective, NaN parameter, infinite parameter, both starts failed, and success flags with no finite usable result. All selected the expected likelihood or raised the unchanged error. Reviewed the new real-optimizer regression and parametrized tests, and the surrounding `_fit_spread`/`fit_street_model` paths. A real SciPy/numpy fit and full `make check` were not rerun; the handoff reports 654 passing tests, including the real-optimizer fixture. No protected files or records were opened.

Ledger: no open findings. Loop optimizer-starts-1 complete. Implementer releases the reviewer lock. Acceptance does not authorize commit, push or merge.
