import unittest

from src.constraints import satisfies_hard_constraints, rank_candidates
from src.models import GroupStream, Student


def s(roll_no, branch, division, year, semester, name="X", subject="AM-111"):
    return Student(roll_no=roll_no, name=name, branch=branch, division=division,
                   year=year, semester=semester, subject=subject)


class TestHardConstraints(unittest.TestCase):
    def test_compatible_different_everything(self):
        a = s(1, "Comp", "B", "SE", "III")
        b = s(1, "Elec", "A", "TE", "V")
        self.assertTrue(satisfies_hard_constraints(a, b))

    def test_h5_same_branch_rejected(self):
        a = s(1, "Comp", "B", "SE", "III")
        b = s(1, "Comp", "A", "TE", "V")
        self.assertFalse(satisfies_hard_constraints(a, b))

    def test_h6_same_division_rejected(self):
        a = s(1, "Comp", "B", "SE", "III")
        b = s(1, "Elec", "B", "TE", "V")
        self.assertFalse(satisfies_hard_constraints(a, b))

    def test_h7_same_year_semester_rejected(self):
        a = s(1, "Comp", "B", "SE", "III")
        b = s(1, "Elec", "A", "SE", "III")
        self.assertFalse(satisfies_hard_constraints(a, b))

    def test_h7_same_year_different_semester_is_allowed(self):
        # Year alone matching is not sufficient to reject: the constraint is
        # on the (year, semester) pair.
        a = s(1, "Comp", "B", "SE", "III")
        b = s(1, "Elec", "A", "SE", "IV")
        self.assertTrue(satisfies_hard_constraints(a, b))

    def test_symmetry(self):
        a = s(1, "Comp", "B", "SE", "III")
        b = s(1, "Elec", "A", "TE", "V")
        self.assertEqual(
            satisfies_hard_constraints(a, b), satisfies_hard_constraints(b, a)
        )


class TestSoftPreferenceRanking(unittest.TestCase):
    def test_prefers_larger_remaining_group(self):
        small = GroupStream("Elec-TE-A", [s(i, "Elec", "A", "TE", "V") for i in range(1, 3)])
        large = GroupStream("Comp-SE-B", [s(i, "Comp", "B", "SE", "III") for i in range(1, 10)])
        ranked = rank_candidates([small, large])
        self.assertEqual(ranked[0].group_key, "Comp-SE-B")

    def test_deterministic_tiebreak_by_group_key(self):
        a = GroupStream("Bravo-SE-A", [s(1, "Bravo", "A", "SE", "III")])
        b = GroupStream("Alpha-SE-A", [s(1, "Alpha", "A", "SE", "III")])
        ranked = rank_candidates([a, b])
        # Equal remaining() (both 1) -> alphabetically first group_key wins.
        self.assertEqual(ranked[0].group_key, "Alpha-SE-A")


if __name__ == "__main__":
    unittest.main()
