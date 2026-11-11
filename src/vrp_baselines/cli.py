"""vrp-baselines solve | bench"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .bench import Run, benchmark, run_one, summary_table, write_csv
from .problem import load_problem
from .solvers import METHODS


def _methods(value: str) -> list[str]:
    ms = [m.strip() for m in value.split(",") if m.strip()]
    bad = [m for m in ms if m not in METHODS]
    if bad:
        raise argparse.ArgumentTypeError(f"unknown method(s): {', '.join(bad)}")
    return ms


def _seeds(value: str) -> list[int]:
    try:
        if "-" in value and "," not in value:
            a, b = (int(x) for x in value.split("-"))
            seeds = list(range(a, b + 1))
        else:
            seeds = [int(x) for x in value.split(",")]
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid seeds {value!r}; use e.g. 1-5 or 1,7,42") from None
    if not seeds:
        raise argparse.ArgumentTypeError(f"empty seed range {value!r}")
    return seeds


def _positive(value: str) -> float:
    x = float(value)
    if x <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return x


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vrp-baselines",
        description="Solve CVRPLIB instances with standard baselines and measure the gap to the best known solution.",
    )
    parser.add_argument("--version", action="version", version=f"vrp-baselines {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-t", "--time-limit", type=_positive, default=10.0,
                        help="seconds per run for ortools and hgs (default 10)")
    common.add_argument("--rounding", choices=("auto", "nint", "ceil", "none"), default="auto",
                        help="distance convention; auto follows the reference solution, else the header")

    s = sub.add_parser("solve", parents=[common], help="solve one instance, write a .sol file")
    s.add_argument("instance")
    s.add_argument("-m", "--method", choices=METHODS, default="hgs")
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("-o", "--out", help="output .sol (default: <instance>.<method>.sol in the current directory)")
    s.add_argument("--bks", help="reference solution for the gap (default: <instance>.sol next to it)")

    b = sub.add_parser("bench", parents=[common], help="benchmark several methods and seeds")
    b.add_argument("instances", nargs="+")
    b.add_argument("-m", "--methods", type=_methods, default=list(METHODS),
                   help="comma-separated, default: savings,ortools,hgs")
    b.add_argument("--seeds", type=_seeds, default=[1, 2, 3, 4, 5],
                   help="e.g. 1-5 or 1,7,42 (deterministic methods run once)")
    b.add_argument("--csv", help="write every run to this CSV file")
    b.add_argument("--sol-dir", help="write every solution as .sol into this directory")
    return parser


def _fmt(r: Run) -> str:
    gap = "" if r.gap_pct is None else f"  gap {r.gap_pct:6.2f} %"
    status = "" if r.feasible else f"  INFEASIBLE: {r.error}"
    return (f"{r.instance:<14} {r.method:<8} seed {r.seed:<3} cost {r.cost:>12,.2f}{gap}"
            f"  {r.routes:>3} routes  {r.wall_s:6.2f} s{status}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "solve":
            problem = load_problem(args.instance, args.rounding, args.bks)
        else:
            problems = [load_problem(path, args.rounding) for path in args.instances]
    except (OSError, ValueError) as exc:
        print(f"vrp-baselines: error: {exc}", file=sys.stderr)
        return 2

    if args.command == "solve":
        out = Path(args.out) if args.out else Path(f"{Path(args.instance).stem}.{args.method}.sol")
        reference = Path(args.bks) if args.bks else Path(args.instance).with_suffix(".sol")
        if out.resolve() == reference.resolve():
            print(f"vrp-baselines: error: refusing to overwrite the reference solution {reference}",
                  file=sys.stderr)
            return 2
        r = run_one(problem, args.method, args.time_limit, args.seed, out_path=out)
        print(_fmt(r))
        print(out)
        return 0 if r.feasible else 1

    runs = benchmark(problems, args.methods, args.seeds, args.time_limit,
                     Path(args.sol_dir) if args.sol_dir else None,
                     progress=lambda r: print(_fmt(r), file=sys.stderr))
    if args.csv:
        write_csv(runs, Path(args.csv))
    print()
    print(f"Gap to BKS in % (mean over seeds, best in brackets), time limit {args.time_limit:g} s")
    print()
    print(summary_table(runs, args.methods))
    return 0 if all(r.feasible for r in runs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
