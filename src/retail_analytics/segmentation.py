"""Customer segmentation: explainable RFM segments, cross-checked with k-means.

RFM is what the CRM team can act on ("email the At Risk segment"); k-means is
the data-driven check that the rule-based segments aren't arbitrary.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from . import warehouse

# Segment rules on the (R, FM) grid, both scored 1-5. Evaluated top to bottom;
# first match wins. Kept as data so the business can review and tweak them.
SEGMENT_RULES: list[tuple[str, tuple[int, int], tuple[int, int]]] = [
    # name,                 R range,  FM range
    ("Champions",           (4, 5),   (4, 5)),
    ("Loyal",               (3, 3),   (4, 5)),
    ("Potential Loyalists", (4, 5),   (2, 3)),
    ("New & Promising",     (4, 5),   (1, 1)),
    ("Needs Attention",     (3, 3),   (2, 3)),
    ("Can't Lose Them",     (1, 2),   (5, 5)),
    ("At Risk",             (1, 2),   (3, 4)),
    ("About to Sleep",      (3, 3),   (1, 1)),
    ("Hibernating / Lost",  (1, 2),   (1, 2)),
]
SEGMENT_ORDER = [s[0] for s in SEGMENT_RULES]

SEGMENT_ACTIONS = {
    "Champions": "Reward & protect: early access, referral asks, no discounts needed.",
    "Loyal": "Upsell premium ranges; loyalty tier; ask for reviews.",
    "Potential Loyalists": "Nudge the 2nd/3rd order: bundles from basket analysis, free-shipping threshold.",
    "New & Promising": "Onboarding series; best-seller recommendations; second-order incentive.",
    "Needs Attention": "Time-limited offer on categories they already buy.",
    "Can't Lose Them": "Personal outreach from account managers — highest revenue at stake.",
    "At Risk": "Win-back campaign before they lapse (90+ days since last order).",
    "About to Sleep": "Low-cost reactivation (newsletter, seasonal catalogue).",
    "Hibernating / Lost": "Suppress from paid channels; occasional low-cost win-back only.",
}


def score_quintiles(s: pd.Series, higher_is_better: bool = True) -> pd.Series:
    """1-5 quintile score. Ranks first so heavy ties (e.g. frequency = 1) don't break qcut."""
    ranks = s.rank(method="first", ascending=higher_is_better)
    return pd.qcut(ranks, 5, labels=[1, 2, 3, 4, 5]).astype(int)


def assign_segment(r: int, fm: int) -> str:
    for name, (r_lo, r_hi), (fm_lo, fm_hi) in SEGMENT_RULES:
        if r_lo <= r <= r_hi and fm_lo <= fm <= fm_hi:
            return name
    return "Hibernating / Lost"


def rfm_table(base: pd.DataFrame | None = None, db=None) -> pd.DataFrame:
    if base is None:
        kw = {"db_path": db} if db else {}
        base = warehouse.table("customer_rfm_base", **kw)
    # Sort first: rank(method="first") breaks ties by row order, and SQL row order
    # isn't guaranteed — without this, segment counts could shift between runs.
    rfm = base.sort_values("customer_id").reset_index(drop=True)
    rfm["R"] = score_quintiles(rfm["recency_days"], higher_is_better=False)
    rfm["F"] = score_quintiles(rfm["frequency"])
    rfm["M"] = score_quintiles(rfm["monetary"])
    rfm["FM"] = np.ceil((rfm["F"] + rfm["M"]) / 2).astype(int)
    rfm["segment"] = [assign_segment(r, fm) for r, fm in zip(rfm["R"], rfm["FM"])]
    rfm["segment"] = pd.Categorical(rfm["segment"], categories=SEGMENT_ORDER, ordered=True)
    return rfm


def segment_summary(rfm: pd.DataFrame) -> pd.DataFrame:
    g = rfm.groupby("segment", observed=True)
    out = pd.DataFrame({
        "customers": g.size(),
        "revenue": g["monetary"].sum(),
        "median_recency_days": g["recency_days"].median(),
        "avg_orders": g["frequency"].mean(),
        "avg_revenue": g["monetary"].mean(),
    })
    out["customer_share"] = out["customers"] / out["customers"].sum()
    out["revenue_share"] = out["revenue"] / out["revenue"].sum()
    out["action"] = out.index.map(SEGMENT_ACTIONS)
    return out


def kmeans_check(rfm: pd.DataFrame, k_range=range(3, 9), seed: int = 42) -> dict:
    """Cluster log-scaled RFM, pick k by silhouette, and cross-tab against RFM segments."""
    X = np.log1p(rfm[["recency_days", "frequency", "monetary"]].clip(lower=0))
    X = StandardScaler().fit_transform(X)
    scores = {}
    for k in k_range:
        labels = KMeans(n_clusters=k, n_init=10, random_state=seed).fit_predict(X)
        scores[k] = silhouette_score(X, labels, sample_size=min(4000, len(X)), random_state=seed)
    best_k = max(scores, key=scores.get)
    km = KMeans(n_clusters=best_k, n_init=10, random_state=seed).fit(X)
    rfm = rfm.assign(cluster=km.labels_)
    profile = rfm.groupby("cluster").agg(
        customers=("customer_id", "size"),
        median_recency=("recency_days", "median"),
        median_orders=("frequency", "median"),
        median_revenue=("monetary", "median"),
    ).sort_values("median_revenue", ascending=False)
    crosstab = pd.crosstab(rfm["segment"], rfm["cluster"], normalize="index")
    return {"silhouette": scores, "best_k": best_k, "profile": profile, "crosstab": crosstab}


def concentration(values: pd.Series) -> pd.DataFrame:
    """Lorenz-style curve: cumulative share of total vs cumulative share of entities (desc)."""
    v = values.sort_values(ascending=False).to_numpy()
    v = v[v > 0]
    return pd.DataFrame({
        "entity_share": np.arange(1, len(v) + 1) / len(v),
        "value_share": np.cumsum(v) / v.sum(),
    })


def share_at(curve: pd.DataFrame, entity_share: float) -> float:
    return float(np.interp(entity_share, curve["entity_share"], curve["value_share"]))
