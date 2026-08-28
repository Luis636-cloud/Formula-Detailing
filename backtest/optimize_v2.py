"""Zweite Optimierungsrunde: sucht gezielt nach einem Edge, indem
zusaetzlich zu den bisherigen Kern-Parametern drei Qualitaetsfilter
zugelassen werden (jeweils per ATR/Volumen normiert, damit sie fuer Gold
und Nasdaq gleichermassen sinnvoll sind):

  - trend_strength_atr_mult: HTF-Bias muss mindestens X*ATR(H4) von der
    EMA(20) entfernt sein -> filtert Range-/Choppy-Tage ohne klaren Trend.
  - sweep_min_wick_atr_mult: der Liquidations-Wick beim Sweep muss
    mindestens X*ATR(M5) ueber/unter das Level hinausreichen -> filtert
    zu schwache/knapp daneben liegende 'Sweeps'.
  - displacement_atr_mult: die CHoCH-bestaetigende Kerze muss einen Body
    von mindestens X*ATR(M5) haben -> verlangt 'Displacement' statt eines
    zufaelligen 1-Tick-Structure-Breaks.
  - volume_mult: das Sweep-Bar-Volumen muss mindestens X * Median(20)
    betragen -> Bestaetigung durch tatsaechliche Handelsaktivitaet.

Optimiert wird PRO INSTRUMENT separat (Gold und Nasdaq haben sehr
unterschiedlichen Charakter) und PRO WALK-FORWARD-RUNDE, per
Koordinatenabstieg: zuerst die Kern-Parameter (wie in optimize.py), dann
bei fixierten Kern-Parametern die Filter -- das haelt die Zahl der
getesteten Kombinationen handhabbar (Overfitting-Risiko bleibt begrenzt).
"""
import itertools
import json
import os

import numpy as np

from data_utils import load_5m
from instruments import INSTRUMENTS
from strategy import precompute, run_strategy
from metrics import compute_metrics
from optimize import FIXED_PARAMS, GRID as CORE_GRID
from walk_forward import make_folds, N_FOLDS

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

FILTER_GRID = {
    "trend_strength_atr_mult": [0.0, 0.3, 0.6, 1.0],
    "sweep_min_wick_atr_mult": [0.0, 0.1, 0.25, 0.5],
    "displacement_atr_mult": [0.0, 0.3, 0.6, 1.0],
    "volume_mult": [0.0, 0.8, 1.2],
}

DEFAULT_FILTERS = {k: 0.0 for k in FILTER_GRID}


def build_core_grid():
    keys = list(CORE_GRID.keys())
    combos = []
    for values in itertools.product(*[CORE_GRID[k] for k in keys]):
        params = dict(FIXED_PARAMS)
        d = dict(zip(keys, values))
        tp_mode, rr = d.pop("tp_rr")
        d["tp_mode"] = tp_mode
        d["rr"] = rr
        params.update(d)
        params.update(DEFAULT_FILTERS)
        combos.append(params)
    return combos


def build_filter_grid(base_params):
    keys = list(FILTER_GRID.keys())
    combos = []
    for values in itertools.product(*[FILTER_GRID[k] for k in keys]):
        params = dict(base_params)
        params.update(dict(zip(keys, values)))
        combos.append(params)
    return combos


def evaluate(df, pre, params, pip, spread):
    trades = run_strategy(df, pre, params, pip, spread)
    return trades, compute_metrics(trades)


def select_best(candidates_with_metrics, min_trades):
    valid = [(p, m) for p, m in candidates_with_metrics
             if m["n_trades"] >= min_trades and m["profit_factor"] >= 1.0]
    pool = valid if valid else candidates_with_metrics
    pool.sort(key=lambda pm: (pm[1]["win_rate"], pm[1]["profit_factor"], pm[1]["expectancy_R"]),
              reverse=True)
    return pool[0]


def coordinate_descent(df, pre, pip, spread, min_trades):
    core_grid = build_core_grid()
    core_results = [(p, evaluate(df, pre, p, pip, spread)[1]) for p in core_grid]
    best_core_params, best_core_metrics = select_best(core_results, min_trades)

    filter_grid = build_filter_grid(best_core_params)
    filter_results = [(p, evaluate(df, pre, p, pip, spread)[1]) for p in filter_grid]
    best_params, best_metrics = select_best(filter_results, min_trades)

    return best_params, best_metrics, {
        "best_core_only": {"params": best_core_params,
                            "metrics": {k: v for k, v in best_core_metrics.items() if k != "curve"}},
    }


def walk_forward_per_instrument(name, min_trades=8):
    df = load_5m(os.path.join(DATA_DIR, f"{name}_5m.csv"))
    folds = make_folds(df, N_FOLDS)
    spec = INSTRUMENTS[name]
    rounds = []
    oos_trades = []

    for r in range(1, N_FOLDS):
        train_idx = list(range(0, r))
        test_idx = r
        train_df = __import__("pandas").concat([folds[i] for i in train_idx])
        test_df = folds[test_idx]

        p = FIXED_PARAMS
        train_pre = precompute(train_df, p["swing_n"], p["micro_n"], p["asia_start"], p["asia_end"])
        best_params, best_train_metrics, extra = coordinate_descent(
            train_df, train_pre, spec["pip"], spec["spread"], min_trades)

        test_pre = precompute(test_df, p["swing_n"], p["micro_n"], p["asia_start"], p["asia_end"])
        test_trades = run_strategy(test_df, test_pre, best_params, spec["pip"], spec["spread"])
        test_metrics = compute_metrics(test_trades)

        for t in test_trades:
            t["wf_round"] = r
            t["instrument"] = name
        oos_trades.extend(test_trades)

        print(f"[{name}] Runde {r}: Train n={best_train_metrics['n_trades']} "
              f"WR={best_train_metrics['win_rate']*100:.1f}% PF={best_train_metrics['profit_factor']:.2f}"
              f"  ->  Test n={test_metrics['n_trades']} WR={test_metrics['win_rate']*100:.1f}% "
              f"PF={test_metrics['profit_factor']:.2f} Exp={test_metrics['expectancy_R']:+.3f}R")
        print(f"        gewaehlte Filter: trend={best_params['trend_strength_atr_mult']} "
              f"wick={best_params['sweep_min_wick_atr_mult']} "
              f"displacement={best_params['displacement_atr_mult']} "
              f"volume={best_params['volume_mult']}")

        rounds.append({
            "round": r,
            "best_params": best_params,
            "train_metrics": {k: v for k, v in best_train_metrics.items() if k != "curve"},
            "test_metrics": {k: v for k, v in test_metrics.items() if k != "curve"},
            "core_only_comparison": extra["best_core_only"],
        })

    overall = compute_metrics(oos_trades)
    print(f"[{name}] GEPOOLTES OOS: n={overall['n_trades']} WR={overall['win_rate']*100:.1f}% "
          f"PF={overall['profit_factor']:.2f} Exp={overall['expectancy_R']:+.3f}R "
          f"MaxDD={overall['max_drawdown_R']:.2f}R Total={overall['total_R']:+.2f}R\n")

    return {
        "instrument": name,
        "rounds": rounds,
        "overall_oos_metrics": {k: v for k, v in overall.items() if k != "curve"},
        "oos_trades": oos_trades,
    }


def main():
    results = {}
    for name in INSTRUMENTS:
        print(f"\n{'='*70}\nWalk-Forward + Filter-Optimierung: {name}\n{'='*70}")
        results[name] = walk_forward_per_instrument(name)

    all_oos = []
    for name, res in results.items():
        all_oos.extend(res["oos_trades"])
    overall = compute_metrics(all_oos)
    print("=" * 70)
    print("GESAMT (Gold + Nasdaq gepoolt, jeweils separat optimiert):")
    print(f"  n={overall['n_trades']} WR={overall['win_rate']*100:.1f}% "
          f"PF={overall['profit_factor']:.2f} Exp={overall['expectancy_R']:+.3f}R "
          f"MaxDD={overall['max_drawdown_R']:.2f}R Total={overall['total_R']:+.2f}R")

    out = {
        "per_instrument": {
            name: {
                "rounds": res["rounds"],
                "overall_oos_metrics": res["overall_oos_metrics"],
            } for name, res in results.items()
        },
        "combined_overall_oos_metrics": {k: v for k, v in overall.items() if k != "curve"},
        "combined_oos_trades": all_oos,
    }
    with open(os.path.join(os.path.dirname(__file__), "optimize_v2_results.json"), "w") as f:
        json.dump(out, f, indent=2, default=str)
    print("\nDetails gespeichert in optimize_v2_results.json")


if __name__ == "__main__":
    main()
