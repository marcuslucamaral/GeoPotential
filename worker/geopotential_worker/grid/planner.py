"""Resource planning before an expensive operation.

MSP-06: **"Não execute operação de alto custo sem estimativa de recursos."**

So an estimate is produced *first*, and it is honest about being an estimate:
it says what it assumed, and it reports the policy that follows — run in
memory, run in blocks, or refuse and say why. Section 18.1's escalation order
is the policy ladder: blocks, windows, temporaries and COG before memory
mapping and a resource scheduler.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from enum import Enum
from typing import Any

BYTES_PER_FLOAT32 = 4
MB = 1 << 20
GB = 1 << 30

# Fraction of available RAM one operation may plan to occupy. The rest is for
# the GUI process, the OS page cache, and the fact that GDAL and scipy both
# allocate more than the arrays they are handed.
RAM_BUDGET = 0.5

# Working-set multiplier. A stage rarely holds one copy: a warp holds source
# and destination, an aggregation holds the stack plus the accumulator.
WORKING_COPIES = 3


class Policy(str, Enum):
    IN_MEMORY = "in_memory"      # fits comfortably; run it
    BLOCKED = "blocked"          # too big for one pass; run in windows
    REFUSE = "refuse"            # will not fit even blocked, or no disk


@dataclass
class Plan:
    """What an operation will cost, and what to do about it."""

    operation: str
    pixels: int
    layers: int
    ram_bytes: int
    disk_bytes: int
    ram_available: int
    disk_available: int
    policy: Policy
    block_rows: int | None
    reason: str
    assumptions: list[str]

    @property
    def ram_mb(self) -> float:
        return round(self.ram_bytes / MB, 1)

    @property
    def disk_mb(self) -> float:
        return round(self.disk_bytes / MB, 1)

    @property
    def fits(self) -> bool:
        return self.policy is not Policy.REFUSE

    def summary(self) -> str:
        """One line for the interface, stating the estimate and the policy."""
        head = (
            f"{self.operation}: about {self.ram_mb:.0f} MB of memory and "
            f"{self.disk_mb:.0f} MB of disk"
        )
        if self.policy is Policy.IN_MEMORY:
            return f"{head}. Runs in one pass."
        if self.policy is Policy.BLOCKED:
            return f"{head}. Runs in blocks of {self.block_rows} rows. {self.reason}"
        return f"{head}. Refused: {self.reason}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "pixels": self.pixels,
            "layers": self.layers,
            "ram_bytes": self.ram_bytes,
            "ram_mb": self.ram_mb,
            "disk_bytes": self.disk_bytes,
            "disk_mb": self.disk_mb,
            "ram_available_mb": round(self.ram_available / MB, 1),
            "disk_available_mb": round(self.disk_available / MB, 1),
            "policy": self.policy.value,
            "block_rows": self.block_rows,
            "reason": self.reason,
            "assumptions": self.assumptions,
            "summary": self.summary(),
            "fits": self.fits,
        }


def available_ram() -> int:
    """Bytes of RAM an operation may reasonably plan to use.

    Reads the OS where it can and falls back to a conservative 2 GB where it
    cannot — a wrong-but-stated assumption beats an unstated one, and the
    assumption is carried in the plan.
    """
    try:
        return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError, AttributeError):
        return 2 * GB


def available_disk(path) -> int:  # noqa: ANN001 - path-like
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return 0


def plan_operation(
    operation: str,
    *,
    width: int,
    height: int,
    layers: int = 1,
    output_layers: int = 1,
    output_dir=None,  # noqa: ANN001 - path-like
    working_copies: int = WORKING_COPIES,
) -> Plan:
    """Estimate an operation's cost and decide how to run it.

    operation       what is being planned, named in the message
    width, height   the target grid
    layers          input layers held at once
    output_layers   float32 bands written
    output_dir      where the output goes, for the disk estimate
    working_copies  copies of the working set a stage holds; 3 by default

    returns  Plan — the estimate, the policy, and the assumptions behind both

    The estimate is deliberately pessimistic. Under-estimating produces a
    process the OS kills halfway through a run, which is the failure this
    exists to prevent.
    """
    pixels = int(width) * int(height)
    per_layer = pixels * BYTES_PER_FLOAT32
    ram_bytes = per_layer * max(1, layers) * max(1, working_copies)
    disk_bytes = per_layer * max(1, output_layers)

    ram_free = available_ram()
    disk_free = available_disk(output_dir or ".")
    budget = int(ram_free * RAM_BUDGET)

    assumptions = [
        f"float32, {BYTES_PER_FLOAT32} bytes per pixel per layer",
        f"{working_copies} working copies held at once",
        f"{int(RAM_BUDGET * 100)}% of free memory is available to one operation",
        "output written uncompressed; compression only reduces the disk figure",
    ]

    if disk_free and disk_bytes > disk_free:
        return Plan(
            operation, pixels, layers, ram_bytes, disk_bytes, ram_free, disk_free,
            Policy.REFUSE, None,
            f"the output needs {disk_bytes / MB:.0f} MB and only "
            f"{disk_free / MB:.0f} MB is free. Free space or choose another "
            f"output location.",
            assumptions,
        )

    if ram_bytes <= budget:
        return Plan(
            operation, pixels, layers, ram_bytes, disk_bytes, ram_free, disk_free,
            Policy.IN_MEMORY, None, "fits in memory", assumptions,
        )

    # Section 18.1: blocks and windows before memory mapping. Choose a row
    # count whose working set fits the budget, with a floor so the per-block
    # overhead does not dominate.
    bytes_per_row = width * BYTES_PER_FLOAT32 * max(1, layers) * max(1, working_copies)
    block_rows = max(1, int(budget // bytes_per_row)) if bytes_per_row else 1
    block_rows = min(block_rows, height)

    if block_rows < 1 or bytes_per_row > budget:
        return Plan(
            operation, pixels, layers, ram_bytes, disk_bytes, ram_free, disk_free,
            Policy.REFUSE, None,
            f"a single row of this grid needs {bytes_per_row / MB:.0f} MB, more "
            f"than the {budget / MB:.0f} MB budget. Reduce the resolution or the "
            f"number of layers held at once.",
            assumptions,
        )

    return Plan(
        operation, pixels, layers, ram_bytes, disk_bytes, ram_free, disk_free,
        Policy.BLOCKED, int(block_rows),
        f"{ram_bytes / MB:.0f} MB exceeds the {budget / MB:.0f} MB budget, so it "
        f"is processed in windows rather than one pass.",
        assumptions,
    )
