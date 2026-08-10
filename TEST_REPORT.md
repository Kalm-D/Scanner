# Stock System Cloud v0.1 — Test Report

Build date: 2026-08-10

## Baseline

- Tracker: `Tracker_v2.0.1_COMPLETE_FULL.zip`
- Alpha Stock: `Alpha_Stock_v1.20_PRO_COMPLETE.zip`
- Hai ZIP gốc không bị chỉnh sửa; cloud package được dựng trên bản sao.

## 1. Python EOD engine

**PASS — 9/9 unit tests**

- ticker stock-only filter
- exchange normalization (HSX/HNX/UPCOM aliases)
- thousand-VND price scaling
- illiquid zero-OHLC sanitization
- incremental merge + duplicate replacement
- rolling session retention
- validator accepts valid synthetic market
- validator rejects undersized universe
- output contract + retry cache fast path

Command:

```bash
python -m unittest discover -s tests -v
```

## 2. Python syntax

**PASS**

`src/cloud_eod.py` compiles with `py_compile`.

## 3. HTML / JavaScript static parsing

**PASS**

- Tracker executable inline scripts parse with Node `--check`.
- Alpha Stock executable inline scripts parse with Node `--check`.
- Cloud landing page executable script parses with Node `--check`.

## 4. Cloud auto-loader contract

**PASS (mock network)**

For both Tracker and Alpha Stock, mocked `status.json + market_history.csv` successfully:

- parse cloud CSV
- set `state.rawRows`
- set source to `Cloud EOD • <market_date>`
- call the existing `runScreener()` pipeline
- leave manual CSV/demo paths intact as fallback

## 5. GitHub Actions workflow

**STATIC PASS**

Workflow includes:

- manual `workflow_dispatch`
- timezone-aware schedules 16:20 / 16:45 / 17:10 Asia/Ho_Chi_Minh
- Python 3.12
- dependency cache
- 9 unit tests before market update
- persistent rolling EOD state via Actions cache
- `--require-today` freshness gate for scheduled runs
- fast-path skip when today's state already succeeded; duplicate retry caches are skipped
- Pages artifact upload + deploy only after successful build

## 6. Data safety gates

Implemented:

- required schema validation
- ticker/date duplicate validation
- OHLC consistency validation
- minimum stock-universe validation
- latest-session coverage validation
- benchmark-date warning
- no publish on critical validation failure
- no scheduled publish until today's EOD exists
- atomic JSON writes
- rolling state kept separately from published output

## 7. Live external-provider acceptance test

**PENDING — must run once on GitHub Actions.**

The secured build environment used to create this package does not have outbound DNS/internet access to call the live VNDIRECT endpoint. Therefore the first real `Run workflow` on GitHub is the live acceptance test for provider connectivity/schema from a GitHub-hosted runner.

This limitation does **not** affect the static/unit tests above. The provider endpoint and field mapping were based on the public VNDIRECT integration already present in Alpha Stock v1.20, then redesigned to use bulk EOD retrieval instead of one request per ticker.

## Acceptance criteria on first GitHub run

The run is accepted when:

1. `Unit tests` is green.
2. `Run EOD engine (manual)` is green.
3. log reports a realistic stock universe and `Validate: ok=True`.
4. `Upload Pages artifact` is green.
5. `Deploy to GitHub Pages` is green.
6. Pages landing page reports `DATA OK` and a market date.
7. Tracker and Alpha Stock both show source `Cloud EOD • <date>` after loading.
