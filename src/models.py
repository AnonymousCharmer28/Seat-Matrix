"""
models.py — Core domain entities for SeatMatrix.

This module has ZERO dependencies on UI, file I/O, or pandas. It only
defines plain Python data structures used by the algorithm core, so the
core stays independently testable (see docs/algorithm.md, Section: Layered
Architecture).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Student
# ---------------------------------------------------------------------------

@dataclass
class Student:
    """A single student record."""

    roll_no: int
    name: str
    branch: str
    division: str
    year: str          # e.g. "SE", "TE", "BE", "FE"
    semester: str
    subject: str

    @property
    def group_key(self) -> str:
        """
        Derived academic-group identifier.

        Example: branch="Comp", year="SE", division="B" -> "Comp-SE-B"
        This is the key used to build GroupStreams and is the unit the
        Priority Queue operates on.
        """
        return f"{self.branch}-{self.year}-{self.division}"

    def as_dict(self) -> dict:
        return {
            "roll_no": self.roll_no,
            "name": self.name,
            "branch": self.branch,
            "division": self.division,
            "year": self.year,
            "semester": self.semester,
            "subject": self.subject,
            "group_key": self.group_key,
        }


# ---------------------------------------------------------------------------
# Bench / Block
# ---------------------------------------------------------------------------

@dataclass
class Bench:
    """A single bench inside a block. seats_per_bench is 1 or 2."""

    bench_no: int
    seats_per_bench: int
    seats: List[Optional[Student]] = field(default_factory=list)
    fallback_closed: bool = False
    """
    True once this bench has received a SINGLE_SEAT_FALLBACK placement.

    Per the documented fallback policy, the second seat of such a bench is
    deliberately left empty and must never be filled afterwards by an
    unrelated later pairing decision — closing the bench (rather than
    treating it as merely "not full") is what keeps that guarantee intact
    even though `next_open_bench()` scans by seat-occupancy.
    """

    def __post_init__(self):
        if self.seats_per_bench not in (1, 2):
            raise ValueError(
                f"Bench {self.bench_no}: seats_per_bench must be 1 or 2, "
                f"got {self.seats_per_bench}"
            )
        if not self.seats:
            self.seats = [None] * self.seats_per_bench

    def is_full(self) -> bool:
        return all(seat is not None for seat in self.seats)

    def is_empty(self) -> bool:
        return all(seat is None for seat in self.seats)

    def is_available_for_allocation(self) -> bool:
        """True if this bench can still receive a NEW placement decision."""
        return not self.is_full() and not self.fallback_closed

    def open_seat_index(self) -> Optional[int]:
        """Return the index of the first empty seat, or None if full."""
        for idx, seat in enumerate(self.seats):
            if seat is None:
                return idx
        return None


@dataclass
class Block:
    """An examination room/block containing benches."""

    floor: str
    block_no: str
    benches: List[Bench]

    @property
    def capacity(self) -> int:
        return sum(b.seats_per_bench for b in self.benches)

    @property
    def occupied_count(self) -> int:
        return sum(
            1 for bench in self.benches for seat in bench.seats if seat is not None
        )

    def next_open_bench(self) -> Optional[Bench]:
        """
        Return the first bench (in bench_no order) that is available for a
        NEW allocation decision — i.e. not full AND not closed by an
        earlier single-seat fallback (see Bench.is_available_for_allocation).
        Returns None if no such bench remains.

        Iterating in a fixed sorted order (rather than dict/set order) is
        part of the determinism guarantee (see docs/algorithm.md).
        """
        for bench in sorted(self.benches, key=lambda b: b.bench_no):
            if bench.is_available_for_allocation():
                return bench
        return None

    def is_full(self) -> bool:
        """
        A block is considered "full" for allocation purposes once every
        bench is either physically full OR permanently closed by fallback
        — a half-empty fallback-closed bench does not offer more capacity.
        """
        return all(not b.is_available_for_allocation() for b in self.benches)


# ---------------------------------------------------------------------------
# GroupStream — the Sequential Allocation Invariant lives here
# ---------------------------------------------------------------------------

@dataclass
class GroupStream:
    """
    Wraps a single academic group's students as an ordered, pointer-based
    stream.

    SEQUENTIAL ALLOCATION INVARIANT (see docs/algorithm.md):
      * `students` is sorted by roll_no ascending once, at construction,
        and is NEVER reordered afterwards.
      * Only `students[pointer]` may ever be consumed.
      * `pointer` only ever increases, and only via `pop()`.
      * `peek()` never advances the pointer — it is safe to call any
        number of times during compatibility search without side effects.
      * If student i+1 is allocated, student i must already have been
        allocated (guaranteed structurally: pop() always returns
        students[pointer] then increments pointer by exactly 1 — there is
        no code path that advances pointer by more than 1 or reads any
        index other than `pointer`).
    """

    group_key: str
    students: List[Student]
    pointer: int = 0

    def __post_init__(self):
        # Enforce sorted order once, at construction time only.
        self.students = sorted(self.students, key=lambda s: s.roll_no)

    def remaining(self) -> int:
        return len(self.students) - self.pointer

    def is_exhausted(self) -> bool:
        return self.remaining() <= 0

    def peek(self) -> Optional[Student]:
        """Look at (but do not consume) the next student in sequence."""
        if self.is_exhausted():
            return None
        return self.students[self.pointer]

    def pop(self) -> Student:
        """
        Consume and return the next student in sequence.

        Raises if the stream is already exhausted — callers must check
        `peek()` / `is_exhausted()` first; pop() must never be called
        speculatively during candidate search.
        """
        if self.is_exhausted():
            raise IndexError(f"GroupStream '{self.group_key}' is exhausted")
        student = self.students[self.pointer]
        self.pointer += 1
        return student


# ---------------------------------------------------------------------------
# Allocation configuration
# ---------------------------------------------------------------------------

@dataclass
class AllocationConfig:
    """
    Configurable knobs for the greedy allocator. Defaults reflect the
    approved v1 policy (see design-amendments, Section 2).
    """

    allow_single_seat_fallback: bool = True
    preserve_roll_sequence: bool = True   # documents the invariant; must stay True
    pairing_enabled: bool = True
    preferred_block_order: Optional[List[str]] = None  # list of block_no, desired order

    def __post_init__(self):
        if not self.preserve_roll_sequence:
            raise ValueError(
                "preserve_roll_sequence is a hard invariant of SeatMatrix "
                "and cannot be disabled."
            )


# ---------------------------------------------------------------------------
# Conflict / event records
# ---------------------------------------------------------------------------

@dataclass
class ConflictEvent:
    """A recorded conflict or fallback event during allocation."""

    type: str                      # e.g. "NO_COMPATIBLE_PAIR", "NO_BLOCK_CAPACITY"
    group_key: Optional[str] = None
    roll_no: Optional[int] = None
    block_no: Optional[str] = None
    bench_no: Optional[int] = None
    fallback: Optional[str] = None  # e.g. "SINGLE_SEAT_FALLBACK", "DEFERRED"
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "type": self.type,
            "group_key": self.group_key,
            "roll_no": self.roll_no,
            "block_no": self.block_no,
            "bench_no": self.bench_no,
            "fallback": self.fallback,
            "reason": self.reason,
        }
