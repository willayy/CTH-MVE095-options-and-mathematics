# Options and Mathematics (MVE095)

This repository contains code for deriving an options trading strategy on the broker platform Interactive Brokers.

## Setup

Activate the Python virtual environment:

```zsh
source .venv/bin/activate
```

Ensure Trader Workstation (TWS) or IB Gateway is running with API socket connections enabled (port `7497` for paper trading).

## Usage & Execution

Run the scripts in order:

### 1. Check TWS Connection

Verify socket connectivity and account data:

```zsh
python src/check_tws_connection.py
```

### 2. Fetch Daily Index Market Data (10 Years)

Downloads 10 years of daily HLOC historical bars for the S&P 500 (`SPX`) and STOXX Europe 600 (`DJ600`) indices directly from TWS:

```zsh
python src/get_data.py
```

Outputs:

- `./data/sp500_daily.csv`: 10 years of daily bars for S&P 500 (`SPX`, ~2,511 trading days)
- `./data/stoxx600_daily.csv`: 10 years of daily bars for STOXX Europe 600 (`DJ600`, ~2,546 trading days)

All data files in `./data/` are gitignored.

### 3. Bayesian Inference

Loads the daily HLOC data and computes open-to-close returns across the indices:

```zsh
python src/bayesian_inference.py
```

### 4. Generate Return Distribution Figures

Generates variance and cumulative movement distribution figures to `./figures/`:

```zsh
python src/figures.py
```

The script outputs threetwo comprehensive 3-panel figures into `./figures/`:

- `daily_returns_variance_comparison.png`: 3-panel figure with side-by-side bucket histograms for S&P 500 and STOXX Europe 600 (top) and their overlaid frequency step distribution (bottom).
- `daily_returns_cumulative_probabilities.png`: 3-panel figure with the cumulative probability of daily absolute movement $P(|R| \le x)$ across both indices (top) and conditional negative vs. positive movement distributions $P(|R| \le x \mid R < 0)$ vs. $P(R \le x \mid R > 0)$ for each index (bottom).
