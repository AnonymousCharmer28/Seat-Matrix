"""
priority_queue.py — Max-heap Priority Queue over GroupStreams.

Python's `heapq` is a min-heap, so we store (-remaining_count, group_key,
GroupStream) tuples: negating remaining_count turns it into max-heap
behavior, and group_key is a deterministic tie-breaker so heap comparisons
never fall through to comparing GroupStream objects directly (which have
no ordering defined).
"""

from __future__ import annotations

import heapq
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import GroupStream


class GroupPriorityQueue:
    """
    Max-heap keyed on GroupStream.remaining(), with a stable group_key
    tie-breaker for full determinism.
    """

    def __init__(self):
        self._heap: List[tuple] = []

    def __len__(self) -> int:
        return len(self._heap)

    def is_empty(self) -> bool:
        return len(self._heap) == 0

    def push(self, group: "GroupStream") -> None:
        """Insert (or re-insert) a group. O(log K)."""
        if group.is_exhausted():
            return  # never queue an exhausted stream
        heapq.heappush(self._heap, (-group.remaining(), group.group_key, group))

    def pop_max(self) -> Optional["GroupStream"]:
        """Remove and return the highest-remaining-count group. O(log K)."""
        if self.is_empty():
            return None
        _, _, group = heapq.heappop(self._heap)
        return group

    def drain_all(self) -> List["GroupStream"]:
        """
        Remove and return ALL groups currently queued, as a plain list.
        Used by the compatible-group search, which needs to scan every
        active group without permanently losing heap contents.
        """
        groups = [entry[2] for entry in self._heap]
        self._heap = []
        return groups

    def rebuild(self, groups: List["GroupStream"]) -> None:
        """Rebuild the heap from a list of groups (drops exhausted ones)."""
        self._heap = []
        for group in groups:
            self.push(group)

    def peek_all(self) -> List["GroupStream"]:
        """Non-destructive view of all queued groups (for reporting/UI)."""
        return [entry[2] for entry in self._heap]
