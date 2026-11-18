"""Fetch 10 years of daily HLOC market data for S&P 500 and STOXX Europe 600."""

from pathlib import Path

from ib_async import IB, Index, util

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    ib = IB()
    print("Connecting to TWS...")
    ib.connect("127.0.0.1", 7497, clientId=10)
    print("Connected.")

    # 1. S&P 500 Index (SPX on CBOE)
    spx = Index("SPX", "CBOE", "USD")
    ib.qualifyContracts(spx)
    bars_spx = ib.reqHistoricalData(
        spx, "", "10 Y", "1 day", "TRADES", useRTH=True, formatDate=1
    )
    df_spx = util.df(bars_spx)
    out_spx = DATA_DIR / "sp500_daily.csv"
    df_spx.to_csv(out_spx, index=False)
    print(f"[SPX] Saved {len(df_spx)} daily bars to {out_spx}")

    # 2. STOXX Europe 600 Index (DJ600 on EUREX)
    dj600 = Index("DJ600", "EUREX", "EUR")
    ib.qualifyContracts(dj600)
    bars_dj600 = ib.reqHistoricalData(
        dj600, "", "10 Y", "1 day", "TRADES", useRTH=True, formatDate=1
    )
    df_dj600 = util.df(bars_dj600)
    out_dj600 = DATA_DIR / "stoxx600_daily.csv"
    df_dj600.to_csv(out_dj600, index=False)
    print(f"[DJ600] Saved {len(df_dj600)} daily bars to {out_dj600}")

    ib.disconnect()
    print("Disconnected from TWS.")


if __name__ == "__main__":
    main()
