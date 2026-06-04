"""Build the DuckDB warehouse from the SQL models in ``sql/``.

Models are plain ``.sql`` files executed in filename order, so the warehouse is
reproducible and every transformation is reviewable as SQL:

    01-06  staging, dimensions and facts (tables)
    10-17  KPI / analysis views on top of the star schema
"""

from __future__ import annotations

from contextlib import contextmanager

import duckdb
import pandas as pd

from . import paths


def sql_files() -> list:
    return sorted(paths.SQL_DIR.glob("*.sql"))


def build(db_path=paths.WAREHOUSE, clean_parquet=paths.CLEAN_PARQUET) -> list[str]:
    """(Re)create every table and view. Returns the names of the models built."""
    built = []
    with duckdb.connect(str(db_path)) as con:
        for f in sql_files():
            sql = f.read_text().replace("{{clean_parquet}}", str(clean_parquet))
            con.execute(sql)
            built.append(f.stem)
    return built


@contextmanager
def connect(db_path=paths.WAREHOUSE, read_only: bool = True):
    con = duckdb.connect(str(db_path), read_only=read_only)
    try:
        yield con
    finally:
        con.close()


def query(sql: str, db_path=paths.WAREHOUSE) -> pd.DataFrame:
    with connect(db_path) as con:
        return con.execute(sql).df()


def table(name: str, db_path=paths.WAREHOUSE) -> pd.DataFrame:
    return query(f"SELECT * FROM {name}", db_path)
