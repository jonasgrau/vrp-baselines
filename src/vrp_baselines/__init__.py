"""vrp-baselines: standard CVRP baselines with verified gaps to the best known solution."""

__version__ = "0.1.0"

from .problem import Problem, load_problem, write_solution  # noqa: E402
from .solvers import METHODS, solve  # noqa: E402

__all__ = ["METHODS", "Problem", "load_problem", "solve", "write_solution"]
