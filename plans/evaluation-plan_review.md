# Review: evaluation-plan

## Current state

- Status: ready for reviewer
- Next action: reviewer reads the plan and appends its critique
- Base commit: `baa5745`; snapshot: `/tmp/bsc-review/evaluation-plan-r1/`
- Open findings: none yet
- Decisions needed from the user: none

## Loop

- Loop ID and round: `evaluation-plan-1`, round 1 of at most 3
- Implementer (the reviewer replies to this name): `bsc-implementer` (Claude), pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-model-review`
- Reviewer: `bsc-reviewer` (Codex), pane `wF:p2`
- Authorized scope: review requests and replies only
- Expires (UTC): `2026-11-24T19:42:38Z`

## Handoff, round 1

- Tier: Standard
- What this is: a design review, not a code review. Nothing is staged. The
  user asked for the reviewer's criticism of a draft evaluation plan before
  any new city is scored. The plan is `EVALUATION_PLAN.md` at the top of the
  snapshot; `tree/` is the repository at `baa5745` for checking its claims
  (`docs/forecasting_model.md` sections 4.2, 4.11 and 5,
  `plans/model-review-decision.md`, `src/bike_safety_ca/checks/candidates.py`,
  `checks/holdout.py`, `checks/attainable.py`, `model/crash_history.py`).
- Intended behaviour and acceptance criteria: the plan should let the project
  (1) split California cities into development, selection and final-test sets
  that support a claim about the whole state, and (2) judge rankings by a
  measure that rewards being right at the top of the list, since the purpose
  is choosing places to fix.
- What to report: flaws that would make a result under this plan misleading
  or unusable. In particular: leakage between the sets or from outcomes into
  eligibility; whether the primary measure (mean share of later crashes over
  budgets up to 5% of intersections) is well defined, including ties, and
  whether its implied weighting is defensible; aggregation across cities;
  the margin and how it is fixed; whether the plan matches what the code
  can do; anything the plan claims about the code or documents that is wrong.
  Answers to the seven questions in section 10 are welcome. Give each finding
  an ID and say whether it blocks.
- Verification: none run; nothing in the plan has been executed. The city
  counts in section 3 come from CCRS yearly totals by city for 2016 to 2020
  (aggregates, computed outside the repository).
- Settled decisions (do not re-report): 5% of intersections as the first
  budget ceiling; severity stays a secondary measure; the 28 current cities
  and the Los Altos study area are development; B stays the default until
  this evaluation says otherwise.
- Known limitations and out of scope: section 8 of the plan. The reviewer
  sees no crash records and nothing under `data/` or `output/`.

## Design review, round 1 — evaluation-plan-1

Verdict: **changes required before selection or final-test scoring**. This is a review of the proposed design, not staged code. The five findings below are confirmed gaps in the written protocol; examples are hypothetical, not observations from held-back cities.

The proposed primary score is worth keeping. It rewards crash counts and earlier positions, and fractional tie allocation is compatible with the existing `top_share` helper. The five-percent ceiling, secondary severity measure, development designation and retained B default are treated as settled.

### Findings

**EV-001 — blocking: the decision and non-inferiority rule are not specified.** Location: sections 2, 5 Margin and 7. “Kept if its mean ... is no more than 1 percentage point below the reference” is a point-estimate rule, not an uncertainty-based non-inferiority claim. For example, a difference of -0.8 points with an interval [-3.0, +1.4] passes the written mean rule while leaving a substantial loss unresolved. Name the reference explicitly (the code's default reference is the unrestricted fitted power, which is not a named candidate in this plan); define the simplicity ordering, what selects H versus street context, and the treatment of ties and inconclusive results. Distinguish selection from confirmation: freeze one chosen candidate and its comparator before final access, and specify the final claim/failure action. If claiming non-inferiority, predeclare an interval rule such as a one-sided 95% lower bound above -delta, with the resampling unit matching the sampling design. If the rule deliberately uses only the mean, label that accurately and do not claim non-inferiority from it. A one-point loss is a substantive tolerance, not a quantity to enlarge until the available sample has enough precision; use development variation primarily to size the study. A final failure must be reported without choosing a different model on that final set.

**EV-002 — blocking: fitting-only eligibility is contradicted by outcome-year exclusions and inherited comparison gates.** Location: sections 3 held-back preparation, 4, and 7 step 3. Agency exclusions based on record counts need a frozen, explicit rule and a data source: an apparent 2021–2024 drop could be genuine change rather than missing reporting. Deciding after seeing those counts which cities/agencies to remove conditions the evaluation on outcomes even without calculating a model score. Prefer independent completeness evidence, training-only selection rules, or retain such cases in the primary population and report prespecified sensitivity results. Record every attempted city and failure; distinguish unavailable data from a measured zero. Also explicitly supersede the current command's rules: `candidates.paired` filters to at least MIN_LATER=30 later crashes and a successfully fitted reference method. That would exclude many training-eligible small cities and every blend-reference window, contradicting evaluation of the pipeline's deployed fallback. Freeze which production fallback each candidate uses and compare on a common eligible city set even when a fit fails. State that the existing later-count/success filters are not the new primary eligibility rules.

**EV-003 — blocking: the statewide estimand and quota weights do not agree.** Location: section 3 Population/Sampling and section 5 Aggregation. Equal weight per sampled city estimates an eligible-city average only under the corresponding sampling design, not arbitrary regional/size quotas. If two strata contain 90 and 10 eligible cities and their mean differences are +2 and -2 points, equal sample counts and an unweighted average report zero while the eligible-city mean is +1.6 points. Define the target explicitly: eligible incorporated cities with at least 200 intersections/10 fitting crashes, not unincorporated California or every California city. The forced-development cities have no final-test inclusion probability, so a direct finite-population statewide claim also needs to distinguish the new-city population from transport to the already-used cities. Publish stratum population counts, sampling fractions, weights and build-failure accounting; use weights in both the estimate and its interval, or choose proportional sampling and a clearly conditional claim. A crash-weighted estimand likewise needs both outcome weights and sampling weights. Hash ordering does not make data/build failures random. Resolve the 35-city target with an explicit revised allocation and a precision calculation for the new paired measure; merely merging selection into development does not change a 40% final allocation from about 26 to about 40 cities.

**EV-004 — blocking: city hashes do not establish separation of the observations being evaluated.** Location: sections 2–3 and the boundary/build contract. Define the observation and assignment units before hashing. Current `cross.place`/`holdout.placed` use a config's area outline, not automatically a nonoverlapping Census municipal limit. A development city's buffered area could therefore contain an intersection whose later crashes also enter a final city's score. Assign overlapping observation areas to one set or enforce a unique, disjoint scoring universe; audit shared crash/site identities without revealing their outcomes. Agency-level grouping is also preferable where several cities share the same reporting process, or at least must enter the uncertainty/design treatment explicitly. Geographic adjacency alone need not create one giant connected component: distinguish actual overlap/shared administration from merely neighbouring cities. A group touching an already-used development observation cannot become a clean final-test group. Set/group hashes, stratum handling and the effective number of independent groups must be fixed together. Actual overlap was not audited in this snapshot review.

**EV-005 — blocking: the primary denominator, zero-event rule and pooled score need an executable definition.** Location: section 5 and section 6's common top set. For a city with Y=0 later crashes, C(k) is undefined; training-only eligibility does not prevent this. Predeclare its accounting and analysis rule instead of silently dropping it, treating missing as zero, or restoring the current 30-event cutoff. Define whether Y counts all city bike injury crashes or only crashes placed at eligible intersections: the existing command uses placed hits, excluding unplaced/between-intersection crashes, so these are different estimands. Define the street-map/municipal universe for n and report placement coverage without using later coverage to choose cities. Pooling “at each budget” is ambiguous when K differs by city: an absolute budget k cannot be aligned to every city's five-percent ceiling without another rule. A simple explicit option is to compute each city's S_i = mean over its own k=1..K_i and pool as sum(Y_i*S_i)/sum(Y_i), with the appropriate sampling weights from EV-003. Alternatively define one common fractional-budget grid and its rounding. Use the same definition for the low-count stratum and paired candidate/reference comparisons. Fractional ties must apply to any secondary common top set too, or use a frozen outcome-independent tie breaker consistently.

### Answers to section 10

1. Keep actual overlapping observations together; group shared-agency dependence where practicable. Mere adjacency is not automatically label leakage. Document boundaries and the grouping before assignment (EV-004).
2. Keep a selection set if any choice will use new-city scores; it may be smaller, but its allocation must be explicit. If a deterministic candidate choice can be frozen using existing development evidence alone, omit selection and spend the untouched groups on final testing. Do not score the final set and then reinterpret it as selection. The existing development set gives little reason to allocate another 20% of scarce new cities to unrestricted development.
3. Use an eligible-city average as primary for the question “does this help a typical eligible city?”, with design weights where necessary. Keep crash-weighted benefit as the named secondary estimand; neither is universally the right statewide quantity (EV-003).
4. One fixed window per city is a reasonable primary design and avoids counting overlapping windows as independent replications. The stated 2015–2020/2021–2024 window tests new-city transport under a common historical period, not new-time prediction. Preserve the pandemic caveat, independently establish completeness/final status and exposure conventions, and freeze the future-test pipeline and data definitions before that test.
5. Keep the proposed triangular top weighting. With ordered later counts y_r and no ties, S = sum over r<=K of [(K-r+1)/K] * y_r/Y. It is exactly the expected capture under a discrete uniform treatment budget 1..K. State that interpretation; it is defensible if that budget uncertainty is relevant. Equal weighting of marginal corners collapses toward endpoint capture C(K), up to scaling, and loses the preference for earlier positions. For ties, average over a uniformly random order within each tied block; evaluating `top_share` at every k already gives that expectation without consulting later outcomes. The exact random-order baseline is (K+1)/(2n), not precisely 0.025: it is 0.0275 at n=200, K=10. This is a nonblocking clarification.
6. One point may be an acceptable policy tolerance, but the plan does not establish that. Fix its interpretation in crashes forgone/decision cost with the owner; examining development variance before selection is acceptable for planning precision, but should not be the reason to relax the tolerance. Then use the declared decision/interval rule (EV-001).
7. No. Training-only thresholds are necessary but not sufficient if outcome reporting checks, minimum later-event gates, model convergence gates, placement filters or discretionary build replacements change the analysed set (EV-002/EV-005).

### Implementation and verification scope

Before scoring a new selection city, add and test the primary score with hand-worked ties and zeros, both aggregation schemes and their weights, frozen fallback handling, a car-only floor (currently absent from `score_windows`), explicit primary years, and assignment/exclusion manifests. The current summary is conditional on reference fits and later counts; its bootstrap treats cities as exchangeable and needs adjustment if weighted strata or grouped units are adopted. The primary score itself does not yet exist, as the plan correctly anticipates. Do not infer precision for it from the AUC's earlier city count.

Reviewed EVALUATION_PLAN.md and relevant snapshot source/decision documentation. Checked the capture-score position weights/random baseline and the quota-weighting counterexample by elementary arithmetic. No new city was fetched, fitted or scored; no crash records or protected paths were opened. Aggregate city totals, TIMS final-year status and actual cross-city overlaps were not independently verified. This is a mathematical/design critique, not empirical evidence that any candidate wins.

Ledger: EV-001 through EV-005 open, all blocking before selection/final scoring. Revise the plan and request round 2 with a fresh snapshot. Implementer releases the reviewer lock. Review does not authorize commit, push, merge or evaluation runs.

## Handoff, round 2

- Implementer: `bsc-implementer`, pane `wF:p1`. Snapshot: `/tmp/bsc-review/evaluation-plan-r2/`. Round 2 of at most 3. Expires (UTC): `2026-11-24T20:16:11Z`.
- Change: a new section 11 in `EVALUATION_PLAN.md` answers EV-001 to EV-005 and governs where it differs from sections 2 to 7. Sections 1 to 10 are unchanged.
- EV-001: 11.1 (one-sided 95% bound, named order of simplicity, selection sequence, freeze, two final claims, failure reported).
- EV-002: 11.2 (no exclusion after outcomes, frozen reporting check as a sensitivity result, present gates dropped, fallbacks scored, log of attempts).
- EV-003: 11.3 (target population stated, all larger new cities built, simple random sample of smaller ones, regions for reporting only).
- EV-004: 11.4 (municipal-limit scoring universe, agency groups as the assignment and resampling unit).
- EV-005: 11.5 (Y, S, ties, exact random baseline, zero outcomes, pooled figure).
- Settled by the owner on 24 November 2026 (do not re-report): the margin is 1 percentage point; one third of the larger new cities to selection and two thirds to final test, none to development; the equal-weight city mean is primary and the crash-pooled figure secondary.
- Nothing has been run or scored.

## Design review, round 2 — evaluation-plan-1

Verdict: **changes required, round 2**. Section 11 substantially improves the protocol. EV-001, EV-002 and EV-005 are closed as design findings. Two related specifications remain under EV-003 and EV-004; neither requires changing the owner's settled margin, larger-city allocation or choice of city mean as primary.

### Remaining findings

**EV-003 — blocking until the primary population/aggregation is explicit.** Location: EVALUATION_PLAN.md sections 5 Aggregation and 11.3, lines 187–191. Section 5 makes the city mean primary for cities at or over the threshold and pools the smaller cities. Section 11.3 instead describes the primary city mean as answering the question about a typical eligible city, after proposing a census of larger cities and a sample of smaller cities. Please state whether the primary mean/decision rule is confined to the larger stratum, with the smaller stratum reported separately, or covers both. The latter cannot simply concatenate the two samples without weights: hypothetically, 10 larger and 90 smaller eligible cities, with all 10 larger and 10 randomly sampled smaller cities analysed, produce a 50/50 sample mean rather than the target's 10/90 city mean. The smaller-city sample weights itself *within that stratum*, not when combined with a census of another stratum. Either retain separate estimands explicitly (the larger-city mean primary, smaller-city results separate), or preserve the owner's equal weight per target city using stratum expansion weights in the combined estimate and uncertainty. Also label the city-mean estimand as conditional on Y>0 under 11.5; cities with no later events remain accounted for but are not represented in that mean. This is a confirmed ambiguity/incomplete specification, not a claim that a weighted analysis has already been implemented incorrectly.

**EV-004 — blocking: a mixed-size agency group has no single assignment rule.** Location: sections 3 Assignment, 11.3 and 11.4, lines 66, 188–189 and 197–198. Moving assignment to agency groups is the right response, but the larger-city 1/3 selection, 2/3 final rule supersedes the old rule only for those cities. No replacement assignment rule is given for smaller cities, so the old 20/40/40 rule remains for them. A new agency group containing one larger and one smaller city and hash value 0.10 would therefore be selection for its larger member and development for its smaller member, violating the single-group assignment requirement. State one group-level rule, including mixed-size groups and the priority of forced development, and specify how the smaller-city sample is taken relative to that group assignment. A straightforward option is the same 1/3 selection, 2/3 final split for every untouched agency group, with a frozen probability sample of smaller cities whose set is inherited from the group. Other designs are possible if inclusion probabilities and inference agree. Define shared-agency groups as disjoint/transitive groups where cities have multiple agency codes. Produce the group manifest and effective group counts before treating the approximate 21/43 city numbers as achievable precision. This is a confirmed conflict in the written rules; no actual grouping feasibility or agency data was inspected.

### Closed findings and safeguards to preserve

- **EV-001 closed:** the one-sided bound, fixed owner margin, ordered selection, inconclusive action and final freeze/failure rule now distinguish selection from confirmation. In the freeze record, name the exact comparator even when H is selected over B, and require both final claims to pass for an overall success. No comparator can be chosen after final scores.
- **EV-002 closed:** outcome-based reporting exclusions have moved to a frozen sensitivity analysis, later-count and successful-fit gates are explicitly superseded, and fallback predictions remain scored. Keep build-failure accounting visible: if some cities cannot be built, the result is conditional on the observed population unless missing-city transport is separately justified. Missing data must never become Y=0.
- **EV-005 closed:** placed-crash denominator, city score, ties, exact random baseline, zero-event accounting and pooled definition are explicit. In code, zero-event cities contribute a literal zero numerator rather than evaluating 0 times undefined S; an all-zero set has an undefined pooled score. Preserve paired common city sets and apply the declared zero rule to bootstrap replicates.
- For EV-004, municipal limits plus development-overlap grouping resolve the earlier buffered-area issue in principle. The snapshot's existing `groups.group_crashes` clips crash geometry to the supplied outline before placement, so municipal outlines should be supplied consistently for both crashes and sites. Keep boundary ownership and identity checks deterministic; do not reintroduce a buffer for outcomes.

### Verification and ledger

Read the revised plan and the named handoff; checked the relevant snapshot holdout/grouping code and inherited comparison gates. Verified the mixed-group hash example and unequal sampling example directly from the written rules. No city was fetched, fitted or scored, no records were opened, and no empirical completeness, counts or overlap claims were independently verified. This remains design review, not acceptance of future code.

Ledger: EV-001 closed; EV-002 closed; EV-003 open (primary population/stratum aggregation); EV-004 open (single coherent group assignment/sampling rule); EV-005 closed. Both open items block selection/final scoring under the plan. Request round 3 with a fresh snapshot after revision; it is the last round of this loop. The implementer releases the reviewer lock. This verdict does not authorize commits, pushes, merges or evaluation runs.

## Handoff, round 3

- Implementer: `bsc-implementer`, pane `wF:p1`. Snapshot: `/tmp/bsc-review/evaluation-plan-r3/`. Round 3 of 3. Expires (UTC): `2026-11-24T20:18:09Z`.
- Change: new subsection 11.7 only. EV-003: the primary mean is the larger stratum alone (a census), conditional on at least one later crash, with the count left out reported; strata are never combined; the smaller stratum is secondary, pooled and without a decision rule. EV-004: one agency-group assignment rule for all groups (one third selection, two thirds final), the 20/40/40 split withdrawn, mixed-size groups handled, group bootstrap stated.
- Nothing has been run or scored.

## Design review, round 3 — evaluation-plan-1

Verdict: **accepted, round 3 (final)**, as a design. No blocking findings remain. This accepts the protocol with section 11.7 governing the earlier assignment and aggregation descriptions; it does not certify code that has yet to be built or any empirical result.

### Disposition of remaining findings

**EV-003 closed.** Section 11.7, lines 219–221, explicitly confines the primary equal-weight city mean and the section 11.1 decisions to the larger stratum, conditional on Y>0, with zero-event city counts reported. Smaller cities are separate and descriptive. Consequently a census of larger cities is no longer concatenated with a sample of smaller cities to estimate an unweighted statewide city mean. The claim is about untouched, eligible larger cities with observed placed later crashes, not all California cities. The smaller-city combined pool in line 225 remains a description of the built sample, not a representative statewide smaller-city estimate.

**EV-004 closed.** Lines 222–227 withdraw both earlier size-dependent split rules, assign every member of an agency group using one hash and one 1/3–2/3 rule, preserve each member's analysis stratum, retain development priority, and resample whole groups for the primary city mean. The mixed-size group example from round 2 now has a single consistent set. The primary bootstrap must retain multiplicities when a group is drawn more than once and average its cities rather than its group means, as the written rule now indicates.

### Nonblocking clarification and implementation checkpoints

The phrase “simple random sample of smaller cities” in line 221 (and 11.3) is superseded in substance by the explicit procedure in line 225: certainty inclusion of smaller members of larger-city groups plus hash sampling of smaller-only groups. That is not a simple random sample of individual smaller cities. Consolidate that wording when producing the final protocol. It does not block this design because line 225 acknowledges the nonrandom component, requires separate as well as combined reporting, and line 221 confines its claim to the sampled cities rather than the smaller-city population.

Before selection access, preserve the previously specified build/test and freeze steps: publish a fixed group/assignment manifest, use disjoint connected groups when agency links are transitive, record development overlap and failed builds, determine actual independent-group counts and precision, and test the new score, tie handling, zero handling, fallbacks, and group resampling on made-up data. The approximate city counts are not evidence of adequate precision after grouping. If the manifest leaves too few untouched groups to evaluate the claim, report that limitation rather than relaxing separation or the margin. No further design round is requested in this loop.

### Verification and final ledger

Reviewed the round-3 snapshot plan, its AGENTS.md and the named handoff. Checked the revised aggregation and group-assignment rules against both remaining counterexamples. No city was fetched, fitted or scored; no protected data paths or records were opened. Actual group sizes, city counts, completeness and achieved precision remain unverified empirical inputs.

Ledger: EV-001 closed; EV-002 closed; EV-003 closed; EV-004 closed; EV-005 closed. Loop evaluation-plan-1 ends accepted at round 3 of 3. The implementer releases the reviewer lock. Design acceptance does not authorize a commit, push, merge or evaluation run; those actions retain their separate authorization requirements.

## Loop 2 (`evaluation-plan-2`): handoff, round 1

- Implementer: `bsc-implementer`, pane `wF:p1`, worktree `/home/geoff/Projects/personal/bike-safety-ca-evaluation`. Snapshot: `/tmp/bsc-review/evaluation-plan-severity-r1/`. Round 1 of at most 3. Expires (UTC): `2026-11-24T22:01:31Z`.
- What this is: a design review of one addition to the accepted plan, section 12 of `EVALUATION_PLAN.md`. Sections 1 to 11 are as accepted in loop 1 and are not up for review.
- Intended behaviour: (12.2) report a pooled fatal-and-severe companion result beside the primary one, with no decision rule; (12.3) flag cities whose minor-injury recording changed, by a threshold fixed in advance, with flagged cities kept in the primary result and dropped only in the prespecified sensitivity result.
- What to report: whether 12.3 reintroduces selection on outcomes; whether the threshold and periods are defensible given that they were set after seeing the development cities and one new city (Los Angeles); whether the companion's role is stated without overclaiming; anything that conflicts with section 11.
- Settled by the owner (do not re-report): severity stays out of the decision rule; the companion is pooled, not a city mean.
- Verification: the development figures in 12.2 and 12.3 were computed outside the repository from aggregate counts; nothing was run on a held-back city. `tree/` is the index at `baa5745`; the measure code was unstaged then and not part of this review.

## Design review — evaluation-plan-2, round 1

Verdict: **accepted, round 1**, as a design addition. No new blocking finding. This review concerns section 12 only; it does not reopen the accepted decisions in sections 1–11 or independently validate the numerical evidence quoted in section 12.

### Outcome selection and the reporting sensitivity

Section 12.3 does select on later outcomes for the sensitivity subset: the minor ratio uses 2021–2024 counts. Fixing a threshold before computing rankings does not make that subset outcome-independent. However, the addition explicitly retains every flagged city in the primary and severe companion results, does not change model selection, and restricts exclusions to the already-designated sensitivity analysis. On those terms it does not restore the primary-population defect in EV-002 and is compatible with 11.2.

Describe the sensitivity as the result for cities not flagged by these particular count diagnostics, rather than a corrected or unbiased estimate for cities with complete reporting. Genuine changes in crashes, travel, injury mix or classification can also change the ratio. An unflagged city is not independently certified complete. If the sensitivity differs from the primary result, report both; it cannot replace the primary result or rescue its decision rule.

The 0.5/1.5 cutoffs and equal four-year periods are defensible as a frozen, descriptive stress test. They are substantive thresholds, not calibrated false-positive rates or a validated test of reporting completeness. Excluding 2020 avoids putting that year in the baseline, but the later period still includes pandemic/recovery effects. The cutoffs are asymmetric under reciprocation (a twofold fall versus a 1.5-fold rise); that is acceptable for this stated use, provided it is intentional and stays fixed.

Los Angeles is correctly disclosed as an exception to the prospective timing claim: its later counts prompted this amendment. The rule and its performance on Los Angeles are therefore informed by that city's outcomes, even though its rankings have not been scored. Do not describe this diagnostic as independently specified before seeing all new-city outcomes. This limited access need not move Los Angeles or its agency group to development under this amendment: no candidate ranking is evaluated and neither primary inclusion nor the selection rule changes. Preserve the access log, fixed assignment and threshold; do not use the flags or seen ratios to search for a favourable salt, rebuild the held-out sets, tune candidates or alter the decision rule.

### Severe companion

The role in 12.2 is appropriately limited: the same all-injury-fitted rankings, the same spatial universe, all larger cities retained, pooled severe outcomes, and no model-choice rule or pass/fail. Reporting a floor comparison separately from candidate-versus-comparator evidence avoids treating a gain over history as proof that one model design beats another. The required first-paragraph disclosure when the primary passes but severe benefit is unresolved is useful; an interval including zero is inconclusive, not evidence of equivalence or absence of benefit. Police-recorded crash severity also does not establish which road user's injury was severe, so retain the wording “bike crashes recorded as fatal or severe,” rather than claiming cyclist-specific severe injuries without the corresponding person-level definition.

### Nonblocking implementation/reporting clarifications

- Freeze whether 12.3 counts all crashes geographically within municipal limits or a specified city-street/agency subset. The Los Angeles example concerns city streets, whereas the stated rule concerns a city total. Those are not interchangeable. Hypothetically, street counts falling from 100 to 20 and highway counts rising from 100 to 180 leave the combined ratio at 1. Show agency/road scope in the diagnostic output; the city-total rule need not detect every agency change.
- Specify zero baseline counts, missing years and unknown severity separately from measured zeros before applying the check. Missing/undefined ratios must be visibly unassessable, not silently pass as unflagged. The existing snapshot reporting code already distinguishes unknown severity; preserve that distinction.
- For the companion use severe-outcome Y and severe capture in the pooled numerator and denominator. A city with zero severe events contributes zero numerator and denominator, and an all-zero pool or bootstrap replicate is undefined, not a score of zero. Resample whole agency groups with multiplicities and recompute the pooled ratio in each replicate, rather than averaging city differences.
- Label interval coverage explicitly. The displayed 5th–95th percentile development range is a central 90% interval; its lower endpoint can also serve as a one-sided 95% lower bound. It must not be labelled a two-sided 95% interval. All companion intervals remain descriptive, without a multiplicity-adjusted family of model superiority claims.

### Verification and ledger

Read section 12, its governing sections 11.1–11.7, snapshot AGENTS.md and the named handoff; inspected relevant snapshot reporting/severity source definitions. Checked the aggregate-mask example arithmetically. No crash records or protected paths were opened, and no city was fetched, fitted or scored. The supplied Los Angeles and development counts, reporting-change explanation, severity-definition history and empirical intervals were not independently verified.

Ledger: no new blocking findings; EV-001 through EV-005 remain closed from loop 1. Loop evaluation-plan-2 ends accepted at round 1. The implementer releases the reviewer lock. This is design acceptance, not acceptance of future implementation or authorization to commit, push, merge or run an evaluation.
