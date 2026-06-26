library(arrow)
library(dplyr)
library(ggplot2)
library(scales)
library(lubridate)

# Root of the data directory (relative to the r/ folder)
DATA_ROOT <- file.path(dirname(getwd()), "data")

# List all downloaded datasets from the catalog
catalog <- function() {
  catalog_path <- file.path(DATA_ROOT, "catalog.json")
  if (!file.exists(catalog_path)) stop("No datasets downloaded yet. Run: energy download <path>")
  jsonlite::fromJSON(catalog_path, simplifyDataFrame = FALSE)
}

# Load a dataset by its EIA path, e.g. "electricity/retail-sales"
load_dataset <- function(path) {
  parquet_path <- file.path(DATA_ROOT, path, "data.parquet")
  meta_path    <- file.path(DATA_ROOT, path, "metadata.json")

  if (!file.exists(parquet_path)) {
    stop(paste0("Dataset not downloaded. Run: energy download ", path))
  }

  df   <- read_parquet(parquet_path)
  meta <- jsonlite::fromJSON(meta_path)

  message(sprintf("Loaded '%s'  |  %s rows  |  frequency: %s  |  downloaded: %s",
                  meta$name, nrow(df), meta$frequency,
                  substr(meta$downloaded_at, 1, 10)))
  df
}
