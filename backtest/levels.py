"""Liquiditaets-Level (Schritt 2): Swing-Hochs/-Tiefs (Fraktale), Equal
Highs/Lows und Asia-Session High/Low."""
import numpy as np
import pandas as pd


def find_fractal_swings(df: pd.DataFrame, n: int = 3):
    """Liefert Liste von (index_pos, timestamp, price, 'high'|'low').

    Ein Bar i ist ein Swing-High, wenn sein High das Maximum im Fenster
    [i-n, i+n] ist (analog fuer Swing-Low). Ein Swing gilt erst als
    'bestaetigt', sobald die n Bars danach vorliegen -> im Backtest nur
    Swings verwenden, deren Bestaetigungsindex <= aktueller Bar ist.
    """
    highs = df["high"].values
    lows = df["low"].values
    idx = df.index
    swings = []
    m = len(df)
    for i in range(n, m - n):
        window_h = highs[i - n : i + n + 1]
        window_l = lows[i - n : i + n + 1]
        if highs[i] == window_h.max() and np.argmax(window_h) == n:
            swings.append({"pos": i, "confirmed_pos": i + n, "ts": idx[i],
                            "price": highs[i], "type": "high"})
        if lows[i] == window_l.min() and np.argmin(window_l) == n:
            swings.append({"pos": i, "confirmed_pos": i + n, "ts": idx[i],
                            "price": lows[i], "type": "low"})
    swings.sort(key=lambda s: s["confirmed_pos"])
    return swings


def asia_session_levels(df: pd.DataFrame, start_hour: int = 0, end_hour: int = 6):
    """High/Low je Kalendertag (UTC) im Asia-Fenster [start_hour, end_hour).

    Rueckgabe: dict date -> {'high': .., 'low': .., 'ready_at': Timestamp}
    ready_at = Ende des Fensters, ab dem das Level im Backtest nutzbar ist.
    """
    out = {}
    mask_hour = (df.index.hour >= start_hour) & (df.index.hour < end_hour)
    sub = df[mask_hour]
    for d, g in sub.groupby(sub.index.date):
        ready_at = pd.Timestamp(d, tz="UTC") + pd.Timedelta(hours=end_hour)
        out[d] = {"high": g["high"].max(), "low": g["low"].min(), "ready_at": ready_at}
    return out


def cluster_equal_levels(pts, tolerance: float):
    """Gruppiert die uebergebenen Swings (bereits auf einen Typ gefiltert
    und auf die letzten `lookback_n` Stueck begrenzt -- siehe strategy.py)
    zu Equal-High/Low Clustern (>=2 Beruehrungen innerhalb `tolerance`).

    Gibt Liste von Levels [(price, confirmed_pos)] zurueck, wobei
    confirmed_pos = Bestaetigungsindex des zuletzt zum Cluster
    hinzugekommenen Swings (ab dann im Backtest verwendbar).

    Performance-Hinweis: der Aufrufer ist dafuer verantwortlich, `pts`
    bereits klein zu halten (z.B. per bisect auf eine nach Typ getrennte,
    nach confirmed_pos sortierte Liste) -- ein Filtern/Slicen der
    kompletten Swing-Historie bei jedem Aufruf waere O(n) pro Bar und
    summiert sich bei zehntausenden Bars/Swings schnell zu Minuten.
    """
    pts = sorted(pts, key=lambda s: s["price"])
    clusters = []
    used = [False] * len(pts)
    for i in range(len(pts)):
        if used[i]:
            continue
        group = [pts[i]]
        used[i] = True
        for j in range(i + 1, len(pts)):
            if used[j]:
                continue
            if abs(pts[j]["price"] - group[0]["price"]) <= tolerance:
                group.append(pts[j])
                used[j] = True
        if len(group) >= 2:
            avg_price = sum(g["price"] for g in group) / len(group)
            confirmed_pos = max(g["confirmed_pos"] for g in group)
            clusters.append({"price": avg_price, "confirmed_pos": confirmed_pos})
    return clusters
