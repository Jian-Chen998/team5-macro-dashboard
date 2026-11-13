"""Tests for engines/macro_engines.py. Run: python engines/test_macro_engines.py (needs pandas)."""
import csv
import io
import json
import math
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import macro_engines as me  # noqa: E402


def months(start, n):
    return list(pd.period_range(start, periods=n, freq="M").astype(str))


class ZScore(unittest.TestCase):
    def test_standard_matches_hand_calculation(self):
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 10.0])
        z = me.zscore(s, 5)
        mu = 4.0
        sd = math.sqrt(sum((v - mu) ** 2 for v in s) / 5)
        self.assertAlmostEqual(z.iloc[-1], (10.0 - mu) / sd)
        self.assertTrue(z.iloc[:4].isna().all())

    def test_downside_uses_months_below_the_mean_over_all_months(self):
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 10.0])
        z = me.zscore(s, 5, downside=True)
        dn = math.sqrt(((1 - 4) ** 2 + (2 - 4) ** 2 + (3 - 4) ** 2) / 5)
        self.assertAlmostEqual(z.iloc[-1], (10.0 - 4.0) / dn)

    def test_missing_months_are_skipped_not_filled(self):
        vals = [float(i) for i in range(10)]
        vals[3] = float("nan")  # one gap in a 10-month window: 90% coverage, still scored
        z = me.zscore(pd.Series(vals), 10)
        w = [v for v in vals if not math.isnan(v)]
        mu = sum(w) / len(w)
        sd = math.sqrt(sum((v - mu) ** 2 for v in w) / len(w))
        self.assertAlmostEqual(z.iloc[-1], (9.0 - mu) / sd)

    def test_too_many_gaps_or_missing_month_gives_no_score(self):
        vals = [float(i) for i in range(10)]
        for k in (1, 2, 3):
            vals[k] = float("nan")  # 70% coverage, below the 80% floor
        self.assertTrue(math.isnan(me.zscore(pd.Series(vals), 10).iloc[-1]))
        vals = [float(i) for i in range(10)] + [float("nan")]
        self.assertTrue(math.isnan(me.zscore(pd.Series(vals), 10).iloc[-1]))


class Parsers(unittest.TestCase):
    def test_fred_monthly_average_in_decimals(self):
        text = "observation_date,DGS10\n2026-01-02,4.00\n2026-01-05,.\n2026-01-06,4.20\n2026-02-02,5.00\n"
        g = me.parse_fred(text, "DGS10")
        self.assertEqual(list(g.period), ["2026-01", "2026-02"])
        self.assertAlmostEqual(g.value.iloc[0], 0.041)
        self.assertAlmostEqual(g.value.iloc[1], 0.05)

    def test_fred_index_series_keep_their_units(self):
        g = me.parse_fred("observation_date,VIXCLS\n2026-01-02,14.0\n2026-01-03,16.0\n", "VIXCLS")
        self.assertAlmostEqual(g.value.iloc[0], 15.0)

    def test_shiller_dates(self):
        self.assertEqual(me.shiller_period(2026.01), "2026-01")
        self.assertEqual(me.shiller_period(2026.1), "2026-10")
        self.assertEqual(me.shiller_period(2026.12), "2026-12")

    def test_french_monthly_block_only_in_decimals(self):
        body = ("This file was created ...\n\n,Mkt-RF,SMB,HML,RF\n"
                "202601,   1.50,  0.1, 0.2,  0.40\n202602,-99.99,  0.1, 0.2,  0.41\n\n"
                " Annual Factors: January-December \n,Mkt-RF,SMB,HML,RF\n2025,  20.00, 1, 1, 4.0\n")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("F-F_Research_Data_Factors.csv", body)
        g = me.parse_french(buf.getvalue())
        got = {(r.period, r.series_id): r.value for r in g.itertuples()}
        self.assertAlmostEqual(got[("2026-01", "FF_MKT_RF")], 0.015)
        self.assertAlmostEqual(got[("2026-02", "FF_RF")], 0.0041)
        self.assertNotIn(("2026-02", "FF_MKT_RF"), got)  # -99.99 means missing
        self.assertFalse(any(p.startswith("2025") for p, _ in got))

    def test_shiller_link(self):
        html = '<a href="//img1.example.com/x/ie_data.xls?ver=1">ie_data.xls</a>'
        self.assertEqual(me.shiller_link(html), "https://img1.example.com/x/ie_data.xls?ver=1")


def write_macro(path, n=150, cpi_gap=None):
    rows = []
    ps = months("2014-01", n)
    for i, p in enumerate(ps):
        rows.append([p, "DGS10", 0.03 + 0.0001 * i, "fred"])
        rows.append([p, "DGS2", 0.02, "fred"])
        rows.append([p, "DFII10", 0.01, "fred"])
        if p != cpi_gap:
            rows.append([p, "CPIAUCSL", 100 * 1.002 ** i, "fred"])
        rows.append([p, "VIXCLS", 15 + (i % 7), "fred"])
        rows.append([p, "THREEFYTP10", 0.005, "fred"])
        rows.append([p, "BAA10Y", 0.015 + 0.0002 * (i % 5), "fred"])
        rows.append([p, "SHILLER_CAPE", 30.0, "shiller_ie_data"])
        rows.append([p, "FF_MKT_RF", 0.01 * ((i % 5) - 1), "french_ff5_mom"])
        rows.append([p, "FF_RF", 0.002, "french_ff5_mom"])
    pd.DataFrame(rows, columns=["period", "series_id", "value", "source_id"]).to_csv(path, index=False)
    return ps


class Build(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def table(self, files, ent):
        return {(r[0], r[2]): r for r in files[ent]}

    def test_rows_follow_the_dashboard_format(self):
        write_macro(self.d / "m.csv")
        files = me.build(self.d / "m.csv", "public_2026-11-13")
        self.assertEqual(sorted(files), sorted(me.ENGINES))
        for ent, rows in files.items():
            self.assertTrue(rows, ent)
            for r in rows:
                self.assertEqual(len(r), len(me.HEADER))
                self.assertEqual(r[1], ent)
                self.assertEqual(r[5:], ["public_2026-11-13", "real", "FALSE"])
                if r[2].startswith("z_score"):
                    self.assertEqual(r[4], "sd")
        self.assertEqual(files["volatility"][0][4], "index")

    def test_engine_formulas(self):
        ps = write_macro(self.d / "m.csv")
        files = me.build(self.d / "m.csv", "x")
        last = ps[-1]
        i = len(ps) - 1
        rr = self.table(files, "real_rate")
        infl = 1.002 ** 12 - 1
        self.assertAlmostEqual(float(rr[(last, "level")][3]), 0.03 + 0.0001 * i - infl, places=5)
        self.assertNotIn((ps[11], "level"), rr)  # no 12-month inflation yet
        self.assertAlmostEqual(float(self.table(files, "breakeven")[(last, "level")][3]), 0.02 + 0.0001 * i, places=5)
        self.assertAlmostEqual(float(self.table(files, "erp")[(last, "level")][3]), 1 / 30 - (0.03 + 0.0001 * i), places=5)
        self.assertAlmostEqual(float(self.table(files, "yield_curve")[(last, "level")][3]), 0.01 + 0.0001 * i, places=5)
        yc = self.table(files, "yield_curve")
        self.assertAlmostEqual(float(yc[(last, "chg_3m")][3]), 0.0003, places=6)
        vol = self.table(files, "volatility")
        self.assertIn((last, "z_score_standard"), vol)
        mom = self.table(files, "momentum")
        r = [0.01 * ((k % 5) - 1) + 0.002 for k in range(i - 11, i + 1)]
        self.assertAlmostEqual(float(mom[(last, "level")][3]), math.prod(1 + x for x in r) - 1, places=5)

    def test_cpi_gap_stays_missing(self):
        ps = write_macro(self.d / "m.csv", cpi_gap="2022-06")
        files = me.build(self.d / "m.csv", "x")
        rr = self.table(files, "real_rate")
        self.assertNotIn(("2022-06", "level"), rr)
        self.assertNotIn(("2023-06", "level"), rr)  # needs the June 2022 CPI for its 12-month change
        self.assertIn(("2023-07", "level"), rr)
        self.assertIn((ps[-1], "z_score"), rr)

    def test_team1_release_for_momentum(self):
        write_macro(self.d / "m.csv")
        rel = self.d / "rel"
        rel.mkdir()
        ps = months("2014-01", 150)
        pd.DataFrame({"period": ps, "factor_set": "ff3_mom", "mkt_rf": 0.01, "smb": 0, "hml": 0, "mom": 0,
                      "rf": 0.001, "source_id": "french_ff5_mom", "data_status": "synthetic"}).to_csv(rel / "factors_monthly.csv", index=False)
        (rel / "MANIFEST.json").write_text(json.dumps({"release_id": "data_v0.2_sample", "validation_passed": True}))
        files = me.build(self.d / "m.csv", "public_x", rel)
        mom = files["momentum"]
        self.assertEqual({(r[5], r[6]) for r in mom}, {("data_v0.2_sample", "synthetic")})
        self.assertEqual({r[5] for r in files["credit"]}, {"public_x"})
        (rel / "MANIFEST.json").write_text(json.dumps({"release_id": "bad", "validation_passed": False}))
        with self.assertRaises(me.EngineError):
            me.build(self.d / "m.csv", "public_x", rel)

    def test_write_and_cli(self):
        write_macro(self.d / "m.csv")
        (self.d / "pull_info.json").write_text(json.dumps({"release_id": "public_2026-11-13"}))
        self.assertEqual(me.main(["build", "--macro", str(self.d / "m.csv"), "-o", str(self.d / "out")]), 0)
        with open(self.d / "out" / "credit.csv", newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[0], me.HEADER)
        self.assertEqual(rows[1][5], "public_2026-11-13")

    def test_public_files_leave_out_ice_spreads(self):
        ps = write_macro(self.d / "m.csv")
        m = pd.read_csv(self.d / "m.csv")
        extra = pd.DataFrame([[p, sid, 0.03, "fred"] for p in ps for sid in ("BAMLH0A0HYM2", "BAMLC0A0CM")],
                             columns=m.columns)
        pd.concat([m, extra]).to_csv(self.d / "m.csv", index=False)
        full = {r[2] for r in me.build(self.d / "m.csv", "x")["credit"]}
        pub = {r[2] for r in me.build(self.d / "m.csv", "x", public=True)["credit"]}
        self.assertTrue({"hy_oas", "ig_oas"} <= full)
        self.assertEqual(pub, full - {"hy_oas", "ig_oas"})

    def test_duplicate_rows_are_rejected(self):
        pd.DataFrame([["2026-01", "DGS10", 0.04, "fred"], ["2026-01", "DGS10", 0.05, "fred"]],
                     columns=["period", "series_id", "value", "source_id"]).to_csv(self.d / "m.csv", index=False)
        with self.assertRaises(me.EngineError):
            me.build(self.d / "m.csv", "x")


if __name__ == "__main__":
    unittest.main(verbosity=1)
