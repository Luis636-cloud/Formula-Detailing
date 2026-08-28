"""Equity-Kurve fuer die finale, validierte Nasdaq-Konfiguration (volle
20-Monats-Historie) sowie Balkendiagramm der 5-Fenster-Konsistenz
Nasdaq vs. Gold (starke Filter-Zone, zum Vergleich der Robustheit)."""
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from data_utils import load_5m
from strategy import precompute, run_strategy
from instruments import INSTRUMENTS
from final_recommendation import NASDAQ_PARAMS

BASE = os.path.dirname(__file__)


def main():
    result = json.load(open(os.path.join(BASE, "final_recommendation.json")))

    df = load_5m(os.path.join(BASE, "data", "NASDAQ_5m.csv"))
    spec = INSTRUMENTS["NASDAQ"]
    pre = precompute(df, NASDAQ_PARAMS["swing_n"], NASDAQ_PARAMS["micro_n"],
                       NASDAQ_PARAMS["asia_start"], NASDAQ_PARAMS["asia_end"])
    trades = run_strategy(df, pre, NASDAQ_PARAMS, spec["pip"], spec["spread"])
    trades.sort(key=lambda t: t["entry_time"])
    eq = 0.0
    xs, ys = [0], [0.0]
    for i, t in enumerate(trades, start=1):
        eq += t["r_multiple"]
        xs.append(i)
        ys.append(eq)

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))

    axes[0].plot(xs, ys, color="#2563eb", linewidth=2)
    axes[0].axhline(0, color="#999", linewidth=1, linestyle="--")
    axes[0].set_title("Nasdaq: Equity ueber volle 20-Monats-Historie (n=113)")
    axes[0].set_xlabel("Trade Nr.")
    axes[0].set_ylabel("Kumulierte R-Vielfache")
    axes[0].grid(alpha=0.3)

    nasdaq_chunks = result["nasdaq_recommended"]["chunks"]
    gold_chunks = result["gold_strict_filter_unconfirmed"]["chunks"]
    labels = [f"F{c['chunk']}" for c in nasdaq_chunks]
    x = range(len(labels))
    w = 0.35
    nasdaq_exp = [c["expectancy_R"] for c in nasdaq_chunks]
    gold_exp = [min(c["expectancy_R"], 1.2) for c in gold_chunks]  # cap fuer Lesbarkeit (PF=142-Ausreisser)
    axes[1].bar([i - w / 2 for i in x], nasdaq_exp, width=w, color="#2563eb", label="Nasdaq (empfohlen)")
    axes[1].bar([i + w / 2 for i in x], gold_exp, width=w, color="#d97706", label="Gold (starke Filter, unbestaetigt)")
    axes[1].axhline(0, color="#999", linewidth=1)
    axes[1].set_xticks(list(x))
    axes[1].set_xticklabels(labels)
    axes[1].set_ylabel("Expectancy (R/Trade) je Zeitfenster")
    axes[1].set_title("Konsistenz ueber 5 unabh. Zeitfenster: Nasdaq robust, Gold nicht")
    axes[1].legend(fontsize=8)
    axes[1].grid(alpha=0.3, axis="y")

    plt.tight_layout()
    out = os.path.join(BASE, "final_equity_and_consistency.png")
    plt.savefig(out, dpi=140)
    print("saved", out)


if __name__ == "__main__":
    main()
