"""California Crash Reporting System (CCRS) crash, party and injured-person
records for the configured cities, from the state open-data portal.

CCRS (data.ca.gov dataset ``ccrs``) is the CHP database that replaced SWITRS
and feeds TIMS.  Unlike a TIMS export it includes property-damage-only crashes
and is updated monthly.  Each year is a separate CKAN datastore resource
(Crashes_YYYY, Parties_YYYY, InjuredWitnessPassengers_YYYY); the statewide
files are about 200 MB each, so this module queries the datastore SQL API for
the configured county and cities and for the parties and injured persons of
those crashes.  Results are paged by ``_id`` because the API returns at most
32,000 rows per call.  A file not loaded into the datastore is streamed in
full and filtered instead: the crash file by county and city, the others by
the Collision Ids of that year's selected crashes.

Written to the output folder: <Table>_<year>.csv (source columns unchanged, as
text) and ccrs_manifest.json (resource ids, last-modified stamps, filters and
row counts).  A year is downloaded again only when its resource's
last-modified stamp changes, or with ``overwrite``.  Duplicate handling is in
``crashes.merge``.  These are individual police records: keep the folder out
of version control.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from bike_safety_ca.config import Config
from bike_safety_ca.io import atomic_write_json, atomic_write_text

API = "https://data.ca.gov/api/3/action"
DATASET = "ccrs"
TABLES = ("Crashes", "Parties", "InjuredWitnessPassengers")
PAGE = 20_000
TIMEOUT = 300

log = logging.getLogger(__name__)


@retry(stop=stop_after_attempt(5), wait=wait_exponential(min=2, max=60), reraise=True)
def _get(client: httpx.Client, action: str, **params: Any) -> Any:
    response = client.get(f"{API}/{action}", params=params)
    response.raise_for_status()
    body = response.json()
    if not body.get("success"):
        raise RuntimeError(f"{action} failed: {body.get('error')}")
    return body["result"]


def resources(client: httpx.Client) -> dict[tuple[str, int], dict[str, Any]]:
    """Map (table, year) to the CKAN resource record for every yearly CCRS file."""
    found = {}
    for resource in _get(client, "package_show", id=DATASET)["resources"]:
        table, _, year = resource["name"].partition("_")
        if table in TABLES and year.isdigit():
            found[(table, int(year))] = resource
    return found


def _quoted(city: str) -> str:
    return "'" + city.replace("'", "''") + "'"


def crash_filter(crash_resource: str, county_code: int, cities: Sequence[str]) -> str:
    """SQL for the Collision Ids of one year's crashes in the county and cities."""
    names = ", ".join(_quoted(city) for city in cities)
    return (
        f'SELECT "Collision Id" FROM "{crash_resource}" '
        f'WHERE "County Code" = {int(county_code)} AND "City Name" IN ({names})'
    )


def _where(table: str, crash_ids: str) -> str:
    key = '"Collision Id"' if table == "Crashes" else '"CollisionId"'
    return f"{key} IN ({crash_ids})"


def fetch_table(client: httpx.Client, resource: str, where: str) -> list[dict[str, Any]]:
    """Page through a datastore resource by _id so no row is skipped or repeated."""
    rows: list[dict[str, Any]] = []
    last_id = 0
    while True:
        sql = (
            f'SELECT * FROM "{resource}" WHERE {where} AND "_id" > {last_id} '
            f'ORDER BY "_id" LIMIT {PAGE}'
        )
        page = _get(client, "datastore_search_sql", sql=sql)["records"]
        rows.extend(page)
        if len(page) < PAGE:
            return rows
        last_id = int(page[-1]["_id"])


def stream_csv(
    client: httpx.Client, url: str, wanted: Callable[[dict[str, Any]], bool]
) -> list[dict[str, Any]]:
    """Fallback for files not loaded into the datastore: stream the CSV and filter."""
    rows: list[dict[str, Any]] = []
    with client.stream("GET", url, follow_redirects=True) as response:
        response.raise_for_status()
        lines = (line.lstrip("\ufeff") for line in response.iter_lines())
        for row in csv.DictReader(lines):
            if wanted(row):
                rows.append(row)
    return rows


def in_cities(county_code: int, cities: Sequence[str]) -> Callable[[dict[str, Any]], bool]:
    """The crash-file test that ``crash_filter`` makes in SQL, for a streamed row."""
    names = {city.strip().upper() for city in cities}

    def wanted(row: dict[str, Any]) -> bool:
        county = str(row.get("County Code", "")).strip()
        same_county = county.isdigit() and int(county) == int(county_code)
        return same_county and str(row.get("City Name", "")).strip().upper() in names

    return wanted


def with_ids(key: str, keep: set[str]) -> Callable[[dict[str, Any]], bool]:
    return lambda row: str(row.get(key, "")).strip() in keep


def _to_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _year_ids(
    client: httpx.Client, crash_resource: dict[str, Any], crash_ids: str, config: Config, out: Path
) -> set[str]:
    """Collision Ids of one year's selected crashes, for filtering a streamed file."""
    saved = out / f"{crash_resource['name']}.csv"
    if saved.exists():  # written a moment ago, or kept from an earlier run
        with saved.open(newline="") as handle:
            return {str(row["Collision Id"]).strip() for row in csv.DictReader(handle)}
    if crash_resource.get("datastore_active"):
        where = _where("Crashes", crash_ids)
        return {
            str(row["Collision Id"]) for row in fetch_table(client, crash_resource["id"], where)
        }
    chosen = in_cities(config.ccrs_county_code, config.ccrs_cities)
    return {
        str(row["Collision Id"]).strip()
        for row in stream_csv(client, crash_resource["url"], chosen)
    }


def download(config: Config, out: Path, overwrite: bool = False) -> None:
    """Fetch every published year for the config's county and cities into ``out``."""
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "ccrs_manifest.json"
    previous: dict[str, Any] = {}
    wanted = {"County Code": config.ccrs_county_code, "City Name": list(config.ccrs_cities)}
    if manifest_path.exists():
        saved = json.loads(manifest_path.read_text())
        had = {key: saved.get("filter", {}).get(key) for key in wanted}
        if had == wanted:
            previous = saved.get("files", {})
        elif not overwrite:
            raise ValueError(
                f"{out} holds CCRS files fetched for {had}, not {wanted}. "
                "Use another folder for this city, or pass --overwrite to replace them."
            )
    files: dict[str, Any] = {}

    def record(complete: bool) -> None:
        # Until the end the list keeps the saved copies not yet looked at.
        listed = files if complete else previous | files
        atomic_write_json(
            manifest_path,
            {
                "dataset": f"https://data.ca.gov/dataset/{DATASET}",
                "filter": {
                    **wanted,
                    "parties_and_injured": "CollisionId of the filtered crashes in the same year",
                },
                "files": listed,
                "complete": complete,
            },
        )

    with httpx.Client(timeout=TIMEOUT, headers={"User-Agent": "bike-safety-ca/0.1"}) as client:
        found = resources(client)
        years = sorted({year for table, year in found if table == "Crashes"})
        for year in years:
            crash_ids = crash_filter(
                found[("Crashes", year)]["id"], config.ccrs_county_code, config.ccrs_cities
            )
            crash_resource = found[("Crashes", year)]
            year_ids: set[str] | None = None  # this year's Collision Ids, fetched if needed
            for table in TABLES:
                resource = found.get((table, year))
                if resource is None:
                    log.warning("CCRS %s_%s not published", table, year)
                    continue
                name = f"{table}_{year}.csv"
                stamp = resource.get("last_modified") or resource.get("metadata_modified")
                # Parties and injured people are chosen by the year's crashes, so a
                # changed crash file makes their saved copies stale too.
                crash_stamp = crash_resource.get("last_modified") or crash_resource.get(
                    "metadata_modified"
                )
                prior = previous.get(name, {})
                if (
                    not overwrite
                    and (out / name).exists()
                    and prior.get("resource_last_modified") == stamp
                    # A copy saved before this was recorded is fetched again, once.
                    and prior.get("crash_resource_last_modified") == crash_stamp
                ):
                    files[name] = prior
                    continue
                # Before anything is fetched: a failure then leaves a list that
                # says the download did not finish, whatever was reused above.
                record(complete=False)
                # The SQL filter reads the crash table, so it works only when both
                # this table and the year's crash table are in the datastore.
                if resource.get("datastore_active") and crash_resource.get("datastore_active"):
                    rows = fetch_table(client, resource["id"], _where(table, crash_ids))
                elif table == "Crashes":
                    rows = stream_csv(
                        client,
                        resource["url"],
                        in_cities(config.ccrs_county_code, config.ccrs_cities),
                    )
                else:
                    if year_ids is None:
                        year_ids = _year_ids(client, crash_resource, crash_ids, config, out)
                    rows = stream_csv(client, resource["url"], with_ids("CollisionId", year_ids))
                atomic_write_text(out / name, _to_csv(rows))
                files[name] = {
                    "resource_id": resource["id"],
                    "resource_last_modified": stamp,
                    "crash_resource_last_modified": crash_stamp,
                    "rows": len(rows),
                    "retrieved_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
                }
                log.info("CCRS %s: %d rows", name, len(rows))
                # Recorded file by file: an interrupted download then leaves the
                # list of what it wrote, and the request it was made for.
                record(complete=False)
    record(complete=True)
