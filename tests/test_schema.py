"""
Regression tests for: energy schema

Tests are split into two groups:
- Local (no API): use already-cached schema.json and local Parquet
- API (marked @pytest.mark.api): fetch fresh from EIA API

Run local tests only: pytest tests/test_schema.py -m "not api"
Run all tests:        pytest tests/test_schema.py -m api
"""

import json
from pathlib import Path

import pytest
from .conftest import run, REPO_ROOT

RETAIL_SALES_PATH = "electricity/retail-sales"
RETAIL_SALES_SCHEMA = REPO_ROOT / "data" / "electricity" / "retail-sales" / "schema.json"


# ── Local tests (no API required) ────────────────────────────────────────────

@pytest.fixture(scope="module")
def schema_data() -> dict:
    """Load the cached schema for electricity/retail-sales."""
    if not RETAIL_SALES_SCHEMA.exists():
        pytest.skip("electricity/retail-sales schema not cached — run: energy schema electricity/retail-sales")
    return json.loads(RETAIL_SALES_SCHEMA.read_text())


def test_schema_no_args_exits_zero():
    result = run("schema")
    assert result.returncode == 0, result.stderr


def test_schema_no_args_lists_known_paths():
    result = run("schema")
    assert result.returncode == 0
    # electricity/retail-sales has been downloaded — should appear
    assert RETAIL_SALES_PATH in result.stdout


def test_schema_no_args_shows_download_marker():
    result = run("schema")
    # Downloaded datasets are marked with ●
    assert "●" in result.stdout


def test_schema_retail_sales_exits_zero():
    result = run("schema", RETAIL_SALES_PATH)
    assert result.returncode == 0, result.stderr


def test_schema_retail_sales_shows_name():
    result = run("schema", RETAIL_SALES_PATH)
    assert "Electricity Sales to Ultimate Customers" in result.stdout


def test_schema_retail_sales_shows_frequency():
    result = run("schema", RETAIL_SALES_PATH)
    assert "monthly" in result.stdout


def test_schema_retail_sales_shows_price_column():
    result = run("schema", RETAIL_SALES_PATH)
    assert "price" in result.stdout
    assert "cents per kilowatt-hour" in result.stdout


def test_schema_retail_sales_shows_nonzero_stats():
    result = run("schema", RETAIL_SALES_PATH)
    # Rich may wrap column headers across lines, so check for the marker text
    assert "(>0)" in result.stdout


def test_schema_retail_sales_shows_state_facet():
    result = run("schema", RETAIL_SALES_PATH)
    assert "stateid" in result.stdout


def test_schema_cached_data_structure(schema_data):
    assert "name" in schema_data
    assert "frequencies" in schema_data
    assert "facets" in schema_data
    assert "columns" in schema_data
    local = schema_data.get("local_stats", {})
    assert local.get("rows", 0) > 0
    assert "period_actual_start" in local
    assert "column_stats" in local


def test_schema_nonexistent_path_fails_cleanly():
    result = run("schema", "nonexistent/path")
    assert result.returncode != 0
    assert "Traceback" not in result.stderr


# ── API tests ─────────────────────────────────────────────────────────────────

@pytest.mark.api
def test_schema_api_fetch_uncached_path():
    """Fetch schema for a path not previously cached."""
    result = run("schema", "nuclear-outages/us-nuclear-outages")
    assert result.returncode == 0, result.stderr
    assert "Nuclear" in result.stdout
    assert "daily" in result.stdout


@pytest.mark.api
def test_schema_refresh_flag():
    result = run("schema", RETAIL_SALES_PATH, "--refresh")
    assert result.returncode == 0, result.stderr
    assert "Electricity Sales to Ultimate Customers" in result.stdout
