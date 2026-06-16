import numpy as np
import pandas as pd

from retail_analytics import forecasting as fc


def _series(n=120, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    rev = 100_000 + 30_000 * np.sin(2 * np.pi * t / 52.18) + rng.normal(0, 3_000, n)
    td = np.full(n, 6.0)
    td[[51, 103]] = 0  # closures
    rev[td == 0] = 0
    idx = pd.date_range("2010-01-04", periods=n, freq="W-MON")
    return pd.DataFrame({"revenue": rev, "trading_days": td}, index=idx)


def test_seasonal_naive_repeats_last_year():
    s = _series()
    hist, fut = s.iloc[:100], s.iloc[100:104]
    np.testing.assert_allclose(fc.forecast("seasonal_naive", hist, fut), np.clip(s["revenue"].iloc[48:52], 0, None))


def test_closed_weeks_forecast_zero_and_nothing_negative():
    s = _series()
    hist, fut = s.iloc[:100], s.iloc[100:108]
    for model in fc.MODELS:
        out = fc.forecast(model, hist, fut)
        assert np.all(out >= 0)
        assert out[3] == 0.0  # week 103 is a closure week


def test_harmonic_beats_naive_on_clean_seasonal_signal():
    s = _series()
    scores = fc.score(fc.backtest(s, n_origins=12, horizon=4, models=("harmonic", "drift_naive")))
    assert scores.loc["harmonic", "WAPE (1-4 wk)"] < scores.loc["drift_naive", "WAPE (1-4 wk)"]


def test_backtest_shape():
    s = _series()
    bt = fc.backtest(s, n_origins=5, horizon=3, models=("seasonal_naive",))
    assert len(bt) == 5 * 3
    assert set(bt["step"]) == {1, 2, 3}
