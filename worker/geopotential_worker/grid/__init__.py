"""Grid engine. MSP-06.

M3 delivers the planner: no high-cost operation runs without a resource
estimate. The operators themselves — reprojection, resampling, rasterization,
distance, IDW — are M5.
"""
from .planner import Plan, Policy, plan_operation

__all__ = ["Plan", "Policy", "plan_operation"]
