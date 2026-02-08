"""
GEPA Leaderboard - Comprehensive experiment analysis.

Analyzes experiment history and presents:
1. Leaderboard table grouped by model pairs
2. Case statistics
3. Anomaly detection
4. ROI analysis
5. Optional charts (requires matplotlib)

Outputs:
- Console table
- Markdown file
- CSV file
- PNG charts (optional)
"""

from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev

from .base import (
    detect_scale,
    extract_budget_from_rows,
    format_currency,
    format_float,
    format_md_table,
    get_output_dir,
    get_timestamp,
    load_metrics,
    parse_float,
    print_table,
)
from .roi_calculator import (
    FALLBACK_MAX_CALLS,
    calculate_optimization_cost,
    calculate_production_roi,
)


def get_stability_label(std: float, scale: float = 1.0) -> str:
    """Classify stability based on standard deviation, normalized by score scale."""
    normalized = std / scale if scale > 0 else std
    if normalized < 0.05:
        return "Alta"
    if normalized < 0.10:
        return "Buena"
    if normalized < 0.15:
        return "Atencion"
    return "Inestable"


def detect_anomalies(data: list[dict]) -> list[dict]:
    """Detect anomalies in individual runs. Scores normalized to %."""
    anomalies = []
    for row in data:
        base = parse_float(row.get("Baseline Score", "0"))
        opt = parse_float(row.get("Optimizado Score", "0"))
        rob = parse_float(row.get("Robustez Score", "0"))
        scale = detect_scale([base, opt, rob])
        to_pct = (100.0 / scale) if scale > 0 else 1.0

        reasons = []
        if opt < base:
            reasons.append("Opt < Base")
        if rob < base:
            reasons.append("Rob < Base")
        if rob == 0.0 or rob == 1.0 or rob == 100.0:
            reasons.append(f"Extremo ({format_float(rob * to_pct)}%)")

        if reasons:
            anomalies.append(
                {
                    "run_id": row.get("Run ID", "?"),
                    "case": row.get("Caso", "?"),
                    "source": row.get("source", "?"),
                    "base": format_float(base * to_pct),
                    "opt": format_float(opt * to_pct),
                    "rob": format_float(rob * to_pct),
                    "reason": ", ".join(reasons),
                }
            )

    return anomalies


def generate_charts(case_stats: list[dict], grouped_data: list[dict], output_dir: Path):
    """Generate performance and ROI charts."""
    try:
        import matplotlib.pyplot as plt
        import numpy as np

        # Chart 1: Performance improvement
        plt.rcParams["figure.figsize"] = (12, 7)
        plt.rcParams["axes.grid"] = True
        plt.rcParams["grid.alpha"] = 0.3

        cases = [s["case"] for s in case_stats]
        base_scores = [s["avg_base"] for s in case_stats]
        opt_scores = [s["avg_opt"] for s in case_stats]

        x = np.arange(len(cases))
        width = 0.35

        fig, ax = plt.subplots()
        ax.bar(x - width / 2, base_scores, width, label="Baseline", color="#95a5a6")
        ax.bar(x + width / 2, opt_scores, width, label="Optimizado", color="#27ae60")

        ax.set_ylabel("Score (%)")
        ax.set_title("Impacto de GEPA en Calidad del Modelo")
        ax.set_xticks(x)
        ax.set_xticklabels(cases, rotation=15, ha="right")
        ax.set_ylim(0, 115)
        ax.legend()

        plt.tight_layout()
        chart_path = output_dir / "performance_improvement.png"
        plt.savefig(chart_path, dpi=150)
        print(f"[INFO] Grafico: {chart_path}")
        plt.close()

        # Chart 2: ROI analysis
        profitable = [d for d in grouped_data if (d.get("savings_1k") or 0) > 0]
        if profitable:
            profitable.sort(key=lambda x: x["savings_1k"], reverse=False)

            names = [f"{d['case']}\n({d['task']})" for d in profitable]
            savings = [d["savings_1k"] for d in profitable]

            fig, ax = plt.subplots(figsize=(10, len(profitable) * 1.2 + 2))
            bars = ax.barh(names, savings, color="#3498db", height=0.6)

            ax.set_xlabel("Ahorro por 1,000 llamadas (USD)")
            ax.set_title("ROI Estimado con GEPA")
            ax.grid(axis="x", linestyle="--", alpha=0.7)

            for bar in bars:
                width = bar.get_width()
                ax.text(
                    width + (max(savings) * 0.02),
                    bar.get_y() + bar.get_height() / 2,
                    f"${width:.2f}",
                    va="center",
                    fontsize=10,
                )

            ax.set_xlim(0, max(savings) * 1.3)
            plt.tight_layout()

            roi_path = output_dir / "roi_analysis.png"
            plt.savefig(roi_path, dpi=150)
            print(f"[INFO] Grafico: {roi_path}")
            plt.close()

    except ImportError:
        print("[INFO] matplotlib no instalado - graficos omitidos")
    except Exception as e:
        print(f"[WARNING] Error generando graficos: {e}")


def run(
    csv_path: Path = None,
    project: str = None,
    case_filter: str = None,
    output: Path = None,
    graphs: bool = False,
):
    """
    Run leaderboard analysis.

    Args:
        csv_path: Explicit path to CSV file
        project: Filter to specific project
        case_filter: Filter to specific case
        output: Output file path (markdown)
        graphs: Generate PNG charts
    """
    data = load_metrics(csv_path=csv_path, project=project, merge=True)

    if case_filter:
        data = [d for d in data if case_filter.lower() in d.get("Caso", "").lower()]

    if not data:
        print("No hay datos para analizar.")
        return

    # Group data
    groups = defaultdict(list)
    for row in data:
        key = (
            row.get("Caso", "Unknown"),
            row.get("Modelo Tarea", "Unknown"),
            row.get("Modelo Profesor", "Unknown"),
        )
        groups[key].append(row)

    # Calculate statistics per group
    grouped_data = []
    for (case, task, reflect), rows in groups.items():
        base = [parse_float(r.get("Baseline Score", "0")) for r in rows]
        opt = [parse_float(r.get("Optimizado Score", "0")) for r in rows]
        rob = [parse_float(r.get("Robustez Score", "0")) for r in rows]

        avg_base, avg_opt, avg_rob = mean(base), mean(opt), mean(rob)
        std_rob = stdev(rob) if len(rob) > 1 else 0.0
        scale = detect_scale(base + opt + rob)

        # Extract budget from Notas (scan all rows in group)
        max_calls = extract_budget_from_rows(rows, FALLBACK_MAX_CALLS)

        # ROI calculation with real budget
        opt_cost = calculate_optimization_cost(case, task, reflect, max_calls=max_calls)

        # Normalize to percentage for uniform display
        to_pct = (100.0 / scale) if scale > 0 else 1.0
        delta_pct = (avg_rob - avg_base) * to_pct

        # ROI only meaningful when optimization improved results
        if delta_pct > 0:
            roi = calculate_production_roi(case, opt_cost["total_cost"], reflect, task, 1000)
            savings_1k = roi["savings"]
            breakeven = roi["breakeven_calls"]
        else:
            savings_1k = None
            breakeven = None

        grouped_data.append(
            {
                "case": case,
                "task": task,
                "reflect": reflect,
                "runs": len(rows),
                "avg_base_pct": avg_base * to_pct,
                "avg_opt_pct": avg_opt * to_pct,
                "avg_rob_pct": avg_rob * to_pct,
                "std_pct": (std_rob / scale * 100) if scale > 0 else 0.0,
                "delta_pct": delta_pct,
                "savings_1k": savings_1k,
                "breakeven": breakeven,
                "status": get_stability_label(std_rob, scale),
                "sources": list({r.get("source", "?") for r in rows}),
            }
        )

    grouped_data.sort(key=lambda x: (x["case"], x["delta_pct"]))

    # Prepare table (all scores normalized to %)
    headers = [
        "Caso",
        "Tarea",
        "Profesor",
        "Runs",
        "Base%",
        "Opt%",
        "Rob%",
        "Std%",
        "Estado",
        "Delta%",
        "Ahorro/1k",
        "Break-even",
    ]
    table_rows = []
    for r in grouped_data:
        if r["savings_1k"] is not None:
            savings_str = format_currency(r["savings_1k"])
            breakeven_str = f"{r['breakeven']:,}"
        else:
            savings_str = "N/A"
            breakeven_str = "N/A"

        table_rows.append(
            [
                r["case"],
                r["task"],
                r["reflect"],
                r["runs"],
                format_float(r["avg_base_pct"], 2),
                format_float(r["avg_opt_pct"], 2),
                format_float(r["avg_rob_pct"], 2),
                format_float(r["std_pct"], 2),
                r["status"],
                f"{r['delta_pct']:+.2f}".replace(".", ","),
                savings_str,
                breakeven_str,
            ]
        )

    # Console output
    print()
    print("=" * 120)
    print("LEADERBOARD DE EXPERIMENTOS")
    print("=" * 120)
    print()
    print_table(headers, table_rows)

    print()
    print("ESCALA DE ESTABILIDAD (Std/Escala):")
    print("  Alta (<5%) | Buena (5-10%) | Atencion (10-15%) | Inestable (>15%)")

    # Case statistics
    case_stats = []
    case_map = defaultdict(list)
    for g in grouped_data:
        case_map[g["case"]].append(g)

    for case, rows in case_map.items():
        case_stats.append(
            {
                "case": case,
                "total_runs": sum(r["runs"] for r in rows),
                "avg_base": mean(r["avg_base_pct"] for r in rows),
                "avg_opt": mean(r["avg_opt_pct"] for r in rows),
                "avg_rob": mean(r["avg_rob_pct"] for r in rows),
                "avg_delta": mean(r["delta_pct"] for r in rows),
            }
        )

    case_stats.sort(key=lambda x: x["avg_delta"], reverse=True)

    print()
    print("ESTADISTICAS POR CASO:")
    case_headers = ["Caso", "Runs", "Base%", "Opt%", "Rob%", "Delta%"]
    case_rows = [
        [
            s["case"],
            s["total_runs"],
            format_float(s["avg_base"], 2),
            format_float(s["avg_opt"], 2),
            format_float(s["avg_rob"], 2),
            f"{s['avg_delta']:+.2f}".replace(".", ","),
        ]
        for s in case_stats
    ]
    print_table(case_headers, case_rows)

    # Anomalies
    anomalies = detect_anomalies(data)
    if anomalies:
        print()
        print(f"ANOMALIAS DETECTADAS: {len(anomalies)}")
        anom_headers = ["Run ID", "Caso", "Fuente", "Base%", "Opt%", "Rob%", "Razon"]
        anom_rows = [
            [a["run_id"], a["case"], a["source"], a["base"], a["opt"], a["rob"], a["reason"]]
            for a in anomalies[:10]
        ]  # Limit to 10
        print_table(anom_headers, anom_rows)
        if len(anomalies) > 10:
            print(f"  ... y {len(anomalies) - 10} mas")

    # Output files
    output_dir = get_output_dir(project)

    # Save CSV
    csv_out = output_dir / "leaderboard.csv"
    import csv

    with open(csv_out, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(headers)
        writer.writerows(table_rows)
    print(f"\n[INFO] CSV: {csv_out}")

    # Save Markdown
    md_out = output or (output_dir / "leaderboard.md")
    md_content = "# Leaderboard GEPA\n\n"
    md_content += f"Generado: {get_timestamp()}\n\n"
    md_content += "## Leaderboard por Modelo\n\n"
    md_content += format_md_table(headers, table_rows)
    md_content += "\n## Estadisticas por Caso\n\n"
    md_content += format_md_table(case_headers, case_rows)

    if anomalies:
        md_content += f"\n## Anomalias ({len(anomalies)})\n\n"
        md_content += format_md_table(anom_headers, anom_rows)

    with open(md_out, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"[INFO] Markdown: {md_out}")

    # Generate charts
    if graphs:
        generate_charts(case_stats, grouped_data, output_dir)

    print()


if __name__ == "__main__":
    run()
