# Review: placement-wording

## Current state

- Status: complete (accepted in round 1)
- Next action: none
- Base commit: `c87bd4e`; snapshot: `/tmp/bsc-review/placement-wording-r1/`
- Open findings: none
- Decisions needed from the user: none

## Loop

- Loop ID and round: `placement-wording-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-placement-wording`
- Reviewer: `bsc-reviewer` (Codex)
- Authorized scope: review requests and replies only
- Expires (UTC): 2026-11-22 19:19

## Handoff, round 1

- Tier: Small
- Change:
  1. `docs/guide.md`: the sentence on placing a crash from its street names said "where they come within 60 m of each other". It now states the code's rules:
     - one crossing in the report's city, or crossings all within 60 m of each other, counted as one place;
     - otherwise roads passing within 15 m without crossing;
     - a looser second pass in which a cross street may stop up to 60 m short.

     It points to section 8.5 of `docs/forecasting_model.md`, which is added by PR #10 and merges before this one.
  2. `src/bike_safety_ca/model/crash_history.py` module docstring: `docs/crash_history_method.md` → `docs/forecasting_model.md`.
- Checks: markdownlint 0 errors; `make check` passed (592 tests).
- Please check: the guide sentence against `crashes/locate.py` (`MAX_INTERSECTION_CENTERLINE_GAP_M`, `DIVIDED_ROAD_CLUSTER_M`, `RELAXED_GAP_M`, `_intersection_location`).

## Review, round 1 — bsc-reviewer

- Loop: `placement-wording-1`, round 1.
- Snapshot reviewed: `/tmp/bsc-review/placement-wording-r1/staged.diff`,
  changed guide paragraph and module docstring, `crashes/locate.py`
  constants and recovery branches, and the two-pass call in
  `crashes/merge.py:place_unlocated`.
- Verified the coordination lock names `bsc-implementer placement-wording`,
  `HERDR_ENV=1`, and the requesting Claude's repository and pane `wF:p1`.
- Assessment: the guide correctly distinguishes the 15 m first-pass
  non-crossing gap from the 60 m multiple-crossing cluster and relaxed
  near-miss threshold. The cluster test is maximum pairwise separation,
  consistent with “all within 60 m of each other.” The relaxed pass only
  recovers a gap after the strict check fails; ambiguous multiple crossings
  do not become eligible merely because their roads are nearby. The new
  wording does not claim otherwise.
- Checks: parsed the changed Python module with `ast.parse`; the staged
  Python diff changes only its documentation reference. Inspected the
  source branches and thresholds; no behavior change found.
- Dependency: `docs/forecasting_model.md` is absent from this snapshot.
  The handoff explicitly requires PR #10 to merge first and supply section
  8.5. Acceptance relies on that stated merge order; the reference cannot
  be verified within this snapshot alone.
- Evidence reused: implementer's reported markdownlint success and
  `make check` success (592 tests).
- Limits: did not rerun the suite or access crash records, map data,
  `data/`, `output/` or `.env`.
- Findings: none under the stated merge dependency.
- Verdict: **accepted, round 1**. This completes the review loop; acceptance
  authorizes no commit, push or merge.
