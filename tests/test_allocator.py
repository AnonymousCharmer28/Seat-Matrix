import unittest

from src.greedy_allocator import allocate_seating
from src.models import AllocationConfig, Bench, Block, Student


def student(roll_no, branch, division, year, semester="III", subject="AM-111"):
    return Student(roll_no=roll_no, name=f"{branch}{division}{year}-{roll_no}", branch=branch,
                   division=division, year=year, semester=semester, subject=subject)


def group(n, branch, division, year, semester="III"):
    return [student(i, branch, division, year, semester) for i in range(1, n + 1)]


def two_seat_block(block_no, num_benches, floor="Ground"):
    return Block(floor=floor, block_no=block_no, benches=[Bench(i + 1, 2) for i in range(num_benches)])


def one_seat_block(block_no, num_benches, floor="Ground"):
    return Block(floor=floor, block_no=block_no, benches=[Bench(i + 1, 1) for i in range(num_benches)])


class TestAllocatorScenarios(unittest.TestCase):
    def test_1_two_compatible_groups_equal_size(self):
        students = group(5, "Comp", "B", "SE") + group(5, "Elec", "A", "TE")
        blocks = [two_seat_block("501", 5)]
        matrix, conflicts = allocate_seating(students, blocks)
        self.assertEqual(matrix.total_occupied(), 10)
        self.assertEqual(len(conflicts), 0)

    def test_2_unequal_group_sizes_triggers_fallback(self):
        # Comp=5, Elec=3 -> after Elec runs out, 2 Comp students go single-seat.
        students = group(5, "Comp", "B", "SE") + group(3, "Elec", "A", "TE")
        blocks = [two_seat_block("501", 5)]
        matrix, conflicts = allocate_seating(students, blocks)
        self.assertEqual(matrix.total_occupied(), 8)
        fallback_events = [c for c in conflicts if c.fallback == "SINGLE_SEAT_FALLBACK"]
        self.assertEqual(len(fallback_events), 2)

    def test_3_more_groups_than_benches_uses_third_compatible_group(self):
        # Three mutually-compatible groups; only enough benches for two pairs
        # per round, so PQ should keep rotating the highest-remaining group in.
        students = group(4, "Comp", "B", "SE") + group(4, "Elec", "A", "TE") + group(4, "Mech", "C", "BE")
        blocks = [two_seat_block("501", 6)]
        matrix, conflicts = allocate_seating(students, blocks)
        self.assertEqual(matrix.total_occupied(), 12)
        self.assertEqual(len(conflicts), 0)

    def test_4_more_students_than_total_capacity(self):
        students = group(10, "Comp", "B", "SE") + group(10, "Elec", "A", "TE")
        blocks = [two_seat_block("501", 5)]  # only 10 seats for 20 students
        matrix, conflicts = allocate_seating(students, blocks)
        self.assertEqual(matrix.total_occupied(), 10)
        no_capacity = [c for c in conflicts if c.type == "NO_BLOCK_CAPACITY"]
        self.assertEqual(len(no_capacity), 10)

    def test_5_only_incompatible_groups_remaining_with_fallback(self):
        # Two groups from the SAME branch: can never be paired together.
        students = group(3, "Comp", "B", "SE") + group(3, "Comp", "A", "TE")
        blocks = [two_seat_block("501", 6)]
        config = AllocationConfig(allow_single_seat_fallback=True)
        matrix, conflicts = allocate_seating(students, blocks, config)
        self.assertEqual(matrix.total_occupied(), 6)  # everyone seated alone
        fallback_events = [c for c in conflicts if c.fallback == "SINGLE_SEAT_FALLBACK"]
        self.assertEqual(len(fallback_events), 6)

    def test_6_single_seat_benches_no_pairing_needed(self):
        students = group(5, "Comp", "B", "SE")
        blocks = [one_seat_block("003", 5)]
        matrix, conflicts = allocate_seating(students, blocks)
        self.assertEqual(matrix.total_occupied(), 5)
        self.assertEqual(len(conflicts), 0)

    def test_7_two_seat_benches_successful_pairing(self):
        students = group(3, "Comp", "B", "SE") + group(3, "Elec", "A", "TE")
        blocks = [two_seat_block("501", 3)]
        matrix, conflicts = allocate_seating(students, blocks)
        self.assertEqual(len(conflicts), 0)
        for _, (floor, block_no, bench_no, seat_idx) in matrix.all_placements():
            pass  # existence check only; pairing correctness checked in demo test below

    def test_8_two_seat_benches_requiring_fallback(self):
        students = group(1, "Comp", "B", "SE")  # alone, no possible partner ever
        blocks = [two_seat_block("501", 1)]
        matrix, conflicts = allocate_seating(students, blocks)
        self.assertEqual(matrix.total_occupied(), 1)
        self.assertEqual(conflicts[0].fallback, "SINGLE_SEAT_FALLBACK")

    def test_9_fallback_disabled_defers_instead_of_pairing(self):
        students = group(1, "Comp", "B", "SE")
        blocks = [two_seat_block("501", 1)]
        config = AllocationConfig(allow_single_seat_fallback=False)
        matrix, conflicts = allocate_seating(students, blocks, config)
        self.assertEqual(matrix.total_occupied(), 0)  # never force-paired
        self.assertTrue(any(c.type == "UNRESOLVED_NO_PAIR_POSSIBLE" for c in conflicts))

    def test_10_multiple_blocks_used_in_order(self):
        students = group(4, "Comp", "B", "SE") + group(4, "Elec", "A", "TE")
        blocks = [two_seat_block("101", 2, floor="First"), two_seat_block("102", 2, floor="First")]
        matrix, conflicts = allocate_seating(students, blocks)
        self.assertEqual(matrix.total_occupied(), 8)
        self.assertEqual(matrix.blocks_used(), 2)

    def test_11_block_exhaustion_moves_to_next_block(self):
        students = group(6, "Comp", "B", "SE") + group(6, "Elec", "A", "TE")
        blocks = [two_seat_block("101", 2), two_seat_block("102", 4)]
        matrix, conflicts = allocate_seating(students, blocks)
        self.assertEqual(matrix.total_occupied(), 12)
        self.assertEqual(len(conflicts), 0)

    def test_12_sequential_roll_number_preservation(self):
        students = group(5, "Comp", "B", "SE") + group(5, "Elec", "A", "TE")
        blocks = [two_seat_block("501", 5)]
        matrix, _ = allocate_seating(students, blocks)

        comp_rolls = []
        elec_rolls = []
        for student, (_, _, bench_no, seat_idx) in sorted(
            matrix.all_placements(), key=lambda p: (p[1][2], p[1][3])
        ):
            if student.branch == "Comp":
                comp_rolls.append(student.roll_no)
            else:
                elec_rolls.append(student.roll_no)

        self.assertEqual(comp_rolls, sorted(comp_rolls))
        self.assertEqual(elec_rolls, sorted(elec_rolls))
        self.assertEqual(comp_rolls, [1, 2, 3, 4, 5])
        self.assertEqual(elec_rolls, [1, 2, 3, 4, 5])

    def test_14_empty_input(self):
        matrix, conflicts = allocate_seating([], [two_seat_block("501", 5)])
        self.assertEqual(matrix.total_occupied(), 0)
        self.assertEqual(len(conflicts), 0)

    def test_15_one_student_input(self):
        students = [student(1, "Comp", "B", "SE")]
        matrix, conflicts = allocate_seating(students, [one_seat_block("003", 1)])
        self.assertEqual(matrix.total_occupied(), 1)

    def test_16_one_group_only_input_two_seater_forces_fallback(self):
        students = group(4, "Comp", "B", "SE")
        blocks = [two_seat_block("501", 4)]
        matrix, conflicts = allocate_seating(students, blocks)
        self.assertEqual(matrix.total_occupied(), 4)
        self.assertTrue(all(c.fallback == "SINGLE_SEAT_FALLBACK" for c in conflicts))

    def test_17_deterministic_repeated_runs(self):
        students = group(6, "Comp", "B", "SE") + group(4, "Elec", "A", "TE") + group(5, "Mech", "C", "BE")
        blocks = [two_seat_block("501", 8)]

        def run():
            m, c = allocate_seating(list(students), [two_seat_block("501", 8)])
            return sorted(
                (s.group_key, s.roll_no, loc) for s, loc in m.all_placements()
            )

        self.assertEqual(run(), run())


class TestDemonstrationScenario(unittest.TestCase):
    """
    Required demonstration scenario (design-amendments):
    Comp-SE-B: 1..5, Elec-TE-A: 1..5, all 2-seat benches, no other groups.
    Expect exact roll-for-roll pairing.
    """

    def test_exact_roll_for_roll_pairing(self):
        students = group(5, "Comp", "B", "SE") + group(5, "Elec", "A", "TE")
        blocks = [two_seat_block("501", 5)]
        matrix, conflicts = allocate_seating(students, blocks)

        self.assertEqual(len(conflicts), 0)

        by_bench = {}
        for s, (_, _, bench_no, seat_idx) in matrix.all_placements():
            by_bench.setdefault(bench_no, {})[seat_idx] = s

        for bench_no in range(1, 6):
            seat_a = by_bench[bench_no][0]
            seat_b = by_bench[bench_no][1]
            comp_side = seat_a if seat_a.branch == "Comp" else seat_b
            elec_side = seat_b if seat_a.branch == "Comp" else seat_a
            self.assertEqual(comp_side.roll_no, bench_no)
            self.assertEqual(elec_side.roll_no, bench_no)


    def test_18_fallback_closed_bench_never_reused_for_a_new_pair(self):
        """
        Regression test using the actual dataset that originally triggered
        this bug during benchmarking (unbalanced, N=2000): once a 2-seater
        bench receives a SINGLE_SEAT_FALLBACK placement, its second seat
        must stay permanently empty, never later filled by an unrelated
        pairing decision. Verified two ways: (a) allocation completes
        without error, and (b) every fallback-closed bench has EXACTLY one
        occupied seat, never two.
        """
        import sys
        import os

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from scripts.benchmark import build_unbalanced, make_blocks

        students = build_unbalanced(2000)
        blocks = make_blocks(int(len(students) * 1.1))

        matrix, conflicts = allocate_seating(students, blocks)  # must not raise

        fallback_closed_benches = [
            bench
            for block in blocks
            for bench in block.benches
            if bench.fallback_closed
        ]
        self.assertGreater(len(fallback_closed_benches), 0, "Expected at least one fallback in this scenario")
        for bench in fallback_closed_benches:
            occupied = sum(1 for seat in bench.seats if seat is not None)
            self.assertEqual(
                occupied, 1,
                f"Fallback-closed bench {bench.bench_no} should have exactly 1 "
                f"occupied seat, found {occupied}",
            )


if __name__ == "__main__":
    unittest.main()
