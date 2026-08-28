"""Kern-Engine der Strategie: Sweep (3) -> CHoCH-Bestaetigung (4) ->
Entry per Retest (5) -> SL am Sweep-Wick (6) -> TP fix oder naechstes
Liquiditaetslevel (7). Ein Trade gleichzeitig pro Instrument.
"""
import bisect
import numpy as np
import pandas as pd

from levels import find_fractal_swings, asia_session_levels, cluster_equal_levels
from bias import daily_bias_map, daily_trend_strength_map
from data_utils import resample_h4
from indicators import atr_series, rolling_median_volume

KILLZONE_PRESETS = {
    "london": [(7, 10)],
    "ny": [(12, 15)],
    "both": [(7, 10), (12, 15)],
}


def _split_by_type(swings):
    """Trennt eine nach confirmed_pos sortierte Swing-Liste in High-/Low-
    Teillisten (bleiben dabei selbst nach pos/confirmed_pos sortiert) und
    liefert dazu deren confirmed_pos- sowie pos-Arrays fuer bisect.

    Performance: das ist die Grundlage dafuer, dass wir bei jedem Bar nur
    noch O(log n) statt O(n) ueber die (bei Monaten an 5m-Daten schnell
    zehntausende Eintraege lange) Swing-Historie suchen muessen.
    """
    highs = [s for s in swings if s["type"] == "high"]
    lows = [s for s in swings if s["type"] == "low"]
    return {
        "high": {"items": highs, "conf": [s["confirmed_pos"] for s in highs],
                  "pos": [s["pos"] for s in highs]},
        "low": {"items": lows, "conf": [s["confirmed_pos"] for s in lows],
                 "pos": [s["pos"] for s in lows]},
    }


def precompute(df: pd.DataFrame, swing_n: int, micro_n: int,
                asia_start: int, asia_end: int, ema_period: int = 20):
    h4 = resample_h4(df)
    bias_map = daily_bias_map(h4, ema_period)
    trend_strength_map = daily_trend_strength_map(h4, ema_period)
    swings = find_fractal_swings(df, swing_n)
    micro_swings = find_fractal_swings(df, micro_n)
    asia_levels = asia_session_levels(df, asia_start, asia_end)
    atr_m5 = atr_series(df, 14).values
    vol_median = rolling_median_volume(df, 20).values
    body = (df["close"] - df["open"]).abs().values
    return {
        "bias_map": bias_map,
        "trend_strength_map": trend_strength_map,
        "swings_by_type": _split_by_type(swings),
        "micro_by_type": _split_by_type(micro_swings),
        "asia_levels": asia_levels,
        "atr_m5": atr_m5,
        "vol_median": vol_median,
        "body": body,
        # fuer den Haupt-Loop vorab aus dem DatetimeIndex extrahiert, um
        # teures Timestamp-Boxing (df.index[i].hour/.date()) pro Bar zu vermeiden
        "hours": df.index.hour.values,
        "dates": df.index.date,
    }


def _threshold_ok(value, ref, mult):
    """True wenn Filter deaktiviert (mult<=0) oder value >= mult*ref (ref muss dafuer gueltig sein)."""
    if mult <= 0:
        return True
    if ref is None or np.isnan(ref):
        return False
    return value >= mult * ref


def _find_choch(df_close, body, atr_m5, micro_by_type, sweep_pos, direction, choch_window,
                  displacement_atr_mult, n):
    """CHoCH = Bruch eines Mikro-Swings nach dem Sweep. Optional muss die
    bestaetigende Kerze eine Mindest-'Displacement'-Groesse (Body relativ zu
    ATR) aufweisen -> filtert schwache/zufaellige Structure-Breaks heraus.

    Performance: `pool` (High- oder Low-Mikro-Swings) ist nach pos/confirmed_pos
    sortiert -> die relevanten Kandidaten (pos > sweep_pos, confirmed_pos <= end)
    werden per bisect als zusammenhaengender Slice gefunden, statt bei jedem
    Sweep die komplette Mikro-Swing-Historie zu durchsuchen.
    """
    end = min(sweep_pos + choch_window, n - 1)
    best = None
    pool = micro_by_type["high"] if direction == "bullish" else micro_by_type["low"]
    lo = bisect.bisect_right(pool["pos"], sweep_pos)
    hi = bisect.bisect_right(pool["conf"], end)
    cands = pool["items"][lo:hi]
    for s in cands:
        start = s["confirmed_pos"] + 1
        if start > end:
            continue
        seg = df_close[start:end + 1]
        break_hit = (seg > s["price"]) if direction == "bullish" else (seg < s["price"])
        if displacement_atr_mult > 0:
            body_seg = body[start:end + 1]
            atr_seg = atr_m5[start:end + 1]
            with np.errstate(invalid="ignore"):
                disp_ok = body_seg >= displacement_atr_mult * atr_seg
            disp_ok = np.where(np.isnan(atr_seg), False, disp_ok)
            hit = np.where(break_hit & disp_ok)[0]
        else:
            hit = np.where(break_hit)[0]
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
    swings_by_type = pre["swings_by_type"]
    micro_by_type = pre["micro_by_type"]
    asia_levels = pre["asia_levels"]
    bias_map = pre["bias_map"]
    trend_strength_map = pre["trend_strength_map"]
    atr_m5 = pre["atr_m5"]
    vol_median = pre["vol_median"]
    body = pre["body"]

    killzones = KILLZONE_PRESETS[params["killzone_mode"]]
    eq_tol = params["eq_tol_pips"] * pip_size
    retest_tol = params["retest_tol_pips"] * pip_size
    eq_lookback = params.get("eq_lookback", 30)
    trend_strength_mult = params.get("trend_strength_atr_mult", 0.0)
    sweep_min_wick_mult = params.get("sweep_min_wick_atr_mult", 0.0)
    volume_mult = params.get("volume_mult", 0.0)
    displacement_mult = params.get("displacement_atr_mult", 0.0)

    volume = df["volume"].values
    low = df["low"].values
    high = df["high"].values
    close = df["close"].values
    hours = pre["hours"]
    dates = pre["dates"]
    idx = df.index  # nur fuer den (seltenen) Asia-ready_at-Vergleich unten benoetigt
    n = len(df)

    high_conf, high_items = swings_by_type["high"]["conf"], swings_by_type["high"]["items"]
    low_conf, low_items = swings_by_type["low"]["conf"], swings_by_type["low"]["items"]

    trades = []
    i = 0
    swept_today = set()
    current_day = None
    cache_key = (-1, -1)
    cache = None  # (last_high, last_low, eq_highs, eq_lows)

    while i < n:
        day = dates[i]
        if day != current_day:
            current_day = day
            swept_today = set()

        bias = bias_map.get(day, "neutral")
        hour = hours[i]
        in_kz = any(a <= hour < b for a, b in killzones)
        trend_ok = trend_strength_map.get(day, 0.0) >= trend_strength_mult

        if bias != "neutral" and in_kz and trend_ok:
            # Nur die letzten `eq_lookback` bestaetigten Swings je Typ werden
            # betrachtet (per bisect statt eines Scans ueber die komplette,
            # bei mehreren Handelsmonaten sehr langen Swing-Historie).
            n_high = bisect.bisect_right(high_conf, i)
            n_low = bisect.bisect_right(low_conf, i)
            key = (n_high, n_low)
            if key != cache_key:
                last_high = high_items[n_high - 1] if n_high > 0 else None
                last_low = low_items[n_low - 1] if n_low > 0 else None
                eq_highs = cluster_equal_levels(high_items[max(0, n_high - eq_lookback):n_high], eq_tol)
                eq_lows = cluster_equal_levels(low_items[max(0, n_low - eq_lookback):n_low], eq_tol)
                cache = (last_high, last_low, eq_highs, eq_lows)
                cache_key = key
            last_high, last_low, eq_highs, eq_lows = cache

            candidates = []
            a = asia_levels.get(day)
            if a is not None and idx[i] >= a["ready_at"]:
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

            atr_i = atr_m5[i]
            vol_ok = _threshold_ok(volume[i], vol_median[i], volume_mult)
            sweep = None
            if bias == "bullish":
                for price, typ, lid in candidates:
                    if typ != "low" or lid in swept_today:
                        continue
                    if low[i] < price and close[i] > price:
                        wick_extent = price - low[i]
                        if _threshold_ok(wick_extent, atr_i, sweep_min_wick_mult) and vol_ok:
                            sweep = (price, lid, "bullish", low[i])
                            break
                        swept_today.add(lid)  # Sweep zwar erkannt, Qualitaet zu schwach -> Level verbraucht
            else:
                for price, typ, lid in candidates:
                    if typ != "high" or lid in swept_today:
                        continue
                    if high[i] > price and close[i] < price:
                        wick_extent = high[i] - price
                        if _threshold_ok(wick_extent, atr_i, sweep_min_wick_mult) and vol_ok:
                            sweep = (price, lid, "bearish", high[i])
                            break
                        swept_today.add(lid)

            if sweep:
                level_price, lid, direction, wick_extreme = sweep
                swept_today.add(lid)
                choch = _find_choch(close, body, atr_m5, micro_by_type, i, direction,
                                      params["choch_window"], displacement_mult, n)
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
                            # Zusatzinfos rein fuer Nachvollziehbarkeit/Visualisierung eines
                            # einzelnen Trades -- werden von metrics.py ignoriert.
                            a = asia_levels.get(day)
                            trade["debug"] = {
                                "bias": bias, "sweep_pos": i, "sweep_time": idx[i],
                                "sweep_level": level_price, "sweep_level_id": lid,
                                "wick_extreme": wick_extreme, "choch_confirm_pos": confirm_pos,
                                "choch_confirm_time": idx[confirm_pos], "choch_level": choch_level,
                                "asia_high": a["high"] if a else None, "asia_low": a["low"] if a else None,
                            }
                            trades.append(trade)
                            i = trade["exit_pos"]
                            continue
        i += 1
    return trades
