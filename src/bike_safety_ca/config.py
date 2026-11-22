"""Load a city's settings from a YAML file."""

from __future__ import annotations

import math
import re
from dataclasses import MISSING, dataclass, field, fields
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml
from pyproj import CRS

CRASH_SOURCES = ("tims+ccrs",)
YEARS = (1990, 2100)  # a year outside this range is a typing mistake
OLDEST = 120
OSM_DATE = "%Y-%m-%dT%H:%M:%SZ"
COUNTIES = (1, 99)  # CCRS numbers California's counties from 1; two digits at most


@dataclass(frozen=True)
class Reassignment:
    """Reports filed under ``filed_as`` that belong to ``agency``.

    A report is moved when its beat starts with ``beat_prefix`` or its city is
    ``city``; either may be left out.  ``from_year`` limits the rule to crashes
    in that year or later.
    """

    filed_as: str
    agency: str
    beat_prefix: str | None = None
    city: str | None = None
    from_year: int | None = None  # leave out to move reports of every year


@dataclass(frozen=True)
class Config:
    city: str
    county: str
    crash_source: str
    first_year: int
    child_max_age: int
    holdout_windows: tuple[tuple[int, int, int | None], ...]
    crs: str
    ccrs_county_code: int
    ccrs_cities: tuple[str, ...]
    latitude: tuple[float, float]
    longitude: tuple[float, float]
    agency_reassignments: tuple[Reassignment, ...] = ()
    municipality_aliases: dict[str, str] = field(default_factory=dict)
    # Optional outlines to use instead of the ones built from the city list.
    area_file: Path | None = None
    city_limit_file: Path | None = None
    # Optional: the city's own city-limit layer (an ArcGIS layer address), used
    # in place of the Census outline when it can be fetched.
    city_limit_url: str | None = None
    # Optional: make the area circles of ``area_buffer_m`` metres, joined with the
    # city limit, around any of: schools looked up by (school, district) in the
    # state's public school directory; (longitude, latitude) points; the points
    # in a CSV of your own with longitude and latitude columns.
    area_schools: tuple[tuple[str, str], ...] = ()
    area_points: tuple[tuple[float, float], ...] = ()
    area_points_file: Path | None = None
    area_buffer_m: float | None = None
    # Optional OpenStreetMap snapshot time ("2026-08-22T23:47:01Z") to pin the streets.
    osm_date: str | None = None
    # Optional ready-made street extract (Overpass JSON, plain or gzipped) to
    # use instead of downloading.
    streets_file: Path | None = None
    # First and last day of the schools' summer break, as (month, day) pairs;
    # used only for the rough school-commute flag in the summaries.
    summer_break: tuple[tuple[int, int], tuple[int, int]] = ((6, 8), (8, 14))
    # True when the crash tables are made up (see ``bike_safety_ca.demo``):
    # every chart and map is then labelled as synthetic.
    synthetic: bool = False


def _whole(value: object, low: int, high: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def _number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _only(entry: object, known: set[str], key: str, path: str | Path) -> None:
    """Refuse a mapping with a key that is not in ``known``."""
    if not isinstance(entry, dict):
        raise ValueError(f"{path}: {key}: each entry is a mapping, not {entry!r}")
    unknown = sorted(str(name) for name in set(entry) - known)
    if unknown:
        raise ValueError(
            f"{path}: {key}: unknown key {', '.join(unknown)}; the keys are "
            f"{', '.join(sorted(known))}"
        )


def _osm_date(value: object, path: str | Path) -> str:
    """The snapshot time as "YYYY-MM-DDTHH:MM:SSZ"; YAML reads an unquoted one as a time."""
    if isinstance(value, datetime):
        utc = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return utc.strftime(OSM_DATE)
    wanted = 'osm_date: must be a UTC time in quotes, like "2026-08-22T23:47:01Z"'
    if isinstance(value, date):
        raise ValueError(f"{path}: {wanted}; {value} has no time of day")
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value):
        raise ValueError(f"{path}: {wanted}, not {value!r}")
    try:
        datetime.strptime(value, OSM_DATE)
    except ValueError:
        raise ValueError(f"{path}: {wanted}; {value!r} is not a real date and time") from None
    return value


def _summer_break(value: object, path: str | Path) -> tuple[tuple[int, int], tuple[int, int]]:
    """The break's first and last day as (month, day) pairs."""
    wanted = f'{path}: summer_break: must be ["MM-DD", "MM-DD"], first day then last, not {value!r}'
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(wanted)
    days = []
    for day in value:
        if not isinstance(day, str) or not re.fullmatch(r"\d\d-\d\d", day):
            raise ValueError(wanted)
        try:
            real = datetime.strptime(f"2000-{day}", "%Y-%m-%d")  # a leap year: 02-29 is a day
        except ValueError:
            raise ValueError(wanted) from None
        days.append((real.month, real.day))
    if not days[0] < days[1]:
        raise ValueError(wanted)
    return (days[0], days[1])


def _check(raw: object, path: str | Path) -> dict[str, Any]:
    """Check the keys, and the values whose mistakes would change results silently."""
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: the config must be a list of `key: value` settings")
    known = {item.name for item in fields(Config)}
    unknown = sorted(str(key) for key in set(raw) - known)
    if unknown:
        raise ValueError(f"{path}: unknown key {', '.join(unknown)}")
    for item in fields(Config):
        required = item.default is MISSING and item.default_factory is MISSING
        if required and raw.get(item.name) is None:
            raise ValueError(f"{path}: {item.name}: this key is required")
    if not _whole(raw["first_year"], *YEARS):
        raise ValueError(
            f"{path}: first_year: must be a whole year from {YEARS[0]} to {YEARS[1]}, "
            f"not {raw['first_year']!r}"
        )
    if not _whole(raw["child_max_age"], 0, OLDEST):
        raise ValueError(
            f"{path}: child_max_age: must be a whole number of years from 0 to {OLDEST}, "
            f"not {raw['child_max_age']!r}"
        )
    windows = raw["holdout_windows"]
    for window in windows if isinstance(windows, list) else [None]:
        if (
            not isinstance(window, list)
            or len(window) != 3
            or not all(_whole(year, *YEARS) for year in window[:2])
            or not (window[2] is None or _whole(window[2], *YEARS))
        ):
            raise ValueError(
                f"{path}: holdout_windows: each window is [last training year, first test "
                f"year, last test year or null] in whole years from {YEARS[0]} to {YEARS[1]}, "
                f"not {window!r}"
            )
    cities = raw["ccrs_cities"]
    if (
        not isinstance(cities, list)
        or not cities
        or not all(isinstance(name, str) and name.strip() for name in cities)
    ):
        raise ValueError(
            f"{path}: ccrs_cities: must be a list of city names, one `- Name` per line, "
            f"not {cities!r}"
        )
    for key, limit in (("latitude", 90), ("longitude", 180)):
        box = raw[key]
        if (
            not isinstance(box, list)
            or len(box) != 2
            or not all(_number(edge) and -limit <= edge <= limit for edge in box)
            or not box[0] < box[1]
        ):
            raise ValueError(
                f"{path}: {key}: must be [low, high] in degrees between -{limit} and {limit}, "
                f"low first, not {box!r}"
            )
    for rule in raw.get("agency_reassignments") or ():
        _only(rule, {item.name for item in fields(Reassignment)}, "agency_reassignments", path)
        if not (rule.get("from_year") is None or _whole(rule["from_year"], *YEARS)):
            raise ValueError(
                f"{path}: agency_reassignments: from_year must be a whole year from "
                f"{YEARS[0]} to {YEARS[1]}, not {rule['from_year']!r}"
            )
    if not _whole(raw["ccrs_county_code"], *COUNTIES):
        raise ValueError(
            f"{path}: ccrs_county_code: must be the county's number in CCRS, a whole number "
            f"from {COUNTIES[0]} to {COUNTIES[1]}, not {raw['ccrs_county_code']!r}"
        )
    buffer = raw.get("area_buffer_m")
    if not (buffer is None or (_number(buffer) and math.isfinite(buffer) and buffer >= 0)):
        raise ValueError(
            f"{path}: area_buffer_m: must be a distance in metres, 0 or more, not {buffer!r}"
        )
    if not isinstance(raw.get("synthetic", False), bool):
        raise ValueError(
            f"{path}: synthetic: must be true or false, without quotes, not {raw['synthetic']!r}"
        )
    if raw.get("summer_break") is not None:
        raw["summer_break"] = _summer_break(raw["summer_break"], path)
    for entry in raw.get("area_schools") or ():
        _only(entry, {"school", "district"}, "area_schools", path)
    if raw.get("osm_date") is not None:
        raw["osm_date"] = _osm_date(raw["osm_date"], path)
    return raw


def load(path: str | Path) -> Config:
    """Read and check a city config; unknown or missing keys are errors.

    Outline files are given relative to the config file.
    """
    raw = _check(yaml.safe_load(Path(path).read_text()), path)
    raw["holdout_windows"] = tuple((a, b, c) for a, b, c in raw["holdout_windows"])
    raw["ccrs_cities"] = tuple(raw["ccrs_cities"])
    for key in ("latitude", "longitude"):
        low, high = raw[key]
        raw[key] = (float(low), float(high))
    raw["agency_reassignments"] = tuple(
        Reassignment(
            filed_as=str(rule["filed_as"]),
            agency=str(rule["agency"]),
            beat_prefix=None if rule.get("beat_prefix") is None else str(rule["beat_prefix"]),
            city=None if rule.get("city") is None else str(rule["city"]),
            from_year=rule.get("from_year"),
        )
        for rule in raw.get("agency_reassignments", ())
    )
    raw["municipality_aliases"] = {
        str(k).upper(): str(v).upper() for k, v in raw.get("municipality_aliases", {}).items()
    }
    for key in ("area_file", "city_limit_file", "area_points_file", "streets_file"):
        if raw.get(key) is not None:
            raw[key] = (Path(path).parent / raw[key]).resolve()
            if not raw[key].exists():
                raise ValueError(f"{key} not found: {raw[key]}")
    raw["area_schools"] = tuple(
        (str(entry["school"]), str(entry["district"])) for entry in raw.get("area_schools", ())
    )
    raw["area_points"] = tuple((float(lon), float(lat)) for lon, lat in raw.get("area_points", ()))
    raw["synthetic"] = raw.get("synthetic", False)
    if raw.get("summer_break") is None:
        raw.pop("summer_break", None)
    config = Config(**raw)
    system = CRS.from_user_input(config.crs)
    units = {axis.unit_name for axis in system.axis_info}
    if not system.is_projected or units != {"metre"}:
        raise ValueError(
            f"crs must be a projected coordinate system in metres; {config.crs} is "
            f"{'projected' if system.is_projected else 'not projected'}, in "
            f"{', '.join(sorted(units))}. Every distance rule here is in metres."
        )
    has_points = bool(config.area_schools or config.area_points or config.area_points_file)
    if has_points != (config.area_buffer_m is not None):
        raise ValueError("area_buffer_m goes with area_schools, area_points or area_points_file")
    if config.crash_source not in CRASH_SOURCES:
        raise ValueError(
            f"crash_source must be {CRASH_SOURCES[0]!r}, not {config.crash_source!r}. "
            "Building the tables from CCRS alone is not supported yet: the merge "
            "step needs a TIMS export."
        )
    for train_to, test_from, test_to in config.holdout_windows:
        ordered = config.first_year <= train_to < test_from
        if not ordered or (test_to is not None and test_to < test_from):
            raise ValueError(
                f"{path}: holdout_windows: hold-out window {(train_to, test_from, test_to)} "
                f"is out of order (first_year is {config.first_year})"
            )
    return config
