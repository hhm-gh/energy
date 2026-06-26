# Run once to install renv and project packages
if (!requireNamespace("renv", quietly = TRUE)) install.packages("renv")
renv::init()
renv::install(c("arrow", "dplyr", "ggplot2", "scales", "lubridate", "jsonlite", "shiny"))
renv::snapshot()
