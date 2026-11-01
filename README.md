# Supplier Scorecard

A small, tested pipeline that scores suppliers from purchase-order history, and a
FastAPI service that exposes it. It is a demonstration of how to replace a
hand-built spreadsheet scoring model with code that is deterministic, explainable
and provably equal to the spreadsheet it replaces.

**All data in this repository is synthetic**, generated from a seed by
`scorecard/generate.py`. It is a self-contained demo project.

## The problem it solves

Many teams score vendors, customers or accounts in a workbook: a few sheets of
lookup bands, nested formulas, and a final weighted score. Such models are hard to
review, hard to rerun on a new month's file, and nobody can say with confidence that
a change did not shift the results.

This project shows the replacement pattern:

1. **Rules live in one config file** (`config/scorecard.yaml`): weights, bands, tiers.
   A reviewer changes a number there, not code.
2. **A pandas pipeline** turns raw purchase orders into five supplier features, scores
   them, and assigns a risk tier. Every intermediate value is kept in the output, so
   any score can be traced step by step.
3. **A parity test proves equivalence.** The test rebuilds the scoring logic as a real
   Excel workbook (approximate-match `VLOOKUP`s, a weighted sum, a tier lookup),
   has LibreOffice calculate it, and checks that Python gives the same answers,
   including values sitting exactly on every band edge.
4. **Bad input fails with a plain message**, not a stack trace.

## Scoring model

| Feature | Meaning | Weight |
|---|---|---|
| `on_time_rate` | share of orders delivered on or before the promised date | 30 |
| `avg_delay_days` | average days late, across late orders only | 15 |
| `fill_rate` | quantity received / quantity ordered | 20 |
| `reject_rate` | quantity rejected on inspection / quantity received | 20 |
| `price_variance` | absolute gap between invoice and expected amount, relative to expected | 15 |

Each feature earns 0 to 100 points from its band table. The overall score is
`sum(weight x points) / 100`, from 0 to 100 (higher is better), mapped to a tier:
Critical, High, Medium or Low. Suppliers with fewer than 5 delivered orders are
reported as **Insufficient data** rather than given a misleading score. Orders with no
delivery date yet are treated as open and left out of every measure.

For each supplier the report also names the **main driver**: the feature that cost the
most points.

## Run it

```bash
pip install -r requirements.txt

# 1. make demo data (200 suppliers, about 7,400 orders)
python -m scorecard.cli generate --out data/orders.csv

# 2. score it into an Excel report
python -m scorecard.cli score --input data/orders.csv --out report.xlsx

# 3. or run the API
uvicorn scorecard.api:app --port 8000
curl -F file=@data/orders.csv "http://localhost:8000/score?top=5"
curl -F file=@data/orders.csv http://localhost:8000/report -o report.xlsx
```

Interactive API docs are at `http://localhost:8000/docs`.

On the default demo data the CLI reports: 88 Low, 39 Medium, 20 High, 41 Critical and
12 Insufficient data.

### Input format

A CSV with these columns: `supplier_id, po_id, promised_date, delivered_date,
qty_ordered, qty_received, qty_rejected, unit_price, invoiced_amount`. Leave
`delivered_date` empty for open orders.

### Report

`report.xlsx` has three sheets: **Summary** (tier counts and weights), **Scores** (every
feature, its points, the score, tier and main driver for every supplier), and
**Exceptions** (Critical and High suppliers).

## Tests

```bash
pytest
```

28 tests cover the feature maths (checked against a hand-calculated supplier), band
boundaries, config validation, determinism, the API, and the Excel parity check. The
parity test needs LibreOffice (`soffice`) and is skipped when it is not installed.

I also checked that the tests can fail: deliberately changing the band-lookup rule
(`side="right"` to `side="left"`) makes the parity test and two others fail.

## Project layout

```
config/scorecard.yaml     weights, bands and tiers: the only place rules live
scorecard/generate.py     seeded synthetic purchase orders
scorecard/features.py     validation and per-supplier features
scorecard/scoring.py      config loading, band lookup, scores, tiers, main driver
scorecard/report.py       Excel report
scorecard/api.py          FastAPI service
scorecard/cli.py          command line
tests/                    unit, API and Excel-parity tests
```

## Design notes

- Band lookup is `numpy.searchsorted(..., side="right")`, which matches an
  approximate-match `VLOOKUP`: a value earns the points of the highest threshold at or
  below it.
- The config loader rejects weights that do not add up to 100, thresholds that are not
  strictly increasing, and points outside 0 to 100, so a typo cannot silently change
  results.
- The same input always produces the same output; the tests check this.
