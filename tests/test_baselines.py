from pathlib import Path

import pytest

from routeviz import check, load_solution
from vrp_baselines import load_problem, solve
from vrp_baselines.bench import benchmark, summary_table
from vrp_baselines.cli import main
from vrp_baselines.solvers import two_opt

INST = Path(__file__).parent.parent / "instances"
A32 = INST / "A-n32-k5.vrp"
CMT6 = INST / "CMT6.vrp"
P16 = INST / "P-n16-k8.vrp"

try:
    import hygese  # noqa: F401
    HAS_HGS = True
except ImportError:
    HAS_HGS = False

needs_hgs = pytest.mark.skipif(not HAS_HGS, reason="hygese not installed")


# --- problem loading ----------------------------------------------------------------

def test_bks_and_rounding_from_reference_solution():
    p = load_problem(A32)
    assert p.bks == 784 and p.rounding == "nint"
    assert p.dist[0][0] == 0 and p.dist[1][2] == int(p.dist[1][2])


def test_unrounded_convention_detected_for_cmt6():
    p = load_problem(CMT6)
    assert p.rounding == "none"
    assert p.bks == pytest.approx(555.43, abs=0.005)
    assert p.instance.max_distance == 200


def test_missing_reference_means_no_gap(tmp_path):
    vrp = tmp_path / "x.vrp"
    vrp.write_text(A32.read_text())
    p = load_problem(vrp)
    assert p.bks is None and p.rounding == "nint"


def test_infeasible_reference_is_rejected(tmp_path):
    bad = tmp_path / "bad.sol"
    bad.write_text("Route #1: 1 2 3\nCost 1\n")
    with pytest.raises(ValueError, match="infeasible"):
        load_problem(A32, bks_path=bad)


# --- solvers: every result must pass routeviz's independent check --------------------

@pytest.mark.parametrize("path", [A32, CMT6, P16])
@pytest.mark.parametrize("method", ["savings", "ortools", pytest.param("hgs", marks=needs_hgs)])
def test_solutions_are_feasible(path, method):
    p = load_problem(path)
    routes = solve(p, method, time_limit=1.0, seed=1)
    from routeviz import Solution
    report = check(p.instance, Solution(routes=routes), rounding=p.rounding)
    assert report.feasible, report.errors
    assert report.computed_cost >= p.bks - 1e-6  # nothing beats a proven optimum


def test_savings_is_deterministic():
    p = load_problem(A32)
    assert solve(p, "savings", 1, 1) == solve(p, "savings", 1, 2)


def test_two_opt_never_increases_length():
    p = load_problem(A32)
    route = list(range(1, 11))
    before = p.route_duration(route)
    after = p.route_duration(two_opt(p, route))
    assert after <= before
    assert sorted(two_opt(p, route)) == route


@needs_hgs
def test_hgs_finds_optimum_on_small_instance():
    p = load_problem(A32)
    routes = solve(p, "hgs", time_limit=2.0, seed=1)
    from routeviz import Solution
    assert check(p.instance, Solution(routes=routes)).computed_cost == 784


def test_unknown_method():
    with pytest.raises(ValueError):
        solve(load_problem(A32), "magic", 1, 1)


# --- benchmark and CLI ----------------------------------------------------------------

def test_deterministic_methods_run_once_per_instance():
    runs = benchmark([load_problem(A32)], ["savings", "ortools"], seeds=[1, 2, 3], time_limit=0.5)
    assert [(r.method, r.seed) for r in runs] == [("savings", 1), ("ortools", 1)]


def test_summary_table_reports_gap():
    runs = benchmark([load_problem(A32), load_problem(P16)], ["savings"], [1], 0.5)
    table = summary_table(runs, ["savings"])
    assert "| A-n32-k5 | 784 |" in table and "**mean**" in table


def test_cli_solve_writes_checkable_solution(tmp_path):
    out = tmp_path / "s.sol"
    assert main(["solve", str(A32), "-m", "savings", "-o", str(out)]) == 0
    sol = load_solution(out)
    from vrp_baselines import load_problem as lp
    assert check(lp(A32).instance, sol).ok  # stated cost matches the routes


def test_cli_bench_csv(tmp_path, capsys):
    csv_path = tmp_path / "runs.csv"
    assert main(["bench", str(A32), "-m", "savings", "--csv", str(csv_path)]) == 0
    assert csv_path.read_text().startswith("instance,method,seed")
    assert "| A-n32-k5 | 784 |" in capsys.readouterr().out


def test_cli_rejects_unknown_method():
    with pytest.raises(SystemExit):
        main(["bench", str(A32), "-m", "savings,foo"])


@needs_hgs
def test_hgs_handles_negative_coordinates():
    p = load_problem(INST / "F-n72-k4.vrp")
    assert min(c[0] for c in p.instance.coords) < 0  # the case this test is about
    routes = solve(p, "hgs", time_limit=1.0, seed=1)
    from routeviz import Solution
    assert check(p.instance, Solution(routes=routes), rounding=p.rounding).feasible


def test_large_costs_are_written_exactly(tmp_path):
    from vrp_baselines import write_solution
    write_solution(tmp_path / "s.sol", [[1]], 1234567.0)
    assert load_solution(tmp_path / "s.sol").cost == 1234567


def test_stated_bks_mismatch_warns(tmp_path):
    ref = tmp_path / "ref.sol"
    ref.write_text((INST / "A-n32-k5.sol").read_text().replace("Cost 784", "Cost 780"))
    with pytest.warns(UserWarning, match="differs from recomputed"):
        p = load_problem(A32, bks_path=ref)
    assert p.bks == 784


def test_cli_solve_writes_exactly_one_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["solve", str(A32), "-m", "savings", "-o", "out/x.sol"]) == 0
    assert [f.name for f in (tmp_path / "out").iterdir()] == ["x.sol"]


@pytest.mark.parametrize("bad", ["5-1", "a-b", "1,x"])
def test_cli_rejects_invalid_seeds(bad):
    with pytest.raises(SystemExit):
        main(["bench", str(A32), "--seeds", bad])


def test_instance_without_capacity_is_an_input_error(tmp_path):
    vrp = tmp_path / "nocap.vrp"
    vrp.write_text("NAME : nocap\nEDGE_WEIGHT_TYPE : EUC_2D\nNODE_COORD_SECTION\n1 0 0\n2 1 1\n"
                   "DEMAND_SECTION\n1 0\n2 1\nDEPOT_SECTION\n1\n-1\nEOF\n")
    assert main(["solve", str(vrp), "-m", "savings", "-o", str(tmp_path / "x.sol")]) == 2


def test_solve_refuses_to_overwrite_reference(tmp_path):
    vrp = tmp_path / "A-n32-k5.vrp"
    vrp.write_text(A32.read_text())
    ref = tmp_path / "A-n32-k5.sol"
    ref.write_text((INST / "A-n32-k5.sol").read_text())
    before = ref.read_text()
    assert main(["solve", str(vrp), "-m", "savings", "-o", str(ref)]) == 2
    assert ref.read_text() == before


def test_savings_runs_record_no_time_limit():
    (r,) = benchmark([load_problem(A32)], ["savings"], [1], time_limit=10)
    assert r.time_limit is None
