# Macro engines

`macro_engines.py` computes the eight risk signals from the Sep 22, 2026 strategy memo. It writes one CSV per signal in the dashboard's format.

## Run it

You need Python 3.12 or newer, plus `pandas` and `xlrd` (`pip install -r engines/requirements.txt`).

```bash
python engines/macro_engines.py fetch --raw <folder>
python engines/macro_engines.py build --macro <folder>/macro_monthly.csv -o <out folder>
python engines/test_macro_engines.py
```

`fetch` downloads the public source files into `<folder>`. It then writes `macro_monthly.csv` in Team 1's long format (`period, series_id, value, source_id`) and `pull_info.json`, which holds the release id `public_<date>`.

`build` writes `<out folder>/<entity>.csv`, one file for each of the eight signals. On the dashboard, select all eight files with **Load data files**.

To take stock market returns from a Team 1 release instead of the French file, add `--team1-release <release folder>` to `build`. The release's `MANIFEST.json` must say `validation_passed: true`. The momentum rows then carry that release's id and `data_status`.

## The eight signals

| entity | Level (what "Today" shows) | Source | Score |
|---|---|---|---|
| `real_rate` | 10-year Treasury yield minus headline CPI inflation over the past 12 months. Core CPI is also included as `level_core`. | FRED DGS10, CPIAUCSL, CPILFESL | 36 months (the memo's "36-month bands") |
| `breakeven` | 10-year Treasury yield minus 10-year TIPS yield | FRED DGS10, DFII10 | 120 months |
| `term_premium` | 10-year term premium from the Kim-Wright model | FRED THREEFYTP10 | 120 months |
| `erp` | Earnings yield (1 / CAPE) minus the 10-year Treasury yield. Also includes `percentile_10y`, the memo's 10-year percentile rank. | Shiller CAPE (shillerdata.com), FRED DGS10 | 120 months |
| `volatility` | VIX, monthly average | FRED VIXCLS | 120 months, **downside semi-deviation** (memo). `z_score_standard` holds the usual score. |
| `momentum` | US stock market total return over 12 months. Also includes `risk_adjusted_12m` and `risk_adjusted_3m`. | French Data Library, US market (Team 1's source) | 120 months, on the 12-month return divided by its annualized volatility (memo) |
| `yield_curve` | 10-year minus 2-year Treasury yield. Also includes `chg_1m`, the memo's 30-day velocity. | FRED DGS10, DGS2 | 120 months |
| `credit` | Moody's Baa corporate yield minus 10-year Treasury yield. Also includes `hy_oas` and `ig_oas` (ICE BofA). | FRED BAA10Y, BAMLH0A0HYM2, BAMLC0A0CM | 120 months |

Every signal has `level`, `z_score`, `chg_3m` and `chg_1y` for each month, so the history chart has a full line.

## Rules

- **Monthly data.** Daily series become monthly averages, the same way Team 1's FRED loader does it. The current, unfinished month is left out.
- **Decimals.** Rates, spreads and returns are decimals (0.025 means 2.5%). The VIX is an index level. Scores are in standard deviations.
- **Score.** Each month is scored against the window of months ending with it: `(value − mean) / standard deviation`. A month gets a score only when it has a value itself and at least 80% of its window has data. Missing months are skipped, never filled.
- **Downside semi-deviation (VIX).** This is the memo's formula: sqrt((1/N) × sum over months below the mean of (X − mean)²), where N is the number of months in the window.
- **Missing stays missing.** For example, BLS published no CPI for October 2025. So the real rate has no reading for October 2025, and none for October 2026, because its 12-month inflation needs the October 2025 CPI. The latest real rate is therefore September 2026.
- **Status.** Every row is `real` and `validated = FALSE` until Team 4 checks it. With `--team1-release`, momentum rows carry Team 1's status instead.

## Choices to confirm with the engine owners

- **Credit.** On FRED, the ICE BofA HY and IG spreads now cover only the last 3 years, which is too short for a 10-year score. So the score uses Moody's Baa minus Treasury (from 1986). The ICE spreads are included as extra metrics. The Merton distance-to-default overlay needs CRSP and Compustat; it is not in this script.
- **Term premium.** The memo allows ACM or Kim-Wright. Kim-Wright is on FRED. ACM is published by the New York Fed as a spreadsheet and could replace it.
- **Breakeven.** This is the plain 10-year breakeven. The memo's TIPS liquidity adjustment is not applied.
- **Momentum.** This uses the US market only. The memo also names the Nasdaq-100 and sector indices.
- **VIX check against the memo.** On daily VIX over the 10 years to Sep 22, 2026, the usual score of 14.28 is −0.60; the memo says −0.66. The memo's formula gives a downside deviation of 3.75 and a score of −1.16; the memo says about 3.20 and −1.63. The memo's figures look rounded or come from a different window. The script follows the memo's formula as written, on monthly averages.

## Data and sharing

All inputs are public. ICE BofA data has its own terms of use. Check those terms before the CSVs are put on the public page.
