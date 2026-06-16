import pandas as pd
import pytest

from retail_analytics.basket import pair_rules


def _baskets(rows):
    return pd.DataFrame([(inv, item) for inv, items in rows for item in items], columns=["invoice", "stock_code"])


def test_support_confidence_lift_by_hand():
    b = _baskets([(1, "A B"), (2, "A B"), (3, "A C"), (4, "B C"), (5, "C")])
    b["stock_code"] = b["stock_code"].str.split()
    b = b.explode("stock_code")
    rules = pair_rules(b, min_support=0.0).set_index(["antecedent", "consequent"])
    ab = rules.loc[("A", "B")]
    assert ab["support"] == pytest.approx(2 / 5)
    assert ab["confidence"] == pytest.approx(2 / 3)           # P(B | A)
    assert ab["lift"] == pytest.approx((2 / 3) / (3 / 5))     # / P(B)
    ba = rules.loc[("B", "A")]
    assert ba["lift"] == pytest.approx(ab["lift"])            # lift is symmetric


def test_min_support_filters_rare_pairs():
    b = _baskets([(i, "A B") for i in range(10)] + [(10, "A C")])
    b["stock_code"] = b["stock_code"].str.split()
    b = b.explode("stock_code")
    rules = pair_rules(b, min_support=0.2)
    assert set(zip(rules["antecedent"], rules["consequent"])) == {("A", "B"), ("B", "A")}
