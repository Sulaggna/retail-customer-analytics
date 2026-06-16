PY ?= python

.PHONY: install data all test dashboard notebook clean

install:            ## install the package with every extra
	$(PY) -m pip install -e ".[dashboard,notebook,dev]"

data:               ## download UCI Online Retail II and convert to Parquet (~45 MB, once)
	$(PY) -m retail_analytics.ingest

all:                ## full pipeline: clean -> warehouse -> analyses -> figures + metrics.json
	$(PY) -m retail_analytics.pipeline

test:               ## unit tests (no dataset needed)
	$(PY) -m pytest

dashboard:          ## interactive Streamlit dashboard (run `make all` first)
	$(PY) -m streamlit run dashboard/app.py

notebook:           ## re-execute the walkthrough notebook in place
	$(PY) -m jupyter nbconvert --to notebook --execute --inplace notebooks/retail_analytics_walkthrough.ipynb

clean:              ## remove derived data (keeps the downloaded zip)
	rm -rf data/processed data/warehouse.duckdb
