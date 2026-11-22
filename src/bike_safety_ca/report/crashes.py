"""The cyclist crashes the summaries and the map are drawn from."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from shapely.geometry.base import BaseGeometry

from bike_safety_ca import CYCLISTS
from bike_safety_ca.config import Config
from bike_safety_ca.crashes import groups
from bike_safety_ca.io import crs_tag
from bike_safety_ca.report.codes import CAUSES, OTHER_CAUSE

DETAIL = [
    "merged_id",
    "CASE_ID",
    "ccrs_collision_id",
    "collision_date",
    "collision_hour",
    "CITY",
    "PCF_VIOL_CATEGORY",
    "TYPE_OF_COLLISION",
]
# Read when present: tables built before it was kept lack it.
OPTIONAL_DETAIL = ["LIGHTING"]


Day = tuple[int, int]


def school_commute(
    date: pd.Series, hour: pd.Series, summer_break: tuple[Day, Day] = ((6, 8), (8, 14))
) -> pd.Series:
    """Weekdays outside the summer break, 7-8 am or 2-4 pm: a rough school-commute flag.

    ``summer_break`` is its first and last day as (month, day), from the
    config; other holidays are not known and count as school days.
    """
    when = date.dt.month * 100 + date.dt.day
    (m0, d0), (m1, d1) = summer_break
    summer = when.between(m0 * 100 + d0, m1 * 100 + d1)
    return date.dt.day_of_week.lt(5) & ~summer & (hour.between(7, 8) | hour.between(14, 16))


def describe(crashes: gpd.GeoDataFrame, detail: pd.DataFrame, config: Config) -> gpd.GeoDataFrame:
    """Add date, hour, cause, commute and in-city columns to grouped crashes."""
    out = crashes.join(detail.drop_duplicates("merged_id").set_index("merged_id"), on="merged_id")
    out["date"] = pd.to_datetime(out.collision_date)
    out["hour"] = pd.to_numeric(out.collision_hour, errors="coerce").astype(float)
    out["cause"] = (
        out.PCF_VIOL_CATEGORY.astype("string").str.strip().map(CAUSES).fillna(OTHER_CAUSE)
    )
    out["commute"] = school_commute(out.date, out.hour, config.summer_break)
    out["in_city"] = out.CITY.astype("string").str.upper().eq(config.city.upper()).fillna(False)
    return out


def load(folder: Path, config: Config, area: BaseGeometry | None) -> gpd.GeoDataFrame:
    """Located injury crashes in ``area`` with their group and the columns above."""
    crashes = groups.load(folder, config.crs, config.child_max_age, area)
    crashes = crashes[crashes.year.ge(config.first_year)]
    path = folder / f"crashes_merged_{crs_tag(config.crs)}.parquet"
    extra = [name for name in OPTIONAL_DETAIL if name in pq.read_schema(path).names]
    detail = pd.read_parquet(path, columns=[*DETAIL, *extra])
    return describe(crashes, detail, config)


def cyclists(crashes: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    return crashes[crashes.group.isin(CYCLISTS)]
