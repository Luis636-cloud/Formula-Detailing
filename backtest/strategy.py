"""Kern-Engine der Strategie: Sweep (3) -> CHoCH-Bestaetigung (4) ->
Entry per Retest (5) -> SL am Sweep-Wick (6) -> TP fix oder naechstes
Liquiditaetslevel (7). Ein Trade gleichzeitig pro Instrument.
"""
import bisect
import numpy as np
import pandas as pd

from levels import find_fractal_swings, asia_session_levels, cluster_equal_levels
from bias import daily_bias_map
from data_utils import resample_h4

KILLZONE_PRESETS = {
    "london": [(7, 10)],
    "ny": [(12, 15)],
    "both": [(7, 10), (12, 15)],
}


def precompute(df: pd.DataFrame, swing_n: int, micro_n: int,
                asia_start: int, asia_end: int, ema_period: int = 20):
    h4 = resample_h4(df)
    bias_map = daily_bias_map(h4, ema_period)
    swings = find_fractal_swings(df, swing_n)
    micro_swings = find_fractal_swings(df, micro_n)
    asia_levels = asia_session_levels(df, asia_start, asia_end)
    confirmed_pos_arr = [s["confirmed_pos"] for s in swings]
    return {
        "bias_map": bias_map,
        "swings": swings,
        "micro_swings": micro_swings,
        "asia_levels": asia_levels,
        "confirmed_pos_arr": confirmed_pos_arr,
    }


def _find_choch(df_close, micro_swings, sweep_pos, direction, choch_window, n):
    end = min(sweep_pos + choch_window, n - 1)
    best = None
    if direction == "bullish":
        cands = [s for s in micro_swings if s["type"] == "high" and s["pos"] > sweep_pos
                  and s["confirmed_pos"] <= end]
    else:
        cands = [s for s in micro_swings if s["type"] == "low" and s["pos"] > sweep_pos
                  and s["confirmed_pos"] <= end]
    for s in cands:
        start = s["confirmed_pos"] + 1
        if start > end:
            continue
        seg = df_close[start:end + 1]
        if direction == "bullish":
            hit = np.where(seg > s["price"])[0]
        else:
            hit = np.where(seg < s["price"])[0]
        if len(hit) > 0:
            confirm_pos = start + hit[0]
            if best is None or confirm_pos < best[0]:
                best = (confirm_pos, s["price"], s["pos"])
    return best


def _find_retest(low, high, start_pos, level_price, tol, window, n):
    end = min(start_pos + window, n - 1)
    for k in range(start_pos + 1, end + 1):
        if low[k] - tol <= level_price <= high[k] + tol:
            return k
    return None


def _compute_sl_tp(direction, entry_price, wick_extreme, params, candidates, pip_size):
    buffer = params["sl_buffer_pips"] * pip_size
    tp_mode = params["tp_mode"]
    rr = params["rr"]
    min_rr = params.get("min_rr", 1.0)
    if direction == "bullish":
        sl = wick_extreme - buffer
        risk = entry_price - sl
        if risk <= 0:
            return None
        if tp_mode == "fixed":
            tp = entry_price + rr * risk
        else:
            opp = [c for c in candidates if c[1] == "high" and c[0] > entry_price]
            if opp:
                nearest = min(opp, key=lambda c: c[0])[0]
                rr_c = (nearest - entry_price) / risk
                tp = nearest if rr_c >= min_rr else entry_price + rr * risk
            else:
                tp = entry_price + rr * risk
    else:
        sl = wick_extreme + buffer
        risk = sl - entry_price
        if risk <= 0:
            return None
        if tp_mode == "fixed":
            tp = entry_price - rr * risk
        else:
            opp = [c for c in candidates if c[1] == "low" and c[0] < entry_price]
            if opp:
                nearest = max(opp, key=lambda c: c[0])[0]
                rr_c = (entry_price - nearest) / risk
                tp = nearest if rr_c >= min_rr else entry_price - rr * risk
            else:
                tp = entry_price - rr * risk
    return sl, tp


def _simulate_trade(df, entry_pos, entry_price, sl, tp, direction, max_hold, spread):
    n = len(df)
    end = min(entry_pos + max_hold, n - 1)
    low = df["low"].values
    high = df["high"].values
    close = df["close"].values
    eff_entry = entry_price + spread if direction == "bullish" else entry_price - spread
    risk = abs(eff_entry - sl)
    exit_pos, exit_price, outcome = end, close[end], "timeout"
    for k in range(entry_pos + 1, end + 1):
        hit_sl = (low[k] <= sl) if direction == "bullish" else (high[k] >= sl)
        hit_tp = (high[k] >= tp) if direction == "bullish" else (low[k] <= tp)
        if hit_sl:
            exit_pos, exit_price, outcome = k, sl, "sl"  # konservativ: SL zuerst, falls beides in einem Bar
            break
        if hit_tp:
            exit_pos, exit_price, outcome = k, tp, "tp"
            break
    pnl = (exit_price - eff_entry) if direction == "bullish" else (eff_entry - exit_price)
    r_multiple = pnl / risk if risk > 0 else 0.0
    return {
        "entry_time": df.index[entry_pos], "entry_price": eff_entry, "direction": direction,
        "sl": sl, "tp": tp, "exit_time": df.index[exit_pos], "exit_price": exit_price,
        "exit_pos": exit_pos, "outcome": outcome, "r_multiple": r_multiple,
    }


def run_strategy(df: pd.DataFrame, pre: dict, params: dict, pip_size: float, spread: float):
    swings = pre["swings"]
    micro_swings = pre["micro_swings"]
    confirmed_pos_arr = pre["confirmed_pos_arr"]
    asia_levels = pre["asia_levels"]
    bias_map = pre["bias_map"]

    killzones = KILLZONE_PRESETS[params["killzone_mode"]]
    eq_tol = params["eq_tol_pips"] * pip_size
    retest_tol = params["retest_tol_pips"] * pip_size
    eq_lookback = params.get("eq_lookback", 30)

    low = df["low"].values
    high = df["high"].values
    close = df["close"].values
    idx = df.index
    n = len(df)

    trades = []
    i = 0
    swept_today = set()
    current_day = None
    cache_count = -1
    cache = None  # (last_high, last_low, eq_highs, eq_lows)

    while i < n:
        ts = idx[i]
        day = ts.date()
        if day != current_day:
            current_day = day
            swept_today = set()

        bias = bias_map.get(day, "neutral")
        hour = ts.hour
        in_kz = any(a <= hour < b for a, b in killzones)

        if bias != "neutral" and in_kz:
            n_confirmed = bisect.bisect_right(confirmed_pos_arr, i)
            if n_confirmed != cache_count:
                recent = swings[:n_confirmed]
                last_high = next((s for s in reversed(recent) if s["type"] == "high"), None)
                last_low = next((s for s in reversed(recent) if s["type"] == "low"), None)
                eq_highs = cluster_equal_levels(recent, "high", eq_tol, eq_lookback)
                eq_lows = cluster_equal_levels(recent, "low", eq_tol, eq_lookback)
                cache = (last_high, last_low, eq_highs, eq_lows)
                cache_count = n_confirmed
            last_high, last_low, eq_highs, eq_lows = cache

            candidates = []
            a = asia_levels.get(day)
            if a is not None and ts >= a["ready_at"]:
                candidates.append((a["high"], "high", f"asia_high_{day}"))
                candidates.append((a["low"], "low", f"asia_low_{day}"))
            if last_high:
                candidates.append((last_high["price"], "high", f"sh_{last_high['pos']}"))
            if last_low:
                candidates.append((last_low["price"], "low", f"sl_{last_low['pos']}"))
            for c in eq_highs:
                candidates.append((c["price"], "high", f"eqh_{round(c['price'], 6)}"))
            for c in eq_lows:
                candidates.append((c["price"], "low", f"eql_{round(c['price'], 6)}"))

            sweep = None
            if bias == "bullish":
                for price, typ, lid in candidates:
                    if typ != "low" or lid in swept_today:
                        continue
                    if low[i] < price and close[i] > price:
                        sweep = (price, lid, "bullish", low[i])
                        break
            else:
                for price, typ, lid in candidates:
                    if typ != "high" or lid in swept_today:
                        continue
                    if high[i] > price and close[i] < price:
                        sweep = (price, lid, "bearish", high[i])
                        break

            if sweep:
                level_price, lid, direction, wick_extreme = sweep
                swept_today.add(lid)
                choch = _find_choch(close, micro_swings, i, direction, params["choch_window"], n)
                if choch:
                    confirm_pos, choch_level, _ = choch
                    entry_pos = _find_retest(low, high, confirm_pos, choch_level, retest_tol,
                                               params["retest_window"], n)
                    if entry_pos:
                        sltp = _compute_sl_tp(direction, choch_level, wick_extreme, params,
                                                candidates, pip_size)
                        if sltp:
                            sl, tp = sltp
                            trade = _simulate_trade(df, entry_pos, choch_level, sl, tp, direction,
                                                      params["max_hold_bars"], spread)
                            trade["instrument_pos_entry"] = entry_pos
                            trades.append(trade)
                            i = trade["exit_pos"]
                            continue
        i += 1
    return trades
