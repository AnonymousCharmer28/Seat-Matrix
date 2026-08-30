import unittest

import pandas as pd

from src.greedy_allocator import allocate_seating
from src.input_parser import (
    has_blocking_errors,
    validate_blocks_df,
    validate_students_df,
)
from src.models import AllocationConfig, Bench, Block, Student


def student(roll_no, branch, division, year, semester="III", subject="AM-111", name=None):
    return Student(roll_no=roll_no, name=name or f"{branch}{division}{year}-{roll_no}",
                   branch=branch, division=division, year=year, semester=semester, subject=subject)


class TestValidation(unittest.TestCase):
    def test_13_duplicate_roll_numbers_detected(self):
        df = pd.DataFrame(
            {
                "Student Name": ["A", "B"],
                "Roll No": [1, 1],
                "Branch": ["Comp", "Comp"],
                "Division": ["B", "B"],
                "Year": ["SE", "SE"],
                "Semester": ["III", "III"],
                "Subject": ["AM-111", "AM-111"],
            }
        )
        issues = validate_students_df(df)
        self.assertTrue(any("Duplicate roll number" in i.message for i in issues))
        self.assertTrue(has_blocking_errors(issues))

    def test_missing_roll_number(self):
        df = pd.DataFrame(
            {
                "Student Name": ["A"],
                "Roll No": [None],
                "Branch": ["Comp"],
                "Division": ["B"],
                "Year": ["SE"],
                "Semester": ["III"],
                "Subject": ["AM-111"],
            }
        )
        issues = validate_students_df(df)
        self.assertTrue(any("Missing roll number" in i.message for i in issues))

    def test_missing_branch(self):
        df = pd.DataFrame(
            {
                "Student Name": ["A"],
                "Roll No": [1],
                "Branch": [None],
                "Division": ["B"],
                "Year": ["SE"],
                "Semester": ["III"],
                "Subject": ["AM-111"],
            }
        )
        issues = validate_students_df(df)
        self.assertTrue(any("Missing branch" in i.message for i in issues))

    def test_missing_required_column_reports_and_stops(self):
        df = pd.DataFrame({"Student Name": ["A"]})
        issues = validate_students_df(df)
        self.assertTrue(has_blocking_errors(issues))

    def test_invalid_seat_count(self):
        df = pd.DataFrame(
            {"Floor": ["G"], "Block No": ["003"], "Benches": [10], "Seats Per Bench": [3]}
        )
        issues = validate_blocks_df(df)
        self.assertTrue(any("Seats per bench must be 1 or 2" in i.message for i in issues))

    def test_negative_bench_count(self):
        df = pd.DataFrame(
            {"Floor": ["G"], "Block No": ["003"], "Benches": [-5], "Seats Per Bench": [1]}
        )
        issues = validate_blocks_df(df)
        self.assertTrue(any("Invalid/negative bench count" in i.message for i in issues))

    def test_duplicate_block_identifier(self):
        df = pd.DataFrame(
            {
                "Floor": ["G", "First"],
                "Block No": ["003", "003"],
                "Benches": [10, 5],
                "Seats Per Bench": [1, 2],
            }
        )
        issues = validate_blocks_df(df)
        self.assertTrue(any("Duplicate block identifier" in i.message for i in issues))


class TestConfig(unittest.TestCase):
    def test_preserve_roll_sequence_cannot_be_disabled(self):
        with self.assertRaises(ValueError):
            AllocationConfig(preserve_roll_sequence=False)


class TestMixedBlockTypes(unittest.TestCase):
    def test_mixed_one_and_two_seater_blocks(self):
        students = (
            [student(i, "Comp", "B", "SE") for i in range(1, 4)]
            + [student(i, "Elec", "A", "TE") for i in range(1, 4)]
        )
        blocks = [
            Block(floor="G", block_no="003", benches=[Bench(1, 1), Bench(2, 1)]),
            Block(floor="First", block_no="101", benches=[Bench(1, 2), Bench(2, 2)]),
        ]
        matrix, conflicts = allocate_seating(students, blocks)
        self.assertEqual(matrix.total_occupied(), 6)


class TestOddCounts(unittest.TestCase):
    def test_odd_number_of_students_in_single_group(self):
        students = [student(i, "Comp", "B", "SE") for i in range(1, 8)]  # 7 students
        blocks = [Block(floor="G", block_no="003", benches=[Bench(i + 1, 1) for i in range(7)])]
        matrix, conflicts = allocate_seating(students, blocks)
        self.assertEqual(matrix.total_occupied(), 7)
        self.assertEqual(len(conflicts), 0)


if __name__ == "__main__":
    unittest.main()
