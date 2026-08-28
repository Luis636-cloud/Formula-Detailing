"""Zusaetzlicher Kontroll-Lauf: EINE fest vorgegebene, nicht optimierte
Parametrisierung ('nach Lehrbuch', beide Killzones, TP fix 1:1.5) ueber
den gesamten verfuegbaren Zeitraum je Instrument. Dient als Gegenprobe zur
Grid-Search/Walk-Forward-Optimierung: zeigt, wie die Strategie abschneidet,
wenn man sie einfach 'wie beschrieben' umsetzt, ohne auf die Daten hin zu
optimieren.
"""
import json
import os

from data_utils import load_5m
from instruments import INSTRUMENTS
from strategy import precompute, run_strategy
from metrics import compute_metrics
from optimize import FIXED_PARAMS

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

BASELINE_PARAMS = dict(FIXED_PARAMS)
BASELINE_PARAMS.update({
    "killzone_mode": "both",
    "choch_window": 24,
    "retest_window": 24,
    "sl_buffer_pips": 3,
    "tp_mode": "fixed",
    "rr": 1.5,
})


def main():
    per_instrument = {}
    all_trades = []
    for name in INSTRUMENTS:
        df = load_5m(os.path.join(DATA_DIR, f"{name}_5m.csv"))
        pre = precompute(df, BASELINE_PARAMS["swing_n"], BASELINE_PARAMS["micro_n"],
                          BASELINE_PARAMS["asia_start"], BASELINE_PARAMS["asia_end"])
        spec = INSTRUMENTS[name]
        trades = run_strategy(df, pre, BASELINE_PARAMS, spec["pip"], spec["spread"])
        for t in trades:
            t["instrument"] = name
        m = compute_metrics(trades)
        per_instrument[name] = {k: v for k, v in m.items() if k != "curve"}
        print(f"{name}: n={m['n_trades']} WR={m['win_rate']*100:.1f}% PF={m['profit_factor']:.2f} "
              f"Exp={m['expectancy_R']:+.3f}R TotalR={m['total_R']:+.2f}")
        all_trades.extend(trades)

    overall = compute_metrics(all_trades)
    print(f"\nCOMBINED: n={overall['n_trades']} WR={overall['win_rate']*100:.1f}% "
          f"PF={overall['profit_factor']:.2f} Exp={overall['expectancy_R']:+.3f}R "
          f"MaxDD={overall['max_drawdown_R']:.2f}R TotalR={overall['total_R']:+.2f}")

    out = {
        "params": BASELINE_PARAMS,
        "per_instrument": per_instrument,
        "combined": {k: v for k, v in overall.items() if k != "curve"},
        "combined_curve": overall["curve"],
    }
    with open(os.path.join(os.path.dirname(__file__), "baseline_results.json"), "w") as f:
        json.dump(out, f, indent=2, default=str)
    return out


if __name__ == "__main__":
    main()
