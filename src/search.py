"""
search.py — Student lookup over an already-built SeatingMatrix.

Search is read-only and never mutates the matrix or the underlying
students/blocks.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from .seating_matrix import SeatingMatrix


def search_students(
    matrix: SeatingMatrix,
    name: Optional[str] = None,
    roll_no: Optional[int] = None,
    branch: Optional[str] = None,
    division: Optional[str] = None,
) -> List[dict]:
    """
    Return matching placements as a list of dicts:
    {student, floor, block_no, bench_no, seat_index}

    All provided filters are combined with AND. Name/branch/division
    matches are case-insensitive substring matches; roll_no is exact.
    """
    results = []
    for student, (floor, block_no, bench_no, seat_idx) in matrix.all_placements():
        if name and name.strip().lower() not in student.name.lower():
            continue
        if roll_no is not None and student.roll_no != roll_no:
            continue
        if branch and branch.strip().lower() not in student.branch.lower():
            continue
        if division and division.strip().lower() not in student.division.lower():
            continue

        results.append(
            {
                "student": student,
                "floor": floor,
                "block_no": block_no,
                "bench_no": bench_no,
                "seat_index": seat_idx,
            }
        )
    return results
