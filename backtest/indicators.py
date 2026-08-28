"""Hilfsindikatoren: ATR und rollierendes Volumen-Perzentil, genutzt fuer
zusaetzliche Qualitaetsfilter (Sweep-Groesse, Displacement, Volumen)."""
import pandas as pd


def atr_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def rolling_median_volume(df: pd.DataFrame, period: int = 20) -> pd.Series:
    return df["volume"].rolling(period, min_periods=period).median()
