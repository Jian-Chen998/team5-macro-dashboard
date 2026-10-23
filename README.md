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

Save it as `inputs/<entity>.csv`, for example `inputs/credit.csv`, and commit it to the repo. When the page is opened from its web address (GitHub Pages), it reads every `inputs/<entity>.csv` automatically. When you open `dashboard.html` as a local file, use the **Load engine CSV files** button instead.

## Using the page

- **Load engine CSV files**: pick one or several CSVs. They are merged.
- **Preview layout with placeholder data**: fills empty rows with made-up numbers tagged PLACEHOLDER. Never present these as real.
- **Download CSV template**, **Export table (CSV)**, **Print / save as PDF**.

`inputs/template.csv` is a starting file.
