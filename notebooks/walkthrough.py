"""A walk through the whole analysis, on made-up crashes by default.

Open it with ``uv run marimo edit notebooks/walkthrough.py`` (or ``marimo run``
for a read-only page).  ``python notebooks/walkthrough.py`` runs every cell as
a plain script, which is how the tests check it.
"""

import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium", app_title="Bike Safety Walkthrough")


@app.cell(hide_code=True)
def _():
    from pathlib import Path

    import geopandas as gpd
    import marimo as mo
    import matplotlib

    if not mo.running_in_notebook():
        matplotlib.use("Agg")  # run as a plain script: draw without a window
    import matplotlib.pyplot as plt
    import pandas as pd

    from bike_safety_ca import CAR, CYCLISTS, demo
    from bike_safety_ca import config as settings
    from bike_safety_ca.checks import holdout, reporting
    from bike_safety_ca.io import read_shapes
    from bike_safety_ca.model.crash_history import rank_intersections
    from bike_safety_ca.network import area as outlines
    from bike_safety_ca.network import junctions
    from bike_safety_ca.network import streets as street_table
    from bike_safety_ca.report import crashes as crash_table
    from bike_safety_ca.report import movement, summary

    ROOT = Path(__file__).resolve().parents[1]

    def table(frame: pd.DataFrame) -> mo.ui.table:
        """A plain table showing every row."""
        return mo.ui.table(frame, page_size=40, selection=None, show_column_summaries=False)

    return (
        CAR,
        CYCLISTS,
        ROOT,
        crash_table,
        demo,
        gpd,
        holdout,
        junctions,
        mo,
        movement,
        outlines,
        pd,
        plt,
        rank_intersections,
        read_shapes,
        reporting,
        settings,
        street_table,
        summary,
        table,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # Ranking intersections for bike crash risk: a walkthrough

    This notebook runs the whole analysis in order: the area and its streets,
    the crash tables, a check for changes in police reporting, a test of the
    ranking on years it has not seen, the ranking itself, and a map of how
    each crash happened.

    Every step calls the same code as the command line, so what you see here
    is what `python -m bike_safety_ca...` produces.

    **It starts on a demo city.** The streets are real (Claremont, California,
    from OpenStreetMap). Every crash is made up. That lets you see each step
    work before you have any police records, and it lets the notebook check
    the ranking against the true risk, which real data never allows.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    config_path = mo.ui.text(
        value="config/demo_claremont.yaml", label="City settings file", full_width=True
    )
    processed_path = mo.ui.text(
        value="data/processed",
        label="Folder holding your own city's built tables (not used for the demo)",
        full_width=True,
    )
    mo.vstack(
        [
            mo.md("## 1. Choose the city"),
            config_path,
            processed_path,
            mo.md(
                "Leave these as they are for the demo. For your own city, copy "
                "`config/los_altos.yaml`, edit it, build the tables with the commands in "
                "section 9, and put the file's path and the tables' folder here. Keep "
                "each city's tables in a folder of their own."
            ),
        ]
    )
    return config_path, processed_path


@app.cell(hide_code=True)
def _(ROOT, config_path, mo, processed_path, settings):
    import json

    config = settings.load(ROOT / config_path.value)
    data_root = ROOT / ("data/demo/processed" if config.synthetic else processed_path.value)
    out_root = ROOT / "output" / ("demo" if config.synthetic else "")
    crash_folder = data_root / "crashes"
    # The merge step records which city it built the tables for.
    _report = crash_folder / "crashes_merge_report.json"
    _built = json.loads(_report.read_text()).get("built_for") if _report.exists() else None
    mo.stop(
        not config.synthetic and _built is not None and _built.get("city") != config.city,
        mo.callout(
            mo.md(
                f"The tables in `{crash_folder}` were built for **{_built and _built.get('city')}**, "
                f"not for {config.city}. Point the folder box at this city's tables."
            ),
            kind="danger",
        ),
    )
    if config.synthetic:
        notice = mo.callout(
            mo.md(
                f"**Synthetic data.** The streets of {config.city} are real; every crash "
                "below is made up. Nothing here describes a real crash or a real person."
            ),
            kind="info",
        )
    else:
        notice = mo.callout(
            mo.md(
                f"**Real crash records for {config.city}.** The tables and the map below "
                "include individual crashes. Share them privately, with the local "
                "authority's staff, rather than publish them; tables of totals can be "
                "published with the sources' credits."
            ),
            kind="warn",
        )
    notice
    return config, crash_folder, data_root, out_root


@app.cell(hide_code=True)
def _(config, crash_folder, data_root, demo, mo, outlines, street_table):
    # Demo: build the made-up tables if they are not there yet (a few seconds).
    if config.synthetic and not demo.paths(data_root.parent, config.crs)["truth"].exists():
        demo.build(config, data_root.parent)
    chosen = outlines.chosen(config, data_root / "boundaries")
    ways_path = street_table.path(data_root / "network", config.crs)
    needed = {
        "Area outline": (chosen["area"], "python -m bike_safety_ca.network --config <file>"),
        "Street table": (ways_path, "python -m bike_safety_ca.network --config <file>"),
        "Crash table": (
            crash_folder / f"crashes_merged_{config.crs.rsplit(':', 1)[-1]}.parquet",
            "python -m bike_safety_ca.crashes --config <file>",
        ),
        "Party table": (
            crash_folder / "parties_merged.parquet",
            "python -m bike_safety_ca.crashes --config <file>",
        ),
    }
    missing = [name for name, (path, _) in needed.items() if path is None or not path.exists()]
    checklist = "\n".join(
        f"| {name} | {'ready' if name not in missing else 'missing'} | `{command}` |"
        for name, (_, command) in needed.items()
    )
    mo.stop(
        bool(missing),
        mo.md(
            "## 2. The files this needs\n\n| File | Status | Made by |\n|---|---|---|\n"
            + checklist
            + "\n\nRun the commands for the missing files in a terminal, then rerun this cell. "
            "See docs/guide.md for the TIMS export, which needs a free account."
        ),
    )
    mo.md(
        "## 2. The files this needs\n\n| File | Status | Made by |\n|---|---|---|\n"
        + checklist
        + (
            "\n\nFor the demo these were built just now by `python -m bike_safety_ca.demo`."
            if config.synthetic
            else ""
        )
    )
    return chosen, ways_path


@app.cell(hide_code=True)
def _(chosen, config, gpd, junctions, mo, plt, read_shapes, ways_path):
    outline = read_shapes(chosen["area"]).to_crs(config.crs).union_all()
    limit = (
        read_shapes(chosen["city_limit"]).to_crs(config.crs).union_all()
        if chosen["city_limit"] is not None
        else None
    )
    ways = gpd.read_parquet(ways_path)
    sites, roads = junctions.build_junctions(ways, outline)
    in_city = sites.geometry.within(limit) if limit is not None else sites.major.notna()

    _figure, _axis = plt.subplots(figsize=(7.5, 7.5))
    _streets = ways[ways.highway.isin(junctions.HIGHWAY_RANK) & ways.intersects(outline)]
    _streets.plot(ax=_axis, color="#c9ced6", linewidth=0.5)
    sites.plot(ax=_axis, color="#2f6fb5", markersize=2)
    gpd.GeoSeries([outline]).boundary.plot(ax=_axis, color="#6b7280", linewidth=1, linestyle="--")
    if limit is not None:
        gpd.GeoSeries([limit]).boundary.plot(ax=_axis, color="#1f2328", linewidth=1.4)
    _axis.set_axis_off()
    _axis.set_title(
        f"{config.city}: {len(sites):,} intersections ({int(in_city.sum()):,} inside the city)",
        loc="left",
        fontsize=11,
    )
    _figure.text(
        0.01,
        0.01,
        "Solid line: city limit. Dashed: study area. Streets © OpenStreetMap contributors.",
        fontsize=8,
        color="#6b7280",
    )
    _figure.tight_layout()
    mo.vstack(
        [
            mo.md(
                "## 3. The area and its intersections\n\n"
                "An intersection is a place where three or more street arms meet. "
                "Nearby map nodes are merged, so a divided road crossing a street counts once. "
                "The study area is wider than the city so that streets are not cut off at "
                "the limit."
            ),
            _figure,
        ]
    )
    return in_city, limit, outline, roads, sites, ways


@app.cell(hide_code=True)
def _(config, crash_folder, crash_table, mo, outline, pd, summary, table):
    crashes = crash_table.load(crash_folder, config, outline)
    parties = pd.read_parquet(crash_folder / "parties_merged.parquet")
    mo.vstack(
        [
            mo.md(
                "## 4. The crashes\n\n"
                "Injury crashes with a location, sorted into the groups the ranking uses: "
                f"cyclists {config.child_max_age} or under, older cyclists, and crashes with "
                "motor vehicles only. Car crashes matter because they show where streets "
                "are busy and where drivers collide, even where few people have been "
                "hit on a bike."
            ),
            table(summary.by_year(crashes).rename(index=str).reset_index()),
        ]
    )
    return crashes, parties


@app.cell(hide_code=True)
def _(config, crash_folder, mo, out_root, reporting, table):
    _reports = reporting.load(crash_folder, config.crs, config.first_year)
    _written = reporting.write(_reports, out_root / "reporting", config.synthetic)
    _pictures = {path.stem: path for path in _written if path.suffix == ".png"}
    _found = reporting.diagnose(_reports)
    _flags = _found["injury_crashes_flags"]
    _steps = _found[reporting.STEPS]
    _planted = mo.accordion(
        {
            "What was planted in the demo data": mo.md(
                "- **SYN-C** changes report format in April 2022 and files only three in "
                "ten of its crashes afterwards. The flag table and the format chart "
                "should both show it.\n"
                "- **SYN-B** changes format in mid-2021 with no loss: a change of format "
                "alone is not a problem.\n"
                "- **SYN-A** changes format in 2023 with no loss, but from 2022 grades most "
                '"complaint of pain" injuries as "visible injury". Its total holds; '
                "the severity chart and the table of lasting changes show it."
            )
        }
    )
    mo.vstack(
        [
            mo.md(
                "## 5. Has police reporting changed?\n\n"
                "A ranking built from police reports reads a fall in reports as a fall in "
                "crashes. Check this before comparing years or cities. A year is flagged "
                "when an agency's count is far below or above its own typical year and the "
                "other agencies did not move the same way (a collapse that every agency "
                "shares is still flagged). The `change` column says which "
                'way, and "possible" marks a smaller move that is worth a look.'
                "\n\n**Flagged agency-years (injury crashes)**"
            ),
            table(_flags.astype({"year": str})) if len(_flags) else mo.md("None flagged."),
            mo.image(src=str(_pictures["reports_by_format"]))
            if "reports_by_format" in _pictures
            else mo.md(""),
            mo.image(src=str(_pictures["injury_crashes_by_severity"])),
            mo.md(
                "**Lasting changes of level.** An agency whose yearly count settles at a "
                "new level, in all injury crashes or at one severity, with the typical "
                "year before and after. `regraded` means the agency's other severities "
                "changed the opposite way by about as much."
            ),
            table(_steps.astype({"from_year": str})) if len(_steps) else mo.md("None found."),
            mo.image(src=str(_pictures["injury_crashes"])),
            _planted if config.synthetic else mo.md(""),
            mo.md(
                "A flag is a question to put to the department, not proof: real crashes "
                "can fall too."
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(chosen, config, crash_folder, holdout, mo, table, ways_path):
    _table = holdout.city_holdout(
        config, crash_folder, ways_path, chosen["area"], chosen["city_limit"]
    )
    # Text cells: a period with too few later crashes shows the count, not a score.
    _wide = holdout.wide(_table)
    # With few crashes the street-length model gives way to a simpler blend: say so.
    _fallback = _table[_table.ranking.eq(holdout.MODEL) & _table.method.ne("street-length model")]
    _note = (
        ""
        if _fallback.empty
        else "\n\nThere were too few crashes to fit the street-length model in "
        f"{_fallback[['trained through', 'outcome']].drop_duplicates().shape[0]} of the fits; "
        'those rows labelled "Street-length model" are the hand-built blend instead.\n\n'
        + "\n\n".join(holdout.notes(_table))
    )
    mo.vstack(
        [
            mo.md(
                "## 6. Does the ranking find later crashes?\n\n"
                "Each ranking is built from crashes up to a cut-off year and scored on the "
                "bike crashes after it. The rank score is the chance that an intersection "
                "with a later crash is ranked above one without: 0.5 is a coin toss, 1 is "
                'perfect. "Past bike crashes" is the plain record; the street-length '
                "model also uses car crashes and the crashes along each street. These are "
                "tests on years already seen while the method was built, so they show "
                "that it is reasonable, not how well it will do on new years. A period with "
                f"fewer than {holdout.MIN_LATER} later crashes shows the count in place of "
                'a score. For children, the "All-cyclist ranking" row scores the ranking '
                "built from every cyclist crash on later child crashes; use that ranking "
                "where there are too few child crashes to fit a ranking of their own." + _note
            ),
            table(_wide.reset_index()),
        ]
    )
    return


@app.cell(hide_code=True)
def _(CAR, CYCLISTS, crashes, junctions, rank_intersections, roads, sites):
    # The ranking itself, from every year of crashes.
    hits = junctions.assign_crashes(
        crashes[crashes.group.isin([*CYCLISTS, CAR])], sites.geometry, roads
    )
    bike = junctions.count_at(hits[hits.group.isin(CYCLISTS)], sites.index)
    car = junctions.count_at(hits[hits.group.eq(CAR)], sites.index)
    ranked = rank_intersections(bike, car, roads.to_dict())
    ranking = (
        sites[["name", "major", "minor"]]
        .assign(bike_crashes=bike, car_crashes=car, score=ranked["score"])
        .sort_values("score", ascending=False, kind="stable")  # sort first, round after
        .round({"score": 3})
    )
    return bike, ranked, ranking


@app.cell(hide_code=True)
def _(config, in_city, mo, ranked, ranking, table):
    _top = ranking[in_city.reindex(ranking.index)].head(25).reset_index(drop=True)
    _top.index = _top.index + 1
    _why = "" if ranked["reason"] is None else f" ({ranked['reason']})"
    mo.vstack(
        [
            mo.md(
                f"## 7. The ranking\n\nThe 25 highest-ranked intersections in {config.city}, "
                f"from all years of crashes. Method used: **{ranked['method']}**{_why}. "
                + (
                    "The score is the model's estimate of police-recorded bike crashes over "
                    "the same years; "
                    if ranked["method"] == "street-length model"
                    else "The score only puts the intersections in order; it is not a count. "
                )
                + "A corner can rank high with no bike crash of its own if its streets and "
                "its car crashes point that way."
            ),
            table(_top.reset_index(names="rank")),
        ]
    )
    return


@app.cell(hide_code=True)
def _(bike, config, data_root, gpd, mo, pd, plt, ranked, table):
    mo.stop(not config.synthetic)
    _truth = gpd.read_parquet(data_root / "truth.parquet").bike_rate.reindex(bike.index)
    _score = ranked["score"]
    _found = pd.DataFrame(
        {
            "Past bike crashes": [
                len(set(_truth.nlargest(k).index) & set(bike.astype(float).nlargest(k).index))
                for k in (25, 50, 100)
            ],
            "Street-length model": [
                len(set(_truth.nlargest(k).index) & set(_score.nlargest(k).index))
                for k in (25, 50, 100)
            ],
        },
        index=pd.Index(
            [f"Of the {k} truly riskiest, found in the top {k}" for k in (25, 50, 100)], name=""
        ),
    )
    _corr = {
        "Past bike crashes": bike.corr(_truth, method="spearman"),
        "Street-length model": _score.corr(_truth, method="spearman"),
    }
    _figure, _axes = plt.subplots(1, 2, figsize=(9, 4), sharey=True)
    for _axis, (_label, _values) in zip(
        _axes, {"Past bike crashes": bike, "Street-length model": _score}.items()
    ):
        _axis.scatter(_values, _truth, s=6, alpha=0.4, color="#2f6fb5")
        _axis.set_title(f"{_label} (rank agreement {_corr[_label]:.2f})", fontsize=10, loc="left")
        _axis.set_xlabel(_label)
        _axis.grid(color="#e5e7eb")
        _axis.set_axisbelow(True)
    _axes[0].set_ylabel("True bike crashes per year")
    _figure.suptitle("SYNTHETIC DATA: each dot is an intersection", fontsize=9, x=0.01, ha="left")
    _figure.tight_layout()
    mo.vstack(
        [
            mo.md(
                "### Demo only: checking against the truth\n\n"
                "The demo knows each intersection's true crash rate, so the ranking can be "
                "scored directly. Rank agreement with the truth (1 is perfect, 0 is none) "
                f"is **{_corr['Past bike crashes']:.2f}** for the plain record and "
                f"**{_corr['Street-length model']:.2f}** for the model. At the very top of "
                "the list the two tend to agree, because a corner with many crashes is high "
                "on both. The model's gain is further down, among the many corners with "
                "no bike crash yet, which the plain record cannot tell apart."
            ),
            table(_found.reset_index()),
            _figure,
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    show_map = mo.ui.checkbox(label="Show the map here (it is a few megabytes)")
    return (show_map,)


@app.cell(hide_code=True)
def _(ROOT, config, crashes, gpd, limit, mo, movement, out_root, parties, show_map, ways):
    _centre = gpd.GeoSeries([limit], crs=config.crs) if limit is not None else None
    map_path = movement.build(
        crashes,
        parties[movement.PARTY_COLUMNS],
        ways,
        config,
        out_root / "crash_movement_map.html",
        _centre,
    )
    _privacy = (
        "The demo map shows made-up crashes, so it is safe to pass around."
        if config.synthetic
        else "**The map shows individual crash records. Share it privately; please do not publish it.**"
    )
    mo.vstack(
        [
            mo.md(
                "## 8. How each crash happened\n\n"
                "The movement map draws every cyclist crash with an arrow per party: the "
                "direction the officer recorded, turned to the line of the nearest street, "
                "and what each party was doing. It is for reading crashes one corner at a "
                f"time.\n\nWritten to `{map_path.relative_to(ROOT)}`. Open that file in a browser. {_privacy}"
            ),
            show_map,
            mo.iframe(map_path.read_text(), height="640px") if show_map.value else mo.md(""),
        ]
    )
    return


@app.cell(hide_code=True)
def _(ROOT, config_path, data_root, mo):
    import os

    _folder = os.path.relpath(data_root, ROOT)
    mo.md(f"""
    ## 9. Your own city

    1. Copy `config/los_altos.yaml` to `config/<city>.yaml`. Edit `city`,
       `county`, `crs`, `ccrs_county_code`, `ccrs_cities` and the `latitude`
       and `longitude` box. Delete the settings that are Los Altos's own:
       `agency_reassignments`, `municipality_aliases`, `city_limit_url`,
       `area_schools`, `area_points`, `area_buffer_m` and `osm_date`. Left in,
       they would build your study area around Los Altos.
    2. Build the area and streets: `python -m bike_safety_ca.network --config config/<city>.yaml`
       (downloads Census outlines and OpenStreetMap streets).
    3. Get the crashes. `python -m bike_safety_ca.crashes download --config config/<city>.yaml`
       fetches the CCRS records. The TIMS export is a manual step with a free
       account; docs/guide.md says which files to save and where. Then
       `python -m bike_safety_ca.crashes --config config/<city>.yaml` builds the
       tables. Building from CCRS alone is not supported yet: the merge step
       needs a TIMS export.
    4. Put your config's path in the box at the top of this notebook.

    Start with section 5. If an agency's reporting changed, rank within that
    agency's city, not across cities, and do not compare years across the change.

    Section 7 shows the top of the ranking. To write the whole ranking as a
    CSV and a GeoJSON file from the tables this notebook is reading, run

    ```
    python -m bike_safety_ca.model --config {config_path.value} \\
        --processed {_folder} --crashes {_folder}/crashes
    ```

    Police crash records describe real people. Keep the tables, the ranking's
    crash counts for single corners and the movement map on your own computer,
    and publish totals.
    """)
    return


if __name__ == "__main__":
    app.run()
