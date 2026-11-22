"""City and county outlines from the U.S. Census Bureau's cartographic boundary files.

These are public generalised outlines (1:500,000) and need no key.  The zip
files are saved unchanged and read in place.
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

VINTAGE = 2023
CALIFORNIA = "06"  # state FIPS code
BASE = "https://www2.census.gov/geo/tiger/GENZ{year}/shp/{name}.zip"

log = logging.getLogger(__name__)


def names(year: int = VINTAGE) -> dict[str, str]:
    """File stems for California's places and the nation's counties."""
    return {"places": f"cb_{year}_{CALIFORNIA}_place_500k", "counties": f"cb_{year}_us_county_500k"}


def _holds_shapefile(path: Path) -> bool:
    if not zipfile.is_zipfile(path):
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            return any(name.lower().endswith(".shp") for name in archive.namelist())
    except zipfile.BadZipFile:
        return False


@retry(stop=stop_after_attempt(4), wait=wait_exponential(min=2, max=60), reraise=True)
def _fetch(url: str, dest: Path) -> None:
    staged = dest.with_name(dest.name + ".part")
    try:
        with httpx.stream(
            "GET",
            url,
            timeout=120,
            follow_redirects=True,
            headers={"User-Agent": "bike-safety-ca/0.1"},
        ) as response:
            response.raise_for_status()
            with staged.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
        if not _holds_shapefile(staged):
            raise ValueError(
                f"the reply from {url} is not a zip file holding a shapefile; "
                f"{dest.name} was not saved"
            )
        staged.replace(dest)
    except BaseException:
        staged.unlink(missing_ok=True)  # a download cut off part-way leaves nothing behind
        raise


def download(out: Path, year: int = VINTAGE, overwrite: bool = False) -> dict[str, Path]:
    """Fetch the place and county boundary zips into ``out``; returns their paths."""
    out.mkdir(parents=True, exist_ok=True)
    paths = {}
    for kind, name in names(year).items():
        dest = out / f"{name}.zip"
        if overwrite or not dest.exists():
            _fetch(BASE.format(year=year, name=name), dest)
            log.info("saved %s", dest)
        paths[kind] = dest
    return paths
