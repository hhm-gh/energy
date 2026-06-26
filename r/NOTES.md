# R / Shiny app — developer notes

## Launch

1. Open `r/energy.Rproj` in RStudio — this sets the working directory to `r/`
2. Run `source("setup.R")` once to install packages via renv
3. Open `app.R` → click **Run App**

## Files

| File | Purpose |
|------|---------|
| `app.R` | Shiny app — state selector + box-and-whisker plot |
| `load.R` | Helper functions: `catalog()`, `load_dataset("path")` |
| `setup.R` | One-time package install via renv |
| `energy.Rproj` | RStudio project file |

## Data path convention

The `data/` directory lives at the repo root, one level above `r/`. All R files resolve it as:

```r
DATA_ROOT <- file.path(dirname(getwd()), "data")
```

This works because RStudio sets `getwd()` to the `.Rproj` directory (`r/`) on project open.

## app.R — current features

- Sector dropdown: residential, commercial, industrial, all sectors, other, transportation
- State checklist: scrollable, all 62 states/territories, **All** / **Clear** buttons
- Box plot sorted by median price (highest at top), monthly data 2001–present
- Source: `data/electricity/retail-sales/data.parquet`

## Packages

| Package | Use |
|---------|-----|
| `arrow` | Read Parquet files |
| `dplyr` | Data filtering and aggregation |
| `ggplot2` | Box plot rendering |
| `scales` | Axis label formatting (¢ suffix) |
| `shiny` | Interactive UI |
| `jsonlite` | Read dataset metadata JSON |
| `lubridate` | Date handling (available, not yet used in app) |
