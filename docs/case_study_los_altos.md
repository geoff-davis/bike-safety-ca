# Case study: Los Altos

Los Altos on its own has too few bike crashes for the model to be fitted, so
it is fitted together with five whole neighbouring cities and its ranking is
read inside its own limit. This note writes the analysis down so it can be
run again with this code and checked against saved figures. Every setting is
in `config/los_altos.yaml`; the expected results are in
`case_studies/los_altos/`. All figures here are totals; no individual crash
is described.

Until 26 November 2026 the case study used a smaller study area: two-mile
circles around the study's public schools, joined with the city limit. That
area has been retired in favour of whole cities, which is how any other
small city would be handled. Where a figure from it is quoted below for
comparison, the text says so.

## Inputs

| Input | What was used | Can someone else get the same? |
|---|---|---|
| TIMS crash exports | SWITRS Query & Map at tims.berkeley.edu. County: Santa Clara. Cities: Cupertino, Los Altos, Los Altos Hills, Mountain View, Palo Alto, Sunnyvale, one export per city. No crash filters. Crashes, Parties and Victims CSVs for 2015 to June 2026. | Nearly. The provisional years (2025 on) change. |
| CCRS records | data.ca.gov dataset `ccrs`, years 2016–2026, county code 43 and the same cities, as downloaded for the tables of 21 November 2026. | Nearly. CCRS is updated monthly, so later downloads have more recent crashes and some corrections. |
| City limits and area | Census Bureau place outlines of the six cities; the area fitted is the six together. | Yes, the network step downloads them. |
| Streets | OpenStreetMap as of 15 November 2026, cut from that day's Geofabrik extract of Northern California. © OpenStreetMap contributors, ODbL 1.0. | Nearly. A later download has later edits. |

## Settings

From `config/los_altos.yaml`:

- First year 2015 (TIMS no longer offers 2014); a child is a cyclist aged 18
  or under.
- Hold-out windows: fit through 2018 and test on 2019–2022; fit through 2020
  and test on 2021–2022; fit through 2022 and test on 2023 onward.
- Distances in EPSG:26910 (UTM zone 10N).
- From 2023 some Los Altos Police reports carry Palo Alto Police's agency code;
  they are recognised by a Los Altos beat or city and counted for Los Altos.

## Commands

With each city's TIMS export in its own folder under
`data/raw/crashes/tims/`:

```bash
uv run python -m bike_safety_ca.network --config config/los_altos.yaml
uv run python -m bike_safety_ca.crashes download --config config/los_altos.yaml
uv run python -m bike_safety_ca.crashes --config config/los_altos.yaml
uv run python -m bike_safety_ca.checks.holdout --config config/los_altos.yaml \
    --expect case_studies/los_altos/expected_holdout.csv
```

These read and write under `data/raw/` and `data/processed/`. To keep the
tables in a folder of their own, as the cross-city check expects
(`data/processed/los_altos/`), name the folders with each command's `--raw`,
`--out`, `--processed` and `--crashes` options; the guide describes them.

The last command prints the scores and says whether every figure matches the
saved table; it exits with an error if any differs. The guide gives each
command's options.

## What you should get

Crash tables:

| Figure | Value |
|---|---|
| TIMS crashes, 2015–June 2026 | 15,516 |
| CCRS reports kept | 35,813 |
| Merged crashes | 37,474 |

Intersections: 6,470 in the six cities, 805 of them in Los Altos.

Mean rank score over the three windows, street-length model
(`expected_holdout.csv` has every ranking, window and top-25/50/100 count):

| | All cyclists | Cyclists 18 or under |
|---|---|---|
| The six cities | 0.843 | 0.825 |
| Los Altos | 0.847 (two windows) | too few to score |

The six-city test rests on 453, 187 and 337 later cyclist crashes at
intersections in the three windows, 142, 56 and 106 of them children.
Inside Los Altos, past bike crashes alone score 0.671 over the same two
windows.

### What the Los Altos row can and cannot show

The ranking is fitted on all six cities, 6,470 intersections of which 805
are in Los Altos, and read inside the city limit. That is what makes a
fitted ranking possible here at all: fitted alone
(`config/los_altos_city.yaml`), Los Altos falls back to the hand-built
blend and scores 0.822 where the six-city fit scores 0.847. The six cities
have 225 to 367 child crashes at intersections in the training years.

The test is a separate matter. A window with fewer than 30 later crashes is
left unscored, because a score on so few is close to those crashes' own ranks.
Inside Los Altos the three windows hold 18, 9 and 19 later child crashes, so
the city has no child score of its own, and 22 later cyclist crashes of any
age in the middle window, so its all-cyclist mean covers the other two.

None of this says the child ranking is unusable in Los Altos. Its
intersections are part of the six-city test, and that test is the evidence:
quote 0.825 for children across the six cities, not a Los Altos figure.

The six cities have enough child crashes for a ranking of their own. Scored
on later child crashes across them, the ranking fitted to child crashes
averages 0.825 and the one fitted to every cyclist crash 0.818 (the
"All-cyclist ranking" rows of `expected_holdout.csv`). In cities fitted alone
with fewer than 100 child crashes the all-cyclist ranking did better: see
"Too few child crashes" in `where_the_ranking_helps.md`.

## What changes the result

```bash
uv run python -m bike_safety_ca.checks.sensitivity --config config/los_altos.yaml \
    --wide-ways data/processed/network/streets_26910.parquet --leave-out "Palo Alto"
```

runs the check with one choice changed at a time (with the tables in a
folder of their own, add `--processed`, `--crashes` and `--boundaries`). Mean
rank score over the windows that were scored, on the crash tables of 21
November 2026. Los Altos has no child column: none of its windows has 30
later child crashes. Its all-cyclist column covers the first and last
windows:

| Variant | Intersections | Crashes placed (cyclist) | Six cities, all | Six cities, children | Los Altos, all (two windows) |
|---|---|---|---|---|---|
| As configured | 6,470 | 6,367 (1,479) | 0.843 | 0.825 | 0.847 |
| Leaving out the 112 intersections wider than 40 m | 6,358 | 6,039 (1,427) | 0.842 | 0.825 | 0.851 |
| Nearness counts whatever streets the report names | 6,470 | 6,576 (1,485) | 0.843 | 0.823 | 0.845 |
| Chains of close corners split at 25 m | 6,559 | 6,382 (1,481) | 0.842 | 0.825 | 0.845 |

- **How crashes are placed and corners joined** moves no six-city score by
  more than 0.002, and the Los Altos score by 0.004 at most.
- **The area** matters more than any of these. On the former study area
  (two-mile circles around the schools, 4,208 intersections, from 2014) the
  same model scored 0.857 for all cyclists and 0.854 for children, and 0.850
  inside Los Altos. For all cyclists the whole difference is in the last
  test window (0.844 on the six cities against 0.886; the first two windows
  score 0.847 and 0.838 against 0.850 and 0.836). The six cities take in
  all of Palo Alto, whose police reports nearly stop in 2022: see the next
  section. The child score is lower in every window (0.839, 0.828 and 0.807
  against 0.859, 0.858 and 0.844), which reporting does not explain.
- **Not rerun here:** streets of another date, and the city's own city limit
  in place of the Census outline. On the former study area each moved scores
  by 0.003 at most.
- **The crash download date.** Later CCRS downloads add crashes to the last
  test window.

`--wide-ways` names the street table again only so that the command prints
its city-by-city table, used in the next section.

## Changes in police reporting

`python -m bike_safety_ca.checks.reporting --config config/los_altos.yaml`
flags these agency-years in the crash tables used here (injury crashes
reported, against the agency's typical year):

| Agency code | City most of its reports name | Typical year | Fall | Possible fall | Possible rise |
|---|---|---|---|---|---|
| 4312 | Palo Alto | 188 | 2023–2025 (lowest: 8 in 2023) | 2022 (80) | 2015 (361), 2016 (366) |
| 4305 | Los Altos | 63 | 2024 (15), 2026 (14 to 5 November) | 2025 (33) | |

Palo Alto's typical year is itself pulled down by the years with almost no
reports, which is why its ordinary early years are marked as possible rises.

For cyclist injury crashes: falls for 4312 in 2022–2025 (1 in 2023, against a
typical 41) and for 4305 in 2024 (4, against 16); possible falls for 4311
(Mountain View) in 2021 (22, against 47) and 4316 (Sunnyvale) in 2020 (22,
against 48); and possible rises for 4312 in 2015 and 2018. No department has
confirmed a change, so these are questions to ask, not findings.

The two other pictures show more:

- **By report format.** Agency 4316 (Sunnyvale) moves to the CCRS format
  during 2021 with no fall in volume. Agency 4312 (Palo Alto) has no
  earlier-format reports in the last quarter of 2022 and a handful after,
  and at most 14 reports of any kind in a quarter until the third quarter of
  2026, which has 67. Agency 4305 (Los Altos) files its last earlier-format
  reports in the third quarter of 2023, and 1 to 12 reports a quarter since,
  against 8 to 28 before. Agencies 4311 and 4300 stay in the earlier format
  until mid-2026.
- **By severity.** For agency 4305 "complaint of pain" crashes fall from 23–53
  a year in 2015–2021 to 8 in 2022 and 3 in 2023, while the yearly total holds
  at 51 to 54 from 2021 to 2023. Agency 4311 shows a similar shift from 2022.
  That pattern is what a change in how injuries are graded would produce. A
  change in the mix of crashes could produce it too, so it is a question for
  the departments.

The table of lasting changes (`level_steps.csv`) puts numbers on this, over
2015 to 2025 (typical year before → after):

| Agency | Measure | From | Level | Other severities | Read as |
|---|---|---|---|---|---|
| 4305 (Los Altos) | Complaint of pain | 2023 | 35 → 1 | 35 → 32 | fewer reports |
| 4312 (Palo Alto) | Complaint of pain | 2022 | 222 → 6 | 127 → 17 | fewer reports |
| 4312 (Palo Alto) | Visible injury | 2023 | 116 → 6 | 193 → 8 | fewer reports |
| 4312 (Palo Alto) | All injury crashes | 2023 | 338 → 16 | | fewer reports |
| 4311 (Mountain View) | Complaint of pain | 2022 | 120 → 32 | 94 → 145 | regraded |
| 4311 (Mountain View) | Serious injury | 2023 | 11 → 21 | 204 → 152 | more reports |
| 4300 (Cupertino) | Complaint of pain | 2019 | 91 → 37 | 63 → 47 | fewer reports |

For agency 4305 the table reads the change as fewer reports, not regrading:
"complaint of pain" crashes all but stop, and the other severities do not
rise to match over the years after as a whole (they do in 2022 and 2023, then
fall in 2024). The yearly flags on the total mark 4305 only from 2024.

Leaving "complaint of pain" crashes out of the ranking does not help here.
The sensitivity command's last table, mean rank score over the three windows
on the six cities:

| Later cyclist crashes | Trained on all injury crashes | Trained on visible injury and worse |
|---|---|---|
| All injury crashes (977) | 0.843 | 0.836 |
| Visible injury and worse (732) | 0.843 | 0.837 |

What this does to the test of the ranking, for 2023 onwards (the city-by-city
table the sensitivity command prints):

| Rank score, street-length model | All cyclists | Children |
|---|---|---|
| The six cities, scored together | 0.844 | 0.807 |
| Each city scored on its own, averaged | 0.858 | 0.814 |

The window holds 337 later cyclist crashes at intersections, 106 of them
children. Scored together, a Palo Alto intersection with a high score and
no reported crash after 2022 counts against the ranking every time it is
compared with a corner in another city that has one.

The second row scores each city on its own and averages the cities,
weighting each by the number of comparisons it holds, so no intersection is
compared with one in another city. It is a check, not a cure. The score
recovers, which fits the reading that the loss comes from reporting but does
not prove it. The missing crashes are still missing, and the model is still
fitted across all the cities.

On the former study area, which took in only part of Palo Alto, the same
window scored 0.886 for all cyclists and 0.844 for children.

## Data credits

Crash figures here are built from two sources:

- Transportation Injury Mapping System (TIMS), Safe Transportation Research
  and Education Center, University of California, Berkeley.
- California Crash Reporting System (CCRS), California Highway Patrol, via
  data.ca.gov.

Street data © OpenStreetMap contributors, ODbL 1.0. See "Crash
records" in `docs/guide.md` for each source's terms.
