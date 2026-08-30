"""
baselines.py — Comparison algorithms for the Analysis-of-Algorithms writeup.

Both baselines operate on the exact same Student/Block models and the exact
same hard constraints as the main greedy allocator, so results are directly
comparable (see docs/complexity.md, "Baseline Comparison").

Approach 1 — Sequential Baseline:
    Groups are processed in input order (no priority queue, no adaptive
    re-prioritization). For each 2-seater bench, the two students placed
    are simply "next group in the fixed list" and "the group after it that
    is currently compatible" — found by a linear scan, not a heap.

Approach 2 — Sort-Then-Allocate Baseline:
    Groups are sorted once, up front, by remaining strength (descending),
    and then processed in that FIXED order for the entire run — unlike the
    main algorithm, priorities are never recomputed as groups shrink.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from .constraints import satisfies_hard_constraints
from .models import AllocationConfig, Block, ConflictEvent, GroupStream, Student
from .seating_matrix import SeatingMatrix
from .greedy_allocator import _order_blocks  # shared deterministic block ordering


def _group_students(students: List[Student]) -> Dict[str, GroupStream]:
    buckets: Dict[str, List[Student]] = defaultdict(list)
    for s in students:
        buckets[s.group_key].append(s)
    return {key: GroupStream(group_key=key, students=lst) for key, lst in buckets.items()}


def _first_compatible(
    groups: List[GroupStream], anchor: Student, exclude_key: str
) -> Optional[GroupStream]:
    """Linear scan for the first (not best) compatible, non-exhausted group."""
    for g in groups:
        if g.group_key == exclude_key or g.is_exhausted():
            continue
        if satisfies_hard_constraints(anchor, g.peek()):
            return g
    return None


def sequential_allocate(
    students: List[Student],
    blocks: List[Block],
    config: Optional[AllocationConfig] = None,
) -> Tuple[SeatingMatrix, List[ConflictEvent]]:
    """
    Approach 1: simple sequential allocation, no priority queue.

    Groups are visited in a fixed order (input/group_key order) every pass.
    No adaptive re-prioritization by remaining strength.
    """
    config = config or AllocationConfig()
    groups = list(_group_students(students).values())
    groups.sort(key=lambda g: g.group_key)  # fixed order, chosen once

    matrix = SeatingMatrix(blocks)
    conflicts: List[ConflictEvent] = []
    ordered_blocks = _order_blocks(blocks, config)

    group_cursor = 0
    for block in ordered_blocks:
        for bench in sorted(block.benches, key=lambda b: b.bench_no):
            if bench.is_full():
                continue

            # Advance to the next group with students left.
            while group_cursor < len(groups) and groups[group_cursor].is_exhausted():
                group_cursor += 1
            if group_cursor >= len(groups):
                break
            group_a = groups[group_cursor]

            if bench.seats_per_bench == 1 or not config.pairing_enabled:
                student = group_a.pop()
                matrix.place(student, block, bench, seat_index=0)
                continue

            anchor = group_a.peek()
            group_b = _first_compatible(groups, anchor, exclude_key=group_a.group_key)

            if group_b is None:
                if config.allow_single_seat_fallback:
                    student_a = group_a.pop()
                    matrix.place(student_a, block, bench, seat_index=0)
                    bench.fallback_closed = True
                    conflicts.append(
                        ConflictEvent(
                            type="NO_COMPATIBLE_PAIR",
                            group_key=group_a.group_key,
                            roll_no=student_a.roll_no,
                            block_no=block.block_no,
                            bench_no=bench.bench_no,
                            fallback="SINGLE_SEAT_FALLBACK",
                            reason="Sequential baseline: no compatible partner found in fixed order scan.",
                        )
                    )
                else:
                    conflicts.append(
                        ConflictEvent(
                            type="NO_COMPATIBLE_PAIR",
                            group_key=group_a.group_key,
                            roll_no=anchor.roll_no,
                            block_no=block.block_no,
                            bench_no=bench.bench_no,
                            fallback="DEFERRED",
                            reason="Sequential baseline: fallback disabled; bench left short.",
                        )
                    )
                continue

            student_a = group_a.pop()
            student_b = group_b.pop()
            matrix.place(student_a, block, bench, seat_index=0)
            matrix.place(student_b, block, bench, seat_index=1)

        if group_cursor >= len(groups) or all(g.is_exhausted() for g in groups):
            break

    # Any students never reached because blocks ran out first.
    for g in groups:
        while not g.is_exhausted():
            s = g.pop()
            conflicts.append(
                ConflictEvent(
                    type="NO_BLOCK_CAPACITY",
                    group_key=g.group_key,
                    roll_no=s.roll_no,
                    reason="Sequential baseline: block capacity exhausted first.",
                )
            )

    return matrix, conflicts


def sort_then_allocate(
    students: List[Student],
    blocks: List[Block],
    config: Optional[AllocationConfig] = None,
) -> Tuple[SeatingMatrix, List[ConflictEvent]]:
    """
    Approach 2: groups sorted once by initial strength (descending), then
    processed in that FIXED order for the whole run — no recomputation of
    priority as groups shrink (that adaptive recomputation is what
    distinguishes the main greedy+PQ approach in greedy_allocator.py).
    """
    config = config or AllocationConfig()
    groups = list(_group_students(students).values())
    groups.sort(key=lambda g: (-g.remaining(), g.group_key))  # sorted once, up front

    matrix = SeatingMatrix(blocks)
    conflicts: List[ConflictEvent] = []
    ordered_blocks = _order_blocks(blocks, config)

    group_cursor = 0
    for block in ordered_blocks:
        for bench in sorted(block.benches, key=lambda b: b.bench_no):
            if bench.is_full():
                continue

            while group_cursor < len(groups) and groups[group_cursor].is_exhausted():
                group_cursor += 1
            if group_cursor >= len(groups):
                break
            group_a = groups[group_cursor]

            if bench.seats_per_bench == 1 or not config.pairing_enabled:
                student = group_a.pop()
                matrix.place(student, block, bench, seat_index=0)
                continue

            anchor = group_a.peek()
            # Static order scan (not re-sorted by current remaining count).
            group_b = _first_compatible(groups, anchor, exclude_key=group_a.group_key)

            if group_b is None:
                if config.allow_single_seat_fallback:
                    student_a = group_a.pop()
                    matrix.place(student_a, block, bench, seat_index=0)
                    bench.fallback_closed = True
                    conflicts.append(
                        ConflictEvent(
                            type="NO_COMPATIBLE_PAIR",
                            group_key=group_a.group_key,
                            roll_no=student_a.roll_no,
                            block_no=block.block_no,
                            bench_no=bench.bench_no,
                            fallback="SINGLE_SEAT_FALLBACK",
                            reason="Sort-then-allocate baseline: no compatible partner in static order.",
                        )
                    )
                else:
                    conflicts.append(
                        ConflictEvent(
                            type="NO_COMPATIBLE_PAIR",
                            group_key=group_a.group_key,
                            roll_no=anchor.roll_no,
                            block_no=block.block_no,
                            bench_no=bench.bench_no,
                            fallback="DEFERRED",
                            reason="Sort-then-allocate baseline: fallback disabled; bench left short.",
                        )
                    )
                continue

            student_a = group_a.pop()
            student_b = group_b.pop()
            matrix.place(student_a, block, bench, seat_index=0)
            matrix.place(student_b, block, bench, seat_index=1)

        if all(g.is_exhausted() for g in groups):
            break

    for g in groups:
        while not g.is_exhausted():
            s = g.pop()
            conflicts.append(
                ConflictEvent(
                    type="NO_BLOCK_CAPACITY",
                    group_key=g.group_key,
                    roll_no=s.roll_no,
                    reason="Sort-then-allocate baseline: block capacity exhausted first.",
                )
            )

    return matrix, conflicts
