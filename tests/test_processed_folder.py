"""The hold-out and corridor checks read built outlines and streets from ``--processed``."""

from __future__ import annotations

import shutil
import sys
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
import yaml

from bike_safety_ca import config, demo
from bike_safety_ca.checks import corridors, holdout
from bike_safety_ca.io import read_shapes
from bike_safety_ca.network import area

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = config.load(ROOT / "config" / "demo_claremont.yaml")


@pytest.fixture(scope="module")
def city(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """The demo city built in a folder of its own, with built outlines and a plain config.

    The config names no outline files, so the checks must find the built ones.
    The area is a small part of the demo's, to keep the checks quick.
    """
    assert SETTINGS.area_file is not None and SETTINGS.city_limit_file is not None
    root = tmp_path_factory.mktemp("city")
    processed = demo.build(SETTINGS, root)["crashes"].parents[1]
    whole = read_shapes(SETTINGS.area_file).to_crs(SETTINGS.crs).union_all()
    limit = read_shapes(SETTINGS.city_limit_file).to_crs(SETTINGS.crs).union_all()
    part = whole.centroid.buffer(1500)
    written = area.paths(processed / "boundaries", SETTINGS.crs)
    written["area"].parent.mkdir()
    for kind, shape in (("area", part), ("city_limit", limit.intersection(part))):
        gpd.GeoDataFrame(geometry=[shape], crs=SETTINGS.crs).to_parquet(written[kind])
    raw = yaml.safe_load((ROOT / "config" / "demo_claremont.yaml").read_text())
    plain = {k: v for k, v in raw.items() if not k.endswith("_file")}
    path = root / "plain.yaml"
    path.write_text(yaml.safe_dump(plain))
    assert asdict(config.load(path))["area_file"] is None
    return {"config": path, "processed": processed}


def _run(monkeypatch: pytest.MonkeyPatch, main: Callable[[], None], *arguments: object) -> None:
    monkeypatch.setattr(sys, "argv", ["command", *(str(argument) for argument in arguments)])
    main()


def test_the_holdout_reads_outlines_and_streets_from_the_processed_folder(
    city: dict[str, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)  # no data/processed here: the default folder would not be found
    processed = city["processed"]
    arguments = ["--config", city["config"], "--crashes", processed / "crashes"]
    _run(monkeypatch, holdout.main, *arguments, "--processed", processed, "--out", "named.csv")
    named = pd.read_csv("named.csv")
    # The built city limit was found too: the city is scored on its own.
    assert set(named.area) == {"All intersections", "Claremont"}
    assert named["later crashes"].sum() > 0

    # Without the option the folder is data/processed, as before.
    with pytest.raises(FileNotFoundError):
        _run(monkeypatch, holdout.main, *arguments)
    Path("data").mkdir()
    shutil.copytree(processed, "data/processed")
    _run(monkeypatch, holdout.main, "--config", city["config"], "--out", "default.csv")
    pd.testing.assert_frame_equal(pd.read_csv("default.csv"), named)


def test_the_corridor_check_reads_outlines_and_streets_from_the_processed_folder(
    city: dict[str, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    processed = city["processed"]
    arguments = ["--config", city["config"], "--crashes", processed / "crashes"]
    _run(monkeypatch, corridors.main, *arguments, "--processed", processed, "--out", "named")
    named = pd.read_csv("named/corridor_holdout.csv")
    assert {"All corridors", "Claremont"} <= set(named.area)
    assert Path("named/corridor_forecast_cyclists_city.csv").exists()

    with pytest.raises(FileNotFoundError):
        _run(monkeypatch, corridors.main, *arguments, "--out", "default")
    Path("data").mkdir()
    shutil.copytree(processed, "data/processed")
    _run(monkeypatch, corridors.main, "--config", city["config"], "--out", "default")
    pd.testing.assert_frame_equal(pd.read_csv("default/corridor_holdout.csv"), named)
