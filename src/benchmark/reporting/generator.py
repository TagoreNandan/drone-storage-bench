import json
from pathlib import Path
from typing import Any

from benchmark.core.specification import BenchmarkResult


class ReportGenerator:
    """Generates artifacts, reports, and formatted tables from benchmark runs.

    Supports exporting to JSON, CSV, and summary Markdown for performance reports.
    """

    def __init__(self, results_dir: Path) -> None:
        """Initialize with target results storage directory."""
        self.results_dir = results_dir

    def generate_json_results(
        self,
        suite_results: list[BenchmarkResult],
        filename: str,
        score_report: Any = None,
    ) -> Path:
        """Saves raw benchmark execution metadata and stats to a JSON file.

        Args:
            suite_results: List of compiled BenchmarkResult objects.
            filename: Target output filename.
            score_report: Optional ScoringReport containing comparative scores.

        Returns:
            Path to the written JSON artifact.
        """
        raw_dir = self.results_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        output_path = raw_dir / filename

        # Dump results model data to JSON
        serializable_results = [result.model_dump(mode="json") for result in suite_results]
        data = {
            "run_timestamp": serializable_results[0]["started_at"] if serializable_results else "",
            "results": serializable_results,
        }
        if score_report is not None:
            data["score_report"] = score_report.model_dump(mode="json")

        with output_path.open("w") as f:
            json.dump(data, f, indent=2)

        return output_path

    def generate_markdown_summary(
        self,
        suite_results: list[BenchmarkResult],
        filename: str,
        score_report: Any = None,
    ) -> Path:
        """Generates a high-level Markdown report comparing the databases.

        Args:
            suite_results: List of compiled BenchmarkResult objects.
            filename: Target output filename.
            score_report: Optional ScoringReport containing comparative scores.

        Returns:
            Path to the written Markdown file.
        """
        reports_dir = self.results_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        output_path = reports_dir / filename

        # Compile comparative Markdown table
        lines = [
            "# Drone Storage Bench - Evaluation Report",
            "",
            "Comparative summary of time-series database benchmark workloads.",
            "",
            (
                "| Database | Scenario | Scenario Type | Success | Duration (s) | "
                "Error Details / Metrics Summary |"
            ),
            "| --- | --- | --- | --- | --- | --- |",
        ]

        for r in suite_results:
            duration = (r.completed_at - r.started_at).total_seconds()
            success_str = "✅ YES" if r.success else "❌ NO"

            # Summarize metrics or errors
            if r.success:
                metrics_summary = ", ".join(
                    [f"{m.metric_type.value}: {m.value} {m.unit.value}" for m in r.metrics]
                )
                details = metrics_summary if metrics_summary else "Completed (No metrics recorded)"
            else:
                details = f"Error: {r.error_message}"

            lines.append(
                f"| {r.database_name} | {r.scenario_name} | {r.scenario_type.value} | "
                f"{success_str} | {duration:.2f} | {details} |"
            )

        if score_report is not None:
            lines.extend(
                [
                    "",
                    "## Performance Rankings and Scores",
                    "",
                    (
                        "| Rank | Database | Overall Score | "
                        "Scenario Scores (Scenario: Raw -> Weighted) |"
                    ),
                    "| --- | --- | --- | --- |",
                ]
            )
            for db_score in score_report.database_scores:
                score_details = []
                for s in db_score.scenario_scores:
                    raw_val_str = f"{s.raw_value:.2f}" if s.raw_value is not None else "N/A"
                    score_details.append(f"{s.scenario}: {raw_val_str} -> {s.weighted_score:.2f}")
                score_details_str = ", ".join(score_details)
                lines.append(
                    f"| {db_score.rank} | {db_score.database} | "
                    f"{db_score.overall_score:.2f} | {score_details_str} |"
                )

        with output_path.open("w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        return output_path

    def generate_html_summary(
        self,
        suite_results: list[BenchmarkResult],
        filename: str,
        score_report: Any = None,
    ) -> Path:
        """Generates a professional, responsive HTML summary report comparing the databases."""
        from datetime import datetime

        reports_dir = self.results_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        output_path = reports_dir / filename

        run_prefix = Path(filename).stem

        # 1. Parse Title and Timestamp
        suite_name_raw = filename.split("_202")[0] if "_202" in filename else run_prefix
        suite_name = suite_name_raw.replace("-", " ").replace("_", " ").title()
        timestamp = datetime.now().strftime("%B %d, %Y - %H:%M:%S UTC")

        db_names = sorted({r.database_name for r in suite_results})
        total_scenarios = len({r.scenario_name for r in suite_results})
        success_count = sum(1 for r in suite_results if r.success)
        total_runs = len(suite_results)

        # 2. Metadata cards HTML
        metadata_html = f"""
        <div class="meta-card">
          <div class="meta-icon">📋</div>
          <div class="meta-content">
            <span class="meta-label">Suite Name</span>
            <span class="meta-value">{suite_name}</span>
          </div>
        </div>
        <div class="meta-card">
          <div class="meta-icon">⚡</div>
          <div class="meta-content">
            <span class="meta-label">Databases Tested</span>
            <span class="meta-value">{", ".join(db_names) if db_names else "None"}</span>
          </div>
        </div>
        <div class="meta-card">
          <div class="meta-icon">📈</div>
          <div class="meta-content">
            <span class="meta-label">Workload Scenarios</span>
            <span class="meta-value">{total_scenarios}</span>
          </div>
        </div>
        <div class="meta-card">
          <div class="meta-icon">🛡️</div>
          <div class="meta-content">
            <span class="meta-label">Execution Success</span>
            <span class="meta-value">{success_count} / {total_runs} Passed</span>
          </div>
        </div>
        """

        # 3. Rankings Section HTML
        rankings_html = []
        if score_report and score_report.database_scores:
            for db_score in score_report.database_scores:
                rank = db_score.rank
                badge_cls = f"rank-{rank}" if rank <= 3 else "rank-other"

                # Detailed progress bars for scenario scores
                scores_list = []
                for s in db_score.scenario_scores:
                    raw_val = f"{s.raw_value:,.2f}" if s.raw_value is not None else "N/A"
                    norm_score = s.normalized_score
                    scores_list.append(
                        f'<div class="progress-container">'
                        f'  <div class="progress-labels">'
                        f'    <span class="progress-scen">{s.scenario}</span>'
                        f'    <span class="progress-val">{raw_val} ({norm_score:.1f}%)</span>'
                        f'  </div>'
                        f'  <div class="progress-bar-track">'
                        f'    <div class="progress-bar-fill" style="width: {norm_score}%"></div>'
                        f'  </div>'
                        f'</div>'
                    )
                scores_html = "\n".join(scores_list)

                # Assign ranking trophy/medal icon
                rank_icon = "🥇" if rank == 1 else ("🥈" if rank == 2 else ("🥉" if rank == 3 else "🏅"))

                rankings_html.append(
                    f'<div class="rank-card {badge_cls}">'
                    f'  <div class="rank-card-header">'
                    f'    <div class="rank-trophy">{rank_icon}</div>'
                    f'    <div class="rank-db-details">'
                    f'      <h3 class="rank-db-title">{db_score.database}</h3>'
                    f'      <span class="rank-lbl">Rank {rank}</span>'
                    f'    </div>'
                    f'    <div class="rank-overall-score">'
                    f'      <span class="score-num">{db_score.overall_score:.1f}</span>'
                    f'      <span class="score-lbl">Index</span>'
                    f'    </div>'
                    f'  </div>'
                    f'  <div class="rank-card-body">'
                    f'    {scores_html}'
                    f'  </div>'
                    f'</div>'
                )
            rankings_section = f"""
            <div class="section-card">
              <h2 class="section-title">🏆 Performance Rankings and Index Scores</h2>
              <div class="rankings-grid">
                {"\n".join(rankings_html)}
              </div>
            </div>
            """
        else:
            rankings_section = ""

        # 4. Workload Tabs HTML
        scenarios_dict = {}
        for r in suite_results:
            if r.scenario_name not in scenarios_dict:
                scenarios_dict[r.scenario_name] = []
            scenarios_dict[r.scenario_name].append(r)

        tab_buttons = []
        tab_panes = []

        for idx, (scen_name, results_list) in enumerate(scenarios_dict.items()):
            active_btn_cls = "active" if idx == 0 else ""
            active_pane_cls = "active" if idx == 0 else ""
            tab_id = f"tab-{idx}"

            tab_buttons.append(
                f'<button class="tab-btn {active_btn_cls}" onclick="switchTab(event, \'{tab_id}\')">{scen_name}</button>'
            )

            rows_html = []
            for res in results_list:
                duration = (res.completed_at - res.started_at).total_seconds()
                status_html = (
                    '<span class="status-badge success"><span class="badge-dot"></span>Success</span>'
                    if res.success else
                    f'<span class="status-badge failure"><span class="badge-dot"></span>Failed</span>'
                )

                # Generate metrics output
                metrics_list = []
                if res.success:
                    for m in res.metrics:
                        metrics_list.append(
                            f'<div class="metric-card-pill">'
                            f'  <span class="metric-card-label">{m.metric_type.value}</span>'
                            f'  <span class="metric-card-value">{m.value:,.2f} <span class="metric-unit">{m.unit.value}</span></span>'
                            f'</div>'
                        )
                    metrics_content = f'<div class="metrics-card-grid">{"".join(metrics_list)}</div>'
                else:
                    metrics_content = f'<div class="error-card-msg">Error: {res.error_message}</div>'

                rows_html.append(
                    f'<tr>'
                    f'  <td><span class="db-row-name">{res.database_name}</span></td>'
                    f'  <td>{status_html}</td>'
                    f'  <td>{duration:.2f}s</td>'
                    f'  <td>{metrics_content}</td>'
                    f'</tr>'
                )

            tab_panes.append(
                f'<div id="{tab_id}" class="tab-pane {active_pane_cls}">'
                f'  <div class="table-container">'
                f'    <table>'
                f'      <thead>'
                f'        <tr>'
                f'          <th>Database</th>'
                f'          <th>Status</th>'
                f'          <th>Execution Time</th>'
                f'          <th>Telemetry & Performance Metrics</th>'
                f'        </tr>'
                f'      </thead>'
                f'      <tbody>'
                f'        {"".join(rows_html)}'
                f'      </tbody>'
                f'    </table>'
                f'  </div>'
                f'</div>'
            )

        workloads_tabs_section = f"""
        <div class="section-card">
          <h2 class="section-title">📊 Detailed Workload Scenarios</h2>
          <div class="tabs-container">
            <div class="tabs-list">
              {"".join(tab_buttons)}
            </div>
            <div class="tabs-content">
              {"".join(tab_panes)}
            </div>
          </div>
        </div>
        """ if scenarios_dict else ""

        # 5. Visualizations Grid HTML
        visualizations_section = f"""
        <div class="section-card">
          <h2 class="section-title">🖼️ Performance Visualizations Gallery</h2>
          <p class="section-subtitle">Click any chart to zoom and inspect in detail.</p>
          <div class="charts-gallery">
            <div class="chart-gallery-item" onclick="openLightbox('../charts/{run_prefix}_overall_score.png', 'Overall Performance Scores')">
              <div class="chart-item-header">Overall Performance Index</div>
              <div class="chart-img-container">
                <img src="../charts/{run_prefix}_overall_score.png" alt="Overall Performance Score">
                <div class="zoom-overlay">🔍 Zoom Chart</div>
              </div>
            </div>
            <div class="chart-gallery-item" onclick="openLightbox('../charts/{run_prefix}_radar_chart.png', 'Multi-Dimensional Comparison')">
              <div class="chart-item-header">Performance Dimensions (Radar)</div>
              <div class="chart-img-container">
                <img src="../charts/{run_prefix}_radar_chart.png" alt="Radar Chart">
                <div class="zoom-overlay">🔍 Zoom Chart</div>
              </div>
            </div>
            <div class="chart-gallery-item" onclick="openLightbox('../charts/{run_prefix}_throughput.png', 'Throughput Performance')">
              <div class="chart-item-header">Write & Read Throughput</div>
              <div class="chart-img-container">
                <img src="../charts/{run_prefix}_throughput.png" alt="Throughput Chart">
                <div class="zoom-overlay">🔍 Zoom Chart</div>
              </div>
            </div>
            <div class="chart-gallery-item" onclick="openLightbox('../charts/{run_prefix}_latency.png', 'Latency Benchmarks')">
              <div class="chart-item-header">Average & Percentile Latencies</div>
              <div class="chart-img-container">
                <img src="../charts/{run_prefix}_latency.png" alt="Latency Chart">
                <div class="zoom-overlay">🔍 Zoom Chart</div>
              </div>
            </div>
            <div class="chart-gallery-item" onclick="openLightbox('../charts/{run_prefix}_compression.png', 'Compression Efficiencies')">
              <div class="chart-item-header">Compression Ratio & Savings</div>
              <div class="chart-img-container">
                <img src="../charts/{run_prefix}_compression.png" alt="Compression Chart">
                <div class="zoom-overlay">🔍 Zoom Chart</div>
              </div>
            </div>
            <div class="chart-gallery-item" onclick="openLightbox('../charts/{run_prefix}_storage_footprint.png', 'Physical Storage Footprints')">
              <div class="chart-item-header">Physical Disk Footprint</div>
              <div class="chart-img-container">
                <img src="../charts/{run_prefix}_storage_footprint.png" alt="Storage Footprint Chart">
                <div class="zoom-overlay">🔍 Zoom Chart</div>
              </div>
            </div>
          </div>
        </div>
        """

        # Complete HTML output compilation
        html_content = f"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Drone Storage Bench - Report</title>
  <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🚁</text></svg>">
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap');
    
    :root {{
      --bg-primary: #f8fafc;
      --bg-secondary: #ffffff;
      --bg-tertiary: #f1f5f9;
      --text-primary: #0f172a;
      --text-secondary: #475569;
      --text-muted: #64748b;
      --border-color: #e2e8f0;
      --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
      --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
      --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);
      --primary: #3b82f6;
      --primary-hover: #2563eb;
      --primary-glow: rgba(59, 130, 246, 0.08);
      --success: #10b981;
      --success-glow: rgba(16, 185, 129, 0.08);
      --danger: #ef4444;
      --danger-glow: rgba(239, 68, 68, 0.08);
      
      --accent-gold: #fbbf24;
      --accent-silver: #94a3b8;
      --accent-bronze: #ca8a04;
      --card-radius: 16px;
    }}
    
    [data-theme="dark"] {{
      --bg-primary: #090d16;
      --bg-secondary: #111827;
      --bg-tertiary: #1f2937;
      --text-primary: #f3f4f6;
      --text-secondary: #9ca3af;
      --text-muted: #6b7280;
      --border-color: #1f2937;
      --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.3);
      --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.3), 0 2px 4px -2px rgb(0 0 0 / 0.3);
      --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.4), 0 4px 6px -4px rgb(0 0 0 / 0.4);
      --primary: #60a5fa;
      --primary-hover: #3b82f6;
      --primary-glow: rgba(96, 165, 250, 0.08);
      --success: #34d399;
      --success-glow: rgba(52, 211, 153, 0.08);
      --danger: #f87171;
      --danger-glow: rgba(248, 113, 113, 0.08);
    }}
    
    body {{
      font-family: 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif;
      background-color: var(--bg-primary);
      color: var(--text-primary);
      margin: 0;
      padding: 0;
      transition: background-color 0.3s, color 0.3s;
      line-height: 1.6;
    }}
    
    .container {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 2rem 1.5rem;
    }}
    
    /* Header Section */
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 2.5rem;
      border-bottom: 1px solid var(--border-color);
      padding-bottom: 1.5rem;
      flex-wrap: wrap;
      gap: 1rem;
    }}
    
    .logo-title-group {{
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }}
    
    .logo-emoji {{
      font-size: 2.5rem;
    }}
    
    .title-area h1 {{
      margin: 0;
      font-size: 1.75rem;
      font-weight: 700;
      letter-spacing: -0.025em;
    }}
    
    .timestamp {{
      font-size: 0.875rem;
      color: var(--text-muted);
      margin-top: 0.25rem;
    }}
    
    /* Dark Mode Toggle Switch */
    .toggle-container {{
      display: flex;
      align-items: center;
      gap: 0.75rem;
      background: var(--bg-secondary);
      padding: 0.5rem 1rem;
      border-radius: 30px;
      border: 1px solid var(--border-color);
      box-shadow: var(--shadow-sm);
    }}
    
    .toggle-label {{
      font-size: 0.85rem;
      font-weight: 600;
      color: var(--text-secondary);
    }}
    
    .theme-switch {{
      position: relative;
      display: inline-block;
      width: 48px;
      height: 24px;
    }}
    
    .theme-switch input {{
      opacity: 0;
      width: 0;
      height: 0;
    }}
    
    .slider {{
      position: absolute;
      cursor: pointer;
      top: 0; left: 0; right: 0; bottom: 0;
      background-color: #cbd5e1;
      transition: .4s;
      border-radius: 34px;
    }}
    
    .slider:before {{
      position: absolute;
      content: "";
      height: 16px;
      width: 16px;
      left: 4px;
      bottom: 4px;
      background-color: white;
      transition: .4s;
      border-radius: 50%;
    }}
    
    input:checked + .slider {{
      background-color: var(--primary);
    }}
    
    input:checked + .slider:before {{
      transform: translateX(24px);
    }}
    
    /* Metadata Grid */
    .metadata-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 1.25rem;
      margin-bottom: 2.5rem;
    }}
    
    .meta-card {{
      background: var(--bg-secondary);
      border: 1px solid var(--border-color);
      border-radius: var(--card-radius);
      padding: 1.25rem;
      display: flex;
      align-items: center;
      gap: 1rem;
      box-shadow: var(--shadow-sm);
      transition: transform 0.2s, box-shadow 0.2s;
    }}
    
    .meta-card:hover {{
      transform: translateY(-2px);
      box-shadow: var(--shadow-md);
    }}
    
    .meta-icon {{
      font-size: 2rem;
      background: var(--primary-glow);
      padding: 0.5rem;
      border-radius: 12px;
      width: 40px;
      height: 40px;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    
    .meta-content {{
      display: flex;
      flex-direction: column;
    }}
    
    .meta-label {{
      font-size: 0.75rem;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    
    .meta-value {{
      font-size: 1.05rem;
      font-weight: 700;
      color: var(--text-primary);
      margin-top: 0.15rem;
    }}
    
    /* Section Cards */
    .section-card {{
      background: var(--bg-secondary);
      border: 1px solid var(--border-color);
      border-radius: var(--card-radius);
      padding: 1.75rem;
      margin-bottom: 2.5rem;
      box-shadow: var(--shadow-sm);
    }}
    
    .section-title {{
      margin: 0 0 1.25rem 0;
      font-size: 1.35rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }}
    
    .section-subtitle {{
      color: var(--text-muted);
      font-size: 0.9rem;
      margin: -0.75rem 0 1.5rem 0;
    }}
    
    /* Rankings & Index */
    .rankings-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 1.25rem;
    }}
    
    .rank-card {{
      border: 1px solid var(--border-color);
      border-radius: 14px;
      padding: 1.25rem;
      background: var(--bg-secondary);
      position: relative;
      overflow: hidden;
    }}
    
    .rank-card::after {{
      content: "";
      position: absolute;
      top: 0; left: 0; right: 0;
      height: 4px;
    }}
    
    .rank-1::after {{ background: var(--accent-gold); }}
    .rank-2::after {{ background: var(--accent-silver); }}
    .rank-3::after {{ background: var(--accent-bronze); }}
    .rank-other::after {{ background: var(--primary); }}
    
    .rank-card-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1.25rem;
    }}
    
    .rank-trophy {{
      font-size: 1.75rem;
    }}
    
    .rank-db-details {{
      flex: 1;
      margin-left: 0.75rem;
    }}
    
    .rank-db-title {{
      margin: 0;
      font-size: 1.15rem;
      font-weight: 700;
    }}
    
    .rank-lbl {{
      font-size: 0.75rem;
      font-weight: 600;
      color: var(--text-muted);
    }}
    
    .rank-overall-score {{
      text-align: right;
    }}
    
    .score-num {{
      display: block;
      font-size: 1.65rem;
      font-weight: 800;
      color: var(--primary);
      line-height: 1.1;
    }}
    
    .score-lbl {{
      font-size: 0.7rem;
      text-transform: uppercase;
      font-weight: 700;
      color: var(--text-muted);
    }}
    
    .rank-card-body {{
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
    }}
    
    .progress-container {{
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
    }}
    
    .progress-labels {{
      display: flex;
      justify-content: space-between;
      font-size: 0.78rem;
      font-weight: 600;
    }}
    
    .progress-scen {{
      color: var(--text-secondary);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 160px;
    }}
    
    .progress-val {{
      color: var(--text-primary);
    }}
    
    .progress-bar-track {{
      background: var(--bg-tertiary);
      height: 6px;
      border-radius: 4px;
      overflow: hidden;
    }}
    
    .progress-bar-fill {{
      background: var(--primary);
      height: 100%;
      border-radius: 4px;
      transition: width 0.8s ease-out;
    }}
    
    /* Interactive Tabs Section */
    .tabs-container {{
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
    }}
    
    .tabs-list {{
      display: flex;
      gap: 0.5rem;
      border-bottom: 1px solid var(--border-color);
      padding-bottom: 0.5rem;
      overflow-x: auto;
      white-space: nowrap;
      -webkit-overflow-scrolling: touch;
    }}
    
    .tab-btn {{
      background: transparent;
      border: none;
      color: var(--text-secondary);
      padding: 0.6rem 1.1rem;
      font-size: 0.875rem;
      font-weight: 600;
      cursor: pointer;
      border-radius: 8px;
      transition: all 0.2s;
    }}
    
    .tab-btn:hover {{
      color: var(--text-primary);
      background: var(--bg-tertiary);
    }}
    
    .tab-btn.active {{
      color: white;
      background: var(--primary);
    }}
    
    .tab-pane {{
      display: none;
    }}
    
    .tab-pane.active {{
      display: block;
      animation: fadeIn 0.3s ease-in-out;
    }}
    
    /* Table Styling */
    .table-container {{
      overflow-x: auto;
      border-radius: 12px;
      border: 1px solid var(--border-color);
    }}
    
    table {{
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 0.9rem;
    }}
    
    th {{
      background: var(--bg-tertiary);
      color: var(--text-secondary);
      font-weight: 600;
      padding: 0.85rem 1.25rem;
      border-bottom: 1px solid var(--border-color);
    }}
    
    td {{
      padding: 1.1rem 1.25rem;
      border-bottom: 1px solid var(--border-color);
      vertical-align: top;
    }}
    
    tr:last-child td {{
      border-bottom: none;
    }}
    
    .db-row-name {{
      font-weight: 700;
      color: var(--text-primary);
    }}
    
    /* Status Badges */
    .status-badge {{
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      font-size: 0.78rem;
      font-weight: 700;
      padding: 0.25rem 0.65rem;
      border-radius: 20px;
    }}
    
    .status-badge.success {{
      background: var(--success-glow);
      color: var(--success);
      border: 1px solid rgba(16, 185, 129, 0.2);
    }}
    
    .status-badge.failure {{
      background: var(--danger-glow);
      color: var(--danger);
      border: 1px solid rgba(239, 68, 68, 0.2);
    }}
    
    .badge-dot {{
      width: 6px;
      height: 6px;
      border-radius: 50%;
      display: inline-block;
    }}
    
    .status-badge.success .badge-dot {{
      background-color: var(--success);
      box-shadow: 0 0 8px var(--success);
      animation: pulse 1.8s infinite;
    }}
    
    .status-badge.failure .badge-dot {{
      background-color: var(--danger);
      box-shadow: 0 0 8px var(--danger);
    }}
    
    /* Metric Pills grid */
    .metrics-card-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
      gap: 0.65rem;
    }}
    
    .metric-card-pill {{
      background: var(--bg-tertiary);
      border: 1px solid var(--border-color);
      padding: 0.5rem 0.75rem;
      border-radius: 8px;
      display: flex;
      flex-direction: column;
    }}
    
    .metric-card-label {{
      font-size: 0.68rem;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.02em;
    }}
    
    .metric-card-value {{
      font-size: 0.9rem;
      font-weight: 700;
      color: var(--text-primary);
      margin-top: 0.15rem;
    }}
    
    .metric-unit {{
      font-size: 0.75rem;
      font-weight: 500;
      color: var(--text-secondary);
    }}
    
    .error-card-msg {{
      color: var(--danger);
      background: var(--danger-glow);
      padding: 0.75rem 1rem;
      border-radius: 8px;
      font-size: 0.85rem;
      font-weight: 600;
      border: 1px dashed rgba(239, 68, 68, 0.3);
    }}
    
    /* Visualizations Gallery */
    .charts-gallery {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 1.5rem;
    }}
    
    .chart-gallery-item {{
      background: var(--bg-tertiary);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 1rem;
      cursor: pointer;
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
      transition: transform 0.25s, box-shadow 0.25s;
    }}
    
    .chart-gallery-item:hover {{
      transform: translateY(-4px);
      box-shadow: var(--shadow-md);
    }}
    
    .chart-item-header {{
      font-size: 0.88rem;
      font-weight: 700;
      color: var(--text-secondary);
      text-transform: uppercase;
      letter-spacing: 0.02em;
    }}
    
    .chart-img-container {{
      position: relative;
      background: white;
      border-radius: 8px;
      overflow: hidden;
      display: flex;
      justify-content: center;
      align-items: center;
      border: 1px solid var(--border-color);
      aspect-ratio: 16/10;
    }}
    
    .chart-img-container img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      transition: filter 0.25s;
    }}
    
    .chart-gallery-item:hover img {{
      filter: blur(1.5px) brightness(0.85);
    }}
    
    .zoom-overlay {{
      position: absolute;
      background: rgba(15, 23, 42, 0.75);
      backdrop-filter: blur(4px);
      color: white;
      font-weight: 700;
      font-size: 0.85rem;
      padding: 0.5rem 1rem;
      border-radius: 20px;
      opacity: 0;
      transition: opacity 0.25s;
      pointer-events: none;
    }}
    
    .chart-gallery-item:hover .zoom-overlay {{
      opacity: 1;
    }}
    
    /* Lightbox Modal */
    .lightbox {{
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(15, 23, 42, 0.85);
      backdrop-filter: blur(12px);
      z-index: 1000;
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      opacity: 0;
      pointer-events: none;
      transition: opacity 0.3s ease;
      padding: 1.5rem;
    }}
    
    .lightbox.open {{
      opacity: 1;
      pointer-events: all;
    }}
    
    .lightbox-img {{
      max-width: 90%;
      max-height: 80%;
      object-fit: contain;
      border-radius: 12px;
      box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5);
      transform: scale(0.9);
      transition: transform 0.3s ease;
      background: white;
    }}
    
    .lightbox.open .lightbox-img {{
      transform: scale(1);
    }}
    
    .close-btn {{
      position: absolute;
      top: 1.5rem;
      right: 1.5rem;
      color: white;
      font-size: 2.25rem;
      cursor: pointer;
      font-weight: bold;
      width: 48px;
      height: 48px;
      background: rgba(255, 255, 255, 0.15);
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background 0.2s;
    }}
    
    .close-btn:hover {{
      background: rgba(255, 255, 255, 0.25);
    }}
    
    .lightbox-caption {{
      color: #f8fafc;
      font-size: 1.1rem;
      font-weight: 700;
      margin-top: 1.25rem;
    }}
    
    /* Animations */
    @keyframes fadeIn {{
      from {{ opacity: 0; transform: translateY(4px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    
    @keyframes pulse {{
      0% {{ box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.4); }}
      70% {{ box-shadow: 0 0 0 8px rgba(16, 185, 129, 0); }}
      100% {{ box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <!-- Header -->
    <header class="header">
      <div class="logo-title-group">
        <div class="logo-emoji">🚁</div>
        <div class="title-area">
          <h1>Drone Storage Bench</h1>
          <div class="timestamp">Generated: {timestamp}</div>
        </div>
      </div>
      
      <div class="toggle-container">
        <span class="toggle-label">Dark Mode</span>
        <label class="theme-switch">
          <input type="checkbox" id="theme-toggle">
          <span class="slider"></span>
        </label>
      </div>
    </header>
    
    <!-- Metadata Dashboard -->
    <section class="metadata-grid">
      {metadata_html}
    </section>
    
    <!-- Comparative scoring rankings -->
    {rankings_section}
    
    <!-- Performance Visualization Gallery -->
    {visualizations_section}
    
    <!-- Detailed telemetry & logs -->
    {workloads_tabs_section}
  </div>
  
  <!-- Lightbox Modal -->
  <div id="lightbox" class="lightbox" onclick="closeLightbox(event)">
    <span class="close-btn" onclick="closeLightbox(event)">&times;</span>
    <img class="lightbox-img" id="lightbox-img" src="" alt="Zoomed Chart">
    <div class="lightbox-caption" id="lightbox-caption"></div>
  </div>

  <script>
    // Tab switching logic
    function switchTab(evt, tabId) {{
      const tabPanes = document.getElementsByClassName("tab-pane");
      for (let i = 0; i < tabPanes.length; i++) {{
        tabPanes[i].classList.remove("active");
      }}
      const tabBtns = document.getElementsByClassName("tab-btn");
      for (let i = 0; i < tabBtns.length; i++) {{
        tabBtns[i].classList.remove("active");
      }}
      document.getElementById(tabId).classList.add("active");
      evt.currentTarget.classList.add("active");
    }}
    
    // Lightbox modal logic
    function openLightbox(src, caption) {{
      const lightbox = document.getElementById("lightbox");
      const img = document.getElementById("lightbox-img");
      const cap = document.getElementById("lightbox-caption");
      img.src = src;
      cap.innerText = caption;
      lightbox.classList.add("open");
    }}
    
    function closeLightbox(event) {{
      if (event.target.id === "lightbox-img") return;
      const lightbox = document.getElementById("lightbox");
      lightbox.classList.remove("open");
    }}
    
    // Dark mode local storage toggle
    const theme = localStorage.getItem("theme") || 
      (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.setAttribute("data-theme", theme);
    
    document.addEventListener("DOMContentLoaded", () => {{
      const toggle = document.getElementById("theme-toggle");
      if (toggle) {{
        toggle.checked = theme === "dark";
        toggle.addEventListener("change", () => {{
          const newTheme = toggle.checked ? "dark" : "light";
          document.documentElement.setAttribute("data-theme", newTheme);
          localStorage.setItem("theme", newTheme);
        }});
      }}
    }});
  </script>
</body>
</html>
"""

        with output_path.open("w", encoding="utf-8") as f:
            f.write(html_content)

        return output_path
