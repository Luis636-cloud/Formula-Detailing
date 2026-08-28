"""Laedt echte 1-Minuten-OHLC-Daten von HistData.com (oeffentlich, kein
API-Key, ein Request-Paar pro Monat statt 24 Einzelabfragen pro Tag wie bei
Dukascopy) und aggregiert sie zu 5-Minuten-Bars im selben CSV-Format wie
fetch_data.py (Yahoo).

Warum HistData statt Dukascopy: Dukascopys datafeed-Endpunkt limitiert sehr
aggressiv nach IP (in dieser Sandbox-Umgebung mit ggf. geteilter Egress-IP
schon nach 1-2 Requests, mit eskalierender Sperre) -- fuer ein Jahr Historie
waeren tausende Einzelrequests noetig. HistData liefert dieselbe Grundlage
(echte Tick-basierte 1m-Bars) als EIN Zip pro Monat -> fuer 24 Monate x 2
Instrumente nur 96 Requests.

Wichtig: HistData-Zeitstempel sind in US-Eastern-Lokalzeit (mit DST,
empirisch gegen unsere Yahoo-UTC-Daten anhand des woechentlichen
Sonntag-Reopens verifiziert: Yahoo 22:00 UTC == HistData 18:00 lokal im
Juli/EDT) -- NICHT die oft kolportierte 'feste EST'-Konvention. Konversion
erfolgt daher ueber zoneinfo('America/New_York'), nicht per fixem Offset.
"""
import datetime
import io
import re
import time
import zipfile
from zoneinfo import ZoneInfo

import requests

NY = ZoneInfo("America/New_York")
UTC = datetime.timezone.utc

SYMBOLS = {
    "XAUUSD": "xauusd",
    "NASDAQ": "nsxusd",
}

BASE = "https://www.histdata.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _month_page_url(symbol, year, month):
    return f"{BASE}/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/{symbol}/{year}/{month}"


def _get_token(session, symbol, year, month):
    url = _month_page_url(symbol, year, month)
    r = session.get(url, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    m = re.search(r'<form id="file_down".*?</form>', r.text, re.S)
    if not m:
        return None  # Monat existiert nicht / keine Daten
    form = m.group(0)

    def field(name):
        fm = re.search(rf'name="{name}" id="{name}" value="([^"]*)"', form)
        return fm.group(1) if fm else None

    return {
        "tk": field("tk"), "date": field("date"), "datemonth": field("datemonth"),
        "platform": field("platform"), "timeframe": field("timeframe"), "fxpair": field("fxpair"),
        "referer": url,
    }


def _download_month_csv(session, fields):
    r = session.post(
        f"{BASE}/get.php",
        headers={"User-Agent": UA, "Referer": fields["referer"]},
        data={"tk": fields["tk"], "date": fields["date"], "datemonth": fields["datemonth"],
              "platform": fields["platform"], "timeframe": fields["timeframe"], "fxpair": fields["fxpair"]},
        timeout=60,
    )
    r.raise_for_status()
    if len(r.content) < 100:
        return None
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    csv_name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
    return zf.read(csv_name).decode("ascii", errors="ignore")


def _parse_month_csv(text):
    """Liefert Liste (epoch_seconds_utc, o, h, l, c, v)."""
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        ts, o, h, l, c, v = line.split(";")
        naive = datetime.datetime.strptime(ts, "%Y%m%d %H%M%S")
        local = naive.replace(tzinfo=NY)
        utc_dt = local.astimezone(UTC)
        rows.append((int(utc_dt.timestamp()), float(o), float(h), float(l), float(c), float(v)))
    return rows


def _aggregate_5m(rows_1m):
    """rows_1m sortiert nach epoch_seconds_utc -> 5-Minuten-OHLC-Bars."""
    buckets = {}
    for ts, o, h, l, c, v in rows_1m:
        b_ts = (ts // 300) * 300
        b = buckets.get(b_ts)
        if b is None:
            buckets[b_ts] = [o, h, l, c, v]
        else:
            b[1] = max(b[1], h)
            b[2] = min(b[2], l)
            b[3] = c
            b[4] += v
    return [(ts, *buckets[ts]) for ts in sorted(buckets)]


def month_range(n_months, end=None):
    """Liefert Liste von (year, month) fuer die letzten n_months, aeltester zuerst."""
    if end is None:
        today = datetime.datetime.now(UTC)
        end = (today.year, today.month)
    y, m = end
    out = []
    for _ in range(n_months):
        out.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(out))


def fetch_instrument(name, n_months=24, delay=1.5, max_retries=4):
    symbol = SYMBOLS[name]
    session = requests.Session()
    all_1m = []
    months = month_range(n_months)
    for (y, m) in months:
        ok = False
        for attempt in range(max_retries):
            try:
                fields = _get_token(session, symbol, y, m)
                if fields is None or not fields.get("tk"):
                    print(f"[{name}] {y}-{m:02d}: kein Datenmonat, ueberspringe")
                    ok = True
                    break
                time.sleep(delay)
                text = _download_month_csv(session, fields)
                if text is None:
                    print(f"[{name}] {y}-{m:02d}: leer")
                    ok = True
                    break
                rows = _parse_month_csv(text)
                all_1m.extend(rows)
                print(f"[{name}] {y}-{m:02d}: {len(rows)} 1m-Bars")
                ok = True
                break
            except Exception as e:
                print(f"[{name}] {y}-{m:02d}: Fehler ({e}), retry {attempt+1}/{max_retries}")
                time.sleep(delay * (attempt + 2))
        if not ok:
            print(f"[{name}] {y}-{m:02d}: aufgegeben nach {max_retries} Versuchen")
        time.sleep(delay)
    all_1m.sort(key=lambda r: r[0])
    bars_5m = _aggregate_5m(all_1m)
    return bars_5m


def save_csv(bars_5m, path):
    with open(path, "w") as f:
        f.write("timestamp_utc,open,high,low,close,volume\n")
        for ts, o, h, l, c, v in bars_5m:
            f.write(f"{ts},{o},{h},{l},{c},{v}\n")
    print(f"-> {path}: {len(bars_5m)} 5m-Bars")


if __name__ == "__main__":
    import os
    import sys
    n_months = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    for name in SYMBOLS:
        bars = fetch_instrument(name, n_months=n_months)
        save_csv(bars, os.path.join(data_dir, f"{name}_5m_histdata.csv"))
