"""
constraints.py — Explicit hard constraints and soft preference scoring.

Hard constraints are predicates that MUST hold for any bench-pairing.
Soft preferences are only ever used to choose between multiple candidates
that already satisfy every hard constraint — they can never override a
hard constraint (see design-amendments, Section 3).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .models import Student, GroupStream


# ---------------------------------------------------------------------------
# Hard constraints (H1-H8, see docs/algorithm.md for the full catalogue;
# H1-H4 and H8 are enforced structurally elsewhere. H5-H7 are enforced here.)
# ---------------------------------------------------------------------------

def satisfies_hard_constraints(student_a: "Student", student_b: "Student") -> bool:
    """
    True only if student_a and student_b may legally share a 2-seater bench.

    H5: different branch
    H6: different class/division
    H7: different academic year/semester
    """
    if student_a.branch == student_b.branch:
        return False
    if student_a.division == student_b.division:
        return False
    if (student_a.year, student_a.semester) == (student_b.year, student_b.semester):
        return False
    return True


def violates_any_hard_constraint(student_a: "Student", student_b: "Student") -> bool:
    """Convenience inverse of satisfies_hard_constraints, for readability at call sites."""
    return not satisfies_hard_constraints(student_a, student_b)


# ---------------------------------------------------------------------------
# Soft preferences — refined per design-amendments Section 3.
#
# The previous "prefer different branch/division/year" preference was
# removed: it is redundant since those are already hard constraints (a
# candidate that reaches this scoring function has already passed them).
#
# The refined hierarchy (highest priority first):
#   1. Prefer the compatible candidate with the highest remaining group size
#      (reduces the risk that a small group is stranded/unpaired later).
#   2. Prefer the candidate that reduces the likelihood of future unmatched
#      students (approximated here by preferring groups whose remaining
#      count, after this allocation, is still comfortably above zero,
#      versus a group about to be exhausted, which is nearly free to place
#      via a 1-seater bench instead).
#   3. Prefer better current bench/seat utilization (not applicable at the
#      single-pair comparison level; handled by the allocator's block/bench
#      selection order, not here).
#   4. Prefer fewer unnecessary block switches (also handled by the
#      allocator's block iteration order).
#   5. Stable deterministic group_key tie-breaker, so identical scores never
#      produce nondeterministic ordering.
# ---------------------------------------------------------------------------

def soft_preference_score(candidate: "GroupStream") -> tuple:
    """
    Returns a sort key (tuple) for ranking compatible candidate GroupStreams.
    Larger tuples (lexicographic) sort as "more preferred" when sorted
    descending. Deterministic: ties are broken by group_key ascending
    (achieved by negating the string comparison via reverse sort behavior
    at the call site — see greedy_allocator.py).
    """
    remaining = candidate.remaining()

    # Preference 1 & 2 collapse into "prefer larger remaining count" — a
    # group with more students left is both less likely to be stranded
    # itself, and by being paired now (rather than a soon-to-be-exhausted
    # group), leaves smaller groups more room to be matched later while
    # they still have partners available.
    primary_score = remaining

    return (primary_score,)


def rank_candidates(candidates: list) -> list:
    """
    Sort a list of compatible GroupStream candidates by soft preference,
    most-preferred first, with a deterministic group_key tie-breaker.
    """
    return sorted(
        candidates,
        key=lambda gs: (-soft_preference_score(gs)[0], gs.group_key),
    )
