# Team 5 dashboard shell

Open `dashboard.html` in any browser. No install needed.

The page is a **layout and wiring shell**. It does not compute any engine. Each engine owner calculates their own numbers and gives us a CSV. Until then the row shows "Awaiting data". The only row filled in is the VIX example from the Sep 22, 2026 strategy memo.

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

Then load the CSV with **Load data files**. For Team 3, `--windows` picks the windows (default `full,t36_now,t36_1y`) and `--model` picks the equity model (default `Carhart4`).

- **Restricted data:** results built from Team 1's real release are restricted. `inputs/allocation.csv` and `inputs/funds.csv` are in `.gitignore`, so keep them out of this repo and share them only as your team agrees.
- **Validated:** rows are marked not validated unless you pass `--team4-validated`, which is only for a file Team 4 has checked.
- **Team 3 rules kept:** bond fund alpha is never shown, alpha stays monthly, and "insufficient history" is shown as no result.
- **Samples:** `inputs/samples/` holds made-up files for testing the layout. They did not come from either team's code and are marked synthetic. `python adapters/make_samples.py` rebuilds them, and `python adapters/test_convert.py` runs the tests.

## Using the page

- **Terminal view**: a dark trading-desk look with a scrolling signal ticker and a local clock. The data colors stay the same: blue is unusually low, orange is unusually high. The choice is remembered in your browser. **Standard view** switches back.
- **Load data files**: pick one or several CSVs. They are merged.
- **Preview with placeholder data**: fills empty rows with made-up numbers tagged TEST. Never present these as real.
- **Show sources and details**: shows owners, planned sources, release IDs and technical columns. They are hidden by default so the page reads cleanly for a portfolio manager.
- **Export table (CSV)** includes a plain-language "what it means" column. **Print / save as PDF** prints what is on screen. **Download CSV template** appears with the details.

`inputs/template.csv` is a starting file.
