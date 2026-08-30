import unittest

from src.models import GroupStream, Student
from src.priority_queue import GroupPriorityQueue


def s(roll_no, branch="Comp", division="B", year="SE", semester="III"):
    return Student(roll_no=roll_no, name=f"S{roll_no}", branch=branch, division=division,
                   year=year, semester=semester, subject="AM-111")


class TestGroupStream(unittest.TestCase):
    def test_peek_does_not_advance_pointer(self):
        gs = GroupStream("G", [s(1), s(2), s(3)])
        self.assertEqual(gs.peek().roll_no, 1)
        self.assertEqual(gs.peek().roll_no, 1)  # still 1 — peek is side-effect free
        self.assertEqual(gs.pointer, 0)

    def test_pop_advances_pointer_by_exactly_one(self):
        gs = GroupStream("G", [s(1), s(2), s(3)])
        first = gs.pop()
        self.assertEqual(first.roll_no, 1)
        self.assertEqual(gs.pointer, 1)
        second = gs.pop()
        self.assertEqual(second.roll_no, 2)
        self.assertEqual(gs.pointer, 2)

    def test_strict_sequential_consumption_order(self):
        gs = GroupStream("G", [s(5), s(1), s(3)])  # constructed out of order
        # __post_init__ must sort by roll_no regardless of input order.
        seen = [gs.pop().roll_no for _ in range(3)]
        self.assertEqual(seen, [1, 3, 5])

    def test_pop_on_exhausted_raises(self):
        gs = GroupStream("G", [s(1)])
        gs.pop()
        with self.assertRaises(IndexError):
            gs.pop()

    def test_empty_stream(self):
        gs = GroupStream("G", [])
        self.assertTrue(gs.is_exhausted())
        self.assertIsNone(gs.peek())


class TestGroupPriorityQueue(unittest.TestCase):
    def test_max_priority_behavior(self):
        pq = GroupPriorityQueue()
        small = GroupStream("Small", [s(1), s(2)])
        big = GroupStream("Big", [s(i) for i in range(1, 10)])
        pq.push(small)
        pq.push(big)
        top = pq.pop_max()
        self.assertEqual(top.group_key, "Big")

    def test_tie_breaking_deterministic(self):
        pq = GroupPriorityQueue()
        a = GroupStream("Bravo", [s(1)])
        b = GroupStream("Alpha", [s(1)])
        pq.push(a)
        pq.push(b)
        top = pq.pop_max()
        self.assertEqual(top.group_key, "Alpha")  # equal remaining -> alphabetical

    def test_reinsertion_after_partial_consumption(self):
        pq = GroupPriorityQueue()
        g = GroupStream("G", [s(1), s(2), s(3)])
        pq.push(g)
        popped = pq.pop_max()
        popped.pop()
        pq.push(popped)
        self.assertEqual(len(pq), 1)
        self.assertEqual(pq.peek_all()[0].remaining(), 2)

    def test_exhausted_group_never_requeued(self):
        pq = GroupPriorityQueue()
        g = GroupStream("G", [s(1)])
        g.pop()
        pq.push(g)  # should be silently ignored
        self.assertTrue(pq.is_empty())

    def test_deterministic_repeated_runs(self):
        def build_and_drain():
            pq = GroupPriorityQueue()
            pq.push(GroupStream("A", [s(1), s(2)]))
            pq.push(GroupStream("B", [s(1), s(2), s(3)]))
            pq.push(GroupStream("C", [s(1), s(2)]))
            order = []
            while not pq.is_empty():
                order.append(pq.pop_max().group_key)
            return order

        self.assertEqual(build_and_drain(), build_and_drain())


if __name__ == "__main__":
    unittest.main()
