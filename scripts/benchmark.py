"""
scripts/benchmark.py — Generates synthetic datasets of varying sizes and
scenario types, runs all three algorithms (Sequential, Sort-Then-Allocate,
Greedy+PQ) on each, and prints a results table.

Run with:  python3 scripts/benchmark.py

Output is also used verbatim to populate docs/test-results.md — numbers
there are copied from an actual run of this script, never invented.
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.baselines import sequential_allocate, sort_then_allocate
from src.greedy_allocator import allocate_seating
from src.models import AllocationConfig, Bench, Block, Student


def make_student(roll_no, branch, division, year, semester="III"):
    return Student(roll_no, f"{branch}{division}-{roll_no}", branch, division, year, semester, "AM-111")


def make_group(n, branch, division, year, semester="III"):
    return [make_student(i, branch, division, year, semester) for i in range(1, n + 1)]


def make_blocks(total_seats, seats_per_bench=2):
    num_benches = (total_seats + seats_per_bench - 1) // seats_per_bench
    per_block = 30
    blocks = []
    remaining = num_benches
    idx = 1
    while remaining > 0:
        n = min(per_block, remaining)
        blocks.append(Block(floor="F", block_no=f"B{idx}", benches=[Bench(i + 1, seats_per_bench) for i in range(n)]))
        remaining -= n
        idx += 1
    return blocks


def _unique_group_tuples(n_groups):
    """
    Deterministic list of `n_groups` DISTINCT (branch, division, year)
    triples, drawn from the full cartesian product so no two synthetic
    groups accidentally collide onto the same group_key (max needed here
    is 5000 // 50 = 100 groups, well under 8*4*4 = 128 possible combos).

    The product is generated branch-major (all divisions/years for one
    branch before moving to the next), which would otherwise make the
    first `divisions * years` groups all share the same branch — an
    unrealistic and needlessly pairing-hostile arrangement for a
    "balanced/compatible" benchmark scenario. A fixed-seed deterministic
    shuffle spreads branches out so adjacent picks are far more often
    mutually compatible, without sacrificing reproducibility.
    """
    import itertools
    import random

    branches = ["Comp", "Elec", "Mech", "Civil", "IT", "AIML", "ENTC", "Chem"]
    years = ["SE", "TE", "BE", "FE"]
    divisions = ["A", "B", "C", "D"]
    combos = list(itertools.product(branches, years, divisions))
    random.Random(42).shuffle(combos)  # fixed seed -> fully reproducible
    if n_groups > len(combos):
        raise ValueError(f"Need {n_groups} distinct groups but only {len(combos)} combos available")
    return combos[:n_groups]


def build_balanced(n_students):
    """Several equal-sized mutually-compatible groups."""
    n_groups = max(2, n_students // 50)
    per_group = n_students // n_groups
    students = []
    for branch, year, division in _unique_group_tuples(n_groups):
        students += make_group(per_group, branch, division, year)
    return students


def build_unbalanced(n_students):
    """One huge group + several small groups (stresses fallback logic)."""
    big = n_students // 2
    rest = n_students - big
    students = make_group(big, "Comp", "B", "SE")
    n_small_groups = max(1, rest // 20)
    per_small = max(1, rest // max(1, n_small_groups))
    # Small groups must never collide with each other or with the big
    # "Comp-SE-B" group — draw distinct (branch, division, year) triples
    # excluding "Comp". Request extra combos since some will be filtered.
    candidate_tuples = _unique_group_tuples(min(128, (n_small_groups + 1) * 3))
    small_tuples = [t for t in candidate_tuples if t[0] != "Comp"][:n_small_groups]
    for branch, year, division in small_tuples:
        students += make_group(per_small, branch, division, year)
    return students[:n_students] if len(students) > n_students else students


SCENARIOS = {
    "balanced": build_balanced,
    "unbalanced": build_unbalanced,
}

SIZES = [50, 100, 250, 500, 1000, 5000]


def run_one(fn, students, blocks, config):
    students_copy = list(students)
    blocks_copy = [Block(b.floor, b.block_no, [Bench(x.bench_no, x.seats_per_bench) for x in b.benches]) for b in blocks]
    start = time.perf_counter()
    matrix, conflicts = fn(students_copy, blocks_copy, config)
    elapsed = time.perf_counter() - start
    total_seats = matrix.total_capacity()
    occupied = matrix.total_occupied()
    util = (occupied / total_seats * 100) if total_seats else 0
    return elapsed, len(conflicts), util


def main():
    config = AllocationConfig()
    print(f"{'Scenario':<12}{'N':>7}{'Algorithm':<20}{'Time(s)':>10}{'Conflicts':>11}{'Util%':>8}")
    print("-" * 70)
    for scenario_name, builder in SCENARIOS.items():
        for n in SIZES:
            students = builder(n)
            blocks = make_blocks(int(len(students) * 1.1))  # ~10% slack capacity

            for algo_name, fn in [
                ("Sequential", sequential_allocate),
                ("SortThenAllocate", sort_then_allocate),
                ("GreedyPQ", allocate_seating),
            ]:
                elapsed, n_conflicts, util = run_one(fn, students, blocks, config)
                print(
                    f"{scenario_name:<12}{len(students):>7}{algo_name:<20}"
                    f"{elapsed:>10.5f}{n_conflicts:>11}{util:>8.1f}"
                )


if __name__ == "__main__":
    main()
