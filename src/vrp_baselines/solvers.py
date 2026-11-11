"""Three baselines for the CVRP, from textbook to state of the art.

savings  Clarke & Wright (1964), parallel version, plus 2-opt within routes.
         Deterministic, no time limit, milliseconds.
ortools  Google OR-Tools routing: savings start + guided local search, the
         configuration that did best on a pilot run (fixed for all instances).
hgs      Hybrid Genetic Search, Vidal (2022), via the PyHygese wrapper.

All solvers return routes as lists of customer indices (1..n, depot = 0) and
respect capacity and, if the instance has one, the route-length limit
DISTANCE including SERVICE_TIME.
"""

from __future__ import annotations

import math

from .problem import Problem

METHODS = ("savings", "ortools", "hgs")


def solve(problem: Problem, method: str, time_limit: float, seed: int) -> list[list[int]]:
    if method == "savings":
        return savings(problem)
    if method == "ortools":
        return ortools(problem, time_limit, seed)
    if method == "hgs":
        return hgs(problem, time_limit, seed)
    raise ValueError(f"unknown method {method!r} (choose from {', '.join(METHODS)})")


# --- Clarke & Wright savings + 2-opt ---------------------------------------------

def savings(p: Problem) -> list[list[int]]:
    n, d, q = p.n, p.dist, p.instance.demands
    limit = p.instance.max_distance
    routes: dict[int, list[int]] = {i: [i] for i in range(1, n + 1)}
    owner = {i: i for i in range(1, n + 1)}
    load = {i: q[i] for i in range(1, n + 1)}

    pairs = sorted(
        ((d[0][i] + d[0][j] - d[i][j], i, j) for i in range(1, n + 1) for j in range(i + 1, n + 1)),
        key=lambda t: (-t[0], t[1], t[2]),  # deterministic tie-breaking
    )
    for s, i, j in pairs:
        if s <= 0:
            break
        ri, rj = owner[i], owner[j]
        if ri == rj or load[ri] + load[rj] > p.capacity:
            continue
        a, b = routes[ri], routes[rj]
        # merge only through route ends: a must end in i, b must start with j
        if a[-1] != i:
            if a[0] != i:
                continue
            a = a[::-1]
        if b[0] != j:
            if b[-1] != j:
                continue
            b = b[::-1]
        merged = a + b
        if limit is not None and p.route_duration(merged) > limit + 1e-9:
            continue
        routes[ri] = merged
        load[ri] += load.pop(rj)
        del routes[rj]
        for c in b:
            owner[c] = ri
    return [two_opt(p, r) for r in routes.values()]


def two_opt(p: Problem, route: list[int]) -> list[int]:
    """First-improvement 2-opt on a single route (length can only decrease)."""
    path = [0, *route, 0]
    d = p.dist
    improved = True
    while improved:
        improved = False
        for i in range(1, len(path) - 2):
            for j in range(i + 1, len(path) - 1):
                a, b, c, e = path[i - 1], path[i], path[j], path[j + 1]
                if d[a][c] + d[b][e] < d[a][b] + d[c][e] - 1e-9:
                    path[i:j + 1] = path[i:j + 1][::-1]
                    improved = True
    return path[1:-1]


# --- OR-Tools ------------------------------------------------------------------------

def ortools(p: Problem, time_limit: float, seed: int) -> list[list[int]]:
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2

    # OR-Tools needs integer arc costs. Rounded conventions are integral already;
    # unrounded distances are scaled by 1000 (error < 0.0005 per arc).
    scale = 1 if p.rounding in ("nint", "ceil") else 1000
    n_nodes = p.n + 1
    cost = [[int(round(p.dist[i][j] * scale)) for j in range(n_nodes)] for i in range(n_nodes)]
    service = int(round(p.instance.service_time * scale))

    # Fleet size: the savings solution is feasible, so its route count is a safe
    # upper bound (a demand-based bound can be too small under a length limit).
    lb = p.lower_bound_vehicles()
    vehicles = min(p.n, max(lb + max(3, math.ceil(0.25 * lb)), len(savings(p))))
    manager = pywrapcp.RoutingIndexManager(n_nodes, vehicles, 0)
    routing = pywrapcp.RoutingModel(manager)

    # Matrices are registered natively (C++). Python callbacks would cost a
    # Python call per arc evaluation and starve the local search of iterations.
    arc_cb = routing.RegisterTransitMatrix(cost)
    routing.SetArcCostEvaluatorOfAllVehicles(arc_cb)

    dem_cb = routing.RegisterUnaryTransitVector([int(q) for q in p.instance.demands])
    routing.AddDimensionWithVehicleCapacity(dem_cb, 0, [p.capacity] * vehicles, True, "load")

    if p.instance.max_distance is not None:
        # duration of arc i -> j = travel time + service at i (none at the depot).
        # Rounded up, so that scaled rounding errors can never hide a violation.
        dur = [[math.ceil(p.dist[i][j] * scale - 1e-9) + (service if i != 0 else 0)
                for j in range(n_nodes)] for i in range(n_nodes)]
        dur_cb = routing.RegisterTransitMatrix(dur)
        routing.AddDimension(dur_cb, 0, int(math.floor(p.instance.max_distance * scale)), True, "duration")

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.SAVINGS
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromMilliseconds(int(time_limit * 1000))
    # The search is deterministic and ignores the seed. Under a time limit the
    # result can still depend on machine speed.

    sol = routing.SolveWithParameters(params)
    if sol is None:
        raise RuntimeError(f"OR-Tools found no feasible solution for {p.name} within {time_limit}s")
    routes = []
    for v in range(vehicles):
        idx, route = routing.Start(v), []
        idx = sol.Value(routing.NextVar(idx))
        while not routing.IsEnd(idx):
            route.append(manager.IndexToNode(idx))
            idx = sol.Value(routing.NextVar(idx))
        if route:
            routes.append(route)
    return routes


# --- HGS -----------------------------------------------------------------------------

def hgs(p: Problem, time_limit: float, seed: int) -> list[list[int]]:
    try:
        import hygese
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError("HGS needs the optional dependency: pip install 'vrp-baselines[hgs]'") from exc
    import numpy as np

    inst = p.instance
    # PyHygese rejects negative coordinates. HGS uses them only for polar angles
    # around the depot (SWAP* sectors); distances come from the matrix. A
    # translation changes neither, so shift the instance into the first quadrant.
    xs = np.array([c[0] for c in inst.coords], dtype=float)
    ys = np.array([c[1] for c in inst.coords], dtype=float)
    data = {
        "x_coordinates": xs - min(0.0, xs.min()),
        "y_coordinates": ys - min(0.0, ys.min()),
        "distance_matrix": np.array(p.dist, dtype=float),
        "demands": np.array(inst.demands, dtype=float),
        "vehicle_capacity": p.capacity,
        "depot": 0,
        "service_times": np.array([0.0] + [inst.service_time] * p.n),
    }
    if inst.max_distance is not None:
        data["duration_limit"] = inst.max_distance
    params = hygese.AlgorithmParameters(timeLimit=time_limit, seed=seed)
    result = hygese.Solver(parameters=params, verbose=False).solve_cvrp(data, rounding=False)
    return [list(r) for r in result.routes if len(r)]
