"""Instrument-Metadaten: Pip-Groesse und ein realistischer, typischer
Retail-Spread (wird im Backtest als Kosten gegen den Trader angesetzt)."""

INSTRUMENTS = {
    # name: pip_size (=Skalierungseinheit fuer Toleranz-/Buffer-Parameter),
    #       typischer Retail-Spread in Preiseinheiten (Kosten je Trade)
    "XAUUSD": {"pip": 0.01, "spread": 0.30},   # Gold-Future GC=F als Proxy, ~30 cent Spread
    "NASDAQ": {"pip": 1.00, "spread": 1.50},   # Nasdaq-100-Future NQ=F als Proxy, ~1.5 Punkte Spread
}
