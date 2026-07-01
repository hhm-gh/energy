# Anthropic API — Notes for This Project

## How Claude is used today

Claude Code (the CLI/IDE tool) is the sole intermediary between this project and Anthropic models. No Python code in the project calls the Anthropic API at runtime — there is no `anthropic` SDK dependency, no `POST /v1/messages` call, nothing in `pyproject.toml` for it. Claude is used only by the developer, interactively, to write and reason about the codebase.

## What explicit API usage would mean

Explicit API usage means the application itself calls Claude at runtime — adding `anthropic` to `pyproject.toml`, importing the SDK in Python, and invoking `client.messages.create(...)` as part of a command or workflow. Claude would then be a component of the running application, not just a development tool.

## When it would make sense for this project

**Natural language queries over local data**
A command like `energy ask "which states had the biggest YoY increase in retail electricity prices?"` could load a Parquet file, send a sample to Claude, and return a plain-English answer — useful when the data shape is complex and writing custom aggregation logic for every question isn't practical.

**Anomaly or pattern narration**
After downloading a bulk dataset, automatically generate a short summary of notable trends (e.g., "EMISS data shows CO₂ from coal dropped 18% in 2023, driven by plant retirements in the Southeast"). Claude reads the numbers; the user gets prose.

**Schema and column interpretation**
EIA datasets often have cryptic column names and codes. Piping a schema and sample rows to Claude could return a human-readable description of what the dataset actually contains — useful as a TUI feature.

**Report generation**
Take multiple downloaded datasets and produce a formatted narrative or markdown report comparing trends across them.

## When it's not worth it

For anything the data can answer mechanically — aggregations, filters, joins, time-series summaries — pandas and Parquet are faster, cheaper, and reproducible. Claude adds value at the interpretation and narration layer, not the computation layer.

The project as designed is a data pipeline. Explicit API use would extend it into a data analyst.
