"""SWITRS / TIMS crash tables from hand-made exports.

TIMS (tims.berkeley.edu) requires a free account, so exports are done by hand
and put in ``<tims folder>/<batch>/``.  Expected files per batch folder:

    Crashes.csv   Parties.csv   Victims.csv      (TIMS standard SWITRS export headers)

Name the batch folder e.g. ``2014-2023_final`` or ``2024-2026_provisional``; a
folder name containing ``provisional`` flags every crash in it as provisional.
Where batches overlap, the later folder (by name) wins.

Outputs: crashes_4326.parquet and crashes_<local>.parquet (one row per crash;
point geometry where SafeTREC geocoded it), parties.parquet, victims.parquet,
bicycle_parties.parquet (bicycle parties with an e-bike evidence tier; see
``ebike``), crashes_year_summary.csv, crashes_agency_reporting.csv and
crashes_ingest_report.json.  All source columns are kept.  These are individual
police records: write them only to a git-ignored folder.

COLLISION_TIME is HHMM but often written without the leading zero and with a
trailing space ("849 " is 08:49); use the derived collision_time and
collision_hour columns.  2500 means unknown.

Reporting agency: one department's reports are sometimes filed under another's
code (the two may share a records system).  ``reporting_agency`` moves those
back using the config's ``agency_reassignments`` and is otherwise JURIS.

Reporting gaps: an agency can stop submitting reports to the state while
crashes keep happening.  crashes_agency_reporting.csv compares each agency-year
with that agency's own typical year; the other agencies in the same year only
excuse a move they share, so that a region-wide dip does not trip it, and a
partial last year is judged against the part of it covered.  Its ``change``
column marks falls and rises, certain and possible.  Crashes in an agency-year
marked as a fall carry agency_reporting_gap = True (use it for within-year
shares such as timing).  For year-over-year trends drop
agency_has_reporting_gap, which marks every year of an agency with any gap;
dropping only the gap years keeps those agencies in early years and
exaggerates declines.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from bike_safety_ca.config import Reassignment
from bike_safety_ca.crashes import ebike
from bike_safety_ca.io import CRS_WGS84, write_dual, write_table

REQUIRED_CRASH_COLS = [
    "CASE_ID",
    "COLLISION_DATE",
    "COLLISION_SEVERITY",
    "PEDESTRIAN_ACCIDENT",
    "BICYCLE_ACCIDENT",
]


def _read(p: Path) -> pd.DataFrame:
    return pd.read_csv(p, dtype=str, low_memory=False, encoding="utf-8-sig", on_bad_lines="warn")


def parse_collision_time(raw: pd.Series) -> pd.DataFrame:
    """Parse SWITRS HHMM text into 'HH:MM' and an integer hour; invalid or 2500 becomes missing."""
    digits = raw.fillna("").astype(str).str.strip()
    well_formed = digits.str.fullmatch(r"\d{1,4}")
    padded = digits.str.zfill(4)
    hour = pd.to_numeric(padded.str[:2], errors="coerce")
    minute = pd.to_numeric(padded.str[2:], errors="coerce")
    valid = well_formed & hour.between(0, 23) & minute.between(0, 59)
    return pd.DataFrame(
        {
            "collision_time": (padded.str[:2] + ":" + padded.str[2:]).where(valid),
            "collision_hour": hour.where(valid).astype("Int64"),
        },
        index=raw.index,
    )


def _text(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def reporting_agency(
    crashes: pd.DataFrame, reassignments: Sequence[Reassignment] = ()
) -> pd.Series:
    """JURIS, with reports filed under another agency's code moved back to their own."""
    juris = _text(crashes["JURIS"])
    for rule in reassignments:
        moved = pd.Series(False, index=crashes.index)
        if rule.beat_prefix and "BEAT_NUMBER" in crashes:
            moved |= _text(crashes["BEAT_NUMBER"]).str.startswith(rule.beat_prefix)
        if rule.city and "CITY" in crashes:
            moved |= _text(crashes["CITY"]).str.upper().eq(rule.city.upper())
        if rule.from_year is not None:
            year = crashes["year"] if "year" in crashes else pd.Series(pd.NA, index=crashes.index)
            moved &= pd.to_numeric(year, errors="coerce").ge(rule.from_year).fillna(False)
        juris = juris.mask(juris.eq(rule.filed_as) & moved, rule.agency)
    return juris


FALL, RISE, POSSIBLE_FALL, POSSIBLE_RISE = "fall", "rise", "possible fall", "possible rise"
# A last year whose records reach this share of it (about 13 December) is taken as whole.
FULL_YEAR = 0.95


def typical_year(counts: pd.Series, band: float) -> float:
    """The median of an agency's yearly counts, leaving out the years far from it.

    A year is left out when it is below ``band`` times the median or above the
    median divided by ``band``; the median is then taken again, until the set
    of years settles.  So a gap of several years does not pull the level down
    towards itself.  With fewer than three years left in, every year is used.
    """
    kept = pd.Series(True, index=counts.index)
    level = float(counts.median())
    for _ in range(10):
        level = float((counts[kept] if kept.sum() >= 3 else counts).median())
        if not level:
            break
        now = counts.ge(band * level) & counts.le(level / band)
        if now.equals(kept):
            break
        kept = now
    return level


def agency_reporting_gaps(
    crashes: pd.DataFrame,
    min_relative_ratio: float = 0.4,
    min_baseline: float = 20.0,
    look_ratio: float = 0.6,
    chance: float = 0.001,
    reassignments: Sequence[Reassignment] = (),
    span: tuple[int, int] | None = None,
    records_to: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Per reporting agency (see reporting_agency) and year, mark counts far from the agency's typical year.

    Each agency is judged against itself.  ``baseline`` is its typical year
    (``typical_year``, over every finished year, so that a gap at the start is
    seen as well as one at the end) and ``agency_ratio`` = crashes / expected,
    where ``expected`` is the baseline, or the part of it that an unfinished
    last year covers.

    The other agencies can only excuse a move, never cause a mark.
    ``region_ratio`` is the median of the same ratio over the other agencies
    large enough to judge, and ``relative_ratio`` = agency_ratio /
    region_ratio, with region_ratio held between ``look_ratio`` and its
    inverse for the division (the ``region_ratio`` column is as measured, so
    the three columns do not divide out where it lies outside that range).
    The others so excuse a moderate shared move, not a collapse: when every
    agency's count falls to a fraction it is more likely the reporting than
    the crashes.  A year is marked in ``change`` as a

    - "fall" when both ratios are under ``min_relative_ratio`` (0.4), or a
      "rise" when both are over its inverse (2.5);
    - "possible fall" or "possible rise" when both are beyond ``look_ratio``
      (0.6, or 1.67) but not both beyond the stronger line.

    So a moderate fall that the other agencies share (2020, say) is not
    marked, a collapse they share still is, and one agency's change is never
    marked against another.  A mark also needs a
    baseline of at least ``min_baseline`` and a count that chance alone would
    give less often than ``chance`` (a Poisson count around the expected
    number).  ``reporting_gap``
    is true for a "fall" only.

    Where no other agency is large enough (``basis`` is "own history only") a
    fall in reporting cannot be told from a real fall everywhere.

    A last year is unfinished when ``records_to``, by default the last crash
    date of ``crashes``, comes before about 13 December (``FULL_YEAR``).  It
    is judged against the part of the year up to that date, its ``basis``
    says so, and it is left out of the typical year; where it is the only
    year there is no baseline and nothing is marked.  That date is only a guess at where the records end: if
    they run later, reporting stopped early and the year is worse than it
    looks.  Rises are not marked in an unfinished year.

    ``span`` gives the first and last year to judge, for a subset of crashes
    (cyclist crashes, say) whose own last year may come before the records
    end: without it, years with none at all after that would go unjudged."""
    from scipy.stats import poisson

    columns = [
        "reporting_agency",
        "year",
        "crashes",
        "baseline",
        "expected",
        "agency_ratio",
        "region_ratio",
        "relative_ratio",
        "basis",
        "change",
        "reporting_gap",
    ]
    known = crashes.dropna(subset=["year"])
    if "JURIS" not in known or known.empty:
        return pd.DataFrame(columns=columns)
    juris = reporting_agency(known, reassignments)
    counts = (
        known.assign(reporting_agency=juris, year=known.year.astype(int))
        .groupby(["reporting_agency", "year"])
        .size()
        .unstack(fill_value=0)
    )
    first, last_year = span or (int(counts.columns.min()), int(counts.columns.max()))
    years = range(
        min(first, int(counts.columns.min())), max(last_year, int(counts.columns.max())) + 1
    )
    counts = counts.reindex(columns=years, fill_value=0)
    # The part of the last year the records cover, where they stop before December.
    part, ends = 1.0, ""
    if records_to is None and "collision_date" in known:
        records_to = pd.to_datetime(known.collision_date, errors="coerce").max()
    if records_to is not None and pd.notna(records_to) and records_to.year == years[-1]:
        covered = records_to.day_of_year / 365
        if covered < FULL_YEAR:
            part = covered
            ends = f"; year judged to {records_to:%-d %b %Y}, the last crash date"
    if part < 1:
        # An unfinished year says nothing about a typical one; alone, it leaves none to judge by.
        typical = counts.iloc[:, :-1].apply(typical_year, axis=1, band=look_ratio)
        if len(years) == 1:
            typical = pd.Series(float("nan"), index=counts.index)
    else:
        typical = counts.apply(typical_year, axis=1, band=look_ratio)
    scale = pd.Series(1.0, index=counts.columns)
    scale.iloc[-1] = part
    ratios = counts.div(typical.where(typical > 0), axis=0).div(scale, axis=1)
    large = typical.ge(min_baseline).to_numpy()
    table, levels, parts = ratios.to_numpy(float), typical.to_numpy(float), scale.to_numpy(float)
    rows = []
    for i, (agency, series) in enumerate(counts.iterrows()):
        baseline = float(levels[i])
        others = table[large & (np.arange(len(table)) != i)]
        for j, year in enumerate(years):
            n = int(series.iloc[j])
            expected = baseline * float(parts[j])
            own = float(table[i, j])
            region = float(np.median(others[:, j])) if len(others) else float("nan")
            alone = pd.isna(region)
            # The others excuse a shared move only as far as the "possible" line.
            shared = 1.0 if alone else min(max(region, look_ratio), 1 / look_ratio)
            relative = own / shared
            change = ""
            if baseline >= min_baseline and not pd.isna(own):
                if own < 1:
                    mildest = max(own, relative)
                    rare = poisson.cdf(n, expected) < chance
                    if rare and mildest < min_relative_ratio:
                        change = FALL
                    elif rare and mildest < look_ratio:
                        change = POSSIBLE_FALL
                elif year != years[-1] or part == 1:
                    mildest = min(own, relative)
                    rare = poisson.sf(n - 1, expected) < chance
                    if rare and mildest > 1 / min_relative_ratio:
                        change = RISE
                    elif rare and mildest > 1 / look_ratio:
                        change = POSSIBLE_RISE
            rows.append(
                {
                    "reporting_agency": agency,
                    "year": year,
                    "crashes": n,
                    "baseline": baseline,
                    "expected": round(expected, 1),
                    "agency_ratio": round(own, 3),
                    "region_ratio": round(region, 3),
                    "relative_ratio": round(relative, 3),
                    "basis": ("own history only" if alone else "against other agencies")
                    + (ends if year == years[-1] else ""),
                    "change": change,
                    "reporting_gap": change == FALL,
                }
            )
    return pd.DataFrame(rows, columns=columns).astype({"reporting_gap": bool})


def _latest_batch(
    frames: list[pd.DataFrame], keys: list[str], winning: pd.Series | None = None
) -> pd.DataFrame:
    """Concatenate batches; where batches overlap, rows from the later batch win.

    ``winning`` gives the batch each crash row was taken from (indexed by
    CASE_ID).  A crash's parties or victims then come from that batch alone,
    so that one removed in a corrected export does not survive from an older
    one.  Rows are left alone where the winning batch holds no such table; a
    table with a header and no rows counts as held.
    """
    combined = pd.concat(frames, ignore_index=True)
    if winning is not None and "CASE_ID" in combined:
        batch = combined.CASE_ID.map(winning)
        named = {frame.attrs.get("tims_batch") for frame in frames} | set(combined.tims_batch)
        supplied = batch.isin(named)
        combined = combined[~supplied | combined.tims_batch.eq(batch)]
    present = [key for key in keys if key in combined]
    return combined.drop_duplicates(subset=present, keep="last") if present else combined


def load_batches(
    tims: Path,
) -> tuple[list[pd.DataFrame], list[pd.DataFrame], list[pd.DataFrame]]:
    """Crash, party and victim frames from every batch folder, oldest name first."""
    crashes: list[pd.DataFrame] = []
    parties: list[pd.DataFrame] = []
    victims: list[pd.DataFrame] = []
    for batch in sorted(p for p in tims.glob("*") if p.is_dir()):
        prov = "provisional" in batch.name.lower()
        files = {f.stem.lower(): f for f in batch.glob("*.csv")}
        c = next((files[k] for k in files if k.startswith("crash")), None)
        if c is None:
            print(f"skipping {batch}: no Crashes.csv")
            continue
        df = _read(c)
        df["tims_batch"] = batch.name
        df["provisional_batch"] = prov
        missing = [k for k in REQUIRED_CRASH_COLS if k not in df.columns]
        if missing:
            raise ValueError(
                f"{c}: missing expected columns {missing}; got {list(df.columns)[:20]}"
            )
        crashes.append(df)
        for key, lst in (("part", parties), ("victim", victims)):
            f = next((files[k] for k in files if k.startswith(key)), None)
            if f is not None:
                d = _read(f)
                d["tims_batch"] = batch.name
                d.attrs["tims_batch"] = batch.name  # kept even if the file has no rows
                lst.append(d)
    return crashes, parties, victims


def build(tims: Path, out: Path, crs: str, reassignments: Sequence[Reassignment] = ()) -> bool:
    """Read the TIMS batches under ``tims`` and write the crash tables to ``out``.

    Returns False, with a message, when there are no exports to read.
    """
    if not tims.exists() or not any(tims.glob("*/*.csv")):
        print(f"No TIMS exports found under {tims}/<batch>/; crash tables not built.")
        return False
    crashes, parties, victims = load_batches(tims)
    c = pd.concat(crashes, ignore_index=True)
    before = len(c)
    c = c.drop_duplicates(subset=["CASE_ID"], keep="last")  # overlapping batches: later file wins
    winning = c.set_index("CASE_ID").tims_batch
    c["collision_date"] = pd.to_datetime(c["COLLISION_DATE"], errors="coerce")
    # One date format is read for all batches; a batch in another (an export
    # saved again from a spreadsheet) would lose its dates, and with them its
    # years and its links to CCRS.
    unread = c.COLLISION_DATE.fillna("").str.strip().ne("") & c.collision_date.isna()
    if unread.any():
        batch = c.tims_batch[unread].iloc[0]
        mine = c.tims_batch.eq(batch)
        file = next(f for f in (tims / batch).glob("*.csv") if f.stem.lower().startswith("crash"))
        raise ValueError(
            f"{file}: {int((unread & mine).sum())} of {int(mine.sum())} COLLISION_DATE "
            f"values not understood (for example {c.COLLISION_DATE[unread & mine].iloc[0]!r}). "
            "Export the batch again, or write its dates the same way as the other batches."
        )
    c["year"] = c.collision_date.dt.year
    if "COLLISION_TIME" in c:
        c[["collision_time", "collision_hour"]] = parse_collision_time(c.COLLISION_TIME)
    for col in ("POINT_X", "POINT_Y", "LATITUDE", "LONGITUDE"):
        if col in c:
            c[col] = pd.to_numeric(c[col], errors="coerce")
        else:
            c[col] = pd.NA
    # TIMS writes 0,0 (or blanks) for crashes SafeTREC could not geocode
    has_pt = c.POINT_X.notna() & c.POINT_Y.notna() & (c.POINT_X != 0) & (c.POINT_Y != 0)
    c["geocoded_by_safetrec"] = has_pt
    c["ped_involved"] = c.PEDESTRIAN_ACCIDENT.fillna("").str.upper().eq("Y")
    c["bike_involved"] = c.BICYCLE_ACCIDENT.fillna("").str.upper().eq("Y")
    tier_counts: dict[str, int] = {}
    c["ebike_involved"] = False
    if parties:
        party_table = _latest_batch(parties, ["CASE_ID", "PARTY_NUMBER"], winning)
        write_table(party_table, out, "parties")
        if {"STWD_VEHICLE_TYPE", "CHP_VEH_TYPE_TOWING", "VEHICLE_MAKE"} <= set(party_table):
            bikes = ebike.bicycle_parties(party_table)
            write_table(bikes, out, "bicycle_parties")
            c["ebike_involved"] = c.CASE_ID.isin(bikes.loc[bikes.ebike, "CASE_ID"])
            tier_counts = {str(k): int(v) for k, v in bikes.ebike_tier.value_counts().items()}
    if victims:
        write_table(
            _latest_batch(victims, ["CASE_ID", "PARTY_NUMBER", "VICTIM_NUMBER"], winning),
            out,
            "victims",
        )
    gaps = agency_reporting_gaps(c, reassignments=reassignments)
    flagged = gaps[gaps.reporting_gap.astype(bool)]
    gap_keys = set(zip(flagged.reporting_agency, flagged.year))
    if "JURIS" in c:
        c["reporting_agency"] = reporting_agency(c, reassignments)
    else:
        c["reporting_agency"] = ""
    c["agency_reporting_gap"] = [
        (j, int(y)) in gap_keys if pd.notna(y) else False
        for j, y in zip(c.reporting_agency, c.year)
    ]
    # Trends need a constant set of agencies: drop every year of a gap agency.
    c["agency_has_reporting_gap"] = c.reporting_agency.isin(set(flagged.reporting_agency))
    geom = gpd.points_from_xy(c.POINT_X.where(has_pt), c.POINT_Y.where(has_pt))
    g = gpd.GeoDataFrame(c, geometry=geom, crs=CRS_WGS84)
    write_dual(g, out, "crashes", crs)
    summary = (
        c.groupby(["year", "provisional_batch"])
        .agg(
            crashes=("CASE_ID", "size"),
            ped=("ped_involved", "sum"),
            bike=("bike_involved", "sum"),
            geocoded=("geocoded_by_safetrec", "sum"),
        )
        .reset_index()
    )
    summary.to_csv(out / "crashes_year_summary.csv", index=False)
    gaps.to_csv(out / "crashes_agency_reporting.csv", index=False)
    (out / "crashes_ingest_report.json").write_text(
        json.dumps(
            {
                "rows_read": before,
                "unique_case_ids": int(len(c)),
                "geocoded_pct": round(100 * float(has_pt.mean()), 1),
                "years": sorted(int(y) for y in c.year.dropna().unique()),
                "collision_time_parsed_pct": round(
                    100 * float(c["collision_hour"].notna().mean())
                    if "collision_hour" in c
                    else 0.0,
                    1,
                ),
                "bicycle_party_ebike_tiers": tier_counts,
                "agency_reporting_gaps": [
                    {"reporting_agency": j, "year": int(y), "crashes": int(n), "baseline": b}
                    for j, y, n, b in flagged[
                        ["reporting_agency", "year", "crashes", "baseline"]
                    ].itertuples(index=False)
                ],
            },
            indent=1,
        )
    )
    print(summary.to_string(index=False))
    for j, y, n, b in flagged[["reporting_agency", "year", "crashes", "baseline"]].itertuples(
        index=False
    ):
        print(f"WARNING reporting gap: agency {j} {y}: {n} crashes vs baseline {b:g}")
    return True
