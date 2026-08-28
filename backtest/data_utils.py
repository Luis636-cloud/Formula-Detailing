"""Laden & Aufbereiten der 5m-Kursdaten (CSV aus fetch_data.py)."""
import pandas as pd


def load_5m(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["dt"] = pd.to_datetime(df["timestamp_utc"], unit="s", utc=True)
    df = df.set_index("dt").sort_index()
    df = df[["open", "high", "low", "close", "volume"]]
    # doppelte Timestamps / offensichtliche Datenfehler entfernen
    df = df[~df.index.duplicated(keep="first")]
    df = df.dropna()
    return df


def resample_h4(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregiert 5m-Bars zu festen 4h-UTC-Bloecken (00,04,08,12,16,20)."""
    o = df["open"].resample("4h", origin="start_day").first()
    h = df["high"].resample("4h", origin="start_day").max()
    l = df["low"].resample("4h", origin="start_day").min()
    c = df["close"].resample("4h", origin="start_day").last()
    out = pd.concat([o, h, l, c], axis=1)
    out.columns = ["open", "high", "low", "close"]
    return out.dropna()


def train_test_split_by_time(df: pd.DataFrame, train_frac: float = 0.7):
    n = len(df)
    cut = int(n * train_frac)
    cut_time = df.index[cut]
    train = df[df.index < cut_time]
    test = df[df.index >= cut_time]
    return train, test
