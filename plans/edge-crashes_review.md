# Review: count a crash recorded just outside the outline at its intersection inside

## Handoff, round 1

- Implementer: `bsc-implementer`, pane `wF:p1`. Base commit `9e2b5bc` (branch `edge-crashes`, from `origin/main`). Snapshot: `/tmp/bsc-review/edge-crashes-r1/` (`staged.diff`, `tree/`). Round 1 of at most 3. Expires (UTC): `2026-11-27T05:57:29Z`.
- The fault: crashes were cut to the area outline (`groups.load(..., outline)`) before `assign_crashes`. A corner a few metres inside a city limit lost every report whose point fell on the other side of the line. On real tables (aggregates): 9 of 470 placed crashes inside one city at 3 corners, 7 of them at one corner; 47 of about 960 in another city.
- Decided by the owner: fix it as its own change; then report how the held-back evaluation moves, with no model re-chosen.
- The change:
  - `junctions.EDGE_REACH_M = 100` (the reach of the name match) and `junctions.assign_in_area`: crashes inside the area are placed exactly as before; crashes outside it within the reach are placed among the area's intersections plus those of the strip beyond the edge (built by `build_junctions` on the buffered outline, renumbered after the area's), and counted only when the intersection they get is in the area. So the result is the old one plus additions, and a crash that belongs to a corner outside is not pulled inside.
  - `holdout.placed` (used by the ranking, hold-out, evaluation, cross-city, candidates, sensitivity, attainable and bike-route checks) loads crashes out to the reach and calls it. `corridors` does the same and then drops outside crashes that were not placed. `report` loads out to the reach, keeps the summaries on crashes inside the outline, and passes the map the inside crashes plus outside cyclist crashes placed at an inside intersection, so the map agrees with the ranking's counts.
- Tests: `test_a_crash_just_outside_the_area_counts_at_an_intersection_inside_it` (made-up streets: nearness, a nearer corner outside, name match, beyond the reach, and agreement with `assign_crashes` when nothing is outside); `test_a_crash_recorded_just_outside_the_outline_counts_at_its_corner` (through `ranking.rank`).
- Expected value changed: in `test_a_small_town_is_ranked_as_worked_out_by_hand` the "outside" crash moves from 5 m to 140 m beyond the outline. At 5 m it now counts by design; moved, every hand-worked figure in that test stays as it was.
- What to report: a crash counted twice or pulled to the wrong intersection; an index clash between the area's intersections and the strip's; a caller left on the old rule that should follow the new one, or the reverse (summaries are meant to stay inside the outline); the map and `movement.place` disagreeing with `assign_in_area` on the crashes passed.
- Verification: `make check` passes (725 tests). On three real areas the additions are 55, 47 and 4 crashes, ids unique.
- Known limitations: `build_junctions` runs a second time on the buffered outline (about doubling placement time). Intersections are still those whose point is inside the outline. A crash on the line between two areas run separately can count in both.

## Review — edge-crashes, round 1

Verdict: **changes required, round 1**. Two confirmed algorithmic boundary cases break the stated placement behavior.

### EDG-001 — the competitor search stops too early (confirmed, blocking, medium)

Location: `network/junctions.py:541–547`, `assign_in_area`.

The crash-loading reach and junction-competitor reach are different. An eligible report can be almost 100 m outside the outline, and its best matching outside junction can lie another 100 m beyond that report. Building competitors only inside `area.buffer(100)` omits such a junction and can wrongly pull the crash into the area.

Concrete made-up geometry, with area x<0: inside junction I at x=-1, report at x=90, outside junction O at x=110. Both junctions have the report's two street names and the report is coded at an intersection. I is a valid name match at 91 m, but O is the better name match at 20 m. The current wider build excludes O because it lies 110 m outside the area, so the report is counted at I. With the complete candidate set, `assign_crashes` selects O and this report must not count inside.

Keep the eligible-crash reach unchanged, but cover the full matching neighborhood of those reports when constructing competitors (up to a further match radius, with the clustering context accounted for). Add a regression with an outside better full-name match beyond the first buffer. This is not a request to count crashes farther outside.

### EDG-002 — rebuilding clusters creates a duplicate outside competitor for an existing inside corner (confirmed by source/control-flow analysis, blocking, medium)

Location: `junctions.py:547–552`, particularly choosing `outer` solely by the rebuilt centroid's position.

`build_junctions` cuts raw junction nodes to its outline before clustering them. Its clusters therefore change when the outline is buffered. A wider cluster can contain the original inside junction but have its new centroid outside. The code appends that cluster as a supposedly separate outside competitor, renumbers it, then drops the report if that duplicate wins.

Concrete made-up streets: Main crosses Oak at x=0 and Elm at x=20, with the area's east edge at x=5. The original build keeps only the Oak node and returns its inside corner at x=0. The wider build includes both nodes: their 12.5 m buffers overlap, producing one symmetric cluster centred at x=10, carrying Main/Oak/Elm. It is classified as outside and appended beside the original x=0 point. A Main/Oak report at x=12 then matches both, selects the duplicate x=10 at 2 m instead of the original inside corner at 12 m, and is discarded. The added test's 40 m spacing avoids this case; use a 20 m cross-boundary spacing to exercise it.

Preserve junction identity across the two candidate sets rather than treating every rebuilt outside centroid as an independent corner. A wider cluster containing the original junction's nodes must not compete with its narrower version as a separate outside corner. Retain the intended behavior for genuinely separate outside corners and verify additions still map to original inside IDs.

### Verification and other observations

Executed the actual AST-extracted `assign_in_area` with synthetic one-dimensional geometry, frame/series and assignment/build stand-ins. The first case counts the report at I, whereas the complete candidate set selects O. The second case drops the report when given the rebuilt x=10 cluster, whereas placement at the original inside corner includes it. The geometric clustering premise follows from `build_junctions`'s node clipping and overlapping 12.5 m buffers; this review did not execute the full GeoPandas clustering pipeline. Please confirm both cases with the real synthetic geometry helpers before changing the code.

The numeric renumbering itself keeps appended IDs disjoint from the original IDs in the reviewed path. Inside and beyond input partitions are disjoint, so the final concatenation does not duplicate an otherwise unique crash ID. Reviewed direct assignment/load callers: hold-out consumers and corridor loading use the new helper; report summaries retain the inside-only frame, and the map prefilters additional cyclist reports through the helper before its existing placement path. No other confirmed caller mismatch was found.

Full pytest/`make check` and the real geospatial pipeline were not independently run because this environment lacks the numerical/dataframe/geospatial test dependencies. The handoff reports 725 passing tests and real-area aggregate probes; those were not independently reproduced. No protected paths, real crash records or real maps were opened and no real area was fitted or scored. The owner-approved evaluation rerun and known cross-area overlap limitation are treated as settled.

Ledger: EDG-001 and EDG-002 open. Request round 2 with a fresh snapshot after testing the findings. Implementer releases the reviewer lock. Review does not authorize a commit, push, merge or evaluation run.

## Handoff, round 2

- Implementer: `bsc-implementer`. Snapshot: `/tmp/bsc-review/edge-crashes-r2/`. Round 2 of at most 3. Expires (UTC): `2026-11-27T06:06:03Z`.
- EDG-001, confirmed and fixed: the intersections beyond the edge are built on `area.buffer(2 * EDGE_REACH_M)`; crashes are still taken only within one reach. Test: `test_a_crash_beyond_the_edge_goes_to_a_better_match_farther_out` (real helpers; the fixture is the reviewer's).
- EDG-002, confirmed and fixed: an intersection of the wider build that lies outside the area is left out of the competitors when it is the same corner as one of the area's: within 25 m of it, or within 60 m and holding all of its streets when it has two or more (the distances at which `build_junctions` joins nodes). The area's own intersection then stands. Test: `test_a_corner_joined_with_a_node_across_the_edge_keeps_its_crashes`.
- On real tables this mattered: of 59 and 456 outside intersections in two areas, 5 and 21 are dropped as the same corner, and the crashes they had been taking (10 and 5) now count inside.
- Verification: `make check` passes (727 tests).
- What to report: whether the same-corner rule can drop a genuinely separate outside corner in a way that pulls a crash inside wrongly; anything left of EDG-001 or EDG-002.

## Review — edge-crashes, round 2

Verdict: **changes required, round 2**. The two new tests cover the original fixtures, but proximity and street-set containment do not establish cluster identity.

### EDG-002 — a shared-node cluster can move beyond the identity-search radius (confirmed by source/control-flow analysis, blocking, medium; remains open)

Location: `src/bike_safety_ca/network/junctions.py:554–564`.

The new 60 m search still admits an outside duplicate of an inside junction when a chain shifts its centroid farther than 60 m. Concrete fixture: Main Street has junction nodes at x=0,20,40,...,160, with Oak Avenue crossing at 0 and Elm Street (or distinct other streets) crossing each remaining node. Use area `box(-300,-300,5,300)` and default `max_cluster_m=None`. The original build contains only the node at 0. The wider build joins the entire chain because adjacent 12.5 m buffers overlap, and its symmetric centroid is x=80. It contains the original Oak node but lies outside every 60 m buffer around the original point, so it survives as a separate outside competitor. A report at x=70 coded Main/Oak, INTERSECTION=Y, DISTANCE=0 matches both: the wider duplicate at 10 m wins over the original at 70 m, and the report is discarded. It should count at the original inside ID under the stated rule. All nodes and the report are within the configured wider/crash reaches.

Track actual member-node identity (or equivalent exact provenance) across builds so that shared clusters are recognized regardless of centroid displacement. Add this chain regression using real geometry helpers; increasing the heuristic distance alone also enlarges the separate-corner problem below.

### EDG-003 — street-set containment removes a genuinely separate outside corner (confirmed by source/control-flow analysis, blocking, medium; new)

Location: `src/bike_safety_ca/network/junctions.py:559–564`.

`build_junctions` merges divided-road blobs only for **equal** name sets. The new exclusion uses a **subset** test, which can remove a distinct junction that the wider build itself deliberately kept separate. Concrete fixture: Main Street crosses Oak Avenue at x=0, and crosses another Oak Avenue segment plus Elm Street at x=40; area east edge x=5. Raw nodes are 40 m apart, so their 12.5 m buffers do not join. Name sets {Main,Oak} and {Main,Oak,Elm} differ, so the exact-name divided-road merge also leaves two distinct corners. Nevertheless, the new identity heuristic removes the outside x=40 corner because it is within 60 m and contains all of the inside corner's street keys.

A report at x=30 coded Main/Elm, INTERSECTION=Y, DISTANCE=0 belongs to the outside corner by full-name matching at 10 m. After the outside corner is removed, it is wrongly counted at the inside corner by nearness at 30 m (Main overlaps, so the names check allows it). This directly violates the requirement not to pull crashes from a genuinely outside intersection. Add a synthetic regression for unequal overlapping name sets and preserve actual cluster identity rather than inferring it from containment/proximity.

### Verification and ledger

EDG-001: **closed for the reported search-reach defect**. Competitors now build out to twice EDGE_REACH_M, while eligible reports retain the original one-reach limit; the new 110 m outside-corner fixture exercises the original failure. Cluster identity remains covered by EDG-002/003.

EDG-002: **open**, original two-node fixture fixed but the chain case above remains. EDG-003: **open**, introduced by the replacement heuristic.

Read the revised helper, clustering implementation, both new tests, and the staged callers. Executed the actual AST-extracted street-containment expression on both synthetic cases: the separate x=40 corner is marked same, while the shared-node x=80 cluster falls outside the spatial candidate radius. The clustering and assignment outcomes above follow from the reviewed buffer radii, exact-name merge and full-name/nearest precedence; they were not independently executed through GeoPandas. This environment lacks pandas, numpy, GeoPandas, Shapely and pytest. The implementer's reported 727 passing tests were not independently reproduced. No protected files or real records were read.

Please confirm these fixtures with the real synthetic geometry helpers before acting. Request round 3 after fixes and checks; the implementer releases the reviewer lock. Review does not authorize a commit, push, merge or evaluation run.

## Handoff, round 3

- Implementer: `bsc-implementer`. Snapshot: `/tmp/bsc-review/edge-crashes-r3/`. Round 3 of at most 3. Expires (UTC): `2026-11-27T06:11:48Z`.
- EDG-002 and EDG-003, both confirmed with the real helpers and fixed as asked, by node membership. `build_junctions` is now a wrapper over `_build_junctions`, which also returns the nodes joined into each intersection (`node`, `iid`, `x`, `y`); its two public return values are unchanged. In `assign_in_area` an intersection of the wider build is left out of the competitors only if it holds a node inside the area: the area's own intersections are made of exactly those nodes (`pts.within(area)`), so that is the same corner. The centroid and street-name rules of round 2 are gone.
- Tests, with the reviewer's fixtures and the real helpers: `test_a_long_chain_across_the_edge_is_still_the_areas_own_corner` (nodes 0 to 160 m, wider centre over 60 m from the area's corner; the coded report counts inside) and `test_a_separate_corner_beyond_the_edge_with_the_same_streets_keeps_its_crash` (inside Main/Oak, outside Main/Oak/Elm 40 m on, two intersections; the report near the second is not pulled inside). The round-2 tests stand.
- Verification: `make check` passes (729 tests). On three real areas the additions are 60, 57 and 11 crashes, ids unique.

## Review — edge-crashes, round 3 (last)

Verdict: **accepted, round 3**. No remaining blocking finding identified in the staged snapshot.

### Finding ledger

- **EDG-001 closed**: competitor construction retains the doubled reach; eligible crashes retain the original 100 m reach. The better outside full-name match beyond the first buffer remains covered by its regression test.
- **EDG-002 closed**: `_build_junctions` now returns raw member nodes with the final merged `iid`. `assign_in_area` excludes a wider cluster if any of its member nodes is inside the original area. This recognizes the original two-node duplicate and the long-chain duplicate without a centroid-distance limit. Original inside points and IDs stand. The two-node test remains and the 0..160 m chain regression covers the round-2 case.
- **EDG-003 closed**: the distance/name-containment heuristic is removed. The separate outside Main/Oak/Elm corner has no inside member node, remains a competitor and retains its crash. The new two-corner regression exercises this even through the nearness path, where both corners are candidates.

### Scope and verification

Reviewed the wrapper extraction, membership provenance through chain splitting and divided-road merging, competitor filtering and renumbering, revised tests, and placement/report callers. The public `build_junctions` still returns the same two values and forwards `max_cluster_m`. Member nodes are taken after final `iid` remapping. Any valid junction node strictly inside the original area has all of its incident selected ways intersecting that area, so the inside-member test agrees with the narrower build's raw-node inclusion rule. The original inside-crash path is unchanged, and additions retain only original inside IDs. No further correctness regression found.

Executed the actual AST-extracted `node_inside`/`shared` statements with standard-library geometry/array stand-ins for the original two-node fixture, the long chain, the separate outside corner, the farther-out competitor and a node exactly on the boundary. All five membership expectations passed. Executed the actual public wrapper with a stub builder: it preserves its two-result interface and forwards the cluster limit. All six changed Python files compile. These checks do not execute real Shapely/GeoPandas clustering or assignment. The environment lacks the required geospatial/dataframe test dependencies, so the implementer's reported `make check` result (729 passing tests) and real-area aggregate probes were not independently reproduced. No protected files, real records or real maps were read.

Final ledger: EDG-001, EDG-002 and EDG-003 all closed. This is the third and final round of edge-crashes. The implementer releases the reviewer lock. Acceptance does not authorize a commit, push, merge or evaluation run.
