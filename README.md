# Team 5 dashboard shell

**Live page:** https://jian-chen998.github.io/team5-macro-dashboard/

Open `dashboard.html` in any browser. No install needed.

The page itself does not compute any engine. `engines/macro_engines.py` computes all eight signals from public data and writes one CSV per signal; see [engines/README.md](engines/README.md). Until a signal's CSV is loaded, its row shows "Awaiting data". The only built-in row is the VIX example from the Sep 22, 2026 strategy memo.

## How to give us your engine's numbers

Make one CSV per engine with these columns:

`date, entity, metric, value, unit, release_id, data_status, validated`

The format follows Team 1's data conventions (`config/conventions.yaml` in their repo), so the same rules apply across teams.

| Column | Meaning |
|---|---|
| `date` | Data date. `YYYY-MM` for monthly data (Team 1's `period` format) or `YYYY-MM-DD` for daily data. A column named `period` is also accepted |
| `entity` | Engine id, exactly as in the table below |
| `metric` | `level`, `z_score`, `chg_3m`, `chg_1y` (optional: `z_score_standard`) |
| `value` | Number. Leave blank if not available. Do not write 0 for missing |
| `unit` | `decimal` for rates, yields, spreads and returns; `index` for index levels such as the VIX; `sd` for Z-scores |
| `release_id` | Team 1's release you built from, e.g. `data_v1.0`. For data you pulled yourself, use a short id with the download date, e.g. `fred_2026-10-20` |
| `data_status` | `real`, `synthetic` or `placeholder`, as in Team 1's tables |
| `validated` | `TRUE` only after Team 4 has checked it, otherwise `FALSE` |

Engine ids and owners:

| entity | Engine | Owner |
|---|---|---|
| `volatility` | Volatility regime (VIX) | C |
| `momentum` | Equity momentum | C |
| `erp` | Equity risk premium | C |
| `real_rate` | Real Treasury rate | D |
| `breakeven` | Expected inflation (break-even) | D |
| `term_premium` | Bond term premium | D |
| `yield_curve` | Yield curve (2s10s) | D |
| `credit` | Credit risk premium | E |

Rules:

- **Decimals, never percent.** 0.025 means 2.5%. FRED publishes yields in percent, so divide by 100 first. The dashboard shows decimals as percent and changes as percentage points (pp).
- **Missing stays missing.** Leave the value blank; no zero fill, no forward fill.
- **Only `real` rows count as signals.** Synthetic and placeholder rows are shown with a tag and left out of the key takeaway and the joint warning.
- Z-scores use the common −3 to +3 scale. If you send several dates, the dashboard uses the latest date for each metric.
- Files in the earlier format (`data_version`, no `data_status`) still load, but show "Status missing" until `data_status` is added.

## Where to put your file

Save it as `inputs/<entity>.csv`, for example `inputs/credit.csv`, and commit it to the repo. When the page is opened from its web address (GitHub Pages), it reads every `inputs/<entity>.csv` automatically. When you open `dashboard.html` as a local file, use the **Load data files** button instead.

## Adding Team 2 and Team 3 results

The page also has an **Asset allocation** panel (Team 2) and a **Fund report cards** panel (Team 3). `adapters/convert.py` turns each team's output into the same CSV format. It uses only the Python standard library and contains no model logic.

```bash
# Team 2: dashboard_result.json comes from allocation_dashboard.export_result
python adapters/convert.py team2 path/to/dashboard_result.json -o inputs/allocation.csv

# Team 3: the run folder holds fit_stats.csv, coefficients.csv and performance.csv
python adapters/convert.py team3 path/to/run_folder -o inputs/funds.csv
```

Then load the CSV with **Load data files**. For Team 3, `--windows` picks the windows (default: whichever of `full,common,t36_now,t36_1y` the run has; `common` is Team 3's common window, 2017-06 to 2026-06, the same months for every fund) and `--model` picks the equity model (default `Carhart4`).

- **Efficient frontier:** when Team 2's result has a `frontier` block, the allocation panel draws a **Risk and return** chart: the frontier curve, the lowest-risk mix, and the reference and suggested portfolios. What-if cases use their own assumptions, so they are not drawn on it. Failed frontier points break the curve.
- **Return over time:** when the run folder has `series.csv`, the fund panel draws each fund's cumulative return above cash next to the part its factor model explains. Team 3 writes monthly series for `full` and `common` only.
- **Sharpe interval:** `sharpe_ci_low` and `sharpe_ci_high` are shown under each Sharpe ratio as its 95% interval.

- **Restricted data:** results built from Team 1's real release are restricted. `inputs/allocation.csv` and `inputs/funds.csv` are in `.gitignore`, so keep them out of this repo and share them only as your team agrees.
- **Validated:** rows are marked not validated unless you pass `--team4-validated`, which is only for a file Team 4 has checked.
- **Team 3 rules kept:** bond fund alpha is never shown, alpha stays monthly, and "insufficient history" is shown as no result.
- **Benchmark comparison:** with Team 3's contract 1.5 or later (current: 1.6, on Team 1's `data_v1.1`), the converter also reads each fund's benchmark proxy, its `Benchmark` model and the columns `active_return`, `tracking_error`, `information_ratio` and `n_obs_relative` in `performance.csv`. The fund panel then shows an **Against its benchmark** table. Blank values stay blank: a fund without a proxy shows "No single benchmark fund", and a proxy with too little history for the period shows "Benchmark history too short". Older run folders without these columns still convert; the table is simply not shown.
- **Samples:** `inputs/samples/` holds made-up files for testing the layout. They did not come from either team's code and are marked synthetic. `python adapters/make_samples.py` rebuilds them, and `python adapters/test_convert.py` runs the tests.

## Using the page

- **Signal history**: click a signal in the chart (or select it and press Enter) to open its history below the chart. It draws every date the owner has sent, with no filling between dates. Switch between **Score** and **Level**, pick **1Y / 3Y / 5Y / All**, hover or use the arrow keys to read each point, and open **Show the numbers** for a table. To get a line, send several dates in your CSV; with one date the panel shows a single point.
- **Cutoff slider**: changes the score that counts as unusual (1.0 to 2.5; the memo uses 1.5). The chart, takeaway, counts and combined warning update together, and the page says when a custom cutoff is in use. It applies to this view only and resets on reload.
- **Asset allocation**: pick any two portfolios (reference, suggested or a what-if) to compare their weights, expected return and volatility. A what-if with no solution says so instead of showing weights. **Where the risk comes from** follows the right-hand pick.
- **Fund report cards**: filter stock or bond funds, sort by return, Sharpe ratio, volatility, alpha or (with benchmarks) active return and information ratio, and tick up to three funds to see them side by side.
- **Terminal view**: a dark trading-desk look with a scrolling signal ticker and a local clock. The data colors stay the same: blue is unusually low, orange is unusually high. The choice is remembered in your browser. **Standard view** switches back.
- **Load data files**: pick one or several CSVs. They are merged.
- **Preview with placeholder data**: fills empty rows with made-up numbers tagged TEST. Never present these as real.
- **Show sources and details**: shows owners, planned sources, release IDs and technical columns. They are hidden by default so the page reads cleanly for a portfolio manager.
- **Export table (CSV)** includes a plain-language "what it means" column. **Print / save as PDF** prints what is on screen. **Download CSV template** appears with the details.

`inputs/template.csv` is a starting file.
