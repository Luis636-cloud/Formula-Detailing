"""Erzeugt Equity-Kurven (in R) fuer den Report."""
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
    wf = json.load(open(os.path.join(BASE, "walk_forward_results.json")))
    bl = json.load(open(os.path.join(BASE, "baseline_results.json")))

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

    xs, ys = curve_from_trades(wf["oos_trades"])
    axes[0].plot(xs, ys, color="#2563eb", linewidth=2)
    axes[0].axhline(0, color="#999", linewidth=1, linestyle="--")
    axes[0].set_title("Walk-Forward Out-of-Sample Equity (Gold + Nasdaq)")
    axes[0].set_xlabel("Trade Nr.")
    axes[0].set_ylabel("Kumulierte R-Vielfache")
    axes[0].grid(alpha=0.3)

    ys2 = bl["combined_curve"]
    xs2 = list(range(1, len(ys2) + 1))
    axes[1].plot(xs2, ys2, color="#dc2626", linewidth=2)
    axes[1].axhline(0, color="#999", linewidth=1, linestyle="--")
    axes[1].set_title("Baseline (fixe Parameter, kein Fit) Equity")
    axes[1].set_xlabel("Trade Nr.")
    axes[1].set_ylabel("Kumulierte R-Vielfache")
    axes[1].grid(alpha=0.3)

    plt.tight_layout()
    out_path = os.path.join(BASE, "equity_curves.png")
    plt.savefig(out_path, dpi=140)
    print("saved", out_path)


if __name__ == "__main__":
    main()
