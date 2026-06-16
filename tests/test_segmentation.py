import numpy as np
import pandas as pd

from retail_analytics import segmentation as seg


def test_every_rfm_cell_maps_to_a_named_segment():
    for r in range(1, 6):
        for fm in range(1, 6):
            assert seg.assign_segment(r, fm) in seg.SEGMENT_ORDER


def test_quintiles_survive_heavy_ties():
    s = pd.Series([1] * 80 + list(range(2, 22)))  # 80% of customers bought once
    scores = seg.score_quintiles(s)
    assert set(scores) == {1, 2, 3, 4, 5}
    assert (scores.value_counts() == 20).all()


def test_recency_is_scored_lower_is_better():
    s = pd.Series([1, 10, 100, 1000, 10000])
    assert list(seg.score_quintiles(s, higher_is_better=False)) == [5, 4, 3, 2, 1]


def test_concentration_curve_ends_at_one_and_is_concave():
    curve = seg.concentration(pd.Series([50, 20, 10, 10, 5, 5]))
    assert curve["value_share"].iloc[-1] == 1.0
    assert np.all(np.diff(curve["value_share"]) >= 0)
    assert seg.share_at(curve, 1 / 6) == 0.5


def test_rfm_table_assigns_champions_and_lost():
    rng = np.random.default_rng(1)
    n = 200
    base = pd.DataFrame({
        "customer_id": np.arange(n),
        "recency_days": rng.integers(1, 700, n),
        "frequency": rng.integers(1, 40, n),
        "monetary": rng.gamma(2, 500, n),
    })
    best = base["recency_days"].idxmin()
    base.loc[best, ["frequency", "monetary"]] = [999, 1e6]
    out = seg.rfm_table(base)
    assert out.loc[out["customer_id"] == best, "segment"].iloc[0] == "Champions"
    assert out["segment"].notna().all()
