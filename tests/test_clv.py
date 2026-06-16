import numpy as np
import pandas as pd
import pytest

from retail_analytics import clv


def _simulate_bgnbd(r, alpha, a, b, n=6000, seed=0):
    rng = np.random.default_rng(seed)
    T = rng.uniform(10, 52, n)
    lam, p = rng.gamma(r, 1 / alpha, n), rng.beta(a, b, n)
    x, t_x = np.zeros(n), np.zeros(n)
    for i in range(n):
        t = 0.0
        while True:
            t += rng.exponential(1 / lam[i])
            if t > T[i]:
                break
            x[i] += 1
            t_x[i] = t
            if rng.random() < p[i]:
                break
    return x, t_x, T


def test_bgnbd_recovers_known_parameters():
    true = dict(r=0.6, alpha=5.0, a=0.8, b=2.5)
    x, t_x, T = _simulate_bgnbd(**true)
    m = clv.BGNBD().fit(x, t_x, T, penalizer=0.0)
    assert m.r == pytest.approx(true["r"], rel=0.15)
    assert m.alpha == pytest.approx(true["alpha"], rel=0.2)
    assert m.a / (m.a + m.b) == pytest.approx(true["a"] / (true["a"] + true["b"]), rel=0.2)


def test_predictions_are_sane():
    m = clv.BGNBD(r=0.7, alpha=9.0, a=0.15, b=3.2)
    x, t_x, T = np.array([0, 2, 10, 10]), np.array([0, 20, 40, 5]), np.array([50, 50, 50, 50])
    p = m.p_alive(x, t_x, T)
    assert np.all((p >= 0) & (p <= 1))
    assert p[0] == 1.0                      # model assumption: no repeat purchase -> can't have died
    assert p[2] > p[3]                      # same frequency, more recent -> more likely alive
    e26, e52 = m.expected_purchases(26, x, t_x, T), m.expected_purchases(52, x, t_x, T)
    assert np.all(e26 >= 0) and np.all(e52 >= e26)


def test_gamma_gamma_shrinks_toward_population_mean():
    rng = np.random.default_rng(3)
    x = rng.integers(1, 20, 3000).astype(float)
    m = rng.gamma(4, 50, 3000)
    gg = clv.GammaGamma().fit(x, m)
    pop = gg.p * gg.v / (gg.q - 1)
    # one-purchase customers are pulled further toward the mean than 19-purchase customers
    lo, hi = gg.expected_value([1, 19], [10 * pop, 10 * pop])
    assert pop < lo < hi < 10 * pop


def test_rfm_summary_definitions():
    tx = pd.DataFrame({
        "customer_id": [1, 1, 1, 2],
        "purchase_date": pd.to_datetime(["2011-01-03", "2011-01-17", "2011-01-31", "2011-01-10"]),
        "value": [100.0, 50.0, 70.0, 30.0],
    })
    s = clv.rfm_summary(tx, "2011-02-14")
    assert s.loc[1, "x"] == 2 and s.loc[1, "t_x"] == 4 and s.loc[1, "T"] == 6
    assert s.loc[1, "monetary"] == 60.0       # mean of repeat purchases only
    assert s.loc[2, "x"] == 0 and s.loc[2, "monetary"] == 0
