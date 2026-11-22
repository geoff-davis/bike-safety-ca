"""The state's public school directory, used to place the schools a study area is built around.

The file stays in the git-ignored data folder.  The Department of Education's
copyright statement asks for permission before material from its website is
reproduced, so this repository names the schools and each user fetches the
directory themselves.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

from bike_safety_ca.io import atomic_write_text

log = logging.getLogger(__name__)

URL = "https://sd.cde.ca.gov/schooldirectory/report?rid=dl1&tp=txt"
PAGE = "https://www.cde.ca.gov/ds/si/ds/pubschls.asp"
NAME = "pubschls.txt"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30), reraise=True)
def _fetch() -> str:
    response = httpx.get(
        URL, timeout=180, follow_redirects=False, headers={"User-Agent": "bike-safety-ca/0.1"}
    )
    response.raise_for_status()
    response.encoding = "latin-1"
    if response.status_code != 200 or not response.text.startswith("CDSCode"):
        raise ValueError("the reply is not the school directory")
    return response.text


def download(dest: Path, overwrite: bool = False) -> Path:
    """Fetch the directory (about 7 MB, tab-delimited) into ``dest``.

    The site may turn away automated requests.  If it does, download "Public
    Schools and Districts (TXT)" from the page named in the error and save it
    as ``dest``.
    """
    if overwrite or not dest.exists():
        try:
            atomic_write_text(dest, _fetch(), encoding="latin-1")
        except (httpx.HTTPError, ValueError) as error:
            raise RuntimeError(
                f"could not fetch the school directory ({error}). Download "
                f'"Public Schools and Districts (TXT)" from {PAGE} and save it as {dest}'
            ) from error
        log.info("saved %s", dest)
    return dest


def locate(directory: Path, schools: tuple[tuple[str, str], ...]) -> pd.DataFrame:
    """Longitude and latitude of each (school, district) among the directory's active schools."""
    table = pd.read_csv(directory, sep="\t", dtype=str, encoding="latin-1")
    table = table[table.StatusType.eq("Active")]
    rows = []
    for school, district in schools:
        found = table[table.School.eq(school) & table.District.eq(district)]
        if len(found) != 1:
            raise ValueError(
                f"{len(found)} active schools named {school!r} in {district!r} in {directory}"
            )
        rows.append(
            {
                "school": school,
                "longitude": float(found.Longitude.iloc[0]),
                "latitude": float(found.Latitude.iloc[0]),
            }
        )
    return pd.DataFrame(rows, columns=["school", "longitude", "latitude"])
