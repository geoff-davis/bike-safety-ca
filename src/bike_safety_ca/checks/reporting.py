"""Has police reporting changed?  ``python -m bike_safety_ca.checks.reporting --config ...``.

A ranking built from police reports treats a fall in reports as a fall in
crashes.  Departments change records systems, stop filing some kinds of
report, or file under another agency's code, and California's move from
SWITRS to CCRS is a time when this is likely.  Run this before trusting any
comparison across years or across cities.

For each reporting agency and year it counts injury crashes, cyclist injury
crashes, and the share of injury crashes found only in CCRS (not in the TIMS
export).  A year is flagged when the agency's count is far below or far above
its own typical year, and the other agencies did not move the same way (the
rule in ``crashes.tims.agency_reporting_gaps``).  So a moderate region-wide
fall such as 2020 is not flagged, though a collapse shared by every agency
is, and one agency's change is never flagged against another.  A flag is a "fall" or "rise" (under 0.4 of the typical year, or
over 2.5 times it) or a "possible" one that is worth a look (under 0.6, or
over 1.67 times).

Two more pictures show what changed.  Reports per quarter by report format
show when each agency moved to CCRS and whether its volume held up afterwards.
Injury crashes per year by severity show a change in how injuries are graded,
which moves crashes between severities without changing the total.

A table of lasting changes of level (``level_steps``) lists each agency whose
yearly count settles at a new level, in all injury crashes or at one
severity, with the year and the level before and after.  It catches what the
yearly flags miss: a step smaller than their lines, and a department that
stops filing its least serious crashes, or grades them differently, while
its total holds.

It writes the tables as CSV and one picture per measure, a small chart per
agency, to ``output/reporting/``.

A flag is a prompt to ask the department, not proof: real crashes can fall
too.  All figures are totals per agency and year.
"""

from __future__ import annotations

import argparse
import logging
import math
from pathlib import Path
from typing import Any

import pandas as pd

from bike_safety_ca import config as settings
from bike_safety_ca.crashes.tims import (
    FALL,
    FULL_YEAR,
    POSSIBLE_FALL,
    POSSIBLE_RISE,
    RISE,
    agency_reporting_gaps,
)
from bike_safety_ca.io import crs_tag

COLUMNS = [
    "merged_id",
    "CASE_ID",
    "COLLISION_SEVERITY",
    "year",
    "collision_date",
    "reporting_agency",
    "CITY",
    "source",
    "injury_crash",
    "bike_involved",
    "possible_duplicate_of",
]
MEASURES = {
    "injury_crashes": ("Injury crashes reported per year", 20.0),
    "cyclist_injury_crashes": ("Cyclist injury crashes reported per year", 8.0),
}
CCRS_ONLY = "ccrs_only_share"
FORMAT, SEVERITY = "reports_by_format", "injury_crashes_by_severity"
# Report formats.  TIMS does not document this: it is read from the style of
# the case number.  Reports that local police file through CCRS carry an
# eight-digit number starting with 8; earlier ones have seven digits, and the
# Highway Patrol's own numbers (eight digits starting with 9) predate CCRS.
# These are conventions inferred from the numbers, not a documented field: a
# number in none of the known styles is shown as "not recognised", never
# counted as the earlier format.
EARLIER, CCRS_FORMAT, CCRS_ALONE, UNRECOGNISED = (
    "Earlier format (SWITRS), inferred",
    "CCRS format, inferred",
    "In CCRS only, not in the TIMS export",
    "Case number style not recognised",
)
FORMAT_COLOURS = {
    EARLIER: "#0072b2",
    CCRS_FORMAT: "#e69f00",
    CCRS_ALONE: "#f3d48a",
    UNRECOGNISED: "#999999",
}
# COLLISION_SEVERITY codes, least severe first, on one hue from light to dark.
SEVERITIES = {
    "4": "Complaint of pain",
    "3": "Visible injury",
    "2": "Serious injury",
    "1": "Fatal",
}
NO_SEVERITY = "Not recorded"
# A lasting step in an agency's yearly counts (``level_step``): the new level under
# 0.6 of the old or over 1.67 times it, three years or more on each side, and a
# level of 20 a year on the higher side.
STEP_RATIO, STEP_YEARS, STEP_LEVEL = 0.6, 3, 20.0
STEPS, ALL_INJURY = "level_steps", "All injury crashes"
FEWER, MORE, REGRADED = "fewer reports", "more reports", "regraded"
# A step at one severity is called regrading when the other severities change the
# opposite way by between this share of it and the inverse (a half to twice).
REGRADED_SHARE = 0.5
# ...and only when that severity is a fifth or more of the agency's injury crashes at
# its higher level, in the same years: beside a much larger group, the group's own drift decides the share.
REGRADED_BAND = 0.2
SEVERITY_COLOURS = dict(
    zip(SEVERITIES.values(), ["#c6dbef", "#6baed6", "#2171b5", "#08306b"], strict=True)
) | {NO_SEVERITY: "#c4c4c4"}
# The check of minor-injury recording (``minor_injury_change``): the two least
# severe grades, per year, in a later period against an earlier one.  2020 is in neither.
MINOR = ("3", "4")
MINOR_BEFORE, MINOR_AFTER = (2016, 2019), (2021, 2024)
MINOR_FALL, MINOR_RISE = 0.5, 1.5
# Not judged when more than this share of a period's injury crashes has no severity.
MINOR_UNGRADED = 0.1
CHANGED, STEADY, NOT_ASSESSABLE = "flagged", "not flagged", "not assessable"
LINE, FLAG, INK, MUTED, GRID = "#2f6fb5", "#b3261e", "#1f2328", "#6b7280", "#e5e7eb"


def load(folder: Path, crs: str, first_year: int) -> pd.DataFrame:
    """Injury crashes, possible duplicate reports removed, located or not."""
    crashes = pd.read_parquet(folder / f"crashes_merged_{crs_tag(crs)}.parquet", columns=COLUMNS)
    kept = crashes[
        crashes.possible_duplicate_of.isna()
        & crashes.injury_crash.astype(bool)
        & crashes.year.ge(first_year)
    ].copy()
    kept["year"] = kept.year.astype(int)
    kept["reporting_agency"] = kept.reporting_agency.astype("string").fillna("").str.strip()
    return kept[kept.reporting_agency.ne("")]


def agency_names(crashes: pd.DataFrame) -> pd.Series:
    """A label per agency code: the code and the city most of its reports name."""
    city = crashes.CITY.astype("string").str.title().fillna("no city")
    top = city.groupby(crashes.reporting_agency).agg(lambda s: s.value_counts().index[0])
    return top.index.to_series() + " · mostly " + top


def all_years(crashes: pd.DataFrame) -> list[int]:
    """Every year from the first crash to the last; empty for an empty table."""
    if crashes.year.notna().sum() == 0:
        return []
    return list(range(int(crashes.year.min()), int(crashes.year.max()) + 1))


def yearly(crashes: pd.DataFrame, years: list[int] | None = None) -> pd.DataFrame:
    """Crashes per agency (rows) and year (columns), every year present.

    ``years`` sets the columns, so that a subset with no crashes in some
    years (or none at all) still lines up with the full table."""
    years = all_years(crashes) if years is None else years
    table = pd.crosstab(crashes.reporting_agency, crashes.year)
    return table.reindex(columns=years, fill_value=0)


def flags(
    crashes: pd.DataFrame,
    min_baseline: float,
    span: tuple[int, int] | None = None,
    records_to: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """The agency-years whose count is far from the agency's typical year, either way.

    ``change`` says which: a "fall" or "rise", or a "possible" one that is
    worth a look.  ``span`` is the first and last year of the whole record,
    and ``records_to`` its last crash date, when ``crashes`` is a subset of it.
    """
    found = agency_reporting_gaps(
        crashes.assign(JURIS=crashes.reporting_agency),
        min_baseline=min_baseline,
        span=span,
        records_to=records_to,
    )
    kept = found.loc[found.change.ne("")]
    return kept.drop(columns="reporting_gap").reset_index(drop=True)


def ccrs_only_share(crashes: pd.DataFrame) -> pd.DataFrame:
    """Share of each agency-year's injury crashes that are in CCRS but not the TIMS export.

    Blank where the agency reported fewer than 10 injury crashes that year.
    """
    total = yearly(crashes)
    only = yearly(crashes[crashes.source.eq("ccrs")], all_years(crashes))
    only = only.reindex(total.index, fill_value=0)
    return (only / total.where(total.ge(10))).round(3)


def report_format(crashes: pd.DataFrame) -> pd.Series:
    """Each report's format, read from the style of its TIMS case number (see above)."""
    case = crashes.CASE_ID.astype("string").fillna("").str.strip()
    out = pd.Series(UNRECOGNISED, index=crashes.index)
    # Made-up records from ``bike_safety_ca.demo`` carry a "SYN-" prefix.
    out[case.str.fullmatch(r"(?:SYN-)?(?:\d{7}|9\d{7})")] = EARLIER
    out[case.str.fullmatch(r"(?:SYN-)?8\d{7}")] = CCRS_FORMAT
    out[crashes.source.eq("ccrs")] = CCRS_ALONE
    return out


def by_format(crashes: pd.DataFrame) -> pd.DataFrame:
    """Injury crash reports per agency and quarter in each format.

    Starts two years before the first CCRS-format report.  Empty when the
    tables hold no TIMS export, since the format cannot then be told.
    """
    kind = report_format(crashes)
    if not crashes.source.eq("tims").any() or not kind.eq(CCRS_FORMAT).any():
        return pd.DataFrame(columns=list(FORMAT_COLOURS))
    quarter = pd.to_datetime(crashes.collision_date).dt.to_period("Q")
    start = quarter[kind.eq(CCRS_FORMAT)].min() - 8
    keep = quarter.ge(start)
    table = pd.crosstab([crashes.reporting_agency[keep], quarter[keep]], kind[keep])
    agencies = list(table.index.get_level_values(0).unique())
    quarters = list(pd.period_range(start, quarter.max(), freq="Q"))
    full = pd.MultiIndex.from_tuples(
        [(a, q) for a in agencies for q in quarters], names=["reporting_agency", "quarter"]
    )
    return table.reindex(index=full, columns=list(FORMAT_COLOURS), fill_value=0)


def by_severity(crashes: pd.DataFrame) -> pd.DataFrame:
    """Injury crashes per agency and year at each severity.

    A crash with no usable severity is counted as "Not recorded", so each
    row adds up to the agency's injury crashes that year.
    """
    severity = crashes.COLLISION_SEVERITY.astype("string").str.strip().map(SEVERITIES)
    severity = severity.fillna(NO_SEVERITY)
    known = crashes.year.notna()
    table = pd.crosstab([crashes.reporting_agency[known], crashes.year[known]], severity[known])
    agencies = list(table.index.get_level_values(0).unique())
    full = pd.MultiIndex.from_tuples(
        [(a, y) for a in agencies for y in all_years(crashes)], names=["reporting_agency", "year"]
    )
    table = table.reindex(index=full, columns=list(SEVERITY_COLOURS), fill_value=0)
    return table if table[NO_SEVERITY].any() else table.drop(columns=NO_SEVERITY)


def minor_injury_change(
    crashes: pd.DataFrame,
    before: tuple[int, int] = MINOR_BEFORE,
    after: tuple[int, int] = MINOR_AFTER,
) -> dict[str, Any]:
    """Has the recording of minor-injury crashes changed between two periods?

    ``crashes`` is an area's injury crashes (``year``, ``COLLISION_SEVERITY``),
    every agency together.  ``ratio`` is the minor-injury crashes per year
    (visible injury and complaint of pain) in ``after`` over the same in
    ``before``, both ends of a period included.  ``verdict`` is ``CHANGED``
    when the ratio is under ``MINOR_FALL`` or over ``MINOR_RISE``, and
    ``STEADY`` otherwise.  It is ``NOT_ASSESSABLE``, with a ``reason``, when
    a year of either period has no injury crash at all, when more than
    ``MINOR_UNGRADED`` of a period's injury crashes have no severity, or when
    the earlier period has no minor-injury crash: none of those is a
    measured zero.

    A flag is a change in the count, whatever its cause: fewer crashes,
    fewer reports and a change of grading all look the same here.  A total
    can also hide one agency's change behind another's.
    """
    severity = crashes.COLLISION_SEVERITY.astype("string").str.strip()
    graded, minor = severity.isin(list(SEVERITIES)), severity.isin(list(MINOR))
    found: dict[str, Any] = {"ratio": float("nan"), "verdict": NOT_ASSESSABLE, "reason": ""}
    reasons = []
    for name, (first, last) in (("before", before), ("after", after)):
        within = crashes.year.between(first, last)
        years = last - first + 1
        found[f"minor per year {name}"] = int((minor & within).sum()) / years
        found[f"ungraded share {name}"] = (
            float((~graded & within).sum() / within.sum()) if within.any() else float("nan")
        )
        empty = sorted(set(range(first, last + 1)) - set(crashes.year[within].astype(int)))
        if empty:
            reasons.append(f"no injury crash in {', '.join(map(str, empty))}")
        elif found[f"ungraded share {name}"] > MINOR_UNGRADED:
            reasons.append(f"severity not recorded for many crashes in {first}-{last}")
    if not reasons and not found["minor per year before"] > 0:
        reasons.append(f"no minor-injury crash in {before[0]}-{before[1]}")
    if reasons:
        return found | {"reason": "; ".join(reasons)}
    ratio = found["minor per year after"] / found["minor per year before"]
    changed = ratio < MINOR_FALL or ratio > MINOR_RISE
    return found | {"ratio": ratio, "verdict": CHANGED if changed else STEADY}


def level_step(
    counts: pd.Series,
    ratio: float = STEP_RATIO,
    min_years: int = STEP_YEARS,
    min_level: float = STEP_LEVEL,
) -> tuple[int, float, float] | None:
    """A lasting change of level in yearly counts: (first year of the new level, before, after).

    The years are split in two at every point that leaves ``min_years`` on
    each side.  A split counts when the smaller side's median is under
    ``ratio`` times the larger's, the larger is at least ``min_level``, and at
    most one year lies on the wrong side of the midpoint between the two
    levels (their geometric mean, or half the larger where the smaller is
    zero), and that year is not one of the two at the split.  Of the splits that count, the one with the fewest years out of
    place wins, then the largest change.  None when no split counts.

    One step at most is reported, and a gap that opens and closes again may
    show as one of its two steps or as none: the year-by-year flags are for
    that.
    """
    best: tuple[int, float, int, float, float] | None = None
    for i in range(min_years, len(counts) - min_years + 1):
        early, late = counts.iloc[:i], counts.iloc[i:]
        before, after = float(early.median()), float(late.median())
        low, high = min(before, after), max(before, after)
        if high < min_level or low >= ratio * high:
            continue
        middle = math.sqrt(low * high) if low else high / 2
        fell = after < before
        # A year exactly at the midpoint is on neither side, so never out of place.
        wrong_early = early.lt(middle) if fell else early.gt(middle)
        wrong_late = late.gt(middle) if fell else late.lt(middle)
        misplaced = int(wrong_early.sum() + wrong_late.sum())
        # A year out of place right at the split means the split belongs elsewhere.
        if misplaced > 1 or wrong_early.iloc[-1] or wrong_late.iloc[0]:
            continue
        size = math.log((high + 1) / (low + 1))
        if best is None or (misplaced, -size) < (best[0], -best[1]):
            best = (misplaced, size, int(counts.index[i]), before, after)
    return None if best is None else best[2:]


def level_steps(crashes: pd.DataFrame) -> pd.DataFrame:
    """Lasting changes of level per agency: in all injury crashes and at each severity.

    One row per agency and measure that has a step (see ``level_step``), over
    the finished years.  For a step at one severity, ``other_before`` and
    ``other_after`` are the agency's typical yearly crashes at every other
    severity on each side of it, and ``moved`` is the share of the change
    that they took up in the opposite direction.  ``kind`` reads that share:
    "regraded" from a half to twice the change (the crashes are still
    reported, at another severity) where this severity is a fifth or more of
    the agency's injury crashes, otherwise "fewer reports" or "more
    reports": under a half the others did not take it up, and over twice they
    changed by far more than this severity did, for some other reason.  A step in all
    injury crashes is always one of the last two.
    """
    columns = [
        "reporting_agency", "measure", "from_year", "before", "after", "ratio",
        "other_before", "other_after", "moved", "kind",
    ]  # fmt: skip
    years = all_years(crashes)
    if years and last_year_ends(crashes) is not None:
        years = years[:-1]
    severity = crashes.COLLISION_SEVERITY.astype("string").str.strip().map(SEVERITIES)
    rows = []
    if not years:
        return pd.DataFrame(columns=columns)
    for agency, mine in crashes.groupby("reporting_agency"):
        total = mine.year.value_counts().reindex(years, fill_value=0)
        band = severity.loc[mine.index]
        bands = {
            name: mine.year[band.eq(name)].value_counts().reindex(years, fill_value=0)
            for name in SEVERITIES.values()
        }
        for measure, counts in {ALL_INJURY: total, **bands}.items():
            step = level_step(counts)
            if step is None:
                continue
            year, before, after = step
            row: dict[str, object] = {
                "reporting_agency": agency,
                "measure": measure,
                "from_year": year,
                "before": before,
                "after": after,
                "ratio": round(after / before, 3) if before else float("nan"),
                "kind": FEWER if after < before else MORE,
            }
            if measure != ALL_INJURY:
                other = total - counts
                was = float(other[other.index < year].median())
                now = float(other[other.index >= year].median())
                moved = (now - was) / (before - after)
                row |= {"other_before": was, "other_after": now, "moved": round(moved, 2)}
                high, beside = (before, was) if before > after else (after, now)
                sizeable = high >= REGRADED_BAND * (high + beside)
                if sizeable and REGRADED_SHARE <= moved <= 1 / REGRADED_SHARE:
                    row["kind"] = REGRADED
            rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def last_year_ends(crashes: pd.DataFrame) -> str | None:
    """The last crash date, if the final year is unfinished by the flagging rule's measure."""
    last = pd.to_datetime(crashes.collision_date).max()
    return None if last.day_of_year / 365 >= FULL_YEAR else f"{last.year} runs to {last:%-d %b}"


def diagnose(crashes: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Every table: counts and flags per measure, and the CCRS-only share."""
    subsets = {
        "injury_crashes": crashes,
        "cyclist_injury_crashes": crashes[crashes.bike_involved.astype(bool)],
    }
    found: dict[str, pd.DataFrame] = {}
    everything = yearly(crashes)
    for name, (_, min_baseline) in MEASURES.items():
        found[name] = yearly(subsets[name], all_years(crashes)).reindex(
            everything.index, fill_value=0
        )
        years = all_years(crashes)
        span = (years[0], years[-1]) if years else None
        ends = (
            pd.to_datetime(crashes.collision_date, errors="coerce").max() if len(crashes) else None
        )
        found[f"{name}_flags"] = flags(subsets[name], min_baseline, span, ends)
    found[CCRS_ONLY] = ccrs_only_share(crashes)
    found[FORMAT] = by_format(crashes)
    found[SEVERITY] = by_severity(crashes)
    found[STEPS] = level_steps(crashes)
    return found


def busiest(table: pd.DataFrame, least: float = 10.0) -> pd.Index:
    """Agencies with at least ``least`` crashes in a typical year, largest first."""
    typical = table.median(axis=1)
    return typical[typical.ge(least)].sort_values(ascending=False).index


def _spans(years: pd.Series) -> str:
    """Years as text, runs joined: 2022, 2023, 2024, 2026 -> "2022–2024, 2026"."""
    runs: list[list[int]] = []
    for year in sorted(int(y) for y in years):
        if runs and year == runs[-1][-1] + 1:
            runs[-1].append(year)
        else:
            runs.append([year])
    return ", ".join(str(r[0]) if len(r) == 1 else f"{r[0]}–{r[-1]}" for r in runs)


def _kinds(marked: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    """The flagged rows of one agency by kind of change, the certain kinds first."""
    kinds = [FALL, RISE, POSSIBLE_FALL, POSSIBLE_RISE]
    return [
        (kind, marked[marked.change.eq(kind)]) for kind in kinds if marked.change.eq(kind).any()
    ]


def ring(axis: Any, marked: pd.DataFrame) -> None:
    """Ring the flagged years: a solid ring for a fall or rise, a dotted one for a possible one."""
    for sure, style in ((True, "solid"), (False, "dotted")):
        some = marked[marked.change.isin([FALL, RISE]) == sure]
        if len(some):
            axis.scatter(
                some.year, some.crashes, s=120, facecolors="none", edgecolors=FLAG,
                linewidths=1.8, linestyles=style, clip_on=False, zorder=3,
            )  # fmt: skip


def _charted(order: pd.Index, present: pd.Index, panels: int) -> list[Any]:
    """The agencies to draw: the busy ones in ``order``, or every agency if none is busy."""
    agencies = [a for a in order if a in present] or list(present)
    return agencies[:panels]


def _nothing_to_chart(title: str, out: Path) -> Path:
    """A picture that says there is nothing to draw, so every run writes the same files."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure = plt.figure(figsize=(8, 2))
    figure.suptitle(title, fontsize=13, color=INK, x=0.02, ha="left", fontweight="bold")
    figure.text(0.02, 0.35, "No crashes of this kind in the tables.", fontsize=10, color=MUTED)
    out.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(out, dpi=150, facecolor="white")
    plt.close(figure)
    return out


def plot(
    table: pd.DataFrame,
    flagged: pd.DataFrame,
    names: pd.Series,
    title: str,
    out: Path,
    note: str | None = None,
    share: bool = False,
    order: pd.Index | None = None,
    panels: int = 12,
) -> Path:
    """One small chart per agency, largest first; flagged years ringed and listed.

    Agencies with fewer than ten crashes in a typical year are left out of the
    picture (they are in the CSV).
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if order is None:
        order = busiest(table)
    agencies = _charted(order, table.index, panels)
    if not agencies:
        return _nothing_to_chart(title, out)
    columns = min(3, len(agencies))
    rows = math.ceil(len(agencies) / columns)
    figure, axes = plt.subplots(
        rows, columns, figsize=(4.2 * columns, 2.6 * rows + 0.9), squeeze=False, sharex=True
    )
    years = list(table.columns)
    for axis, agency in zip(axes.flat, agencies, strict=False):
        series = table.loc[agency]
        axis.plot(years, series, color=LINE, linewidth=2, marker="o", markersize=3.5)
        top = 1.0 if share else max(float(series.max()), 1.0) * 1.25
        axis.set_ylim(0, top)
        marked = flagged[flagged.reporting_agency.eq(agency)]
        if len(marked):
            ring(axis, marked)
            lines = [f"{kind.capitalize()}: {_spans(rows.year)}" for kind, rows in _kinds(marked)]
            axis.text(
                0.98, 0.95,
                "\n".join([*lines, f"typical year {marked.baseline.iloc[0]:.0f}"]),
                transform=axis.transAxes, ha="right", va="top", fontsize=8, color=INK,
            )  # fmt: skip
        axis.set_title(names.get(agency, agency), fontsize=10, color=INK, loc="left")
        axis.grid(axis="y", color=GRID, linewidth=0.8)
        axis.set_axisbelow(True)
        axis.tick_params(colors=MUTED, labelsize=8, length=0)
        for side in ("top", "right", "left"):
            axis.spines[side].set_visible(False)
        axis.spines["bottom"].set_color(GRID)
        axis.set_xticks(years[::2])
        if share:
            axis.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    for axis in list(axes.flat)[len(agencies) :]:
        axis.set_visible(False)
    figure.suptitle(title, fontsize=13, color=INK, x=0.01, ha="left", fontweight="bold")
    if share:
        footer = (
            "A rise in the last years is expected where the TIMS export stops earlier than CCRS;"
            " a rise in one agency alone is worth asking about."
        )
    else:
        footer = (
            "Each chart has its own scale, from zero. Ringed years are far below or above the"
            " agency's typical year and not explained by the other agencies' change; a dotted"
            " ring is a smaller move, worth a look."
        )
        if len(table) == 1:
            footer = (
                "Ringed years are far below or above this agency's typical year; a dotted ring"
                " is a smaller move, worth a look. With one agency there is nothing to compare"
                " against, so a real change in crashes looks the same, and no ring does not"
                " show that reporting was steady."
            )
    if note:
        footer += f" {note}."
    figure.text(0.01, 0.005, footer, fontsize=8, color=MUTED, ha="left", va="bottom", wrap=True)
    figure.tight_layout(rect=(0, 0.035, 1, 0.97))
    out.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(out, dpi=150, facecolor="white")
    plt.close(figure)
    return out


def plot_stacked(
    table: pd.DataFrame,
    colours: dict[str, str],
    names: pd.Series,
    title: str,
    out: Path,
    footer: str,
    order: pd.Index,
    panels: int = 12,
) -> Path:
    """One small stacked-bar chart per agency; ``table`` is indexed by agency and period."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    colours = {label: c for label, c in colours.items() if label in table.columns}
    agencies = _charted(order, table.index.get_level_values(0).unique(), panels)
    if not agencies:
        return _nothing_to_chart(title, out)
    columns = min(3, len(agencies))
    rows = math.ceil(len(agencies) / columns)
    figure, axes = plt.subplots(
        rows, columns, figsize=(4.4 * columns, 2.5 * rows + 1.3), squeeze=False, sharex=True
    )
    periods = table.index.get_level_values(1).unique()
    quarterly = isinstance(periods[0], pd.Period)
    spots = range(len(periods))
    for axis, agency in zip(axes.flat, agencies, strict=False):
        part = table.loc[agency]
        base = pd.Series(0.0, index=part.index)
        for label, colour in colours.items():
            axis.bar(
                spots, part[label], bottom=base, color=colour, width=0.82,
                edgecolor="white", linewidth=0.6,
            )  # fmt: skip
            base = base + part[label]
        axis.set_ylim(0, max(float(base.max()), 1.0) * 1.12)
        axis.set_title(names.get(agency, agency), fontsize=10, color=INK, loc="left")
        axis.grid(axis="y", color=GRID, linewidth=0.8)
        axis.set_axisbelow(True)
        axis.tick_params(colors=MUTED, labelsize=8, length=0)
        for side in ("top", "right", "left"):
            axis.spines[side].set_visible(False)
        axis.spines["bottom"].set_color(GRID)
        if quarterly:
            starts = [i for i, p in enumerate(periods) if p.quarter == 1]
            axis.set_xticks(starts, [str(periods[i].year) for i in starts])
        else:
            axis.set_xticks(list(spots)[::2], [str(p) for p in periods[::2]])
    for axis in list(axes.flat)[len(agencies) :]:
        axis.set_visible(False)
    figure.suptitle(title, fontsize=13, color=INK, x=0.01, ha="left", fontweight="bold")
    figure.legend(
        handles=[Patch(facecolor=c, label=label) for label, c in colours.items()],
        loc="upper left", bbox_to_anchor=(0.005, 0.955), ncols=len(colours), frameon=False,
        fontsize=9, labelcolor=INK,
    )  # fmt: skip
    figure.text(0.01, 0.005, footer, fontsize=8, color=MUTED, ha="left", va="bottom", wrap=True)
    figure.tight_layout(rect=(0, 0.035, 1, 0.92))
    out.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(out, dpi=150, facecolor="white")
    plt.close(figure)
    return out


SYNTHETIC = " · SYNTHETIC DATA, not real crashes"


def write(crashes: pd.DataFrame, out: Path, synthetic: bool = False) -> list[Path]:
    """Write every table and picture to ``out``; ``synthetic`` labels each picture."""
    out.mkdir(parents=True, exist_ok=True)
    found = diagnose(crashes)
    names = agency_names(crashes)
    note = last_year_ends(crashes)
    mark = SYNTHETIC if synthetic else ""
    order = busiest(found["injury_crashes"])
    written = []
    for name, table in found.items():
        path = out / f"{name}.csv"
        flat = name.endswith("_flags") or name == STEPS  # one row per finding, no index
        table.rename(index=names.to_dict()).to_csv(path, index=not flat)
        written.append(path)
    partial = f" {note}." if note else ""
    if len(found[FORMAT]):
        written.append(
            plot_stacked(
                found[FORMAT],
                FORMAT_COLOURS,
                names,
                "Injury crash reports per quarter, by report format" + mark,
                out / f"{FORMAT}.png",
                "Each chart has its own scale. Format is read from the style of the case number."
                " Look for volume that does not carry over when an agency changes format."
                " The latest quarters are still filling in." + partial,
                order,
            )  # fmt: skip
        )
    written.append(
        plot_stacked(
            found[SEVERITY],
            SEVERITY_COLOURS,
            names,
            "Injury crashes per year, by severity" + mark,
            out / f"{SEVERITY}.png",
            "Each chart has its own scale. A shift between severities with a steady total"
            " points to a change in how injuries are graded." + partial,
            order,
        )  # fmt: skip
    )
    for name, (title, _) in MEASURES.items():
        written.append(
            plot(
                found[name],
                found[f"{name}_flags"],
                names,
                title + mark,
                out / f"{name}.png",
                note,
                order=order,
            )  # fmt: skip
        )
    none = found["injury_crashes_flags"].iloc[0:0]
    written.append(
        plot(
            found[CCRS_ONLY],
            none,
            names,
            "Share of injury crashes found only in CCRS, not in the TIMS export" + mark,
            out / f"{CCRS_ONLY}.png",
            note,
            share=True,
            order=order,
        )  # fmt: skip
    )
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--crashes", type=Path, default=Path("data/processed/crashes"))
    parser.add_argument("--out", type=Path, default=Path("output/reporting"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = settings.load(args.config)
    crashes = load(args.crashes, config.crs, config.first_year)
    names = agency_names(crashes)
    for name, (title, _) in MEASURES.items():
        found = diagnose(crashes)[f"{name}_flags"]
        found = found.assign(reporting_agency=found.reporting_agency.map(names))
        print(f"\n{title}: flagged agency-years")
        print(found.to_string(index=False) if len(found) else "none")
    steps = level_steps(crashes)
    steps = steps.assign(reporting_agency=steps.reporting_agency.map(names))
    print("\nLasting changes of level, in all injury crashes and by severity")
    print(steps.to_string(index=False) if len(steps) else "none")
    change = minor_injury_change(crashes)
    print(
        f"\nMinor-injury crashes per year, {MINOR_AFTER[0]}-{MINOR_AFTER[1]} over "
        f"{MINOR_BEFORE[0]}-{MINOR_BEFORE[1]}: {change['ratio']:.2f}, {change['verdict']}"
        + (f" ({change['reason']})" if change["reason"] else "")
    )
    for path in write(crashes, args.out, config.synthetic):
        logging.info("wrote %s", path)


if __name__ == "__main__":
    main()
