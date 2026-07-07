import matplotlib

matplotlib.use("Agg")  # Use non-interactive backend for headless environments

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

from benchmark.core.specification import BenchmarkResult, MetricType
from benchmark.scoring.engine import ScoringReport

# Modern color palette for databases
COLOR_PALETTE = [
    "#3b82f6",  # Blue
    "#10b981",  # Emerald
    "#f59e0b",  # Amber
    "#8b5cf6",  # Violet
    "#ec4899",  # Pink
    "#ef4444",  # Red
    "#06b6d4",  # Cyan
    "#f97316",  # Orange
]


# Consistent mapping of database names to colors
def get_db_colors(databases: list[str]) -> dict[str, str]:
    return {db: COLOR_PALETTE[i % len(COLOR_PALETTE)] for i, db in enumerate(sorted(databases))}


# Latency metric mappings to clean labels
LATENCY_METRICS_MAP = {
    MetricType.AVERAGE_LATENCY_MS: "Mean",
    MetricType.AVERAGE_BATCH_LATENCY_MS: "Mean",
    MetricType.WRITE_LATENCY_MEAN: "Mean",
    MetricType.READ_LATENCY_MEAN: "Mean",
    MetricType.P50_LATENCY_MS: "P50",
    MetricType.P50_BATCH_LATENCY_MS: "P50",
    MetricType.P95_LATENCY_MS: "P95",
    MetricType.P95_BATCH_LATENCY_MS: "P95",
    MetricType.WRITE_LATENCY_P95: "P95",
    MetricType.READ_LATENCY_P95: "P95",
    MetricType.P99_LATENCY_MS: "P99",
    MetricType.P99_BATCH_LATENCY_MS: "P99",
    MetricType.WRITE_LATENCY_P99: "P99",
    MetricType.READ_LATENCY_P99: "P99",
    MetricType.JOIN_LATENCY_MS: "Join Latency",
    MetricType.MERGE_DURATION_MS: "Merge Duration",
}


def apply_premium_style(ax: Any, title: str, xlabel: str = "", ylabel: str = "") -> None:
    """Applies a premium, modern design style to matplotlib charts."""
    ax.set_title(title, fontsize=12, fontweight="bold", pad=15, color="#1e293b")
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=10, fontweight="semibold", color="#475569", labelpad=8)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=10, fontweight="semibold", color="#475569", labelpad=8)

    # Soft gridlines
    ax.grid(True, linestyle="--", alpha=0.5, color="#cbd5e1")
    ax.set_axisbelow(True)

    # Hide top and right spines for a clean flat look
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    for spine in ["left", "bottom"]:
        ax.spines[spine].set_color("#94a3b8")
        ax.spines[spine].set_linewidth(1.0)

    ax.tick_params(colors="#475569", labelsize=9)


def draw_placeholder(filename: Path, title: str, message: str = "No Data Available") -> None:
    """Draws a clean, styled placeholder image when no data exists for a chart."""
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.text(
        0.5, 0.5, message, ha="center", va="center", fontsize=12, color="#64748b", weight="semibold"
    )
    ax.set_title(title, fontsize=12, fontweight="bold", color="#1e293b", pad=15)

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # Save with border
    fig.patch.set_edgecolor("#e2e8f0")
    fig.patch.set_linewidth(1)

    fig.tight_layout()
    fig.savefig(filename, dpi=150, bbox_inches="tight")
    plt.close(fig)


def generate_overall_score_chart(
    score_report: ScoringReport | None, output_path: Path, db_colors: dict[str, str]
) -> None:
    """Generates a horizontal bar chart of the overall scores."""
    if not score_report or not score_report.database_scores:
        draw_placeholder(output_path, "Overall Performance Scores", "No score data available")
        return

    scores = score_report.database_scores
    # Sort ascending for horizontal bar chart so that highest is at the top
    scores = sorted(scores, key=lambda x: x.overall_score)

    dbs = [s.database for s in scores]
    vals = [s.overall_score for s in scores]
    colors = [db_colors.get(db, "#3b82f6") for db in dbs]

    fig, ax = plt.subplots(figsize=(8, max(4, len(dbs) * 0.8)))
    bars = ax.barh(dbs, vals, color=colors, height=0.55, edgecolor="none")

    # Note: 'left', 'right', 'top', 'bottom' variables passed in custom config can be strings
    ax.set_title(
        "Overall Database Score (Higher is Better)",
        fontsize=12,
        fontweight="bold",
        pad=15,
        color="#1e293b",
    )
    ax.set_xlabel(
        "Weighted Score (0 - 100)", fontsize=10, fontweight="semibold", color="#475569", labelpad=8
    )
    ax.grid(True, linestyle="--", alpha=0.5, color="#cbd5e1")
    ax.set_axisbelow(True)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    for spine in ["left", "bottom"]:
        ax.spines[spine].set_color("#94a3b8")
        ax.spines[spine].set_linewidth(1.0)
    ax.tick_params(colors="#475569", labelsize=9)

    ax.set_xlim(0, 105)

    for bar in bars:
        width = bar.get_width()
        ax.annotate(
            f"{width:.1f}",
            xy=(width, bar.get_y() + bar.get_height() / 2),
            xytext=(6, 0),
            textcoords="offset points",
            ha="left",
            va="center",
            fontsize=9,
            fontweight="bold",
            color="#334155",
        )

    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def generate_radar_chart(
    score_report: ScoringReport | None, output_path: Path, db_colors: dict[str, str]
) -> None:
    """Generates a polar radar chart comparing database dimension scores."""
    if not score_report or not score_report.database_scores:
        draw_placeholder(
            output_path, "Performance Dimensions Comparison", "No scoring data available"
        )
        return

    # Extract scenarios evaluated
    scenarios = [s.scenario for s in score_report.database_scores[0].scenario_scores]
    if not scenarios:
        draw_placeholder(
            output_path, "Performance Dimensions Comparison", "No scenario data available"
        )
        return

    num_vars = len(scenarios)
    labels = list(scenarios)

    # Pad to 3 axes if there are fewer than 3 scenarios (polar plots require at least 3)
    if num_vars < 3:
        for i in range(3 - num_vars):
            labels.append(f"Dimension {i + 1}")
        num_vars = 3

    angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
    angles += angles[:1]  # Close the loop

    fig, ax_polar = plt.subplots(figsize=(8, 8), subplot_kw={"polar": True})
    ax: Any = ax_polar
    ax.set_theta_offset(np.pi / 2)  # top
    ax.set_theta_direction(-1)  # clockwise

    plt.xticks(angles[:-1], labels, color="#334155", size=9, fontweight="semibold")

    ax.set_rlabel_position(180 / num_vars)
    plt.yticks([20, 40, 60, 80, 100], ["20", "40", "60", "80", "100"], color="#64748b", size=8)
    plt.ylim(0, 100)

    for db_score in score_report.database_scores:
        db_name = db_score.database
        scores_dict = {s.scenario: s.normalized_score for s in db_score.scenario_scores}

        values = [scores_dict.get(label, 0.0) for label in labels]
        values += values[:1]  # Close the loop

        color = db_colors.get(db_name, "#3b82f6")
        ax.plot(angles, values, linewidth=2, linestyle="solid", label=db_name, color=color)
        ax.fill(angles, values, color=color, alpha=0.12)

    ax.legend(
        loc="upper right",
        bbox_to_anchor=(1.15, 1.05),
        frameon=True,
        facecolor="#f8fafc",
        edgecolor="#e2e8f0",
    )
    ax.set_title(
        "Performance Dimensions (Normalized, Higher is Better)",
        fontsize=12,
        fontweight="bold",
        pad=20,
        color="#1e293b",
    )

    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def generate_throughput_chart(
    suite_results: list[BenchmarkResult], output_path: Path, db_colors: dict[str, str]
) -> None:
    """Generates bar charts comparing read/write/replay throughput across databases."""
    throughput_scenarios: dict[str, dict[str, Any]] = {}

    tp_types = {
        MetricType.ROWS_PER_SECOND,
        MetricType.WRITE_THROUGHPUT,
        MetricType.READ_THROUGHPUT,
        MetricType.REPLAY_THROUGHPUT_ROWS_PER_SECOND,
    }

    for r in suite_results:
        if not r.success:
            continue
        for m in r.metrics:
            if m.metric_type in tp_types:
                if r.scenario_name not in throughput_scenarios:
                    throughput_scenarios[r.scenario_name] = {"unit": m.unit.value, "data": {}}
                throughput_scenarios[r.scenario_name]["data"][r.database_name] = m.value

    if not throughput_scenarios:
        draw_placeholder(output_path, "Throughput Comparison", "No throughput metrics recorded")
        return

    n_scens = len(throughput_scenarios)
    fig, axes = plt.subplots(n_scens, 1, figsize=(8.5, 4.5 * n_scens), squeeze=False)

    for idx, (scen_name, info) in enumerate(throughput_scenarios.items()):
        ax = axes[idx, 0]
        data = info["data"]
        unit = info["unit"]

        dbs = sorted(data.keys())
        vals = [data[db] for db in dbs]
        colors = [db_colors.get(db, "#3b82f6") for db in dbs]

        x = np.arange(len(dbs))
        bars = ax.bar(x, vals, color=colors, width=0.45, edgecolor="none")

        ax.set_title(
            f"Throughput: {scen_name}", fontsize=12, fontweight="bold", pad=15, color="#1e293b"
        )
        ax.set_ylabel(
            f"Throughput ({unit})", fontsize=10, fontweight="semibold", color="#475569", labelpad=8
        )
        ax.grid(True, linestyle="--", alpha=0.5, color="#cbd5e1")
        ax.set_axisbelow(True)
        for spine in ["top", "right"]:
            ax.spines[spine].set_visible(False)
        for spine in ["left", "bottom"]:
            ax.spines[spine].set_color("#94a3b8")
            ax.spines[spine].set_linewidth(1.0)
        ax.tick_params(colors="#475569", labelsize=9)

        ax.set_xticks(x)
        ax.set_xticklabels(dbs, rotation=15, ha="right")

        for bar in bars:
            height = bar.get_height()
            val_str = f"{height:,.0f}" if height >= 100 else f"{height:.2f}"
            ax.annotate(
                val_str,
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=8.5,
                fontweight="bold",
                color="#334155",
            )

    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def generate_latency_chart(
    suite_results: list[BenchmarkResult], output_path: Path, _db_colors: dict[str, str]
) -> None:
    """Generates grouped bar charts comparing mean/p95/p99 latency dimensions."""
    latency_scenarios: dict[str, dict[str, Any]] = {}

    for r in suite_results:
        if not r.success:
            continue

        for m in r.metrics:
            metric_label = LATENCY_METRICS_MAP.get(m.metric_type)
            if metric_label:
                if r.scenario_name not in latency_scenarios:
                    latency_scenarios[r.scenario_name] = {"unit": m.unit.value, "data": {}}
                scen_data = latency_scenarios[r.scenario_name]["data"]
                if r.database_name not in scen_data:
                    scen_data[r.database_name] = {}
                scen_data[r.database_name][metric_label] = m.value

    if not latency_scenarios:
        draw_placeholder(output_path, "Latency Comparison", "No latency metrics recorded")
        return

    n_scens = len(latency_scenarios)
    fig, axes = plt.subplots(n_scens, 1, figsize=(9.5, 5 * n_scens), squeeze=False)

    metric_colors = {
        "Mean": "#3b82f6",
        "P50": "#06b6d4",
        "P95": "#f59e0b",
        "P99": "#ef4444",
        "Join Latency": "#8b5cf6",
        "Merge Duration": "#ec4899",
    }

    for idx, (scen_name, info) in enumerate(latency_scenarios.items()):
        ax = axes[idx, 0]
        data = info["data"]
        unit = info["unit"]

        dbs = sorted(data.keys())
        all_labels = set()
        for db_vals in data.values():
            all_labels.update(db_vals.keys())

        label_order = ["Mean", "P50", "P95", "P99", "Join Latency", "Merge Duration"]
        sorted_labels = [lbl for lbl in label_order if lbl in all_labels]
        for lbl in sorted(all_labels):
            if lbl not in sorted_labels:
                sorted_labels.append(lbl)

        n_dbs = len(dbs)
        n_labels = len(sorted_labels)

        x = np.arange(n_dbs)
        total_width = 0.7
        width = total_width / max(1, n_labels)

        for l_idx, label in enumerate(sorted_labels):
            vals = [data[db].get(label, 0.0) for db in dbs]
            offset = (l_idx - (n_labels - 1) / 2) * width
            color = metric_colors.get(label, COLOR_PALETTE[l_idx % len(COLOR_PALETTE)])

            bars = ax.bar(x + offset, vals, width, label=label, color=color, edgecolor="none")

            for bar in bars:
                height = bar.get_height()
                if height > 0:
                    val_str = f"{height:.1f}" if height >= 1 else f"{height:.3f}"
                    ax.annotate(
                        val_str,
                        xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 2),
                        textcoords="offset points",
                        ha="center",
                        va="bottom",
                        fontsize=7.5,
                        color="#475569",
                    )

        ax.set_title(
            f"Latency: {scen_name} (Lower is Better)",
            fontsize=12,
            fontweight="bold",
            pad=15,
            color="#1e293b",
        )
        ax.set_ylabel(
            f"Latency ({unit})", fontsize=10, fontweight="semibold", color="#475569", labelpad=8
        )
        ax.grid(True, linestyle="--", alpha=0.5, color="#cbd5e1")
        ax.set_axisbelow(True)
        for spine in ["top", "right"]:
            ax.spines[spine].set_visible(False)
        for spine in ["left", "bottom"]:
            ax.spines[spine].set_color("#94a3b8")
            ax.spines[spine].set_linewidth(1.0)
        ax.tick_params(colors="#475569", labelsize=9)

        ax.set_xticks(x)
        ax.set_xticklabels(dbs, rotation=15, ha="right")
        ax.legend(frameon=True, facecolor="#f8fafc", edgecolor="#cbd5e1", fontsize=8.5)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def generate_compression_chart(
    suite_results: list[BenchmarkResult], output_path: Path, db_colors: dict[str, str]
) -> None:
    """Generates charts comparing compression ratio and savings percentage."""
    comp_ratio = {}
    comp_pct = {}

    for r in suite_results:
        if not r.success:
            continue
        for m in r.metrics:
            if m.metric_type == MetricType.COMPRESSION_RATIO:
                if m.value is not None:
                    comp_ratio[r.database_name] = m.value
            elif m.metric_type == MetricType.COMPRESSION_PERCENTAGE:
                if m.value is not None:
                    comp_pct[r.database_name] = m.value

    if not comp_ratio and not comp_pct:
        draw_placeholder(output_path, "Compression Efficiency", "No compression metrics recorded")
        return

    dbs = sorted(set(comp_ratio.keys()) | set(comp_pct.keys()))
    colors = [db_colors.get(db, "#3b82f6") for db in dbs]

    has_ratio = len(comp_ratio) > 0
    has_pct = len(comp_pct) > 0

    if has_ratio and has_pct:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    else:
        fig, ax1 = plt.subplots(1, 1, figsize=(7, 5))
        ax2 = None

    x = np.arange(len(dbs))

    if has_ratio:
        vals = [comp_ratio.get(db, 0.0) for db in dbs]
        bars1 = ax1.bar(x, vals, color=colors, width=0.45, edgecolor="none")
        ax1.set_title(
            "Compression Ratio (Higher is Better)",
            fontsize=12,
            fontweight="bold",
            pad=15,
            color="#1e293b",
        )
        ax1.set_ylabel("Ratio (x)", fontsize=10, fontweight="semibold", color="#475569", labelpad=8)
        ax1.grid(True, linestyle="--", alpha=0.5, color="#cbd5e1")
        ax1.set_axisbelow(True)
        for spine in ["top", "right"]:
            ax1.spines[spine].set_visible(False)
        for spine in ["left", "bottom"]:
            ax1.spines[spine].set_color("#94a3b8")
            ax1.spines[spine].set_linewidth(1.0)
        ax1.tick_params(colors="#475569", labelsize=9)

        ax1.set_xticks(x)
        ax1.set_xticklabels(dbs, rotation=15, ha="right")
        for bar in bars1:
            h = bar.get_height()
            if h > 0:
                ax1.annotate(
                    f"{h:.2f}x",
                    xy=(bar.get_x() + bar.get_width() / 2, h),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    fontsize=8.5,
                    fontweight="bold",
                    color="#334155",
                )

    if ax2 and has_pct:
        vals = [comp_pct.get(db, 0.0) for db in dbs]
        bars2 = ax2.bar(x, vals, color=colors, width=0.45, edgecolor="none")
        ax2.set_title(
            "Space Saved (Higher is Better)",
            fontsize=12,
            fontweight="bold",
            pad=15,
            color="#1e293b",
        )
        ax2.set_ylabel(
            "Percentage (%)", fontsize=10, fontweight="semibold", color="#475569", labelpad=8
        )
        ax2.grid(True, linestyle="--", alpha=0.5, color="#cbd5e1")
        ax2.set_axisbelow(True)
        for spine in ["top", "right"]:
            ax2.spines[spine].set_visible(False)
        for spine in ["left", "bottom"]:
            ax2.spines[spine].set_color("#94a3b8")
            ax2.spines[spine].set_linewidth(1.0)
        ax2.tick_params(colors="#475569", labelsize=9)

        ax2.set_xticks(x)
        ax2.set_xticklabels(dbs, rotation=15, ha="right")
        ax2.set_ylim(0, 105)
        for bar in bars2:
            h = bar.get_height()
            if h > 0:
                ax2.annotate(
                    f"{h:.1f}%",
                    xy=(bar.get_x() + bar.get_width() / 2, h),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    fontsize=8.5,
                    fontweight="bold",
                    color="#334155",
                )

    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def generate_storage_footprint_chart(
    suite_results: list[BenchmarkResult], output_path: Path, db_colors: dict[str, str]
) -> None:
    """Generates a bar chart comparing final physical storage footprints."""
    storage_data = {}

    for r in suite_results:
        if not r.success:
            continue
        for m in r.metrics:
            if m.metric_type == MetricType.PHYSICAL_STORAGE_SIZE_BYTES:
                if m.value is not None:
                    storage_data[r.database_name] = m.value

    if not storage_data:
        draw_placeholder(output_path, "Storage Footprint", "No storage footprint metrics recorded")
        return

    dbs = sorted(storage_data.keys())
    raw_vals = [storage_data[db] for db in dbs]
    colors = [db_colors.get(db, "#3b82f6") for db in dbs]

    max_bytes = max(raw_vals)
    if max_bytes >= 1e9:
        unit = "GB"
        factor = 1e9
    elif max_bytes >= 1e6:
        unit = "MB"
        factor = 1e6
    elif max_bytes >= 1e3:
        unit = "KB"
        factor = 1e3
    else:
        unit = "Bytes"
        factor = 1

    vals = [val / factor for val in raw_vals]

    fig, ax = plt.subplots(figsize=(7, 5))
    x = np.arange(len(dbs))
    bars = ax.bar(x, vals, color=colors, width=0.45, edgecolor="none")

    ax.set_title(
        "Physical Storage Size (Lower is Better)",
        fontsize=12,
        fontweight="bold",
        pad=15,
        color="#1e293b",
    )
    ax.set_ylabel(f"Size ({unit})", fontsize=10, fontweight="semibold", color="#475569", labelpad=8)
    ax.grid(True, linestyle="--", alpha=0.5, color="#cbd5e1")
    ax.set_axisbelow(True)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    for spine in ["left", "bottom"]:
        ax.spines[spine].set_color("#94a3b8")
        ax.spines[spine].set_linewidth(1.0)
    ax.tick_params(colors="#475569", labelsize=9)

    ax.set_xticks(x)
    ax.set_xticklabels(dbs, rotation=15, ha="right")

    for bar in bars:
        h = bar.get_height()
        if h > 0:
            val_str = f"{h:.1f}" if h >= 1 else f"{h:.3f}"
            ax.annotate(
                f"{val_str} {unit}",
                xy=(bar.get_x() + bar.get_width() / 2, h),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=8.5,
                fontweight="bold",
                color="#334155",
            )

    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def generate_all_charts(
    suite_results: list[BenchmarkResult],
    score_report: ScoringReport | None,
    charts_dir: Path,
    run_prefix: str,
) -> dict[str, Path]:
    """Generates all 6 required benchmark charts and saves them to the target directory."""
    charts_dir.mkdir(parents=True, exist_ok=True)

    # 1. Determine unique databases in the results to assign consistent colors
    dbs = set()
    for r in suite_results:
        dbs.add(r.database_name)
    if score_report:
        for ds in score_report.database_scores:
            dbs.add(ds.database)

    db_colors = get_db_colors(list(dbs))

    # 2. Define target chart paths
    chart_paths = {
        "overall_score": charts_dir / f"{run_prefix}_overall_score.png",
        "radar": charts_dir / f"{run_prefix}_radar_chart.png",
        "throughput": charts_dir / f"{run_prefix}_throughput.png",
        "latency": charts_dir / f"{run_prefix}_latency.png",
        "compression": charts_dir / f"{run_prefix}_compression.png",
        "storage_footprint": charts_dir / f"{run_prefix}_storage_footprint.png",
    }

    # 3. Generate each chart
    generate_overall_score_chart(score_report, chart_paths["overall_score"], db_colors)
    generate_radar_chart(score_report, chart_paths["radar"], db_colors)
    generate_throughput_chart(suite_results, chart_paths["throughput"], db_colors)
    generate_latency_chart(suite_results, chart_paths["latency"], db_colors)
    generate_compression_chart(suite_results, chart_paths["compression"], db_colors)
    generate_storage_footprint_chart(suite_results, chart_paths["storage_footprint"], db_colors)

    return chart_paths
