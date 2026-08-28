"""Equity-Kurven fuer den v3-Lauf (70/30-Split je Instrument, mit/ohne
Qualitaetsfilter) -- Ergaenzung zu make_charts.py."""
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = os.path.dirname(__file__)


def curve_from_trades(trades):
    eq = 0.0
    xs, ys = [0], [0.0]
    for i, t in enumerate(sorted(trades, key=lambda x: x["entry_time"]), start=1):
        eq += t["r_multiple"]
        xs.append(i)
        ys.append(eq)
    return xs, ys


def main():
    v3 = json.load(open(os.path.join(BASE, "optimize_v3_results.json")))

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    colors = {"XAUUSD": "#d97706", "NASDAQ": "#2563eb"}
    for ax, name in zip(axes, ["XAUUSD", "NASDAQ"]):
        trades = [t for t in v3["combined_test_trades"] if t["instrument"] == name]
        xs, ys = curve_from_trades(trades)
        ax.plot(xs, ys, color=colors[name], linewidth=2)
        ax.axhline(0, color="#999", linewidth=1, linestyle="--")
        ax.set_title(f"{name}: Out-of-Sample Equity (Kern+Filter, 70/30-Split)")
        ax.set_xlabel("Trade Nr.")
        ax.set_ylabel("Kumulierte R-Vielfache")
        ax.grid(alpha=0.3)

    plt.tight_layout()
    out_path = os.path.join(BASE, "equity_curves_v3.png")
    plt.savefig(out_path, dpi=140)
    print("saved", out_path)


if __name__ == "__main__":
    main()
