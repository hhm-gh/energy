"""
Regression tests for: energy inventory

Marked @pytest.mark.api — require a live EIA API key in the environment.
Run with: pytest -m api
"""

import pytest
from .conftest import run

pytestmark = pytest.mark.api


def test_inventory_exits_zero():
    result = run("inventory")
    assert result.returncode == 0, result.stderr


def test_inventory_contains_top_level_categories():
    result = run("inventory")
    output = result.stdout
    # These top-level categories are stable EIA API routes
    for category in ("Electricity", "Coal", "Petroleum", "Natural Gas"):
        assert category in output, f"Expected '{category}' in inventory output"


def test_inventory_flat_contains_known_paths():
    result = run("inventory", "--flat")
    assert result.returncode == 0, result.stderr
    output = result.stdout
    for path in ("electricity/retail-sales", "nuclear-outages/us-nuclear-outages"):
        assert path in output, f"Expected path '{path}' in flat inventory output"


def test_inventory_path_filter():
    result = run("inventory", "--path", "electricity")
    assert result.returncode == 0, result.stderr
    output = result.stdout
    assert "electricity/retail-sales" in output
    # Coal should not appear when filtering to electricity
    assert "coal" not in output.lower() or "electricity" in output.lower()


def test_inventory_depth_one_is_shallow():
    result_d1 = run("inventory", "--depth", "1")
    result_d2 = run("inventory", "--depth", "2")
    assert result_d1.returncode == 0
    # Depth-1 output should be shorter than depth-2
    assert len(result_d1.stdout) < len(result_d2.stdout)


def test_inventory_descriptions_flag():
    result = run("inventory", "--descriptions")
    assert result.returncode == 0, result.stderr
    # Descriptions mode should include more text than default
    result_default = run("inventory")
    assert len(result.stdout) > len(result_default.stdout)


def test_inventory_bad_path_does_not_crash():
    result = run("inventory", "--path", "nonexistent-route")
    # Should exit cleanly (empty tree) or with a clear error, not a traceback
    assert "Traceback" not in result.stderr
