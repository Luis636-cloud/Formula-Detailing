"""Definitive Zusammenfassung der Edge-Suche auf Gold & Nasdaq.

Die automatische Grid-Search/Koordinatenabstieg-Selektion (optimize_v3.py)
waehlt bei reiner 'hoechste Winrate zuerst'-Regel systematisch immer
staerkere Filter, weil Winrate mit Filterstaerke (fast) monoton steigt --
das Resultat sind am Ende Konfigurationen mit so wenigen Out-of-Sample-
Trades (n=7-11), dass keine seriöse Aussage mehr moeglich ist. Das ist ein
Artefakt der Auswahlregel, kein Beleg gegen den Effekt.

Dieses Skript validiert stattdessen EXPLIZIT die Konfiguration, die sich
aus einer Sensitivitaetsanalyse (glatter, monotoner Zusammenhang
Filterstaerke -> Trefferquote ueber ein ganzes Raster benachbarter Werte,
siehe REPORT.md Abschnitt 7) als bester Kompromiss aus Stichprobengroesse
und Effektstaerke ergeben hat, und zwar mit allen drei Validierungsschritten
nebeneinander: Train/Test-Split, 5 unabhaengige Zeitfenster, volle Historie.
"""
import json
import os

import numpy as np

from data_utils import load_5m, train_test_split_by_time
from instruments import INSTRUMENTS
from strategy import precompute, run_strategy
from metrics import compute_metrics

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

NASDAQ_PARAMS = {
    "swing_n": 3, "micro_n": 1, "eq_tol_pips": 3, "eq_lookback": 30,
    "retest_tol_pips": 2, "max_hold_bars": 48, "min_rr": 1.0,
    "asia_start": 0, "asia_end": 6,
    "killzone_mode": "london", "choch_window": 24, "retest_window": 24,
    "sl_buffer_pips": 2, "tp_mode": "fixed", "rr": 1.5,
    "trend_strength_atr_mult": 1.0, "sweep_min_wick_atr_mult": 0.25,
    "displacement_atr_mult": 1.0, "volume_mult": 0.0,
}

# Gold: bestes Kern-Setup aus optimize_v3 (killzone=ny, choch_window=12,
# retest_window=24, sl_buffer=2, RR=1.5) OHNE Filter -- als Referenz, um zu
# zeigen dass Gold hier weiterhin keinen Edge hat.
GOLD_CORE_PARAMS = {
    "swing_n": 3, "micro_n": 1, "eq_tol_pips": 3, "eq_lookback": 30,
    "retest_tol_pips": 2, "max_hold_bars": 48, "min_rr": 1.0,
    "asia_start": 0, "asia_end": 6,
    "killzone_mode": "ny", "choch_window": 12, "retest_window": 24,
    "sl_buffer_pips": 2, "tp_mode": "fixed", "rr": 1.5,
    "trend_strength_atr_mult": 0.0, "sweep_min_wick_atr_mult": 0.0,
    "displacement_atr_mult": 0.0, "volume_mult": 0.0,
}

# Gold "starke Filter"-Zone: in der Sensitivitaetsanalyse auf der vollen
# Historie profitabel (WR ~52-65%), aber die Out-of-Sample-Stichprobe ist
# mit n=7 Trades zu klein fuer eine belastbare Aussage -- explizit als
# UNBESTAETIGT gekennzeichnet, nicht als Edge behandelt.
GOLD_STRICT_FILTER_PARAMS = dict(GOLD_CORE_PARAMS)
GOLD_STRICT_FILTER_PARAMS.update(
    trend_strength_atr_mult=1.2, sweep_min_wick_atr_mult=0.1, displacement_atr_mult=1.0)


def eval_full(name, params):
    df = load_5m(os.path.join(DATA_DIR, f"{name}_5m.csv"))
    spec = INSTRUMENTS[name]
    pre = precompute(df, params["swing_n"], params["micro_n"], params["asia_start"], params["asia_end"])
    trades = run_strategy(df, pre, params, spec["pip"], spec["spread"])
    return df, pre, trades, compute_metrics(trades)


def eval_train_test(name, params, train_frac=0.7):
    df = load_5m(os.path.join(DATA_DIR, f"{name}_5m.csv"))
    train, test = train_test_split_by_time(df, train_frac)
    spec = INSTRUMENTS[name]
    pre_tr = precompute(train, params["swing_n"], params["micro_n"], params["asia_start"], params["asia_end"])
    pre_te = precompute(test, params["swing_n"], params["micro_n"], params["asia_start"], params["asia_end"])
    tr_trades = run_strategy(train, pre_tr, params, spec["pip"], spec["spread"])
    te_trades = run_strategy(test, pre_te, params, spec["pip"], spec["spread"])
    return compute_metrics(tr_trades), compute_metrics(te_trades)


def eval_chunks(name, params, n_chunks=5):
    df = load_5m(os.path.join(DATA_DIR, f"{name}_5m.csv"))
    spec = INSTRUMENTS[name]
    n = len(df)
    edges = np.linspace(0, n, n_chunks + 1).astype(int)
    out = []
    for i in range(n_chunks):
        chunk = df.iloc[edges[i]:edges[i + 1]]
        pre = precompute(chunk, params["swing_n"], params["micro_n"], params["asia_start"], params["asia_end"])
        trades = run_strategy(chunk, pre, params, spec["pip"], spec["spread"])
        m = compute_metrics(trades)
        out.append({
            "chunk": i + 1, "start": str(chunk.index.min().date()), "end": str(chunk.index.max().date()),
            "n_trades": m["n_trades"], "win_rate": m["win_rate"], "profit_factor": m["profit_factor"],
            "expectancy_R": m["expectancy_R"], "total_R": m["total_R"],
        })
    return out


def strip_curve(m):
    return {k: v for k, v in m.items() if k != "curve"}


def main():
    result = {}

    print("=" * 70)
    print("NASDAQ -- empfohlene Konfiguration (Kern + Qualitaetsfilter)")
    print("=" * 70)
    df, pre, trades, m_full = eval_full("NASDAQ", NASDAQ_PARAMS)
    m_train, m_test = eval_train_test("NASDAQ", NASDAQ_PARAMS)
    chunks = eval_chunks("NASDAQ", NASDAQ_PARAMS)
    print(f"Volle Historie (20 Monate): n={m_full['n_trades']} WR={m_full['win_rate']*100:.1f}% "
          f"PF={m_full['profit_factor']:.2f} Exp={m_full['expectancy_R']:+.3f}R "
          f"MaxDD={m_full['max_drawdown_R']:.2f}R Total={m_full['total_R']:+.2f}R")
    print(f"Train (70%): n={m_train['n_trades']} WR={m_train['win_rate']*100:.1f}% PF={m_train['profit_factor']:.2f}")
    print(f"Test  (30%, OOS): n={m_test['n_trades']} WR={m_test['win_rate']*100:.1f}% "
          f"PF={m_test['profit_factor']:.2f} Exp={m_test['expectancy_R']:+.3f}R")
    print("5 unabhaengige Zeitfenster:")
    all_positive = True
    for c in chunks:
        ok = c["profit_factor"] > 1.0
        all_positive &= ok
        print(f"  {c['start']}..{c['end']}: n={c['n_trades']:3d} WR={c['win_rate']*100:5.1f}% "
              f"PF={c['profit_factor']:.2f} Exp={c['expectancy_R']:+.3f}R  {'OK' if ok else 'NEGATIV'}")
    print(f"-> in allen 5 Fenstern profitabel: {all_positive}")

    result["nasdaq_recommended"] = {
        "params": NASDAQ_PARAMS,
        "full_history": strip_curve(m_full),
        "train": strip_curve(m_train),
        "test_oos": strip_curve(m_test),
        "chunks": chunks,
        "all_chunks_profitable": all_positive,
    }

    print("\n" + "=" * 70)
    print("XAUUSD -- Kern-Parameter ohne Filter (Referenz: kein Edge)")
    print("=" * 70)
    _, _, _, m_full_g = eval_full("XAUUSD", GOLD_CORE_PARAMS)
    m_train_g, m_test_g = eval_train_test("XAUUSD", GOLD_CORE_PARAMS)
    print(f"Volle Historie: n={m_full_g['n_trades']} WR={m_full_g['win_rate']*100:.1f}% "
          f"PF={m_full_g['profit_factor']:.2f} Exp={m_full_g['expectancy_R']:+.3f}R Total={m_full_g['total_R']:+.2f}R")
    print(f"Test (OOS): n={m_test_g['n_trades']} WR={m_test_g['win_rate']*100:.1f}% "
          f"PF={m_test_g['profit_factor']:.2f} Exp={m_test_g['expectancy_R']:+.3f}R")

    result["gold_core_no_edge"] = {
        "params": GOLD_CORE_PARAMS, "full_history": strip_curve(m_full_g),
        "train": strip_curve(m_train_g), "test_oos": strip_curve(m_test_g),
    }

    print("\n" + "=" * 70)
    print("XAUUSD -- starke Filter-Zone (UNBESTAETIGT: OOS-Stichprobe zu klein)")
    print("=" * 70)
    _, _, _, m_full_gs = eval_full("XAUUSD", GOLD_STRICT_FILTER_PARAMS)
    m_train_gs, m_test_gs = eval_train_test("XAUUSD", GOLD_STRICT_FILTER_PARAMS)
    chunks_gs = eval_chunks("XAUUSD", GOLD_STRICT_FILTER_PARAMS)
    print(f"Volle Historie: n={m_full_gs['n_trades']} WR={m_full_gs['win_rate']*100:.1f}% "
          f"PF={m_full_gs['profit_factor']:.2f} Exp={m_full_gs['expectancy_R']:+.3f}R")
    print(f"Test (OOS): n={m_test_gs['n_trades']} WR={m_test_gs['win_rate']*100:.1f}% "
          f"PF={m_test_gs['profit_factor']:.2f}  <- zu wenige Trades fuer eine Aussage")
    print("5 unabhaengige Zeitfenster:")
    for c in chunks_gs:
        print(f"  {c['start']}..{c['end']}: n={c['n_trades']:3d} WR={c['win_rate']*100:5.1f}% "
              f"PF={c['profit_factor']:.2f} Exp={c['expectancy_R']:+.3f}R")

    result["gold_strict_filter_unconfirmed"] = {
        "params": GOLD_STRICT_FILTER_PARAMS, "full_history": strip_curve(m_full_gs),
        "train": strip_curve(m_train_gs), "test_oos": strip_curve(m_test_gs), "chunks": chunks_gs,
    }

    with open(os.path.join(os.path.dirname(__file__), "final_recommendation.json"), "w") as f:
        json.dump(result, f, indent=2, default=str)
    print("\nGespeichert in final_recommendation.json")


if __name__ == "__main__":
    main()
