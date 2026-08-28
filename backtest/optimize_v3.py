"""Dritter Optimierungs-Anlauf: der 4-Fold-Walk-Forward aus optimize_v2.py
hat sich als zu granular erwiesen -- pro Runde blieben nach Filterung nur
noch 3-14 Trades zur Auswahl bzw. Validierung uebrig, das ist statistisches
Rauschen, kein belastbares Ergebnis (siehe optimize_v2_results.json).

Dieser Lauf verwendet stattdessen EINEN einzigen 70/30 Zeit-Split pro
Instrument (mehr Daten je Seite: ~50 Handelstage Training, ~22 Tage Test)
und erzwingt eine Mindest-Trade-Zahl bei der Parameterauswahl, damit nicht
eine zufaellig gute Handvoll Trades als 'bester Filter' gewaehlt wird.
"""
import json
import os

from data_utils import load_5m, train_test_split_by_time
from instruments import INSTRUMENTS
from strategy import precompute, run_strategy
from metrics import compute_metrics
from optimize import FIXED_PARAMS
from optimize_v2 import build_core_grid, build_filter_grid, evaluate, select_best

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
MIN_TRADES_TRAIN = 20


def run_instrument(name, train_frac=0.7):
    df = load_5m(os.path.join(DATA_DIR, f"{name}_5m.csv"))
    train, test = train_test_split_by_time(df, train_frac)
    spec = INSTRUMENTS[name]
    p = FIXED_PARAMS

    train_pre = precompute(train, p["swing_n"], p["micro_n"], p["asia_start"], p["asia_end"])
    test_pre = precompute(test, p["swing_n"], p["micro_n"], p["asia_start"], p["asia_end"])

    # Pass 1: Kern-Parameter (Filter aus)
    core_grid = build_core_grid()
    core_results = [(pp, evaluate(train, train_pre, pp, spec["pip"], spec["spread"])[1])
                     for pp in core_grid]
    best_core_params, best_core_metrics = select_best(core_results, MIN_TRADES_TRAIN)

    # Pass 2: Filter bei fixierten Kern-Parametern
    filter_grid = build_filter_grid(best_core_params)
    filter_results = [(pp, evaluate(train, train_pre, pp, spec["pip"], spec["spread"])[1])
                        for pp in filter_grid]
    best_params, best_train_metrics = select_best(filter_results, MIN_TRADES_TRAIN)

    # Referenz: bester Kern-Fund OHNE Filter, zum Vergleich auf Test
    core_only_trades = run_strategy(test, test_pre, best_core_params, spec["pip"], spec["spread"])
    core_only_test_metrics = compute_metrics(core_only_trades)

    test_trades, test_metrics = evaluate(test, test_pre, best_params, spec["pip"], spec["spread"])
    for t in test_trades:
        t["instrument"] = name

    print(f"\n=== {name} ===")
    print(f"Train (n={len(train)} bars): bester Kern-Fund       "
          f"n={best_core_metrics['n_trades']:3d} WR={best_core_metrics['win_rate']*100:5.1f}% "
          f"PF={best_core_metrics['profit_factor']:.2f}")
    print(f"Train (n={len(train)} bars): bester Kern+Filter-Fund "
          f"n={best_train_metrics['n_trades']:3d} WR={best_train_metrics['win_rate']*100:5.1f}% "
          f"PF={best_train_metrics['profit_factor']:.2f}")
    print(f"  gewaehlte Filter: trend={best_params['trend_strength_atr_mult']} "
          f"wick={best_params['sweep_min_wick_atr_mult']} "
          f"displacement={best_params['displacement_atr_mult']} "
          f"volume={best_params['volume_mult']}")
    print(f"Test  (n={len(test)} bars, OOS) Kern ohne Filter:     "
          f"n={core_only_test_metrics['n_trades']:3d} WR={core_only_test_metrics['win_rate']*100:5.1f}% "
          f"PF={core_only_test_metrics['profit_factor']:.2f} Exp={core_only_test_metrics['expectancy_R']:+.3f}R")
    print(f"Test  (n={len(test)} bars, OOS) Kern+Filter:          "
          f"n={test_metrics['n_trades']:3d} WR={test_metrics['win_rate']*100:5.1f}% "
          f"PF={test_metrics['profit_factor']:.2f} Exp={test_metrics['expectancy_R']:+.3f}R "
          f"Total={test_metrics['total_R']:+.2f}R")

    return {
        "instrument": name,
        "best_core_params": best_core_params,
        "best_core_train_metrics": {k: v for k, v in best_core_metrics.items() if k != "curve"},
        "best_params": best_params,
        "best_train_metrics": {k: v for k, v in best_train_metrics.items() if k != "curve"},
        "core_only_test_metrics": {k: v for k, v in core_only_test_metrics.items() if k != "curve"},
        "test_metrics": {k: v for k, v in test_metrics.items() if k != "curve"},
        "test_trades": test_trades,
    }


def main():
    results = {}
    for name in INSTRUMENTS:
        results[name] = run_instrument(name)

    all_test_trades = []
    for name, res in results.items():
        all_test_trades.extend(res["test_trades"])
    overall = compute_metrics(all_test_trades)
    print(f"\n{'='*70}\nGESAMT OOS (Gold + Nasdaq, je separat optimiert, 70/30-Split):")
    print(f"  n={overall['n_trades']} WR={overall['win_rate']*100:.1f}% "
          f"PF={overall['profit_factor']:.2f} Exp={overall['expectancy_R']:+.3f}R "
          f"MaxDD={overall['max_drawdown_R']:.2f}R Total={overall['total_R']:+.2f}R")

    out = {
        "per_instrument": {n: {k: v for k, v in r.items() if k != "test_trades"}
                             for n, r in results.items()},
        "combined_test_metrics": {k: v for k, v in overall.items() if k != "curve"},
        "combined_test_trades": all_test_trades,
    }
    with open(os.path.join(os.path.dirname(__file__), "optimize_v3_results.json"), "w") as f:
        json.dump(out, f, indent=2, default=str)
    print("\nDetails gespeichert in optimize_v3_results.json")


if __name__ == "__main__":
    main()
