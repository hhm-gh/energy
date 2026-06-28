# Testing

## Design

Tests are CLI-level regression tests — they invoke the `energy` command as a subprocess and assert on exit codes and output content. This tests the full stack (argument parsing, module imports, API calls, output formatting) rather than individual units, which means a passing test suite confirms the commands actually work end-to-end.

Tests are split into two groups by a pytest marker:

| Group | Marker | When to run |
|-------|--------|-------------|
| Local | *(no marker)* | Any time — no network, reads from local cache |
| API | `@pytest.mark.api` | Before shipping — requires live EIA API and Keychain key |

```bash
pytest -m "not api"   # local tests only (~3s)
pytest -m api         # all tests, including live API calls (~45s)
```

## Files

| File | Purpose |
|------|---------|
| `tests/conftest.py` | Shared `run()` helper — invokes CLI as subprocess from repo root |
| `tests/test_inventory.py` | Regression tests for `energy inventory` |
| `tests/test_schema.py` | Regression tests for `energy schema` |

## Test coverage

### `energy inventory` (all API-dependent)

| Test | What it checks |
|------|---------------|
| `test_inventory_exits_zero` | Command returns exit code 0 |
| `test_inventory_contains_top_level_categories` | Output includes Electricity, Coal, Petroleum, Natural Gas |
| `test_inventory_flat_contains_known_paths` | `--flat` output includes known leaf paths |
| `test_inventory_path_filter` | `--path electricity` scopes output correctly |
| `test_inventory_depth_one_is_shallow` | `--depth 1` produces less output than `--depth 2` |
| `test_inventory_descriptions_flag` | `--descriptions` produces more output than default |
| `test_inventory_bad_path_does_not_crash` | Unknown path exits cleanly, no traceback |

### `energy schema` (local unless marked)

| Test | API? | What it checks |
|------|------|---------------|
| `test_schema_no_args_exits_zero` | No | No-arg form exits 0 |
| `test_schema_no_args_lists_known_paths` | No | `electricity/retail-sales` appears in path list |
| `test_schema_no_args_shows_download_marker` | No | Downloaded datasets show `●` marker |
| `test_schema_retail_sales_exits_zero` | No | Command exits 0 for downloaded dataset |
| `test_schema_retail_sales_shows_name` | No | Full dataset name appears in output |
| `test_schema_retail_sales_shows_frequency` | No | `monthly` frequency appears |
| `test_schema_retail_sales_shows_price_column` | No | `price` column and units appear |
| `test_schema_retail_sales_shows_nonzero_stats` | No | `(>0)` column headers appear |
| `test_schema_retail_sales_shows_state_facet` | No | `stateid` facet appears |
| `test_schema_cached_data_structure` | No | `schema.json` has expected keys and non-zero row count |
| `test_schema_nonexistent_path_fails_cleanly` | No | Bad path exits non-zero, no traceback |
| `test_schema_api_fetch_uncached_path` | **Yes** | Fresh API fetch for `nuclear-outages/us-nuclear-outages` |
| `test_schema_refresh_flag` | **Yes** | `--refresh` re-fetches and still shows correct output |

## Last run — 2026-06-27

```
pytest -m "not api"
11 passed in 1.66s

pytest -m api
9 passed in 41.03s

Total: 20 passed, 0 failed
```

## Not yet covered

The following commands added after the last test run have no automated tests:

| Command group | Notes |
|--------------|-------|
| `energy pub-list`, `pub-download`, `pub-status` | Excel publication commands — would benefit from a `tests/test_publications.py` with a local fixture xlsx and a live download test marked `@pytest.mark.api` |
| `energy bulk-list` | Bulk manifest listing — network-dependent; a `@pytest.mark.api` test asserting known dataset IDs (e.g. `ELEC`, `NG`) appear in output would suffice |

## Notes

- Rich wraps long column headers across lines in narrow terminals. Tests check for sub-strings (e.g. `"(>0)"`) rather than full header strings to avoid brittle terminal-width dependencies.
- Local schema tests require `data/electricity/retail-sales/schema.json` to exist. If it is missing, the fixture calls `pytest.skip()` with instructions to run `energy schema electricity/retail-sales` first.
- API tests require the EIA API key to be present in macOS Keychain (`security find-generic-password -a eia -s eia-api-key -w`).
