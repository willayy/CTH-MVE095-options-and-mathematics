"""Fetch 10 years of daily HLOC market data for S&P 500 and STOXX Europe 600."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ib_client import check_connection, download_data

if __name__ == "__main__":
    download_data(
        sys.argv[1].upper(),
        sys.argv[2].upper(),
        sys.argv[3].upper(),
        "127.0.0.1",
        7497,
        10,
    )
