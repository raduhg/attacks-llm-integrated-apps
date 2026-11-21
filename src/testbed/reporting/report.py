"""Thesis tables and charts from the experiment results on disk. No API calls.

    python -m testbed.reporting.report            # writes results/report/

Reads results/<experiment>/runs.jsonl and meta.json for the experiments listed in EXPERIMENTS,
and writes:
    tables.md                        every table below, with provenance (model, profile, commit)
    defenses_<experiment>.csv        per-defense metrics, one file per defense matrix
    fig_asr_heatmap.png              ASR per defense x (attack category, model, profile)
    fig_asr_fpr.png                  ASR and false-positive rate per defense, one panel per matrix
    fig_tradeoff.png                 security vs usability: ASR against FPR per defense
    fig_models.png                   baseline (D0) ASR per model and app profile

Every rate is shown with its count (k/n) and a Wilson 95% interval, and every figure names the
model and app profile its numbers come from, because results from the default and the weak
profile must never be mixed without saying so.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from testbed.config import PROJECT_ROOT
from testbed.evaluation.metrics import wilson

RESULTS = PROJECT_ROOT / "results"
DEFENSES = ["D0", "D1", "D1-LLM", "D2", "D3", "D3-dm", "D4", "D5", "D6"]

# id -> (model label, app profile). Only these experiments feed the report.
EXPERIMENTS: dict[str, tuple[str, str]] = {
    "m5_defenses": ("Haiku 5.5", "default"),
    "m6_leakage": ("Haiku 5.5", "default"),
    "m6_weak_haiku45_defenses": ("Haiku 4.5", "weak"),
    "m6_haiku45_probe": ("Haiku 4.5", "default"),
    "m6_weak_probe": ("Haiku 5.5", "weak"),
    "m6_weak_probe_haiku45": ("Haiku 4.5", "weak"),
}
MATRICES = ["m6_weak_haiku45_defenses", "m5_defenses"]  # full defense matrices, most informative first

# Chart colours: the validated reference palette (light mode, print). Blue = ASR, orange = FPR.
INK, INK_2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
BLUE, ORANGE = "#2a78d6", "#eb6834"
SEQUENTIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]


# --- data -----------------------------------------------------------------


def load(exp: str, results: Path = RESULTS) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Rows of runs.jsonl and meta.json of one experiment."""
    d = results / exp
    rows = [json.loads(ln) for ln in (d / "runs.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    return rows, json.loads((d / "meta.json").read_text(encoding="utf-8"))


def rate(k: int, n: int) -> dict[str, Any]:
    """A rate with its count and Wilson 95% interval; n=0 means not measured."""
    if n == 0:
        return {"k": 0, "n": 0, "rate": None, "lo": None, "hi": None}
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": k / n, "lo": lo, "hi": hi}


def defense_metrics(rows: list[dict[str, Any]], category: str | None = None) -> dict[str, dict[str, Any]]:
    """Per defense: ASR, utility under attack, benign failure (FPR), cost. `category` limits ASR
    and utility to one attack category."""
    g: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        x = g[r["defense"]]
        x["cost"].append(r["cost_usd"] + r.get("detector_cost_usd", 0))
        x["det"].append(r.get("detector_cost_usd", 0))
        if r["kind"] == "benign":
            x["benign_fail"].append(not r["task_passed"])
        elif category is None or r["category"] == category:
            x["asr"].append(bool(r["attack_success"]))
            if r.get("user_task_completed") is not None:
                x["utility"].append(bool(r["user_task_completed"]))
    return {
        d: {
            "asr": rate(sum(x["asr"]), len(x["asr"])),
            "utility": rate(sum(x["utility"]), len(x["utility"])),
            "fpr": rate(sum(x["benign_fail"]), len(x["benign_fail"])),
            "cost_per_run": sum(x["cost"]) / len(x["cost"]),
            "detector_cost_per_run": sum(x["det"]) / len(x["det"]),
        }
        for d, x in g.items()
    }


def categories(rows: list[dict[str, Any]]) -> list[str]:
    return sorted({r["category"] for r in rows if r["kind"] == "attack"})


# --- tables ---------------------------------------------------------------


def _cell(r: dict[str, Any]) -> str:
    if r["n"] == 0:
        return "–"
    return f"{r['k']}/{r['n']} ({r['rate']:.0%}, CI {r['lo']:.0%}–{r['hi']:.0%})"


def _provenance(exp: str, meta: dict[str, Any]) -> str:
    model, profile = EXPERIMENTS[exp]
    commit = meta.get("git_commit", "?")[:7] + (" (uncommitted changes)" if meta.get("git_dirty") else "")
    reps = meta["experiment"]["repetitions"]
    return f"Model {model}, {profile} profile, N={reps}, commit {commit}, finished {meta.get('finished_utc', '?')}."


def write_tables(data: dict[str, tuple[list, dict]], out: Path) -> None:
    lines = ["# Results tables", "", "Generated by `python -m testbed.reporting.report`. Rates are k/n with a Wilson 95% CI.", ""]
    for exp in MATRICES:
        if exp not in data:
            continue
        rows, meta = data[exp]
        m = defense_metrics(rows)
        lines += [f"## Defense matrix `{exp}`", "", _provenance(exp, meta),
                  f"Attack categories: {', '.join(categories(rows))}.", "",
                  "| Defense | ASR | Utility under attack | False-positive rate (benign) | Cost/run (USD) |",
                  "|---|---|---|---|---|"]
        csv_rows = []
        for d in DEFENSES:
            if d not in m:
                continue
            x = m[d]
            lines.append(f"| {d} | {_cell(x['asr'])} | {_cell(x['utility'])} | {_cell(x['fpr'])} | {x['cost_per_run']:.5f} |")
            metrics = {f"{k}_{f}": x[k][f] for k in ("asr", "utility", "fpr") for f in ("k", "n", "rate", "lo", "hi")}
            csv_rows.append({"defense": d, **metrics, "cost_per_run_usd": round(x["cost_per_run"], 6),
                             "detector_cost_per_run_usd": round(x["detector_cost_per_run"], 6)})
        lines.append("")
        with (out / f"defenses_{exp}.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(csv_rows[0]))
            w.writeheader()
            w.writerows(csv_rows)

    lines += ["## Baseline (D0) ASR by model and app profile", "",
              "| Attack category | Model | Profile | ASR | Experiment |", "|---|---|---|---|---|"]
    for cat, model, profile, r, exp in model_comparison(data):
        lines.append(f"| {cat} | {model} | {profile} | {_cell(r)} | `{exp}` |")
    lines += ["", "## Provenance", ""] + [f"- `{e}`: {_provenance(e, data[e][1])}" for e in EXPERIMENTS if e in data]
    (out / "tables.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def model_comparison(data: dict[str, tuple[list, dict]]) -> list[tuple[str, str, str, dict, str]]:
    """D0 ASR per (category, model, profile). Where two experiments measure the same cell, the one
    with more attempts wins (the full matrices use N=5, the probes N=3)."""
    best: dict[tuple[str, str, str], tuple[dict, str]] = {}
    for exp, (rows, _) in data.items():
        model, profile = EXPERIMENTS[exp]
        d0 = [r for r in rows if r["defense"] == "D0" and r["kind"] == "attack"]
        for cat in sorted({r["category"] for r in d0}):
            hits = [bool(r["attack_success"]) for r in d0 if r["category"] == cat]
            r = rate(sum(hits), len(hits))
            key = (cat, model, profile)
            if key not in best or r["n"] > best[key][0]["n"]:
                best[key] = (r, exp)
    return [(c, m, p, r, e) for (c, m, p), (r, e) in sorted(best.items())]


# --- charts ---------------------------------------------------------------


def _style(ax: Any) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
    ax.tick_params(colors=INK_2, labelsize=9)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _pct(r: dict[str, Any]) -> float:
    """Rate as a percentage; NaN (no bar, no point) when not measured."""
    return float("nan") if r["n"] == 0 else 100 * r["rate"]


def _err(rs: list[dict[str, Any]]) -> list[list[float]]:
    # max(0, ...): at a rate of 0 or 1 the Wilson bound can land a float hair inside the rate
    lo = [0.0 if r["n"] == 0 else max(0.0, 100 * (r["rate"] - r["lo"])) for r in rs]
    hi = [0.0 if r["n"] == 0 else max(0.0, 100 * (r["hi"] - r["rate"])) for r in rs]
    return [lo, hi]


def fig_heatmap(data: dict[str, tuple[list, dict]], out: Path, plt: Any) -> None:
    from matplotlib.colors import LinearSegmentedColormap

    cols = []  # (label, metrics per defense)
    for exp in ("m5_defenses", "m6_leakage", "m6_weak_haiku45_defenses"):
        if exp not in data:
            continue
        rows, _ = data[exp]
        model, profile = EXPERIMENTS[exp]
        for cat in categories(rows):
            cols.append((f"{cat.replace('_', ' ')}\n{model}, {profile}", defense_metrics(rows, cat)))
    cmap = LinearSegmentedColormap.from_list("seq", SEQUENTIAL)
    fig, ax = plt.subplots(figsize=(1.9 * len(cols) + 1.6, 5.2), facecolor=SURFACE)
    import numpy as np

    grid = np.full((len(DEFENSES), len(cols)), np.nan)
    for j, (_, m) in enumerate(cols):
        for i, d in enumerate(DEFENSES):
            if d in m and m[d]["asr"]["n"]:
                grid[i, j] = 100 * m[d]["asr"]["rate"]
    ax.imshow(np.ma.masked_invalid(grid), cmap=cmap, vmin=0, vmax=100, aspect="auto")
    for j, (_, m) in enumerate(cols):
        for i, d in enumerate(DEFENSES):
            r = m.get(d, {}).get("asr")
            if not r or not r["n"]:
                ax.text(j, i, "not run", ha="center", va="center", fontsize=8, color=MUTED)
                continue
            ax.text(j, i, f"{r['rate']:.0%}\n{r['k']}/{r['n']}", ha="center", va="center", fontsize=8,
                    color="#ffffff" if r["rate"] > 0.45 else INK)
    ax.set_xticks(range(len(cols)), [c[0] for c in cols], fontsize=8.5, color=INK_2)
    ax.set_yticks(range(len(DEFENSES)), DEFENSES, fontsize=9, color=INK_2)
    ax.tick_params(which="both", length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xticks([x - 0.5 for x in range(1, len(cols))], minor=True)
    ax.set_yticks([y - 0.5 for y in range(1, len(DEFENSES))], minor=True)
    ax.grid(which="minor", color=SURFACE, linewidth=2)
    ax.set_title("Attack success rate by defense (N=5 per attack)", loc="left", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(out / "fig_asr_heatmap.png", dpi=200)
    plt.close(fig)


def fig_asr_fpr(data: dict[str, tuple[list, dict]], out: Path, plt: Any) -> None:
    exps = [e for e in MATRICES if e in data]
    fig, axes = plt.subplots(1, len(exps), figsize=(6.2 * len(exps), 4.2), facecolor=SURFACE, squeeze=False)
    for ax, exp in zip(axes[0], exps, strict=True):
        rows, _ = data[exp]
        m = defense_metrics(rows)
        ds = [d for d in DEFENSES if d in m]
        asr, fpr = [m[d]["asr"] for d in ds], [m[d]["fpr"] for d in ds]
        x = list(range(len(ds)))
        w = 0.38
        _style(ax)
        ax.bar([i - w / 2 - 0.01 for i in x], [_pct(r) for r in asr], w, color=BLUE, label="Attack success rate",
               yerr=_err(asr), error_kw={"ecolor": INK_2, "elinewidth": 0.8, "capsize": 2})
        ax.bar([i + w / 2 + 0.01 for i in x], [_pct(r) for r in fpr], w, color=ORANGE, label="False-positive rate",
               yerr=_err(fpr), error_kw={"ecolor": INK_2, "elinewidth": 0.8, "capsize": 2})
        ax.set_xticks(x, ds)
        ax.set_ylim(0, 100)
        ax.set_ylabel("%", color=INK_2)
        model, profile = EXPERIMENTS[exp]
        n_att, n_ben = asr[0]["n"], fpr[0]["n"]
        cats = ", ".join(c.replace("_", " ") for c in categories(rows))
        ax.set_title(f"{model}, {profile} profile ({cats})\n"
                     f"{n_att} attack runs and {n_ben} benign runs per defense", loc="left", fontsize=10, color=INK)
    axes[0][0].legend(frameon=False, fontsize=9, labelcolor=INK_2, loc="upper right")
    fig.tight_layout()
    fig.savefig(out / "fig_asr_fpr.png", dpi=200)
    plt.close(fig)


def fig_tradeoff(data: dict[str, tuple[list, dict]], out: Path, plt: Any) -> None:
    exp = MATRICES[0]
    if exp not in data:
        return
    rows, _ = data[exp]
    m = defense_metrics(rows)
    points: dict[tuple[float, float], list[str]] = defaultdict(list)  # defenses at identical points share a label
    for d in DEFENSES:
        if d in m and m[d]["asr"]["n"] and m[d]["fpr"]["n"]:
            points[(round(100 * m[d]["fpr"]["rate"], 2), round(100 * m[d]["asr"]["rate"], 2))].append(d)
    fig, ax = plt.subplots(figsize=(6.4, 4.6), facecolor=SURFACE)
    _style(ax)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    for (fx, ay), ds in points.items():
        r = m[ds[0]]
        xe, ye = _err([r["fpr"]]), _err([r["asr"]])
        ax.errorbar(fx, ay, xerr=xe, yerr=ye,
                    fmt="o", color=BLUE, markersize=8, markeredgecolor=SURFACE, markeredgewidth=2,
                    ecolor=AXIS, elinewidth=0.8, capsize=0)
        crowded = any(ox == fx and 0 < oy - ay < 6 for ox, oy in points)  # a point just above: put the label below
        ax.annotate(", ".join(ds), (fx, ay), xytext=(9, -13 if crowded else 4), textcoords="offset points", fontsize=9, color=INK)
    model, profile = EXPERIMENTS[exp]
    ax.set_xlim(-2, max(100 * m[d]["fpr"]["hi"] for ds in points.values() for d in ds) + 6)
    ax.set_ylim(-3, 80)
    ax.set_xlabel("False-positive rate on benign tasks (%)", color=INK_2)
    ax.set_ylabel("Attack success rate (%)", color=INK_2)
    ax.set_title(f"Security vs usability per defense\n{model}, {profile} profile, leakage attacks; "
                 "lower left is better", loc="left", fontsize=10, color=INK)
    fig.tight_layout()
    fig.savefig(out / "fig_tradeoff.png", dpi=200)
    plt.close(fig)


def fig_models(data: dict[str, tuple[list, dict]], out: Path, plt: Any) -> None:
    comp = model_comparison(data)
    cats = sorted({c for c, *_ in comp})
    fig, axes = plt.subplots(1, len(cats), figsize=(4.6 * len(cats), 4.0), facecolor=SURFACE, squeeze=False, sharey=True)
    for ax, cat in zip(axes[0], cats, strict=True):
        items = [(f"{m}\n{p}", r) for c, m, p, r, _ in comp if c == cat]
        _style(ax)
        rs = [r for _, r in items]
        ax.bar(range(len(items)), [_pct(r) for r in rs], 0.55, color=BLUE,
               yerr=_err(rs), error_kw={"ecolor": INK_2, "elinewidth": 0.8, "capsize": 2})
        for i, r in enumerate(rs):
            ax.text(i, 100 * r["hi"] + 2, f"{r['k']}/{r['n']}", ha="center", fontsize=9, color=INK_2)
        ax.set_xticks(range(len(items)), [lbl for lbl, _ in items], fontsize=9)
        ax.set_ylim(0, 100)
        ax.set_title(cat.replace("_", " "), loc="left", fontsize=10, color=INK)
    axes[0][0].set_ylabel("Attack success rate at D0 (%)", color=INK_2)
    fig.suptitle("Baseline vulnerability by model and app profile (no defense)", x=0.01, ha="left", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(out / "fig_models.png", dpi=200)
    plt.close(fig)


# --- entry point ----------------------------------------------------------


def build_report(results: Path = RESULTS, out: Path | None = None) -> Path:
    """Load every listed experiment that has results and write all tables and figures."""
    import matplotlib

    matplotlib.use("Agg")  # files only, no window
    import matplotlib.pyplot as plt

    out = out or results / "report"
    out.mkdir(parents=True, exist_ok=True)
    data = {}
    for exp in EXPERIMENTS:
        if (results / exp / "meta.json").exists():
            rows, meta = load(exp, results)
            if rows:
                data[exp] = (rows, meta)
    write_tables(data, out)
    for fig in (fig_heatmap, fig_asr_fpr, fig_tradeoff, fig_models):
        fig(data, out, plt)
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, help="output folder (default results/report)")
    args = parser.parse_args(argv)
    out = build_report(out=args.out)
    print(f"Report written to {out}")
    for p in sorted(out.iterdir()):
        print("  ", p.name)


if __name__ == "__main__":
    main()
