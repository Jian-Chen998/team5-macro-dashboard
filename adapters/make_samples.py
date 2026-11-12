#!/usr/bin/env python3
"""Write made-up input files shaped like Team 2's and Team 3's documented outputs.

These numbers are invented to test the layout. They did not come from either team's code.
Every row is marked synthetic, so the dashboard tags it and never treats it as a signal.

    python adapters/make_samples.py
"""
import csv
import math
import random
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
            "suite": {"asset_ids": ASSETS, "reference": reference, "baseline_solution": baseline, "scenarios": [lower, failed]},
            "frontier": frontier_sample()}


def frontier_sample():
    """A made-up minimum-variance curve that passes through the sample's suggested portfolio
    (6.0% return, 9.0% volatility). Point 7 fails, so the drawn line must break there."""
    def point(ret):
        vol = math.sqrt(0.085 ** 2 + 13.67 * (ret - 0.052) ** 2)
        return {"status": "success", "expected_return": round(ret, 6), "volatility": round(vol, 6), "target_return": ret}
    targets = [0.052 + i * (0.075 - 0.052) / 11 for i in range(12)]
    points = [point(r) for r in targets]
    points[6] = {"status": "solver_error", "expected_return": None, "volatility": None, "target_return": targets[6]}
    return {"status": "partial_failure", "gmv": point(0.052), "maximum": point(0.075), "points": points,
            "degenerate": False, "reason": None}


def write_table(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def fit(fund, model, window, status, nobs, r2, reason="", bench=""):
    return {"entity_id": fund, "model": model, "window_id": window, "status": status, "status_reason": reason,
            "r2": r2, "nobs": nobs, "end_period": "2026-06" if status == "ok" else "", "data_status": "synthetic",
            "proxy_obs": 0, "release_id": "made_up_sample", "benchmark_id": bench}


def coef(fund, model, window, term, estimate, t):
    return {"entity_id": fund, "model": model, "window_id": window, "term": term, "estimate": estimate, "t_stat": t}


def perf(fund, window, ret, vol, sharpe, status="ok", bench="", active="", te="", ir="", n_rel="", se=0.3):
    """Contract 1.5 adds the columns against the benchmark proxy; blank when there is none."""
    return {"entity_id": fund, "window_id": window, "status": status, "end_period": "2026-06", "ann_return": ret,
            "ann_vol": vol, "sharpe": sharpe, "sharpe_ci_low": round(sharpe - 1.96 * se, 4),
            "sharpe_ci_high": round(sharpe + 1.96 * se, 4), "data_status": "synthetic", "release_id": "made_up_sample",
            "benchmark_id": bench, "active_return": active, "tracking_error": te, "information_ratio": ir,
            "n_obs_relative": n_rel}


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
        months = 120 if window == "full" else 36
        # Fund A has a benchmark proxy with as much history as the fund.
        perfs.append(perf("SAMPLE_FUND_A", window, 0.095, 0.16, 0.48, bench="SAMPLE_PROXY_EQ",
                          active=-0.004 if window == "full" else 0.006, te=0.021, ir=-0.19 if window == "full" else 0.29,
                          n_rel=months))
        fits.append(fit("SAMPLE_FUND_A", "Benchmark", window, "ok", months, 0.97, bench="SAMPLE_PROXY_EQ"))
        coefs += [coef("SAMPLE_FUND_A", "Benchmark", window, "alpha", -0.0003, -0.5),
                  coef("SAMPLE_FUND_A", "Benchmark", window, "benchmark", 0.97, 41.0)]
        # Fund B has no proxy: Benchmark is not_applicable and the relative columns stay blank.
        fits.append(fit("SAMPLE_FUND_B", "Carhart4", window, "insufficient_history", 22, ""))
        fits.append(fit("SAMPLE_FUND_B", "Benchmark", window, "not_applicable", "", "", reason="no_benchmark_proxy"))
        perfs.append(perf("SAMPLE_FUND_B", window, 0.07, 0.19, 0.25))
        fits.append(fit("SAMPLE_BOND_C", "EquityBeta", window, "ok", months, 0.09))
        coefs += [coef("SAMPLE_BOND_C", "EquityBeta", window, "alpha", 0.0009, 2.5),
                  coef("SAMPLE_BOND_C", "EquityBeta", window, "mkt_rf", 0.10, 1.9)]
        # Bond C's proxy starts later: over the full window it has 48 months, below min_obs (60),
        # so the relative columns stay blank there and Benchmark has too little history.
        if window == "full":
            perfs.append(perf("SAMPLE_BOND_C", window, 0.031, 0.045, 0.22, bench="SAMPLE_PROXY_BOND", n_rel=48))
            fits.append(fit("SAMPLE_BOND_C", "Benchmark", window, "insufficient_history", 48, "", bench="SAMPLE_PROXY_BOND"))
        else:
            perfs.append(perf("SAMPLE_BOND_C", window, 0.031, 0.045, 0.22, bench="SAMPLE_PROXY_BOND",
                              active=0.002, te=0.008, ir=0.25, n_rel=36))
            fits.append(fit("SAMPLE_BOND_C", "Benchmark", window, "ok", 36, 0.88, bench="SAMPLE_PROXY_BOND"))
            coefs += [coef("SAMPLE_BOND_C", "Benchmark", window, "alpha", 0.0001, 0.4),
                      coef("SAMPLE_BOND_C", "Benchmark", window, "benchmark", 0.92, 15.2)]
        fits.append(fit("SAMPLE_BOND_C", "Carhart4", window, "not_applicable", "", ""))
    write_table(folder / "fit_stats.csv", fits)
    write_table(folder / "coefficients.csv", coefs)
    write_table(folder / "performance.csv", perfs)
    write_table(folder / "series.csv", series_sample())


def series_sample():
    """Made-up monthly excess returns and fitted values for the full window, Jul 2016..Jun 2026."""
    rng, rows = random.Random(5), []
    for fund, model, beta, noise in (("SAMPLE_FUND_A", "Carhart4", 0.98, 0.006), ("SAMPLE_BOND_C", "EquityBeta", 0.10, 0.009)):
        for i in range(120):
            y, m = 2016 + (i + 6) // 12, (i + 6) % 12 + 1
            market = rng.gauss(0.006, 0.04)
            fitted = beta * market
            rows.append({"entity_id": fund, "model": model, "window_id": "full", "period": f"{y}-{m:02d}",
                         "excess_return": round(fitted + rng.gauss(0.0005, noise), 6), "fitted": round(fitted, 6),
                         "residual": "", "benchmark_id": ""})
    return rows


def main():
    samples = ROOT / "inputs" / "samples"
    write_rows(convert_team2(team2_sample()), samples / "allocation_sample.csv")
    with tempfile.TemporaryDirectory() as tmp:
        team3_sample(Path(tmp))
        write_rows(convert_team3(tmp, ("full", "t36_now")), samples / "funds_sample.csv")
    print("wrote samples to", samples)


if __name__ == "__main__":
    main()
