import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import integrate, optimize, stats

DATA_DIRECTORY = Path(__file__).resolve().parent.parent / "data"


def load_daily_returns(file_path: Path | str) -> pd.Series:
    data_frame = pd.read_csv(Path(file_path), usecols=["date", "open", "close"])
    data_frame["date"] = pd.to_datetime(data_frame["date"])
    daily_returns = (data_frame["close"] - data_frame["open"]) / data_frame["open"]
    return_series = pd.Series(daily_returns.values, index=data_frame["date"])
    return_series.index.name = "date"
    return return_series.sort_index()


def compute_exponential_weights(
    number_of_samples: int,
    decay_factor: float,
) -> np.ndarray:
    if not (0.0 < decay_factor <= 1.0):
        raise ValueError(f"decay_factor must be in (0, 1], got {decay_factor}")
    exponents = np.arange(number_of_samples - 1, -1, -1, dtype=float)
    return np.power(decay_factor, exponents)


def posterior(
    mu: float,
    returns: np.ndarray,
) -> stats.rv_continuous:
    """Computes the exact posterio Gamma distribution from an uninformative Gamma prior (using the improper limit alpha,beta = =) and a Gaussian likelihood with mean mu"""
    alpha = 0.5 * float(len(returns))
    beta = 0.5 * float(np.sum(np.square(returns - mu)))
    return stats.gamma(a=alpha, scale=1.0 / beta)


def hierarchical_gaussian_cdf(
    value: float,
    mu: float,
    precision_distribution: stats.rv_continuous,
) -> float:
    """The CDF of the Hierarchical Gaussian distribution with mean mu, and precision as Gamma distribution, computed using numerical integration."""
    lower_bound = precision_distribution.ppf(1e-7)
    upper_bound = precision_distribution.ppf(1.0 - 1e-7)
    integrand = lambda precision_value: (
        stats.norm.cdf(value, loc=mu, scale=1.0 / np.sqrt(precision_value))
        * precision_distribution.pdf(precision_value)
    )
    integration_result, _ = integrate.quad(integrand, lower_bound, upper_bound)
    return float(integration_result)


def optimize_bound(
    target_probability: float,
    mu: float,
    precision_distribution: stats.rv_continuous,
    lower_search_bound: float,
    upper_search_bound: float,
) -> float:
    return float(
        optimize.brentq(
            lambda return_value: (
                hierarchical_gaussian_cdf(return_value, mu, precision_distribution)
                - target_probability
            ),
            lower_search_bound,
            upper_search_bound,
        )
    )


def critical_price_interval(
    initial_price: float,
    mu: float,
    precision_distribution: stats.rv_continuous,
    coverage_probability: float,
) -> tuple[float, float]:
    """Gets the critical values of the credibility interval such that, given the initial price, there is a coverage_probability probability of the price staying within the interval."""
    tail_probability = (1.0 - coverage_probability) / 2.0

    lower_search_bound = -0.2
    upper_search_bound = 0.20

    lower_return_bound = optimize_bound(
        tail_probability,
        mu,
        precision_distribution,
        lower_search_bound,
        upper_search_bound,
    )
    upper_return_bound = optimize_bound(
        1.0 - tail_probability,
        mu,
        precision_distribution,
        lower_search_bound,
        upper_search_bound,
    )
    return (
        initial_price * (1.0 + lower_return_bound),
        initial_price * (1.0 + upper_return_bound),
    )


def load_last_price(file_path: Path | str) -> float:
    data_frame = pd.read_csv(Path(file_path), usecols=["close"])
    return float(data_frame["close"].iloc[-1])


def bayesian_inference(
    symbol: str,
    initial_price: float,
    coverage_probability: float,
    decay_factor: float,
) -> tuple[float, float]:
    file_path = DATA_DIRECTORY / f"{symbol.lower()}_daily.csv"
    returns = load_daily_returns(file_path).dropna().values

    weights = compute_exponential_weights(len(returns), decay_factor)
    normalized_weights = weights * len(returns) / np.sum(weights)
    weighted_returns = returns * np.sqrt(normalized_weights)
    precision_posterior = posterior(0.0, weighted_returns)

    return critical_price_interval(
        initial_price,
        0.0,
        precision_posterior,
        coverage_probability,
    )


def main() -> None:
    ticker = sys.argv[1].upper()
    coverage_probability_value = 0.95
    decay_factor_value = 0.995
    file_path = DATA_DIRECTORY / f"{ticker.lower()}_daily.csv"
    last_price = load_last_price(file_path)
    final_interval = bayesian_inference(
        ticker,
        last_price,
        coverage_probability_value,
        decay_factor_value,
    )
    print(final_interval)


if __name__ == "__main__":
    main()
