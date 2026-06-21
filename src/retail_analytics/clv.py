"""Customer lifetime value with BG/NBD + Gamma-Gamma, written with scipy.

Churn isn't observed in retail, customers just stop ordering. BG/NBD assumes
each customer buys at their own Poisson rate while active and has some chance
of dropping out after every purchase. It only needs frequency (x), recency (t_x)
and age (T) per customer and gives P(alive) and expected future purchases.
Gamma-Gamma models the spend per purchase.

References
    Fader, Hardie & Lee (2005). "Counting Your Customers" the Easy Way: An
        Alternative to the Pareto/NBD Model. Marketing Science 24(2).
    Fader, Hardie & Lee (2005). RFM and CLV: Using Iso-Value Curves for
        Customer Base Analysis. Journal of Marketing Research 42(4).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import gammaln, hyp2f1
from scipy.stats import spearmanr

from . import warehouse

WEEK = 7.0

TRANSACTIONS_SQL = """
SELECT customer_id, date_key AS purchase_date, SUM(order_value) AS value
FROM fct_orders
WHERE customer_id IS NOT NULL AND NOT fully_cancelled
GROUP BY customer_id, date_key
HAVING SUM(order_value) > 0
"""


def load_transactions(db=None) -> pd.DataFrame:
    kw = {"db_path": db} if db else {}
    tx = warehouse.query(TRANSACTIONS_SQL, **kw)
    tx["purchase_date"] = pd.to_datetime(tx["purchase_date"])
    return tx


def rfm_summary(tx: pd.DataFrame, observation_end, start=None) -> pd.DataFrame:
    """Per-customer (x, t_x, T, monetary) in weeks, using purchases up to ``observation_end``.

    x        = number of repeat purchase days (first purchase not counted)
    t_x      = weeks between first and last purchase
    T        = weeks between first purchase and the end of the observation window
    monetary = mean value of the repeat purchases (Gamma-Gamma convention)
    """
    end = pd.Timestamp(observation_end)
    d = tx[tx["purchase_date"] <= end]
    if start is not None:
        d = d[d["purchase_date"] >= pd.Timestamp(start)]
    d = d.sort_values("purchase_date")
    g = d.groupby("customer_id")
    first, last = g["purchase_date"].min(), g["purchase_date"].max()
    n = g.size()
    first_value = g["value"].first()
    total_value = g["value"].sum()
    out = pd.DataFrame({
        "x": (n - 1).astype(float),
        "t_x": (last - first).dt.days / WEEK,
        "T": (end - first).dt.days / WEEK,
    })
    repeat_value = total_value - first_value
    out["monetary"] = np.where(out["x"] > 0, repeat_value / out["x"].replace(0, np.nan), 0.0)
    return out


# BG/NBD
@dataclass
class BGNBD:
    r: float = 1.0
    alpha: float = 1.0
    a: float = 1.0
    b: float = 1.0

    @staticmethod
    def _neg_ll(log_params, x, t_x, T):
        r, alpha, a, b = np.exp(log_params)
        ln_a1 = gammaln(r + x) - gammaln(r) + r * np.log(alpha)
        ln_a2 = gammaln(a + b) + gammaln(b + x) - gammaln(b) - gammaln(a + b + x)
        ln_a3 = -(r + x) * np.log(alpha + T)
        with np.errstate(divide="ignore", invalid="ignore"):
            ln_a4 = np.log(a) - np.log(b + x - 1) - (r + x) * np.log(alpha + t_x)
        ln_a4 = np.where(x > 0, ln_a4, -np.inf)
        ll = ln_a1 + ln_a2 + np.logaddexp(ln_a3, ln_a4)
        return -ll.sum()

    def fit(self, x, t_x, T, penalizer: float = 1e-3) -> "BGNBD":
        """MLE on log-params.

        Without bounds the optimiser runs off to a -> 0, b -> ~1e15, where the
        gammaln differences are just rounding error, so params are kept in
        [1e-4, 8e3]. The small L2 penalty (same idea as the lifetimes package)
        is there because the likelihood is very flat in (a, b) on this data.
        """
        x, t_x, T = (np.asarray(v, dtype=float) for v in (x, t_x, T))

        def objective(lp):
            return self._neg_ll(lp, x, t_x, T) + penalizer * np.sum(np.exp(lp) ** 2)

        bounds = [(-9.0, 9.0)] * 4
        res = minimize(objective, x0=np.zeros(4), method="Nelder-Mead",
                       options={"maxiter": 20000, "xatol": 1e-8, "fatol": 1e-8})
        res = minimize(objective, x0=np.clip(res.x, -9, 9), method="L-BFGS-B", bounds=bounds)
        self.r, self.alpha, self.a, self.b = np.exp(res.x)
        self.converged_ = bool(res.success)
        self.log_likelihood_ = -float(res.fun)
        return self

    def _odds_dead(self, x, t_x, T):
        r, alpha, a, b = self.r, self.alpha, self.a, self.b
        with np.errstate(divide="ignore", invalid="ignore"):
            term = (a / (b + x - 1)) * ((alpha + T) / (alpha + t_x)) ** (r + x)
        return np.where(x > 0, term, 0.0)

    def p_alive(self, x, t_x, T):
        x, t_x, T = (np.asarray(v, dtype=float) for v in (x, t_x, T))
        return 1.0 / (1.0 + self._odds_dead(x, t_x, T))

    def expected_purchases(self, t, x, t_x, T):
        """E[number of purchases in the next t weeks | x, t_x, T]  (FHL 2005, eq. 10)."""
        x, t_x, T = (np.asarray(v, dtype=float) for v in (x, t_x, T))
        r, alpha, a, b = self.r, self.alpha, self.a, self.b
        z = t / (alpha + T + t)
        hyp = hyp2f1(r + x, b + x, a + b + x - 1, z)
        num = (a + b + x - 1) / (a - 1) * (1 - ((alpha + T) / (alpha + T + t)) ** (r + x) * hyp)
        return num / (1.0 + self._odds_dead(x, t_x, T))


# Gamma-Gamma
@dataclass
class GammaGamma:
    p: float = 1.0
    q: float = 1.0
    v: float = 1.0

    @staticmethod
    def _neg_ll(log_params, x, m):
        p, q, v = np.exp(log_params)
        ll = (gammaln(p * x + q) - gammaln(p * x) - gammaln(q) + q * np.log(v)
              + (p * x - 1) * np.log(m) + p * x * np.log(x) - (p * x + q) * np.log(v + m * x))
        return -ll.sum()

    def fit(self, x, monetary) -> "GammaGamma":
        x, m = np.asarray(x, float), np.asarray(monetary, float)
        keep = (x > 0) & (m > 0)
        x, m = x[keep], m[keep]
        res = minimize(self._neg_ll, x0=np.log([1.0, 2.0, np.median(m)]), args=(x, m),
                       method="Nelder-Mead", options={"maxiter": 20000})
        res = minimize(self._neg_ll, x0=res.x, args=(x, m), method="L-BFGS-B",
                       bounds=[(-9.0, 9.0), (np.log(1.0001), 9.0), (-9.0, 12.0)])  # q > 1 keeps E[M] finite
        self.p, self.q, self.v = np.exp(res.x)
        self.converged_ = bool(res.success)
        return self

    def expected_value(self, x, monetary):
        """E[average purchase value | x, m̄]; equals the population mean p·v/(q-1) when x = 0."""
        x, m = np.asarray(x, float), np.asarray(monetary, float)
        return self.p * (self.v + m * x) / (self.p * x + self.q - 1)


def frequency_value_correlation(summary: pd.DataFrame) -> float:
    """Gamma-Gamma assumes spend per purchase doesn't depend on frequency, check it."""
    rep = summary[summary["x"] > 0]
    return float(np.corrcoef(rep["x"], rep["monetary"])[0, 1])


# validation
def holdout_validation(tx: pd.DataFrame, calibration_end="2011-06-09", holdout_end="2011-12-09") -> dict:
    """Fit on purchases up to calibration_end, predict the holdout, compare with actuals.

    Default: calibrate on Dec-2009 to Jun-2011 and hold out the next 26 weeks
    (which includes Q4). 12 months of calibration over-forecasts a lot here, see
    calibration_sensitivity().
    """
    cal_end, hold_end = pd.Timestamp(calibration_end), pd.Timestamp(holdout_end)
    horizon = (hold_end - cal_end).days / WEEK

    cal = rfm_summary(tx, cal_end)
    hold = tx[(tx["purchase_date"] > cal_end) & (tx["purchase_date"] <= hold_end)]
    actual = hold.groupby("customer_id").agg(actual_purchases=("value", "size"), actual_value=("value", "sum"))
    df = cal.join(actual, how="left").fillna({"actual_purchases": 0, "actual_value": 0})

    bg = BGNBD().fit(df["x"], df["t_x"], df["T"])
    gg = GammaGamma().fit(df["x"], df["monetary"])
    df["pred_purchases"] = bg.expected_purchases(horizon, df["x"], df["t_x"], df["T"])
    df["p_alive"] = bg.p_alive(df["x"], df["t_x"], df["T"])
    df["pred_avg_value"] = gg.expected_value(df["x"], df["monetary"])
    df["pred_value"] = df["pred_purchases"] * df["pred_avg_value"]

    # baseline: customer keeps buying at their historical rate
    df["naive_purchases"] = (df["x"] + 1) / df["T"].clip(lower=1) * horizon
    hist_avg = (tx[tx["purchase_date"] <= cal_end].groupby("customer_id")["value"].mean())
    df["naive_value"] = df["naive_purchases"] * hist_avg.reindex(df.index)

    def top_share(score, actual_col, q=0.2):
        cutoff = df[score].quantile(1 - q)
        return df.loc[df[score] >= cutoff, actual_col].sum() / df[actual_col].sum()

    buckets = df.assign(x_bucket=df["x"].clip(upper=10).astype(int)).groupby("x_bucket").agg(
        customers=("x", "size"), actual=("actual_purchases", "mean"),
        bgnbd=("pred_purchases", "mean"), naive=("naive_purchases", "mean"))

    metrics = {
        "customers": int(len(df)),
        "horizon_weeks": round(horizon, 1),
        "actual_total_purchases": int(df["actual_purchases"].sum()),
        "bgnbd_total_purchases": float(df["pred_purchases"].sum()),
        "naive_total_purchases": float(df["naive_purchases"].sum()),
        "bgnbd_mae": float((df["pred_purchases"] - df["actual_purchases"]).abs().mean()),
        "naive_mae": float((df["naive_purchases"] - df["actual_purchases"]).abs().mean()),
        "bgnbd_spearman": float(spearmanr(df["pred_purchases"], df["actual_purchases"]).statistic),
        "naive_spearman": float(spearmanr(df["naive_purchases"], df["actual_purchases"]).statistic),
        "bgnbd_value_top20_capture": float(top_share("pred_value", "actual_value")),
        "naive_value_top20_capture": float(top_share("naive_value", "actual_value")),
        "actual_total_value": float(df["actual_value"].sum()),
        "bgnbd_total_value": float(df["pred_value"].sum()),
        "params_bgnbd": {"r": bg.r, "alpha": bg.alpha, "a": bg.a, "b": bg.b},
        "params_gamma_gamma": {"p": gg.p, "q": gg.q, "v": gg.v},
        "freq_value_corr": frequency_value_correlation(cal),
    }
    return {"metrics": metrics, "buckets": buckets, "frame": df}


def calibration_sensitivity(tx: pd.DataFrame, windows=None) -> pd.DataFrame:
    """Re-run the holdout test for a few calibration lengths.

    With 12 months ending right after the Q4 peak, customers acquired in Q4 look
    like heavy buyers and the next year gets over-forecast. Longer calibration
    mostly fixes it.
    """
    windows = windows or [("2010-12-09", "2011-12-09"), ("2011-03-09", "2011-12-09"), ("2011-06-09", "2011-12-09")]
    rows = []
    for cal_end, hold_end in windows:
        m = holdout_validation(tx, cal_end, hold_end)["metrics"]
        rows.append({
            "calibration": f"Dec-2009 to {pd.Timestamp(cal_end):%b-%Y}",
            "holdout_weeks": m["horizon_weeks"],
            "predicted / actual purchases": m["bgnbd_total_purchases"] / m["actual_total_purchases"],
            "MAE (BG/NBD)": m["bgnbd_mae"],
            "MAE (naive)": m["naive_mae"],
            "rank corr (BG/NBD)": m["bgnbd_spearman"],
        })
    return pd.DataFrame(rows)


def predict_clv(tx: pd.DataFrame, observation_end="2011-12-09", horizon_weeks: float = 52.0) -> pd.DataFrame:
    """Refit on all data and score every customer for the next ``horizon_weeks``."""
    s = rfm_summary(tx, observation_end)
    bg = BGNBD().fit(s["x"], s["t_x"], s["T"])
    gg = GammaGamma().fit(s["x"], s["monetary"])
    s["p_alive"] = bg.p_alive(s["x"], s["t_x"], s["T"])
    s["exp_purchases_12m"] = bg.expected_purchases(horizon_weeks, s["x"], s["t_x"], s["T"])
    s["exp_avg_value"] = gg.expected_value(s["x"], s["monetary"])
    s["clv_12m"] = s["exp_purchases_12m"] * s["exp_avg_value"]
    s.attrs["bgnbd"], s.attrs["gamma_gamma"] = bg, gg
    return s
