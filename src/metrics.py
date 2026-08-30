"""
metrics.py — Statistics and timing for a completed allocation run.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, List, Tuple

from .models import ConflictEvent
from .seating_matrix import SeatingMatrix


@dataclass
class AllocationStats:
    total_students: int
    total_seats: int
    seats_occupied: int
    seats_empty: int
    blocks_used: int
    benches_used: int
    allocation_conflicts: int
    constraint_violations: int
    utilization_pct: float
    execution_time_sec: float

    def as_dict(self) -> dict:
        return {
            "Total Students": self.total_students,
            "Total Seats": self.total_seats,
            "Seats Occupied": self.seats_occupied,
            "Empty Seats": self.seats_empty,
            "Blocks Used": self.blocks_used,
            "Benches Used": self.benches_used,
            "Allocation Conflicts": self.allocation_conflicts,
            "Constraint Violations": self.constraint_violations,
            "Utilization %": round(self.utilization_pct, 2),
            "Execution Time (s)": round(self.execution_time_sec, 4),
        }


def compute_stats(
    total_students: int,
    matrix: SeatingMatrix,
    conflicts: List[ConflictEvent],
    execution_time_sec: float,
) -> AllocationStats:
    total_seats = matrix.total_capacity()
    occupied = matrix.total_occupied()

    # "Constraint violations" is reserved for genuine hard-constraint
    # breaches (which SeatMatrix's design never allows to occur — see
    # docs/algorithm.md). Distinct from NO_COMPATIBLE_PAIR / fallback
    # conflicts, which are handled gracefully, not violations.
    constraint_violations = sum(1 for c in conflicts if c.type == "HARD_CONSTRAINT_VIOLATION")

    return AllocationStats(
        total_students=total_students,
        total_seats=total_seats,
        seats_occupied=occupied,
        seats_empty=total_seats - occupied,
        blocks_used=matrix.blocks_used(),
        benches_used=matrix.benches_used(),
        allocation_conflicts=len(conflicts),
        constraint_violations=constraint_violations,
        utilization_pct=(occupied / total_seats * 100.0) if total_seats else 0.0,
        execution_time_sec=execution_time_sec,
    )


def timed_run(allocate_fn: Callable, *args, **kwargs) -> Tuple[object, float]:
    """Run an allocator function and return (result, elapsed_seconds)."""
    start = time.perf_counter()
    result = allocate_fn(*args, **kwargs)
    elapsed = time.perf_counter() - start
    return result, elapsed
