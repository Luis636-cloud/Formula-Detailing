"""Zeichnet einen einzelnen, realen Beispiel-Trade (M5-Candlestick-Chart)
mit allen Strategie-Elementen annotiert: Asia-High/Low, Sweep, CHoCH-Level,
Entry (Retest), SL, TP, Exit."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
from matplotlib.patches import Rectangle

from data_utils import load_5m
from strategy import precompute, run_strategy
from instruments import INSTRUMENTS
from final_recommendation import NASDAQ_PARAMS


LEVEL_LABELS = {
    "asia_high": "Asia-High", "asia_low": "Asia-Low",
    "sh": "Swing-High", "sl": "Swing-Low",
    "eqh": "Equal-High", "eql": "Equal-Low",
}


def level_label(level_id: str) -> str:
    prefix = level_id.split("_")[0] if not level_id.startswith("asia") else "_".join(level_id.split("_")[:2])
    return LEVEL_LABELS.get(prefix, level_id)


def plot_trade(df, trade, pad_before=20, pad_after=6, out_path="example_trade.png"):
    dbg = trade["debug"]
    sweep_kind = level_label(dbg["sweep_level_id"])
    start = dbg["sweep_pos"] - pad_before
    end = trade["exit_pos"] + pad_after
    window = df.iloc[start:end + 1]

    fig, ax = plt.subplots(figsize=(13, 7))

    for t, row in window.iterrows():
        color = "#16a34a" if row["close"] >= row["open"] else "#dc2626"
        ax.plot([t, t], [row["low"], row["high"]], color=color, linewidth=1, zorder=2)
        body_lo, body_hi = sorted([row["open"], row["close"]])
        width = pd.Timedelta(minutes=3.2)
        ax.add_patch(Rectangle((mdates.date2num(t) - width.total_seconds() / 86400 / 2, body_lo),
                                 width.total_seconds() / 86400, max(body_hi - body_lo, 0.05),
                                 facecolor=color, edgecolor=color, zorder=3))

    x0, x1 = window.index.min(), window.index.max()

    # Preisspanne des Fensters, um Text-Kollisionen bei eng beieinander
    # liegenden Levels (z.B. Entry nahe am CHoCH-Level) minimal zu vermeiden.
    y_span = window["high"].max() - window["low"].min()
    placed_labels = []

    def hline(y, color, label, ls="--"):
        ax.hlines(y, x0, x1, color=color, linestyle=ls, linewidth=1.4, zorder=1)
        y_text = y
        for prev in placed_labels:
            if abs(y_text - prev) < 0.045 * y_span:
                y_text = prev - 0.045 * y_span
        placed_labels.append(y_text)
        ax.text(x1, y_text, f"  {label}", va="center", ha="left", color=color, fontsize=9, fontweight="bold")

    hline(dbg["asia_high"], "#94a3b8", f"Asia-High {dbg['asia_high']:.1f}")
    hline(dbg["asia_low"], "#94a3b8", f"Asia-Low {dbg['asia_low']:.1f}")
    hline(trade["sl"], "#dc2626", f"SL {trade['sl']:.1f}", ls="-")
    hline(trade["tp"], "#16a34a", f"TP {trade['tp']:.1f}", ls="-")
    hline(dbg["sweep_level"], "#a855f7", f"Sweep-Level ({sweep_kind}) {dbg['sweep_level']:.1f}")
    hline(dbg["choch_level"], "#0891b2", f"CHoCH-Level {dbg['choch_level']:.1f}")
    hline(trade["entry_price"], "#1d4ed8", f"Entry {trade['entry_price']:.1f}", ls=":")

    def mark(t, y, text, color, dx=0, dy=1):
        ax.annotate(text, xy=(t, y), xytext=(45 * dx, 24 * dy), textcoords="offset points",
                     ha="center", fontsize=9, fontweight="bold", color=color,
                     arrowprops=dict(arrowstyle="->", color=color, lw=1.5))

    mark(dbg["sweep_time"], dbg["wick_extreme"], f"① Sweep\n(Wick-Rejection\n{sweep_kind})", "#a855f7", dx=-2, dy=-2)
    mark(dbg["choch_confirm_time"], dbg["choch_level"], "② CHoCH\nbestaetigt", "#0891b2", dx=-2, dy=2)
    mark(trade["entry_time"], trade["entry_price"], "③ Entry\n(Retest)", "#1d4ed8", dx=2, dy=3)
    mark(trade["exit_time"], trade["exit_price"], f"④ Exit ({trade['outcome'].upper()})\n{trade['r_multiple']:+.2f}R",
         "#16a34a" if trade["outcome"] == "tp" else "#dc2626", dx=1, dy=2)

    ax.set_title(f"Realer Nasdaq-Trade: {dbg['sweep_time'].strftime('%Y-%m-%d')} "
                  f"({'Long' if trade['direction']=='bullish' else 'Short'}, London-Killzone)", fontsize=13)
    ax.set_ylabel("Preis (Punkte)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.grid(alpha=0.25)
    fig.autofmt_xdate()
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    print("saved", out_path)


if __name__ == "__main__":
    df = load_5m("data/NASDAQ_5m.csv")
    spec = INSTRUMENTS["NASDAQ"]
    pre = precompute(df, NASDAQ_PARAMS["swing_n"], NASDAQ_PARAMS["micro_n"],
                       NASDAQ_PARAMS["asia_start"], NASDAQ_PARAMS["asia_end"])
    trades = run_strategy(df, pre, NASDAQ_PARAMS, spec["pip"], spec["spread"])
    plot_trade(df, trades[21], out_path="example_trade_long.png")
    plot_trade(df, trades[78], out_path="example_trade_short.png")
