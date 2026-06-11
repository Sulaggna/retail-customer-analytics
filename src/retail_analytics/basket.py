"""Market-basket analysis: which products are bought together?

Pairwise association rules computed with one sparse matrix product instead of
an iterative Apriori loop: with an invoice x product incidence matrix X,
``X.T @ X`` gives every pair's co-occurrence count in a single pass.

    support(A,B)      share of baskets containing both A and B
    confidence(A->B)  P(B in basket | A in basket)
    lift(A->B)        confidence / support(B); > 1 means "bought together more than chance"
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import sparse

from . import warehouse

BASKETS_SQL = """
SELECT l.invoice, l.stock_code
FROM fct_order_lines l
JOIN fct_orders o USING (invoice)
WHERE l.line_type = 'sale' AND NOT o.fully_cancelled
GROUP BY l.invoice, l.stock_code
"""


def load_baskets(db=None) -> pd.DataFrame:
    kw = {"db_path": db} if db else {}
    return warehouse.query(BASKETS_SQL, **kw)


def pair_rules(baskets: pd.DataFrame, min_support: float = 0.01, min_confidence: float = 0.0,
               min_item_support: float | None = None) -> pd.DataFrame:
    """All A->B rules whose pair support clears ``min_support``.

    ``baskets`` has one row per (invoice, item). Items below ``min_item_support``
    (defaults to ``min_support``) are dropped first: a pair can't be more frequent
    than its rarer item, so this pruning is lossless (the Apriori property).
    """
    min_item_support = min_support if min_item_support is None else min_item_support
    n_baskets = baskets["invoice"].nunique()
    item_counts = baskets["stock_code"].value_counts()
    keep = item_counts[item_counts / n_baskets >= min_item_support].index
    b = baskets[baskets["stock_code"].isin(keep)]

    inv_codes, inv_idx = np.unique(b["invoice"].to_numpy(), return_inverse=True)
    item_codes, item_idx = np.unique(b["stock_code"].to_numpy(), return_inverse=True)
    X = sparse.csr_matrix((np.ones(len(b), dtype=np.float32), (inv_idx, item_idx)),
                          shape=(len(inv_codes), len(item_codes)))
    co = (X.T @ X).tocoo()
    item_support = np.asarray(X.sum(axis=0)).ravel() / n_baskets

    mask = co.row != co.col
    pairs = pd.DataFrame({"a": co.row[mask], "b": co.col[mask], "count": co.data[mask]})
    pairs["support"] = pairs["count"] / n_baskets
    pairs = pairs[pairs["support"] >= min_support].copy()
    pairs["support_a"] = item_support[pairs["a"]]
    pairs["support_b"] = item_support[pairs["b"]]
    pairs["confidence"] = pairs["support"] / pairs["support_a"]
    pairs["lift"] = pairs["confidence"] / pairs["support_b"]
    pairs["leverage"] = pairs["support"] - pairs["support_a"] * pairs["support_b"]
    pairs["antecedent"] = item_codes[pairs["a"]]
    pairs["consequent"] = item_codes[pairs["b"]]
    pairs = pairs[pairs["confidence"] >= min_confidence]
    cols = ["antecedent", "consequent", "count", "support", "confidence", "lift", "leverage"]
    out = pairs[cols].sort_values("lift", ascending=False).reset_index(drop=True)
    out["count"] = out["count"].astype(int)
    out.attrs["n_baskets"] = n_baskets
    return out


def add_descriptions(rules: pd.DataFrame, db=None) -> pd.DataFrame:
    kw = {"db_path": db} if db else {}
    names = warehouse.query("SELECT stock_code, description FROM dim_product", **kw).set_index("stock_code")["description"]
    rules = rules.copy()
    rules.insert(1, "antecedent_name", rules["antecedent"].map(names))
    rules.insert(3, "consequent_name", rules["consequent"].map(names))
    return rules


def dedupe_symmetric(rules: pd.DataFrame) -> pd.DataFrame:
    """A->B and B->A share support and lift; keep the direction with higher confidence."""
    key = rules.apply(lambda r: tuple(sorted((r["antecedent"], r["consequent"]))), axis=1)
    return (rules.assign(_k=key).sort_values("confidence", ascending=False)
            .drop_duplicates("_k").drop(columns="_k").sort_values("lift", ascending=False)
            .reset_index(drop=True))


def same_collection_share(rules: pd.DataFrame) -> float:
    """Share of rules whose two products share a design name (e.g. PINK vs GREEN REGENCY TEACUP).

    Heuristic: strip colour words and compare the remaining words."""
    colours = {"RED", "PINK", "BLUE", "GREEN", "WHITE", "BLACK", "IVORY", "CREAM", "PURPLE", "YELLOW",
               "ORANGE", "SILVER", "GOLD", "ROSES", "SPOTTY", "RETROSPOT"}

    def core(name):
        return frozenset(w for w in str(name).upper().replace(",", " ").split() if w not in colours)

    same = [len(core(a) & core(b)) >= 2 for a, b in zip(rules["antecedent_name"], rules["consequent_name"])]
    return float(np.mean(same)) if len(same) else float("nan")
