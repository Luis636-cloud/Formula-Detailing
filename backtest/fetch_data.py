"""
Lädt historische 5-Minuten-OHLC-Daten über die öffentliche Yahoo-Finance
Chart-API (keine Authentifizierung nötig) und speichert sie als CSV.

Genutzt für den Backtest der Liquidity-Sweep / CHoCH Intraday-Strategie.
"""
import json
import time
import urllib.parse
import urllib.request
import csv
import os

SYMBOLS = {
    "XAUUSD": "GC=F",   # Gold-Future als Proxy fuer XAUUSD (Yahoo hat kein XAUUSD=X Chart)
    "NASDAQ": "NQ=F",   # Nasdaq-100 E-mini-Future als Proxy fuer den Nasdaq-Index (~24h Handel)
}

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


def fetch_json(symbol, interval="5m", rng="60d"):
    enc = urllib.parse.quote(symbol, safe="")
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{enc}?interval={interval}&range={rng}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def to_csv(name, raw, out_path):
    result = raw["chart"]["result"][0]
    ts = result["timestamp"]
    quote = result["indicators"]["quote"][0]
    o, h, l, c, v = quote["open"], quote["high"], quote["low"], quote["close"], quote["volume"]
    rows = []
    for i in range(len(ts)):
        if o[i] is None or h[i] is None or l[i] is None or c[i] is None:
            continue
        rows.append((ts[i], o[i], h[i], l[i], c[i], v[i] or 0))
    rows.sort(key=lambda r: r[0])
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp_utc", "open", "high", "low", "close", "volume"])
        for r in rows:
            w.writerow(r)
    return len(rows)


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    for name, ysym in SYMBOLS.items():
        print(f"Fetching {name} ({ysym}) ...")
        raw = fetch_json(ysym)
        out = os.path.join(DATA_DIR, f"{name}_5m.csv")
        n = to_csv(name, raw, out)
        print(f"  -> {n} bars saved to {out}")
        time.sleep(2)


if __name__ == "__main__":
    main()
