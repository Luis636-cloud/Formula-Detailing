# Liquidity-Sweep / CHoCH Intraday-Backtest (Gold & Nasdaq)

Backtest-Engine fuer die vorgegebene ICT-artige Strategie:

1. **HTF-Bias** (H4) via EMA(20)-Trendfilter
2. **Liquiditaetslevel**: Asia-Session High/Low, Equal Highs/Lows, letzter Swing
3. **Sweep** eines Levels mit Wick-Rejection waehrend London-/NY-Killzone
4. **CHoCH-Bestaetigung** auf M5 nach dem Sweep
5. **Entry** per Retest des gebrochenen Micro-Structure-Levels
6. **SL** knapp hinter dem Sweep-Wick
7. **TP** fix (1:1.5 / 1:2) oder naechstes Liquiditaetslevel

Getestete Instrumente: **XAUUSD** (Gold, Proxy: `GC=F` Future) und **Nasdaq-100**
(Proxy: `NQ=F` E-mini-Future, ~24h gehandelt -> Asia/London/NY-Sessions sind
hier definiert). Datenquelle: oeffentliche Yahoo-Finance Chart-API, 5-Minuten-
Kerzen, ca. 72 Tage Historie (laenger ist bei 5m-Aufloesung dort nicht
verfuegbar).

## Ergebnis in Kuerze

**Die Strategie zeigt in diesem Zeitraum/auf diesen Instrumenten keinen
robusten, profitablen Edge** — auch nicht nach einem gezielten zweiten
Optimierungslauf mit zusaetzlichen ATR-/Volumen-basierten Qualitaetsfiltern
(Trendstaerke, Sweep-Groesse, CHoCH-Displacement, Volumen), separat fuer
Gold und Nasdaq optimiert. Winrate liegt je nach Parametrisierung bei
~32-48%, Out-of-Sample durchgaengig mit Profit-Factor <= 1.1. Einziger
schwacher Lichtblick: Gold mit Filtern erreicht PF 1.11 auf nur 13
Out-of-Sample-Trades — statistisch nicht belastbar. Details und Methodik:
siehe [`REPORT.md`](REPORT.md) (Abschnitt 6 fuer den zweiten Anlauf).

## Struktur

```
backtest/
  fetch_data.py       # Laedt 5m-OHLC-Daten (Yahoo Chart API) -> data/*.csv
  data_utils.py        # CSV laden, H4-Resampling, Train/Test-Split
  instruments.py        # Pip-Groesse & typischer Spread je Instrument
  bias.py               # HTF-Bias (EMA20 auf H4)
  levels.py             # Fraktal-Swings, Asia-Session-Level, Equal-Highs/Lows
  strategy.py            # Sweep -> CHoCH -> Retest-Entry -> SL/TP -> Simulation
  metrics.py             # Winrate, Profit-Factor, Expectancy, Max-Drawdown
  optimize.py            # Grid-Search mit einfachem 70/30 Train/Test-Split
  walk_forward.py        # Robustere Analyse: rollierende Walk-Forward-Validierung
  baseline_check.py      # Kontroll-Lauf mit fest vorgegebenen (nicht optimierten) Parametern
  indicators.py           # ATR & rollierender Volumen-Median (fuer Qualitaetsfilter)
  optimize_v2.py           # 2. Anlauf: 4-Fold-Walk-Forward + Filter pro Instrument (verworfen, zu wenig Trades/Fold)
  optimize_v3.py           # 2. Anlauf: einzelner 70/30-Split + Filter pro Instrument (finales Ergebnis)
  make_charts.py           # Equity-Kurven (1. Anlauf) als PNG
  make_charts_v3.py         # Equity-Kurven (2. Anlauf, Gold/Nasdaq einzeln) als PNG
  data/*.csv                # Rohdaten (bereits geladen, fuer Reproduzierbarkeit)
  REPORT.md                 # Ausfuehrlicher Ergebnisbericht (inkl. Abschnitt 6: Filter-Anlauf)
```

## Reproduzieren

```bash
pip install pandas numpy matplotlib
cd backtest
python fetch_data.py        # optional: Daten neu laden
python optimize.py          # einfacher Train/Test-Split + Grid-Search
python walk_forward.py       # rollierende Walk-Forward-Validierung (empfohlen)
python baseline_check.py     # Kontroll-Lauf ohne Parameter-Fit
python make_charts.py        # Equity-Kurven-PNG erzeugen (1. Anlauf)
python optimize_v3.py         # 2. Anlauf: Qualitaetsfilter, 70/30-Split pro Instrument
python make_charts_v3.py      # Equity-Kurven-PNG erzeugen (2. Anlauf)
```

## Wichtige methodische Entscheidungen

- **Killzones**: London 07:00-10:00 UTC, NY 12:00-15:00 UTC (Standard-ICT-Fenster).
- **Asia-Session**: 00:00-06:00 UTC fuer Asia-High/Low.
- **Ein Trade gleichzeitig** je Instrument, Zeit-Stop nach 4h (48 M5-Bars) ohne SL/TP-Treffer.
- **Kosten**: realistischer Retail-Spread je Instrument wird bei Entry angesetzt
  (Gold ~0.30$, Nasdaq ~1.5 Punkte) — die Strategie muss die Kosten ueberdecken,
  nicht nur "auf dem Papier" funktionieren.
- **Konservative Fill-Annahme**: Treffen SL und TP im selben Balken beide zu,
  zaehlt SL zuerst (worst case, verhindert Schoenrechnen).
- **Grid-Search NUR** auf den performance-kritischen Parametern (Killzone-Wahl,
  CHoCH-/Retest-Fenster, SL-Puffer, TP-Modus/RR); strukturelle Parameter
  (Fraktal-Groessen, Toleranzen) sind fest auf ICT-uebliche Werte gesetzt, um
  Overfitting auf ~72 Tage Historie zu begrenzen.
- **Walk-Forward statt einmaligem Split**: Because ein einzelner 70/30-Split
  Zufallsglueck der Testperiode als Ergebnis ausgeben kann, wird zusaetzlich in
  3 rollierenden Runden trainiert/validiert und das gepoolte Out-of-Sample-
  Ergebnis berichtet — das ist die belastbarste Zahl in diesem Repo.
