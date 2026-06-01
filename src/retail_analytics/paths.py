"""Single source of truth for file locations, so every module agrees."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

RAW_ZIP = RAW_DIR / "online_retail_ii.zip"
RAW_PARQUET = PROCESSED_DIR / "raw_transactions.parquet"
CLEAN_PARQUET = PROCESSED_DIR / "transactions_clean.parquet"
WAREHOUSE = DATA_DIR / "warehouse.duckdb"

SQL_DIR = ROOT / "sql"
REPORTS_DIR = ROOT / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"
TABLES_DIR = REPORTS_DIR / "tables"
METRICS_JSON = REPORTS_DIR / "metrics.json"
DOCS_DIR = ROOT / "docs"

DATASET_URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"


def ensure_dirs() -> None:
    for d in (RAW_DIR, PROCESSED_DIR, FIGURES_DIR, TABLES_DIR):
        d.mkdir(parents=True, exist_ok=True)
