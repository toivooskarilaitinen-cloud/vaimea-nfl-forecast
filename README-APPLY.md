# SARKA production automation changeset

Target repository: `toivooskarilaitinen-cloud/vaimea-nfl-forecast`

## What this changes

- Adds automatic weekly/daily forecast review packaging from the frozen season forecast input and current nflverse/nfldata schedule.
- Opens/updates a GitHub Issue assigned to the repository owner whenever human QB review is required.
- Changes the approval workflow to require only reviewer name + explicit `APPROVE` confirmation.
- Enforces a hard **T−90 minute FINAL LOCK** at approval time.
- Blocks publication if the live QB differs from the QB used to calculate the probability (`probability must be recomputed`).
- Preserves every approved snapshot in the append-only ledger.
- Changes public `latest.json` to merge the newest official snapshot **per game**, so earlier locked games are not lost when later games receive newer snapshots.
- Adds `updateable` / `final` public lock status and per-game snapshot metadata.
- Closes the QB-review Issue automatically after successful publication.

## Files

Replace these existing files with the versions in this bundle:

- `src/vaimea/operations.py`
- `src/vaimea/publish.py`
- `src/vaimea/cli.py`
- `.github/workflows/update.yml`
- `.github/workflows/approve.yml`
- `docs/KAYTTOOHJE.md`

Add these new files:

- `src/vaimea/production.py`
- `tests/test_production.py`
- `tests/test_publish.py`

## Required validation after applying

```bash
pip install -e ".[dev]"
ruff check src tests
pytest
```

Then manually run **Actions → Update forecasts** once. It should create:

- `data/drafts/latest.json`
- `data/operator/starter-review.json`
- `public/data/review-request.json`
- an Issue titled `SARKA QB review required: Week 1`

Review the QB table. If all rows are correct and no row says `recompute required`, run:

**Actions → Approve official forecast → Run workflow**

Enter reviewer name and type exactly `APPROVE`.

The approval must occur before the earliest game's T−90 final lock. The workflow itself enforces this; it cannot be bypassed by using an old draft.

## Local validation performed in ChatGPT

- New production tests: **7 passed**
- Python syntax compilation: passed
- Workflow YAML parsing: passed
- Direct GitHub commit attempt: blocked by connected GitHub App scope with `403 Resource not accessible by integration`.

No repository content was overwritten by the failed write attempt.
