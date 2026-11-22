"""Hold-out check and forecast table for corridors (named streets).

Each ranking of corridors uses only crashes up to a cut-off year and is scored
on the cyclist crashes after it, as the intersection check is.  Three rankings
are compared: past crashes on the corridor, street length alone, and the
corridor model (``model.corridors``).  Totals are scored by rank score, by the
rank correlation of score with later crashes (which still works when every
corridor has a later crash, where a rank score cannot be had) and by later
crashes found in the top corridors; rates by how well each ranking's
crashes per km order the later crashes per km, over corridors at least
``MIN_KM`` long.  All figures are counts per ranking, not individual records.

With a city limit each corridor is split into its part inside the city and
its part outside, the model is fitted on all of them, and the city's pieces
are also scored on their own.

``python -m bike_safety_ca.checks.corridors --synthetic`` runs on the made-up
city and needs no data.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Collection, Mapping, Sequence
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from shapely.geometry.base import BaseGeometry

from bike_safety_ca import CAR, CHILD, CYCLISTS, age_label
from bike_safety_ca.checks.holdout import MIN_LATER, OUTCOMES, WINDOWS, Window
from bike_safety_ca.model.corridors import score_corridors
from bike_safety_ca.model.crash_history import rank_score, top_share
from bike_safety_ca.network.names import corridor

PAST = "Past crashes on the corridor"
LENGTH = "Street length alone"
MODEL = "Corridor model"
ALL_CYCLISTS = "All-cyclist corridor model"
TOPS = (10, 25)
# Shorter pieces have rates that swing on a single crash.
MIN_KM = 0.5
NOTE = (
    "A corner counts for every street through it, so corridor totals add up to "
    "more than the area's total. Expected counts are sums of estimates that share "
    "street averages; read them to the nearest few crashes."
)

Streets = Mapping[Any, Collection[str]]
Key = Callable[[str, bool], str]


def piece(city: str | None) -> Key:
    """Name for a corridor, or for its part inside or outside ``city`` when given."""
    if city is None:
        return lambda name, inside: name
    return lambda name, inside: f"{name} ({city if inside else 'elsewhere'})"


def pieces(
    sites: pd.Index,
    streets: Streets,
    inside: pd.Series,
    key: Key,
    label: Callable[[str], str] = corridor,
    known: pd.Index | None = None,
) -> tuple[dict[Any, list[Any]], int]:
    """The corners on each corridor piece, and how many corners are on none.

    ``inside`` says which corners are in the city and ``label`` names the
    corridor of each street name at a corner.  With ``known`` (the pieces that
    have a length), a corner whose piece has none goes to the other side of the
    limit, as a corner on the boundary of a street mapped only on one side;
    a corner on no known piece at all is counted, not kept.
    """
    corners: dict[Any, list[Any]] = {}
    lost = 0
    for site in sorted(sites, key=str):
        names = sorted({label(n) for n in streets.get(site, ())} - {""})
        placed = False
        for name in names:
            here = bool(inside.get(site, False))
            choice = key(name, here)
            if known is not None and choice not in known:
                choice = key(name, not here)
                if choice not in known:
                    continue
            corners.setdefault(choice, []).append(site)
            placed = True
        lost += not placed
    return dict(sorted(corners.items())), lost


def street_labels(names: pd.Series) -> dict[str, str]:
    """A readable corridor name for each mapped street, by its street key.

    Streets are grouped by ``junctions.street_key``, the key the intersection
    model uses, which keeps the street type: Park Avenue, Park Place and Park
    Way are three corridors.  The label is the commonest tidied name
    (``corridor``) among the mapped names of a street, ties broken
    alphabetically.  ``corridor`` drops generic types, so where two streets
    would get one label ("1st" for 1st Street and 1st Avenue) each gets its
    type as well; no two streets share a label.
    """
    from bike_safety_ca.network.junctions import road_key, street_key

    table = pd.DataFrame({"key": names.map(street_key), "label": names.map(corridor)})
    table = table[(table.key != "") & (table.label != "")]
    counts = table.groupby(["key", "label"]).size().reset_index(name="n")
    counts = counts.sort_values(["key", "n", "label"], ascending=[True, False, True])
    labels = {
        str(k): str(v) for k, v in counts.drop_duplicates("key").set_index("key").label.items()
    }
    for _ in range(2):  # add the type where a label is shared, then fall back to the key
        shared = {label for label in labels.values() if list(labels.values()).count(label) > 1}
        for key, label in labels.items():
            if label in shared:
                kind = key.removeprefix(road_key(key)).strip().title()
                labels[key] = (
                    f"{label} {kind}" if kind and not label.endswith(kind) else key.title()
                )
    return labels


def streets_by_name(lines: gpd.GeoDataFrame) -> dict[str, list[str]]:
    """The mapped streets (street keys) under each name (``road_key``), longest first."""
    from bike_safety_ca.network.junctions import road_key, street_key

    named = lines[lines["name"].notna()]
    metres = pd.Series(
        named.geometry.length.to_numpy(), index=named["name"].map(street_key).to_numpy()
    )
    metres = metres[metres.index != ""].groupby(level=0).sum()
    table = pd.DataFrame(
        {"key": metres.index, "name": metres.index.map(road_key), "metres": metres.to_numpy()}
    )
    table = table.sort_values(["metres", "key"], ascending=[False, True])
    return {str(name): list(part.key) for name, part in table.groupby("name")}


def reported_street(text: object, by_name: Mapping[str, Sequence[str]]) -> str:
    """The mapped street (street key) a crash report's road text names; empty if none.

    Police abbreviate and drop street types, so the name alone (``road_key``)
    is matched, as ``assign_crashes`` does.
    """
    from bike_safety_ca.network.junctions import road_key, street_key

    name = road_key(text)
    streets = by_name.get(name, ())
    # Several mapped streets can share the name (Park Avenue, Park Place).  The
    # match stays tolerant, as it was when they were one corridor: no crash is
    # dropped for it.  The report's own type decides when it names one of them;
    # a report with no type, or with a type that is not mapped, goes to the
    # longest of them, which may be the wrong one.  A street mapped without a
    # type ("Park") gets no preference from a report that gives none.
    exact = street_key(text)
    return exact if exact != name and exact in streets else next(iter(streets), "")


def piece_lengths(
    lines: gpd.GeoDataFrame,
    outline: BaseGeometry,
    limit: BaseGeometry | None,
    labels: Mapping[str, str],
    key: Key,
) -> pd.Series:
    """Length in km of each corridor piece inside ``outline``.

    The street lines are clipped to the outline and then split by the limit,
    so a street along the boundary is counted once, on the inside (as corners
    and crashes on the boundary are).
    """
    from bike_safety_ca.network.junctions import street_key

    named = lines[lines["name"].notna()]
    names = [labels.get(street_key(n), "") for n in named["name"]]
    clipped = named.geometry.intersection(outline)
    parts = (
        [(True, clipped.intersection(limit)), (False, clipped.difference(limit))]
        if limit is not None
        else [(False, clipped)]
    )
    km = pd.concat(
        pd.Series(
            (geometry.length / 1000).to_numpy(),
            index=[key(n, inside) if n else "" for n in names],
        )
        for inside, geometry in parts
    )
    return km[(km.index != "") & (km > 0)].groupby(level=0).sum().sort_index()


def split(
    crashes: pd.DataFrame, at: pd.Series, chosen: pd.Series, sites: pd.Index, pieces: pd.Index
) -> tuple[pd.Series, pd.Series]:
    """Chosen crashes counted per intersection, and the rest per corridor piece between corners.

    A crash with an intersection in ``at`` counts there and nowhere else; any
    other counts on its ``corridor`` piece, if it has one.
    """
    at = at.reindex(crashes.index)
    corner = at.notna()
    site = at[chosen & corner].value_counts().reindex(sites, fill_value=0)
    between = crashes.corridor[chosen & ~corner]
    between = between[between != ""].value_counts().reindex(pieces, fill_value=0)
    return site.astype(float), between.astype(float)


def holdout(
    crashes: pd.DataFrame,
    at: pd.Series,
    sites: pd.Index,
    streets: Streets,
    corners: Mapping[Any, list[Any]],
    km: pd.Series,
    windows: Sequence[Window] = WINDOWS,
    areas: Mapping[str, pd.Index] | None = None,
    min_later: int = MIN_LATER,
    min_km: float = MIN_KM,
) -> pd.DataFrame:
    """One row per window, outcome, area and ranking.

    ``crashes`` has one row per crash with ``year``, ``group`` and
    ``corridor`` (the piece of its reported primary road, empty if none);
    ``at`` gives the intersection of each crash placed at one, indexed like
    ``crashes``; every other crash is between corners.  ``corners`` and ``km``
    are the corridor pieces, and ``areas`` names subsets of them to score on
    their own.  Where an area has fewer than ``min_later`` later crashes the
    scores are left empty, and ``scored`` says whether a rank score came out
    (it cannot when every corridor, or none, had a later crash).

    ``training crashes`` and ``later crashes`` count each crash on the area's
    corridors once, and the ``min_later`` floor is on that count, as in the
    intersection check.  The per-corridor counts that are ranked and scored
    still include a corner crash on every street through the corner.
    """
    areas = {"All corridors": km.index, **(areas or {})}

    def counts(groups: list[str], first: int, last: int | None) -> tuple[pd.Series, pd.Series]:
        years = crashes.year.ge(first) if last is None else crashes.year.between(first, last)
        return split(crashes, at, crashes.group.isin(groups) & years, sites, km.index)

    def on(site: pd.Series, between: pd.Series) -> pd.Series:
        total = pd.Series(
            [float(site.reindex(corners.get(k, []), fill_value=0).sum()) for k in km.index],
            index=km.index,
        )
        return total + between

    def distinct(site: pd.Series, between: pd.Series, index: pd.Index) -> int:
        """Crashes on the corridors in ``index``, a corner crash counted once."""
        at = sorted({s for k in index for s in corners.get(k, [])}, key=str)
        return int(site.reindex(at, fill_value=0).sum() + between.reindex(index).sum())

    rows = []
    for train_to, test_from, test_to in windows:
        car = counts([CAR], 0, train_to)

        def fitted(groups: list[str], train_to: int = train_to, car: Any = car) -> dict[str, Any]:
            bike_site, bike_between = counts(groups, 0, train_to)
            car_site, car_between = car
            return score_corridors(
                bike_site, car_site, streets, corners, bike_between, car_between, km
            )

        everyone = fitted(CYCLISTS)
        for outcome, groups in OUTCOMES.items():
            whole = set(groups) == set(CYCLISTS)
            result = everyone if whole else fitted(groups)
            table = result["table"]
            earlier = counts(groups, 0, train_to)
            after = counts(groups, test_from, test_to)
            later = on(*after)
            method = f"corners: {result['corner_method']}; between: {result['between_method']}"
            rankings = {
                PAST: (table.past, PAST),
                LENGTH: (km, LENGTH),
                MODEL: (table.expected, method),
            }
            if not whole:
                rankings[ALL_CYCLISTS] = (
                    everyone["table"].expected,
                    f"corners: {everyone['corner_method']}; between: {everyone['between_method']}",
                )
            for area, index in areas.items():
                target = later.reindex(index)
                # The floor is on crashes, not on the corridor sum, which
                # holds a corner crash once per street.
                n_later = distinct(*after, index)
                n_training = distinct(*earlier, index)
                enough = n_later >= min_later
                long = km.reindex(index) >= min_km
                for name, (score, how) in rankings.items():
                    score = score.reindex(index)
                    auc = rank_score(score, target) if enough else float("nan")
                    order = float("nan")
                    if enough and len(index) >= 3:
                        order = float(spearmanr(score, target).statistic)
                    rate = float("nan")
                    if enough and name != LENGTH and int(long.sum()) >= 3:
                        rate = float(
                            spearmanr(
                                (score / km.reindex(index))[long],
                                (target / km.reindex(index))[long],
                            ).statistic
                        )
                    rows.append(
                        {
                            "trained through": train_to,
                            "tested on": f"{test_from}–{test_to or 'latest'}",
                            "outcome": outcome,
                            "area": area,
                            "ranking": name,
                            "method": how,
                            "corridors": len(index),
                            "training crashes": n_training,
                            "later crashes": n_later,
                            "scored": bool(np.isfinite(auc)),
                            "rank score": round(auc, 3) if enough else float("nan"),
                            **{
                                f"found in top {k}": round(top_share(score, target, k), 1)
                                if enough
                                else float("nan")
                                for k in TOPS
                            },
                            "count correlation": round(order, 3)
                            if np.isfinite(order)
                            else float("nan"),
                            "rate correlation": round(rate, 3)
                            if np.isfinite(rate)
                            else float("nan"),
                        }
                    )
    return pd.DataFrame(rows)


def report(table: pd.DataFrame) -> str:
    """Rank score and rate correlation per ranking and test period, as printed text."""
    lines = []
    for (outcome, area), part in table.groupby(["outcome", "area"], sort=False):
        lines.append(f"\n{outcome}, {area}")
        for measure in (
            "rank score",
            "count correlation",
            "rate correlation",
            f"found in top {TOPS[0]}",
        ):
            wide = part.pivot_table(
                index="ranking", columns="tested on", values=measure, sort=False, dropna=False
            )
            lines.append(f"  {measure}:")
            lines.append("    " + wide.to_string(na_rep="–").replace("\n", "\n    "))
        model = part[part.ranking == MODEL]
        eligible = int(model["later crashes"].ge(MIN_LATER).sum())
        lines.append(
            f"  windows scored: {int(model.scored.sum())} of {eligible} with "
            f"{MIN_LATER}+ later crashes; method: {'; '.join(sorted(set(model.method)))}"
        )
    return "\n".join(lines)


def forecast_table(result: dict[str, Any], index: pd.Index, min_km: float = MIN_KM) -> pd.DataFrame:
    """The corridor forecast for ``index``, most expected crashes first, rounded for reading.

    Rates are left empty for pieces shorter than ``min_km``: a corner at the
    end of a short stub would give it a rate that means nothing.
    """
    table = result["table"].reindex(index)
    out = pd.DataFrame(
        {
            "km": table.km.round(2),
            "past crashes": table.past.astype(int),
            "expected": table.expected.round(1),
            "expected per km": table.per_km.where(table.km >= min_km).round(1),
            "of which at corners": table.corners.round(1),
            "between corners": table.between.round(1),
        }
    )
    return out.sort_values(["expected", "past crashes"], ascending=False)


def load(
    config: Any, crash_folder: Path, ways: Path, outline: BaseGeometry, limit: BaseGeometry | None
) -> dict[str, Any]:
    """Crashes, intersections and corridor pieces for a real area."""
    from bike_safety_ca.crashes import groups
    from bike_safety_ca.network import junctions
    from bike_safety_ca.network import streets as street_table

    lines = gpd.read_parquet(ways, columns=street_table.COLUMNS)
    sites, streets = junctions.build_junctions(lines, outline)
    crashes = groups.load(crash_folder, config.crs, config.child_max_age, outline)
    crashes = crashes[crashes.group.isin([*CYCLISTS, CAR]) & crashes.year.ge(config.first_year)]
    if not crashes.merged_id.is_unique:
        raise ValueError("crash table has repeated merged_id values")
    # assign_crashes returns only the crashes at an intersection, by merged_id.
    site = junctions.assign_crashes(crashes, sites.geometry, streets).site
    at = crashes.merged_id.map(site).dropna()
    city = config.city if limit is not None else None
    key = piece(city)
    labels = street_labels(lines["name"].dropna())
    km = piece_lengths(lines, outline, limit, labels, key)

    def covered(geometry: gpd.GeoSeries) -> pd.Series:
        if limit is None:
            return pd.Series(False, index=geometry.index)
        return geometry.covered_by(limit)  # the boundary counts as inside

    inside_crash = covered(crashes.geometry)
    by_name = streets_by_name(lines)
    names = [labels.get(reported_street(n, by_name), "") for n in crashes.PRIMARY_RD]
    pieces_of_crashes = []
    for name, inside in zip(names, inside_crash, strict=True):
        choice = key(name, bool(inside)) if name else ""
        if choice and choice not in km.index:
            choice = key(name, not inside) if key(name, not inside) in km.index else ""
        pieces_of_crashes.append(choice)
    crashes = crashes.assign(corridor=pieces_of_crashes)
    corners, lost_corners = pieces(
        sites.index,
        streets.to_dict(),
        covered(sites.geometry),
        key,
        lambda name: labels.get(name, ""),
        km.index,
    )
    between = crashes.group.isin(CYCLISTS) & ~crashes.index.isin(at.index)
    areas = {city: km.index[km.index.str.endswith(f"({city})")]} if city else {}
    return {
        "crashes": crashes,
        "at": at,
        "sites": sites.index,
        "streets": streets.to_dict(),
        "corners": corners,
        "km": km,
        "areas": areas,
        "unplaced": {
            "intersections on no mapped corridor": lost_corners,
            "cyclist crashes between corners on no mapped corridor": int(
                (between & crashes.corridor.eq("")).sum()
            ),
            "cyclist crashes between corners": int(between.sum()),
        },
    }


def main() -> None:
    from bike_safety_ca.config import load as load_config
    from bike_safety_ca.io import read_shapes
    from bike_safety_ca.network.area import chosen as chosen_outlines
    from bike_safety_ca.network.streets import path as street_path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthetic", action="store_true", help="use the made-up city")
    parser.add_argument("--config", type=Path, help="city settings (YAML)")
    parser.add_argument("--crashes", type=Path, default=Path("data/processed/crashes"))
    parser.add_argument(
        "--processed",
        type=Path,
        default=Path("data/processed"),
        help="folder holding the built boundaries and network folders",
    )
    parser.add_argument("--ways", type=Path, help="street table (default: the one in --processed)")
    parser.add_argument("--area", type=Path, help="your own outline of the area")
    parser.add_argument("--city-limit", type=Path, help="your own outline scored on its own")
    parser.add_argument("--out", type=Path, help="folder for the hold-out and forecast CSV files")
    args = parser.parse_args()
    if args.synthetic:
        from bike_safety_ca.synthetic import make_city

        data = synthetic_inputs(make_city())
        windows: Sequence[Window] = WINDOWS
        label = "synthetic city"
    else:
        if not args.config:
            parser.error("give --synthetic or --config")
        config = load_config(args.config)
        outlines = chosen_outlines(config, args.processed / "boundaries", args.area)
        ways = args.ways or street_path(args.processed / "network", config.crs)
        if outlines["area"] is None:
            parser.error("no outline of the area: give --area")
        outline = read_shapes(outlines["area"]).to_crs(config.crs).union_all()
        limit_path = args.city_limit or outlines["city_limit"]
        limit = read_shapes(limit_path).to_crs(config.crs).union_all() if limit_path else None
        data = load(config, args.crashes, ways, outline, limit)
        windows, label = config.holdout_windows, config.city
    table = holdout(
        data["crashes"],
        data["at"],
        data["sites"],
        data["streets"],
        data["corners"],
        data["km"],
        windows,
        data["areas"],
    )
    if not args.synthetic:
        table["outcome"] = [age_label(name, config.child_max_age) for name in table.outcome]
    print(f"Corridor hold-out ({label})")
    print(report(table))
    print("\n" + NOTE)
    for what, n in data["unplaced"].items():
        print(f"{what}: {n}")
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        table.to_csv(args.out / "corridor_holdout.csv", index=False)
        methods = []
        for outcome, groups in OUTCOMES.items():
            result = forecast(data, groups)
            methods.append(
                {
                    "outcome": outcome
                    if args.synthetic
                    else age_label(outcome, config.child_max_age),
                    "at corners": result["corner_method"],
                    "between corners": result["between_method"],
                    "fallback reasons": "; ".join(result["reasons"]),
                }
            )
            for area, index in {"All corridors": data["km"].index, **data["areas"]}.items():
                tag = "all" if area == "All corridors" else "city"
                who = "children" if CHILD in groups and len(groups) == 1 else "cyclists"
                forecast_table(result, index).to_csv(
                    args.out / f"corridor_forecast_{who}_{tag}.csv"
                )
        # Which method each forecast table came from, so a fallback is not hidden.
        pd.DataFrame(methods).to_csv(args.out / "corridor_forecast_methods.csv", index=False)
        print(f"\nwrote {args.out}")


def forecast(data: Mapping[str, Any], groups: list[str]) -> dict[str, Any]:
    """The corridor model fitted on every year of crashes, for the forecast table."""
    crashes = data["crashes"]
    sites, index = data["sites"], data["km"].index
    bike_site, bike_between = split(crashes, data["at"], crashes.group.isin(groups), sites, index)
    car_site, car_between = split(crashes, data["at"], crashes.group.eq(CAR), sites, index)
    return score_corridors(
        bike_site, car_site, data["streets"], data["corners"], bike_between, car_between, data["km"]
    )


def synthetic_inputs(city: Any) -> dict[str, Any]:
    """Corridor inputs from the made-up city, whose crashes all sit at intersections."""
    crashes = city.crashes.assign(corridor="")
    at = crashes.site
    km = pd.Series(
        dict.fromkeys(sorted({corridor(n) for s in city.streets.values() for n in s} - {""}), 1.0)
    )
    corners, _ = pieces(city.sites.index, city.streets, pd.Series(dtype=bool), piece(None))
    return {
        "crashes": crashes,
        "at": at,
        "sites": city.sites.index,
        "streets": city.streets,
        "corners": corners,
        "km": km,
        "areas": {},
        "unplaced": {},
    }


if __name__ == "__main__":
    main()
