# Team 5 dashboard shell

Open `dashboard.html` in any browser. No install needed.

The page is a **layout and wiring shell**. It does not compute any engine. Each engine owner calculates their own numbers and gives us a CSV. Until then the row shows "Awaiting data". The only row filled in is the VIX example from the Sep 22, 2026 strategy memo.

## How to give us your engine's numbers

Make one CSV per engine with these columns:

`date, entity, metric, value, unit, data_version, validated`

| Column | Meaning |
|---|---|
| `date` | Data date, `YYYY-MM-DD` |
| `entity` | Engine id, exactly as in the table below |
| `metric` | `level`, `z_score`, `chg_3m`, `chg_1y` (optional: `z_score_standard`) |
| `value` | Number. Leave blank if not available. Do not write 0 for missing |
| `unit` | e.g. `%`, `index`, `sd` |
| `data_version` | Which data version you used (Team 1's version if available) |
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

Rules: percentages as plain numbers in the unit given (2.5 means 2.5%). Z-score on the common scale. If you send several dates, the dashboard uses the latest date for each metric.

## Where to put your file

Save it as `inputs/<entity>.csv`, for example `inputs/credit.csv`, and commit it to the repo. When the page is opened from its web address (GitHub Pages), it reads every `inputs/<entity>.csv` automatically. When you open `dashboard.html` as a local file, use the **Load engine CSV files** button instead.

## Using the page

- **Load engine CSV files**: pick one or several CSVs. They are merged.
- **Preview layout with illustrative data**: fills empty rows with placeholder numbers, clearly tagged. Never present these as real.
- **Download CSV template**, **Export table (CSV)**, **Print / save as PDF**.

`inputs/template.csv` is a starting file.
