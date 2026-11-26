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
small city would be handled. The last two sections of this note still
report results from it and say so.

## Inputs

| Input | What was used | Can someone else get the same? |
|---|---|---|
| TIMS crash exports | SWITRS Query & Map at tims.berkeley.edu. County: Santa Clara. Cities: Cupertino, Los Altos, Los Altos Hills, Mountain View, Palo Alto, Sunnyvale, one export per city. No crash filters. Crashes, Parties and Victims CSVs for 2015 to June 2026. | Nearly. The provisional years (2025 on) change. |
| CCRS records | data.ca.gov dataset `ccrs`, years 2016–2026, county code 43 and the same cities, as downloaded for the tables of 21 November 2026. | Nearly. CCRS is updated monthly, so later downloads have more recent crashes and some corrections. |
| City limits and area | Census Bureau place outlines of the six cities; the area fitted is the six together. | Yes, the network step downloads them. |
| Streets | OpenStreetMap as downloaded for the tables of 21 November 2026. © OpenStreetMap contributors, ODbL 1.0. | Nearly. A later download has later edits. |

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

## What changes the result (former study area, not rerun)

This section and the next were run on the former study area (4,208
intersections, from 2014, with the City of Los Altos's own city limit and
OpenStreetMap as of 22 August 2026) and have not been repeated on the six
cities. The command works on any config; the figures are a record. The last
row of the table is close to today's area: the six cities with the
unincorporated county between them.

```bash
uv run python -m bike_safety_ca.checks.sensitivity --config config/los_altos.yaml \
    --other-ways path/to/streets_of_another_date.parquet \
    --wide-ways path/to/streets_for_the_city_list_area.parquet --leave-out "Palo Alto"
```

runs the check with one choice changed at a time. Each street table is built
by `python -m bike_safety_ca.network` with its own `--raw` and `--out` folders
(for the wide area, from a copy of the config without the study-area
settings). Mean rank score over the windows that were scored, on the crash
tables of 21 November 2026. Los Altos has no child column: none of its
windows has 30 later child crashes. Its all-cyclist column covers the first
and last windows, with 45 and 32 later crashes:

| Variant | Intersections | Crashes placed (cyclist) | Study area, all | Study area, children | Los Altos, all (two windows) |
|---|---|---|---|---|---|
| As configured | 4,208 | 3,339 (928) | 0.857 | 0.854 | 0.850 |
| Leaving out the 58 intersections wider than 40 m | 4,150 | 3,173 (896) | 0.857 | 0.858 | 0.864 |
| Nearness counts whatever streets the report names | 4,208 | 3,410 (934) | 0.856 | 0.853 | 0.844 |
| Chains of close corners split at 25 m | 4,258 | 3,346 (931) | 0.856 | 0.853 | 0.847 |
| Census city limit in place of the city's own | 4,208 | 3,339 (928) | 0.857 | 0.854 | 0.853 |
| Streets of November 2026 | 4,217 | 3,342 (930) | 0.857 | 0.854 | 0.849 |
| Area built from the city list (295 km²) | 6,912 | 7,164 (1,741) | 0.836 | 0.817 | 0.848 |

- **How crashes are placed and corners joined** moves no study-area score by
  more than 0.004. The Los Altos all-cyclist score moves more, between 0.844
  and 0.864, as expected of a score on 77 later crashes over two windows.
  Counting nearness for reports that name two other streets (71 more crashes,
  6 of them cyclist crashes, mostly freeway crashes above surface streets)
  gives the 0.844.
- **The city limit and the street date** move scores by 0.003 at most. With
  the Census outline the saved table no longer matches exactly.
- **The area** matters most. The fall on the wider area is in the added
  territory and in the last test window: see the next section.
- **The crash download date.** Later CCRS downloads add crashes to the last
  test window.

## Changes in police reporting (former study area, not rerun)

`python -m bike_safety_ca.checks.reporting --config config/los_altos.yaml`
flags these agency-years in the crash tables used here (injury crashes
reported, against the agency's typical year):

| Agency code | City most of its reports name | Typical year | Fall | Possible fall |
|---|---|---|---|---|
| 4312 | Palo Alto | 366 | 2022–2025 (lowest: 8 in 2023) | 2026 (94 to 20 October) |
| 4305 | Los Altos | 66 | 2024 (15), 2026 (12 to 20 October) | 2025 (33) |
| 4300 | Cupertino | 127 | | 2019 (73), 2026 (33 to 20 October; the TIMS export stops in March) |
| 9725 | Unincorporated (highway patrol) | 416 | | 2014 (196) |

No rise is flagged. The 2014 mark is the first year of the tables, which
comes from TIMS alone; whether that is reporting or the source has not been
checked.

For cyclist injury crashes: falls for 4312 in 2022–2025 (1 in 2023, against a
typical 82), 4305 in 2024 (4, against 17) and 4300 in 2026 (6 to 20 October,
against 36); a possible fall for 4311 (Mountain View) in 2014 (23, against
47); and a possible rise for highway patrol area 9330 in 2024 (29, against
15). No department has confirmed a change, so these are questions to ask,
not findings.

The two other pictures show more:

- **By report format.** Agency 4316 (Sunnyvale) moves to the CCRS format
  during 2021 with no fall in volume. Agency 4312 (Palo Alto) has almost no
  earlier-format reports after the third quarter of 2022 and few reports of
  any kind until mid-2026. Agency 4305 (Los Altos) files its last earlier-format
  reports in the third quarter of 2023, and 1 to 12 reports a quarter since,
  against 8 to 28 before. Agencies 4311 and 4300 stay in the earlier format
  throughout.
- **By severity.** For agency 4305 "complaint of pain" crashes fall from 23–53
  a year in 2014–2021 to 8 in 2022 and 3 in 2023, while the yearly total holds
  at 51 to 54 from 2021 to 2023. Agency 4311 shows a similar shift from 2022.
  That pattern is what a change in how injuries are graded would produce. A
  change in the mix of crashes could produce it too, so it is a question for
  the departments.

The table of lasting changes (`level_steps.csv`) puts numbers on this, over
2014 to 2025 (typical year before → after):

| Agency | Measure | From | Level | Other severities | Read as |
|---|---|---|---|---|---|
| 4305 (Los Altos) | Complaint of pain | 2023 | 37 → 1 | 34 → 32 | fewer reports |
| 4312 (Palo Alto) | Complaint of pain | 2022 | 228 → 6 | 132 → 17 | fewer reports |
| 4312 (Palo Alto) | Visible injury | 2023 | 116 → 6 | 225 → 8 | fewer reports |
| 4312 (Palo Alto) | All injury crashes | 2023 | 361 → 16 | | fewer reports |
| 4311 (Mountain View) | Complaint of pain | 2022 | 119 → 32 | 91 → 145 | regraded |
| 4300 (Cupertino) | Complaint of pain | 2019 | 89 → 37 | 59 → 47 | fewer reports |

For agency 4305 the table reads the change as fewer reports, not regrading:
"complaint of pain" crashes all but stop, and the other severities do not
rise to match over the years after as a whole (they do in 2022 and 2023, then
fall in 2024). The yearly flags on the total mark 4305 only from 2024. It
also lists rises in serious injuries for agencies 4311 (11 → 21 from 2023)
and 9340 (25 → 41 from 2020).

Leaving "complaint of pain" crashes out of the ranking does not help here.
The sensitivity command's last table, mean rank score over the three windows
on the study area:

| Later cyclist crashes | Trained on all injury crashes | Trained on visible injury and worse |
|---|---|---|
| All injury crashes (593) | 0.857 | 0.855 |
| Visible injury and worse (451) | 0.855 | 0.855 |

What this does to the test of the ranking, for 2023 onwards (the second table
the sensitivity command prints, and the study-area row from
`expected_holdout.csv`):

| Rank score, street-length model | All cyclists | Children |
|---|---|---|
| Study area, as configured | 0.886 | 0.844 |
| City-list area, all intersections | 0.837 | 0.780 |
| City-list area, intersections inside the study area | 0.885 | 0.839 |
| City-list area, intersections outside it | 0.758 | too few (24) |
| The same, leaving out Palo Alto | 0.810 | too few (23) |
| City-list area, each city scored on its own, averaged | 0.858 | 0.803 |

Palo Alto has 883 of the 2,867 intersections outside the study area and 54% of
the 200 highest-scoring ones, and almost no reported crashes after 2022. Outside
the study area there are 24 later child crashes, 23 without Palo Alto: too
few to score, so those cells show the count.

The last row scores each city on its own and averages the cities, weighting
each by the number of comparisons it holds, so no intersection is compared
with one in another city. It is a check, not a cure. The score recovers,
which fits the reading that the fall comes from reporting but does not prove
it. The missing crashes are still missing, and the model is still fitted
across all the cities.

## Data credits

Crash figures here are built from two sources:

- Transportation Injury Mapping System (TIMS), Safe Transportation Research
  and Education Center, University of California, Berkeley.
- California Crash Reporting System (CCRS), California Highway Patrol, via
  data.ca.gov.

Street data © OpenStreetMap contributors, ODbL 1.0. See "Crash
records" in `docs/guide.md` for each source's terms.
