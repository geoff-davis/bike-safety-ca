# Case study: Los Altos

This is the analysis the method was built on, written down so it can be run
again with this code and checked against the original figures. Every setting
is in `config/los_altos.yaml`; the expected results are in
`case_studies/los_altos/`. All figures here are totals; no individual crash
is described.

## Inputs

| Input | What was used | Can someone else get the same? |
|---|---|---|
| TIMS crash exports | SWITRS Query & Map at tims.berkeley.edu. County: Santa Clara. Cities: Cupertino, Los Altos, Los Altos Hills, Mountain View, Palo Alto, Sunnyvale, Unincorporated. No crash filters. Crashes, Parties and Victims CSVs in two batches: 2014–2023 (final), exported 22 August 2026, and 2024–March 2026 (provisional). | Not fully. TIMS no longer offers 2014, and provisional years change. |
| CCRS records | data.ca.gov dataset `ccrs`, years 2016–2026, county code 43 and the same cities, downloaded 28 October 2026. | Nearly. CCRS is updated monthly, so later downloads have more recent crashes and some corrections. |
| Road centerlines | The City of Los Altos citywide road-centerline layer, used only to place crashes that have no coordinates. | Yes, from the city's public map service. |
| City limit | The City of Los Altos city-limit layer, fetched from the city's map service (`city_limit_url` in the config). It is not kept in this repository: the city's website policy does not allow passing its content on without permission. | Yes, the download fetches it. If it fails, the Census outline is used instead and the result differs slightly (see below). |
| Study area | 2-mile (3,218.7 m) circles around 19 public school sites, joined with the city limit: 124 km². Eighteen schools are named in the config (`area_schools`) and placed from the California Department of Education's public school directory, which the area step downloads; the second Bullis Charter campus is a point placed by hand (`area_points`). The directory is not kept in this repository: the department's copyright statement asks for permission before its material is reproduced. | Yes, while the directory lists these schools at the same coordinates (checked with the copy downloaded in August 2026). If the automated download is turned away, download "Public Schools and Districts (TXT)" from <https://www.cde.ca.gov/ds/si/ds/pubschls.asp> and save it as `data/raw/schools/pubschls.txt`. |
| Streets | OpenStreetMap as of 22 August 2026 (`osm_date` in the config). © OpenStreetMap contributors, ODbL 1.0. | Yes, the download asks for the map at that time. |

## Settings

From `config/los_altos.yaml`:

- First year 2014; a child is a cyclist aged 18 or under.
- Hold-out windows: fit through 2018 and test on 2019–2022; fit through 2020
  and test on 2021–2022; fit through 2022 and test on 2023 onward.
- Distances in EPSG:26910 (UTM zone 10N).
- From 2023 some Los Altos Police reports carry Palo Alto Police's agency code;
  they are recognised by a Los Altos beat or city and counted for Los Altos.
- Crash reports coded "Unincorporated" are matched to "Santa Clara County" in
  the centerline layer.

## Commands

With the TIMS exports in `data/raw/crashes/tims/<batch>/`:

```bash
uv run python -m bike_safety_ca.network --config config/los_altos.yaml
uv run python -m bike_safety_ca.crashes download --config config/los_altos.yaml
uv run python -m bike_safety_ca.crashes --config config/los_altos.yaml \
    --centerlines path/to/road_centerlines.parquet
uv run python -m bike_safety_ca.checks.holdout --config config/los_altos.yaml \
    --expect case_studies/los_altos/expected_holdout.csv
```

The last command prints the scores and says whether every figure matches the
saved table; it exits with an error if any differs.

## What you should get

Crash tables:

| Figure | Value |
|---|---|
| TIMS crashes, 2014–March 2026 | 24,883 |
| of which in 2014 | 1,910 (272 involving a bicycle) |
| CCRS reports kept | 55,678 |
| Merged crashes | 59,821 |

Intersections: 4,208 in the study area, 803 of them in Los Altos.

Of 1,336 located cyclist injury crashes in the study area, 27 have no cyclist
age recorded, 19 of them in 2026 (of that year's 50), when the records come
from CCRS alone. They count toward "all cyclists" and not toward the child
figures.

Of the 6,701 located injury crashes used (cyclist or motor-vehicle-only, 2014
on), 3,339 are placed at an intersection, 928 of them cyclist crashes.

Mean rank score over the three windows, street-length model
(`expected_holdout.csv` has every ranking, window and top-25/50/100 count):

| | All cyclists | Cyclists 18 or under |
|---|---|---|
| Study area | 0.857 | 0.854 |
| Los Altos | 0.850 (two windows) | too few to score |

The study-area test rests on 261, 114 and 218 later cyclist crashes at
intersections in the three windows, 87, 40 and 76 of them children.

### What the Los Altos row can and cannot show

The ranking is fitted on the whole study area, 4,208 intersections of which
803 are in Los Altos, and read inside the city limit. That is what makes a
child ranking possible here at all: Los Altos alone has 28 to 46 child
crashes at intersections in the training years, the study area 174 to 261.

The test is a separate matter. A window with fewer than 30 later crashes is
left unscored, because a score on so few is close to those crashes' own ranks.
Inside Los Altos the three windows hold 18, 9 and 18 later child crashes, so
the city has no child score of its own, and 22 later cyclist crashes of any
age in the middle window, so its all-cyclist mean covers the other two.
Before the floor was added this table gave 0.855 and 0.847 for the row; those
were the same rankings scored on those few crashes.

None of this says the child ranking is unusable in Los Altos. Its
intersections are part of the study-area test, and that test is the evidence:
quote 0.854 for children across the study area, not a Los Altos figure.

The study area has enough child crashes for a ranking of its own. Scored on
later child crashes across the study area, the ranking fitted to child
crashes averages 0.854 and the one fitted to every cyclist crash 0.851 (the
"All-cyclist ranking" rows of `expected_holdout.csv`). In cities fitted alone
with fewer than 100 child crashes the all-cyclist ranking did better: see
"Too few child crashes" in `where_the_ranking_helps.md`.

## What changes the result

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

## Changes in police reporting

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
