# Contributing

Changes that affect probabilities must include a leakage-focused test, walk-forward comparison and model-version decision. Never rewrite files in `data/forecast-ledger`. Data-source changes require license, availability timestamp and schema-drift documentation. Run `ruff check src tests` and `pytest` before opening a pull request.

