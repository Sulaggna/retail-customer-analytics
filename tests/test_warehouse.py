"""Build the real SQL models against the fixture and check the KPIs reconcile."""

import duckdb
import pytest

from retail_analytics import cleaning, warehouse


@pytest.fixture
def db(raw_sample, tmp_path):
    clean, _ = cleaning.clean(raw_sample)
    pq = tmp_path / "clean.parquet"
    clean.to_parquet(pq, index=False)
    db_path = tmp_path / "wh.duckdb"
    warehouse.build(db_path=db_path, clean_parquet=pq)
    return db_path, clean


def test_all_models_build(db):
    db_path, _ = db
    with duckdb.connect(str(db_path), read_only=True) as con:
        names = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
    for expected in ("fct_order_lines", "fct_orders", "dim_customer", "dim_product", "dim_date",
                     "kpi_monthly", "cohort_retention", "product_performance", "customer_rfm_base"):
        assert expected in names


def test_monthly_net_revenue_reconciles_to_line_level(db):
    db_path, clean = db
    expected = clean.loc[clean["line_type"].isin(["sale", "cancellation"]), "revenue"].sum()
    got = warehouse.query("SELECT SUM(net_revenue) AS v FROM kpi_monthly", db_path=db_path)["v"].iloc[0]
    assert got == pytest.approx(expected)


def test_orders_exclude_cancellations_and_non_products(db):
    db_path, _ = db
    invoices = set(warehouse.query("SELECT invoice FROM fct_orders", db_path=db_path)["invoice"])
    assert invoices == {"536365", "536366", "536400", "536406"}


def test_cohort_month_zero_is_full_retention(db):
    db_path, _ = db
    m0 = warehouse.query("SELECT retention_rate FROM cohort_retention WHERE months_since_first = 0", db_path=db_path)
    assert (m0["retention_rate"] == 1.0).all()


def test_guest_orders_have_no_customer_row(db):
    db_path, _ = db
    n = warehouse.query("SELECT COUNT(*) AS n FROM dim_customer WHERE customer_id IS NULL", db_path=db_path)["n"].iloc[0]
    assert n == 0
