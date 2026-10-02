import copy
import csv
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

EXPERIMENT = Path(__file__).resolve().parents[1] / "experiments" / "0dte-skew-reversion"
spec = importlib.util.spec_from_file_location("quantileflow_skew_0dte_study", EXPERIMENT / "run_study.py")
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)
CFG = json.loads((EXPERIMENT / "research-config.json").read_text(encoding="utf-8"))


def raw_row(ts="2026-09-01T10:00:00-04:00", right="P", delta=-0.25, iv=0.30):
    day = study.aware(ts).astimezone(study.ET).date().isoformat()
    return {"timestamp": ts, "quote_timestamp": ts, "greeks_timestamp": ts,
            "underlying_quote_timestamp": ts, "symbol": "SPY", "expiration": day,
            "option_symbol": day + right, "right": right, "strike": "99" if right == "P" else "101",
            "bid": "1", "ask": "1", "bid_size": "10", "ask_size": "10",
            "iv": str(iv), "delta": str(delta), "underlying_bid": "100", "underlying_ask": "100",
            "multiplier": "100", "exercise_style": "american"}


def chain_path():
    ts = study.aware("2026-09-01T10:00:00-04:00")
    day = "2026-09-01"
    calendar = {day: study.aware(day + "T16:00:00-04:00")}
    snapshots = {}
    for i in range(8):
        stamp = (ts + timedelta(minutes=5 * i)).isoformat()
        rows = [study.validate_row(raw_row(stamp), calendar, CFG),
                study.validate_row(raw_row(stamp, "C", 0.25, 0.20), calendar, CFG)]
        snapshots[study.aware(stamp)] = {r["option_symbol"]: r for r in rows}
    signal = {"ts": ts, "day": day, "minute": 600, "rr": 10, "z": -3,
              "residual": -3, "put": day + "P", "call": day + "C"}
    return signal, snapshots, calendar


class StudyTests(unittest.TestCase):
    def test_timezone_required_and_dst(self):
        with self.assertRaises(ValueError):
            study.aware("2026-01-01T10:00:00")
        self.assertEqual(study.aware("2026-01-02T10:00:00-05:00").hour, 15)
        self.assertEqual(study.aware("2026-09-01T10:00:00-04:00").hour, 14)

    def test_future_and_stale_quotes_rejected(self):
        _, _, calendar = chain_path()
        for field, stamp in [("quote_timestamp", "2026-09-01T10:00:01-04:00"),
                             ("underlying_quote_timestamp", "2026-09-01T09:59:54-04:00")]:
            row = raw_row()
            row[field] = stamp
            with self.assertRaises(ValueError):
                study.validate_row(row, calendar, CFG)

    def test_half_day_close_and_grid(self):
        calendar = {"2026-09-01": study.aware("2026-09-01T13:00:00-04:00")}
        with self.assertRaises(ValueError):
            study.validate_row(raw_row("2026-09-01T13:00:00-04:00"), calendar, CFG)
        with self.assertRaises(ValueError):
            study.validate_row(raw_row("2026-09-01T10:01:00-04:00"), calendar, CFG)

    def test_iv_units_and_delta_sign(self):
        _, _, calendar = chain_path()
        with self.assertRaises(ValueError):
            study.validate_row(raw_row(iv=30), calendar, CFG)
        with self.assertRaises(ValueError):
            study.validate_row(raw_row(delta=0.25), calendar, CFG)

    def test_interpolation_and_no_extrapolation(self):
        _, _, calendar = chain_path()
        left = study.validate_row(raw_row(delta=-0.20, iv=0.20), calendar, CFG)
        right = study.validate_row(raw_row(delta=-0.30, iv=0.40), calendar, CFG)
        left["option_symbol"] = "left"
        right["option_symbol"] = "right"
        self.assertAlmostEqual(study.interpolate_leg([left, right], "P", CFG)[0], 0.30)
        self.assertIsNone(study.interpolate_leg([left], "P", CFG))
        right["delta"] = -0.50
        self.assertIsNone(study.interpolate_leg([left, right], "P", CFG))

    def test_duplicate_snapshot_not_last_row_wins(self):
        _, _, calendar = chain_path()
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "quotes.csv"
            with file.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, study.FIELDS)
                writer.writeheader()
                writer.writerows([raw_row(), raw_row()])
            snapshots, audit = study.read_quotes(file, calendar, CFG)
        self.assertEqual(snapshots, {})
        self.assertEqual(audit["rejected_whole_snapshots"], 1)

    def test_normalization_uses_prior_sessions_only(self):
        cfg = dict(CFG, minimum_baseline_observations=2)
        rr, calendar = {}, {}
        for i, value in enumerate([1, 3, 100, 1000]):
            day = f"2026-09-0{i + 1}"
            ts = study.aware(day + "T10:00:00-04:00")
            calendar[day] = study.aware(day + "T16:00:00-04:00")
            rr[ts] = {"ts": ts, "day": day, "minute": 600, "rr": value}
        result = study.normalize(rr, calendar, cfg)
        third = list(rr)[2]
        self.assertEqual(result[third]["baseline"], 2)
        rr[list(rr)[3]]["rr"] = -9999
        self.assertEqual(study.normalize(rr, calendar, cfg)[third], result[third])

    def test_ou_no_overnight_or_gap_pairs(self):
        ts = study.aware("2026-09-01T10:00:00-04:00")
        rows = {ts: {"day": "2026-09-01", "residual": 1},
                ts + timedelta(minutes=10): {"day": "2026-09-01", "residual": 2},
                ts + timedelta(days=1): {"day": "2026-09-02", "residual": 3}}
        self.assertEqual(study.ou_diagnostic(rows, 5)["pairs"], 0)

    def test_execution_signs(self):
        self.assertAlmostEqual(study.fill_cash(100, 1, 1.1, 0.01, 0.005), -111.5)
        self.assertAlmostEqual(study.fill_cash(-100, 1, 1.1, 0.01, 0.005), 98.5)
        self.assertEqual(study.fill_cash(0, 1, 1.1, 0.01, 0.005), 0)

    def test_flat_market_net_roundtrip_and_initial_delta(self):
        signal, snapshots, _ = chain_path()
        cfg = dict(CFG, debit_financing_annual=0, short_stock_borrow_annual=0)
        result = study.replay(signal, snapshots, cfg)
        # Two option legs roundtrip: $4 adverse slippage + $2.60 fees.
        # Buy and sell 50 shares: $1 slippage + $0.50 fees.
        self.assertAlmostEqual(result["net_pnl_usd"], -8.10)
        self.assertEqual(result["path"][0]["hedge_shares"], 50)
        self.assertEqual(result["stock_share_turnover"], 100)
        stressed = study.replay(signal, snapshots, cfg, 2)
        self.assertLess(stressed["net_pnl_usd"], result["net_pnl_usd"])

    def test_initial_and_subsequent_hedges_lag(self):
        signal, snapshots, _ = chain_path()
        ts = signal["ts"] + timedelta(minutes=5)
        snapshots[ts][signal["put"]]["delta"] = -0.50
        result = study.replay(signal, snapshots, CFG)
        self.assertEqual(result["path"][0]["hedge_shares"], 50)
        self.assertEqual(result["path"][1]["hedge_shares"], 75)

    def test_linear_delta_hedge_offsets_directional_move(self):
        signal, snapshots, _ = chain_path()
        cfg = dict(CFG, debit_financing_annual=0, short_stock_borrow_annual=0,
                   stock_extra_slippage_usd_per_share=0, option_extra_slippage_usd_per_share=0,
                   stock_fee_usd_per_share_side=0, option_fee_usd_per_contract_side=0)
        for i, chain in enumerate(snapshots.values()):
            # Move occurs after entry: P loses .25, C gains .25, stock gains 1.
            if i >= 2:
                for row in chain.values():
                    row["underlying_bid"] = row["underlying_ask"] = 101
                    row["bid"] = row["ask"] = 0.75 if row["right"] == "P" else 1.25
        self.assertAlmostEqual(study.replay(signal, snapshots, cfg)["net_pnl_usd"], 0)

    def test_missing_fixed_strike_never_substituted(self):
        signal, snapshots, _ = chain_path()
        ts = signal["ts"] + timedelta(minutes=15)
        row = snapshots[ts].pop(signal["put"])
        snapshots[ts]["another_put"] = row
        self.assertEqual(study.replay(signal, snapshots, CFG)["status"], "unpriceable")

    def test_bootstrap_requires_multiple_blocks(self):
        self.assertIsNone(study.block_interval([1, 2], CFG))
        result = study.block_interval([1] * 30, dict(CFG, bootstrap_draws=10))
        self.assertEqual(result, [1, 1])

    def test_signal_decisions_independent_of_future_priceability(self):
        signal, snapshots, calendar = chain_path()
        synthetic = {}
        for ts in snapshots:
            synthetic[ts] = dict(signal, ts=ts)
        from unittest.mock import patch
        cfg = dict(CFG, bootstrap_draws=10)
        with patch.object(study, "normalize", return_value=synthetic):
            first_report, first_ledger, _, _ = study.analyze(snapshots, calendar, cfg, signal["day"])
        broken = copy.deepcopy(snapshots)
        broken.pop(signal["ts"] + timedelta(minutes=15))
        with patch.object(study, "normalize", return_value=synthetic):
            report, ledger, _, _ = study.analyze(broken, calendar, cfg, signal["day"])
        self.assertEqual([r["signal_timestamp"] for r in first_ledger], [r["signal_timestamp"] for r in ledger])
        self.assertEqual(report["unpriceable_paths"], 1)
        self.assertIsNone(report["mean_daily_net_usd"])
        self.assertIsNone(report["mean_daily_net_95pct_block_interval"])
        self.assertEqual(report["status"], "not_demonstrated")

    def test_cli_writes_auditable_results_without_real_data_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quotes, calendar = root / "quotes.csv", root / "calendar.csv"
            with calendar.open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["session_date", "close_timestamp"])
                writer.writerow(["2026-09-01", "2026-09-01T16:00:00-04:00"])
            with quotes.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, study.FIELDS)
                writer.writeheader()
                writer.writerows([raw_row(), raw_row(right="C", delta=0.25, iv=0.20)])
            result = subprocess.run([sys.executable, str(Path(study.__file__)), "--quotes", str(quotes),
                                     "--calendar", str(calendar), "--evaluation-start", "2026-09-01",
                                     "--out", str(root / "results")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((root / "results" / "report.json").read_text())
            self.assertEqual(report["status"], "not_demonstrated")
            self.assertEqual(report["attempted_signals"], 0)
            self.assertEqual(len(report["provenance"]["sha256"]), 4)
            self.assertTrue((root / "results" / "signals.csv").exists())


if __name__ == "__main__":
    unittest.main()
