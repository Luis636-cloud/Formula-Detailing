"""Kennzahlen aus einer Trade-Liste (r_multiple = PnL in Vielfachen des Risikos)."""


def compute_metrics(trades):
    n = len(trades)
    if n == 0:
        return {"n_trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
                "expectancy_R": 0.0, "max_drawdown_R": 0.0, "total_R": 0.0, "curve": []}

    wins = [t for t in trades if t["r_multiple"] > 0]
    losses = [t for t in trades if t["r_multiple"] <= 0]
    win_rate = len(wins) / n
    gross_win = sum(t["r_multiple"] for t in wins)
    gross_loss = -sum(t["r_multiple"] for t in losses)
    if gross_loss > 0:
        profit_factor = gross_win / gross_loss
    else:
        profit_factor = float("inf") if gross_win > 0 else 0.0
    expectancy = sum(t["r_multiple"] for t in trades) / n

    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    curve = []
    for t in sorted(trades, key=lambda x: x["entry_time"]):
        equity += t["r_multiple"]
        curve.append(equity)
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    return {
        "n_trades": n, "win_rate": win_rate, "profit_factor": profit_factor,
        "expectancy_R": expectancy, "max_drawdown_R": max_dd, "total_R": equity,
        "curve": curve,
    }
