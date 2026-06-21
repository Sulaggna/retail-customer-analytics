"""Download the UCI Online Retail II workbook and save it as parquet.

Parsing the xlsx (two sheets, 2009-2010 and 2010-2011) takes ~30s, so it's done
once here and everything downstream reads the parquet file.

    python -m retail_analytics.ingest
"""

from __future__ import annotations

import io
import urllib.request
import zipfile

import pandas as pd

from . import paths

RAW_COLUMNS = {
    "Invoice": "invoice",
    "StockCode": "stock_code",
    "Description": "description",
    "Quantity": "quantity",
    "InvoiceDate": "invoice_date",
    "Price": "unit_price",
    "Customer ID": "customer_id",
    "Country": "country",
}


def download(force: bool = False) -> None:
    """Fetch the zip from UCI (CC BY 4.0) if it isn't there already."""
    paths.ensure_dirs()
    if paths.RAW_ZIP.exists() and not force:
        return
    print(f"Downloading {paths.DATASET_URL} ...")
    urllib.request.urlretrieve(paths.DATASET_URL, paths.RAW_ZIP)


def read_workbook() -> pd.DataFrame:
    """Read both sheets into one frame with snake_case columns."""
    with zipfile.ZipFile(paths.RAW_ZIP) as zf:
        xlsx_name = next(n for n in zf.namelist() if n.endswith(".xlsx"))
        payload = io.BytesIO(zf.read(xlsx_name))

    # read as text first - otherwise pandas guesses types per cell and codes like
    # 85123 / 85123A come out as int and str
    sheets = pd.read_excel(payload, sheet_name=None, dtype=str, engine="openpyxl")
    frames = []
    for sheet_name, df in sheets.items():
        df = df.rename(columns=RAW_COLUMNS)
        df["source_sheet"] = sheet_name
        frames.append(df)
    raw = pd.concat(frames, ignore_index=True)

    raw["quantity"] = pd.to_numeric(raw["quantity"], errors="coerce").astype("Int64")
    raw["unit_price"] = pd.to_numeric(raw["unit_price"], errors="coerce")
    raw["invoice_date"] = pd.to_datetime(raw["invoice_date"], errors="coerce")
    # customer ids come through as "13085.0"
    raw["customer_id"] = pd.to_numeric(raw["customer_id"], errors="coerce").astype("Int64")
    for col in ("invoice", "stock_code", "description", "country"):
        raw[col] = raw[col].astype("string").str.strip()
    return raw


def main() -> None:
    download()
    raw = read_workbook()
    raw.to_parquet(paths.RAW_PARQUET, index=False)
    print(f"Wrote {len(raw):,} rows -> {paths.RAW_PARQUET.relative_to(paths.ROOT)}")


if __name__ == "__main__":
    main()
