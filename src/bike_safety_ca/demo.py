"""Made-up crashes on a real street map: ``python -m bike_safety_ca.demo --config config/demo_claremont.yaml``.

The streets and outlines are real (OpenStreetMap and the Census Bureau).  Every
crash and every party is invented: nothing here is fitted to, copied from or
checked against police records.  The settings are round numbers chosen so the
tables look roughly like a small city's.

Each intersection gets a true yearly bike crash rate from the size of its
roads, a hazard shared along each street and its own luck, and crashes are
drawn from those rates year by year.  Because the true rates are saved beside
the crash tables, a ranking can be scored against the truth as well as against
later crashes, which real data never allows.

Three made-up agencies report the crashes, and each has a planted change for
the reporting check to find:

- ``SYN-A`` (the city) changes report format in 2023 with no loss, and from
  2022 grades most "complaint of pain" injuries as "visible injury".
- ``SYN-B`` (the west side) changes report format in mid-2021 with no loss.
- ``SYN-C`` (the east side) changes report format in April 2022 and from then
  on files only three in ten of its crashes.

Cyclist crashes follow a few everyday patterns (a car turning right across a
cyclist going straight, a car turning left across an oncoming cyclist, two
parties going straight across each other, and so on), with movements and
directions that agree.  Three of the city's intersections have a planted
pattern for the map's collision diagrams to show (``PLANTED``): right hooks
from one direction at the first, left crosses from one direction at the
second, and crashes after dark at the third.

The tables have the columns the other steps read, so the hold-out check, the
reporting check, the summaries and the movement map all run on them unchanged.
Case numbers start with ``SYN-`` so no row can be mistaken for a real record.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry.base import BaseGeometry

from bike_safety_ca import config as settings
from bike_safety_ca.config import Config
from bike_safety_ca.io import crs_tag, read_shapes
from bike_safety_ca.network import junctions
from bike_safety_ca.network import streets as street_table
from bike_safety_ca.report import codes
from bike_safety_ca.report.movement import Bearings

log = logging.getLogger(__name__)

PREFIX = "SYN-"
CITY_AGENCY, WEST_AGENCY, EAST_AGENCY = "SYN-A", "SYN-B", "SYN-C"
WEST, EAST = "Neighbour West", "Neighbour East"
# Date each agency starts filing in the newer report format.
FORMAT_CHANGE = {CITY_AGENCY: "2023-01-01", WEST_AGENCY: "2021-07-01", EAST_AGENCY: "2022-04-01"}
EAST_KEPT_SHARE = 0.3  # share of its crashes the east agency files after its change
REGRADE_FROM, REGRADE_SHARE = 2022, 0.8  # the city agency's change in injury grading
CCRS_ONLY_FROM = "2025-07-01"  # later crashes are "in CCRS only", as recent months are
# Round-number totals for the whole area, per year.
BIKE_PER_YEAR, CAR_PER_YEAR, CHILD_SHARE = 90.0, 600.0, 0.35
MID_BLOCK_SHARE = 0.2  # extra crashes placed along streets, away from intersections
FLOW = {"Major arterial": 20.0, "Arterial": 10.0, "Collector": 4.0, "Local": 1.0}
COMPASS = "NESW"
# Cyclist crash patterns: (the other party's heading less the cyclist's,
# cyclist's movement, other party's movement, collision type, who is at fault)
# and a weight.  Movements and collision types are the SWITRS codes.
RIGHT_HOOK = (0, "B", "D", "B", "other")
LEFT_CROSS = (180, "B", "E", "D", "other")
SCENARIOS = {
    (90, "B", "B", "D", ""): 20,  # straight across each other, the other from the left
    (270, "B", "B", "D", ""): 20,  # ... from the right
    RIGHT_HOOK: 14,
    LEFT_CROSS: 12,
    (0, "B", "B", "C", "other"): 8,  # rear end
    (180, "E", "B", "D", "cyclist"): 6,  # cyclist turning left across an oncoming car
    (270, "B", "L", "D", "other"): 6,  # car pulling out from the cyclist's right
    (0, "B", "O", "B", "other"): 6,  # a parked car (a door opening)
    (90, "Q", "D", "D", "cyclist"): 4,  # cyclist riding the wrong way
}
# The three planted intersections, in the order chosen (the city's corners of
# two named streets with the most cyclist crashes first), and the share of
# each one's cyclist crashes changed.
PLANTED = ("right hook", "left cross", "after dark")
PLANTED_SHARE = 0.8


@dataclass(frozen=True)
class Demo:
    """``crashes`` and ``parties`` in the merged-table layout; ``truth`` has one row
    per intersection with its true yearly rates."""

    crashes: gpd.GeoDataFrame
    parties: pd.DataFrame
    truth: gpd.GeoDataFrame


def true_rates(sites: gpd.GeoDataFrame, roads: pd.Series, rng: np.random.Generator) -> pd.DataFrame:
    """True yearly car and bike crash rates per intersection."""
    names = sorted({name for keys in roads for name in keys})
    hazard = pd.Series(rng.lognormal(0, 0.8, len(names)), names)
    shared = np.array([hazard[sorted(keys)].mean() if keys else 1.0 for keys in roads])
    flow = (sites.major.map(FLOW) + sites.minor.map(FLOW)).to_numpy(dtype=float)
    car = flow * rng.lognormal(0, 0.5, len(sites))
    bike = flow**0.8 * shared * rng.lognormal(0, 0.5, len(sites))
    at_sites = 1 - MID_BLOCK_SHARE
    return pd.DataFrame(
        {
            "car_rate": car / car.sum() * CAR_PER_YEAR * at_sites,
            "bike_rate": bike / bike.sum() * BIKE_PER_YEAR * at_sites,
        },
        index=sites.index,
    )


def _draw(rng: np.random.Generator, options: dict[str, float], size: int) -> np.ndarray:
    weights = np.array(list(options.values()), dtype=float)
    return rng.choice(list(options), size=size, p=weights / weights.sum())


def _dates(rng: np.random.Generator, years: np.ndarray, child: np.ndarray) -> pd.Series:
    """A date in each crash's year; children's crashes are mostly on school days."""
    start = pd.to_datetime(pd.Series(years).astype(str) + "-01-01")
    days = pd.to_timedelta(rng.integers(0, 365, len(years)), unit="D")
    date = start + days
    # Move most children's weekend and summer crashes to a school day in spring or autumn.
    off = child & (date.dt.day_of_week.ge(5) | date.dt.month.isin([6, 7, 8]))
    move = off & (rng.random(len(years)) < 0.7)
    school_day = start + pd.to_timedelta(rng.choice(np.r_[20:140, 250:340], len(years)), unit="D")
    school_day = school_day - pd.to_timedelta(
        np.maximum(school_day.dt.day_of_week - 4, 0), unit="D"
    )
    return date.where(~move, school_day)


def _hours(rng: np.random.Generator, child: np.ndarray, bike: np.ndarray) -> np.ndarray:
    """Hour of day: children cluster at school-commute hours, cyclists in daylight."""
    hour = rng.integers(0, 24, len(child))
    hour = np.where(bike, rng.integers(6, 22, len(child)), hour)
    commute = child & (rng.random(len(child)) < 0.55)
    return np.where(commute, rng.choice([7, 8, 14, 15, 16], len(child)), hour)


def _compass(bearing: float) -> str:
    return COMPASS[int(round(bearing / 90.0)) % 4]


def _lighting(rng: np.random.Generator, date: pd.Series, hour: np.ndarray) -> np.ndarray:
    """Light at each crash: dark at night and on winter evenings, dusk or dawn around them."""
    winter = date.dt.month.isin([11, 12, 1, 2]).to_numpy()
    sunset = np.where(winter, 17, 20)
    night = (hour >= sunset + 1) | (hour < 6)
    twilight = (hour == sunset) | (hour == 6)
    dark = rng.choice(["C", "D", "E"], len(hour), p=[0.8, 0.17, 0.03])
    return np.where(night, dark, np.where(twilight, "B", "A"))


def _stage(
    rows: pd.DataFrame,
    parties: pd.DataFrame,
    bike: np.ndarray,
    planted: dict[int, str],
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Give each cyclist crash a pattern, and plant three at their intersections.

    Rewrites ``parties`` (the cyclist is party 1, the other party 2) and sets
    ``TYPE_OF_COLLISION``, ``LIGHTING`` and, at the dark corner,
    ``collision_hour`` on ``rows``.  Returns the parties.
    """
    keys = list(SCENARIOS)
    weights = np.array(list(SCENARIOS.values()), dtype=float)
    chosen = [keys[i] for i in rng.choice(len(keys), len(rows), p=weights / weights.sum())]
    first_party = parties[parties.PARTY_NUMBER.eq("1")].set_index("CASE_ID").DIR_OF_TRAVEL
    heading = first_party.reindex(rows.merged_id).to_numpy().copy()
    site = rows.site.to_numpy()
    dark = np.zeros(len(rows), dtype=bool)
    for where, kind in planted.items():
        here = np.flatnonzero(bike & (site == where))
        if not len(here):
            continue
        changed = rng.choice(here, int(np.ceil(PLANTED_SHARE * len(here))), replace=False)
        if kind == "after dark":
            dark[changed] = True
            continue
        common = pd.Series(heading[here]).mode().iloc[0]
        heading[changed] = common
        for i in changed:
            chosen[i] = RIGHT_HOOK if kind == "right hook" else LEFT_CROSS
    hours = rows.collision_hour.to_numpy().copy()
    hours[dark] = rng.choice([19, 20, 21, 22], int(dark.sum()))
    rows["collision_hour"] = hours
    rows["LIGHTING"] = _lighting(rng, pd.to_datetime(rows.collision_date), hours)
    rows.loc[dark, "LIGHTING"] = rng.choice(["C", "D"], int(dark.sum()), p=[0.4, 0.6])

    idx = np.flatnonzero(bike)
    plan = pd.DataFrame(
        [chosen[i] for i in idx], columns=["turn", "rider", "other", "collision", "fault"]
    )
    plan["case"] = rows.merged_id.to_numpy()[idx]
    plan["own"] = heading[idx]
    plan["their"] = [
        _compass(codes.BEARINGS[h] + t) for h, t in zip(plan.own, plan.turn, strict=True)
    ]
    plan = plan.set_index("case")
    rows.loc[idx, "TYPE_OF_COLLISION"] = plan.collision.to_numpy()

    parties = parties.copy()
    staged = parties.CASE_ID.isin(plan.index)
    first, second = staged & parties.PARTY_NUMBER.eq("1"), staged & parties.PARTY_NUMBER.eq("2")

    def put(which: pd.Series, column: str, values: pd.Series) -> None:
        parties.loc[which, column] = parties.loc[which, "CASE_ID"].map(values).to_numpy()

    put(first, "DIR_OF_TRAVEL", plan.own)
    put(first, "MOVE_PRE_ACC", plan.rider)
    put(second, "DIR_OF_TRAVEL", plan.their)
    put(second, "MOVE_PRE_ACC", plan.other)
    parked = plan.index[plan.other.eq("O")]
    parties.loc[second & parties.CASE_ID.isin(parked), "PARTY_TYPE"] = "3"
    blamed = plan.fault.ne("")
    put(
        first & parties.CASE_ID.isin(plan.index[blamed]),
        "AT_FAULT",
        plan.fault.eq("cyclist").map({True: "Y", False: "N"}),
    )
    put(
        second & parties.CASE_ID.isin(plan.index[blamed]),
        "AT_FAULT",
        plan.fault.eq("cyclist").map({True: "N", False: "Y"}),
    )
    return parties


def make(
    config: Config,
    ways: gpd.GeoDataFrame,
    area: BaseGeometry,
    limit: BaseGeometry,
    seed: int = 0,
    last_year: int = 2025,
) -> Demo:
    """Invent crashes for ``config.first_year`` to ``last_year`` on the streets in ``ways``."""
    rng = np.random.default_rng(seed)
    sites, roads = junctions.build_junctions(ways, area)
    rates = true_rates(sites, roads, rng)
    years = np.arange(config.first_year, last_year + 1)

    # Crashes at intersections, drawn from the true rates.
    parts = []
    for kind, rate in (
        ("car", rates.car_rate),
        ("child", CHILD_SHARE * rates.bike_rate),
        ("adult", (1 - CHILD_SHARE) * rates.bike_rate),
    ):
        counts = rng.poisson(np.outer(rate.to_numpy(), np.ones(len(years))))
        site, year = np.nonzero(counts)
        repeat = counts[site, year]
        parts.append(
            pd.DataFrame(
                {
                    "site": np.repeat(sites.index.to_numpy()[site], repeat),
                    "year": np.repeat(years[year], repeat),
                    "kind": kind,
                }
            )
        )
    rows = pd.concat(parts, ignore_index=True)
    points = gpd.GeoSeries(sites.geometry.reindex(rows.site))
    rows["x"] = np.asarray(points.x) + rng.normal(0, 6, len(rows))
    rows["y"] = np.asarray(points.y) + rng.normal(0, 6, len(rows))
    names = sites.name.reindex(rows.site).fillna("").str.split(" / ")
    rows["PRIMARY_RD"] = [n[0].upper() if n and n[0] else None for n in names]
    rows["SECONDARY_RD"] = [n[1].upper() if len(n) > 1 else None for n in names]
    at_corner = rng.random(len(rows)) < 0.7
    rows["INTERSECTION"] = np.where(at_corner, "Y", "N")
    rows["DISTANCE"] = np.where(at_corner, 0, rng.integers(10, 90, len(rows))).astype(str)

    # Extra crashes along streets, away from intersections.
    named = ways[ways.name.notna() & ways.highway.isin(junctions.HIGHWAY_RANK)]
    named = named[named.intersects(area)]
    extra = int(len(rows) * MID_BLOCK_SHARE / (1 - MID_BLOCK_SHARE))
    pick = rng.choice(len(named), extra, p=(named.length / named.length.sum()).to_numpy())
    spots = gpd.GeoSeries(named.geometry.iloc[pick]).interpolate(
        pd.Series(rng.random(extra), index=named.index[pick]), normalized=True
    )
    bike_share = BIKE_PER_YEAR / (BIKE_PER_YEAR + CAR_PER_YEAR)
    mid_kind = np.where(
        rng.random(extra) < bike_share,
        np.where(rng.random(extra) < CHILD_SHARE, "child", "adult"),
        "car",
    )
    mid = pd.DataFrame(
        {
            "site": -1,
            "year": rng.choice(years, extra),
            "kind": mid_kind,
            "x": np.asarray(spots.x),
            "y": np.asarray(spots.y),
            "PRIMARY_RD": named.name.iloc[pick].str.upper().to_numpy(),
            "SECONDARY_RD": None,
            "INTERSECTION": "N",
            "DISTANCE": rng.integers(120, 600, extra).astype(str),
        }
    )
    rows = pd.concat([rows, mid], ignore_index=True)
    geometry = gpd.points_from_xy(rows.x, rows.y, crs=ways.crs)
    rows = rows[np.asarray(geometry.within(area))].reset_index(drop=True)
    geometry = gpd.points_from_xy(rows.x, rows.y, crs=ways.crs)

    child, bike = rows.kind.eq("child").to_numpy(), rows.kind.ne("car").to_numpy()
    rows["collision_date"] = _dates(rng, rows.year.to_numpy(), child).to_numpy()
    rows["collision_hour"] = _hours(rng, child, bike)

    # Who reports: the city's agency inside the limit, two neighbours outside.
    inside = np.asarray(geometry.within(limit))
    west = rows.x.to_numpy() < limit.centroid.x
    rows["CITY"] = np.where(inside, config.city, np.where(west, WEST, EAST))
    rows["reporting_agency"] = np.where(
        inside, CITY_AGENCY, np.where(west, WEST_AGENCY, EAST_AGENCY)
    )
    changed = rows.collision_date >= rows.reporting_agency.map(FORMAT_CHANGE).astype(
        "datetime64[ns]"
    )
    unfiled = (
        rows.reporting_agency.eq(EAST_AGENCY) & changed & (rng.random(len(rows)) > EAST_KEPT_SHARE)
    )
    keep = ~unfiled.to_numpy()
    rows, geometry, changed = rows[keep].reset_index(drop=True), geometry[keep], changed[keep]
    changed = changed.reset_index(drop=True)
    child, bike = rows.kind.eq("child").to_numpy(), rows.kind.ne("car").to_numpy()
    n = len(rows)

    severity = _draw(rng, {"4": 55, "3": 35, "2": 9, "1": 1}, n)
    regrade = (
        rows.reporting_agency.eq(CITY_AGENCY).to_numpy()
        & rows.year.ge(REGRADE_FROM).to_numpy()
        & (severity == "4")
        & (rng.random(n) < REGRADE_SHARE)
    )
    rows["COLLISION_SEVERITY"] = np.where(regrade, "3", severity)

    # Identifiers: every one starts with SYN- and none is a real case number.
    serial = pd.Series(np.arange(n))
    ccrs_only = (rows.collision_date >= pd.Timestamp(CCRS_ONLY_FROM)).to_numpy()
    newer = PREFIX + "8" + serial.map("{:07d}".format)
    earlier = PREFIX + "9" + serial.map("{:06d}".format)
    case = newer.where(changed, earlier)
    rows["CASE_ID"] = case.where(~ccrs_only, None).astype("string")
    rows["merged_id"] = case.where(~ccrs_only, PREFIX + "C" + serial.map("{:07d}".format))
    rows["ccrs_collision_id"] = (
        (9_000_000_000 + serial).where(ccrs_only).astype("Int64")  # far above real ids
    )
    rows["source"] = np.where(ccrs_only, "ccrs", "tims")

    # Parties: a cyclist and a driver, or two drivers, moving along the streets.
    bearings = Bearings(ways)
    near: dict[int, list[float]] = {}
    first_dir, second_dir = [], []
    turn = rng.choice([0, 90, 180, 270], n, p=[0.4, 0.25, 0.1, 0.25])
    for i, (site, point) in enumerate(zip(rows.site, geometry)):
        found = near.get(site) if site >= 0 else None
        if found is None:
            found = bearings.near(point) or [0.0, 90.0, 180.0, 270.0]
            if site >= 0:
                near[site] = found
        heading = found[int(rng.integers(len(found)))]
        first_dir.append(_compass(heading))
        second_dir.append(_compass(heading + turn[i]))
    rider_move = _draw(rng, {"B": 80, "E": 8, "D": 5, "Q": 4, "L": 3}, n)
    driver_move = _draw(rng, {"B": 50, "D": 20, "E": 20, "A": 5, "H": 5}, n)
    rider_fault = rng.random(n) < 0.45
    age_child = rng.integers(6, 19, n)
    age_adult = rng.integers(19, 80, n)
    first = pd.DataFrame(
        {
            "CASE_ID": rows.merged_id,
            "ccrs_collision_id": rows.ccrs_collision_id,
            "PARTY_NUMBER": "1",
            "PARTY_TYPE": np.where(bike, "4", "1"),
            "AT_FAULT": np.where(rider_fault, "Y", "N"),
            "PARTY_AGE": np.where(child, age_child, age_adult).astype(str),
            "DIR_OF_TRAVEL": first_dir,
            "MOVE_PRE_ACC": np.where(bike, rider_move, driver_move),
            "STWD_VEHICLE_TYPE": np.where(bike, "L", "A"),
            "source": rows.source,
        }
    )
    second = first.assign(
        PARTY_NUMBER="2",
        PARTY_TYPE="1",
        AT_FAULT=np.where(rider_fault, "N", "Y"),
        PARTY_AGE=rng.integers(17, 85, n).astype(str),
        DIR_OF_TRAVEL=second_dir,
        MOVE_PRE_ACC=_draw(rng, {"B": 50, "D": 20, "E": 20, "A": 5, "H": 5}, n),
        STWD_VEHICLE_TYPE="A",
    )
    parties = pd.concat([first, second], ignore_index=True).sort_values(
        ["CASE_ID", "PARTY_NUMBER"], ignore_index=True
    )

    cause = _draw(rng, dict.fromkeys(codes.CAUSES, 1.0) | {"09": 4, "08": 3, "12": 3, "03": 2}, n)
    wrong_way = bike & (rider_move == "Q")
    rows["PCF_VIOL_CATEGORY"] = np.where(wrong_way, "05", cause)
    rows["TYPE_OF_COLLISION"] = _draw(rng, {"D": 50, "B": 20, "C": 15, "A": 5, "H": 10}, n)
    # Patterns and light come from a second generator, so the draws above,
    # and the tables the other checks rely on, are the same as without them.
    # The city's corners of two named streets with the most cyclist crashes.
    corners = sites.index[sites.geometry.within(limit) & sites.name.str.contains(" / ")]
    tally = pd.Series(rows.site.to_numpy()[bike]).value_counts()
    tally = (
        tally[tally.index.isin(corners)].sort_index().sort_values(ascending=False, kind="stable")
    )
    planted = dict(zip((int(i) for i in tally.index[: len(PLANTED)]), PLANTED, strict=False))
    parties = _stage(rows, parties, bike, planted, np.random.default_rng([seed, 1]))
    # Staging can make a cyclist ride the wrong way, or stop doing so; the cause follows.
    riders = parties[parties.PARTY_NUMBER.eq("1")].set_index("CASE_ID").MOVE_PRE_ACC
    wrong_way = bike & (riders.reindex(rows.merged_id).to_numpy() == "Q")
    rows["PCF_VIOL_CATEGORY"] = np.where(wrong_way, "05", cause)
    rows["injury_crash"] = True
    rows["bike_involved"] = bike
    rows["ped_involved"] = False
    rows["possible_duplicate_of"] = pd.Series([None] * n, dtype="string")
    rows["collision_hour"] = rows.collision_hour.astype("Int64")
    rows["year"] = rows.year.astype("int32")
    crashes = gpd.GeoDataFrame(
        rows.drop(columns=["site", "kind", "x", "y"]), geometry=geometry, crs=ways.crs
    )
    truth = gpd.GeoDataFrame(
        rates.assign(
            name=sites.name,
            in_city=sites.geometry.within(limit),
            planted=pd.Series(planted, dtype="string").reindex(sites.index),
        ),
        geometry=sites.geometry,
        crs=ways.crs,
    )
    return Demo(crashes, parties, truth)


def paths(out: Path, crs: str) -> dict[str, Path]:
    """Where ``write`` puts each table under ``out``."""
    processed = out / "processed"
    return {
        "streets": street_table.path(processed / "network", crs),
        "crashes": processed / "crashes" / f"crashes_merged_{crs_tag(crs)}.parquet",
        "parties": processed / "crashes" / "parties_merged.parquet",
        "truth": processed / "truth.parquet",
    }


def build(config: Config, out: Path, seed: int = 0) -> dict[str, Path]:
    """Build the demo city's street table and made-up crash tables under ``out``."""
    if not config.synthetic:
        raise ValueError("the config must say `synthetic: true` to make demo data")
    if config.streets_file is None or config.area_file is None or config.city_limit_file is None:
        raise ValueError("the demo config needs streets_file, area_file and city_limit_file")
    written = paths(out, config.crs)
    street_table.build(config.streets_file, written["streets"].parent, config.crs)
    ways = gpd.read_parquet(written["streets"])
    area = read_shapes(config.area_file).to_crs(config.crs).union_all()
    limit = read_shapes(config.city_limit_file).to_crs(config.crs).union_all()
    demo = make(config, ways, area, limit, seed)
    written["crashes"].parent.mkdir(parents=True, exist_ok=True)
    demo.crashes.to_parquet(written["crashes"], index=False)
    demo.parties.to_parquet(written["parties"], index=False)
    demo.truth.to_parquet(written["truth"])
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", type=Path, default=Path("config/demo_claremont.yaml"))
    parser.add_argument("--out", type=Path, default=Path("data/demo"))
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    for name, path in build(settings.load(args.config), args.out, args.seed).items():
        log.info("wrote %s: %s", name, path)
    log.info("every crash in these tables is made up")


if __name__ == "__main__":
    main()
