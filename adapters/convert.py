#!/usr/bin/env python3
"""Convert other teams' outputs into the dashboard's CSV format. Standard library only.

    python adapters/convert.py team2 <dashboard_result.json> -o inputs/allocation.csv
    python adapters/convert.py team3 <run_dir> -o inputs/funds.csv

Team 2 input follows docs/team5_interface.md (dashboard-result/1).
Team 3 input follows docs/OUTPUT_CONTRACT.md (version 1.3 or later). The benchmark
comparison (the Benchmark model, and benchmark_id, active_return, tracking_error,
information_ratio and n_obs_relative in performance.csv) is read when present, from 1.5 on,
as are the Sharpe ratio's interval (sharpe_ci_low, sharpe_ci_high) and series.csv.
Team 2's efficient frontier (the `frontier` block) is read when the result has one.

No model logic lives here. Values pass through unchanged, except Team 3's correlation
for bond funds, which the contract defines as sign(beta) * sqrt(r2).
"""
import argparse
import csv
import json
import math
from pathlib import Path

HEADER = ["date", "entity", "metric", "value", "unit", "release_id", "data_status", "validated"]
ALLOWED_STATUS = {"real", "synthetic", "placeholder", "mixed", "hypothetical"}
EQUITY_MODELS = ("CAPM", "FF3", "Carhart4")
BOND_MODEL = "EquityBeta"
BENCH_MODEL = "Benchmark"
# performance.csv columns against the benchmark proxy (contract 1.5, section 10), with the dashboard unit
RELATIVE = (("benchmark_id", "text"), ("active_return", "decimal"), ("tracking_error", "decimal"),
            ("information_ratio", "ratio"), ("n_obs_relative", "count"))
# Used when --windows is not given; windows missing from the run are skipped. "common" is
# Team 3's common estimation window (2017-06..2026-06), the same months for every fund.
DEFAULT_WINDOWS = ("full", "common", "t36_now", "t36_1y")
SHARPE_CI = (("sharpe_ci_low", "ratio"), ("sharpe_ci_high", "ratio"))


class ConvertError(Exception):
    """The input does not match the documented format."""


def _status(value, where):
    if value not in ALLOWED_STATUS:
        raise ConvertError(f"{where}: unknown data_status {value!r}")
    return value


def _flag(validated):
    return "TRUE" if validated else "FALSE"


def _text(value):
    return "" if value is None else str(value)


def _describe_changes(changes):
    parts = []
    for c in changes or []:
        asset = c.get("asset_id", "")
        if c.get("field") == "expected_returns" and c.get("delta") is not None:
            parts.append(f"{asset} expected return {c['delta'] * 100:+.2f} pp")
        elif c.get("field") == "upper_bounds" and c.get("new") is not None:
            parts.append(f"{asset} cap {c['new'] * 100:.2f}%")
        else:
            parts.append(f"{asset} {c.get('field', 'change')}")
    return "; ".join(parts)


def convert_team2(result, validated=False):
    """dashboard-result/1 -> rows. Calculation fields are decimals, so nothing is rescaled."""
    if not isinstance(result, dict) or result.get("schema_version") != "dashboard-result/1":
        raise ConvertError("Team 2: expected schema_version dashboard-result/1")
    if result.get("status") not in ("success", "partial_failure"):
        raise ConvertError(f"Team 2: result status is {result.get('status')!r}, nothing to show")
    try:
        suite, source = result["suite"], result["source"]
        asset_ids = suite["asset_ids"]
        records = [suite["reference"], suite["baseline_solution"], *suite["scenarios"]]
        release = source.get("release_id")
        source_status = _status(source["data_status"], "Team 2 source")
    except (KeyError, TypeError) as exc:
        raise ConvertError(f"Team 2: missing field {exc}") from exc

    rows = []
    for record in records:
        rec = record["record_id"]
        role = record.get("role")
        # Dates stay blank unless the record has its own. A CME date is never used for the reference.
        date = ""
        status = source_status
        if role == "source_reference":
            meta = record.get("metadata") or {}
            date = _text(meta.get("as_of"))
            status = _status(meta.get("data_status", source_status), "Team 2 reference")
        elif role == "scenario_target":
            status = _status(record.get("data_status", "hypothetical"), "Team 2 scenario")

        def add(entity, metric, value, unit):
            if value is not None:   # missing stays missing, never zero
                rows.append([date, entity, f"{rec}.{metric}", value, unit, _text(release), status, _flag(validated)])

        add("alloc/portfolio", "status", record.get("status"), "text")
        if role == "scenario_target":
            add("alloc/portfolio", "change", _describe_changes(record.get("changes")) or None, "text")
        metrics = record.get("metrics") or {}
        add("alloc/portfolio", "expected_return", metrics.get("expected_return"), "decimal")
        add("alloc/portfolio", "volatility", metrics.get("volatility"), "decimal")
        vectors = (("weight", record.get("weights"), "decimal"),
                   ("vol_contribution", metrics.get("volatility_contributions"), "decimal"),
                   ("risk_share", metrics.get("risk_shares"), "fraction"))
        for name, vector, unit in vectors:
            if vector is None:
                continue
            if len(vector) != len(asset_ids):
                raise ConvertError(f"Team 2: {rec}.{name} does not match asset_ids")
            for asset, value in zip(asset_ids, vector):
                add(f"alloc/{asset}", name, value, unit)
    rows += _frontier_rows(result.get("frontier"), release, source_status, validated)
    return rows


def _frontier_rows(frontier, release, status, validated):
    """Team 2's frontier scan under the baseline assumptions. Failed points keep their status
    and have no numbers, so the drawn line breaks there (team5_interface.md)."""
    if not isinstance(frontier, dict):
        return []
    rows = []

    def add(metric, value, unit):
        if value is not None:
            rows.append(["", "alloc/frontier", metric, value, unit, _text(release), status, _flag(validated)])

    add("scan.status", frontier.get("status"), "text")
    gmv = frontier.get("gmv") or {}
    if gmv.get("status") == "success":
        add("gmv.expected_return", gmv.get("expected_return"), "decimal")
        add("gmv.volatility", gmv.get("volatility"), "decimal")
    for i, point in enumerate(frontier.get("points") or [], 1):
        key = f"p{i:02d}"
        add(f"{key}.status", point.get("status"), "text")
        if point.get("status") == "success":
            add(f"{key}.expected_return", point.get("expected_return"), "decimal")
            add(f"{key}.volatility", point.get("volatility"), "decimal")
    return rows


def _read_csv(path):
    if not path.is_file():
        raise ConvertError(f"Team 3: {path.name} not found in the run folder")
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _require(rows, columns, name):
    if rows and not set(columns) <= set(rows[0]):
        missing = sorted(set(columns) - set(rows[0]))
        raise ConvertError(f"Team 3: {name} has no column {missing}; contract 1.3 or later is required")


def _correlation(beta, r2):
    """Contract section 6: sign(beta) * sqrt(r2). r2 can be a tiny negative from rounding."""
    b, r = float(beta), max(float(r2), 0.0)
    return math.copysign(math.sqrt(r), b)


def convert_team3(run_dir, windows=None, model="Carhart4", validated=False):
    """Team 3 run folder -> rows, one window at a time (contract: always filter on window_id).
    windows=None takes DEFAULT_WINDOWS that the run has; named windows must all be present."""
    if model not in EQUITY_MODELS:
        raise ConvertError(f"Team 3: model must be one of {EQUITY_MODELS}")
    run_dir = Path(run_dir)
    fit = _read_csv(run_dir / "fit_stats.csv")
    coef = _read_csv(run_dir / "coefficients.csv")
    perf = _read_csv(run_dir / "performance.csv")
    _require(fit, ("entity_id", "model", "window_id", "status", "status_reason", "r2", "nobs", "end_period",
                   "data_status", "proxy_obs", "release_id"), "fit_stats.csv")
    _require(coef, ("entity_id", "model", "window_id", "term", "estimate", "t_stat"), "coefficients.csv")
    _require(perf, ("entity_id", "window_id", "status", "end_period", "ann_return", "ann_vol", "sharpe",
                    "data_status", "release_id"), "performance.csv")
    present = {r["window_id"] for r in fit}
    if windows is None:
        windows = tuple(w for w in DEFAULT_WINDOWS if w in present)
        if not windows:
            raise ConvertError(f"Team 3: none of the default windows {DEFAULT_WINDOWS} is in this run")
    absent = [w for w in windows if w not in present]
    if absent:
        raise ConvertError(f"Team 3: window {absent} is not in this run (found {sorted(present)})")

    estimates = {}
    for r in coef:
        key = (r["entity_id"], r["model"], r["window_id"], r["term"])
        if key in estimates:
            raise ConvertError(f"Team 3: duplicate coefficient {key}")
        estimates[key] = r

    rows, seen, fitted_ok = [], set(), {}
    for r in fit:
        win, name = r["window_id"], r["model"]
        if win not in windows or name not in (model, BOND_MODEL, BENCH_MODEL) or r["status"] == "not_applicable":
            continue
        key = (r["entity_id"], name, win)
        if key in seen:
            raise ConvertError(f"Team 3: duplicate fit row {key}")
        seen.add(key)
        status = _status(r["data_status"], f"Team 3 {key}")
        entity = f"fund/{r['entity_id']}"
        prefix = f"{win}.{name}"

        def add(metric, value, unit):
            if value not in ("", None):
                rows.append([r["end_period"], entity, f"{prefix}.{metric}", value, unit, r["release_id"],
                             status, _flag(validated)])

        add("status", r["status"], "text")
        add("status_reason", r["status_reason"], "text")
        add("nobs", r["nobs"], "count")
        add("proxy_obs", r["proxy_obs"], "count")
        add("benchmark_id", r.get("benchmark_id", ""), "text")
        if r["status"] != "ok":
            continue    # no estimates exist; report as no result, not as a weak result
        if name != BENCH_MODEL:
            fitted_ok[key] = (status, r["release_id"])
        add("r2", r["r2"], "fraction")
        terms = [t for (e, m, w, t) in estimates if (e, m, w) == key]
        for term in terms:
            if name == BOND_MODEL and term == "alpha":
                continue    # contract section 6: EquityBeta's alpha must not be reported
            c = estimates[(*key, term)]
            add(f"{term}.estimate", c["estimate"], "decimal_monthly" if term == "alpha" else "beta")
            add(f"{term}.t_stat", c["t_stat"], "t")
        if name == BOND_MODEL and (*key, "mkt_rf") in estimates and r["r2"]:
            add("correlation", _correlation(estimates[(*key, "mkt_rf")]["estimate"], r["r2"]), "fraction")

    seen_perf = set()
    for r in perf:
        if r["window_id"] not in windows:
            continue
        key = (r["entity_id"], r["window_id"])
        if key in seen_perf:
            raise ConvertError(f"Team 3: duplicate performance row {key}")
        seen_perf.add(key)
        status = _status(r["data_status"], f"Team 3 performance {key}")
        # Relative columns are optional (contract 1.5+); blank stays blank, as Team 3 leaves them
        # blank without a proxy or when the proxy's history is shorter than min_obs.
        for metric, unit in (("status", "text"), ("ann_return", "decimal"), ("ann_vol", "decimal"), ("sharpe", "ratio"),
                             *SHARPE_CI, *RELATIVE):
            if r.get(metric, "") != "":
                rows.append([r["end_period"], f"fund/{r['entity_id']}", f"{r['window_id']}.perf.{metric}", r[metric],
                             unit, r["release_id"], status, _flag(validated)])
    rows += _series_rows(run_dir / "series.csv", windows, fitted_ok, validated)
    return rows


def _series_rows(path, windows, fitted_ok, validated):
    """series.csv (contract section 9): monthly excess return and the model's fitted value, for the
    fits shown above. Only windows configured with series: true have rows (full and common)."""
    if not path.is_file():
        return []
    series = _read_csv(path)
    _require(series, ("entity_id", "model", "window_id", "period", "excess_return", "fitted"), "series.csv")
    rows, seen = [], set()
    for r in series:
        key = (r["entity_id"], r["model"], r["window_id"])
        if r["window_id"] not in windows or key not in fitted_ok:
            continue
        if (*key, r["period"]) in seen:
            raise ConvertError(f"Team 3: duplicate series row {(*key, r['period'])}")
        seen.add((*key, r["period"]))
        status, release = fitted_ok[key]
        for metric in ("excess_return", "fitted"):
            if r[metric] != "":
                rows.append([r["period"], f"fund/{r['entity_id']}", f"{r['window_id']}.series.{metric}", r[metric],
                             "decimal_monthly", release, status, _flag(validated)])
    return rows


def write_rows(rows, out):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(HEADER)
        writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="team", required=True)
    t2 = sub.add_parser("team2", help="Team 2 dashboard_result.json")
    t2.add_argument("source")
    t3 = sub.add_parser("team3", help="Team 3 run folder")
    t3.add_argument("source")
    t3.add_argument("--windows", default=None,
                    help="comma-separated window_id values (default: those of %s in the run)" % ",".join(DEFAULT_WINDOWS))
    t3.add_argument("--model", default="Carhart4", choices=EQUITY_MODELS, help="model shown for equity funds")
    for p in (t2, t3):
        p.add_argument("-o", "--output", required=True)
        p.add_argument("--team4-validated", action="store_true",
                       help="only after Team 4 has checked this exact file")
    args = parser.parse_args(argv)
    try:
        if args.team == "team2":
            result = json.loads(Path(args.source).read_text(encoding="utf-8"))
            rows = convert_team2(result, args.team4_validated)
        else:
            windows = tuple(w for w in args.windows.split(",") if w) if args.windows else None
            rows = convert_team3(args.source, windows, args.model, args.team4_validated)
    except (ConvertError, OSError, json.JSONDecodeError) as exc:
        parser.exit(1, f"error: {exc}\n")
    write_rows(rows, args.output)
    statuses = sorted({r[6] for r in rows})
    print(f"wrote {len(rows)} rows to {args.output}; data_status: {', '.join(statuses)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
