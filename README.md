# VAIMEA SPORTS FORECAST — NFL v0.1

An auditable NFL forecasting foundation built on nflverse. Every official forecast is created from an **as-of cutoff**, receives a model version, and is written once to an append-only ledger. The goal of v0.1 is not false precision: it is a forecast that can be reproduced and honestly scored after the fact.

> Status: engineering-ready v0.1. Before publishing 2026 probabilities, run the preseason checklist below, backfill the selected training window and review the walk-forward report. This repository does not claim that an unrun model is calibrated.

## Architecture

```text
nflverse release (source)
  -> data/raw/<UTC snapshot>/       byte-for-byte source files; never overwritten
  -> data/clean/<UTC snapshot>/     selected, typed rows + available_at
  -> data/features/<model>/<cutoff> only information available before cutoff
  -> data/forecast-ledger/          immutable official predictions
  -> public/data/                   latest.json, history.json, movers.json
```

Large raw/clean/features artifacts are intentionally gitignored. Their manifests include source, schema, row count, creation time and SHA-256. Official compact forecasts are committed.

## Model

**Team state.** Offensive and defensive EPA/play are separate latent ratings. Recent games receive exponentially decaying weight (default half-life eight games). Ratings are iteratively opponent-adjusted and empirical-Bayes shrunk toward league average by effective play count. Centering each iteration makes the system identifiable.

**Quarterback.** Dropbacks only. A weighted combination of EPA/dropback (75%) and CPOE (25%, scaled to an EPA-like range) is shrunk toward league average with a 180-dropback prior. A starter can be selected from a verified depth chart or an explicit operator override. v0.1 does not scrape or infer injuries.

**Game context.** Neutral-site-aware home field and capped rest differential are explicit features. The production design must calculate both strictly as of the forecast cutoff.

**Game probability.** L2-regularized logistic regression uses home-minus-away team strength, QB difference, home indicator and rest difference. Coefficients and hyperparameters are fitted using past seasons only. No betting market input is used as a feature; closing-market probability is a valuable *evaluation baseline* when a properly timestamped licensed source is later configured.

**Validation.** `walk_forward` trains on seasons strictly before each test season. Reports include Brier score, log loss, accuracy, decile calibration and a constant-rate baseline. Add Elo and timestamped market baselines before making public skill claims. Compare paired out-of-sample predictions, not training fit.

**Season simulation.** Remaining games are Bernoulli draws from frozen game probabilities. Division champions and wild cards are selected conference-by-conference. v0.1 implements the reliably derivable core order (record, head-to-head proxy, division/conference record, point differential) but deliberately does **not** claim exact NFL tiebreaking: multi-club head-to-head sweeps, common-games eligibility, strength of victory/schedule, combined rankings and coin toss require a richer results graph. Outputs should carry `tiebreaker_mode: approximation_v0.1`. Championship odds are not fabricated until a round-by-round playoff matchup engine is implemented.

## Quick start

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
vaimea download --season 2024 --season 2025
vaimea publish
```

Configuration lives in `config/model.yaml`. Pin the environment (`pip freeze > requirements-lock.txt`) for an official release and record Python, package, config, git commit, input hashes, cutoff and random seed in its run manifest.

## Data contracts and leakage protection

- `available_at` means when a row could first have been used, not when the game occurred.
- Feature builders must call `assert_asof` before aggregating a forecast.
- Never use final season totals, corrected data published after cutoff, future starter information or closing lines for an earlier forecast.
- NFL statistical corrections mean a replay may differ unless the original raw snapshot is retained. That is why raw snapshots are immutable.
- Quality gates stop on missing keys, empty inputs, impossible offense/defense identity and extreme EPA tails. Production should additionally compare row/game counts to rolling expectations and quarantine anomalous snapshots.

## Automated operation

`CI` runs lint and tests. `Update forecasts` is scheduled for Thursday 10:17 UTC, after typical statistical corrections, and can be run manually. The workflow currently performs ingestion, tests and publication; **it intentionally cannot create an official forecast until the operator has supplied/verified the upcoming schedule, starters and trained model artifact.** Add that orchestrated production command only after the 2026 preseason acceptance gate below. GitHub Actions permissions are limited to repository contents.

### 2026 preseason acceptance gate

1. Backfill nflverse seasons in `config/model.yaml`; archive all manifests.
2. Build game-level as-of features after each historical week, never from end-of-season aggregates.
3. Run walk-forward evaluation; publish season-by-season and aggregate metrics plus calibration plots.
4. Add naïve home-rate, previous-season record/Elo and properly timestamped market baselines.
5. Freeze the starter input contract and require a human-reviewed QB override file with timestamp/provenance.
6. Expand simulator tiebreak tests from official NFL examples; label approximations in every JSON response.
7. Train/freeze `model_version`, sign its manifest, dry-run two full weeks, then enable ledger creation.
8. Verify GitHub branch protection and require passing CI for workflow changes.

## Data sources and licenses

- [nflverse data](https://github.com/nflverse/nflverse-data): schedules, play-by-play and derived fields. Follow the license and attribution shipped with each nflverse dataset/repository; nflverse commonly publishes data under CC BY 4.0, but verify the specific release before redistribution.
- NFL team names and marks belong to their respective owners. This project is unaffiliated with the NFL.
- Code in this repository is MIT licensed. The MIT license does not relicense third-party data.

## Forecast JSON contract

Each ledger object contains at minimum `game_id`, teams, kickoff, cutoff, `home_win_probability`, model version, input-manifest hashes, starter provenance and warnings. Files are never replaced. `latest.json` is a view; `history.json` is the audit trail; `movers.json` is the change from the prior official snapshot for the same game.

## Next steps after v0.1

- Exact graph-based NFL tiebreakers and playoff bracket simulation.
- Time-aware hyperparameter selection nested inside walk-forward validation.
- Weather and travel features only from timestamped, stable sources.
- Bayesian hierarchical team/QB state-space model and uncertainty propagation.
- Human-reviewed injury adjustments with a licensed provenance trail—never opaque scraping.
- Static public site with forecast cards, calibration record, methodology and downloadable ledger.
- Monitoring for source schema drift, stale updates, probability drift and calibration degradation.

## Responsible use

Probabilities are estimates, not guarantees or betting advice. Publish the complete historical ledger and failures alongside successes.

