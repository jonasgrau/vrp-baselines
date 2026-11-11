"""Problem data shared by all solvers.

Every method gets the same distance matrix, built with the same rounding
convention, so cost differences come from the algorithms and not from how
distances were computed.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from pathlib import Path

from routeviz import Instance, Solution, check, load_instance, load_solution
from routeviz.check import default_rounding, distance


@dataclass
class Problem:
    instance: Instance
    rounding: str  # "nint" | "ceil" | "none"
    dist: list[list[float]]
    bks: float | None  # best known solution value, if a reference .sol was found
    path: Path

    @property
    def name(self) -> str:
        return self.instance.name

    @property
    def n(self) -> int:
        return self.instance.n_customers

    @property
    def capacity(self) -> int:
        if self.instance.capacity is None:
            raise ValueError(f"{self.name}: instance has no CAPACITY")
        return self.instance.capacity

    def route_duration(self, route: list[int]) -> float:
        """Route length plus service times, the quantity bounded by DISTANCE."""
        path = [0, *route, 0]
        length = sum(self.dist[i][j] for i, j in zip(path, path[1:]))
        return length + self.instance.service_time * len(route)

    def lower_bound_vehicles(self) -> int:
        return max(1, math.ceil(sum(self.instance.demands[1:]) / self.capacity))


def load_problem(path: str | Path, rounding: str = "auto", bks_path: str | Path | None = None) -> Problem:
    """Load an instance and its reference solution.

    The reference solution defaults to ``<instance>.sol`` next to the instance
    (CVRPLIB ships best known solutions that way). With ``rounding="auto"`` the
    convention is taken from the reference solution when there is one: routeviz
    detects sets such as CMT and Golden that declare EUC_2D but are scored with
    unrounded distances. Without a reference, EDGE_WEIGHT_TYPE decides.
    """
    path = Path(path)
    inst = load_instance(path)
    if inst.capacity is None:
        raise ValueError(f"{path}: instance has no CAPACITY, so it is not a CVRP instance")
    ref_path = Path(bks_path) if bks_path else path.with_suffix(".sol")
    ref: Solution | None = load_solution(ref_path) if ref_path.exists() else None

    if rounding == "auto":
        if ref is not None and ref.cost is not None:
            rounding = check(inst, ref).rounding
        else:
            rounding = default_rounding(inst)

    bks = None
    if ref is not None:
        report = check(inst, ref, rounding=rounding)
        if not report.feasible:
            raise ValueError(f"{ref_path}: reference solution is infeasible: {report.errors[0]}")
        bks = report.computed_cost
        if report.cost_matches is False:
            warnings.warn(
                f"{ref_path}: stated cost {ref.cost} differs from recomputed {bks} "
                f"(rounding {rounding}); gaps use the recomputed value",
                stacklevel=2,
            )

    c = inst.coords
    dist = [[distance(c[i], c[j], rounding) for j in range(len(c))] for i in range(len(c))]
    return Problem(instance=inst, rounding=rounding, dist=dist, bks=bks, path=path)


def write_solution(path: str | Path, routes: list[list[int]], cost: float, comment: str = "") -> None:
    lines = [f"Route #{i}: {' '.join(map(str, r))}" for i, r in enumerate(routes, start=1)]
    # integral costs exactly (":g" would print 1.23457e+06 for large instances)
    lines.append(f"Cost {int(cost)}" if cost == int(cost) else f"Cost {cost:.6f}")
    if comment:
        lines.append(f"Comment: {comment}")
    Path(path).write_text("\n".join(lines) + "\n")
