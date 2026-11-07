"""Manager + four domain specialists + integrator."""

from slm.pipeline.dispatch import run_plan, solve, solve_project
from slm.pipeline.router import adapter_for, route

__all__ = ["run_plan", "solve", "solve_project", "adapter_for", "route"]
