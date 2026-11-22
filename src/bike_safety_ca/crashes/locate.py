"""Place crashes that have no coordinates from the intersection the report names.

Police reports give a primary road, a cross street and often a distance and
compass direction from the corner.  These functions find that corner on a
road-centerline layer and move along the named road by the reported offset.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point
from shapely.ops import nearest_points, unary_union

MAX_INTERSECTION_CENTERLINE_GAP_M = 15.0


NO_DIRECTION_STATUS = "recovered_at_intersection_offset_direction_missing"


_COMPASS = r"NORTH|SOUTH|EAST|WEST|N|S|E|W"
_ROAD_TYPE = (
    r"AVENUE|AVE|AV|ROAD|RD|STREET|ST|DRIVE|DR|COURT|CT|WAY|WY|"
    r"LANE|LN|BOULEVARD|BLVD|TERRACE|TER|PLACE|PL|CIRCLE|CIR|"
    r"PARKWAY|PKWY|EXPRESSWAY|EXPWY|EXPY"
)
# A leading ST before a name is Saint ("ST FRANCIS DR"), not Street; before a
# street type, a direction or a route it is not ("ST RT 9", "N ST W").
_SAINT = re.compile(
    rf"^\s*((?:{_COMPASS})\.?\s+)?ST\.?\s+"
    rf"(?!(?:{_ROAD_TYPE}|{_COMPASS}|RT|RTE|ROUTE|HWY|HIGHWAY)\b)(?=[A-Z])"
)


def _normalized_road_name(value: Any) -> str:
    """Road name for matching: upper case, without directions or street types.

    A name made only of direction and type words before its type ("South
    Street", "N St", "West Lane", "Court Street") keeps the word that is its
    name ("SOUTH", "N", "WEST", "COURT"), so that such a street still has one.
    """
    text = str(value or "").upper().replace("&", " AND ")
    text = re.sub(r"\([^)]*\)", " ", text)
    text = _SAINT.sub(r"\1SAINT ", text)
    plain = re.sub(rf"\b({_COMPASS})[ /-]*B(?:OUND)?\b", " ", text)
    plain = re.sub(rf"\b({_COMPASS})\b", " ", plain)
    plain = re.sub(rf"\b({_ROAD_TYPE})\b", " ", plain)
    name = " ".join(re.sub(r"[^A-Z0-9]+", " ", plain).split())
    if name:
        return name
    # "S/B", "southbound" and a closing "S B" are directions of travel; the B
    # of "West B Street" is the street.
    text = re.sub(rf"\b({_COMPASS})(/B|[ /-]*BOUND|[ -]*B\s*$)\b", " ", text)
    words = re.sub(r"[^A-Z0-9]+", " ", text).split()
    if len(words) < 2 or not re.fullmatch(_ROAD_TYPE, words[-1]):
        return ""
    words.pop()
    while len(words) > 1 and re.fullmatch(_COMPASS, words[0]):  # "N Court St" is Court Street
        words.pop(0)
    return " ".join(words)


normalized_road_name = _normalized_road_name


def _point_parts(geometry: Any) -> list[Point]:
    if geometry is None or geometry.is_empty:
        return []
    if geometry.geom_type == "Point":
        return [geometry]
    if geometry.geom_type in {"MultiPoint", "GeometryCollection"}:
        return [point for part in geometry.geoms for point in _point_parts(part)]
    return []


def _intersection_location(
    primary: gpd.GeoDataFrame,
    secondary: gpd.GeoDataFrame,
    *,
    maximum_gap_m: float,
    cluster_m: float = 0.0,
) -> tuple[Point | None, str, float | None]:
    if primary.empty or secondary.empty:
        return None, "road_name_not_in_retained_centerlines", None
    primary_geometry = unary_union(primary.geometry.to_list())
    secondary_geometry = unary_union(secondary.geometry.to_list())
    points = _point_parts(primary_geometry.intersection(secondary_geometry))
    if len(points) == 1:
        return points[0], "recovered_unique_centerline_intersection", 0.0
    # Divided roads cross a side street once per carriageway: one intersection.
    if len(points) > 1 and cluster_m > 0:
        if max(a.distance(b) for a in points for b in points) <= cluster_m:
            center = Point(np.mean([p.x for p in points]), np.mean([p.y for p in points]))
            return center, "recovered_divided_road_intersection", 0.0
    if len(points) > 1:
        return None, "ambiguous_multiple_intersections", 0.0
    gap = float(primary_geometry.distance(secondary_geometry))
    if gap > maximum_gap_m:
        return None, "centerlines_do_not_meet_within_tolerance", gap
    first, second = nearest_points(primary_geometry, secondary_geometry)
    return (
        Point((first.x + second.x) / 2, (first.y + second.y) / 2),
        "recovered_unique_near_centerline_intersection",
        gap,
    )


FEET_TO_M = 0.3048
MAX_REPORTED_OFFSET_M = 152.4  # 500 ft; farther offsets are left unlocated
DIVIDED_ROAD_CLUSTER_M = 60.0
_DIRECTION_VECTORS = {"N": (0.0, 1.0), "S": (0.0, -1.0), "E": (1.0, 0.0), "W": (-1.0, 0.0)}


def prepare_centerlines(centerlines: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Add the normalized road name and municipality used to match crash reports.

    The layer needs columns STNAME (street name), FULLNAME (used where STNAME
    is missing) and MUNICIPALI (municipality).
    """
    centerlines = centerlines.copy()
    centerlines["normalized_road_name"] = centerlines.STNAME.fillna(centerlines.FULLNAME).map(
        _normalized_road_name
    )
    centerlines["normalized_municipality"] = (
        centerlines.MUNICIPALI.fillna("").astype(str).str.upper().str.strip()
    )
    return centerlines


UNINCORPORATED = "UNINCORPORATED"


def streets_as_centerlines(streets: gpd.GeoDataFrame, places: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """A centerline layer made from a street table and city outlines.

    ``streets`` needs a ``name`` column (the OpenStreetMap street table);
    ``places`` needs ``NAME`` (the incorporated cities' outlines).  Each named
    street is cut at the city limits: the part inside a city carries that
    city's name and the part in no city is "UNINCORPORATED".  The result has
    the STNAME, FULLNAME and MUNICIPALI columns ``prepare_centerlines`` reads.

    Streets are matched as drawn lines, so two that cross on a bridge without
    joining look like an intersection.
    """
    named = streets.loc[
        streets.name.fillna("").astype(str).str.strip().ne(""), ["name", "geometry"]
    ]
    assert named.crs is not None
    cities = places.to_crs(named.crs)[["NAME", "geometry"]]
    inside = gpd.overlay(named, cities, how="intersection", keep_geom_type=True)
    outside = gpd.overlay(named, cities, how="difference", keep_geom_type=True)
    parts = pd.concat([inside, outside.assign(NAME=UNINCORPORATED)], ignore_index=True)
    parts = parts[~parts.geometry.is_empty]
    return gpd.GeoDataFrame(
        {
            "STNAME": parts.name.to_numpy(),
            "FULLNAME": parts.name.to_numpy(),
            "MUNICIPALI": parts.NAME.str.upper().to_numpy(),
        },
        geometry=parts.geometry.to_numpy(),
        crs=named.crs,
    )


def _city_lines(
    by_city: dict[str, gpd.GeoDataFrame], aliases: Mapping[str, str], value: Any
) -> tuple[str, gpd.GeoDataFrame | None]:
    """The centerlines of a report's city: under its alias, else its own name."""
    raw = str(value or "").upper().strip()
    for name in (aliases.get(raw, raw), raw):
        if name in by_city:
            return name, by_city[name]
    return raw, None


def _by_city(centerlines: gpd.GeoDataFrame) -> dict[str, gpd.GeoDataFrame]:
    return {
        str(name): gpd.GeoDataFrame(group, crs=centerlines.crs)
        for name, group in centerlines.groupby("normalized_municipality")
    }


def distance_to_named_roads(
    crashes: gpd.GeoDataFrame,
    centerlines: gpd.GeoDataFrame,
    municipality_aliases: Mapping[str, str] | None = None,
) -> pd.Series:
    """Metres from each crash's point to the nearest street its report names.

    Looks in the report's own city, at every stretch of road carrying either
    name.  Missing where the crash has no point or neither name is found.
    ``crashes`` must be in the centerlines' CRS.
    """
    by_city = _by_city(prepare_centerlines(centerlines))
    roads: dict[tuple[str, str, str], Any] = {}
    result: dict[Any, float] = {}
    for index, row in crashes.iterrows():
        name, city = _city_lines(by_city, municipality_aliases or {}, row.CITY)
        wanted = {_report_road_name(row.PRIMARY_RD), _report_road_name(row.SECONDARY_RD)} - {""}
        if city is None or not wanted or row.geometry is None or row.geometry.is_empty:
            continue
        key = (name, min(wanted), max(wanted))
        if key not in roads:
            lines = city[city.normalized_road_name.isin(wanted)]
            roads[key] = None if lines.empty else unary_union(lines.geometry.to_list())
        if roads[key] is not None:
            result[index] = float(row.geometry.distance(roads[key]))
    return pd.Series(result, dtype=float).reindex(crashes.index)


def _report_road_name(value: Any) -> str:
    """Normalized road name with a leading house number ("123 N MAIN ST") removed."""
    value = "" if value is None or value is pd.NA or value != value else value  # no name
    text = re.sub(r"^\s*\d+\s+(?=[A-Za-z])", "", str(value or "")).upper()
    # "THE SOUTH CURBLINE OF ELM AVENUE" names Elm Avenue.
    text = re.sub(r"^.*\bCURB\s*LINE\s+OF\b", " ", text)
    text = re.sub(r"\b(?:ST\.?\s+)?(?:SR|RT|RTE)[ -]*82\b", "EL CAMINO REAL", text)
    # Abbreviations the shared normalizer does not strip (FOOTHILL EXPR, EL MONTE BL).
    text = re.sub(r"\b(?:EXPR|EXP|EX)\b\.?", " EXPRESSWAY ", text)
    text = re.sub(r"\bBL\b\.?", " BOULEVARD ", text)
    return _normalized_road_name(text)


def _offset_location(
    corner: Point,
    roads: list[Any],
    offset_m: float,
    direction: str,
) -> tuple[Point | None, str]:
    """Move from the intersection along whichever named road runs in the reported direction."""
    dx, dy = _DIRECTION_VECTORS[direction]
    target = Point(corner.x + dx * offset_m, corner.y + dy * offset_m)
    best: tuple[float, Point] | None = None
    for road in roads:
        snapped = nearest_points(road, target)[0]
        miss = snapped.distance(target)
        if best is None or miss < best[0]:
            best = (miss, snapped)
    if best is None or best[0] > max(0.5 * offset_m, 15.0):
        return None, "reported_direction_not_along_named_roads"
    return best[1], "recovered_offset_from_centerline_intersection"


RELAXED_GAP_M = 60.0  # side streets stop short of an expressway's centerline
RELAXED_OFFSET_M = 304.8  # 1,000 ft
_MIN_DIRECTION_COSINE = 0.5  # the road must run within 60 degrees of the reported direction


def _near_miss_location(
    primary: gpd.GeoDataFrame, secondary: gpd.GeoDataFrame, maximum_gap_m: float
) -> tuple[Point | None, str, float | None]:
    """Where the primary road passes closest to a cross street it does not quite meet."""
    if primary.empty or secondary.empty:
        return None, "road_name_not_in_retained_centerlines", None
    primary_geometry = unary_union(primary.geometry.to_list())
    secondary_geometry = unary_union(secondary.geometry.to_list())
    gap = float(primary_geometry.distance(secondary_geometry))
    if gap > maximum_gap_m:
        return None, "centerlines_do_not_meet_within_tolerance", gap
    return (
        nearest_points(primary_geometry, secondary_geometry)[0],
        "recovered_near_miss_centerlines",
        gap,
    )


def _offset_along_road(
    corner: Point, roads: list[Any], offset_m: float, direction: str
) -> tuple[Point | None, str]:
    """The point `offset_m` from the corner on the named road that best runs `direction`.

    Unlike `_offset_location` this does not need the road to run due north, south,
    east or west, so it works on a street grid at an angle to the compass."""
    dx, dy = _DIRECTION_VECTORS[direction]
    ring = corner.buffer(offset_m, quad_segs=64).exterior
    best: tuple[float, Point] | None = None
    for road in roads:
        for point in _point_parts(road.intersection(ring)):
            cosine = ((point.x - corner.x) * dx + (point.y - corner.y) * dy) / offset_m
            if best is None or cosine > best[0]:
                best = (cosine, point)
    if best is None or best[0] < _MIN_DIRECTION_COSINE:
        return None, "reported_direction_not_along_named_roads"
    return best[1], "recovered_offset_along_road"


def locate_reported_intersections(
    crashes: pd.DataFrame,
    centerlines: gpd.GeoDataFrame,
    *,
    maximum_gap_m: float = MAX_INTERSECTION_CENTERLINE_GAP_M,
    maximum_offset_m: float = MAX_REPORTED_OFFSET_M,
    relaxed: bool = False,
    municipality_aliases: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """Approximate points for crashes reported relative to a named intersection.

    Roads are matched by normalized name within the crash's own municipality only.
    The intersection must be unique there (as in the overlay recovery). A crash
    reported a distance and direction (N/S/E/W) from it is moved that far along
    the named road that runs in that direction; with no distance, or a distance
    but no direction, it is placed at the intersection. Offsets beyond `maximum_offset_m`
    are not placed. `crashes` needs PRIMARY_RD, SECONDARY_RD, CITY, DISTANCE (feet)
    and DIRECTION; the result is indexed like it, in the centerlines' CRS.

    `relaxed` is a second, more tolerant pass for crashes the first could not place.
    It accepts a cross street that stops up to `RELAXED_GAP_M` short of the primary
    road (placing the crash on the primary road), offsets up to `RELAXED_OFFSET_M`,
    and roads that run at an angle to the reported compass direction.

    `municipality_aliases` maps a crash report's city name to the municipality
    name the centerline layer uses, where they differ.
    """
    aliases = municipality_aliases or {}
    if relaxed:
        maximum_offset_m = max(maximum_offset_m, RELAXED_OFFSET_M)
    centerlines = prepare_centerlines(centerlines)
    by_city = _by_city(centerlines)
    rows: list[dict[str, Any]] = []
    # Many reports name the same corner: work each one out once.
    corners: dict[tuple[str, str, str], tuple[Point | None, str, float | None]] = {}
    for index, row in crashes.iterrows():
        primary = _report_road_name(row.PRIMARY_RD)
        secondary = _report_road_name(row.SECONDARY_RD)
        city_name, city = _city_lines(by_city, aliases, row.CITY)
        distance_ft = pd.to_numeric(pd.Series([row.DISTANCE]), errors="coerce").iloc[0]
        offset_m = 0.0 if pd.isna(distance_ft) else float(distance_ft) * FEET_TO_M
        direction = "" if pd.isna(row.DIRECTION) else str(row.DIRECTION).strip().upper()[:1]
        location: Point | None = None
        gap: float | None = None
        if not primary or not secondary:
            status = "road_names_missing"
        elif primary == secondary:
            status = "same_normalized_road_name_is_ambiguous"
        elif city is None:
            status = "municipality_not_in_retained_centerlines"
        elif offset_m > maximum_offset_m:
            status = "reported_offset_too_far"
        else:
            primary_lines = city[city.normalized_road_name.eq(primary)]
            secondary_lines = city[city.normalized_road_name.eq(secondary)]
            corner = (city_name, primary, secondary)
            if corner not in corners:
                found = _intersection_location(
                    primary_lines,
                    secondary_lines,
                    maximum_gap_m=maximum_gap_m,
                    cluster_m=DIVIDED_ROAD_CLUSTER_M,
                )
                if found[0] is None and relaxed and found[1].startswith("centerlines_do_not_meet"):
                    found = _near_miss_location(primary_lines, secondary_lines, RELAXED_GAP_M)
                corners[corner] = found
            location, status, gap = corners[corner]
            if location is not None and offset_m > 0 and direction not in _DIRECTION_VECTORS:
                # The report gives a distance but not which way: the corner
                # itself is the best that can be said, at most the offset out.
                status = NO_DIRECTION_STATUS
            elif location is not None and offset_m > 0:
                location, status = (_offset_along_road if relaxed else _offset_location)(
                    location,
                    [
                        unary_union(primary_lines.geometry.to_list()),
                        unary_union(secondary_lines.geometry.to_list()),
                    ],
                    offset_m,
                    direction,
                )
        rows.append(
            {
                "index": index,
                "geometry": location,
                "recovery_status": status,
                "intersection_match_gap_m": gap,
                "reported_offset_m": offset_m,
            }
        )
    result = pd.DataFrame(
        rows,
        columns=[
            "index",
            "geometry",
            "recovery_status",
            "intersection_match_gap_m",
            "reported_offset_m",
        ],
    )
    return gpd.GeoDataFrame(result.set_index("index"), geometry="geometry", crs=centerlines.crs)
