"""Holt echte Tick-Daten von Dukascopy (oeffentlich, kein API-Key noetig)
fuer einen deutlich laengeren Zeitraum als die 72 Tage von Yahoo Finance,
und aggregiert sie zu 5-Minuten-OHLC-Bars.

Format: https://datafeed.dukascopy.com/datafeed/{SYMBOL}/{YYYY}/{MM-1}/{DD}/{HH}h_ticks.bi5
- LZMA-komprimiert, je Tick 20 Bytes big-endian: (ms_offset, ask*factor, bid*factor, ask_vol, bid_vol)
- point_factor=1000 fuer sowohl XAUUSD als auch USATECHIDXUSD (empirisch verifiziert)
- Symbol-Zuordnung: XAUUSD -> 'XAUUSD' (Gold/USD CFD), NASDAQ -> 'USATECHIDXUSD' (Nasdaq-100 CFD)

Rate-Limit: Dukascopy blockt bei zu hoher Parallelitaet mit HTTP 429 fuer
eine kurze Cooldown-Phase. Daher: kleine Thread-Pools + Exponential-Backoff-
Retry, Fortschritt wird taeglich auf Platte geschrieben (fortsetzbar).
"""
import concurrent.futures
import datetime
import json
import lzma
import os
import struct
import time

import requests

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
PROGRESS_DIR = os.path.join(DATA_DIR, "_dukascopy_progress")

SYMBOLS = {
    "XAUUSD": {"duka_symbol": "XAUUSD", "point_factor": 1000},
    "NASDAQ": {"duka_symbol": "USATECHIDXUSD", "point_factor": 1000},
}

MAX_WORKERS = 6
MAX_RETRIES = 5


def _url(duka_symbol, dt):
    return (f"https://datafeed.dukascopy.com/datafeed/{duka_symbol}/"
            f"{dt.year}/{dt.month - 1:02d}/{dt.day:02d}/{dt.hour:02d}h_ticks.bi5")


def _fetch_hour(session, duka_symbol, dt):
    """Liefert Liste von (epoch_ms, bid, ask) Ticks fuer diese Stunde, oder []
    wenn keine Daten (Wochenende/Feiertag/Marktschluss)."""
    url = _url(duka_symbol, dt)
    hour_start_ms = int(dt.replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)
    backoff = 2
    for attempt in range(MAX_RETRIES):
        try:
            r = session.get(url, timeout=20)
        except requests.RequestException:
            time.sleep(backoff)
            backoff *= 2
            continue
        if r.status_code == 200:
            raw = r.content
            if len(raw) == 0:
                return []
            try:
                data = lzma.decompress(raw)
            except lzma.LZMAError:
                return []
            n = len(data) // 20
            out = []
            factor = SYMBOLS_BY_DUKA[duka_symbol]["point_factor"]
            for i in range(n):
                ms_off, ask_raw, bid_raw, _av, _bv = struct.unpack_from(">iiiff", data, i * 20)
                out.append((hour_start_ms + ms_off, bid_raw / factor, ask_raw / factor))
            return out
        if r.status_code == 404:
            return []
        if r.status_code == 429:
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)
            continue
        # anderer Fehler (5xx etc.) -> retry
        time.sleep(backoff)
        backoff *= 2
    return []  # nach MAX_RETRIES aufgeben, Stunde zaehlt als "keine Daten"


SYMBOLS_BY_DUKA = {v["duka_symbol"]: v for v in SYMBOLS.values()}


def _aggregate_5m(ticks):
    """ticks: Liste (epoch_ms, bid, ask) fuer EINEN Tag. Liefert Liste von
    5-Minuten-OHLC-Zeilen (timestamp_utc, open, high, low, close, volume)
    auf Basis des Mid-Preises, plus Tick-Count als Volumen-Proxy."""
    if not ticks:
        return []
    ticks.sort(key=lambda t: t[0])
    buckets = {}
    for ms, bid, ask in ticks:
        mid = (bid + ask) / 2.0
        bucket_ts = (ms // 1000 // 300) * 300  # 300s = 5min Bucket, epoch seconds
        b = buckets.get(bucket_ts)
        if b is None:
            buckets[bucket_ts] = [mid, mid, mid, mid, 1]
        else:
            b[1] = max(b[1], mid)
            b[2] = min(b[2], mid)
            b[3] = mid
            b[4] += 1
    rows = []
    for ts in sorted(buckets):
        o, h, l, c, v = buckets[ts]
        rows.append((ts, o, h, l, c, v))
    return rows


def fetch_day(session, duka_symbol, day: datetime.date):
    all_ticks = []
    hours = [datetime.datetime(day.year, day.month, day.day, h) for h in range(24)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for ticks in ex.map(lambda dt: _fetch_hour(session, duka_symbol, dt), hours):
            all_ticks.extend(ticks)
    return _aggregate_5m(all_ticks)


def fetch_range(name, days_back=365, end_date=None):
    spec = SYMBOLS[name]
    duka_symbol = spec["duka_symbol"]
    os.makedirs(PROGRESS_DIR, exist_ok=True)
    out_csv = os.path.join(DATA_DIR, f"{name}_5m_dukascopy.csv")
    progress_file = os.path.join(PROGRESS_DIR, f"{name}_progress.json")

    if end_date is None:
        end_date = datetime.datetime.now(datetime.timezone.utc).date() - datetime.timedelta(days=1)
    start_date = end_date - datetime.timedelta(days=days_back)

    done_days = set()
    if os.path.exists(progress_file):
        done_days = set(json.load(open(progress_file)))

    write_header = not os.path.exists(out_csv)
    session = requests.Session()

    day = start_date
    n_days_total = (end_date - start_date).days + 1
    processed = 0
    t0 = time.time()
    with open(out_csv, "a") as f:
        if write_header:
            f.write("timestamp_utc,open,high,low,close,volume\n")
        while day <= end_date:
            key = day.isoformat()
            processed += 1
            if key in done_days:
                day += datetime.timedelta(days=1)
                continue
            if day.weekday() == 5:  # Samstag: praktisch nie Handel (24/5 Markt)
                done_days.add(key)
                day += datetime.timedelta(days=1)
                continue
            rows = fetch_day(session, duka_symbol, day)
            for ts, o, h, l, c, v in rows:
                f.write(f"{ts},{o},{h},{l},{c},{v}\n")
            f.flush()
            done_days.add(key)
            if processed % 10 == 0 or day == end_date:
                json.dump(sorted(done_days), open(progress_file, "w"))
                elapsed = time.time() - t0
                print(f"[{name}] {key}: {len(rows)} Bars  "
                      f"({processed}/{n_days_total} Tage, {elapsed:.0f}s)", flush=True)
            day += datetime.timedelta(days=1)
    json.dump(sorted(done_days), open(progress_file, "w"))
    print(f"[{name}] fertig -> {out_csv}")


if __name__ == "__main__":
    import sys
    days_back = int(sys.argv[1]) if len(sys.argv) > 1 else 365
    for name in SYMBOLS:
        fetch_range(name, days_back=days_back)
