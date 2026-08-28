"""Grid-Search zur Parameteroptimierung mit Train/Test-Split (kein
Look-Ahead, keine In-Sample-Ergebnisse als 'Wahrheit' verkauft).

Nur die Parameter mit dem groessten erwarteten Einfluss auf Winrate/PF
werden durchsucht; strukturelle Parameter (Fraktal-Groessen, Toleranzen)
sind fest auf ICT-uebliche, robuste Werte gesetzt, um Overfitting auf die
knapp 60 Tage Historie zu begrenzen.
"""
import itertools
import json
import os

from data_utils import load_5m, train_test_split_by_time
from instruments import INSTRUMENTS
from strategy import precompute, run_strategy
from metrics import compute_metrics

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

FIXED_PARAMS = {
    "swing_n": 3,
    "micro_n": 1,
    "eq_tol_pips": 3,
    "eq_lookback": 30,
    "retest_tol_pips": 2,
    "max_hold_bars": 48,   # 48 * 5min = 4h Zeit-Stop
    "min_rr": 1.0,
    "asia_start": 0,
    "asia_end": 6,
}

GRID = {
    "killzone_mode": ["london", "ny", "both"],
    "choch_window": [12, 24],
    "retest_window": [12, 24],
    "sl_buffer_pips": [2, 5],
    "tp_rr": [("fixed", 1.5), ("fixed", 2.0), ("next_level", 1.5)],
}


def load_all(train_frac=0.7):
    data = {}
    for name in INSTRUMENTS:
        df = load_5m(os.path.join(DATA_DIR, f"{name}_5m.csv"))
        train, test = train_test_split_by_time(df, train_frac)
        data[name] = {"full": df, "train": train, "test": test}
    return data


def precompute_all(data, split):
    pre = {}
    for name, d in data.items():
        df = d[split]
        p = FIXED_PARAMS
        pre[name] = precompute(df, p["swing_n"], p["micro_n"], p["asia_start"], p["asia_end"])
    return pre


def build_param_grid():
    keys = list(GRID.keys())
    combos = []
    for values in itertools.product(*[GRID[k] for k in keys]):
        params = dict(FIXED_PARAMS)
        d = dict(zip(keys, values))
        tp_mode, rr = d.pop("tp_rr")
        d["tp_mode"] = tp_mode
        d["rr"] = rr
        params.update(d)
        combos.append(params)
    return combos


def run_config_all_instruments(data, pre, params, split):
    all_trades = []
    per_instrument = {}
    for name, d in data.items():
        df = d[split]
        spec = INSTRUMENTS[name]
        trades = run_strategy(df, pre[name], params, spec["pip"], spec["spread"])
        for t in trades:
            t["instrument"] = name
        all_trades.extend(trades)
        per_instrument[name] = trades
    return all_trades, per_instrument


def optimize(min_trades=20):
    print("Lade Daten & splitte 70% Train / 30% Test (zeitlich, kein Leakage) ...")
    data = load_all(0.7)
    for name, d in data.items():
        print(f"  {name}: train={len(d['train'])} bars, test={len(d['test'])} bars")

    print("Precompute (Swings/Bias/Asia-Levels) auf Trainings-Split ...")
    pre_train = precompute_all(data, "train")

    grid = build_param_grid()
    print(f"Grid-Search ueber {len(grid)} Parameter-Kombinationen (aggregiert ueber 4 Instrumente) ...")

    results = []
    for params in grid:
        trades, _ = run_config_all_instruments(data, pre_train, params, "train")
        m = compute_metrics(trades)
        results.append((params, m))

    # Auswahlregel: Ziel ist maximale Winrate, aber nur unter Konfigurationen
    # mit genuegend Trades (Signifikanz) und Profit-Factor >= 1.0 (nicht nur
    # hohe Trefferquote bei negativem Erwartungswert).
    valid = [(p, m) for p, m in results if m["n_trades"] >= min_trades and m["profit_factor"] >= 1.0]
    pool = valid if valid else results
    pool.sort(key=lambda pm: (pm[1]["win_rate"], pm[1]["profit_factor"], pm[1]["expectancy_R"]), reverse=True)

    print("\nTop 5 Konfigurationen (Train-Split):")
    for p, m in pool[:5]:
        print(f"  WR={m['win_rate']*100:5.1f}% PF={m['profit_factor']:.2f} "
              f"Exp={m['expectancy_R']:+.3f}R n={m['n_trades']:3d}  {p}")

    best_params, best_train_metrics = pool[0]

    print("\nPrecompute auf Test-Split (Out-of-Sample) ...")
    pre_test = precompute_all(data, "test")
    test_trades, test_per_instr = run_config_all_instruments(data, pre_test, best_params, "test")
    test_metrics = compute_metrics(test_trades)

    print("\nOut-of-Sample Ergebnis (Test-Split, unangetastete letzte 30% der Daten):")
    print(f"  n={test_metrics['n_trades']} WR={test_metrics['win_rate']*100:.1f}% "
          f"PF={test_metrics['profit_factor']:.2f} Exp={test_metrics['expectancy_R']:+.3f}R "
          f"MaxDD={test_metrics['max_drawdown_R']:.2f}R TotalR={test_metrics['total_R']:+.2f}")

    return {
        "best_params": best_params,
        "train_metrics": best_train_metrics,
        "test_metrics": test_metrics,
        "test_trades": test_trades,
        "test_per_instrument": test_per_instr,
        "all_results": results,
        "data": data,
    }


if __name__ == "__main__":
    out = optimize()
    with open(os.path.join(os.path.dirname(__file__), "best_params.json"), "w") as f:
        json.dump(out["best_params"], f, indent=2)
