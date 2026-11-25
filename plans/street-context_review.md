# Review: street-context

## Current state

- Status: complete (round 1 accepted)
- Next action: none
- Base commit: `475cffd`; snapshot: `/tmp/bsc-review/street-context-r1/`
- Open findings: none
- Decisions needed from the user: none

## Loop

- Loop ID and round: `street-context-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-model-review`
- Reviewer: `bsc-reviewer` (Codex), pane `wF:p2`
- Authorized scope: review requests and replies only
- Expires (UTC): `2026-11-24T02:59:04Z`

## Handoff, round 1

- Tier: Standard
- Intended behavior and acceptance criteria. One more research challenger, specified by the outside reviewer and frozen: the textbook model of `standard_eb` with two added regression columns.
  - A site's neighbours N are the distinct other intersections sharing at least one named street with it, each counted once. Columns: `log(1 + |N|)` and `log(1 + c)`, with `c = (sum of neighbours' car crashes) / (|N| * years)`. With no neighbour, `c` is the area's car crashes per intersection per year and `|N| = 0`. No bike crash enters either column. Coefficients are fitted freely by the same NB2 fit; the gamma update is unchanged.
  - `fit_standard_eb` and `rank_standard` take an optional `streets`; without it they behave as before. `checks.candidates` scores the new version ("Standard empirical Bayes with street context") and accepts it as `--reference`.
  - `membership` moves from `street_effects` to `standard_eb` unchanged (`street_effects` imports it), so `street_context` can use it without a circular import.
  - Docstrings only, no behaviour: the count fallback is described as a rule and not as the model with no predictors; the street-effects module says precisely what its approximation is (regression maximises the penalised likelihood; the determinant is of the effects block alone; this is the less exact `nAGQ = 0` scheme, not the usual Laplace fit; not checked against a package; plug-in effects can move the estimates).
- Changed areas and affected producers and consumers: `model/standard_eb.py`, `model/street_effects.py` (import and docstring), `checks/candidates.py` (version list), tests.
- Pattern inventory: the textbook versions are listed once, in `candidates.TEXTBOOK`, used for scoring, for `--reference` and in the tests.
- Verification: `make check` | working tree on 475cffd | 682 passed | slow tests deselected | bsc-implementer.
- Condition inventory:

  | Condition | Test or probe | Caught / survived / not exercised | Note |
  | --- | --- | --- | --- |
  | a neighbour sharing two streets counted once | `test_street_context_counts_each_neighbour_once_and_uses_no_bike_crash` | caught | sites 1 and 2 share A and B |
  | the site itself is not its neighbour | same test | caught | |
  | no neighbour (alone on its street, or no name) | same test | caught | area rate, 0 neighbours |
  | columns enter only with `streets`; update unchanged | `test_street_context_enters_the_regression_only_when_streets_are_given` | caught | |
  | new version scored, forecast, usable as reference | `test_textbook_models_are_scored_...`, `test_a_textbook_model_can_be_the_reference` (three versions) | caught | |
  | an area with no intersections | none | not exercised | no caller passes one |

- Settled decisions (do not re-report): the two columns and their transformations (the outside reviewer's specification, no alternatives tried); streets told apart by name.
- Known limitations and out of scope: none beyond those of `standard_eb`.

## Review, round 1 — street-context-1

Verdict: **accepted** (round 1). No correctness findings.

The context calculation reduces shared memberships to a binary relation, removes the diagonal, and derives both neighbour count and car total from that same relation. Thus another intersection sharing multiple streets contributes once and the site itself is excluded. The isolated-site fallback and yearly denominator match the specified area rate. No bike counts enter the context function. Optional streets are forwarded only for the new context version; the plain design/gamma update remain unchanged. The TEXTBOOK list reaches scoring and CLI reference choices, and the context fit uses the existing standard fitted-method label accepted by pairing. The moved membership implementation and its import preserve street-effects use.

Validation: executed the exact `membership()` and `street_context()` functions with minimal dense matrix/vector/frame stand-ins and made-up indexed car counts. Checked repeated street names, two sites sharing two streets, self exclusion, correct neighbour car rates, isolated/unnamed sites, output index preservation and an entirely unnamed area. All passed. Reviewed the optional regression-column wiring, reference integration, docstring corrections and regression tests. These are isolated algorithm checks, not SciPy sparse/pandas/statsmodels fitting runs or performance checks. Full `make check` was not rerun; the handoff reports 682 passing tests. No protected files or records were opened.

Ledger: no open findings. Loop street-context-1 complete. Implementer releases the reviewer lock. Acceptance does not authorize commit, push or merge.
