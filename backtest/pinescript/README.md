# Pine Script Port: Liquidity-Sweep/CHoCH Nasdaq-Strategie

`nasdaq_liquidity_sweep_choch.pine` ist die Pine-Script-v5-Umsetzung der in
`final_recommendation.py` validierten Nasdaq-Konfiguration (siehe
`REPORT.md` Abschnitt 7 im `backtest/`-Verzeichnis fuer die vollstaendige
Herleitung und Kennzahlen).

## Installation in TradingView

1. Chart auf ein Nasdaq-100-Instrument stellen (z.B. `NQ1!`, `USATECH`,
   `US100`, `NAS100` — je nach Broker/Datenfeed).
2. **Timeframe auf 5 Minuten (M5)** stellen — die Strategie ist dafuer kalibriert.
3. Pine-Editor oeffnen -> Inhalt von `nasdaq_liquidity_sweep_choch.pine`
   einfuegen -> "Add to Chart".
4. Im Strategy-Tester unter "Properties" eine ausreichend lange Historie
   laden (TradingView laedt bei Bedarf automatisch mehr nach).
5. `slippage` (im `strategy()`-Header) und ggf. den Tick-Wert an dein
   konkretes Symbol anpassen, damit die Kosten realistisch bleiben
   (Zielgroesse: ~1.5 Punkte Gesamtkosten pro Trade, wie im Python-Backtest
   angenommen).

## Was 1:1 identisch zur Python-Engine ist

- HTF-Bias: H4-EMA(20), einmal pro UTC-Tag aus der letzten **vor**
  Tagesbeginn abgeschlossenen H4-Kerze eingefroren (kein Blick in die Zukunft).
- Trendstaerke-, Sweep-Wick- und Displacement-Filter: alle drei ATR-basiert,
  exakt dieselben Schwellenwerte (1.0 / 0.25 / 1.0 x ATR).
- Asia-Session-Fenster (00-06 UTC), Killzone-Fenster (London 07-10 / NY 12-15 UTC).
- Ein Trade gleichzeitig, Zeit-Stop nach 48 Bars (4h), SL am Sweep-Wick,
  TP fix 1:1.5.

## Bewusste Vereinfachungen (im Script-Header dokumentiert)

1. **Equal-Highs/Lows**: es wird nur das jeweils juengste Cluster verfolgt,
   nicht alle historischen Cluster parallel.
2. **CHoCH-Kandidaten**: werden als Liste ab dem Sweep gesammelt und jeden
   Bar auf Bruch geprueft — das ist inhaltlich identisch zur "fruehester
   Bruch"-Logik in `strategy.py`, nur bar-fuer-bar (kausal) statt vektorisiert
   umgesetzt (so, wie es live ohnehin laufen wuerde).
3. **Retest-Entry**: nutzt eine native Pine-Limit-Order zum CHoCH-Level
   (mit halber Retest-Toleranz entgegenkommend) statt eines manuellen
   Fenster-Scans — realistischer als die Python-Simulation, da es der
   tatsaechlichen Order-Ausfuehrung entspricht.

Diese Unterschiede koennen zu leicht abweichenden Trades/Kennzahlen fuehren
als im Python-Backtest berichtet (WR 46-55%, PF 1.3-1.7, Exp +0.16 bis
+0.28 R/Trade). Das ist gewollt: die TradingView-Version ist der unabhaengige
Gegentest, kein Duplikat.

## Empfehlung

Alle Kernparameter sind als Inputs exponiert (Gruppen 1-5 in den
Strategie-Einstellungen). Vor Live-Einsatz: Forward-Test auf einem
Demo-Konto, Kennzahlen gegen die hier dokumentierten Referenzwerte pruefen.
