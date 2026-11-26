# Review record: a machine-dependent expected value in one test

## Handoff, round 1

- Implementer: `bsc-implementer`, pane `wF:p1`. Base commit `baa5745` (branch `model-review`, PR #29). Snapshot: `/tmp/bsc-review/ci-tolerance-r1/` (`staged.diff`, `tree/`). Round 1 of at most 3. Expires (UTC): `2026-11-25T02:50:49Z`.
- File: `tests/test_crash_history.py`, one assertion in `test_a_failed_start_does_not_discard_one_that_converged`.
- The problem: the required CI job `test (3.12)` fails on this test alone, in both runs of the pull request (at `79fb6cf` and `baa5745`), each time with a log-likelihood of -149.2195 against the expected -148.877 ± 0.01. `test (3.14)` passes on CI. Locally the value is -148.8772 under Python 3.15 and under Python 3.12 with the same locked numpy 2.5.5, scipy 1.18.1 and statsmodels 0.15.0, so the difference is the runner, not the library versions. I could not reproduce the CI value.
- The change: the tolerance goes from 0.01 to 0.5, with a comment giving both values and the reason. The test's purpose (commit `79fb6cf`) is that a start which converged is not discarded when another start fails; before that fix the call raised. The assertion that the fit returns finite values is unchanged.
- Why the value moves: the made-up case puts all 120 corners on one street, so the street term is nearly constant and the fit ends at a boundary (alpha about 4e-7, street power about -11.8, car shape about 403 locally). The likelihood is close to flat there.
- What to report: whether the loosened assertion still fails on the bug the test was written for; whether a difference of 0.34 points to a defect in choosing among starts and not to a flat likelihood.
- Verification: `make check` passes (686 tests on this branch).
- Known limitation: the cause on the runner is inferred, not shown.

## Review — ci-tolerance, round 1

Verdict: **accepted, round 1**. No correctness findings in this test-only change.

The widened bound admits both supplied results without changing production fitting code, the finite-score assertion or the requirement that this integration fit return successfully. If the original discarded-start bug makes this call raise, a wider numerical tolerance cannot make it pass. More importantly, the adjacent deterministic parametrized test independently checks retention of a converged start after a failed NaN/lower-objective start, minimum objective among successful starts, rejection of nonfinite objectives, and failure when neither start is usable. Those checks remain unchanged and directly protect the selection rule.

The 0.3425 log-likelihood difference alone does not establish a start-selection defect. The actual helper filters to successful finite results and then chooses the minimum objective. The one-street design and reported near-boundary parameters make numerical sensitivity plausible, but neither the exact runner cause nor the assertion that the objective is flat enough to explain this difference was independently reproduced. Treat that explanation in the comment/handoff as a hypothesis rather than a demonstrated diagnosis. Acceptance here is for making an integration test's machine-specific number less restrictive while preserving its failure/retention coverage, not proof of numerical equivalence between those two fits.

Verification: executed the actual AST-extracted `_fit_spread` start-filter and selection control flow against all five deterministic scenarios, using standard-library numerical/vector stand-ins and optimizer-result stubs; all pass. The loss and real optimizer were not evaluated. Checked arithmetically that both reported values lie within -148.877 ± 0.5 and that the reported CI value fails the old ±0.01 bound. Full pytest/`make check` and the numerical integration fit were not rerun because this review environment lacks NumPy, pandas and pytest; the handoff reports 686 passing checks on this branch. CI logs and installed version claims were supplied context, not independently retrieved.

No protected paths or real records were opened. Ledger: no findings; loop ci-tolerance ends accepted at round 1. Implementer releases the reviewer lock. Review does not authorize a commit, push or merge.
