"""
greedy_allocator.py — SeatMatrix's core Greedy + Priority Queue algorithm
(Approach 3 in the algorithm comparison; see baselines.py for Approaches 1-2).

GREEDY CHOICE (documented, see docs/algorithm.md):
  At every step, the highest-remaining-strength group is served first.
  When a bench requires pairing, the highest-remaining-strength *compatible*
  partner is chosen among currently-active groups. This is a local greedy
  choice: it does not guarantee a globally minimal number of conflicts.

SEQUENTIAL ALLOCATION INVARIANT:
  Enforced entirely by GroupStream (models.py) — this module never accesses
  `GroupStream.students` directly, only `.peek()` and `.pop()`.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from .constraints import satisfies_hard_constraints, rank_candidates
from .models import AllocationConfig, Block, ConflictEvent, GroupStream, Student
from .priority_queue import GroupPriorityQueue
from .seating_matrix import SeatingMatrix


def _group_students(students: List[Student]) -> Dict[str, GroupStream]:
    """Group students by group_key into GroupStreams (sorted internally)."""
    buckets: Dict[str, List[Student]] = defaultdict(list)
    for s in students:
        buckets[s.group_key].append(s)
    return {key: GroupStream(group_key=key, students=lst) for key, lst in buckets.items()}


def _order_blocks(blocks: List[Block], config: AllocationConfig) -> List[Block]:
    """
    Deterministic block visiting order. If the config specifies a preferred
    order (list of block_no), respect it; otherwise fall back to a stable
    sort by (floor, block_no) so results are reproducible across runs.
    """
    if config.preferred_block_order:
        order_index = {bno: i for i, bno in enumerate(config.preferred_block_order)}
        return sorted(
            blocks,
            key=lambda b: (order_index.get(b.block_no, len(order_index)), b.floor, b.block_no),
        )
    return sorted(blocks, key=lambda b: (b.floor, b.block_no))


def find_compatible_group(
    pq: GroupPriorityQueue, anchor: Student, exclude_group_key: str
) -> Optional[GroupStream]:
    """
    Greedy candidate selection for the second seat of a 2-seater bench.

    Drains the queue, filters to groups whose *next* student (peek()) is
    hard-constraint-compatible with `anchor`, ranks the survivors by the
    soft-preference hierarchy (constraints.rank_candidates), picks the
    top-ranked one, and rebuilds the heap with everyone else (including
    the anchor's own group, which the caller re-pushes separately).

    Never consumes (`pop()`s) any candidate — only `peek()`s. The caller
    is responsible for popping the winning group exactly once.
    """
    all_groups = pq.drain_all()

    candidates = [
        g
        for g in all_groups
        if g.group_key != exclude_group_key
        and not g.is_exhausted()
        and satisfies_hard_constraints(anchor, g.peek())
    ]

    winner = rank_candidates(candidates)[0] if candidates else None

    # Rebuild the heap with everything except the winner (winner is popped
    # by the caller and re-pushed only if it still has students left).
    remaining_groups = [g for g in all_groups if winner is None or g.group_key != winner.group_key]
    pq.rebuild(remaining_groups)

    return winner


def allocate_seating(
    students: List[Student],
    blocks: List[Block],
    config: Optional[AllocationConfig] = None,
) -> Tuple[SeatingMatrix, List[ConflictEvent]]:
    """
    Run SeatMatrix's Greedy + Priority Queue allocation.

    Returns (SeatingMatrix, list[ConflictEvent]).
    Deterministic: identical (students, blocks, config) always produces an
    identical result (see docs/algorithm.md, "Determinism").
    """
    config = config or AllocationConfig()

    groups = _group_students(students)
    pq = GroupPriorityQueue()
    for g in groups.values():
        pq.push(g)

    matrix = SeatingMatrix(blocks)
    conflicts: List[ConflictEvent] = []

    ordered_blocks = _order_blocks(blocks, config)
    block_cursor = 0

    def current_block() -> Optional[Block]:
        nonlocal block_cursor
        while block_cursor < len(ordered_blocks) and ordered_blocks[block_cursor].is_full():
            block_cursor += 1
        return ordered_blocks[block_cursor] if block_cursor < len(ordered_blocks) else None

    while not pq.is_empty():
        block = current_block()
        if block is None:
            # No block capacity left anywhere: log every remaining student
            # as a conflict rather than crashing or dropping them silently.
            for g in pq.drain_all():
                while not g.is_exhausted():
                    student = g.peek()
                    conflicts.append(
                        ConflictEvent(
                            type="NO_BLOCK_CAPACITY",
                            group_key=g.group_key,
                            roll_no=student.roll_no,
                            reason="All block capacity exhausted before this student could be seated.",
                        )
                    )
                    g.pop()
            break

        bench = block.next_open_bench()
        if bench is None:
            # Shouldn't normally happen (current_block() skips full blocks),
            # but guard defensively and advance.
            block_cursor += 1
            continue

        if bench.seats_per_bench == 1 or not config.pairing_enabled:
            # --- Single-seat bench: no pairing constraint (H8) ---
            group = pq.pop_max()
            if group is None:
                break
            student = group.pop()
            matrix.place(student, block, bench, seat_index=0)
            if not group.is_exhausted():
                pq.push(group)

        else:
            # --- Two-seater bench: requires a compatible pair ---
            # The bench may already have one seat filled (e.g. a previous
            # single-seat-fallback placed a student here and left the
            # bench not-yet-full) — always resolve the actual open seat
            # index dynamically rather than assuming seat 0.
            first_idx = bench.open_seat_index()

            group_a = pq.pop_max()
            if group_a is None:
                break
            anchor = group_a.peek()  # do NOT pop yet — pairing might fail

            group_b = find_compatible_group(pq, anchor, exclude_group_key=group_a.group_key)

            if group_b is None:
                # --- No compatible partner currently available ---
                if config.allow_single_seat_fallback:
                    student_a = group_a.pop()
                    matrix.place(student_a, block, bench, seat_index=first_idx)
                    bench.fallback_closed = True  # second seat permanently left empty
                    conflicts.append(
                        ConflictEvent(
                            type="NO_COMPATIBLE_PAIR",
                            group_key=group_a.group_key,
                            roll_no=student_a.roll_no,
                            block_no=block.block_no,
                            bench_no=bench.bench_no,
                            fallback="SINGLE_SEAT_FALLBACK",
                            reason="No hard-constraint-compatible partner was available; "
                            "seated alone, second seat left empty.",
                        )
                    )
                    if not group_a.is_exhausted():
                        pq.push(group_a)
                else:
                    # Fallback disabled: do NOT force-pair, do NOT advance
                    # the pointer (student is not placed). Defer this group
                    # to the back of the queue by re-pushing it unchanged,
                    # and record the deferral. If the *entire* queue is only
                    # this one group (i.e. it can never be paired), avoid an
                    # infinite loop by leaving it permanently deferred and
                    # reporting it once.
                    conflicts.append(
                        ConflictEvent(
                            type="NO_COMPATIBLE_PAIR",
                            group_key=group_a.group_key,
                            roll_no=anchor.roll_no,
                            block_no=block.block_no,
                            bench_no=bench.bench_no,
                            fallback="DEFERRED",
                            reason="No compatible partner available and single-seat "
                            "fallback is disabled; student left unallocated for now.",
                        )
                    )
                    if _only_group_left(pq, group_a):
                        # No other group will ever appear to pair with —
                        # report as unresolved and stop trying this bench.
                        while not group_a.is_exhausted():
                            student = group_a.pop()
                            conflicts.append(
                                ConflictEvent(
                                    type="UNRESOLVED_NO_PAIR_POSSIBLE",
                                    group_key=group_a.group_key,
                                    roll_no=student.roll_no,
                                    reason="Fallback disabled and no other group remains "
                                    "to pair with; student could not be seated.",
                                )
                            )
                        block_cursor += 1  # move on, this bench stays half-empty
                    else:
                        pq.push(group_a)
                        block_cursor += 1  # avoid retrying the same bench forever
                continue

            # --- Compatible pair found: place both ---
            student_a = group_a.pop()
            student_b = group_b.pop()
            matrix.place(student_a, block, bench, seat_index=first_idx)
            second_idx = bench.open_seat_index()
            matrix.place(student_b, block, bench, seat_index=second_idx)

            if not group_a.is_exhausted():
                pq.push(group_a)
            if not group_b.is_exhausted():
                pq.push(group_b)

    return matrix, conflicts


def _only_group_left(pq: GroupPriorityQueue, excluded: GroupStream) -> bool:
    """True if `excluded` is the only non-exhausted group anywhere in the queue."""
    others = [g for g in pq.peek_all() if g.group_key != excluded.group_key and not g.is_exhausted()]
    return len(others) == 0
