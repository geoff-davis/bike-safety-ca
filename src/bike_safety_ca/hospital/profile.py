"""A statewide profile of bicycle injuries treated in hospital, from tables already saved.

``python -m bike_safety_ca.hospital.profile --tables <folder> --residents <folder>
--out <folder>`` writes it as Markdown and, with ``--pdf``, as a PDF.  It covers
all California residents in 2023–2024, the first full years in which hospital
records could name an electric bicycle, and splits the injuries three ways:

- age and sex, as visits per resident, from unique visits by age group and sex;
- electric or ordinary bicycle, from the injury cause;
- whether a motor vehicle was involved, from EpiCenter's "MVT-Pedal Cyclist"
  mechanism (a collision with a motor vehicle in traffic).  Each cause belongs
  to one mechanism, so the two splits can be crossed.

It adds trends over 2016–2024: rates by year for four broad age groups, and the
motor-vehicle share by year (the e-bike share from 2023, its first full year).

Splits by cause or mechanism count a visit once under each cause it is coded
with (EpiCenter's FAQ), so they are shares of coded injuries, a little above
the visits.  Hidden cells hold 1 to 10, and every figure built on one is a
range; a group joining hidden and published cells is printed as a range too,
since its published part is in the source's own table.  No hidden count is
worked out from others.  The charts add a 95% interval for chance to each
range (Wilson for shares, exact Poisson for rates).

Source of the counts: California Department of Public Health, EpiCenter –
California Injury Data Online.  Residents: U.S. Census Bureau, Population
Estimates Program.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd
from scipy import stats

from bike_safety_ca import links
from bike_safety_ca.hospital import epicenter, population, rates
from bike_safety_ca.hospital import tables as er
from bike_safety_ca.hospital.ebike import EBIKE
from bike_safety_ca.hospital.report import (
    AGE,
    CAUSE,
    CREDIT,
    HIDDEN_COUNTS,
    SHARING,
    STATE_YEARS,
    _ages,
)

SEX = "Sex"
MECH = "Injury Mechanism"
MVT = "Transportation: MVT-Pedal Cyclist"
SEXES = tuple(population.SEXES)  # "Male", "Female": the sexes the Census counts
AGES = list(population.AGE_GROUPS)
OUTCOMES = ("ed", "hosp")
TABLES = tuple(
    f"{outcome}_state_{name}"
    for name in (
        "total_age_groups",
        "total_age_sex",
        "bike_mech_age_sex",
        "bike_cause_mech_age",
        "bike_cause_mech_sex",
    )
    for outcome in OUTCOMES
)
# Read when saved: the report leaves the trends out until they are pulled.
TREND_TABLES = tuple(
    f"{outcome}_state_trend_{name}"
    for name in ("total_year_age", "bike_cause_mech_year")
    for outcome in OUTCOMES
)
ALL = "All ages"
Z = float(stats.norm.ppf(0.975))
TREND_YEARS = epicenter.YEARS
EBIKE_CODES = 2023  # the first full year in which a record could name an e-bike
# The trend's broad age groups, from the report's age groups.
BROAD = {
    "0-4": "Under 15",
    "5-9": "Under 15",
    "10-14": "Under 15",
    "15-19": "15–24",
    "20-24": "15–24",
    "25-44": "25–64",
    "45-64": "25–64",
    "65-84": "65 and over",
    "85+": "65 and over",
}
# The groups the e-bike key points compare, by count and per resident.
TEENS, TEENS_LABEL = ["10-14", "15-19"], "10–19"
ADULTS, ADULTS_LABEL = ["25-44", "45-64"], "25–64"
CHART_NOTE = (
    "Bars: the figure, with a paler end where hidden counts leave a range. Thin lines: a 95% "
    "interval for chance, treating 2023–2024 as one draw of the underlying risk."
)
TABLE_NOTE = "The ranges in the table cover hidden counts only, not chance."


def cells(folder: Path, name: str) -> pd.DataFrame:
    """One saved table as bounds per cell, with plain columns for age, sex, e-bike and vehicle."""
    saved = er.table(folder, name).drop(columns="kind", errors="ignore")
    keys = [c for c in saved.columns if c != "Count"]
    every = (
        pd.Index(saved[keys[0]], name=keys[0])
        if len(keys) == 1
        else pd.MultiIndex.from_frame(saved[keys])
    )
    found = rates.cells(saved, keys, every).reset_index()
    if AGE in keys:
        found["age"] = found[AGE].map(population.age_group)
    if SEX in keys:
        found["sex"] = found[SEX]
    if CAUSE in keys:
        found["ebike"] = found[CAUSE].str.contains(EBIKE, case=False, regex=False)
    if MECH in keys:
        found["vehicle"] = found[MECH].eq(MVT)
    if "Year" in keys:
        found["year"] = found["Year"].astype(int)
    return found


def summed(found: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Lowest and highest total, and the number of hidden cells in it, for each group."""
    grouped = found.groupby(by) if by else found.groupby(lambda _: "all")
    total = grouped[["low", "high"]].sum()
    total["hidden"] = grouped.hidden.sum()
    total["cells"] = grouped.size()
    return total


def _span(low: float, high: float, scale: float = 1, places: int = 0, unit: str = "") -> str:
    """A range rounded outwards, so the print never claims more than is known."""
    if math.isnan(low) or math.isnan(high):
        return "none"
    if low == high:  # nothing hidden: an exact figure, rounded as usual
        return f"{low * scale:,.{places}f}{unit}"
    step = 10**places
    one = math.floor(low * scale * step) / step
    two = math.ceil(high * scale * step) / step
    a, b = f"{one:,.{places}f}", f"{two:,.{places}f}"
    return f"{a}{unit}" if a == b else f"{a} to {b}{unit}"


def _wilson(k: float, n: float) -> tuple[float, float]:
    """The 95% Wilson score interval for ``k`` cases in ``n``."""
    if n <= 0:
        return math.nan, math.nan
    p, c = k / n, Z * Z / n
    centre = (p + c / 2) / (1 + c)
    half = Z * math.sqrt(p * (1 - p) / n + c / (4 * n)) / (1 + c)
    return max(centre - half, 0.0), min(centre + half, 1.0)


def _poisson(low: float, high: float) -> tuple[float, float]:
    """The exact 95% Poisson interval, from the lowest and the highest count."""
    lower = float(stats.chi2.ppf(0.025, 2 * low) / 2) if low > 0 else 0.0
    return lower, float(stats.chi2.ppf(0.975, 2 * high + 2) / 2)


def share_of(part: pd.Series, rest: pd.Series) -> pd.Series:
    """``part`` as a share of ``part`` and ``rest`` together: its range and chance interval.

    The lowest share pairs the fewest cases in the group with the most outside
    it, and its interval's lower end is taken there; the highest the reverse.
    """
    least, most = part["low"] + rest["high"], part["high"] + rest["low"]
    return pd.Series(
        {
            "low": part["low"] / least if least else math.nan,
            "high": part["high"] / most if most else math.nan,
            "ci_low": _wilson(part["low"], least)[0],
            "ci_high": _wilson(part["high"], most)[1],
        }
    )


def rate_of(part: pd.Series, people: float) -> pd.Series:
    """Cases per 100,000 a year (``people`` is resident-years), with a chance interval."""
    lower, upper = _poisson(part["low"], part["high"])
    scale = 1e5 / people
    return pd.Series(
        {
            "low": part["low"] * scale,
            "high": part["high"] * scale,
            "ci_low": lower * scale,
            "ci_high": upper * scale,
            "suppressed": bool(part["hidden"] and part["cells"] == 1),
        }
    )


def _percent(low: float, high: float) -> str:
    return _span(low, high, 100, unit="%")


def _per(low: float, high: float) -> str:
    return _span(low, high, places=1)


def _rate_text(figure: pd.Series) -> str:
    text = _per(figure["low"], figure["high"])
    return f"{text} (suppressed)" if figure["suppressed"] else text


def _treated(folder: Path, name: str, by: list[str]) -> pd.DataFrame:
    """ED visits plus admissions (a visit admitted at the same hospital is one admission)."""
    both = [summed(cells(folder, f"{outcome}_{name}"), by) for outcome in OUTCOMES]
    return both[0].add(both[1], fill_value=0)


def _row(table: pd.DataFrame, key: str | tuple) -> pd.Series:
    """One group's sums; a group with no row at all had no cases and nothing hidden."""
    if key in table.index:
        found = table.loc[key]
        assert isinstance(found, pd.Series)  # the keys name one group each
        return found
    return pd.Series({"low": 0, "high": 0, "hidden": 0, "cells": 0})


def _frame(figures: Mapping[Any, pd.Series]) -> pd.DataFrame:
    """Figures as rows, in the order given."""
    return pd.DataFrame(dict(figures)).T.infer_objects()


def _at(frame: pd.DataFrame, row: Any) -> pd.Series:
    found = frame.loc[row]
    assert isinstance(found, pd.Series)  # each row label is used once
    return found


def _rates(
    found: dict[str, pd.DataFrame], key: Callable[[str], Any], people: Callable[[str], float]
) -> pd.DataFrame:
    """For each age group, then all ages: ED visits, admissions and both per 100,000 a
    year, and the share of the two that were admissions."""
    rows = {}
    for age in [*AGES, ALL]:
        ed, hosp = (_row(found[o], key(age)) for o in OUTCOMES)
        both = ed[["low", "high", "hidden", "cells"]] + hosp[["low", "high", "hidden", "cells"]]
        figures = {
            "ed": rate_of(ed, people(age)),
            "hosp": rate_of(hosp, people(age)),
            "treated": rate_of(both, people(age)),
            "admitted": share_of(hosp, ed),
        }
        rows[_ages(age)] = pd.concat(figures)
    return _frame(rows)


def _split(table: pd.DataFrame, what: str) -> pd.DataFrame:
    """One figure's columns (low, high, ...) from a table made by ``_rates``."""
    part = table[what]
    assert isinstance(part, pd.DataFrame)
    return part


def _people(residents: Path) -> pd.Series:
    """Resident-years in 2023–2024, by age group."""
    everyone = population.residents(residents)
    return everyone[everyone.year.between(*STATE_YEARS)].groupby("age_group").residents.sum()


def rates_by_age(folder: Path, residents: Path) -> pd.DataFrame:
    """All riders: see ``_rates``.  Unique visits, any sex recorded or none."""
    people = _people(residents)
    found = {}
    for outcome in OUTCOMES:
        counted = cells(folder, f"{outcome}_state_total_age_groups")
        by_age = summed(counted, ["age"])
        found[outcome] = pd.concat([by_age, summed(counted, []).rename(index={"all": ALL})])
    return _rates(found, lambda age: age, lambda age: people.sum() if age == ALL else people[age])


def rates_by_age_sex(folder: Path, residents: Path) -> dict[str, pd.DataFrame]:
    """By sex (female or male): see ``_rates``."""
    everyone = population.residents(residents, by_sex=True)
    recent = everyone[everyone.year.between(*STATE_YEARS)]
    people = recent.groupby(["age_group", "sex"]).residents.sum()
    found = {}
    for outcome in OUTCOMES:
        counted = cells(folder, f"{outcome}_state_total_age_sex")
        counted = counted[counted.sex.isin(SEXES)]
        whole = summed(counted, ["sex"])
        whole.index = pd.MultiIndex.from_arrays([[ALL] * len(whole), whole.index])
        found[outcome] = pd.concat([summed(counted, ["age", "sex"]), whole])
    result = {}
    for sex in ("Female", "Male"):
        mine = people.xs(sex, level="sex")

        def key(age: str, sex: str = sex) -> tuple[str, str]:
            return (age, sex)

        def size(age: str, mine: pd.Series = mine) -> float:
            return float(mine.sum() if age == ALL else mine[age])

        result[sex] = _rates(found, key, size)
    return result


def unknown_sex(folder: Path) -> str:
    """How many visits and admissions have no sex recorded as male or female."""
    parts = []
    for outcome, what in (("ed", "emergency department visits"), ("hosp", "admissions")):
        found = cells(folder, f"{outcome}_state_total_age_sex")
        part = _row(summed(found[~found.sex.isin(SEXES)], []), "all")
        parts.append(f"{_span(part['low'], part['high'])} {what}")
    return " and ".join(parts)


def vehicle_by_age(folder: Path) -> pd.DataFrame:
    """Share of coded injuries treated that involved a motor vehicle: rows by age, any sex."""
    treated = _treated(folder, "state_bike_mech_age_sex", ["age", "vehicle"])
    return _frame(
        {
            _ages(age): share_of(_row(treated, (age, True)), _row(treated, (age, False)))
            for age in AGES
        }
    )


def ebike_figures(folder: Path, by: str) -> dict[str, pd.DataFrame]:
    """By age or sex: e-bike share ("share"), and motor-vehicle share for "ebike" and "other"."""
    name = "state_bike_cause_mech_age" if by == "age" else "state_bike_cause_mech_sex"
    treated = _treated(folder, name, [by, "ebike", "vehicle"])
    kinds = _treated(folder, name, [by, "ebike"])
    groups = AGES if by == "age" else ["Female", "Male"]
    labels = {g: _ages(g) if by == "age" else g for g in groups}
    found = {
        "share": _frame(
            {labels[g]: share_of(_row(kinds, (g, True)), _row(kinds, (g, False))) for g in groups}
        )
    }
    for key, ebike in (("ebike", True), ("other", False)):
        found[key] = _frame(
            {
                labels[g]: share_of(
                    _row(treated, (g, ebike, True)), _row(treated, (g, ebike, False))
                )
                for g in groups
            }
        )
    return found


def admitted(folder: Path) -> dict[tuple[bool, bool], pd.DataFrame]:
    """Share of coded injuries treated that were admissions, by (e-bike, motor vehicle).

    Rows by age group, then all ages.
    """
    found = {o: cells(folder, f"{o}_state_bike_cause_mech_age") for o in OUTCOMES}
    by_age = {o: summed(f, ["age", "ebike", "vehicle"]) for o, f in found.items()}
    overall = {o: summed(f, ["ebike", "vehicle"]) for o, f in found.items()}
    result = {}
    for ebike in (True, False):
        for vehicle in (True, False):
            figures = {
                _ages(age): share_of(
                    _row(by_age["hosp"], (age, ebike, vehicle)),
                    _row(by_age["ed"], (age, ebike, vehicle)),
                )
                for age in AGES
            }
            figures[ALL] = share_of(
                _row(overall["hosp"], (ebike, vehicle)), _row(overall["ed"], (ebike, vehicle))
            )
            result[ebike, vehicle] = _frame(figures)
    return result


def _sum(rows: list[pd.Series]) -> pd.Series:
    return sum(rows[1:], rows[0][["low", "high", "hidden", "cells"]])


def ebike_reach(folder: Path, residents: Path) -> dict[str, pd.Series]:
    """For ages 10–19 ("teens") and 25–64 ("adults"): e-bike injuries treated per 100,000 a
    year ("<group>_rate") and the group's share of all e-bike injuries treated
    ("<group>_share")."""
    kinds = _treated(folder, "state_bike_cause_mech_age", ["age", "ebike"])
    people = _people(residents)
    found = {}
    for name, ages in (("teens", TEENS), ("adults", ADULTS)):
        mine = _sum([_row(kinds, (age, True)) for age in ages])
        rest = _sum([_row(kinds, (age, True)) for age in AGES if age not in ages])
        found[f"{name}_rate"] = rate_of(mine, float(people[ages].sum()))
        found[f"{name}_share"] = share_of(mine, rest)
    return found


def ebike_rates(folder: Path, residents: Path) -> pd.DataFrame:
    """E-bike injuries treated per 100,000 a year, rows by age."""
    kinds = _treated(folder, "state_bike_cause_mech_age", ["age", "ebike"])
    people = _people(residents)
    return _frame({_ages(age): rate_of(_row(kinds, (age, True)), people[age]) for age in AGES})


def admission_ratio(folder: Path) -> tuple[float, float]:
    """E-bike admissions over those expected at ordinary-bike shares for the same ages: the
    lowest and highest the hidden counts allow, rounded outwards to two places.

    As ``ebike.admission_ratio``, from the cause-by-mechanism table this profile reads
    (coded injuries, not visits): expected admissions are, in each age group, e-bike
    injuries treated times the share of ordinary-bike injuries admitted.
    """
    found = {
        o: summed(cells(folder, f"{o}_state_bike_cause_mech_age"), ["age", "ebike"])
        for o in OUTCOMES
    }

    def side(admitted: str, visits: str) -> tuple[list[float], list[float], list[float]]:
        """E-bike admissions, e-bike injuries treated and the ordinary share, by age."""
        # The lowest ratio pairs the fewest e-bike admissions with the most e-bike visits and
        # the highest ordinary share; the highest ratio the reverse.
        other = ("high", "low") if admitted == "low" else ("low", "high")
        hosp, treated, share = [], [], []
        for age in AGES:
            e_ed, e_hosp = (_row(found[o], (age, True)) for o in OUTCOMES)
            o_ed, o_hosp = (_row(found[o], (age, False)) for o in OUTCOMES)
            hosp.append(float(e_hosp[admitted]))
            treated.append(float(e_hosp[admitted] + e_ed[visits]))
            ordinary = float(o_hosp[other[0]] + o_ed[other[1]])
            if treated[-1] and not ordinary:
                raise ValueError("an age group with e-bike injuries and no other bicycles")
            share.append(float(o_hosp[other[0]]) / ordinary if ordinary else 0.0)
        return hosp, treated, share

    ends = []
    for admitted, visits in (("low", "high"), ("high", "low")):
        hosp, treated, share = side(admitted, visits)
        ratio = sum(hosp) / sum(t * s for t, s in zip(treated, share, strict=True))
        # More e-bike admissions raise the count and the expected count; the pairing gives
        # true bounds only while the first wins, which is while each share times it is under 1.
        if max(share) * ratio >= 1:
            raise ValueError("the e-bike admission ratio's range is not a bound here")
        ends.append(ratio)
    # Rounded to nine places first, so float noise is not taken outwards as a real excess.
    return math.floor(round(ends[0] * 100, 9)) / 100, math.ceil(round(ends[1] * 100, 9)) / 100


def _middle(frame: pd.DataFrame) -> pd.Series:
    """The middle of each row's range, for picking the highest and lowest group."""
    return (frame["low"] + frame["high"]) / 2


def _times(low: float, high: float) -> str:
    return _span(low, high, places=1)


def key_points(
    everyone: pd.DataFrame,
    rates: dict[str, pd.DataFrame],
    vehicle: pd.DataFrame,
    ebikes: dict[str, pd.DataFrame],
    reach: dict[str, pd.Series],
    by_age_rates: pd.DataFrame,
    ratio: tuple[float, float],
) -> dict[str, list[str]]:
    """One or two things to take from each chart, worked out from its figures."""
    treated, share = _split(everyone, "treated"), _split(everyone, "admitted")
    ages = [a for a in treated.index if a != ALL]
    top = str(_middle(treated.loc[ages]).idxmax())
    least, most = (str(f(_middle(share.loc[ages]))) for f in (pd.Series.idxmin, pd.Series.idxmax))
    female, male = (_at(_split(rates[s], "treated"), ALL) for s in ("Female", "Male"))
    by_sex = (male["low"] / female["high"], male["high"] / female["low"])
    near, far = (str(f(_middle(vehicle))) for f in (pd.Series.idxmax, pd.Series.idxmin))
    used, struck = (str(_middle(f).idxmax()) for f in (ebikes["share"], by_age_rates))
    teens, adults = (reach[f"{g}_share"] for g in ("teens", "adults"))
    if adults["low"] > teens["high"]:
        count = f"By count, ages {ADULTS_LABEL} had more e-bike injuries than ages {TEENS_LABEL}"
    elif teens["low"] > adults["high"]:
        count = f"By count, ages {TEENS_LABEL} had more e-bike injuries than ages {ADULTS_LABEL}"
    else:
        count = f"By count, ages {TEENS_LABEL} and {ADULTS_LABEL} cannot be told apart"
    if ratio[0] > 1:
        serious = f"E-bike injuries were admitted more often: about {_times(*ratio)} times as often"
    elif ratio[1] < 1:
        serious = f"E-bike injuries were admitted less often: about {_times(*ratio)} times as often"
    else:
        serious = f"E-bike injuries were admitted {_times(*ratio)} times as often, so no more"
        serious += " or less often than could be told,"
    return {
        "totals": [
            f"- **Injuries treated per resident were highest at ages {top}:** "
            f"{_rate_text(_at(treated, top))} per 100,000 a year, against "
            f"{_rate_text(_at(treated, ALL))} for all ages.",
            f"- **The share admitted was lowest at ages {least} and highest at {most}:** "
            f"{_share_text(_at(share, least))} against {_share_text(_at(share, most))}.",
        ],
        "sexes": [
            f"- **Males were treated at {_times(*by_sex)} times the rate of females**, all ages "
            f"together: {_rate_text(male)} against {_rate_text(female)} per 100,000 a year.",
        ],
        "vehicle": [
            f"- **A motor vehicle was involved most often at ages {near}** "
            f"({_share_text(_at(vehicle, near))} of injuries treated) and least often at ages "
            f"{far} ({_share_text(_at(vehicle, far))}).",
        ],
        "ebike": [
            f"- **E-bikes were the largest share of injuries treated at ages {used}** "
            f"({_share_text(_at(ebikes['share'], used))}), **and e-bike injuries per resident "
            f"were highest at ages {struck}:** {_rate_text(_at(by_age_rates, struck))} per "
            f"100,000 a year, against {_rate_text(reach['adults_rate'])} at ages {ADULTS_LABEL}.",
            f"- **{count}:** ages {ADULTS_LABEL} had {_share_text(adults)} of all e-bike "
            f"injuries treated and ages {TEENS_LABEL} {_share_text(teens)}. A group's count depends on how many people are in it as well "
            "as on their risk.",
        ],
        "admitted": [
            f"- **{serious}** as ordinary-bike injuries to riders of the same ages would be. "
            "Comparing within age matters, since the share admitted rises and falls with age "
            "and e-bike riders are not spread across ages as other riders are.",
            "- Caveat: an admitted patient's record is fuller than a short emergency visit's, so "
            "an e-bike is probably more often named when the injury is serious. That would make "
            "e-bikes look more serious than they are; the data cannot say by how much.",
        ],
    }


def trend_rates(folder: Path, residents: Path) -> dict[str, dict[str, pd.DataFrame]]:
    """Visits and admissions per 100,000 a year, by year, for four broad age groups."""
    everyone = population.residents(residents)
    everyone = everyone.assign(broad=everyone.age_group.map(BROAD))
    people = everyone.groupby(["year", "broad"]).residents.sum()
    years = range(TREND_YEARS[0], TREND_YEARS[1] + 1)
    found: dict[str, dict[str, pd.DataFrame]] = {}
    for outcome in OUTCOMES:
        counted = cells(folder, f"{outcome}_state_trend_total_year_age")
        counted["broad"] = counted.age.map(BROAD)
        total = summed(counted, ["year", "broad"])
        found[outcome] = {
            group: _frame(
                {
                    year: rate_of(_row(total, (year, group)), people.loc[(year, group)])
                    for year in years
                }
            )
            for group in dict.fromkeys(BROAD.values())
        }
    return found


def trend_kinds(folder: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """By year: share of coded injuries treated with a motor vehicle involved (from the first
    year), and e-bike share (from the first full year of e-bike codes)."""
    treated = _treated(folder, "state_trend_bike_cause_mech_year", ["year", "vehicle"])
    kinds = _treated(folder, "state_trend_bike_cause_mech_year", ["year", "ebike"])
    years = range(TREND_YEARS[0], TREND_YEARS[1] + 1)
    vehicle = _frame(
        {y: share_of(_row(treated, (y, True)), _row(treated, (y, False))) for y in years}
    )
    ebike = _frame(
        {
            y: share_of(_row(kinds, (y, True)), _row(kinds, (y, False)))
            for y in years
            if y >= EBIKE_CODES
        }
    )
    return vehicle, ebike


def _lines(frames: dict, keys: list, label: Callable[[pd.Series], str]) -> list[str]:
    """Markdown table rows: one per row of the frames, a column per key."""
    first = frames[keys[0]]
    return [
        f"| {row} | " + " | ".join(label(_at(frames[k], row)) for k in keys) + " |"
        for row in first.index
    ]


def _table(columns: list[tuple[pd.DataFrame, Callable[[pd.Series], str]]]) -> list[str]:
    """Markdown table rows: one per row of the first frame, a column per (frame, writer)."""
    return [
        f"| {row} | " + " | ".join(write(_at(frame, row)) for frame, write in columns) + " |"
        for row in columns[0][0].index
    ]


def _share_text(figure: pd.Series) -> str:
    return _percent(figure["low"], figure["high"])


def charts(
    everyone: pd.DataFrame,
    rates: dict[str, pd.DataFrame],
    vehicle: pd.DataFrame,
    ebikes: dict[str, pd.DataFrame],
    serious: dict[tuple[bool, bool], pd.DataFrame],
) -> dict[str, str]:
    """The report's charts, as SVG, from the figures its tables print."""
    from bike_safety_ca.hospital import charts as draw

    one = [("all", "All riders", draw.FIRST)]
    sexes = [("Female", "Female", draw.FIRST), ("Male", "Male", draw.SECOND)]
    kinds = [("ebike", "E-bikes", draw.FIRST), ("other", "Other bicycles", draw.SECOND)]
    treated, admitted_share = "Injuries treated per 100,000 a year", "Share admitted"
    return {
        "totals": draw.ranged(
            [
                (treated, {"all": _split(everyone, "treated")}, _per, False),
                (admitted_share, {"all": _split(everyone, "admitted")}, _percent, True),
            ],
            one,
        ),
        "sexes": draw.ranged(
            [
                (treated, {s: _split(rates[s], "treated") for s in SEXES}, _per, False),
                (
                    admitted_share,
                    {s: _split(rates[s], "admitted") for s in SEXES},
                    _percent,
                    True,
                ),
            ],
            sexes,
        ),
        "vehicle": draw.ranged([("Motor vehicle involved", {"all": vehicle}, _percent, True)], one),
        "ebike": draw.ranged(
            [
                ("E-bike share of injuries treated", {"ebike": ebikes["share"]}, _percent, True),
                (
                    "Motor vehicle involved",
                    {"ebike": ebikes["ebike"], "other": ebikes["other"]},
                    _percent,
                    True,
                ),
            ],
            kinds,
        ),
        "admitted": draw.ranged(
            [
                (
                    "Admitted: motor vehicle involved",
                    {"ebike": serious[True, True], "other": serious[False, True]},
                    _percent,
                    True,
                ),
                (
                    "Admitted: no motor vehicle",
                    {"ebike": serious[True, False], "other": serious[False, False]},
                    _percent,
                    True,
                ),
            ],
            kinds,
        ),
    }


def trend_section(folder: Path, residents: Path) -> tuple[list[str], list[str], dict[str, str]]:
    """The trends' Markdown (body and appendix tables) and charts."""
    from bike_safety_ca.hospital import charts as draw

    trends = trend_rates(folder, residents)
    vehicle_years, ebike_years = trend_kinds(folder)
    keys = list(dict.fromkeys(BROAD.values()))
    colours = dict(zip(keys, (draw.FIRST, draw.SECOND, draw.THIRD, draw.FOURTH), strict=True))
    drawn = {
        "trend_rates": draw.lines(
            [("ED visits per 100,000", trends["ed"]), ("Admissions per 100,000", trends["hosp"])],
            colours,
        ),
        "trend_vehicle": draw.lines(
            [("Motor vehicle involved", {"All ages": vehicle_years})],
            {"All ages": draw.FIRST},
            percent=True,
        ),
    }
    body = [
        f"## Trends, {TREND_YEARS[0]}–{TREND_YEARS[1]}",
        "",
        "<!-- chart: trend_rates -->",
        "",
        "Visits and admissions per 100,000 residents in each year, each visit counted once. "
        f"Bands: a 95% interval for chance. {CREDIT}",
        "",
        "<!-- chart: trend_vehicle -->",
        "",
        "Share of injuries treated coded as a collision with a motor vehicle in traffic, by "
        f"year. Band: a 95% interval for chance. {CREDIT}",
        "",
        "| Year | Motor vehicle involved | E-bike share of injuries treated |",
        "|---|---:|---:|",
        *(
            f"| {year} | {_share_text(row)} | "
            + (_share_text(_at(ebike_years, year)) if year in ebike_years.index else "—")
            + " |"
            for year, row in vehicle_years.iterrows()
        ),
        "",
        "*E-bike codes start in October 2022, so their share is given from 2023. Two years are "
        "too few for a trend, and a share that grows as coders take up a new code is not "
        f"growth in injuries alone. {TABLE_NOTE}* {CREDIT}",
        "",
    ]
    tables = []
    for outcome, what in (("ed", "ED visits"), ("hosp", "Admissions")):
        tables += [
            f"### {what} per 100,000 residents, by year",
            "",
            "| Year | " + " | ".join(keys) + " |",
            "|---|" + "---:|" * len(keys),
            *_lines(trends[outcome], keys, _rate_text),
            "",
            f"*Each visit is counted once. {TABLE_NOTE}* {CREDIT}",
            "",
        ]
    return body, tables, drawn


def markdown(folder: Path, residents: Path) -> tuple[str, dict[str, str]]:
    """The report's Markdown and its charts (SVG), for ``pdf.write``.

    Each section is a chart; the figures behind the charts are tables in the appendix.
    """
    er.check_source(folder, None, STATE_YEARS, STATE_YEARS, required=TABLES)
    # The trends come from two later tables; until they are pulled the report leaves them out.
    saved = json.loads((folder / er.MANIFEST).read_text())["files"]
    has_trends = all(f"{name}.csv" in saved for name in TREND_TABLES)
    first, last = STATE_YEARS
    span = f"{first}–{last}"
    everyone = rates_by_age(folder, residents)
    rates = rates_by_age_sex(folder, residents)
    vehicle = vehicle_by_age(folder)
    by_age, by_sex = ebike_figures(folder, "age"), ebike_figures(folder, "sex")
    serious = admitted(folder)
    drawn = charts(everyone, rates, vehicle, by_age, serious)
    points = key_points(
        everyone,
        rates,
        vehicle,
        by_age,
        ebike_reach(folder, residents),
        ebike_rates(folder, residents),
        admission_ratio(folder),
    )
    trend_body: list[str] = []
    trend_tables: list[str] = []
    if has_trends:
        trend_body, trend_tables, trend_charts = trend_section(folder, residents)
        drawn |= trend_charts
    ebike_keys = ["share", "ebike", "other"]
    ebike_head = (
        "E-bike share of injuries treated | Motor vehicle involved, e-bikes | "
        "Motor vehicle involved, other bicycles |"
    )
    women, men = (_share_text(_at(by_sex["share"], s)) for s in ("Female", "Male"))
    lines = [
        f"# Bicycle injuries treated in hospital: California, {span}",
        "",
        f"**{SHARING}**",
        "",
        "**Purpose.** To help cities improve local bike safety: who is hurt badly enough to be "
        "treated in hospital, on what kind of bicycle, and how often a motor vehicle was involved.",
        "",
        "**Source.** California Department of Public Health, EpiCenter – California Injury Data "
        f"Online: unintentional injuries to pedal cyclists, all California residents, {span}"
        + (f" (trends {TREND_YEARS[0]}–{TREND_YEARS[1]}). " if has_trends else ". ")
        + "Residents: U.S. Census Bureau, Population Estimates Program. Each chart's figures "
        "are tables in the appendix.",
        "",
        "## Bicycle injuries treated in hospital, by age",
        "",
        *points["totals"],
        "",
        "<!-- chart: totals -->",
        "",
        "Unintentional bicycle injuries only. Left: emergency department visits plus hospital "
        "admissions per 100,000 residents a year, each visit counted once (a visit that ends "
        "in admission counts once, as an admission). Right: the share of those that were "
        f"admissions. {CHART_NOTE} {CREDIT}",
        "",
        "## Bicycle injuries treated in hospital, by age and sex",
        "",
        *points["sexes"],
        "",
        "<!-- chart: sexes -->",
        "",
        "As above, for women and men. Records with sex other than male or female, or not "
        f"recorded, are left out: {unknown_sex(folder)}. {CHART_NOTE} {CREDIT}",
        "",
        "## How often a motor vehicle was involved, by age",
        "",
        *points["vehicle"],
        "",
        "<!-- chart: vehicle -->",
        "",
        "Share of bicycle injuries treated (emergency department visits plus admissions) coded "
        f"as a collision with a motor vehicle in traffic. {CHART_NOTE} {CREDIT}",
        "",
        "## Electric bicycles, by age",
        "",
        *points["ebike"],
        "",
        "<!-- chart: ebike -->",
        "",
        "Left: of all bicycle injuries treated (emergency department visits plus admissions), "
        "the share whose cause names an electric bicycle. It is a floor: no code says a "
        "bicycle's kind is unknown, so a record that does not name an electric bicycle counts "
        "as an ordinary one, and the range shown comes from hidden counts only. Right: the "
        "share coded as a collision with a motor vehicle, for each kind of bicycle. By sex, "
        f"e-bikes were {women} of injuries treated among women and {men} among men. "
        f"{CHART_NOTE} {CREDIT}",
        "",
        "## How serious: share of injuries treated that were admissions",
        "",
        *points["admitted"],
        "",
        "<!-- chart: admitted -->",
        "",
        f"{CHART_NOTE} {CREDIT}",
        "",
        "| All ages | Motor vehicle involved | No motor vehicle |",
        "|---|---:|---:|",
        *(
            f"| {label} | "
            + " | ".join(_share_text(_at(serious[ebike, v], ALL)) for v in (True, False))
            + " |"
            for ebike, label in ((True, "Electric bicycle"), (False, "Other bicycle"))
        ),
        "",
        f"*{TABLE_NOTE}* {CREDIT}",
        "",
        *trend_body,
        "## Limits",
        "",
        "- **Per resident, not per ride.** There is no count of riders or miles, so a group that "
        "rides more will have more injuries per resident.",
        "- **Injuries, not visits, in the splits.** A visit coded under two causes or mechanisms "
        "is counted under each, so the shares are of coded injuries. The rates by age and sex "
        "count each visit once.",
        "- **Coding.** A record names an e-bike or a motor vehicle only if it was noted; a "
        "change in how fully these are recorded looks like a change in injuries. The e-bike "
        "share is a floor.",
        "- **Seriousness and coding.** An e-bike is probably named more often on the fuller "
        "record of an admitted patient than on a short emergency visit's, which would make "
        "e-bike injuries look more serious than they are.",
        "- **Two kinds of uncertainty.** Ranges cover hidden counts; the charts' intervals add "
        "chance. Neither covers coding.",
        "",
        "<!-- appendix -->",
        "",
        "## Appendix: the figures as tables",
        "",
        "### Bicycle injuries treated in hospital, all riders",
        "",
        "| Age | ED visits per 100,000 | Admissions per 100,000 | Both per 100,000 | "
        "Share admitted |",
        "|---|---:|---:|---:|---:|",
        *_table(
            [
                (_split(everyone, "ed"), _rate_text),
                (_split(everyone, "hosp"), _rate_text),
                (_split(everyone, "treated"), _rate_text),
                (_split(everyone, "admitted"), _share_text),
            ]
        ),
        "",
        '*Rates are per resident a year; each visit is counted once. "Suppressed" marks a '
        f"count the source hides (under 11), entered as 1 to 10. {TABLE_NOTE}* " + CREDIT,
        "",
        "### Bicycle injuries treated in hospital, by sex",
        "",
        "| Age | Both per 100,000, female | Both per 100,000, male | Share admitted, female | "
        "Share admitted, male |",
        "|---|---:|---:|---:|---:|",
        *_table(
            [(_split(rates[s], "treated"), _rate_text) for s in ("Female", "Male")]
            + [(_split(rates[s], "admitted"), _share_text) for s in ("Female", "Male")]
        ),
        "",
        f"*Records with sex other than male or female, or not recorded, are left out. "
        f"{TABLE_NOTE}* {CREDIT}",
        "",
        "### Motor vehicle involved, share of bicycle injuries treated",
        "",
        "| Age | All riders |",
        "|---|---:|",
        *_table([(vehicle, _share_text)]),
        "",
        f"*{TABLE_NOTE}* {CREDIT}",
        "",
        "### Electric bicycles, by age",
        "",
        f"| Age | {ebike_head}",
        "|---|---:|---:|---:|",
        *_lines(by_age, ebike_keys, _share_text),
        "",
        f"*{TABLE_NOTE}* {CREDIT}",
        "",
        "### Electric bicycles, by sex",
        "",
        f"| Sex | {ebike_head}",
        "|---|---:|---:|---:|",
        *_lines(by_sex, ebike_keys, _share_text),
        "",
        f"*{TABLE_NOTE}* {CREDIT}",
        "",
        "### Share admitted, by age",
        "",
        "| Age | E-bike, motor vehicle | Other, motor vehicle | E-bike, no motor vehicle | "
        "Other, no motor vehicle |",
        "|---|---:|---:|---:|---:|",
        *_lines(serious, [(True, True), (False, True), (True, False), (False, False)], _share_text),
        "",
        f"*{TABLE_NOTE}* {CREDIT}",
        "",
        *trend_tables,
        "## Appendix: how the figures are worked out",
        "",
        "**Treated.** Emergency department visits plus admissions. A visit that ends in "
        "admission at the same hospital is counted once, as an admission. Admissions use the "
        "comprehensive definition (a bicycle-injury code anywhere on the record).",
        "",
        '**Motor vehicle involved.** EpiCenter\'s mechanism "MVT-Pedal Cyclist": a pedal '
        "cyclist hurt in a collision with a motor vehicle in traffic. Falls, collisions with "
        "other cyclists or pedestrians, and crashes off the road are the other mechanism.",
        "",
        "**Electric bicycle.** A cause naming an electric (assisted) bicycle, in use since "
        "October 2022.",
        "",
        "**Shares.** The lowest share pairs the fewest cases in the group with the most outside "
        "it, and the highest the reverse. A group that joins hidden and published counts is "
        "printed as a range: its published part is in the source's own table.",
        "",
        "**Chance intervals.** For a share, the 95% Wilson score interval; for a rate, the exact "
        "95% Poisson interval for its count. Each is taken at the ends of the range: the lower "
        "limit at the lowest figure, the upper at the highest.",
        "",
        "**Hidden counts.**",
        "",
        *HIDDEN_COUNTS,
        "",
        links.MADE_WITH,
        "",
    ]
    return "\n".join(lines), drawn


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Bicycle injuries treated in hospital, California."
    )
    parser.add_argument("--tables", type=Path, required=True, help="an EpiCenter folder")
    parser.add_argument("--residents", type=Path, required=True, help="the Census PEP folder")
    parser.add_argument("--out", type=Path, required=True, help="folder for the report")
    parser.add_argument("--pdf", action="store_true", help="also print a PDF (needs Chrome)")
    args = parser.parse_args(argv)
    text, drawn = markdown(args.tables, args.residents)
    args.out.mkdir(parents=True, exist_ok=True)
    stem = "hospital_profile_california"
    (args.out / f"{stem}.md").write_text(text)
    print(f"wrote {args.out / f'{stem}.md'}")
    if args.pdf:
        from bike_safety_ca.hospital import pdf

        print(f"wrote {pdf.write(stem, text, drawn, args.out)}")


if __name__ == "__main__":
    main()
