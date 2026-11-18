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

CONFIGS = {
    "S&P 500 (SPX)": ("SP500", 4.0, 0.25),
    "STOXX Europe 600 (DJ600)": ("STOXX600", 4.0, 0.25),
}
COLORS = {"SP500": "#1f77b4", "STOXX600": "#ff7f0e"}


# --- Reusable Helpers ---


def get_pct_returns(returns_df: pd.DataFrame, sym: str) -> np.ndarray:
    """Return non-null percentage returns for a symbol."""
    return (returns_df[sym].dropna() * 100).values


def compute_ecdf(data: np.ndarray, edges: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Compute empirical cumulative distribution steps over specified bin edges."""
    counts, _ = np.histogram(np.clip(data, edges[0], edges[-1]), bins=edges)
    cum = np.cumsum(counts) / len(data)
    return np.concatenate([[edges[0]], edges[1:]]), np.concatenate([[0.0], cum])


def save_and_close(fig: plt.Figure, out_path: Path) -> Path:
    """Save figure at 300 DPI and close it."""
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out_path}")
    return out_path


def format_cumulative_axis(
    ax: plt.Axes, xmax: float = 6.0, ylabel: str | None = None
) -> None:
    """Apply standard styling to cumulative probability axes."""
    ax.set_xlabel("Movement Magnitude Threshold x (%)", fontsize=10)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=11)
    ax.set_xlim(0, xmax)
    ax.set_ylim(0, 1.02)
    ax.set_xticks(np.arange(0, xmax + 0.5, 0.5))
    ax.set_yticks(np.arange(0, 1.1, 0.1))
    ax.grid(True, linestyle=":", alpha=0.6)


# --- Plotting Functions ---


def plot_variance_comparison(returns_df: pd.DataFrame, figures_dir: Path) -> Path:
    """Generate 3-panel figure: side-by-side bucket histograms (top) and overlaid distribution (bottom)."""
    fig, axd = plt.subplot_mosaic(
        [["SP500", "STOXX600"], ["overlaid", "overlaid"]],
        figsize=(14, 9.5),
        layout="constrained",
    )

    # Top panels: side-by-side histograms
    for label, (sym, span, width) in CONFIGS.items():
        ax = axd[sym]
        data = get_pct_returns(returns_df, sym)
        edges = np.arange(-span, span + width, width)
        clipped = np.clip(data, edges[0], edges[-1])
        ax.hist(
            clipped,
            bins=edges,
            weights=np.ones(len(clipped)) / len(clipped) * 100,
            color=COLORS[sym],
            edgecolor="black",
            linewidth=0.5,
            rwidth=0.85,
        )
        ax.set_title(
            f"{label} (Daily Std: {data.std():.2f}%)\nBucket Size: {width:.2f}%",
            fontsize=11,
            fontweight="bold",
        )
        ax.set_xlabel(f"Daily Return Bucket (Width: {width:.2f}%)", fontsize=10)
        ax.set_ylabel("Percentage of Days (%)", fontsize=10)
        ax.grid(True, axis="y", linestyle=":", alpha=0.7)

    # Bottom panel: overlaid frequency step comparison
    ax_bottom = axd["overlaid"]
    edges_overlay = np.arange(-5.0, 5.25, 0.25)
    for label, (sym, _, _) in CONFIGS.items():
        data = get_pct_returns(returns_df, sym)
        counts, _ = np.histogram(
            np.clip(data, edges_overlay[0], edges_overlay[-1]), bins=edges_overlay
        )
        ax_bottom.step(
            edges_overlay[:-1],
            counts / len(data) * 100,
            where="post",
            linewidth=2.0,
            color=COLORS[sym],
            label=f"{label} (Daily Std: {data.std():.2f}%)",
        )

    ax_bottom.set_title(
        "Overlaid Discretized Daily Return Distributions (Bucket Size: 0.25%)",
        fontsize=12,
        fontweight="bold",
    )
    ax_bottom.set_xlabel("Daily Return Bucket (Width: 0.25%)", fontsize=10)
    ax_bottom.set_ylabel("Percentage of Days (%)", fontsize=10)
    ax_bottom.set_xlim(-5.0, 5.0)
    ax_bottom.set_xticks(np.arange(-5.0, 5.5, 1.0))
    ax_bottom.grid(True, linestyle=":", alpha=0.6)
    ax_bottom.legend(frameon=True)

    fig.suptitle(
        "10-Year Daily Return Distributions: S&P 500 vs. STOXX Europe 600",
        fontsize=14,
        fontweight="bold",
    )
    return save_and_close(fig, figures_dir / "daily_returns_variance_comparison.png")


def plot_cumulative_movement(returns_df: pd.DataFrame, figures_dir: Path) -> Path:
    """Generate 3-panel figure: absolute movement ECDF (top) and conditional negative/positive ECDFs (bottom)."""
    fig, axd = plt.subplot_mosaic(
        [["abs", "abs"], ["SP500", "STOXX600"]],
        figsize=(14, 9.5),
        layout="constrained",
    )
    edges = np.arange(0.0, 6.10, 0.10)

    # Top panel: Cumulative probability of daily absolute movement P(|Return| <= x)
    ax_abs = axd["abs"]
    for label, (sym, _, _) in CONFIGS.items():
        abs_data = np.abs(get_pct_returns(returns_df, sym))
        x_vals, y_vals = compute_ecdf(abs_data, edges)
        p1, p2 = (abs_data <= 1.0).mean() * 100, (abs_data <= 2.0).mean() * 100
        ax_abs.step(
            x_vals,
            y_vals,
            where="post",
            linewidth=2.2,
            color=COLORS[sym],
            label=f"{label} (P(|R| ≤ 1%): {p1:.1f}%, P(|R| ≤ 2%): {p2:.1f}%)",
        )
        ax_abs.fill_between(x_vals, y_vals, step="post", alpha=0.10, color=COLORS[sym])

    ax_abs.set_title(
        "Cumulative Probability of Daily Absolute Movement P(|Return| ≤ x)",
        fontsize=12,
        fontweight="bold",
    )
    format_cumulative_axis(ax_abs, xmax=6.0, ylabel="Cumulative Probability P(|R| ≤ x)")
    ax_abs.legend(frameon=True, fontsize=9.5, loc="lower right")

    # Bottom panels: Conditional negative vs. positive daily movements
    for label, (sym, _, _) in CONFIGS.items():
        ax = axd[sym]
        data = get_pct_returns(returns_df, sym)
        neg, pos = np.abs(data[data <= 0]), data[data >= 0]
        x, y_neg = compute_ecdf(neg, edges)
        _, y_pos = compute_ecdf(pos, edges)
        p_neg, p_pos = (neg <= 1.0).mean() * 100, (pos <= 1.0).mean() * 100

        ax.step(
            x,
            y_neg,
            where="post",
            color="#d62728",
            linewidth=2.2,
            linestyle="--",
            label=f"Negative (Down {len(neg) / len(data) * 100:.1f}%)\n  P(|R|≤1%): {p_neg:.1f}%",
        )
        ax.step(
            x,
            y_pos,
            where="post",
            color="#2ca02c",
            linewidth=2.2,
            linestyle="-",
            label=f"Positive (Up {len(pos) / len(data) * 100:.1f}%)\n  P(R≤1%): {p_pos:.1f}%",
        )
        ax.fill_between(
            x,
            y_neg,
            y_pos,
            step="post",
            alpha=0.15,
            color="#9467bd",
            label="Diff (Asymmetry)",
        )
        ax.set_title(label, fontsize=11, fontweight="bold")
        format_cumulative_axis(
            ax, xmax=6.0, ylabel="Cumulative Probability" if sym == "SP500" else None
        )
        ax.legend(frameon=True, fontsize=9.0, loc="lower right")

    fig.suptitle(
        "Cumulative Daily Movement Probabilities: Absolute and Conditional Asymmetry",
        fontsize=14,
        fontweight="bold",
    )
    return save_and_close(
        fig, figures_dir / "daily_returns_cumulative_probabilities.png"
    )


def main() -> None:
    data_dir = PROJECT_ROOT / "data"
    figures_dir = PROJECT_ROOT / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading daily return data from {data_dir}...")
    returns_df = load_daily_returns(data_dir)

    print("Generating daily return distribution figures...")
    plot_variance_comparison(returns_df, figures_dir)
    plot_cumulative_movement(returns_df, figures_dir)


if __name__ == "__main__":
    main()
