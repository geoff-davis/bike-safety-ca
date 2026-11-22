"""Summary tables of crashes: totals only, no individual record."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd

from bike_safety_ca import CAR, CYCLISTS
from bike_safety_ca.crashes.groups import BICYCLE, MAX_AGE, OTHER
from bike_safety_ca.report.crashes import cyclists

GROUPS = [*CYCLISTS, CAR, OTHER]
HOURS = {"12-6 am": (0, 5), "6-9 am": (6, 8), "9 am-2 pm": (9, 13), "2-5 pm": (14, 16),
         "5-8 pm": (17, 19), "8 pm-12 am": (20, 23)}  # fmt: skip
UNKNOWN = "not recorded"


def by_year(crashes: gpd.GeoDataFrame) -> pd.DataFrame:
    """Injury crashes per year in each group."""
    table = pd.crosstab(crashes.year, crashes.group).reindex(columns=GROUPS, fill_value=0)
    table.loc["All years"] = table.sum()
    return table


def by_cause(crashes: gpd.GeoDataFrame) -> pd.DataFrame:
    """Cyclist crashes by the cause the officer coded, children and adults."""
    bike = cyclists(crashes)
    table = pd.crosstab(bike.cause, bike.group).reindex(columns=CYCLISTS, fill_value=0)
    table["All cyclists"] = table.sum(axis=1)
    return table.sort_values("All cyclists", ascending=False)


def by_hour(crashes: gpd.GeoDataFrame) -> pd.DataFrame:
    """Cyclist crashes by time of day, with a row for school-commute hours."""
    bike = cyclists(crashes)
    band = pd.Series(UNKNOWN, index=bike.index)
    for label, (first, last) in HOURS.items():
        band[bike.hour.between(first, last)] = label
    table = pd.crosstab(band.rename("time of day"), bike.group).reindex(
        index=[*HOURS, UNKNOWN], columns=CYCLISTS, fill_value=0
    )
    table.loc["School-commute hours"] = (
        bike[bike.commute].group.value_counts().reindex(CYCLISTS, fill_value=0)
    )
    return table


def by_age(crashes: gpd.GeoDataFrame, parties: pd.DataFrame, child_max_age: int) -> pd.DataFrame:
    """Cyclists in the crashes by age band, with how many were coded at fault."""
    riders = parties[
        parties.PARTY_TYPE.astype("string").str.strip().eq(BICYCLE)
        & parties.CASE_ID.isin(cyclists(crashes).merged_id)
    ]
    age = pd.to_numeric(riders.PARTY_AGE, errors="coerce")
    age = age.where(age.le(MAX_AGE))
    edges = sorted({-1, 10, 13, child_max_age, 24, 44, 64, MAX_AGE})
    labels = [f"{low + 1}-{high}" for low, high in zip(edges, edges[1:], strict=False)]
    band = pd.cut(age, edges, labels=labels).astype("string").fillna(UNKNOWN)
    fault = riders.AT_FAULT.astype("string").eq("Y").fillna(False)
    table = pd.DataFrame(
        {"cyclists": band.value_counts(), "coded at fault": band[fault].value_counts()}
    )
    return table.reindex([*labels, UNKNOWN]).fillna(0).astype(int).rename_axis("age")


def tables(
    crashes: gpd.GeoDataFrame, parties: pd.DataFrame, child_max_age: int
) -> dict[str, pd.DataFrame]:
    return {
        "crashes_by_year": by_year(crashes),
        "cyclist_crashes_by_cause": by_cause(crashes),
        "cyclist_crashes_by_hour": by_hour(crashes),
        "cyclists_by_age": by_age(crashes, parties, child_max_age),
    }


def write(found: dict[str, pd.DataFrame], out: Path, prefix: str) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, table in found.items():
        path = out / f"{prefix}_{name}.csv"
        table.to_csv(path)
        written.append(path)
    return written
