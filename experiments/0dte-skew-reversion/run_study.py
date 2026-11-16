"""Research-only SPY 0DTE RR study. No network, credentials, orders or app DB."""
import argparse
import csv
import hashlib
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
HERE = Path(__file__).resolve().parent
FIELDS = (
    "timestamp quote_timestamp greeks_timestamp underlying_quote_timestamp "
    "symbol expiration option_symbol right strike bid ask bid_size ask_size "
    "iv delta underlying_bid underlying_ask multiplier exercise_style"
).split()


def aware(value):
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("timestamp requires UTC offset")
    return stamp.astimezone(timezone.utc)


def number(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("nonfinite number")
    return result


def read_calendar(path):
    calendar = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            close = aware(row["close_timestamp"])
            local = close.astimezone(ET)
            if (row["session_date"] != local.date().isoformat()
                    or row["session_date"] in calendar
                    or (local.hour, local.minute, local.second) not in [(13, 0, 0), (16, 0, 0)]):
                raise ValueError("invalid/duplicate calendar close; use official US half/full sessions")
            datetime.fromisoformat(row["session_date"])
            calendar[row["session_date"]] = close
    if not calendar:
        raise ValueError("empty calendar")
    return dict(sorted(calendar.items()))


def validate_row(row, calendar, cfg):
    ts = aware(row["timestamp"])
    local = ts.astimezone(ET)
    day = local.date().isoformat()
    if day not in calendar:
        raise ValueError("date_not_in_calendar")
    minute = local.hour * 60 + local.minute
    if (local.second or local.microsecond or minute % cfg["grid_minutes"]
            or minute < cfg["first_minute_et"]
            or ts > calendar[day] - timedelta(minutes=cfg["last_snapshot_minutes_before_close"])):
        raise ValueError("outside_snapshot_grid")
    if row["symbol"] != cfg["symbol"] or row["expiration"] != day:
        raise ValueError("not_target_0dte")
    if row["exercise_style"].lower() != "american" or row["right"] not in ("P", "C"):
        raise ValueError("contract_style_or_right")
    limits = {"quote_timestamp": cfg["max_option_quote_age_seconds"],
              "greeks_timestamp": cfg["max_greeks_age_seconds"],
              "underlying_quote_timestamp": cfg["max_underlying_quote_age_seconds"]}
    for field, limit in limits.items():
        if not 0 <= (ts - aware(row[field])).total_seconds() <= limit:
            raise ValueError("stale_or_future_" + field)
    result = dict(row, ts=ts, day=day, minute=minute)
    for field in ("strike", "bid", "ask", "bid_size", "ask_size", "iv", "delta",
                  "underlying_bid", "underlying_ask", "multiplier"):
        result[field] = number(row[field])
    if result["multiplier"] != cfg["option_multiplier"] or not row["option_symbol"].strip():
        raise ValueError("nonstandard_contract")
    if (not 0 < result["bid"] <= result["ask"] or result["bid_size"] < 1
            or result["ask_size"] < 1 or not 0 < result["underlying_bid"] <= result["underlying_ask"]):
        raise ValueError("invalid_or_empty_market")
    if not 0 < result["iv"] <= 5 or result["strike"] <= 0:
        raise ValueError("invalid_iv_or_strike")
    delta = result["delta"]
    if not (0 < delta < 1 if row["right"] == "C" else -1 < delta < 0):
        raise ValueError("invalid_delta_sign")
    return result


def read_quotes(path, calendar, cfg):
    snapshots = defaultdict(dict)
    rejected = Counter()
    invalid_snapshots = set()
    contract_specs = {}
    total = 0
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not set(FIELDS).issubset(reader.fieldnames or []):
            raise ValueError("missing CSV fields: " + ", ".join(sorted(set(FIELDS) - set(reader.fieldnames or []))))
        for raw in reader:
            total += 1
            try:
                row = validate_row(raw, calendar, cfg)
            except (ValueError, KeyError) as error:
                rejected[str(error)] += 1
                continue
            ts, symbol = row["ts"], row["option_symbol"]
            spec = (row["right"], row["strike"], row["expiration"], row["multiplier"])
            if symbol in contract_specs and contract_specs[symbol] != spec:
                raise ValueError("contract metadata changes for " + symbol)
            contract_specs[symbol] = spec
            existing = snapshots[ts]
            if symbol in existing:
                rejected["duplicate_contract_snapshot"] += 1
                invalid_snapshots.add(ts)
            if existing:
                first = next(iter(existing.values()))
                if (first["underlying_bid"], first["underlying_ask"], first["underlying_quote_timestamp"]) != (
                        row["underlying_bid"], row["underlying_ask"], row["underlying_quote_timestamp"]):
                    rejected["inconsistent_underlying_snapshot"] += 1
                    invalid_snapshots.add(ts)
            existing[symbol] = row
    for ts in invalid_snapshots:
        snapshots.pop(ts, None)
    return dict(snapshots), {"input_rows": total, "rejected_rows_by_reason": dict(rejected),
                             "rejected_whole_snapshots": len(invalid_snapshots)}


def interpolate_leg(rows, right, cfg):
    target = cfg["target_absolute_delta"]
    eligible = []
    for row in rows:
        spot = (row["underlying_bid"] + row["underlying_ask"]) / 2
        if row["right"] == right and (row["strike"] >= spot if right == "C" else row["strike"] <= spot):
            eligible.append(row)
    eligible.sort(key=lambda row: (abs(row["delta"]), row["option_symbol"]))
    if not eligible:
        return None
    nearest = min(eligible, key=lambda row: (abs(abs(row["delta"]) - target), row["option_symbol"]))
    exact = [row for row in eligible if abs(abs(row["delta"]) - target) < 1e-12]
    if exact:
        return exact[0]["iv"], nearest["option_symbol"]
    below = [row for row in eligible if abs(row["delta"]) < target]
    above = [row for row in eligible if abs(row["delta"]) > target]
    if not below or not above:
        return None  # never extrapolate a sparse chain
    left, right_row = below[-1], above[0]
    width = abs(right_row["delta"]) - abs(left["delta"])
    if width > cfg["maximum_interpolation_delta_gap"]:
        return None
    weight = (target - abs(left["delta"])) / width
    return left["iv"] + weight * (right_row["iv"] - left["iv"]), nearest["option_symbol"]


def build_rr(snapshots, cfg):
    result = {}
    for ts, chain in sorted(snapshots.items()):
        put = interpolate_leg(chain.values(), "P", cfg)
        call = interpolate_leg(chain.values(), "C", cfg)
        if put and call:
            first = next(iter(chain.values()))
            result[ts] = {"ts": ts, "day": first["day"], "minute": first["minute"],
                          "rr": 100 * (put[0] - call[0]), "put": put[1], "call": call[1]}
    return result


def normalize(rr, calendar, cfg):
    days = list(calendar)
    index = {day: i for i, day in enumerate(days)}
    history = defaultdict(list)
    result = {}
    for ts, row in sorted(rr.items()):
        i = index[row["day"]]
        past = [value for day_i, value in history[row["minute"]]
                if i - cfg["baseline_lookback_sessions"] <= day_i < i]
        if len(past) >= cfg["minimum_baseline_observations"]:
            sd = statistics.stdev(past)
            if sd > 1e-9:
                mu = statistics.mean(past)
                result[ts] = dict(row, baseline=mu, sd=sd, residual=row["rr"] - mu,
                                  z=(row["rr"] - mu) / sd)
        history[row["minute"]].append((i, row["rr"]))
    return result


def ou_diagnostic(rows, grid_minutes):
    pairs = []
    for ts, row in rows.items():
        next_row = rows.get(ts + timedelta(minutes=grid_minutes))
        if next_row and next_row["day"] == row["day"]:
            pairs.append((row["residual"], next_row["residual"]))
    if len(pairs) < 3:
        return {"pairs": len(pairs), "ar1": None, "half_life_minutes": None}
    mx, my = statistics.mean(x for x, _ in pairs), statistics.mean(y for _, y in pairs)
    denom = sum((x - mx) ** 2 for x, _ in pairs)
    beta = sum((x - mx) * (y - my) for x, y in pairs) / denom if denom else None
    half = -grid_minutes * math.log(2) / math.log(beta) if beta is not None and 0 < beta < 1 else None
    return {"pairs": len(pairs), "ar1": beta, "half_life_minutes": half,
            "note": "Diagnostic only: pooled residual AR(1), no stationarity proof, no automatic strategy rejection."}


def fill_cash(quantity, bid, ask, slippage, fee):
    """Signed quantity: buying costs ask; selling receives bid; adverse slippage."""
    if not quantity:
        return 0.0
    price = ask + slippage if quantity > 0 else bid - slippage
    if price < 0:
        raise ValueError("adverse_slippage_exceeds_bid")
    return -quantity * price - abs(quantity) * fee


def replay(signal, snapshots, cfg, stress=1):
    direction = -1 if signal["z"] > 0 else 1  # positive = long put, short call
    step = timedelta(minutes=cfg["grid_minutes"])
    entry = signal["ts"] + step
    exit_ts = entry + timedelta(minutes=cfg["holding_minutes_after_entry"])
    put, call = signal["put"], signal["call"]
    timestamps = [signal["ts"] + i * step for i in range(
        1 + int((exit_ts - signal["ts"]) / step))]
    # Missing fixed-strike quote anywhere makes the entire replay unpriceable.
    if any(ts not in snapshots or put not in snapshots[ts] or call not in snapshots[ts] for ts in timestamps):
        return {"status": "unpriceable", "reason": "missing_fixed_contract_path"}
    oq = cfg["option_contracts_each_leg"]
    multiplier = cfg["option_multiplier"]
    leg_quantities = [(put, direction * oq), (call, -direction * oq)]
    opt_slip = cfg["option_extra_slippage_usd_per_share"] * stress
    stock_slip = cfg["stock_extra_slippage_usd_per_share"] * stress
    cash = 0.0
    shares = 0
    turnover = 0
    path = []
    financing = 0.0
    for i, ts in enumerate(timestamps[1:], start=1):
        chain = snapshots[ts]
        spot_row = chain[put]
        if i > 1:
            prev = snapshots[timestamps[i - 1]][put]
            years = step.total_seconds() / (365 * 24 * 3600)
            cost = max(-cash, 0) * cfg["debit_financing_annual"] * years
            cost += max(-shares, 0) * prev["underlying_ask"] * cfg["short_stock_borrow_annual"] * years
            financing += cost
            cash -= cost
        if ts == entry or ts == exit_ts:
            for symbol, contracts in leg_quantities:
                row = chain[symbol]
                signed = contracts if ts == entry else -contracts
                cash += fill_cash(signed * multiplier, row["bid"], row["ask"], opt_slip,
                                  cfg["option_fee_usd_per_contract_side"] / multiplier)
        # Initial and subsequent hedges use PRIOR snapshot deltas, executed now.
        previous_chain = snapshots[timestamps[i - 1]]
        target = 0 if ts == exit_ts else round(-multiplier * sum(
            contracts * previous_chain[symbol]["delta"] for symbol, contracts in leg_quantities))
        change = target - shares
        cash += fill_cash(change, spot_row["underlying_bid"], spot_row["underlying_ask"],
                          stock_slip, cfg["stock_fee_usd_per_share_side"])
        shares = target
        turnover += abs(change)
        liquidated = cash
        if ts != exit_ts:
            for symbol, contracts in leg_quantities:
                row = chain[symbol]
                liquidated += fill_cash(-contracts * multiplier, row["bid"], row["ask"], opt_slip,
                                        cfg["option_fee_usd_per_contract_side"] / multiplier)
            liquidated += fill_cash(-shares, spot_row["underlying_bid"], spot_row["underlying_ask"],
                                    stock_slip, cfg["stock_fee_usd_per_share_side"])
        path.append({"timestamp": ts.isoformat(), "hedge_shares": shares,
                     "liquidation_pnl_usd": liquidated})
    return {"status": "priced", "net_pnl_usd": cash, "stock_share_turnover": turnover,
            "financing_and_borrow_usd": financing,
            "worst_liquidation_pnl_usd": min(p["liquidation_pnl_usd"] for p in path), "path": path}


def percentile(values, q):
    values = sorted(values)
    pos = (len(values) - 1) * q
    lower, upper = math.floor(pos), math.ceil(pos)
    return values[lower] + (values[upper] - values[lower]) * (pos - lower)


def block_interval(values, cfg):
    if len(values) < 2:
        return None
    rng = random.Random(cfg["random_seed"])
    length = min(cfg["bootstrap_block_sessions"], len(values))
    if len(values) < 2 * length:
        return None  # too few independent blocks
    means = []
    for _ in range(cfg["bootstrap_draws"]):
        sample = []
        while len(sample) < len(values):
            start = rng.randrange(len(values))
            sample.extend(values[(start + j) % len(values)] for j in range(length))
        means.append(statistics.mean(sample[:len(values)]))
    return [percentile(means, 0.025), percentile(means, 0.975)]


def analyze(snapshots, calendar, cfg, evaluation_start):
    rr = build_rr(snapshots, cfg)
    normalized = normalize(rr, calendar, cfg)
    train = {ts: row for ts, row in normalized.items() if row["day"] < evaluation_start}
    test = {ts: row for ts, row in normalized.items() if row["day"] >= evaluation_start}
    sessions = [day for day in calendar if day >= evaluation_start]
    if not sessions:
        raise ValueError("no evaluation calendar sessions")
    daily = {day: {"base": 0.0, "stress": 0.0, "signals": 0, "unpriceable": 0,
                   "forecast": [], "valid_rr": 0, "expected_rr": 0} for day in sessions}
    for day in sessions:
        first = datetime.fromisoformat(day).replace(tzinfo=ET) + timedelta(minutes=cfg["first_minute_et"])
        last = calendar[day] - timedelta(minutes=cfg["last_snapshot_minutes_before_close"])
        expected = max(0, int((last - first) / timedelta(minutes=cfg["grid_minutes"])) + 1)
        daily[day]["expected_rr"] = expected
        daily[day]["valid_rr"] = sum(row["day"] == day for row in rr.values())
    ledger = []
    occupied_until = None
    for ts, signal in sorted(test.items()):
        if (occupied_until is not None and ts <= occupied_until
                or abs(signal["z"]) < cfg["entry_absolute_z"]
                or ts > calendar[signal["day"]] - timedelta(minutes=cfg["last_signal_minutes_before_close"])):
            continue
        entry = ts + timedelta(minutes=cfg["grid_minutes"])
        occupied_until = entry + timedelta(minutes=cfg["holding_minutes_after_entry"])
        direction = -1 if signal["z"] > 0 else 1
        endpoint = test.get(ts + timedelta(minutes=cfg["holding_minutes_after_entry"]))
        # Compare to the FUTURE slot's baseline known at signal time (prior days only).
        convergence = direction * (endpoint["residual"] - signal["residual"]) if endpoint else None
        record = {"signal_timestamp": ts.isoformat(), "entry_timestamp": entry.isoformat(),
                  "exit_timestamp": occupied_until.isoformat(), "session_date": signal["day"],
                  "z": signal["z"], "rr_vol_points": signal["rr"], "direction": direction,
                  "put": signal["put"], "call": signal["call"],
                  "convergence_vol_points_30m": convergence}
        try:
            record["base"] = replay(signal, snapshots, cfg)
            record["stress"] = replay(signal, snapshots, cfg, cfg["cost_stress_extra_slippage_multiplier"])
        except ValueError as error:
            record["base"] = record["stress"] = {"status": "unpriceable", "reason": str(error)}
        day_metrics = daily[signal["day"]]
        day_metrics["signals"] += 1
        if convergence is not None:
            day_metrics["forecast"].append(convergence)
        if record["base"]["status"] == record["stress"]["status"] == "priced":
            day_metrics["base"] += record["base"]["net_pnl_usd"]
            day_metrics["stress"] += record["stress"]["net_pnl_usd"]
        else:
            day_metrics["unpriceable"] += 1
        ledger.append(record)
    missing = sum(v["unpriceable"] for v in daily.values())
    forecast_missing = sum(r["convergence_vol_points_30m"] is None for r in ledger)
    expected = sum(v["expected_rr"] for v in daily.values())
    coverage = sum(v["valid_rr"] for v in daily.values()) / expected if expected else 0
    base = [v["base"] for v in daily.values()]
    stress = [v["stress"] for v in daily.values()]
    # Missing executions are never silently imputed as zero return.
    base_ci = block_interval(base, cfg) if not missing else None
    stress_ci = block_interval(stress, cfg) if not missing else None
    forecast_daily = [statistics.mean(v["forecast"]) for v in daily.values() if v["forecast"]]
    forecast_ci = block_interval(forecast_daily, cfg) if not forecast_missing else None
    active = sum(v["signals"] > 0 for v in daily.values())
    gates = {"enough_evaluation_sessions": len(sessions) >= cfg["minimum_evaluation_sessions_for_gate"],
             "enough_active_sessions": active >= cfg["minimum_active_sessions_for_gate"],
             "snapshot_coverage": coverage >= cfg["minimum_snapshot_coverage"],
             "all_attempted_paths_priced": bool(ledger) and missing == 0,
             "positive_convergence_interval": forecast_ci is not None and forecast_ci[0] > 0,
             "positive_base_net_interval": base_ci is not None and base_ci[0] > 0,
             "positive_stress_net_interval": stress_ci is not None and stress_ci[0] > 0}
    report = {"status": "candidate_for_prospective_paper_validation" if all(gates.values()) else "not_demonstrated",
              "evaluation_start": evaluation_start, "evaluation_sessions": len(sessions),
              "active_sessions": active, "attempted_signals": len(ledger),
              "unpriceable_paths": missing, "missing_forecast_endpoints": forecast_missing,
              "snapshot_coverage": coverage, "gate_checks": gates,
              "train_ou_diagnostic": ou_diagnostic(train, cfg["grid_minutes"]),
              "test_ou_diagnostic": ou_diagnostic(test, cfg["grid_minutes"]),
              "mean_daily_net_usd": statistics.mean(base) if not missing else None,
              "mean_daily_net_95pct_block_interval": base_ci,
              "mean_daily_stress_net_usd": statistics.mean(stress) if not missing else None,
              "mean_daily_stress_95pct_block_interval": stress_ci,
              "mean_active_day_convergence_vol_points": statistics.mean(forecast_daily) if forecast_daily else None,
              "convergence_95pct_block_interval": forecast_ci,
              "covered_subset_base_pnl_usd": sum(base),
              "covered_subset_stress_pnl_usd": sum(stress),
              "limitations": ["Retrospective study unless the split was fixed before collecting outcomes.",
                              "NBBO sizes are contract counts; underlying displayed depth and actual fills are not modeled.",
                              "One 5-minute fill/hedge delay; execution and intra-grid adverse excursions remain uncertain.",
                              "Delta-neutral risk reversal retains gamma, vega, jump and model risk; short leg has no fixed loss cap.",
                              "No taxes, cash credit interest, broker margin simulation or within-session risk stops.",
                              "OU half-life is diagnostic; gates are research choices, not proof or production authorization.",
                              "Missing chain snapshots may be informative; inspect coverage by session and regime."]}
    return report, ledger, daily, normalized


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quotes", type=Path, required=True)
    parser.add_argument("--calendar", type=Path, required=True)
    parser.add_argument("--evaluation-start", required=True)
    parser.add_argument("--config", type=Path, default=HERE / "research-config.json")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if datetime.fromisoformat(args.evaluation_start).date().isoformat() != args.evaluation_start:
        raise ValueError("evaluation-start must be YYYY-MM-DD")
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    if cfg["symbol"] != "SPY" or cfg["option_contracts_each_leg"] != 1 or cfg["option_multiplier"] != 100:
        raise ValueError("This prototype supports one standard SPY contract per leg only")
    if (cfg["grid_minutes"] != 5 or cfg["holding_minutes_after_entry"] != 30
            or cfg["minimum_baseline_observations"] < 2):
        raise ValueError("Keep the preregistered five-minute grid and 30-minute primary horizon")
    for key in ("option_extra_slippage_usd_per_share", "stock_extra_slippage_usd_per_share",
                "option_fee_usd_per_contract_side", "stock_fee_usd_per_share_side",
                "debit_financing_annual", "short_stock_borrow_annual"):
        if not math.isfinite(cfg[key]) or cfg[key] < 0:
            raise ValueError("invalid cost: " + key)
    calendar = read_calendar(args.calendar)
    snapshots, audit = read_quotes(args.quotes, calendar, cfg)
    report, ledger, daily, normalized = analyze(snapshots, calendar, cfg, args.evaluation_start)
    report["data_audit"] = audit
    report["provenance"] = {"config": cfg, "sha256": {str(path): digest(path) for path in (
        args.quotes, args.calendar, args.config, Path(__file__))}}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    (args.out / "trade-ledger.json").write_text(json.dumps(ledger, indent=2, allow_nan=False), encoding="utf-8")
    (args.out / "daily-results.json").write_text(json.dumps(daily, indent=2, allow_nan=False), encoding="utf-8")
    with (args.out / "signals.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp", "session_date", "rr_vol_points", "baseline", "sd", "z", "put", "call"])
        writer.writeheader()
        for ts, row in sorted(normalized.items()):
            writer.writerow({"timestamp": ts.isoformat(), "session_date": row["day"], "rr_vol_points": row["rr"],
                             **{key: row[key] for key in ("baseline", "sd", "z", "put", "call")}})
    print(json.dumps({key: report[key] for key in ("status", "attempted_signals", "unpriceable_paths", "snapshot_coverage")}, indent=2))


if __name__ == "__main__":
    main()
