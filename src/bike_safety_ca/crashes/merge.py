"""Merge CCRS crash records (``download.ccrs``) with the TIMS/SWITRS crash tables.

TIMS remains the primary source: every TIMS crash is kept with its own values,
and CCRS adds (a) crashes TIMS does not have, chiefly property-damage-only
crashes and months after the TIMS export, and (b) coordinates where TIMS has
none. ``tims.build`` must run first; its outputs are left unchanged.

Duplicate checks, in order (all counts go to crashes_merge_report.json):

1. CCRS internal. Rows marked IsDeleted are dropped. A Collision Id repeated
   across yearly files keeps its latest ModifiedDate. A report resubmitted under
   a new Collision Id (same agency and report number, crash dates within
   RESUBMISSION_MAX_DAYS) keeps the highest Report Version, then the latest
   ModifiedDate; the others are listed in ccrs_superseded.csv. Report numbers
   are not unique across agencies, so the agency is part of the key.
2. TIMS to CCRS. TIMS CASE_IDs of 8 digits starting with 8 or 9 are "8" or "9"
   plus the CCRS Collision Id (city police and CHP/Sheriff respectively), and
   are linked directly when the crash dates agree within a day. Where they
   do not (case_id_date_mismatch) the link is refused and both rows are
   kept. If the two also share a road name or lie within
   ATTRIBUTE_MAX_METRES (one shared name does not count against points over
   ATTRIBUTE_CONTRADICTION_METRES apart), a date was corrected in one
   source: the CCRS report gets possible_duplicate_of. One shared name
   with a point missing on either side is not enough. This needs exactly
   one TIMS row that fits the report and is not itself a duplicate (several
   may be different crashes), and that row must have a date, and a point
   unless the report has none; otherwise nothing is marked. Nothing is
   copied from the report to the TIMS row. With the id alone they stay two
   crashes. Each case is
   counted in the report. Older 7-digit
   SWITRS IDs are matched on the same agency and date, crash time within
   ATTRIBUTE_MAX_MINUTES, and a shared road name or coordinates within
   ATTRIBUTE_MAX_METRES. A candidate more than ATTRIBUTE_CONTRADICTION_METRES
   away loses to any nearer one. A TIMS crash with two equally good CCRS
   reports that differ, and TIMS crashes that differ but share one best CCRS
   report, are left unlinked (attributes_ambiguous).
   Two TIMS crashes linked to the same CCRS report (directly or through a
   superseded resubmission) are flagged as duplicate_of. Audit:
   ccrs_tims_links.csv.
3. Duplicate reports. The same crash reported by two agencies (for example CHP
   and a city) is flagged when crash dates match, times are within
   CROSS_AGENCY_MAX_MINUTES, and the locations agree (same road pair or within
   CROSS_AGENCY_MAX_METRES). Two reports from one agency with different report
   numbers are flagged under tighter limits (SAME_AGENCY_MAX_MINUTES,
   SAME_AGENCY_MAX_METRES) and only when both list the same parties (type,
   sex, age), because a chain-reaction crash is filed as separate reports.
   Coordinates decide location when both records have them; road names
   only otherwise (a shared freeway pair can be kilometres apart). The lower-priority record (CCRS-only before TIMS,
   no-injury before injury, CHP/Sheriff before city) gets possible_duplicate_of;
   nothing is dropped. Pairs: crashes_duplicate_reports.csv.

Outputs: crashes_merged_4326.parquet and crashes_merged_<local>.parquet,
parties_merged.parquet, victims_merged.parquet, bicycle_parties_merged.parquet,
ccrs_crashes.parquet (cleaned CCRS, one row per kept report), and the audit
files above. CCRS-only rows carry the TIMS column names for the fields used in
here (codes translated to TIMS codes); other TIMS columns are empty.
Filter with injury_crash to compare with TIMS, which holds injury crashes only,
and drop possible_duplicate_of for counts."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from bike_safety_ca.config import Config
from bike_safety_ca.crashes import ebike
from bike_safety_ca.crashes.locate import (
    NO_DIRECTION_STATUS,
    distance_to_named_roads,
    locate_reported_intersections,
    normalized_road_name,
)
from bike_safety_ca.crashes.tims import (
    agency_reporting_gaps,
    parse_collision_time,
    reporting_agency,
)
from bike_safety_ca.io import CRS_WGS84, write_dual, write_table

RESUBMISSION_MAX_DAYS = 60
ATTRIBUTE_MAX_MINUTES = 20
ATTRIBUTE_MAX_METRES = 150.0
ATTRIBUTE_CONTRADICTION_METRES = 1000.0  # one shared street name cannot outweigh this
FAR_PENALTY = ATTRIBUTE_MAX_MINUTES + 15  # more than time and name differences together
CROSS_AGENCY_MAX_MINUTES = 15
CROSS_AGENCY_MAX_METRES = 100.0
SAME_AGENCY_MAX_MINUTES = 2
SAME_AGENCY_MAX_METRES = 100.0

log = logging.getLogger(__name__)

PARTY_TYPE = {
    "Driver": "1",
    "Pedestrian": "2",
    "ParkedVehicle": "3",
    "Bicyclist": "4",
    "Other": "5",
}
VICTIM_ROLE = {"Driver": "1", "Passenger": "2", "Pedestrian": "3", "Bicyclist": "4", "Other": "5"}
# TIMS VICTIM_DEGREE_OF_INJURY codes, including the CCRS-era 5-7.
INJURY_DEGREE = {
    "Fatal": "1",
    "SevereInactive": "2",
    "OtherVisibleInactive": "3",
    "ComplaintOfPainInactive": "4",
    "SuspectSerious": "5",
    "SuspectMinor": "6",
    "PossibleInjury": "7",
}
# TIMS COLLISION_SEVERITY: 1 fatal, 2 serious, 3 minor/visible, 4 possible/pain, 0 none.
DEGREE_TO_SEVERITY = {"1": 1, "2": 2, "5": 2, "3": 3, "6": 3, "4": 4, "7": 4}


# Columns the merge reads from the party and injured-person files: an empty
# download still has to give tables with these columns.
PARTY_COLUMNS = [
    "PartyId",
    "CollisionId",
    "PartyNumber",
    "PartyType",
    "IsAtFault",
    "GenderCode",
    "StatedAge",
    "SobrietyDrugPhysicalCode1",
    "DirectionOfTravel",
    "MovementPrecCollCode",
    "Vehicle1TypeId",
    "Vehicle1Year",
    "Vehicle1Make",
    "Vehicle1Model",
    "RaceCode",
    "SpeedLimit",
]
INJURED_COLUMNS = [
    "InjuredWitPassId",
    "CollisionId",
    "PartyNumber",
    "IsWitnessOnly",
    "InjuredPersonType",
    "ExtentOfInjuryCode",
    "Gender",
    "StatedAge",
]


def manifest_files(root: Path, config: Config | None = None) -> set[str] | None:
    """Names of the files the last download wrote, or None when it left no list.

    A folder downloaded for other cities than the config's is refused: its
    files would be merged as if they were this city's.  With no list that
    cannot be checked, and a download that stopped part-way lacks its later
    years; both are warned about.
    """
    path = root / "ccrs_manifest.json"
    if not path.exists():
        log.warning(
            "%s has no ccrs_manifest.json: every CCRS file in it is used as it is, and "
            "which cities and years they hold is not checked. Run the download step to "
            "write one.",
            root,
        )
        return None
    manifest = json.loads(path.read_text())
    if config is not None:
        had = manifest.get("filter", {})
        wanted = {"County Code": config.ccrs_county_code, "City Name": list(config.ccrs_cities)}
        if {key: had.get(key) for key in wanted} != wanted:
            raise ValueError(
                f"{root} holds CCRS files fetched for {had.get('City Name')} in county "
                f"{had.get('County Code')}, not for this config. Download this city's "
                "files into their own folder."
            )
    if not manifest.get("complete", True):
        log.warning(
            "The CCRS download into %s did not finish: later years are missing. "
            "Run the download step again before relying on the merged tables.",
            root,
        )
    return set(manifest.get("files", {}))


def _read(
    table: str, root: Path, listed: set[str] | None = None, columns: list[str] | None = None
) -> pd.DataFrame:
    """Every yearly file of ``table``; only those in ``listed`` when a list is given."""
    frames = []
    for path in sorted(root.glob(f"{table}_*.csv")):
        if listed is not None and path.name not in listed:
            log.warning("%s is not in the download's list of files; left out", path.name)
            continue
        if path.stat().st_size == 0:
            continue
        frame = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
        frame["ccrs_file"] = path.stem
        frames.append(frame)
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    for column in columns or []:
        if column not in out.columns:
            out[column] = pd.Series(pd.NA, index=out.index, dtype="object")
    return out


def _when(text: pd.Series) -> pd.Series:
    """Dates and times, read value by value so that differing precision is no obstacle."""
    try:
        return pd.to_datetime(text, errors="coerce", format="ISO8601")
    except (ValueError, TypeError):
        return pd.to_datetime(text, errors="coerce", format="mixed")


def _true(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip().str.lower().eq("true")


def _as_text(values: pd.Series) -> pd.Series:
    """Text as TIMS writes it: whole numbers without a decimal point, missing stays missing."""
    if pd.api.types.is_numeric_dtype(values) and not pd.api.types.is_bool_dtype(values):
        numbers = pd.to_numeric(values, errors="coerce")
        if (numbers.dropna() % 1 == 0).all():
            values = numbers.astype("Int64")
    return values.astype("string")


def _int(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype("Int64")


# --- 1. CCRS internal duplicates ----------------------------------------------------------


def clean_crashes(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Keep each Collision Id's latest row, then drop deleted rows and superseded resubmissions.

    The latest row is picked before deleted rows are dropped, so that a report
    deleted in a later year's file does not survive through an older copy."""
    stats: dict[str, Any] = {"rows_read": int(len(raw))}
    crashes = raw.copy()
    crashes["ccrs_collision_id"] = _int(crashes["Collision Id"])
    crashes["_version"] = _int(crashes["Report Version"]).fillna(0)
    crashes["_modified"] = _when(crashes["ModifiedDate"])
    crashes["_crash_dt"] = _when(crashes["Crash Date Time"])
    stats["crash_dates_not_understood"] = int(
        (crashes._crash_dt.isna() & crashes["Crash Date Time"].notna()).sum()
    )
    stats["modified_dates_not_understood"] = int(
        (crashes._modified.isna() & crashes["ModifiedDate"].notna()).sum()
    )
    # Rows with no modified date sort first, so a dated row is the latest.
    crashes = crashes.sort_values(
        ["ccrs_collision_id", "_modified", "_version"], na_position="first", kind="stable"
    )
    before = len(crashes)
    crashes = crashes.drop_duplicates("ccrs_collision_id", keep="last")
    stats["repeated_collision_ids_dropped"] = int(before - len(crashes))
    latest = len(crashes)
    crashes = crashes[~_true(crashes.get("IsDeleted", pd.Series("", index=crashes.index)))].copy()
    stats["deleted_rows_dropped"] = int(latest - len(crashes))

    report = crashes["Report Number"].fillna("").astype(str).str.strip().str.upper()
    crashes["_report_key"] = crashes["NCIC Code"].fillna("").astype(str).str.strip() + "|" + report
    crashes["superseded_by"] = pd.NA
    crashes["report_number_conflict"] = False
    keyed = crashes[report.ne("")]
    repeated = keyed[keyed.duplicated("_report_key", keep=False)].sort_values(
        ["_report_key", "_version", "_modified"]
    )
    for _, group in repeated.groupby("_report_key", sort=False):
        # One report number can be reused for crashes far apart in time.  Rows
        # are split into runs: a run holds the crash dates within the limit of
        # its earliest one, and an undated row stands alone.  Within a run the
        # latest version is kept, and an earlier one is dropped only when
        # something besides the number says it is the same crash: a crash
        # date within a day of the kept one's, or a street name in common.
        # A number sequence that restarts each January reuses numbers weeks apart.
        dated = group.sort_values("_crash_dt", na_position="last", kind="stable")
        runs: list[int] = []
        start = pd.NaT
        for when in dated._crash_dt:
            new = pd.isna(when) or pd.isna(start) or (when - start).days > RESUBMISSION_MAX_DAYS
            start = when if new else start
            runs.append((runs[-1] if runs else 0) + int(new))
        run = pd.Series(runs, index=dated.index)
        winners = []
        for _, members in dated.groupby(run):
            members = members.sort_values(["_version", "_modified"], kind="stable")
            roads = dict(zip(members.index, _roads(members.PrimaryRoad, members.SecondaryRoad)))
            # Members that describe one crash form a set; each set keeps its last.
            # A member joins the first set whose every member it agrees with, so
            # a chain of small differences cannot join two unlike reports.  One
            # that agrees with two sets joins the earlier; the other set stays,
            # and all the kept rows are marked as a conflict.
            sets: list[list[Any]] = []
            day = pd.Timedelta(days=1)
            for label, member in members.iterrows():
                for same in sets:
                    if all(
                        abs(member._crash_dt - members.loc[other, "_crash_dt"]) <= day
                        or roads[label] & roads[other]
                        for other in same
                    ):
                        same.append(label)
                        break
                else:
                    sets.append([label])
            for same in sets:
                kept_id = members.loc[same[-1], "ccrs_collision_id"]
                crashes.loc[same[:-1], "superseded_by"] = kept_id
                winners.append(same[-1])
        if len(winners) > 1:
            crashes.loc[winners, "report_number_conflict"] = True
    superseded = crashes[crashes.superseded_by.notna()].copy()
    crashes = crashes[crashes.superseded_by.isna()].drop(columns="superseded_by")
    stats["superseded_resubmissions"] = int(len(superseded))
    stats["report_number_conflicts_kept"] = int(crashes.report_number_conflict.sum())
    stats["kept_reports"] = int(len(crashes))
    audit = superseded[
        [
            "ccrs_collision_id",
            "superseded_by",
            "NCIC Code",
            "Report Number",
            "Report Version",
            "Crash Date Time",
            "City Name",
            "PrimaryRoad",
            "SecondaryRoad",
        ]
    ]
    return crashes, audit, stats


def _road_key(value: Any) -> str:
    """Road name for matching: overlay normalization plus one spelling per state route."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ""
    text = str(value).upper()
    # El Camino Real is State Route 82 where this was written.  Elsewhere the
    # two names simply become one label on both sides of every comparison.
    text = re.sub(r"\bEL CAMINO( REAL)?\b", "RT 82", text)
    # Police abbreviations the shared normalizer does not know (DE ANZA BL,
    # FOOTHILL EXPR): without this they never match the street's mapped name.
    # They are written out, not dropped, so that "SOUTH BL" keeps a name.
    text = re.sub(r"\b(?:EXPR|EXP|EX)\b\.?", " EXPRESSWAY ", text)
    text = re.sub(r"\bBL\b\.?", " BOULEVARD ", text)
    text = re.sub(
        r"\b(?:SR|RT|RTE|US|I|HWY|HIGHWAY|ROUTE|STATE ROUTE|INTERSTATE)[ -]*(\d{1,3})\b",
        r"RT \1",
        text,
    )
    return normalized_road_name(text)


def _roads(primary: pd.Series, secondary: pd.Series) -> list[frozenset[str]]:
    return [
        frozenset(key for key in (_road_key(a), _road_key(b)) if key)
        for a, b in zip(primary, secondary)
    ]


def ccrs_crash_columns(
    crashes: pd.DataFrame,
    injured: pd.DataFrame,
    parties: pd.DataFrame,
    latitude: tuple[float, float] = (-90.0, 90.0),
    longitude: tuple[float, float] = (-180.0, 180.0),
) -> pd.DataFrame:
    """Translate kept CCRS crashes to the TIMS column names used here.

    Coordinates outside the ``latitude`` and ``longitude`` ranges become missing.
    """
    out = pd.DataFrame(index=crashes.index)
    out["ccrs_collision_id"] = crashes.ccrs_collision_id
    out["ccrs_report_number"] = crashes["Report Number"]
    out["ccrs_report_version"] = crashes._version
    out["ccrs_modified"] = crashes._modified
    out["JURIS"] = crashes["NCIC Code"].fillna("").astype(str).str.strip()
    out["CITY"] = crashes["City Name"].fillna("").str.upper().str.strip()
    out["BEAT_NUMBER"] = crashes["Beat"]
    out["collision_date"] = crashes._crash_dt.dt.normalize()
    out["COLLISION_DATE"] = out.collision_date.dt.strftime("%Y-%m-%d")
    out["year"] = out.collision_date.dt.year
    out["COLLISION_TIME"] = crashes["Crash Time Description"]
    out[["collision_time", "collision_hour"]] = parse_collision_time(
        crashes["Crash Time Description"]
    )
    out["PRIMARY_RD"] = crashes["PrimaryRoad"].str.strip()
    out["SECONDARY_RD"] = crashes["SecondaryRoad"].str.strip()
    # Distance from the secondary road, in feet as in TIMS; CCRS also records miles ("M").
    distance = pd.to_numeric(crashes["SecondaryDistance"], errors="coerce")
    miles = crashes["SecondaryUnitOfMeasure"].fillna("").astype(str).str.strip().eq("M")
    out["DISTANCE"] = distance.where(~miles, distance * 5280).round(1)
    out["DIRECTION"] = crashes["SecondaryDirection"]
    for target, source in {
        "TYPE_OF_COLLISION": "Collision Type Code",
        "PRIMARY_COLL_FACTOR": "Primary Collision Factor Code",
        "PCF_VIOLATION": "Primary Collision Factor Violation",
        "LIGHTING": "LightingCode",
        "MVIW": "MotorVehicleInvolvedWithCode",
        "PED_ACTION": "PedestrianActionCode",
        "ROAD_SURFACE": "RoadwaySurfaceCode",
        "CONTROL_DEVICE": "TrafficControlDeviceCode",
        "WEATHER_1": "Weather 1",
    }.items():
        out[target] = crashes[source]
    out["HIT_AND_RUN"] = crashes["HitRun"].fillna("N")
    out["NUMBER_INJURED"] = _int(crashes["NumberInjured"]).fillna(0)
    out["NUMBER_KILLED"] = _int(crashes["NumberKilled"]).fillna(0)
    lat = pd.to_numeric(crashes["Latitude"], errors="coerce")
    lon = pd.to_numeric(crashes["Longitude"], errors="coerce")
    valid = lat.between(*latitude) & lon.between(*longitude)
    out["LATITUDE"], out["LONGITUDE"] = lat.where(valid), lon.where(valid)

    injured = injured[~_true(injured.IsWitnessOnly)]
    degree = injured.ExtentOfInjuryCode.map(INJURY_DEGREE)
    worst = (
        pd.DataFrame({"id": _int(injured.CollisionId), "sev": degree.map(DEGREE_TO_SEVERITY)})
        .dropna()
        .groupby("id")
        .sev.min()
    )
    severity = out.ccrs_collision_id.map(worst)
    killed = out.NUMBER_KILLED.gt(0)
    severity = severity.where(~killed, 1)
    out["injury_crash"] = severity.notna() | out.NUMBER_INJURED.gt(0) | killed
    # An injury crash with no injured person whose degree is known has no
    # severity; "0" would say nobody was hurt.
    severity = severity.where(out.injury_crash, 0)
    out["COLLISION_SEVERITY"] = severity.astype("Int64").astype("string")
    types = parties.assign(id=_int(parties.CollisionId))
    ped_ids = set(types.loc[types.PartyType.eq("Pedestrian"), "id"])
    bike_ids = set(types.loc[types.PartyType.eq("Bicyclist"), "id"])
    out["ped_involved"] = out.ccrs_collision_id.isin(ped_ids)
    out["bike_involved"] = out.ccrs_collision_id.isin(bike_ids)
    out["PEDESTRIAN_ACCIDENT"] = np.where(out.ped_involved, "Y", "")
    out["BICYCLE_ACCIDENT"] = np.where(out.bike_involved, "Y", "")
    out["INTERSECTION"] = np.where(out.DISTANCE.fillna(-1).eq(0), "Y", "N")
    out["report_number_conflict"] = crashes.report_number_conflict
    return out.reset_index(drop=True)


def _file_year(names: pd.Series) -> pd.Series:
    return names.astype(str).str.rsplit("_", n=1).str[-1]


def latest_rows(
    rows: pd.DataFrame, keys: list[list[str]], kept: pd.DataFrame | None = None
) -> pd.DataFrame:
    """Drop earlier copies of a party or injured person, keeping the last one read.

    The yearly files are read in order, so the last copy is the latest.  With
    ``kept`` (the crash rows chosen by ``clean_crashes``), a collision keeps
    only the people in the yearly file its chosen crash row came from: a
    person taken out of a corrected report has no later row to replace the
    old one.  Then each entry of ``keys`` names columns that identify one
    person; a row repeated on any of them is one person filed twice.  Rows
    with a key missing are kept.
    """
    if kept is not None and {"CollisionId", "ccrs_file"} <= set(rows.columns) and len(rows):
        chosen = dict(zip(kept.ccrs_collision_id, _file_year(kept.ccrs_file)))
        wanted = _int(rows.CollisionId).map(chosen)
        rows = rows[wanted.isna() | _file_year(rows.ccrs_file).eq(wanted)]
    for key in keys:
        if not set(key) <= set(rows.columns):
            continue
        repeat = rows.duplicated(key, keep="last") & rows[key].notna().all(axis=1)
        rows = rows[~repeat]
    return rows


def cause_categories(crashes: pd.DataFrame, min_rows: int = 5, min_share: float = 0.9) -> dict:
    """Vehicle Code section to PCF violation category, learned from rows that have both.

    TIMS gives the category; CCRS gives only the section cited.  A section is
    mapped when at least ``min_rows`` rows cite it and ``min_share`` of them
    carry one category.
    """
    section = crashes.PCF_VIOLATION.astype("string").str.extract(r"(\d{4,5})")[0]
    category = crashes.PCF_VIOL_CATEGORY.astype("string").str.strip()
    known = section.notna() & category.notna() & category.ne("") & category.ne("-")
    table = pd.crosstab(section[known], category[known])
    if table.empty:
        return {}
    keep = table.sum(axis=1).ge(min_rows) & (table.max(axis=1) / table.sum(axis=1)).ge(min_share)
    return table[keep].idxmax(axis=1).to_dict()


def ccrs_party_columns(parties: pd.DataFrame, stwd_by_chp: dict[str, str]) -> pd.DataFrame:
    chp = (
        _int(parties.Vehicle1TypeId).astype(str).str.zfill(2).where(parties.Vehicle1TypeId.notna())
    )
    sex = parties.GenderCode.fillna("-").replace({"U": "-"})
    return pd.DataFrame(
        {
            "ccrs_collision_id": _int(parties.CollisionId),
            "PARTY_NUMBER": _int(parties.PartyNumber).astype(str),
            "PARTY_TYPE": parties.PartyType.map(PARTY_TYPE).fillna("-"),
            "AT_FAULT": np.where(_true(parties.IsAtFault), "Y", "N"),
            "PARTY_SEX": sex,
            "PARTY_AGE": parties.StatedAge.fillna("998"),
            "PARTY_SOBRIETY": parties.SobrietyDrugPhysicalCode1.fillna("-"),
            "DIR_OF_TRAVEL": parties.DirectionOfTravel.fillna("-"),
            "MOVE_PRE_ACC": parties.MovementPrecCollCode.fillna("-"),
            "VEHICLE_YEAR": parties.Vehicle1Year,
            "VEHICLE_MAKE": parties.Vehicle1Make.fillna("-"),
            "VEHICLE_MODEL": parties.Vehicle1Model,
            "CHP_VEH_TYPE_TOWING": chp,
            "STWD_VEHICLE_TYPE": chp.map(stwd_by_chp).astype(object).fillna("-"),
            "RACE": parties.RaceCode,
            "SPEED_LIMIT": parties.SpeedLimit,
        }
    )


def ccrs_victim_columns(injured: pd.DataFrame) -> pd.DataFrame:
    injured = injured[~_true(injured.IsWitnessOnly)].copy()
    injured = injured[injured.InjuredPersonType.notna() | injured.ExtentOfInjuryCode.notna()]
    injured["_id"] = _int(injured.CollisionId)
    injured = injured.sort_values(["_id", "InjuredWitPassId"])
    return pd.DataFrame(
        {
            "ccrs_collision_id": injured._id,
            "PARTY_NUMBER": _int(injured.PartyNumber).astype(str),
            "VICTIM_NUMBER": (injured.groupby("_id").cumcount() + 1).astype(str),
            "VICTIM_ROLE": injured.InjuredPersonType.map(VICTIM_ROLE).fillna("-"),
            "VICTIM_SEX": injured.Gender.fillna("-"),
            "VICTIM_AGE": injured.StatedAge.fillna("998"),
            "VICTIM_DEGREE_OF_INJURY": injured.ExtentOfInjuryCode.map(INJURY_DEGREE).fillna("0"),
        }
    )


def stwd_by_chp_code(
    tims_parties: pd.DataFrame, links: pd.DataFrame, ccrs_parties: pd.DataFrame
) -> dict[str, str]:
    """Statewide vehicle type for each CHP code, learned from linked TIMS parties.

    A code is mapped only when one statewide type covers at least 90% of the
    linked parties with that code, so the translation follows TIMS exactly."""
    direct = links[links.link_method.eq("case_id")]
    pairs = (
        ccrs_parties.merge(direct[["CASE_ID", "ccrs_collision_id"]], on="ccrs_collision_id")
        .merge(
            tims_parties[["CASE_ID", "PARTY_NUMBER", "STWD_VEHICLE_TYPE"]],
            on=["CASE_ID", "PARTY_NUMBER"],
            suffixes=("_ccrs", ""),
        )
        .dropna(subset=["CHP_VEH_TYPE_TOWING"])
    )
    mapping = {}
    for code, group in pairs.groupby("CHP_VEH_TYPE_TOWING"):
        shares = group.STWD_VEHICLE_TYPE.value_counts(normalize=True)
        if len(group) >= 3 and shares.iloc[0] >= 0.9:
            mapping[str(code)] = str(shares.index[0])
    return mapping


# --- 2. TIMS to CCRS links ----------------------------------------------------------------


def ccrs_id_from_case_id(case_id: pd.Series) -> pd.Series:
    """CCRS Collision Id embedded in a CCRS-era TIMS CASE_ID, else missing."""
    text = case_id.fillna("").astype(str).str.strip()
    embedded = text.str.fullmatch(r"[89]\d{7}")
    return pd.to_numeric(text.str[1:].where(embedded), errors="coerce").astype("Int64")


def _minutes(hour_minute: pd.Series) -> pd.Series:
    text = hour_minute.fillna("")
    return pd.to_numeric(text.str[:2], errors="coerce") * 60 + pd.to_numeric(
        text.str[3:], errors="coerce"
    )


def _metres(a: gpd.GeoSeries, b: gpd.GeoSeries, crs: str) -> np.ndarray:
    return a.to_crs(crs).distance(b.to_crs(crs), align=False).to_numpy()


def _points(lon: pd.Series, lat: pd.Series) -> gpd.GeoSeries:
    return gpd.GeoSeries(gpd.points_from_xy(lon, lat), crs=CRS_WGS84)


def link_tims(
    tims: pd.DataFrame, ccrs: pd.DataFrame, superseded: pd.DataFrame, crs: str
) -> pd.DataFrame:
    """One row per TIMS crash: the CCRS report it corresponds to, and how it was found.

    ``crs`` is a projected coordinate system in metres, for distances.
    """
    kept_id = dict(zip(superseded.ccrs_collision_id, superseded.superseded_by))
    by_id = ccrs.set_index("ccrs_collision_id")
    links = pd.DataFrame({"CASE_ID": tims.CASE_ID.astype(str).to_numpy()})
    embedded = ccrs_id_from_case_id(tims.CASE_ID).to_numpy()
    links["embedded_ccrs_id"] = embedded
    resolved = [kept_id.get(int(i), int(i)) if pd.notna(i) else pd.NA for i in embedded]
    links["ccrs_collision_id"] = pd.array(resolved, dtype="Int64")
    links["via_superseded_report"] = [pd.notna(i) and int(i) in kept_id for i in embedded]
    tims_dates = pd.to_datetime(tims.collision_date).dt.normalize().to_numpy()
    found = links.ccrs_collision_id.isin(by_id.index)
    ccrs_dates = links.ccrs_collision_id.map(by_id.collision_date)
    agree = (pd.Series(tims_dates) - ccrs_dates).abs().le(pd.Timedelta(days=1))
    links["link_method"] = np.where(found & agree, "case_id", "")
    links.loc[found & ~agree, "link_method"] = "case_id_date_mismatch"
    # The report refused for its date, and whether anything besides the id
    # says it is the same crash: both road names, points close together, or
    # one road name with points measured within the contradiction limit.
    refused = (found & ~agree).to_numpy()
    links["date_mismatch_ccrs_id"] = links.ccrs_collision_id.where(refused)
    links["date_mismatch_corroborated"] = False
    if refused.any():
        mine = tims[refused]
        theirs = by_id.loc[links.ccrs_collision_id[refused].astype(int)]
        shared = np.array(
            [
                len(a & b)
                for a, b in zip(
                    _roads(mine.PRIMARY_RD, mine.SECONDARY_RD),
                    _roads(theirs.PRIMARY_RD, theirs.SECONDARY_RD),
                )
            ]
        )
        tims_x = pd.to_numeric(mine.POINT_X, errors="coerce").fillna(0).to_numpy()
        tims_y = pd.to_numeric(mine.POINT_Y, errors="coerce").fillna(0).to_numpy()
        both = (tims_x != 0) & (tims_y != 0) & theirs.LATITUDE.notna().to_numpy()
        metres = np.full(len(mine), np.nan)
        if both.any():
            metres[both] = _metres(
                _points(tims_x[both], tims_y[both]),
                _points(theirs.LONGITUDE[both], theirs.LATITUDE[both]),
                crs,
            )
        # A missing point gives no distance, and no distance supports nothing.
        near = np.nan_to_num(metres, nan=np.inf) <= ATTRIBUTE_MAX_METRES
        close = np.nan_to_num(metres, nan=np.inf) <= ATTRIBUTE_CONTRADICTION_METRES
        links.loc[refused, "date_mismatch_corroborated"] = (
            (shared >= 2) | ((shared == 1) & close) | near
        )
    links.loc[links.link_method.ne("case_id"), "ccrs_collision_id"] = pd.NA

    # Attribute matching for unlinked TIMS crashes in years CCRS covers.
    first_year = int(ccrs.year.min()) if len(ccrs) else 9999
    pending = links.link_method.eq("") & tims.year.ge(first_year).to_numpy()
    taken = set(links.ccrs_collision_id.dropna().astype(int))
    pool = ccrs[~ccrs.ccrs_collision_id.isin(taken)].copy()
    pool["_min"] = _minutes(pool.collision_time)
    pool["_roads"] = pd.Series(_roads(pool.PRIMARY_RD, pool.SECONDARY_RD), index=pool.index)
    left = tims[pending].copy()
    left["_row"] = np.flatnonzero(pending)
    left["_min"] = _minutes(left.collision_time)
    left["_roads"] = pd.Series(_roads(left.PRIMARY_RD, left.SECONDARY_RD), index=left.index)
    left["collision_date"] = pd.to_datetime(left.collision_date).dt.normalize()
    candidates = left[
        ["_row", "JURIS", "collision_date", "_min", "_roads", "POINT_X", "POINT_Y"]
    ].merge(
        pool[
            [
                "ccrs_collision_id",
                "JURIS",
                "collision_date",
                "_min",
                "_roads",
                "LATITUDE",
                "LONGITUDE",
            ]
        ].rename(
            columns={
                "_min": "_min_c",
                "_roads": "_roads_c",
                "LATITUDE": "lat_c",
                "LONGITUDE": "lon_c",
            }
        ),
        on=["JURIS", "collision_date"],
    )
    links["minutes_apart"] = np.nan
    links["metres_apart"] = np.nan
    if len(candidates):
        candidates = candidates.reset_index(drop=True)
        dt = (candidates._min - candidates._min_c).abs()
        both_unknown = candidates._min.isna() & candidates._min_c.isna()
        candidates["minutes_apart"] = dt
        time_ok = (dt.le(ATTRIBUTE_MAX_MINUTES) | both_unknown).to_numpy()
        shared = np.array([len(a & b) for a, b in zip(candidates._roads, candidates._roads_c)])
        # TIMS writes 0 (or a blank) where SafeTREC could not geocode the crash.
        x = pd.to_numeric(candidates.POINT_X, errors="coerce").fillna(0)
        y = pd.to_numeric(candidates.POINT_Y, errors="coerce").fillna(0)
        has_xy = (x.ne(0) & y.ne(0) & candidates.lat_c.notna()).to_numpy()
        metres = np.full(len(candidates), np.nan)
        if has_xy.any():
            sub = candidates[has_xy]
            metres[has_xy] = _metres(
                _points(sub.POINT_X, sub.POINT_Y), _points(sub.lon_c, sub.lat_c), crs
            )
        candidates["metres_apart"] = metres
        near = np.nan_to_num(metres, nan=np.inf) <= ATTRIBUTE_MAX_METRES
        # Coordinates that put the two reports far apart count against a
        # candidate by more than any difference in time can: a report at the
        # same place a few minutes off beats one across town at the same minute.
        far = np.nan_to_num(metres, nan=0.0) > ATTRIBUTE_CONTRADICTION_METRES
        candidates["score"] = (
            dt.fillna(0).to_numpy()
            + np.where(shared >= 2, 0, np.where(shared == 1, 5, 10))
            + np.where(far, FAR_PENALTY, 0)
        )
        # One shared street name is weak evidence: it does not outweigh
        # coordinates that put the two reports far apart, and it is not enough
        # when neither report gives a time.
        untimed = both_unknown.to_numpy()
        named = (shared >= 2) | ((shared == 1) & ~far & ~untimed)
        # Equal scores go to the nearer report, then to those with no distance.
        good = candidates[time_ok & (named | near)].sort_values(
            ["score", "metres_apart"], kind="stable"
        )
        # Greedy one-to-one by score. A TIMS crash whose best score is shared by
        # CCRS reports that differ in time or roads is ambiguous; identical
        # candidates are one crash reported twice (flagged later as duplicates).
        best = good.groupby("_row").score.transform("min")
        top = good[good.score.eq(best)]
        signature = top._min_c.astype(str) + "|" + top._roads_c.map(sorted).astype(str)
        distinct = signature.groupby(top._row).nunique()
        ties = set(distinct.index[distinct > 1])
        # The same from the other side: a CCRS report that is the best match
        # of two TIMS crashes which differ in time or roads cannot be given
        # to either.  TIMS crashes alike in both are one crash entered twice.
        mine = top.assign(_sig=top._min.astype(str) + "|" + top._roads.map(sorted).astype(str))
        lowest = mine.groupby("ccrs_collision_id").score.transform("min")
        mine = mine[mine.score.eq(lowest)]
        rivals = mine.groupby("ccrs_collision_id")._sig.nunique()
        contested = set(rivals.index[rivals > 1])
        ties |= set(mine.loc[mine.ccrs_collision_id.isin(contested), "_row"])
        used_rows: set[int] = set()
        used_ids: set[int] = set()
        accepted = []
        for index, row_id, ccrs_id in zip(good.index, good._row, good.ccrs_collision_id):
            if row_id in ties or row_id in used_rows or ccrs_id in used_ids:
                continue
            used_rows.add(row_id)
            used_ids.add(ccrs_id)
            accepted.append(index)
        unique = good.loc[accepted]
        rows = unique._row.to_numpy()
        links.loc[rows, "ccrs_collision_id"] = unique.ccrs_collision_id.to_numpy()
        links.loc[rows, "link_method"] = "attributes"
        links.loc[rows, "minutes_apart"] = unique.minutes_apart.to_numpy()
        links.loc[rows, "metres_apart"] = unique.metres_apart.to_numpy()
        links.loc[sorted(ties - used_rows), "link_method"] = "attributes_ambiguous"
    links["link_method"] = links.link_method.replace("", "unlinked")

    # TIMS crashes resolving to the same kept CCRS report are one crash entered twice.
    linked = links[links.ccrs_collision_id.notna()]
    first = linked.drop_duplicates("ccrs_collision_id").set_index("ccrs_collision_id").CASE_ID
    repeat = linked.ccrs_collision_id.duplicated(keep="first")
    links["duplicate_of"] = pd.NA
    links.loc[linked.index[repeat], "duplicate_of"] = (
        linked.loc[repeat, "ccrs_collision_id"].map(first).to_numpy()
    )
    return links


# --- 3. Cross-agency duplicates -----------------------------------------------------------


def duplicate_reports(crashes: gpd.GeoDataFrame, crs: str) -> pd.DataFrame:
    """Pairs of reports that describe the same crash, from the same or different agencies."""
    frame = pd.DataFrame(
        {
            "merged_id": crashes.merged_id.to_numpy(),
            "agency": crashes.reporting_agency.to_numpy(),
            "date": pd.to_datetime(crashes.collision_date).dt.normalize().to_numpy(),
            "minute": _minutes(crashes.collision_time).to_numpy(),
            "roads": _roads(crashes.PRIMARY_RD, crashes.SECONDARY_RD),
            "geometry": crashes.geometry.to_crs(crs).to_numpy(),
            "priority": crashes._priority.to_numpy(),
            "parties": crashes._party_signature.to_numpy(),
        }
    ).dropna(subset=["date", "minute"])
    pairs = frame.merge(frame, on="date", suffixes=("_a", "_b"))
    pairs = pairs[
        (pairs.merged_id_a < pairs.merged_id_b)
        & (pairs.minute_a - pairs.minute_b).abs().le(CROSS_AGENCY_MAX_MINUTES)
    ].copy()
    if pairs.empty:
        return pd.DataFrame(
            columns=["merged_id_a", "merged_id_b", "same_agency", "duplicate", "keep"]
        )
    pairs["same_roads"] = [len(a) == 2 and a == b for a, b in zip(pairs.roads_a, pairs.roads_b)]
    metres = gpd.GeoSeries(pairs.geometry_a.to_numpy(), crs=crs).distance(
        gpd.GeoSeries(pairs.geometry_b.to_numpy(), crs=crs), align=False
    )
    pairs["metres_apart"] = metres.to_numpy()
    pairs["same_agency"] = pairs.agency_a.eq(pairs.agency_b)
    pairs["same_parties"] = [same_parties(a, b) for a, b in zip(pairs.parties_a, pairs.parties_b)]
    minutes = (pairs.minute_a - pairs.minute_b).abs()
    located = pairs.metres_apart.notna()

    def place(max_metres: float) -> pd.Series:
        # Coordinates decide when both exist; road names only otherwise.
        return pairs.metres_apart.le(max_metres).where(located, pairs.same_roads)

    # Two agencies describe people differently, but not a cyclist as a driver:
    # a report with a cyclist or pedestrian and one without are two crashes.
    kinds = np.array([same_kinds(a, b) for a, b in zip(pairs.parties_a, pairs.parties_b)])
    cross = ~pairs.same_agency & place(CROSS_AGENCY_MAX_METRES) & kinds
    # One agency filing twice lists the same people; a chain-reaction crash does not.
    same = (
        pairs.same_agency
        & minutes.le(SAME_AGENCY_MAX_MINUTES)
        & place(SAME_AGENCY_MAX_METRES)
        & pairs.same_parties
    )
    pairs = pairs[cross | same]
    a_first = pairs.priority_a <= pairs.priority_b
    pairs["keep"] = np.where(a_first, pairs.merged_id_a, pairs.merged_id_b)
    pairs["duplicate"] = np.where(a_first, pairs.merged_id_b, pairs.merged_id_a)
    pairs["minutes_apart"] = (pairs.minute_a - pairs.minute_b).abs()
    return pairs[
        [
            "merged_id_a",
            "merged_id_b",
            "agency_a",
            "agency_b",
            "date",
            "minutes_apart",
            "metres_apart",
            "same_roads",
            "same_agency",
            "same_parties",
            "keep",
            "duplicate",
        ]
    ].reset_index(drop=True)


def party_signatures(
    tims_parties: pd.DataFrame, ccrs_parties: pd.DataFrame, ccrs_only: pd.DataFrame
) -> pd.Series:
    """Sorted (party type, sex, age) list per merged crash id, as text."""

    def signature(frame: pd.DataFrame, key: str) -> pd.Series:
        parts = (
            frame.PARTY_TYPE.astype(str)
            + ":"
            + frame.PARTY_SEX.astype(str)
            + ":"
            + frame.PARTY_AGE.astype(str)
        )
        joined: pd.Series = parts.groupby(frame[key]).agg(lambda v: ",".join(sorted(v)))
        return joined

    tims = signature(tims_parties.assign(key=tims_parties.CASE_ID.astype(str)), "key")
    ids = ccrs_only.set_index("ccrs_collision_id").merged_id
    selected = ccrs_parties[ccrs_parties.ccrs_collision_id.isin(ids.index)]
    ccrs_signatures = signature(selected.assign(key=selected.ccrs_collision_id.map(ids)), "key")
    combined: pd.Series = pd.concat([tims, ccrs_signatures])
    return combined


def same_kinds(a: str, b: str) -> bool:
    """Both reports, or neither, list a cyclist (likewise a pedestrian) who can be one person.

    True when either party list is unknown.  Two agencies can count drivers
    and parked vehicles differently for one crash, so only cyclists and
    pedestrians are compared.  One of them in each report must be able to be
    the same person: the same sex where both record it, and ages within a
    year where both record one.
    """
    if not a or not b:
        return True

    def people(signature: str) -> dict[str, list[tuple[str, int | None]]]:
        out: dict[str, list[tuple[str, int | None]]] = {}
        for item in signature.split(","):
            kind, sex, age = item.split(":")
            if kind in ("2", "4"):
                known = int(age) if age.isdigit() and int(age) < 998 else None
                out.setdefault(kind, []).append((sex if sex in ("M", "F") else "", known))
        return out

    def alike(one: tuple[str, int | None], other: tuple[str, int | None]) -> bool:
        sexes = not one[0] or not other[0] or one[0] == other[0]
        ages = one[1] is None or other[1] is None or abs(one[1] - other[1]) <= 1
        return sexes and ages

    left, right = people(a), people(b)
    if set(left) != set(right):
        return False
    return all(any(alike(x, y) for x in left[kind] for y in right[kind]) for kind in left)


def same_parties(a: str, b: str) -> bool:
    """Same party types and sexes, with ages within a year (CCRS stated age vs TIMS age).

    Unknown ages (998 or blank) match any age."""
    if not a or not b:
        return False

    def groups(signature: str) -> dict[str, list[int | None]]:
        out: dict[str, list[int | None]] = {}
        for item in signature.split(","):
            kind, sex, age = item.split(":")
            number = int(age) if age.isdigit() and int(age) < 998 else None
            out.setdefault(f"{kind}:{sex}", []).append(number)
        return out

    left, right = groups(a), groups(b)
    if {k: len(v) for k, v in left.items()} != {k: len(v) for k, v in right.items()}:
        return False
    for key, ages in left.items():
        known_left = sorted(x for x in ages if x is not None)
        known_right = sorted(x for x in right[key] if x is not None)
        # Pair known ages within a year of each other, youngest first. Every
        # known age left over needs an unknown age on the other side.
        pairs = i = j = 0
        while i < len(known_left) and j < len(known_right):
            if abs(known_left[i] - known_right[j]) <= 1:
                pairs, i, j = pairs + 1, i + 1, j + 1
            elif known_left[i] < known_right[j]:
                i += 1
            else:
                j += 1
        unknown_left = len(ages) - len(known_left)
        unknown_right = len(ages) - len(known_right)
        if len(known_left) - pairs > unknown_right or len(known_right) - pairs > unknown_left:
            return False
    return True


# --- assembly -----------------------------------------------------------------------------


def posted_speed_limits(parties: pd.DataFrame) -> pd.Series:
    """Highest plausible (5-70 mph) driver-recorded speed limit per CCRS collision."""
    drivers = parties[parties.PARTY_TYPE.eq("1")]
    limit = pd.to_numeric(drivers.SPEED_LIMIT, errors="coerce")
    limit = limit.where(limit.between(5, 70))
    return limit.groupby(drivers.ccrs_collision_id).max().dropna()


WRONG_POINT_M = 1000.0  # a CCRS point this far from the streets its report names is doubted


def place_unlocated(
    merged: gpd.GeoDataFrame,
    centerlines: gpd.GeoDataFrame,
    crs: str,
    municipality_aliases: Mapping[str, str] | None = None,
) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    """Place crashes with no coordinates from their reported intersection and offset.

    Also crashes whose CCRS point is over ``WRONG_POINT_M`` from both streets
    the report names (``reported_point_replaced``); one that cannot be placed
    keeps its point.  TIMS points are kept.

    Uses the road-centerline matching of the collision overlays
    (`locate_reported_intersections`). Placed rows get geometry_source
    "intersection_centerline" and geometry_is_approximate, and
    offset_direction_missing where a distance was given without a direction and
    the crash sits at the corner itself; the audit lists every
    attempt with its status."""
    merged = merged.copy()
    merged["geometry_is_approximate"] = False
    merged["offset_direction_missing"] = False
    merged["reported_offset_m"] = np.nan
    merged["reported_point_replaced"] = False
    lines = centerlines.to_crs(crs)
    # A CCRS point far from both streets its own report names is wrong (some
    # early CCRS years hold coordinates tens of kilometres off): the crash is
    # then placed from the street names like one with no point.  Being far
    # from the named corner alone is not enough, since street names are
    # matched loosely and the corner found could be the wrong one.
    given = merged[merged.geometry_source.eq("ccrs")]
    off = distance_to_named_roads(given.to_crs(crs), lines, municipality_aliases)
    doubted = pd.Series(merged.index.isin(off.index[off > WRONG_POINT_M]), index=merged.index)
    todo = merged[merged.geometry_source.eq("") | doubted]
    found = locate_reported_intersections(todo, lines, municipality_aliases=municipality_aliases)
    # Second pass for the rest: cross streets that stop short of an expressway,
    # longer offsets, and roads at an angle to the reported compass direction.
    again = locate_reported_intersections(
        todo[found.geometry.isna()], lines, relaxed=True, municipality_aliases=municipality_aliases
    )
    again = again[again.geometry.notna()]
    found.loc[again.index, again.columns] = again
    placed = found[found.geometry.notna()]
    points = placed.geometry.to_crs(merged.crs)
    merged.loc[placed.index, "geometry"] = points.to_numpy()
    merged.loc[placed.index, "geometry_source"] = "intersection_centerline"
    merged.loc[placed.index, "reported_point_replaced"] = doubted.loc[placed.index]
    merged.loc[placed.index, "geometry_is_approximate"] = True
    # Placed at the corner although the report gives a distance from it: the
    # direction was not recorded, so the point is up to reported_offset_m out.
    merged.loc[placed.index, "offset_direction_missing"] = placed.recovery_status.eq(
        NO_DIRECTION_STATUS
    ).to_numpy()
    merged.loc[placed.index, "reported_offset_m"] = placed.reported_offset_m.round(1)
    audit = todo[
        ["merged_id", "source", "injury_crash", "CITY", "PRIMARY_RD", "SECONDARY_RD"]
    ].join(found.drop(columns="geometry"))
    audit["location_recovered"] = audit.index.isin(placed.index)
    audit["reported_point_doubted"] = doubted.loc[todo.index]
    return merged, audit.reset_index(drop=True)


def build(
    root: Path,
    out: Path,
    config: Config,
    centerlines: Path | None = None,
    streets: gpd.GeoDataFrame | None = None,
) -> bool:
    """Merge the CCRS download under ``root`` with the TIMS tables already in ``out``.

    ``centerlines`` is a road-centerline layer (GeoParquet) used to place
    crashes that have no coordinates, or a CCRS point far from both streets
    the report names.  ``streets`` is a layer of the same columns made from the
    street table (``locate.streets_as_centerlines``), used when there is no
    centerline file; with neither, those crashes stay as they are.  A
    centerline file that is named and does not exist is an error.  Returns
    False, with a message, when either input is missing.
    """
    if centerlines is not None and not centerlines.exists():
        raise FileNotFoundError(f"road centerlines {centerlines} do not exist")
    crs, rules = config.crs, config.agency_reassignments
    listed = manifest_files(root, config)
    raw_crashes = _read("Crashes", root, listed)
    tims_path = out / "crashes_4326.parquet"
    if raw_crashes.empty or not tims_path.exists():
        print("CCRS download or TIMS crash tables missing; run those steps first.")
        return False
    absent = [name for name in ("parties.parquet", "victims.parquet") if not (out / name).exists()]
    if absent:  # the tims step writes each only when the export has its CSV
        print(
            f"TIMS tables missing ({', '.join(absent)}): every TIMS batch needs "
            "Parties.csv and Victims.csv beside Crashes.csv; add them and run the tims step again."
        )
        return False
    raw_parties = _read("Parties", root, listed, PARTY_COLUMNS)
    raw_injured = _read("InjuredWitnessPassengers", root, listed, INJURED_COLUMNS)
    read = len(raw_parties), len(raw_injured)
    kept, superseded, stats = clean_crashes(raw_crashes)
    raw_parties = latest_rows(raw_parties, [["PartyId"], ["CollisionId", "PartyNumber"]], kept)
    raw_injured = latest_rows(raw_injured, [["InjuredWitPassId"]], kept)
    ccrs = ccrs_crash_columns(kept, raw_injured, raw_parties, config.latitude, config.longitude)
    write_table(ccrs, out, "ccrs_crashes")
    superseded.to_csv(out / "ccrs_superseded.csv", index=False)

    tims = gpd.read_parquet(tims_path)
    tims_parties = pd.read_parquet(out / "parties.parquet")
    tims_victims = pd.read_parquet(out / "victims.parquet")
    links = link_tims(tims, ccrs, superseded, crs)
    links.to_csv(out / "ccrs_tims_links.csv", index=False)

    # Merged crash table: all TIMS crashes, then CCRS reports TIMS lacks.
    tims = tims.reset_index(drop=True)
    tims["ccrs_collision_id"] = links.ccrs_collision_id.to_numpy()
    tims["ccrs_link_method"] = links.link_method.to_numpy()
    tims["duplicate_of"] = links.duplicate_of.to_numpy()
    tims["source"] = "tims"
    tims["in_ccrs"] = tims.ccrs_collision_id.notna()
    tims["injury_crash"] = True
    tims["merged_id"] = tims.CASE_ID.astype(str)
    tims["geometry_source"] = np.where(~tims.geometry.isna() & ~tims.geometry.is_empty, "tims", "")
    by_id = ccrs.set_index("ccrs_collision_id")
    fill = tims.geometry_source.eq("") & tims.ccrs_collision_id.notna()
    lat = tims.ccrs_collision_id.map(by_id.LATITUDE)
    lon = tims.ccrs_collision_id.map(by_id.LONGITUDE)
    fill &= lat.notna()
    tims.loc[fill, "geometry"] = gpd.points_from_xy(lon[fill], lat[fill])
    tims.loc[fill, "geometry_source"] = "ccrs"

    linked_ids = set(tims.ccrs_collision_id.dropna().astype(int))
    extra = ccrs[~ccrs.ccrs_collision_id.isin(linked_ids)].copy()
    extra["source"] = "ccrs"
    extra["in_ccrs"] = True
    extra["CASE_ID"] = pd.NA
    extra["merged_id"] = "CCRS-" + extra.ccrs_collision_id.astype(str)
    extra["ccrs_link_method"] = "ccrs_only"
    extra["duplicate_of"] = pd.NA
    has_xy = extra.LATITUDE.notna()
    extra["geometry_source"] = np.where(has_xy, "ccrs", "")
    extra = gpd.GeoDataFrame(
        extra,
        geometry=gpd.points_from_xy(extra.LONGITUDE.where(has_xy), extra.LATITUDE.where(has_xy)),
        crs=CRS_WGS84,
    )
    for column in extra.columns.intersection(tims.columns).drop("geometry", errors="ignore"):
        if pd.api.types.is_string_dtype(tims[column]) and not pd.api.types.is_string_dtype(
            extra[column]
        ):
            extra[column] = _as_text(extra[column])
    merged = gpd.GeoDataFrame(pd.concat([tims, extra], ignore_index=True), crs=CRS_WGS84)
    lines = streets
    if centerlines is not None and centerlines.exists():
        lines = gpd.read_parquet(centerlines)
    if lines is not None:
        merged, placement = place_unlocated(merged, lines, crs, config.municipality_aliases)
    else:
        log.warning("No road centerlines or street table; unlocated crashes stay unlocated")
        merged["reported_point_replaced"] = False
        merged["geometry_is_approximate"] = False
        merged["offset_direction_missing"] = False
        merged["reported_offset_m"] = np.nan
        placement = pd.DataFrame(columns=["recovery_status", "location_recovered"])
    placement.to_csv(out / "crashes_merged_location_recovery.csv", index=False)
    merged["ccrs_collision_id"] = merged.ccrs_collision_id.astype("Int64")
    merged["year"] = pd.to_datetime(merged.collision_date).dt.year
    # CCRS gives the Vehicle Code section but no cause category: take the
    # category TIMS gives that section elsewhere in these tables.
    merged["cause_category_inferred"] = False
    if {"PCF_VIOLATION", "PCF_VIOL_CATEGORY"} <= set(merged.columns):
        learned = cause_categories(merged)
        section = merged.PCF_VIOLATION.astype("string").str.extract(r"(\d{4,5})")[0]
        blank = merged.PCF_VIOL_CATEGORY.isna() & section.isin(list(learned))
        merged.loc[blank, "PCF_VIOL_CATEGORY"] = section[blank].map(learned)
        merged.loc[blank, "cause_category_inferred"] = True
    merged["reporting_agency"] = reporting_agency(merged, rules)
    merged["_priority"] = (
        merged.source.ne("tims").astype(int) * 4
        + (~merged.injury_crash.astype(bool)).astype(int) * 2
        + merged.reporting_agency.str.startswith("9").astype(int)
    )
    merged["_party_signature"] = merged.merged_id.map(
        party_signatures(tims_parties, ccrs_party_columns(raw_parties, {}), extra)
    ).fillna("")
    pairs = duplicate_reports(merged[merged.duplicate_of.isna()], crs)
    pairs.to_csv(out / "crashes_duplicate_reports.csv", index=False)
    partner = pairs.drop_duplicates("duplicate").set_index("duplicate").keep
    # As objects: with no pairs the mapped column is all missing and numeric,
    # and filling it with report IDs is something pandas is about to refuse.
    possible = merged.merged_id.map(partner).astype(object)
    # A CCRS-only report whose id a TIMS crash carries, with a date over a day
    # off (case_id_date_mismatch) and a road name or place in common: the link
    # stays refused, and the report is marked so that a date corrected in one
    # source does not count a crash twice.  Only when one TIMS row that is
    # not itself marked fits the report, and that row can stand for the crash
    # as well as the report can: it has a date, and a point unless the report
    # has none.  With the id alone, with several such rows (which may be
    # different crashes) or with a row that lacks either, every row is counted.
    agreed = links.date_mismatch_corroborated & ~links.date_mismatch_ccrs_id.isin(
        links.ccrs_collision_id.dropna()
    )
    unmarked = merged.merged_id[possible.isna() & merged.duplicate_of.isna()]
    fits = links[agreed & links.CASE_ID.isin(set(unmarked))]
    alone = fits[~fits.date_mismatch_ccrs_id.duplicated(keep=False)]
    report_id = "CCRS-" + alone.date_mismatch_ccrs_id.astype(str)
    dated = set(merged.merged_id[merged.collision_date.notna()])
    placed = set(merged.merged_id[merged.geometry_source.ne("")])
    complete = alone.CASE_ID.isin(dated) & (alone.CASE_ID.isin(placed) | ~report_id.isin(placed))
    carried_by = dict(zip(report_id[complete], alone.CASE_ID[complete]))
    mismatched = merged.merged_id.where(merged.source.eq("ccrs") & possible.isna())
    mismatched = mismatched.map(carried_by).astype(object)
    marked = possible.fillna(mismatched).fillna(merged.duplicate_of)
    # A row marked against a row that is itself marked (a second report of
    # the crash, against the report marked above) is a duplicate of the row
    # finally kept: counts drop every marked row, so each must name a kept one.
    for _ in range(len(merged)):
        onward = marked.map(dict(zip(merged.merged_id, marked))).astype(object)
        if onward.isna().all():
            break
        marked = onward.fillna(marked)
    merged["possible_duplicate_of"] = marked
    named = marked.dropna()
    wrong = ~named.isin(set(merged.merged_id)) | named.isin(set(merged.merged_id[marked.notna()]))
    if wrong.any():
        raise AssertionError(
            f"{int(wrong.sum())} possible_duplicate_of values name a row that is absent or "
            "is itself marked as a duplicate"
        )

    injury = merged[merged.injury_crash.astype(bool) & merged.possible_duplicate_of.isna()]
    gaps = agency_reporting_gaps(injury.assign(JURIS=injury.reporting_agency), reassignments=rules)
    flagged = gaps[gaps.reporting_gap.astype(bool)]
    keys = set(zip(flagged.reporting_agency, flagged.year))
    merged["agency_reporting_gap"] = [
        (a, int(y)) in keys if pd.notna(y) else False
        for a, y in zip(merged.reporting_agency, merged.year)
    ]
    merged["agency_has_reporting_gap"] = merged.reporting_agency.isin(set(flagged.reporting_agency))
    gaps.to_csv(out / "crashes_merged_agency_reporting.csv", index=False)

    # Parties and victims: TIMS rows, plus CCRS rows for CCRS-only crashes.
    stwd = stwd_by_chp_code(tims_parties, links, ccrs_party_columns(raw_parties, {}))
    extra_ids = extra.set_index("ccrs_collision_id").merged_id
    c_parties = ccrs_party_columns(raw_parties, stwd)
    # Posted speed limit (CCRS only, mostly 2021 on): the highest recorded for a
    # driver, i.e. the fastest road a motor vehicle was on. Also for TIMS crashes
    # linked to a CCRS report.
    merged["posted_speed_limit_mph"] = merged.ccrs_collision_id.map(
        posted_speed_limits(c_parties)
    ).astype("Float64")
    c_parties = c_parties[c_parties.ccrs_collision_id.isin(extra_ids.index)]
    c_parties["CASE_ID"] = c_parties.ccrs_collision_id.map(extra_ids)
    c_victims = ccrs_victim_columns(raw_injured)
    c_victims = c_victims[c_victims.ccrs_collision_id.isin(extra_ids.index)]
    c_victims["CASE_ID"] = c_victims.ccrs_collision_id.map(extra_ids)
    parties = pd.concat(
        [tims_parties.assign(source="tims"), c_parties.assign(source="ccrs")], ignore_index=True
    )
    victims = pd.concat(
        [tims_victims.assign(source="tims"), c_victims.assign(source="ccrs")], ignore_index=True
    )
    write_table(parties, out, "parties_merged")
    write_table(victims, out, "victims_merged")
    bikes = ebike.bicycle_parties(parties)
    write_table(bikes, out, "bicycle_parties_merged")
    merged["ebike_involved"] = merged.merged_id.isin(bikes.loc[bikes.ebike, "CASE_ID"])
    write_dual(merged.drop(columns=["_priority", "_party_signature"]), out, "crashes_merged", crs)

    stats.update(
        {
            "tims_crashes": int(len(tims)),
            "tims_link_methods": {
                str(k): int(v) for k, v in links.link_method.value_counts().items()
            },
            "tims_linked_via_superseded_report": int(links.via_superseded_report.sum()),
            "tims_duplicates_of_same_ccrs_report": int(links.duplicate_of.notna().sum()),
            "ccrs_only_flagged_for_case_id_date_mismatch": int(mismatched.notna().sum()),
            "case_id_date_mismatches_kept_as_two_crashes": int(
                (
                    ~links.date_mismatch_corroborated
                    & links.date_mismatch_ccrs_id.isin(extra.ccrs_collision_id)
                ).sum()
            ),
            "case_id_date_mismatches_with_several_tims_rows_kept": int(
                fits.date_mismatch_ccrs_id.nunique() - len(alone)
            ),
            "case_id_date_mismatches_kept_because_tims_row_incomplete": int((~complete).sum()),
            "ccrs_injury_crashes_without_severity": int(
                (ccrs.injury_crash & ccrs.COLLISION_SEVERITY.isna()).sum()
            ),
            "ccrs_only_crashes": int(len(extra)),
            "ccrs_only_injury_crashes": int(extra.injury_crash.sum()),
            "ccrs_only_injury_crashes_by_year": {
                str(k): int(v)
                for k, v in extra[extra.injury_crash].year.value_counts().sort_index().items()
            },
            "duplicate_report_pairs_cross_agency": int((~pairs.same_agency.astype(bool)).sum()),
            "duplicate_report_pairs_same_agency": int(pairs.same_agency.astype(bool).sum()),
            "duplicate_pairs_by_source": {
                str(k): int(v)
                for k, v in pairs.assign(
                    kind=pairs.keep.str.startswith("CCRS-").map({True: "ccrs", False: "tims"})
                    + "+"
                    + pairs.duplicate.str.startswith("CCRS-").map({True: "ccrs", False: "tims"})
                )
                .kind.value_counts()
                .items()
            },
            "rows_flagged_possible_duplicate": int(merged.possible_duplicate_of.notna().sum()),
            "repeated_party_rows_dropped": read[0] - len(raw_parties),
            "repeated_injured_rows_dropped": read[1] - len(raw_injured),
            "tims_crashes_left_unlinked_as_ambiguous": int(
                links.link_method.eq("attributes_ambiguous").sum()
            ),
            "attribute_links_over_1km_apart": int(
                (links.link_method.eq("attributes") & links.metres_apart.gt(1000)).sum()
            ),
            "cause_categories_inferred": int(merged.cause_category_inferred.sum()),
            "merged_rows": int(len(merged)),
            "built_for": {
                "city": config.city,
                "county_code": config.ccrs_county_code,
                "ccrs_cities": list(config.ccrs_cities),
            },
            "placed_from": (
                "centerlines"
                if centerlines is not None and centerlines.exists()
                else "street table"
                if streets is not None
                else "nothing"
            ),
            "ccrs_points_replaced_from_street_names": int(merged.reported_point_replaced.sum()),
            "merged_rows_without_geometry": int(merged.geometry_source.eq("").sum()),
            "crashes_with_posted_speed_limit": int(merged.posted_speed_limit_mph.notna().sum()),
            "merged_geometry_sources": {
                str(k): int(v) for k, v in merged.geometry_source.value_counts().items()
            },
            "location_recovery_status": {
                str(k): int(v) for k, v in placement.recovery_status.value_counts().items()
            },
            "chp_to_statewide_vehicle_type": stwd,
            "agency_reporting_gaps": [
                {"reporting_agency": a, "year": int(y)}
                for a, y in flagged[["reporting_agency", "year"]].itertuples(index=False)
            ],
        }
    )
    (out / "crashes_merge_report.json").write_text(json.dumps(stats, indent=1, default=str))
    print(json.dumps(stats, indent=1, default=str))
    return True
