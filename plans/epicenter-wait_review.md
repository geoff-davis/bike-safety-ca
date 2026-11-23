# Review: epicenter-wait

## Current state

- Status: complete (round 2 accepted)
- Base commit: `2215944`; snapshot: `/tmp/bsc-review/epicenter-wait-r1/`
- Decisions needed from the user: none

## Loop

- Loop ID and round: `epicenter-wait-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-epicenter-wait`
- Reviewer: `bsc-reviewer` (Codex)
- Authorized scope: review requests and replies only
- Expires (UTC): 2026-11-23 04:51

## Handoff, round 1

- Tier: Small.
- Problem: twice today, `await_agreement` raised "closed without I Agree" a moment after the browser opened, before the user could click. The cause is that `wait_for_selector("#shiny-modal", state="hidden")` returns at once while the Bootstrap modal is in the DOM but not yet visible: it fades in. `_SHOWN_OR_AGREED` only checks that the button exists.
- Fix: unless the click is already recorded, wait (up to 90 s) for `#shiny-modal` to be visible before waiting for it to close. The script still never clicks the agreement.
- Evidence: with the fix, the user read the agreement and clicked "I Agree"; the script logged "Agreed" and pulled all six tables.
- Tests: a new FakePage test checks the order of the waits (visible, then hidden); the existing agreement tests are unchanged. `make check` passed.
- Status: ready for reviewer

## Review, round 1 — epicenter-wait-1

Verdict: **changes required** (round 1).

- **EW-001 — confirmed control-flow race, medium:** `src/bike_safety_ca/hospital/epicenter.py:365–367`. The separate acceptance check and visible-only wait can miss a legitimate acceptance. Concrete sequence: `_SHOWN_OR_AGREED` completes; `evaluate(_AGREED)` returns false; the user clicks I Agree and the modal closes before `wait_for_selector(..., state="visible")` observes it. The trusted-click watcher has now recorded acceptance, but the new wait never checks that flag again and times out after 90 seconds, aborting the pull. Previously the hidden wait plus final acceptance check allowed this sequence. Wait for visibility **or recorded acceptance** together, then retain the hidden wait and final trusted-click check. Add a regression case where acceptance occurs between the initial check and observation of visibility; checking an already-true flag at function entry does not cover it.

Validation: read the staged diff, click watcher, agreement predicates, download call site and existing fake-page tests. Executed the exact extracted `await_agreement()` with controlled page stand-ins: normal acceptance and already-recorded acceptance succeed, dismissal raises RuntimeError, an open modal times out, and acceptance between the new check and visibility observation raises TimeoutError despite the acceptance flag being true. This confirms the branch behavior under that event ordering; it is not a live Playwright/browser timing reproduction. The added order-of-waits test covers the fade-in ordering but not this transition. Full `make check` was not rerun; the handoff reports it passed. No protected files or records were opened, and no agreement was clicked by the review.

Finding ledger: EW-001 open. Test the finding before changing the staged files, then request round 2 with a fresh snapshot. Review does not authorize commit, push or merge. Implementer releases the reviewer lock.

## Handoff, round 2

- Snapshot: `/tmp/bsc-review/epicenter-wait-r2/`. Round 2 of at most 3.
- EW-001 confirmed by reading: with `evaluate(_AGREED)` false, a click during the fade-in closes the modal before `wait_for_selector(visible)` sees it, and that wait then times out at 90 s.
- Fix: a single `wait_for_function(_VISIBLE_OR_AGREED)` that is true when `__bscAgreed` is set or `#shiny-modal` is visible as Playwright counts it (a client rect, and not `visibility: hidden`). The hidden wait and the final `_AGREED` check are kept.
- Tests: the order test now expects `_SHOWN_OR_AGREED`, then `_VISIBLE_OR_AGREED`, then the hidden wait. A headless Chrome run on a local stand-in modal gave: `display:none` false, shown true, `visibility:hidden` false, agreed while hidden true. `make check` passed.
- Status: ready for reviewer

## Review, round 2 — epicenter-wait-1

Verdict: **accepted** (round 2). No new correctness findings.

**EW-001 — closed, fixed:** `_VISIBLE_OR_AGREED` checks visibility and the recorded trusted-click flag in one browser predicate. Acceptance before the visibility poll now completes that wait even when the modal has already been removed. The subsequent hidden wait and final acceptance check remain, preserving rejection of dismissal without acceptance and timeout of a dialog left open. The watcher is unchanged and the script still does not click the agreement.

Validation: executed the exact snapshot visibility predicate in Node with controlled DOM stand-ins for absent modal, display-none, visible, visibility-hidden, and accepted-then-removed states; all five passed. Executed the exact extracted `await_agreement()` with page stand-ins for normal acceptance, already-recorded acceptance, acceptance between waits, dismissal and a modal left open; all five returned or raised as expected. Reviewed the updated order-of-waits test. These are isolated predicate/control-flow checks, not a live Playwright/browser integration run. Full `make check` was not rerun; the handoff reports it passed. No protected files or records were opened, and no agreement was clicked by the review.

Final ledger: EW-001 closed; no open findings. Loop epicenter-wait-1 complete. Implementer releases the reviewer lock. Acceptance does not authorize commit, push or merge.
