"""Sort injury crashes into the groups the ranking uses.

A crash is a child cyclist crash if any cyclist in it is at or under the
child age, an adult cyclist crash if a cyclist is older than that, and a
cyclist crash of unrecorded age if it involved a bicycle but no cyclist's age
is known.  All three count toward "all cyclists"; only the first counts as a
child crash, so child figures cover known ages only.  A crash with no cyclist
or pedestrian is motor-vehicle-only.  Everything else (pedestrian crashes) is
"Other" and is not used.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import shapely
from shapely.geometry.base import BaseGeometry

from bike_safety_ca import ADULT, CAR, CHILD, UNKNOWN_AGE
from bike_safety_ca.io import crs_tag

OTHER = "Other"
BICYCLE = "4"  # PARTY_TYPE code
# How sure the location is, and the injury severity (for ``checks.sensitivity.by_severity``).
OPTIONAL = ["offset_direction_missing", "reported_offset_m", "COLLISION_SEVERITY"]
MAX_AGE = 100  # larger values are placeholders for an unknown age
COLUMNS = [
    "merged_id",
    "year",
    "injury_crash",
    "bike_involved",
    "ped_involved",
    "possible_duplicate_of",
    "INTERSECTION",
    "DISTANCE",
    "PRIMARY_RD",
    "SECONDARY_RD",
    "geometry",
]


def group_crashes(
    crashes: gpd.GeoDataFrame,
    parties: pd.DataFrame,
    child_max_age: int = 18,
    area: BaseGeometry | None = None,
) -> gpd.GeoDataFrame:
    """Located injury crashes, one row each, with a ``group`` column.

    ``crashes`` is the merged crash table and ``parties`` the merged party
    table (``CASE_ID`` holding the crash's ``merged_id``).  Possible duplicate
    reports, crashes without injury and crashes without a location are dropped,
    as are crashes outside ``area`` when one is given.
    """
    kept = crashes[crashes.possible_duplicate_of.isna() & crashes.injury_crash.astype(bool)]
    shapes = kept.geometry.to_numpy()
    kept = kept[shapely.is_geometry(shapes) & ~shapely.is_empty(shapes)].copy()
    if area is not None:
        kept = kept[kept.geometry.within(area)].copy()

    age = pd.to_numeric(parties.PARTY_AGE, errors="coerce")
    age = age.where(age.between(0, MAX_AGE))
    cyclist = parties.PARTY_TYPE.astype("string").str.strip().eq(BICYCLE)
    child = set(parties.CASE_ID[cyclist & age.le(child_max_age)])
    adult = set(parties.CASE_ID[cyclist & age.gt(child_max_age)])

    motor_only = ~kept.bike_involved.astype(bool) & ~kept.ped_involved.astype(bool)
    kept["group"] = OTHER
    kept.loc[motor_only, "group"] = CAR
    kept.loc[kept.bike_involved.astype(bool), "group"] = UNKNOWN_AGE
    kept.loc[kept.merged_id.isin(adult), "group"] = ADULT
    kept.loc[kept.merged_id.isin(child), "group"] = CHILD
    return kept


def load(
    folder: Path, crs: str, child_max_age: int = 18, area: BaseGeometry | None = None
) -> gpd.GeoDataFrame:
    """Read the crash tables written by ``python -m bike_safety_ca.crashes`` and group them."""
    path = folder / f"crashes_merged_{crs_tag(crs)}.parquet"
    # Tables built before these columns existed, or without centerlines, lack them.
    extra = [name for name in OPTIONAL if name in pq.read_schema(path).names]
    crashes = gpd.read_parquet(path, columns=[*COLUMNS, *extra])
    parties = pd.read_parquet(
        folder / "parties_merged.parquet", columns=["CASE_ID", "PARTY_TYPE", "PARTY_AGE"]
    )
    return group_crashes(crashes, parties, child_max_age, area)
