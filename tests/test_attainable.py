"""The attainable-score check, on made-up counts only."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from bike_safety_ca import CAR, CYCLISTS
from bike_safety_ca.checks.attainable import attainable, main, rank_scores, share_below, simulate
from bike_safety_ca.model.crash_history import rank_score
from bike_safety_ca.synthetic import make_city


def _sites(n: int = 3000, seed: int = 1) -> pd.DataFrame:
    """A made-up fitted table: expectations, gamma shapes and counts drawn from them."""
    rng = np.random.default_rng(seed)
    predicted = rng.lognormal(-2.0, 1.0, n)
    shape = predicted ** (2 - 1.4) / 0.4
    observed = rng.poisson(rng.gamma(shape, predicted / shape))
    eb = (shape + observed) / (shape / predicted + 1)
    return pd.DataFrame(
        {"observed": observed, "predicted": predicted, "prior_shape": shape, "eb": eb}
    )


def test_many_rank_scores_at_once_match_the_single_one() -> None:
    rng = np.random.default_rng(7)
    score = rng.integers(0, 5, 400).astype(float)  # many ties
    hits = rng.random((6, 400)) < 0.2
    expected = [rank_score(pd.Series(score), pd.Series(row.astype(int))) for row in hits]
    np.testing.assert_allclose(rank_scores(score, hits), expected)


def test_a_draw_with_no_hits_scores_nothing() -> None:
    hits = np.zeros((1, 5), dtype=bool)
    assert np.isnan(rank_scores(np.arange(5.0), hits)[0])


def test_counts_drawn_from_the_models_own_rates_score_inside_the_simulated_range() -> None:
    sites = _sites()
    rng = np.random.default_rng(3)
    rates = rng.gamma(
        sites.prior_shape + sites.observed, 1 / (sites.prior_shape / sites.predicted + 1)
    )
    later = pd.Series(rng.poisson(rates))
    found, sims = simulate(sites, float(later.sum()), draws=400, seed=5)
    real = rank_score(sites.eb, later)
    assert found["simulated 5%"] <= real <= found["simulated 95%"]
    assert len(sims) == 400
    # The best any ranking could do on the draws is at least the model's own score.
    assert found["oracle mean"] >= found["simulated mean"]
    assert abs(found["simulated share hit"] - (later > 0).mean()) < 0.02


def test_the_draws_repeat_with_the_seed() -> None:
    sites = _sites(500)
    first, _ = simulate(sites, 60.0, draws=150, seed=11)
    again, _ = simulate(sites, 60.0, draws=150, seed=11)
    assert first == again


def test_each_window_of_the_synthetic_city_gets_a_row() -> None:
    city = make_city()
    table = attainable(city.crashes, city.sites.index, city.streets, draws=100)
    assert len(table) == 3
    fitted = table[table.method == "street-length model"]
    assert len(fitted) > 0
    assert fitted["simulated mean"].between(0.5, 1).all()
    assert (fitted["simulated 5%"] <= fitted["simulated 95%"]).all()
    assert table["car crashes alone"].between(0, 1).all()


def test_a_window_left_to_the_blend_has_no_simulated_figures() -> None:
    sites = pd.Index(range(50))
    streets = {i: [f"Road {i % 5}"] for i in sites}
    crashes = pd.DataFrame(
        {"site": [1, 2, 3, 4, 5, 6], "year": [2016, 2017, 2018, 2020, 2021, 2023],
         "group": [CYCLISTS[0], CAR, CYCLISTS[0], CYCLISTS[0], CAR, CYCLISTS[0]]}
    )  # fmt: skip
    table = attainable(crashes, sites, streets, windows=[(2018, 2019, None)], draws=10)
    assert table.loc[0, "method"] == "hand-built blend"
    assert "simulated mean" not in table or table["simulated mean"].isna().all()


def test_the_command_runs_on_the_synthetic_city(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "table.csv"
    argv = ["attainable", "--synthetic", "--draws", "50", "--out", str(out)]
    monkeypatch.setattr(sys, "argv", argv)
    main()
    assert "synthetic city" in capsys.readouterr().out
    assert len(pd.read_csv(out)) == 3


def test_the_command_needs_a_city(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["attainable"])
    with pytest.raises(SystemExit):
        main()


def test_draws_with_no_score_are_left_out_of_the_share_below() -> None:
    sims = np.array([0.6, np.nan, 0.8, np.nan])
    assert share_below(sims, 0.7) == 0.5


def test_the_share_below_is_empty_without_a_real_score_or_any_scored_draw() -> None:
    assert np.isnan(share_below(np.array([0.6, 0.8]), float("nan")))
    assert np.isnan(share_below(np.array([np.nan, np.nan]), 0.7))
