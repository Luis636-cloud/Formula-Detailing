"""HTF-Bias (Schritt 1 der Strategie): Trendrichtung auf H4 via EMA(20).

Bias fuer einen Handelstag wird ausschliesslich aus H4-Bars bestimmt, die vor
dem Start dieses Tages (00:00 UTC) abgeschlossen sind -> kein Lookahead.
"""
import pandas as pd


def compute_h4_bias_series(h4: pd.DataFrame, ema_period: int = 20) -> pd.Series:
    ema = h4["close"].ewm(span=ema_period, adjust=False).mean()
    ema_slope = ema.diff()

    bias = pd.Series(index=h4.index, dtype=object)
    bullish = (h4["close"] > ema) & (ema_slope > 0)
    bearish = (h4["close"] < ema) & (ema_slope < 0)
    bias[:] = "neutral"
    bias[bullish] = "bullish"
    bias[bearish] = "bearish"
    return bias


def daily_bias_map(h4: pd.DataFrame, ema_period: int = 20) -> dict:
    """Liefert dict: pandas.Timestamp(date) -> 'bullish'|'bearish'|'neutral'.

    Fuer Tag D wird der Bias-Wert des letzten H4-Balkens von Tag D-1
    (Bucket 20:00-24:00 UTC) verwendet, sofern vorhanden.
    """
    bias_series = compute_h4_bias_series(h4, ema_period)
    result = {}
    dates = sorted(set(h4.index.date))
    for d in dates:
        prior = bias_series[bias_series.index.date < d]
        if len(prior) == 0:
            continue
        result[d] = prior.iloc[-1]
    return result
