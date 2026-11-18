"""Load and compute open-to-close returns for S&P 500 and STOXX Europe 600 daily data."""

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_daily_returns(data_dir: Path | str = DATA_DIR) -> pd.DataFrame:
    """Load and compute open-to-close daily returns for SP500 and STOXX600.

    Computes raw open-to-close daily returns: (close - open) / open.
    No artificial filters needed for 10-year continuous electronic index series.
    """
    data_path = Path(data_dir)
    mapping = {
        "SP500": data_path / "sp500_daily.csv",
        "STOXX600": data_path / "stoxx600_daily.csv",
    }

    series_dict = {}
    for label, file_path in mapping.items():
        if not file_path.exists() or file_path.stat().st_size == 0:
            continue

        df = pd.read_csv(file_path, usecols=["date", "open", "close"])
        if df.empty or "date" not in df.columns:
            continue

        df["date"] = pd.to_datetime(df["date"])
        ret = (df["close"] - df["open"]) / df["open"]
        series_dict[label] = pd.Series(ret.values, index=df["date"])

    if not series_dict:
        return pd.DataFrame()

    returns_df = pd.DataFrame(series_dict)
    returns_df.index.name = "date"
    return returns_df.sort_index()


if __name__ == "__main__":
    print(f"Loading daily returns from {DATA_DIR}...")
    returns_df = load_daily_returns(DATA_DIR)
    print(f"Dataset shape: {returns_df.shape} (dates x indices)")
    print("\nSummary statistics:")
    print(returns_df.describe())
    print("\nRecent records:")
    print(returns_df.tail())
