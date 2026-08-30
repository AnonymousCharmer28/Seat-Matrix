"""
seating_matrix.py — Physical seating grid + bidirectional lookup indexes.

Represents:  Block -> Bench -> Seat
Supports O(1):
    Student -> (floor, block_no, bench_no, seat_index)
    (floor, block_no, bench_no, seat_index) -> Student
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Block, Student

Location = Tuple[str, str, int, int]  # (floor, block_no, bench_no, seat_index)


class SeatingMatrix:
    """
    Wraps the list of Blocks (already containing Benches/Seats) and
    maintains the reverse-lookup indexes used by search.py and exporters.py.
    """

    def __init__(self, blocks: List["Block"]):
        self.blocks: List["Block"] = blocks
        self._block_by_no: Dict[str, "Block"] = {b.block_no: b for b in blocks}

        # roll_no + group_key uniquely identifies a student (roll numbers
        # repeat across groups, e.g. every class has a roll #1).
        self._student_to_location: Dict[Tuple[str, int], Location] = {}
        self._location_to_student: Dict[Location, "Student"] = {}

    # -- Placement -----------------------------------------------------

    def place(self, student: "Student", block: "Block", bench, seat_index: int) -> None:
        """
        Occupy a specific seat with a specific student.

        Hard-constraint H1/H2 enforcement point: raises if the seat is
        already occupied (H2) — the allocator must never call place() on
        an occupied seat, and never call it twice for the same student (H1).
        """
        if bench.seats[seat_index] is not None:
            raise ValueError(
                f"Seat already occupied: block={block.block_no} "
                f"bench={bench.bench_no} seat={seat_index}"
            )

        key = (student.group_key, student.roll_no)
        if key in self._student_to_location:
            raise ValueError(
                f"Student already allocated: {student.name} "
                f"(roll {student.roll_no}, group {student.group_key})"
            )

        bench.seats[seat_index] = student
        location: Location = (block.floor, block.block_no, bench.bench_no, seat_index)
        self._student_to_location[key] = location
        self._location_to_student[location] = student

    # -- Lookups ---------------------------------------------------------

    def locate_student(self, group_key: str, roll_no: int) -> Optional[Location]:
        return self._student_to_location.get((group_key, roll_no))

    def student_at(self, location: Location) -> Optional["Student"]:
        return self._location_to_student.get(location)

    def all_placements(self) -> List[Tuple["Student", Location]]:
        """Every (student, location) pair currently placed, for exporters."""
        result = []
        for block in self.blocks:
            for bench in sorted(block.benches, key=lambda b: b.bench_no):
                for seat_idx, student in enumerate(bench.seats):
                    if student is not None:
                        loc = (block.floor, block.block_no, bench.bench_no, seat_idx)
                        result.append((student, loc))
        return result

    # -- Stats -------------------------------------------------------------

    def total_capacity(self) -> int:
        return sum(b.capacity for b in self.blocks)

    def total_occupied(self) -> int:
        return sum(b.occupied_count for b in self.blocks)

    def blocks_used(self) -> int:
        return sum(1 for b in self.blocks if b.occupied_count > 0)

    def benches_used(self) -> int:
        return sum(
            1
            for b in self.blocks
            for bench in b.benches
            if not bench.is_empty()
        )
