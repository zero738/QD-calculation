#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PLOTS = ROOT / "plots"
NAMES = (
    "coverage_formation_energy.png", "coverage_curvature_proxy.png",
    "coverage_electronic_proxies.png", "thickness_H1_H2_proxies.png",
    "relative_fermi_alignment.png", "work_function_status.png",
)


def csv_rows(name: str) -> list[dict]:
    path = ROOT / "results" / name
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def numeric_values(rows: list[dict]) -> list[float]:
    values = []
    for row in rows:
        for key, value in row.items():
            if key.startswith("value_") or key.endswith("_ev"):
                try:
                    values.append(float(value))
                except (TypeError, ValueError):
                    pass
    return values


def main() -> int:
    PLOTS.mkdir(exist_ok=True)
    sources = {
        NAMES[0]: "relative_coverage_formation_energy.csv",
        NAMES[1]: "coverage_curvature_proxy.csv",
        NAMES[2]: "dft_proxy_summary.csv",
        NAMES[3]: "dft_proxy_summary.csv",
        NAMES[4]: "relative_fermi_alignment.csv",
        NAMES[5]: "work_function_status.csv",
    }
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:
        (ROOT / "results/plot_status.json").write_text(json.dumps({"status": "pending_local_plot", "reason": f"matplotlib unavailable: {exc}", "plots": list(NAMES)}, indent=2) + "\n", encoding="utf-8")
        return 0
    statuses = {}
    for filename, source in sources.items():
        rows = csv_rows(source); values = numeric_values(rows)
        fig, ax = plt.subplots(figsize=(7, 4))
        if values:
            ax.plot(range(len(values)), values, marker="o")
            ax.set_ylabel("available proxy value")
            status = "generated_from_available_values"
        else:
            ax.text(0.5, 0.5, "missing / failed / blocked\n(no zero substitution)", ha="center", va="center", transform=ax.transAxes)
            ax.set_xticks([]); ax.set_yticks([])
            status = "generated_missing_state_placeholder"
        ax.set_title(filename.replace("_", " ").replace(".png", ""))
        fig.tight_layout(); fig.savefig(PLOTS / filename, dpi=150); plt.close(fig)
        statuses[filename] = status
    (ROOT / "results/plot_status.json").write_text(json.dumps({"status": "complete", "plots": statuses}, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
