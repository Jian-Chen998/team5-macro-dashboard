#!/usr/bin/env python3
"""Write made-up input files shaped like Team 2's and Team 3's documented outputs.

These numbers are invented to test the layout. They did not come from either team's code.
Every row is marked synthetic, so the dashboard tags it and never treats it as a signal.

    python adapters/make_samples.py
"""
import csv
import tempfile
from pathlib import Path

from convert import convert_team2, convert_team3, write_rows

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ["SAMPLE_equity", "SAMPLE_intl", "SAMPLE_bonds"]


def record(record_id, role, weights, er, vol, contributions, **extra):
    shares = [c / vol for c in contributions]
    return {"record_id": record_id, "role": role, "status": "success", "weights": weights,
            "metrics": {"expected_return": er, "volatility": vol, "volatility_contributions": contributions,
                        "risk_shares": shares}, **extra}


def team2_sample():
    reference = record("reference", "source_reference", [0.50, 0.20, 0.30], 0.058, 0.100, [0.070, 0.024, 0.006],
                       metadata={"as_of": None, "data_status": "synthetic"})
    baseline = record("baseline_solution", "optimized_baseline", [0.45, 0.15, 0.40], 0.060, 0.090, [0.060, 0.022, 0.008])
    lower = record("scenario_1", "scenario_target", [0.50, 0.15, 0.35], 0.060, 0.097, [0.068, 0.022, 0.007],
                   data_status="hypothetical",
                   changes=[{"field": "expected_returns", "asset_id": "SAMPLE_equity", "delta": -0.01}])
    failed = {"record_id": "scenario_2", "role": "scenario_target", "status": "infeasible", "weights": None, "metrics": None,
              "data_status": "hypothetical", "changes": [{"field": "upper_bounds", "asset_id": "SAMPLE_equity", "new": 0.05}]}
    return {"schema_version": "dashboard-result/1", "status": "partial_failure",
            "source": {"data_status": "synthetic", "release_id": "made_up_sample"},
            "suite": {"asset_ids": ASSETS, "reference": reference, "baseline_solution": baseline, "scenarios": [lower, failed]}}


def write_table(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def fit(fund, model, window, status, nobs, r2, reason=""):
    return {"entity_id": fund, "model": model, "window_id": window, "status": status, "status_reason": reason,
            "r2": r2, "nobs": nobs, "end_period": "2026-06" if status == "ok" else "", "data_status": "synthetic",
            "proxy_obs": 0, "release_id": "made_up_sample"}


def coef(fund, model, window, term, estimate, t):
    return {"entity_id": fund, "model": model, "window_id": window, "term": term, "estimate": estimate, "t_stat": t}


def perf(fund, window, ret, vol, sharpe, status="ok"):
    return {"entity_id": fund, "window_id": window, "status": status, "end_period": "2026-06", "ann_return": ret,
            "ann_vol": vol, "sharpe": sharpe, "data_status": "synthetic", "release_id": "made_up_sample"}


def team3_sample(folder):
    fits, coefs, perfs = [], [], []
    equity = {"full": (0.0012, 1.4, 0.98, 2.0, 0.92), "t36_now": (0.0005, 0.5, 1.02, 1.1, 0.90)}
    for window, (alpha, alpha_t, beta, beta_t, r2) in equity.items():
        fits.append(fit("SAMPLE_FUND_A", "Carhart4", window, "ok", 120 if window == "full" else 36, r2))
        coefs += [coef("SAMPLE_FUND_A", "Carhart4", window, "alpha", alpha, alpha_t),
                  coef("SAMPLE_FUND_A", "Carhart4", window, "mkt_rf", beta, beta_t),
                  coef("SAMPLE_FUND_A", "Carhart4", window, "smb", -0.08, -1.2),
                  coef("SAMPLE_FUND_A", "Carhart4", window, "hml", 0.15, 2.1),
                  coef("SAMPLE_FUND_A", "Carhart4", window, "mom", -0.03, -0.6)]
        perfs.append(perf("SAMPLE_FUND_A", window, 0.095, 0.16, 0.48))
        fits.append(fit("SAMPLE_FUND_B", "Carhart4", window, "insufficient_history", 22, ""))
        perfs.append(perf("SAMPLE_FUND_B", window, 0.07, 0.19, 0.25))
        fits.append(fit("SAMPLE_BOND_C", "EquityBeta", window, "ok", 120 if window == "full" else 36, 0.09))
        coefs += [coef("SAMPLE_BOND_C", "EquityBeta", window, "alpha", 0.0009, 2.5),
                  coef("SAMPLE_BOND_C", "EquityBeta", window, "mkt_rf", 0.10, 1.9)]
        perfs.append(perf("SAMPLE_BOND_C", window, 0.031, 0.045, 0.22))
        fits.append(fit("SAMPLE_BOND_C", "Carhart4", window, "not_applicable", "", ""))
    write_table(folder / "fit_stats.csv", fits)
    write_table(folder / "coefficients.csv", coefs)
    write_table(folder / "performance.csv", perfs)


def main():
    samples = ROOT / "inputs" / "samples"
    write_rows(convert_team2(team2_sample()), samples / "allocation_sample.csv")
    with tempfile.TemporaryDirectory() as tmp:
        team3_sample(Path(tmp))
        write_rows(convert_team3(tmp, ("full", "t36_now")), samples / "funds_sample.csv")
    print("wrote samples to", samples)


if __name__ == "__main__":
    main()
