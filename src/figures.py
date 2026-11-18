"""Generate return distribution figures for S&P 500 and STOXX Europe 600 daily data."""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.bayesian_inference import load_daily_returns

DATA_DIRECTORY = PROJECT_ROOT / "data"
FIGURES_DIRECTORY = PROJECT_ROOT / "figures"


def get_percentage_returns(return_series: pd.Series) -> np.ndarray:
    """Return non-null percentage returns for a symbol."""
    return (return_series.dropna() * 100.0).values


def compute_empirical_cumulative_distribution_function(
    data: np.ndarray,
    edges: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute empirical cumulative distribution steps over specified bin edges."""
    counts, _ = np.histogram(np.clip(data, edges[0], edges[-1]), bins=edges)
    cumulative_probabilities = np.cumsum(counts) / len(data)
    return (
        np.concatenate([[edges[0]], edges[1:]]),
        np.concatenate([[0.0], cumulative_probabilities]),
    )


def save_and_close_figure(figure: plt.Figure, output_file_path: Path) -> Path:
    """Save figure at 300 DPI and close it."""
    figure.savefig(output_file_path, dpi=300, bbox_inches="tight")
    plt.close(figure)
    print(f"Saved: {output_file_path}")
    return output_file_path


def format_cumulative_axis(
    axes: plt.Axes,
    maximum_x_value: float,
    y_axis_label: str,
) -> None:
    """Apply standard styling to cumulative probability axes."""
    axes.set_xlabel("Movement Magnitude Threshold x (%)", fontsize=10)
    if y_axis_label:
        axes.set_ylabel(y_axis_label, fontsize=11)
    axes.set_xlim(0, maximum_x_value)
    axes.set_ylim(0, 1.02)
    axes.set_xticks(np.arange(0, maximum_x_value + 0.5, 0.5))
    axes.set_yticks(np.arange(0, 1.1, 0.1))
    axes.grid(True, linestyle=":", alpha=0.6)


def plot_variance_distribution(
    ticker: str,
    return_series: pd.Series,
    output_directory: Path,
) -> Path:
    percentage_returns = get_percentage_returns(return_series)
    span = 4.0
    bucket_width = 0.25
    edges = np.arange(-span, span + bucket_width, bucket_width)
    clipped_data = np.clip(percentage_returns, edges[0], edges[-1])

    figure, axes = plt.subplots(figsize=(10, 6), layout="constrained")
    axes.hist(
        clipped_data,
        bins=list(edges),
        weights=np.ones(len(clipped_data)) / len(clipped_data) * 100.0,
        color="#1f77b4",
        edgecolor="black",
        linewidth=0.5,
        rwidth=0.85,
    )
    axes.set_title(
        f"{ticker.upper()} Daily Return Distribution (Daily Std: {percentage_returns.std():.2f}%)\nBucket Size: {bucket_width:.2f}%",
        fontsize=12,
        fontweight="bold",
    )
    axes.set_xlabel(f"Daily Return Bucket (Width: {bucket_width:.2f}%)", fontsize=10)
    axes.set_ylabel("Percentage of Days (%)", fontsize=10)
    axes.grid(True, axis="y", linestyle=":", alpha=0.7)

    output_path = output_directory / f"{ticker.lower()}_variance_distribution.png"
    return save_and_close_figure(figure, output_path)


def plot_cumulative_movement(
    ticker: str,
    return_series: pd.Series,
    output_directory: Path,
) -> Path:
    percentage_returns = get_percentage_returns(return_series)
    absolute_data = np.abs(percentage_returns)
    edges = np.arange(0.0, 6.10, 0.10)

    figure, (axes_top, axes_bottom) = plt.subplots(
        2, 1, figsize=(10, 9), layout="constrained"
    )

    # Top panel: Cumulative probability P(|R| <= x)
    x_values, y_values = compute_empirical_cumulative_distribution_function(
        absolute_data, edges
    )
    probability_1pct = float((absolute_data <= 1.0).mean() * 100.0)
    probability_2pct = float((absolute_data <= 2.0).mean() * 100.0)

    axes_top.step(
        x_values,
        y_values,
        where="post",
        linewidth=2.2,
        color="#1f77b4",
        label=f"{ticker.upper()} (P(|R| ≤ 1%): {probability_1pct:.1f}%, P(|R| ≤ 2%): {probability_2pct:.1f}%)",
    )
    axes_top.fill_between(x_values, y_values, step="post", alpha=0.10, color="#1f77b4")
    axes_top.set_title(
        f"{ticker.upper()} Cumulative Probability of Daily Absolute Movement P(|Return| ≤ x)",
        fontsize=12,
        fontweight="bold",
    )
    format_cumulative_axis(axes_top, 6.0, "Cumulative Probability P(|R| ≤ x)")
    axes_top.legend(frameon=True, fontsize=10, loc="lower right")

    # Bottom panel: Conditional negative vs. positive movements
    negative_returns = np.abs(percentage_returns[percentage_returns <= 0.0])
    positive_returns = percentage_returns[percentage_returns >= 0.0]
    x_negative, y_negative = compute_empirical_cumulative_distribution_function(
        negative_returns, edges
    )
    x_positive, y_positive = compute_empirical_cumulative_distribution_function(
        positive_returns, edges
    )

    percentage_negative = len(negative_returns) / len(percentage_returns) * 100.0
    percentage_positive = len(positive_returns) / len(percentage_returns) * 100.0

    axes_bottom.step(
        x_negative,
        y_negative,
        where="post",
        color="#d62728",
        linewidth=2.2,
        linestyle="--",
        label=f"Negative (Down {percentage_negative:.1f}% of days)",
    )
    axes_bottom.step(
        x_positive,
        y_positive,
        where="post",
        color="#2ca02c",
        linewidth=2.2,
        linestyle="-",
        label=f"Positive (Up {percentage_positive:.1f}% of days)",
    )
    axes_bottom.fill_between(
        x_negative,
        y_negative,
        y_positive,
        step="post",
        alpha=0.15,
        color="#9467bd",
        label="Asymmetry Difference",
    )
    axes_bottom.set_title(
        f"{ticker.upper()} Conditional Directional Movement Probabilities",
        fontsize=12,
        fontweight="bold",
    )
    format_cumulative_axis(axes_bottom, 6.0, "Cumulative Probability")
    axes_bottom.legend(frameon=True, fontsize=9.5, loc="lower right")

    output_path = output_directory / f"{ticker.lower()}_cumulative_probabilities.png"
    return save_and_close_figure(figure, output_path)


if __name__ == "__main__":
    ticker_name = sys.argv[1].lower()
    FIGURES_DIRECTORY.mkdir(parents=True, exist_ok=True)
    input_file_path = DATA_DIRECTORY / f"{ticker_name}_daily.csv"
    returns_series = load_daily_returns(input_file_path)

    plot_variance_distribution(ticker_name, returns_series, FIGURES_DIRECTORY)
    plot_cumulative_movement(ticker_name, returns_series, FIGURES_DIRECTORY)
