"""Run methods x seeds x instances and report routeviz-verified results."""

from __future__ import annotations

import csv
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from routeviz import Solution, check

from .problem import Problem, write_solution
from .solvers import solve

# Ignore the seed, so extra seeds would repeat the same run. (OR-Tools under a time
# limit can still vary with machine speed; repeated runs here were identical.)
DETERMINISTIC = {"savings", "ortools"}


@dataclass
class Run:
    instance: str
    method: str
    seed: int
    time_limit: float | None  # None for savings, which has no time limit
    cost: float  # recomputed by routeviz, never taken from the solver
    bks: float | None
    gap_pct: float | None
    routes: int
    wall_s: float
    feasible: bool
    error: str = ""


def run_one(problem: Problem, method: str, time_limit: float, seed: int,
            out_dir: Path | None = None, out_path: Path | None = None) -> Run:
    limit = None if method == "savings" else time_limit
    start = time.perf_counter()
    try:
        routes = solve(problem, method, time_limit, seed)
    except Exception as exc:  # a failing solver is a result, not a crash of the whole benchmark
        return Run(problem.name, method, seed, limit, float("nan"), problem.bks, None, 0,
                   time.perf_counter() - start, False, f"{type(exc).__name__}: {exc}")
    wall = time.perf_counter() - start

    report = check(problem.instance, Solution(routes=routes), rounding=problem.rounding)
    cost = report.computed_cost
    gap = 100.0 * (cost - problem.bks) / problem.bks if problem.bks else None
    if out_path is None and out_dir is not None:
        out_path = out_dir / f"{problem.name}.{method}.seed{seed}.sol"
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_solution(out_path, routes, cost,
                       comment=f"vrp-baselines {method}, seed {seed}"
                               + (f", time limit {limit}s" if limit is not None else ""))
    return Run(problem.name, method, seed, limit, cost, problem.bks, gap, report.n_routes,
               wall, report.feasible, "; ".join(report.errors))


def benchmark(problems: list[Problem], methods: list[str], seeds: list[int], time_limit: float,
              out_dir: Path | None = None, progress=None) -> list[Run]:
    runs = []
    for p in problems:
        for m in methods:
            for s in (seeds[:1] if m in DETERMINISTIC else seeds):
                r = run_one(p, m, time_limit, s, out_dir)
                runs.append(r)
                if progress:
                    progress(r)
    return runs


def write_csv(runs: list[Run], path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(runs[0])))
        w.writeheader()
        for r in runs:
            w.writerow(asdict(r))


def summary_table(runs: list[Run], methods: list[str]) -> str:
    """Markdown table: mean gap to BKS per instance and method (min over seeds in brackets)."""
    instances = sorted(dict.fromkeys(r.instance for r in runs), key=str.lower)
    bks = {r.instance: r.bks for r in runs}
    head = "| Instance | BKS | " + " | ".join(methods) + " |"
    sep = "|---|---:|" + "---:|" * len(methods)
    lines = [head, sep]
    mean_gaps: dict[str, list[float]] = {m: [] for m in methods}
    for inst in instances:
        cells = []
        for m in methods:
            rs = [r for r in runs if r.instance == inst and r.method == m]
            ok = [r.gap_pct for r in rs if r.feasible and r.gap_pct is not None]
            if not rs:
                cells.append("")
            elif len(ok) < len(rs):
                cells.append(f"{len(rs) - len(ok)}/{len(rs)} failed")
            else:
                mean = statistics.fmean(ok)
                mean_gaps[m].append(mean)
                cells.append(f"{mean:.2f} %" + (f" ({min(ok):.2f})" if len(ok) > 1 else ""))
        b = bks[inst]
        b_s = "–" if b is None else (f"{b:,.0f}" if b == int(b) else f"{b:,.2f}")
        lines.append(f"| {inst} | {b_s} | " + " | ".join(cells) + " |")
    if len(instances) > 1:
        lines.append("| **mean** | | " + " | ".join(
            f"**{statistics.fmean(g):.2f} %**" if len(g) == len(instances) else "" for g in mean_gaps.values()
        ) + " |")
    return "\n".join(lines)
