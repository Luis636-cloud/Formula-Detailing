"""Walk-Forward-Analyse statt eines einzelnen Train/Test-Splits.

Ein einzelner 70/30-Split kann Zufallsglueck/-pech einer Periode als
'Ergebnis' ausgeben. Deshalb: Zeitachse in 4 gleich lange Folds teilen und
mehrfach rollierend optimieren/validieren:

  Runde 1: Train=Fold1        -> Test=Fold2
  Runde 2: Train=Fold1+2      -> Test=Fold3
  Runde 3: Train=Fold1+2+3    -> Test=Fold4

Alle Out-of-Sample-Trades (aus den jeweiligen Test-Folds, nie Teil des
zugehoerigen Trainings) werden gepoolt -> das ist die realistischste
verfuegbare Schaetzung der Live-Performance mit den vorhandenen ~72 Tagen
Historie.
"""
import json
import os
import numpy as np

from data_utils import load_5m
from instruments import INSTRUMENTS
from strategy import precompute, run_strategy
from metrics import compute_metrics
from optimize import FIXED_PARAMS, build_param_grid

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
N_FOLDS = 4


def make_folds(df, n_folds=N_FOLDS):
    n = len(df)
    edges = np.linspace(0, n, n_folds + 1).astype(int)
    return [df.iloc[edges[i]:edges[i + 1]] for i in range(n_folds)]


def load_all_folds():
    per_instr = {}
    for name in INSTRUMENTS:
        df = load_5m(os.path.join(DATA_DIR, f"{name}_5m.csv"))
        per_instr[name] = make_folds(df)
    return per_instr


def precompute_folds(folds_by_instr, fold_indices):
    """Precompute je Instrument auf der Konkatenation der gegebenen Folds."""
    import pandas as pd
    pre = {}
    dfs = {}
    p = FIXED_PARAMS
    for name, folds in folds_by_instr.items():
        df = pd.concat([folds[i] for i in fold_indices])
        dfs[name] = df
        pre[name] = precompute(df, p["swing_n"], p["micro_n"], p["asia_start"], p["asia_end"])
    return dfs, pre


def run_config(dfs, pre, params, min_trades=None):
    all_trades = []
    for name, df in dfs.items():
        spec = INSTRUMENTS[name]
        trades = run_strategy(df, pre[name], params, spec["pip"], spec["spread"])
        for t in trades:
            t["instrument"] = name
        all_trades.extend(trades)
    return all_trades


def select_best(grid, dfs, pre, min_trades=12):
    results = []
    for params in grid:
        trades = run_config(dfs, pre, params)
        m = compute_metrics(trades)
        results.append((params, m))
    valid = [(p, m) for p, m in results if m["n_trades"] >= min_trades and m["profit_factor"] >= 1.0]
    pool = valid if valid else results
    pool.sort(key=lambda pm: (pm[1]["win_rate"], pm[1]["profit_factor"], pm[1]["expectancy_R"]), reverse=True)
    return pool[0], pool[:5]


def main():
    print("Lade Daten und teile in 4 chronologische Folds je Instrument ...")
    folds_by_instr = load_all_folds()
    grid = build_param_grid()
    print(f"Grid-Groesse: {len(grid)} Kombinationen\n")

    oos_trades_all = []
    round_summaries = []

    for r in range(1, N_FOLDS):
        train_idx = list(range(0, r))
        test_idx = [r]
        print(f"=== Runde {r}: Train=Fold{train_idx} Test=Fold{test_idx} ===")

        train_dfs, train_pre = precompute_folds(folds_by_instr, train_idx)
        for name, df in train_dfs.items():
            print(f"  Train {name}: {len(df)} bars ({df.index.min()} .. {df.index.max()})")

        (best_params, best_train_metrics), top5 = select_best(grid, train_dfs, train_pre)
        print(f"  Beste Train-Konfig: WR={best_train_metrics['win_rate']*100:.1f}% "
              f"PF={best_train_metrics['profit_factor']:.2f} n={best_train_metrics['n_trades']}")

        test_dfs, test_pre = precompute_folds(folds_by_instr, test_idx)
        for name, df in test_dfs.items():
            print(f"  Test  {name}: {len(df)} bars ({df.index.min()} .. {df.index.max()})")

        test_trades = run_config(test_dfs, test_pre, best_params)
        test_metrics = compute_metrics(test_trades)
        print(f"  OOS Test-Fold: n={test_metrics['n_trades']} WR={test_metrics['win_rate']*100:.1f}% "
              f"PF={test_metrics['profit_factor']:.2f} Exp={test_metrics['expectancy_R']:+.3f}R "
              f"TotalR={test_metrics['total_R']:+.2f}\n")

        for t in test_trades:
            t["wf_round"] = r
        oos_trades_all.extend(test_trades)
        round_summaries.append({
            "round": r, "best_params": best_params,
            "train_metrics": {k: v for k, v in best_train_metrics.items() if k != "curve"},
            "test_metrics": {k: v for k, v in test_metrics.items() if k != "curve"},
        })

    print("=" * 70)
    overall = compute_metrics(oos_trades_all)
    print("GEPOOLTES OUT-OF-SAMPLE-ERGEBNIS (alle Test-Folds, Runden 1-3):")
    print(f"  n_trades={overall['n_trades']}")
    print(f"  Winrate={overall['win_rate']*100:.1f}%")
    print(f"  Profit-Factor={overall['profit_factor']:.2f}")
    print(f"  Expectancy={overall['expectancy_R']:+.3f} R/Trade")
    print(f"  Max Drawdown={overall['max_drawdown_R']:.2f} R")
    print(f"  Total={overall['total_R']:+.2f} R")

    with open(os.path.join(os.path.dirname(__file__), "walk_forward_results.json"), "w") as f:
        json.dump({
            "rounds": round_summaries,
            "overall_oos_metrics": {k: v for k, v in overall.items() if k != "curve"},
            "oos_trades": [
                {**{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in t.items()}}
                for t in oos_trades_all
            ],
        }, f, indent=2, default=str)
    print("\nDetails gespeichert in walk_forward_results.json")
    return oos_trades_all, overall, round_summaries


if __name__ == "__main__":
    main()
