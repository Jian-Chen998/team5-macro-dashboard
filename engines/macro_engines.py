"""Team 5 macro engines: the eight risk signals of the Sep 22, 2026 strategy memo.

Two steps:

  python engines/macro_engines.py fetch --raw <folder>
      Downloads the public source files into <folder> and writes <folder>/macro_monthly.csv
      in Team 1's long format (period, series_id, value, source_id). Daily series become
      monthly averages, as Team 1's own FRED loader does. The current, unfinished month is
      left out.

  python engines/macro_engines.py build --macro <folder>/macro_monthly.csv -o <out folder>
      Computes the eight engines and writes one dashboard CSV per engine,
      <out folder>/<entity>.csv, in the dashboard's format
      (date, entity, metric, value, unit, release_id, data_status, validated).
      Load them with "Load data files" on the dashboard.

  Add --team1-release <release folder> to build to take stock market returns (momentum)
  from Team 1's factors_monthly.csv instead of the public French file. The release's
  MANIFEST.json must say validation_passed: true. Its release_id and data_status are
  carried into the momentum rows.

Units follow Team 1's conventions: rates, spreads and returns are decimals (0.025 = 2.5%),
the VIX is an index level, Z-scores are in standard deviations. Missing values stay
missing: nothing is filled forward or set to zero. Every row is validated=FALSE until
Team 4 has checked it.

Each engine, its source and its Z-score window are set in ENGINES below. See
engines/README.md for the reasoning behind each choice.
"""
import argparse
import csv
import datetime as dt
import io
import json
import math
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
SHILLER_PAGE = "https://shillerdata.com/"
FRENCH_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_CSV.zip"

# FRED series: id -> (source_id, how a month is formed)
FRED_SERIES = {
    "DGS10": "fred",         # 10-year Treasury yield, percent, daily
    "DGS2": "fred",          # 2-year Treasury yield, percent, daily
    "DFII10": "fred",        # 10-year TIPS yield, percent, daily
    "CPIAUCSL": "fred",      # headline CPI, index, monthly
    "CPILFESL": "fred",      # core CPI, index, monthly
    "VIXCLS": "fred",        # Cboe VIX, index, daily
    "THREEFYTP10": "fred",   # Kim-Wright 10-year term premium, percent, daily
    "BAA10Y": "fred",        # Moody's Baa yield minus 10-year Treasury, percent, daily
    "BAMLH0A0HYM2": "fred",  # ICE BofA US High Yield OAS, percent, daily (FRED keeps 3 years)
    "BAMLC0A0CM": "fred",    # ICE BofA US Corporate (IG) OAS, percent, daily (FRED keeps 3 years)
}
PERCENT_SERIES = {"DGS10", "DGS2", "DFII10", "THREEFYTP10", "BAA10Y", "BAMLH0A0HYM2", "BAMLC0A0CM"}

# Engine settings. window: months in the rolling Z-score window. downside: use the memo's
# downside semi-deviation instead of the usual standard deviation.
ENGINES = {
    "real_rate":    {"unit": "decimal", "window": 36,  "downside": False},
    "breakeven":    {"unit": "decimal", "window": 120, "downside": False},
    "term_premium": {"unit": "decimal", "window": 120, "downside": False},
    "erp":          {"unit": "decimal", "window": 120, "downside": False},
    "volatility":   {"unit": "index",   "window": 120, "downside": True},
    "momentum":     {"unit": "decimal", "window": 120, "downside": False},
    "yield_curve":  {"unit": "decimal", "window": 120, "downside": False},
    "credit":       {"unit": "decimal", "window": 120, "downside": False},
}
MIN_COVERAGE = 0.8  # share of a Z-score window's months that must have data
MIN_MTD_DAYS = 5    # trading days needed before a month-to-date reading is shown
MTD_COLUMNS = ["period", "series_id", "value", "source_id", "n_days", "through"]
HEADER = ["date", "entity", "metric", "value", "unit", "release_id", "data_status", "validated"]


class EngineError(Exception):
    pass


# ---------------------------------------------------------------------------
# Fetch: public sources -> macro_monthly.csv (Team 1 long format)
# ---------------------------------------------------------------------------
def _get(url, tries=3):
    for k in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return r.read()
        except OSError as e:
            if k == tries - 1:
                raise EngineError(f"download failed: {url} ({e})")


def _period(ts):
    return f"{ts.year:04d}-{ts.month:02d}"


def parse_fred(text, series_id):
    """FRED graph CSV -> monthly rows. Daily values are averaged within each month."""
    df = pd.read_csv(io.StringIO(text))
    date_col, val_col = df.columns[0], df.columns[1]
    df[val_col] = pd.to_numeric(df[val_col], errors="coerce")  # FRED writes "." for gaps
    df = df.dropna(subset=[val_col])
    df["period"] = pd.to_datetime(df[date_col]).dt.to_period("M").astype(str)
    g = df.groupby("period", as_index=False)[val_col].mean()
    g.columns = ["period", "value"]
    if series_id in PERCENT_SERIES:
        g["value"] = g["value"] / 100.0
    g["series_id"] = series_id
    g["source_id"] = "fred"
    return g[["period", "series_id", "value", "source_id"]]


def shiller_link(page_html):
    m = re.search(r'href="([^"]*/ie_data\.xls[^"]*)"', page_html)
    if not m:
        raise EngineError("could not find the ie_data.xls link on shillerdata.com")
    url = m.group(1)
    return "https:" + url if url.startswith("//") else url


DAILY_SERIES = {"DGS10", "DGS2", "DFII10", "VIXCLS", "THREEFYTP10", "BAA10Y", "BAMLH0A0HYM2", "BAMLC0A0CM"}


def parse_fred_mtd(text, series_id, current):
    """Average of the daily values so far in the current, unfinished month, with the number
    of days and the last date. None when the month has no data yet."""
    df = pd.read_csv(io.StringIO(text))
    date_col, val_col = df.columns[0], df.columns[1]
    df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
    df = df.dropna(subset=[val_col])
    d = pd.to_datetime(df[date_col])
    cur = df[d.dt.to_period("M").astype(str) == current]
    if cur.empty:
        return None
    v = cur[val_col].mean()
    if series_id in PERCENT_SERIES:
        v = v / 100.0
    through = pd.to_datetime(cur[date_col]).max().strftime("%Y-%m-%d")
    return [current, series_id, v, "fred", len(cur), through]


def shiller_period(x):
    """Shiller writes months as decimals: 2026.01 is January and 2026.1 is October."""
    year = int(math.floor(x + 1e-9))
    month = int(round((x - year) * 100))
    if not 1 <= month <= 12:
        raise EngineError(f"Shiller file: bad date {x!r}")
    return f"{year:04d}-{month:02d}"


def parse_shiller(path):
    """Shiller ie_data.xls -> monthly CAPE rows. Dates are written as 2026.1 for October."""
    d = pd.read_excel(path, sheet_name="Data", header=None, engine="xlrd")
    hdr = next((i for i in range(min(len(d), 30)) if str(d.iat[i, 0]).strip() == "Date"), None)
    if hdr is None:
        raise EngineError("Shiller file: header row with 'Date' not found")
    cols = [str(c).strip() for c in d.iloc[hdr]]
    if "CAPE" not in cols:
        raise EngineError("Shiller file: no CAPE column")
    j = cols.index("CAPE")
    out = []
    for i in range(hdr + 1, len(d)):
        raw = d.iat[i, 0]
        try:
            x = float(raw)
        except (TypeError, ValueError):
            continue
        if math.isnan(x):
            continue
        v = pd.to_numeric(d.iat[i, j], errors="coerce")
        if pd.notna(v):
            out.append([shiller_period(x), "SHILLER_CAPE", float(v), "shiller_ie_data"])
    return pd.DataFrame(out, columns=["period", "series_id", "value", "source_id"])


def parse_french(zbytes):
    """French F-F_Research_Data_Factors -> monthly Mkt-RF and RF in decimals (monthly block only)."""
    with zipfile.ZipFile(io.BytesIO(zbytes)) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        text = z.read(name).decode("latin-1")
    out, header_seen = [], False
    for line in text.splitlines():
        cells = [c.strip() for c in line.split(",")]
        if not header_seen:
            header_seen = len(cells) > 1 and cells[1].lower() == "mkt-rf"
            if header_seen:
                cols = cells
            continue
        if not cells[0]:
            break  # the annual block follows a blank line
        if not re.fullmatch(r"\d{6}", cells[0]):
            break
        period = f"{cells[0][:4]}-{cells[0][4:]}"
        row = dict(zip(cols[1:], cells[1:]))
        for src, sid in (("Mkt-RF", "FF_MKT_RF"), ("RF", "FF_RF")):
            v = float(row[src])
            if v > -99.99:
                out.append([period, sid, v / 100.0, "french_ff5_mom"])
    if not out:
        raise EngineError("French file: no monthly rows found")
    return pd.DataFrame(out, columns=["period", "series_id", "value", "source_id"])


def fetch(raw_dir, today=None):
    raw = Path(raw_dir)
    raw.mkdir(parents=True, exist_ok=True)
    today = today or dt.date.today()
    current = f"{today.year:04d}-{today.month:02d}"
    frames, mtd = [], []
    for sid in FRED_SERIES:
        text = _get(FRED_URL.format(sid)).decode("utf-8")
        (raw / f"fred_{sid}.csv").write_text(text, encoding="utf-8")
        frames.append(parse_fred(text, sid))
        print(f"  FRED {sid}: {len(frames[-1])} months")
        if sid in DAILY_SERIES:
            row = parse_fred_mtd(text, sid, current)
            if row:
                mtd.append(row)
    link = shiller_link(_get(SHILLER_PAGE).decode("utf-8", "replace"))
    xls = raw / "shiller_ie_data.xls"
    xls.write_bytes(_get(link))
    frames.append(parse_shiller(xls))
    print(f"  Shiller CAPE: {len(frames[-1])} months")
    zb = _get(FRENCH_URL)
    (raw / "french_factors.zip").write_bytes(zb)
    frames.append(parse_french(zb))
    print(f"  French market factors: {frames[-1].period.nunique()} months")
    out = pd.concat(frames, ignore_index=True)
    out = out[out.period < current]  # the current month is not finished
    path = raw / "macro_monthly.csv"
    out.sort_values(["series_id", "period"]).to_csv(path, index=False)
    pd.DataFrame(mtd, columns=MTD_COLUMNS).to_csv(raw / "macro_mtd.csv", index=False)
    info = {"pulled_on": today.isoformat(), "release_id": f"public_{today.isoformat()}",
            "sources": {"fred": list(FRED_SERIES), "shiller": link, "french": FRENCH_URL},
            "note": "Monthly averages of daily series; the current month is left out of "
                    "macro_monthly.csv. macro_mtd.csv holds its month-to-date averages."}
    (raw / "pull_info.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    print(f"wrote {path} ({len(out):,} rows), release id {info['release_id']}")
    return path


# ---------------------------------------------------------------------------
# Build: macro_monthly.csv -> eight engines -> dashboard CSVs
# ---------------------------------------------------------------------------
def monthly_index(start, end):
    return pd.period_range(start, end, freq="M").astype(str)


def zscore(s, window, downside=False):
    """Rolling Z-score of each month against the `window` months ending with it.

    The standard version divides by the usual standard deviation (population, ddof=0).
    The downside version follows the memo: sqrt( (1/N) * sum over X_i < mean of (X_i - mean)^2 ),
    with N the number of months in the window that have data. A month gets a score only when
    it has a value itself and at least MIN_COVERAGE of the window's months have data; missing
    months are skipped, never filled. (BLS published no CPI for October 2025, for example.)
    """
    vals = s.to_numpy(dtype=float)
    out = [float("nan")] * len(vals)
    need = math.ceil(MIN_COVERAGE * window)
    for i in range(window - 1, len(vals)):
        if math.isnan(vals[i]):
            continue
        w = [v for v in vals[i - window + 1:i + 1] if not math.isnan(v)]
        if len(w) < need:
            continue
        n = len(w)
        mu = sum(w) / n
        if downside:
            sd = math.sqrt(sum((v - mu) ** 2 for v in w if v < mu) / n)
        else:
            sd = math.sqrt(sum((v - mu) ** 2 for v in w) / n)
        if sd > 0:
            out[i] = (vals[i] - mu) / sd
    return pd.Series(out, index=s.index)


def load_macro(path):
    df = pd.read_csv(path, dtype={"period": str, "series_id": str})
    need = {"period", "series_id", "value"}
    if not need <= set(df.columns):
        raise EngineError(f"{path}: needs columns {sorted(need)}")
    if df.duplicated(["period", "series_id"]).any():
        raise EngineError(f"{path}: duplicate (period, series_id) rows")
    wide = df.pivot(index="period", columns="series_id", values="value").sort_index()
    wide = wide.reindex(monthly_index(wide.index.min(), wide.index.max()))
    return wide


def team1_market(release):
    """US market total return (mkt_rf + rf) from a Team 1 release's factors_monthly.csv."""
    rel = Path(release)
    man = json.loads((rel / "MANIFEST.json").read_text(encoding="utf-8"))
    if man.get("validation_passed") is not True:
        raise EngineError(f"{rel}: MANIFEST.json does not say validation_passed: true")
    f = pd.read_csv(rel / "factors_monthly.csv", dtype={"period": str})
    us = f[f.factor_set == "ff3_mom"].set_index("period").sort_index()
    statuses = sorted(us["data_status"].dropna().unique()) if "data_status" in us else ["real"]
    status = statuses[0] if len(statuses) == 1 else "mixed"
    ret = (us["mkt_rf"] + us["rf"]).reindex(monthly_index(us.index.min(), us.index.max()))
    return ret, man["release_id"], status


def engine_levels(w, market=None):
    """Monthly level of each engine, plus extra metrics. Returns {entity: {metric: Series}}."""
    g = lambda c: w[c] if c in w else pd.Series(float("nan"), index=w.index)
    infl = g("CPIAUCSL") / g("CPIAUCSL").shift(12) - 1
    core = g("CPILFESL") / g("CPILFESL").shift(12) - 1
    mkt = market if market is not None else g("FF_MKT_RF") + g("FF_RF")
    mkt = mkt.reindex(w.index.union(mkt.index)).sort_index()
    growth = (1 + mkt)
    r12 = growth.rolling(12, min_periods=12).apply(lambda x: x.prod(), raw=True) - 1
    r3 = growth.rolling(3, min_periods=3).apply(lambda x: x.prod(), raw=True) - 1
    vol = mkt.rolling(12, min_periods=12).std(ddof=1) * math.sqrt(12)
    out = {
        "real_rate": {"level": g("DGS10") - infl, "level_core": g("DGS10") - core},
        "breakeven": {"level": g("DGS10") - g("DFII10")},
        "term_premium": {"level": g("THREEFYTP10")},
        "erp": {"level": 1.0 / g("SHILLER_CAPE") - g("DGS10")},
        "volatility": {"level": g("VIXCLS")},
        "momentum": {"level": r12, "risk_adjusted_12m": r12 / vol, "risk_adjusted_3m": r3 / (vol * math.sqrt(3 / 12))},
        "yield_curve": {"level": g("DGS10") - g("DGS2")},
        "credit": {"level": g("BAA10Y"), "hy_oas": g("BAMLH0A0HYM2"), "ig_oas": g("BAMLC0A0CM")},
    }
    return out


# The Z-score is computed on this metric (the level, unless named here).
SCORE_ON = {"momentum": "risk_adjusted_12m"}
EXTRA_UNITS = {"level_core": "decimal", "risk_adjusted_12m": "ratio", "risk_adjusted_3m": "ratio",
               "hy_oas": "decimal", "ig_oas": "decimal", "chg_1m": None, "percentile_10y": "fraction"}


def percentile(s, window):
    vals = s.to_numpy(dtype=float)
    out = [float("nan")] * len(vals)
    need = math.ceil(MIN_COVERAGE * window)
    for i in range(window - 1, len(vals)):
        if math.isnan(vals[i]):
            continue
        w = [v for v in vals[i - window + 1:i + 1] if not math.isnan(v)]
        if len(w) >= need:
            out[i] = sum(1 for v in w if v <= vals[i]) / len(w)
    return pd.Series(out, index=s.index)


# ICE BofA data has its own terms of use, so the public files leave these metrics out.
NOT_PUBLIC = {"hy_oas", "ig_oas"}


def build(macro_path, release_id, team1_release=None, public=False, mtd_path=None):
    w = load_macro(macro_path)
    mtd = load_mtd(mtd_path) if mtd_path else None
    market, m_release, m_status = None, release_id, "real"
    if team1_release:
        market, m_release, m_status = team1_market(team1_release)
    levels = engine_levels(w, market)
    files = {}
    for ent, cfg in ENGINES.items():
        mets = levels[ent]
        lv = mets["level"].dropna()
        if lv.empty:
            files[ent] = []
            continue
        idx = mets["level"].index
        base = mets[SCORE_ON.get(ent, "level")]
        cols = {
            "level": mets["level"],
            "z_score": zscore(base, cfg["window"], cfg["downside"]),
            "chg_3m": mets["level"] - mets["level"].shift(3),
            "chg_1y": mets["level"] - mets["level"].shift(12),
        }
        if cfg["downside"]:
            cols["z_score_standard"] = zscore(base, cfg["window"], False)
        if ent == "yield_curve":
            cols["chg_1m"] = mets["level"] - mets["level"].shift(1)
        if ent == "erp":
            cols["percentile_10y"] = percentile(mets["level"], 120)
        for k, s in mets.items():
            if k != "level" and not (public and k in NOT_PUBLIC):
                cols[k] = s
        rel, status = (m_release, m_status) if ent == "momentum" else (release_id, "real")
        rows = []
        for p in idx:
            if p < lv.index.min() or p > lv.index.max():
                continue
            for metric, s in cols.items():
                v = s.get(p, float("nan"))
                if pd.isna(v):
                    continue
                unit = "sd" if metric.startswith("z_score") else (EXTRA_UNITS.get(metric) or cfg["unit"])
                rows.append([p, ent, metric, f"{float(v):.6g}", unit, rel, status, "FALSE"])
        if mtd is not None and ent in PROVISIONAL:
            rows += provisional_rows(ent, cfg, mets["level"], w, mtd, rel)
        files[ent] = rows
    return files


# Month-to-date readings, only for signals whose inputs are all daily. ERP pairs the
# month-to-date 10-year yield with the latest monthly CAPE.
PROVISIONAL = {
    "breakeven":    (("DGS10", "DFII10"), lambda v, w: v["DGS10"] - v["DFII10"]),
    "term_premium": (("THREEFYTP10",),    lambda v, w: v["THREEFYTP10"]),
    "erp":          (("DGS10",),          lambda v, w: 1.0 / w["SHILLER_CAPE"].dropna().iloc[-1] - v["DGS10"]),
    "volatility":   (("VIXCLS",),         lambda v, w: v["VIXCLS"]),
    "yield_curve":  (("DGS10", "DGS2"),   lambda v, w: v["DGS10"] - v["DGS2"]),
    "credit":       (("BAA10Y",),         lambda v, w: v["BAA10Y"]),
}


def load_mtd(path):
    df = pd.read_csv(path, dtype={"period": str, "series_id": str, "through": str})
    if df.empty:
        return {}
    if not set(MTD_COLUMNS) <= set(df.columns):
        raise EngineError(f"{path}: needs columns {MTD_COLUMNS}")
    if df.period.nunique() != 1:
        raise EngineError(f"{path}: month-to-date rows must all be for one month")
    return {r.series_id: r for r in df.itertuples()}


def provisional_rows(ent, cfg, level, w, mtd, release):
    """Rows for this month so far, dated with the last day of data (YYYY-MM-DD).

    The reading is scored like a month: against the window of months ending with this one,
    with this month's value taken from the month-to-date average. `mtd_days` (trading days in
    the average) marks the reading as provisional on the dashboard."""
    inputs, f = PROVISIONAL[ent]
    if not all(s in mtd for s in inputs):
        return []
    days = min(int(mtd[s].n_days) for s in inputs)
    if days < MIN_MTD_DAYS:
        return []
    period = mtd[inputs[0]].period
    if not level.dropna().empty and period <= level.dropna().index.max():
        raise EngineError(f"month-to-date period {period} is not after the last full month")
    through = min(mtd[s].through for s in inputs)
    if ent == "erp" and ("SHILLER_CAPE" not in w or w["SHILLER_CAPE"].dropna().empty):
        return []
    value = f({s: float(mtd[s].value) for s in inputs}, w)
    s = level.reindex(monthly_index(level.index.min(), period))
    s.loc[period] = value
    i = len(s) - 1
    cols = {"level": value,
            "z_score": zscore(s, cfg["window"], cfg["downside"]).iloc[i],
            "chg_3m": value - s.iloc[i - 3] if i >= 3 else float("nan"),
            "chg_1y": value - s.iloc[i - 12] if i >= 12 else float("nan")}
    if cfg["downside"]:
        cols["z_score_standard"] = zscore(s, cfg["window"], False).iloc[i]
    cols["mtd_days"] = days
    rows = []
    for metric, v in cols.items():
        if pd.isna(v):
            continue
        unit = "sd" if metric.startswith("z_score") else ("days" if metric == "mtd_days" else cfg["unit"])
        rows.append([through, ent, metric, f"{float(v):.6g}", unit, release, "real", "FALSE"])
    return rows


def write(files, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for ent, rows in files.items():
        with open(out / f"{ent}.csv", "w", newline="", encoding="utf-8") as f:
            wr = csv.writer(f, lineterminator="\n")
            wr.writerow(HEADER)
            wr.writerows(rows)
        last = max((r[0] for r in rows), default="none")
        z = [r for r in rows if r[0] == last and r[2] == "z_score"]
        print(f"  {ent:13s} {len(rows):6,d} rows, latest {last}, z = {z[0][3] if z else 'n/a'}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="download public sources into a folder")
    f.add_argument("--raw", required=True, help="folder for the downloaded files and macro_monthly.csv")
    b = sub.add_parser("build", help="compute the eight engines")
    b.add_argument("--macro", required=True, help="macro_monthly.csv from fetch (or from Team 1)")
    b.add_argument("--release-id", help="release id for the rows; default: from pull_info.json next to --macro")
    b.add_argument("--team1-release", help="Team 1 release folder; momentum then uses its factors_monthly.csv")
    b.add_argument("--public", action="store_true",
                   help="leave out the ICE BofA spreads (hy_oas, ig_oas), for files on the public page")
    b.add_argument("--mtd", help="month-to-date file; default: macro_mtd.csv next to --macro, if it exists")
    b.add_argument("--no-mtd", action="store_true", help="full months only, no month-to-date readings")
    b.add_argument("-o", "--output", required=True, help="folder for <entity>.csv files")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "fetch":
            fetch(a.raw)
        else:
            rid = a.release_id
            if not rid:
                info = Path(a.macro).with_name("pull_info.json")
                if not info.exists():
                    raise EngineError("give --release-id, or keep pull_info.json next to the macro file")
                rid = json.loads(info.read_text(encoding="utf-8"))["release_id"]
            mtd = a.mtd or Path(a.macro).with_name("macro_mtd.csv")
            mtd = mtd if (a.mtd or Path(mtd).exists()) and not a.no_mtd else None
            write(build(a.macro, rid, a.team1_release, a.public, mtd), a.output)
    except EngineError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
