#!/usr/bin/env python3
"""Tests for convert.py, using made-up inputs shaped like each team's documented format.

    python adapters/test_convert.py
"""
import tempfile
import unittest
from pathlib import Path

from convert import ConvertError, convert_team2, convert_team3
from make_samples import team2_sample, team3_sample


def lookup(rows):
    return {(r[1], r[2]): r for r in rows}


class Team2(unittest.TestCase):
    def setUp(self):
        self.rows = convert_team2(team2_sample())
        self.by = lookup(self.rows)

    def test_decimals_are_not_rescaled(self):
        self.assertEqual(self.by[("alloc/SAMPLE_equity", "baseline_solution.weight")][3], 0.45)
        self.assertEqual(self.by[("alloc/portfolio", "baseline_solution.volatility")][3], 0.09)

    def test_failed_scenario_keeps_status_and_has_no_numbers(self):
        self.assertEqual(self.by[("alloc/portfolio", "scenario_2.status")][3], "infeasible")
        self.assertNotIn(("alloc/portfolio", "scenario_2.volatility"), self.by)
        self.assertNotIn(("alloc/SAMPLE_equity", "scenario_2.weight"), self.by)

    def test_missing_reference_date_stays_blank(self):
        self.assertEqual(self.by[("alloc/SAMPLE_equity", "reference.weight")][0], "")

    def test_status_is_carried_and_nothing_is_validated(self):
        self.assertEqual(self.by[("alloc/SAMPLE_equity", "baseline_solution.weight")][6], "synthetic")
        self.assertEqual(self.by[("alloc/portfolio", "scenario_1.volatility")][6], "hypothetical")
        self.assertEqual({r[7] for r in self.rows}, {"FALSE"})

    def test_frontier_points_pass_through_and_failed_points_have_no_numbers(self):
        self.assertEqual(self.by[("alloc/frontier", "gmv.volatility")][3], 0.085)
        self.assertEqual(self.by[("alloc/frontier", "p01.status")][3], "success")
        self.assertEqual(self.by[("alloc/frontier", "p07.status")][3], "solver_error")
        self.assertNotIn(("alloc/frontier", "p07.volatility"), self.by)
        self.assertEqual(self.by[("alloc/frontier", "scan.status")][3], "partial_failure")

    def test_result_without_frontier_still_converts(self):
        sample = team2_sample()
        sample["frontier"] = None
        self.assertFalse([r for r in convert_team2(sample) if r[1] == "alloc/frontier"])

    def test_rejects_other_schema(self):
        with self.assertRaises(ConvertError):
            convert_team2({"schema_version": "allocation-scenarios/1", "status": "success"})

    def test_rejects_unknown_data_status(self):
        bad = team2_sample()
        bad["source"]["data_status"] = "final"
        with self.assertRaises(ConvertError):
            convert_team2(bad)

    def test_rejects_failed_baseline(self):
        bad = team2_sample()
        bad["status"] = "infeasible"
        with self.assertRaises(ConvertError):
            convert_team2(bad)


class Team3(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        team3_sample(Path(self.tmp.name))
        self.rows = convert_team3(self.tmp.name, ("full", "t36_now"))
        self.by = lookup(self.rows)

    def tearDown(self):
        self.tmp.cleanup()

    def test_each_window_stays_separate(self):
        self.assertEqual(self.by[("fund/SAMPLE_FUND_A", "full.Carhart4.mkt_rf.estimate")][3], "0.98")
        self.assertEqual(self.by[("fund/SAMPLE_FUND_A", "t36_now.Carhart4.mkt_rf.estimate")][3], "1.02")

    def test_bond_alpha_is_never_reported(self):
        self.assertFalse([k for k in self.by if k[0] == "fund/SAMPLE_BOND_C" and ".EquityBeta.alpha" in k[1]])
        self.assertIn(("fund/SAMPLE_BOND_C", "full.EquityBeta.mkt_rf.estimate"), self.by)

    def test_benchmark_relative_columns_pass_through(self):
        self.assertEqual(self.by[("fund/SAMPLE_FUND_A", "full.perf.benchmark_id")][3], "SAMPLE_PROXY_EQ")
        row = self.by[("fund/SAMPLE_FUND_A", "full.perf.active_return")]
        self.assertEqual((row[3], row[4]), ("-0.004", "decimal"))
        self.assertEqual(self.by[("fund/SAMPLE_FUND_A", "t36_now.perf.information_ratio")][3], "0.29")
        self.assertEqual(self.by[("fund/SAMPLE_FUND_A", "full.perf.n_obs_relative")][4], "count")

    def test_benchmark_model_is_kept_and_its_alpha_can_be_reported(self):
        self.assertEqual(self.by[("fund/SAMPLE_FUND_A", "full.Benchmark.benchmark.estimate")][3], "0.97")
        self.assertIn(("fund/SAMPLE_FUND_A", "full.Benchmark.alpha.estimate"), self.by)
        self.assertEqual(self.by[("fund/SAMPLE_BOND_C", "t36_now.Benchmark.benchmark_id")][3], "SAMPLE_PROXY_BOND")

    def test_fund_without_proxy_has_no_benchmark_rows(self):
        self.assertFalse([k for k in self.by if k[0] == "fund/SAMPLE_FUND_B"
                          and ("Benchmark" in k[1] or "benchmark" in k[1] or "active" in k[1])])

    def test_short_proxy_history_leaves_relative_blank(self):
        self.assertEqual(self.by[("fund/SAMPLE_BOND_C", "full.perf.n_obs_relative")][3], "48")
        self.assertNotIn(("fund/SAMPLE_BOND_C", "full.perf.active_return"), self.by)
        self.assertEqual(self.by[("fund/SAMPLE_BOND_C", "full.Benchmark.status")][3], "insufficient_history")
        self.assertNotIn(("fund/SAMPLE_BOND_C", "full.Benchmark.benchmark.estimate"), self.by)

    def test_contract_before_benchmarks_still_converts(self):
        folder = Path(self.tmp.name)
        for name, drop in (("performance.csv", 5), ("fit_stats.csv", 1)):
            lines = (folder / name).read_text(encoding="utf-8").splitlines()
            cut = [",".join(line.split(",")[:-drop]) for line in lines]
            (folder / name).write_text("\n".join(cut) + "\n", encoding="utf-8")
        by = lookup(convert_team3(self.tmp.name, ("full", "t36_now")))
        self.assertIn(("fund/SAMPLE_FUND_A", "full.perf.sharpe"), by)
        self.assertFalse([k for k in by if "active_return" in k[1] or "benchmark_id" in k[1]])

    def test_sharpe_interval_passes_through(self):
        row = self.by[("fund/SAMPLE_FUND_A", "full.perf.sharpe_ci_low")]
        self.assertEqual((row[3], row[4]), ("-0.108", "ratio"))

    def test_series_rows_are_monthly_and_follow_the_shown_model(self):
        rows = [r for r in self.rows if r[1] == "fund/SAMPLE_FUND_A" and r[2] == "full.series.fitted"]
        self.assertEqual(len(rows), 120)
        self.assertEqual((rows[0][0], rows[0][4]), ("2016-07", "decimal_monthly"))
        self.assertFalse([r for r in self.rows if ".series." in r[2] and r[2].startswith("t36_now")])

    def test_default_windows_skip_those_not_in_the_run(self):
        by = lookup(convert_team3(self.tmp.name))
        self.assertIn(("fund/SAMPLE_FUND_A", "t36_now.perf.sharpe"), by)
        self.assertFalse([k for k in by if k[1].startswith("common.")])

    def test_bond_correlation_follows_contract(self):
        self.assertAlmostEqual(self.by[("fund/SAMPLE_BOND_C", "full.EquityBeta.correlation")][3], 0.3)

    def test_insufficient_history_has_no_estimates(self):
        self.assertEqual(self.by[("fund/SAMPLE_FUND_B", "full.Carhart4.status")][3], "insufficient_history")
        self.assertNotIn(("fund/SAMPLE_FUND_B", "full.Carhart4.mkt_rf.estimate"), self.by)
        self.assertNotIn(("fund/SAMPLE_FUND_B", "full.Carhart4.r2"), self.by)

    def test_not_applicable_rows_are_dropped(self):
        self.assertNotIn(("fund/SAMPLE_BOND_C", "full.Carhart4.status"), self.by)

    def test_alpha_stays_monthly(self):
        row = self.by[("fund/SAMPLE_FUND_A", "full.Carhart4.alpha.estimate")]
        self.assertEqual((row[3], row[4]), ("0.0012", "decimal_monthly"))

    def test_missing_window_is_an_error(self):
        with self.assertRaises(ConvertError):
            convert_team3(self.tmp.name, ("t60_now",))

    def test_old_contract_is_rejected(self):
        path = Path(self.tmp.name) / "fit_stats.csv"
        text = path.read_text(encoding="utf-8").replace("window_id", "window_name", 1)
        path.write_text(text, encoding="utf-8")
        with self.assertRaises(ConvertError):
            convert_team3(self.tmp.name)


if __name__ == "__main__":
    unittest.main()
