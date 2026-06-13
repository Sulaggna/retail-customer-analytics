"""Weekly revenue forecasting with an honest, rolling-origin backtest.

With ~2 years of weekly data the interesting question isn't "which fancy model
wins" but "does anything beat the obvious baselines, and by how much?". So
every model is scored the same way: refit at each origin on data available at
that time, forecast 1-4 weeks ahead, compare to what actually happened.

Models
    seasonal_naive   same ISO week last year
    drift_naive      last 4-week average (a 'run-rate' baseline)
    ets              Holt's damped trend (statsmodels ExponentialSmoothing), no seasonality
    harmonic         OLS on trend + yearly Fourier terms + trading-days regressor
    ensemble         simple average of seasonal_naive and harmonic

Christmas closures (shop shut ~23 Dec - 4 Jan) mean some weeks have 0-3
trading days; ``trading_days`` is known in advance, so it is a legitimate regressor.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from . import warehouse

WEEKLY_SQL = """
SELECT DATE_TRUNC('week', date_key)::DATE AS week_start,
       SUM(revenue)                        AS revenue,
       COUNT(DISTINCT date_key)            AS trading_days
FROM fct_order_lines
GROUP BY 1 ORDER BY 1
"""

PERIOD = 52.18  # average weeks per year


def weekly_series(db=None) -> pd.DataFrame:
    """Complete Monday-start weekly series. Closure weeks get revenue 0, trading_days 0.
    The final week is partial (data ends Friday 9 Dec 2011 at lunchtime) and is dropped."""
    kw = {"db_path": db} if db else {}
    w = warehouse.query(WEEKLY_SQL, **kw)
    w["week_start"] = pd.to_datetime(w["week_start"])
    full = pd.date_range(w["week_start"].min(), w["week_start"].max(), freq="W-MON")
    w = w.set_index("week_start").reindex(full).fillna({"revenue": 0.0, "trading_days": 0})
    w.index.name = "week_start"
    return w.iloc[:-1]


def _fourier(t: np.ndarray, k: int) -> np.ndarray:
    cols = []
    for i in range(1, k + 1):
        cols += [np.sin(2 * np.pi * i * t / PERIOD), np.cos(2 * np.pi * i * t / PERIOD)]
    return np.column_stack(cols)


def _design(t: np.ndarray, trading_days: np.ndarray, k: int) -> np.ndarray:
    td = trading_days / 6.0  # the shop trades 6 days a week (closed Saturdays)
    return np.column_stack([np.ones_like(t, dtype=float), t / 52.0, td, _fourier(t, k)])


def forecast(model: str, history: pd.DataFrame, future: pd.DataFrame, k: int = 4) -> np.ndarray:
    """Forecast ``len(future)`` weeks after ``history``. ``future`` supplies known trading days.

    Weeks with no trading days (Christmas closure) are forecast as exactly 0, and
    no forecast is allowed to go negative."""
    fc = _raw_forecast(model, history, future, k)
    closed = future["trading_days"].to_numpy() == 0
    return np.where(closed, 0.0, np.clip(fc, 0.0, None))


def _raw_forecast(model: str, history: pd.DataFrame, future: pd.DataFrame, k: int) -> np.ndarray:
    y = history["revenue"].to_numpy()
    h = len(future)
    if model == "seasonal_naive":
        idx = np.arange(len(history), len(history) + h) - 52
        return y[idx]
    if model == "drift_naive":
        open_weeks = history.loc[history["trading_days"] >= 5, "revenue"]
        per_day = open_weeks.iloc[-4:].mean() / 6.0
        return per_day * future["trading_days"].to_numpy()
    if model == "ets":
        per_day = y / np.maximum(history["trading_days"].to_numpy(), 1)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fit = ExponentialSmoothing(per_day, trend="add", damped_trend=True).fit()
        return fit.forecast(h) * future["trading_days"].to_numpy()
    if model == "harmonic":
        t_hist = np.arange(len(history), dtype=float)
        t_fut = np.arange(len(history), len(history) + h, dtype=float)
        X = _design(t_hist, history["trading_days"].to_numpy(), k)
        fit = sm.OLS(y, X).fit()
        return fit.predict(_design(t_fut, future["trading_days"].to_numpy(), k))
    if model == "ensemble":
        return 0.5 * (_raw_forecast("seasonal_naive", history, future, k)
                      + _raw_forecast("harmonic", history, future, k))
    raise ValueError(f"unknown model {model!r}")


MODELS = ("seasonal_naive", "drift_naive", "ets", "harmonic", "ensemble")


def backtest(series: pd.DataFrame, n_origins: int = 26, horizon: int = 4, models=MODELS) -> pd.DataFrame:
    """Rolling-origin evaluation over the last ``n_origins`` weeks.

    Returns one row per (model, origin, step) with actual and forecast values.
    """
    rows = []
    last_origin = len(series) - horizon
    for origin in range(last_origin - n_origins + 1, last_origin + 1):
        hist, fut = series.iloc[:origin], series.iloc[origin:origin + horizon]
        for m in models:
            fc = forecast(m, hist, fut)
            for step, (week, actual, pred) in enumerate(zip(fut.index, fut["revenue"], fc), start=1):
                rows.append({"model": m, "origin": series.index[origin], "week": week,
                             "step": step, "actual": actual, "forecast": float(pred)})
    return pd.DataFrame(rows)


def score(bt: pd.DataFrame) -> pd.DataFrame:
    """WAPE (weighted absolute % error) and bias, overall and for the 1-week-ahead horizon."""
    def wape(d):
        return (d["forecast"] - d["actual"]).abs().sum() / d["actual"].abs().sum()

    def bias(d):
        return (d["forecast"] - d["actual"]).sum() / d["actual"].sum()

    out = bt.groupby("model").apply(lambda d: pd.Series({
        "WAPE (1-4 wk)": wape(d),
        "WAPE (1 wk)": wape(d[d["step"] == 1]),
        "Bias": bias(d),
    }), include_groups=False)
    return out.sort_values("WAPE (1-4 wk)")


def final_forecast(series: pd.DataFrame, weeks: int = 8, model: str = "ensemble",
                   interval: float = 0.8) -> pd.DataFrame:
    """Forecast beyond the data with an empirical prediction interval from backtest residuals."""
    future_idx = pd.date_range(series.index[-1] + pd.Timedelta(weeks=1), periods=weeks, freq="W-MON")
    # Trading days for the future weeks: repeat the pattern of the same weeks last year.
    last_year = series["trading_days"].iloc[-52:].to_numpy()
    future = pd.DataFrame({"trading_days": last_year[:weeks]}, index=future_idx)
    point = forecast(model, series, future)
    bt = backtest(series, n_origins=26, horizon=1, models=(model,))
    bt = bt[bt["forecast"] > 0]
    rel = (bt["actual"] - bt["forecast"]) / bt["forecast"]
    lo, hi = np.quantile(rel, [(1 - interval) / 2, 1 - (1 - interval) / 2])
    return pd.DataFrame({"forecast": point, "lower": point * (1 + lo), "upper": point * (1 + hi),
                         "trading_days": future["trading_days"]}, index=future_idx)
