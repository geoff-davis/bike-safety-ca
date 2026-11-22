"""The outline of the area the crash tables cover, from the config's city list.

The area is the listed cities and towns joined together.  If the list includes
"Unincorporated", county land outside every city is added where it lies inside
the hull drawn around the listed cities: the pockets between and beside them,
not the whole unincorporated county.  Supply your own outline instead if that
does not match where your crashes are.
"""

from __future__ import annotations

from difflib import get_close_matches
from pathlib import Path

import geopandas as gpd
import pandas as pd

from bike_safety_ca.config import Config
from bike_safety_ca.download import schools
from bike_safety_ca.download.census import CALIFORNIA
from bike_safety_ca.io import CRS_WGS84, crs_tag, read_shapes

UNINCORPORATED = "UNINCORPORATED"
CDP = "57"  # LSAD code of a census-designated place, which is not incorporated


def incorporated(places: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """California's cities and towns from the Census places, under the names crash reports use.

    The Census gives a few cities a formal name with the everyday one in
    brackets, such as "San Buenaventura (Ventura)".  Those get the everyday
    name in ``NAME``; ``formal`` and ``census_name`` keep the other two forms,
    which are each city's own name where there are no brackets.
    """
    cities = places[places.STATEFP.eq(CALIFORNIA) & places.LSAD.ne(CDP)].copy()
    parts = cities.NAME.str.extract(r"^(?P<formal>.+?)\s*\((?P<everyday>[^()]+)\)\s*$")
    cities["census_name"] = cities.NAME
    cities["formal"] = parts.formal.fillna(cities.NAME)
    cities["NAME"] = parts.everyday.fillna(cities.NAME)
    return cities


def _named(cities: gpd.GeoDataFrame, wanted: list[str]) -> gpd.GeoDataFrame:
    """The rows of ``incorporated`` that ``wanted`` names, by any of a city's three names."""
    names = [cities[column].str.upper() for column in ("NAME", "formal", "census_name")]
    known = set().union(*names)
    missing = sorted(set(wanted) - known)
    if missing:
        hints = [
            f"{name} (closest: {', '.join(close)})" if close else name
            for name in missing
            for close in [get_close_matches(name, sorted(known), n=3, cutoff=0.6)]
        ]
        raise ValueError(f"no Census place named: {'; '.join(hints)}")
    return cities[names[0].isin(wanted) | names[1].isin(wanted) | names[2].isin(wanted)]


def outlines(
    places: gpd.GeoDataFrame, counties: gpd.GeoDataFrame, config: Config
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """(area, city limit) as one-row frames in the config's coordinate system.

    ``places`` and ``counties`` are the Census boundary layers, with ``NAME``,
    ``LSAD`` and ``STATEFP`` columns.
    """
    places = incorporated(places).to_crs(config.crs)
    wanted = [c.upper() for c in config.ccrs_cities]
    cities = _named(places, [c for c in wanted if c != UNINCORPORATED])
    shape = cities.union_all()
    if UNINCORPORATED in wanted:
        county = counties[
            counties.STATEFP.eq(CALIFORNIA) & counties.NAME.str.upper().eq(config.county.upper())
        ].to_crs(config.crs)
        if len(county) != 1:
            raise ValueError(f"no Census county named {config.county}")
        open_land = county.union_all().difference(places.union_all())
        shape = shape.union(open_land.intersection(shape.convex_hull))
    area = gpd.GeoDataFrame({"name": ["area"]}, geometry=[shape], crs=config.crs)
    limit = _named(places, [config.city.upper()]).dissolve()[["geometry"]].assign(name=config.city)
    return area, limit


def paths(out: Path, crs: str) -> dict[str, Path]:
    return {kind: out / f"{kind}_{crs_tag(crs)}.parquet" for kind in ("area", "city_limit")}


def around_points(
    points: pd.DataFrame, buffer_m: float, limit: gpd.GeoDataFrame, crs: str
) -> gpd.GeoDataFrame:
    """Circles of ``buffer_m`` metres around ``points`` (longitude, latitude), joined with ``limit``."""
    spots = gpd.GeoSeries(
        gpd.points_from_xy(points.longitude, points.latitude), crs=CRS_WGS84
    ).to_crs(crs)
    shape = spots.buffer(buffer_m).union_all().union(limit.to_crs(crs).union_all())
    return gpd.GeoDataFrame({"name": ["area"]}, geometry=[shape], crs=crs)


def centres(config: Config, school_directory: Path | None = None) -> pd.DataFrame:
    """The points the config asks for circles around (longitude, latitude)."""
    found = [pd.DataFrame(list(config.area_points), columns=["longitude", "latitude"])]
    if config.area_schools:
        if school_directory is None:
            raise ValueError("area_schools needs the state school directory")
        found.append(schools.locate(school_directory, config.area_schools))
    if config.area_points_file is not None:
        found.append(pd.read_csv(config.area_points_file))
    return pd.concat([f[["longitude", "latitude"]] for f in found], ignore_index=True)


def build(
    sources: dict[str, Path],
    out: Path,
    config: Config,
    city_limit: Path | None = None,
    school_directory: Path | None = None,
) -> dict[str, Path]:
    """Write the area and city-limit outlines.

    They come from the Census zips in ``sources`` unless the config says
    otherwise: ``city_limit`` (the city's own layer, already downloaded)
    replaces the Census city limit, and ``area_buffer_m`` makes the area
    circles around the config's schools and points, joined with the city limit.
    """
    area, limit = outlines(
        gpd.read_file(sources["places"]), gpd.read_file(sources["counties"]), config
    )
    if city_limit is not None:
        limit = read_shapes(city_limit).to_crs(config.crs).dissolve()[["geometry"]]
        limit = limit.assign(name=config.city)
    if config.area_buffer_m is not None:
        points = centres(config, school_directory)
        area = around_points(points, config.area_buffer_m, limit, config.crs)
    out.mkdir(parents=True, exist_ok=True)
    written = paths(out, config.crs)
    area.to_parquet(written["area"], index=False)
    limit.to_parquet(written["city_limit"], index=False)
    return written


def chosen(config: Config, out: Path, area: Path | None = None) -> dict[str, Path | None]:
    """The outlines to use: the caller's, else the config's, else the built ones.

    With the caller's own area the built city limit is not used, since it may
    not belong to that area.
    """
    built = paths(out, config.crs)
    limit = config.city_limit_file or (None if area else built["city_limit"])
    return {"area": area or config.area_file or built["area"], "city_limit": limit}
