# Backtest-Report: Liquidity-Sweep / CHoCH-Strategie (Gold & Nasdaq)

Zeitraum: ca. 72 Tage 5-Minuten-Daten (18. Juni – 28. August 2026), Quelle:
Yahoo-Finance Chart-API. Instrumente: **XAUUSD** (Gold, via `GC=F`-Future)
und **Nasdaq-100** (via `NQ=F`-Future).

## 1. Ergebnis auf einen Blick

| Auswertung | Trades | Winrate | Profit-Factor | Expectancy | Total (R) |
|---|---|---|---|---|---|
| **Walk-Forward Out-of-Sample** (gepoolt, 3 Runden) | 64 | **37.5 %** | 0.91 | -0.051 R | -3.28 R |
| Baseline, feste Parameter, kein Fit (gesamter Zeitraum) | 171 | 38.6 % | 0.84 | -0.094 R | -16.03 R |
| Grid-Search In-Sample (bester Fund, Train-Split) | 157 | 50.3 % | 1.05 | +0.022 R | – |
| Grid-Search Out-of-Sample (derselbe Parametersatz, Test-Split) | 64 | 32.8 % | 0.57 | -0.281 R | -17.97 R |

**Kernaussage: Die Strategie ist in dieser Form auf Gold und Nasdaq im
getesteten Zeitraum nicht profitabel.** Die Winrate liegt bei ca. 33-45 %
und damit nahe oder unter der Break-Even-Schwelle fuer ein RR von 1:1.5–1:2
(rechnerisches Break-Even bei RR 1.5 = 40 %, bei RR 2.0 = 33 %). Sobald die
Parameter nicht auf die Trainingsdaten hin optimiert werden, sondern man die
Regeln "wie beschrieben" mit sinnvollen Standardwerten umsetzt, ergibt sich
ein leicht negativer Erwartungswert. Die In-Sample-Optimierung liefert zwar
eine deutlich hoehere Winrate (50 %), diese bricht aber Out-of-Sample auf
33 % ein — ein klares Overfitting-Signal, kein reproduzierbarer Edge.

![Equity-Kurven](equity_curves.png)

*Links: gepoolte Out-of-Sample-Trades aus der Walk-Forward-Validierung
(re-optimiert pro Runde, aber immer nur auf zuvor ungesehenen Daten
getestet). Rechts: Baseline mit fest vorgegebenen, nicht angepassten
Parametern ueber den gesamten Zeitraum.*

## 2. Methodik

### 2.1 Umsetzung der Strategie-Schritte

1. **HTF-Bias**: H4-Kerzen (aus 5m aggregiert) + EMA(20). Bias = *bullish*,
   wenn Close > EMA und EMA steigend; *bearish* bei umgekehrtem Fall; sonst
   *neutral* (kein Trade). Der Bias eines Handelstags wird ausschliesslich
   aus der letzten **vor** Tagesbeginn (00:00 UTC) abgeschlossenen H4-Kerze
   bestimmt — kein Blick in die Zukunft.
2. **Liquiditaetslevel**: Asia-High/Low (00:00-06:00 UTC), Fraktal-Swings
   (n=3 Bars beidseitig) sowie Equal-Highs/Lows (>=2 Swings innerhalb
   Toleranz, Cluster ueber die letzten 30 bestaetigten Swings).
3. **Sweep**: Innerhalb der Killzone durchbricht der Kerzen-Wick ein Level
   und der Kerzen-Close kehrt dahinter zurueck (Wick-Rejection). Nur Sweeps
   in Richtung des HTF-Bias werden beachtet (bullish Bias -> Sweep von
   Tiefs/Sell-Side-Liquidity; bearish Bias -> Sweep von Hochs).
4. **CHoCH-Bestaetigung**: Nach dem Sweep wird ein Mikro-Swing (n=1 Bar,
   M5) gesucht, dessen Bruch (Close jenseits davon) den Trendwechsel
   bestaetigt — die fruehestmoegliche Bestaetigung im Zeitfenster wird
   verwendet.
5. **Entry**: Retest des gebrochenen CHoCH-Levels innerhalb eines
   Zeitfensters nach der Bestaetigung (Toleranz 2 Pips/Punkte).
6. **SL**: Extrempunkt des Sweep-Wicks +/- Puffer (2 oder 5 Pips/Punkte,
   je nach Konfiguration).
7. **TP**: Entweder fixes RR (1.5 oder 2.0) oder naechstes gegenlaeufiges
   Liquiditaetslevel (mit Mindest-RR 1.0, sonst Fallback auf fixes RR).

### 2.2 Kosten & Fill-Annahmen

- Realistischer Spread wird beim Entry angesetzt (Gold ~0.30 $, Nasdaq
  ~1.5 Punkte) — reduziert den Erwartungswert wie im echten Handel.
- Treffen SL und TP im selben 5m-Balken zu, zaehlt **SL zuerst**
  (konservativ, verhindert Schoenrechnen durch Intrabar-Unsicherheit).
- Zeit-Stop nach 4 Stunden (48 Bars) ohne SL/TP-Treffer -> Trade wird zum
  Schlusskurs geschlossen und als "timeout" gewertet.
- Nur ein offener Trade gleichzeitig je Instrument.

### 2.3 Parameteroptimierung

Durchsucht wurden nur die Parameter mit dem groessten erwarteten Einfluss:
Killzone-Auswahl (London/NY/beide), CHoCH-Fenster (12/24 Bars), Retest-
Fenster (12/24 Bars), SL-Puffer (2/5 Pips), TP-Modus/RR (fix 1.5, fix 2.0,
naechstes Level). Strukturelle Parameter (Fraktal-Groessen, Equal-Level-
Toleranz) sind bewusst **nicht** mit-optimiert, sondern fest auf uebliche
ICT-Werte gesetzt, um Overfitting auf die kurze Historie (~72 Tage) zu
begrenzen.

**Zwei Auswertungen wurden durchgefuehrt:**

1. **Einfacher 70/30-Split** (`optimize.py`): Grid-Search auf den ersten
   70 % der Daten, Auswahl der Konfiguration mit hoechster Winrate (bei
   Profit-Factor >= 1.0 und ausreichend Trades), Validierung auf den
   letzten 30 %.
2. **Walk-Forward-Validierung** (`walk_forward.py`, methodisch robuster):
   Die Zeitachse wird in 4 gleich lange Folds geteilt und 3x rollierend neu
   optimiert und auf dem jeweils naechsten, ungesehenen Fold getestet.
   Alle Out-of-Sample-Trades werden gepoolt — das ist die belastbarste
   Schaetzung fuer "echte" Performance, die mit den vorhandenen Daten
   moeglich ist.

## 3. Detailergebnisse

### 3.1 Walk-Forward (3 Runden)

| Runde | Train-Fenster | Train WR/PF | Test-Fenster | Test n | Test WR | Test PF | Test Exp. |
|---|---|---|---|---|---|---|---|
| 1 | Fold 1 (~18 Tage) | 61.1 % / 2.65 | Fold 2 | 19 | 31.6 % | 0.81 | -0.116 R |
| 2 | Fold 1-2 (~36 Tage) | 51.2 % / 1.34 | Fold 3 | 22 | 45.5 % | 1.17 | +0.086 R |
| 3 | Fold 1-3 (~54 Tage) | 50.7 % / 1.34 | Fold 4 | 23 | 34.8 % | 0.77 | -0.129 R |
| **Gepoolt** | | | | **64** | **37.5 %** | **0.91** | **-0.051 R** |

Auffaellig: Die In-Sample-Winrate ist in jeder Runde deutlich hoeher als die
nachfolgende Out-of-Sample-Winrate (61→32 %, 51→46 %, 51→35 %). Nur Runde 2
war leicht profitabel — kein konsistentes Muster, sondern eher Streuung um
die Nulllinie.

### 3.2 Baseline (feste Parameter, kein Fit, gesamter Zeitraum)

| Instrument | Trades | Winrate | Profit-Factor | Expectancy | Total (R) | Ausgaenge (TP/SL/Timeout) |
|---|---|---|---|---|---|---|
| XAUUSD | 73 | 31.5 % | 0.58 | -0.276 R | -20.18 R | 20 / 47 / 6 |
| NASDAQ | 98 | 43.9 % | 1.08 | +0.042 R | +4.15 R | 35 / 46 / 17 |
| **Kombiniert** | **171** | **38.6 %** | **0.84** | **-0.094 R** | **-16.03 R** | |

Auf Gold verliert die Strategie in diesem Zeitraum deutlich (WR 31.5 %,
PF 0.58). Auf Nasdaq ist sie nahezu Break-Even, leicht positiv (WR 43.9 %,
PF 1.08) — aber mit nur +4 R auf 98 Trades statistisch nicht belastbar
signifikant von Zufall unterscheidbar.

## 4. Einordnung & Grenzen

- **Datenbasis begrenzt**: Yahoo Finance liefert 5m-Intraday-Daten nur fuer
  rueckwirkend ca. 60-90 Tage. 64-171 Trades sind fuer belastbare
  Winrate-/PF-Schaetzungen wenig — die Konfidenzintervalle sind breit.
- **Datenqualitaet**: Futures-Kontinuitaet (`GC=F`, `NQ=F`) statt echter
  Tick-/Spot-Daten; kleine Basis-Differenzen und Rollover-Effekte moeglich.
- **Kein Hebel-/Money-Management** simuliert, nur R-Vielfache pro Trade
  (Risiko pro Trade konstant angenommen).
- **Der Kernbefund ist trotzdem belastbar genug fuer eine klare Aussage**:
  Es gibt in diesem Sample **keinen robusten, aus den Daten heraus
  bestaetigten Edge**. Eine auf denselben Daten "optimierte" hohe Winrate
  (50 %) ist nicht reproduzierbar und faellt Out-of-Sample auf ein
  Verlust-Niveau zurueck. Eine literal nach Vorschrift umgesetzte,
  nicht angepasste Version der Strategie ist leicht negativ.

## 5. Fazit

**Nein, die Strategie ist auf Gold und Nasdaq im getesteten Zeitraum nicht
zuverlaessig profitabel**, und die angestrebte "moeglichst hohe Winrate"
laesst sich nur durch In-Sample-Ueberanpassung erzeugen — nicht durch einen
echten, aus der Marktstruktur kommenden Edge. Realistisch zu erwartende
Winrate bei diesem Regelwerk: **35-45 %**, mit einem Erwartungswert nahe
Null bis leicht negativ nach Kosten.

**Ansatzpunkte fuer weitere Verbesserung** (nicht mehr in diesem Backtest
umgesetzt, aber naheliegend):
- Laengere/hochwertigere Tick-Historie (>1 Jahr) fuer belastbarere Statistik.
- Zusaetzlicher Qualitaetsfilter fuer den Sweep (z. B. Mindest-Wickgroesse
  relativ zum ATR, Volumen-Bestaetigung).
- CHoCH-Bestaetigung auf einer *festen* Struktur (z. B. immer der
  unmittelbar vorausgehende signifikante Swing) statt des fruehesten
  Mikro-Swing-Bruchs, um Fehlsignale in Choppy-Phasen zu reduzieren.
- Handel nur an Tagen mit klar definiertem HTF-Trend (z. B. Mindestabstand
  Close zu EMA), um "neutrale"/Range-Phasen konsequenter auszufiltern.
