# SeatMatrix — Complexity Analysis

## Variable Definitions

- **N** = total number of students
- **K** = number of distinct academic groups (K ≪ N in practice — bounded
  by the number of branch × year × division × ... combinations a college
  actually runs, typically tens, not thousands)
- **B** = number of blocks
- **S** = total physical seat capacity across all blocks

## Operation-Level Complexity

| Operation | Complexity | Notes |
|---|---|---|
| Parse + validate input | O(N) | Single pass per row (`input_parser.validate_students_df`) |
| Group students by group_key | O(N) | Hash-map grouping (`_group_students`) |
| Sort each group by roll number | O(N log N) worst case | Sum over groups of `nᵢ log nᵢ`; `GroupStream.__post_init__` |
| Build initial max-heap | O(K log K) | K insertions into `GroupPriorityQueue` |
| Pop max-priority group | O(log K) | `heapq.heappop` |
| Push group back after consuming | O(log K) | `heapq.heappush` |
| Find compatible group (one pairing decision) | O(K) worst case | `find_compatible_group` drains + rescans up to K groups |
| Total pairing decisions | O(N / 2) worst case | One per bench-pair, at most |
| **Overall allocation (Approach 3)** | **O(N log N + N·K)** | Sorting term + pairing-search term |
| Seat placement | O(1) amortized | `SeatingMatrix.place()` — direct dict/list write |
| Student → Location search | O(1) | Precomputed `dict[(group_key, roll_no)] → location` |
| Output generation (all reports) | O(N + S) | Single pass over placements (`exporters.py`) |

## Overall Complexity — Approach 3 (Greedy + Priority Queue)

```
Time:  O(N log N + N·K)
Space: O(N + S)
```

## Best / Average / Worst Case Discussion

- **Best case:** all active groups are mutually compatible and evenly
  sized. The pairing search (`find_compatible_group`) still scans up to K
  candidates in the worst case per call, but when a compatible candidate
  is found near the beginning of the candidate scan (a common case when
  most groups qualify), the *practical* cost approaches O(1) per pairing
  decision — making total runtime close to **O(N log N)**, dominated by
  the initial sort. We do **not** claim the search itself is O(1); only
  that its *practical* cost is often much lower than its O(K) worst case.

- **Worst case:** groups become mutually incompatible near the end of
  allocation (e.g., only two groups remain and they share a branch). Each
  remaining pairing decision then costs the full O(K) scan, and the
  **O(N·K)** term dominates. This remains practical in real college
  settings because K stays small (tens of groups) even as N scales into
  the thousands — confirmed empirically in `docs/test-results.md`.

- **Average case:** meaningful only relative to a specific distribution of
  group sizes/compatibility; not derived analytically here — the measured
  benchmark results in `docs/test-results.md` serve as the empirical
  average-case evidence for realistic, moderately unbalanced inputs.

## Space Complexity

```
O(N + S)
```

One `Student` record per student, one seat slot per physical seat
(`Bench.seats`), plus O(K) for the priority queue and its temporary
drain/rebuild buffer during a pairing decision.

## Baseline Comparison

| Approach | Time Complexity | Adaptive re-prioritization? | Partner selection |
|---|---|---|---|
| 1 — Sequential | O(N·K) worst case (linear scan per pairing decision, fixed group order) | No | First compatible group found |
| 2 — Sort-Then-Allocate | O(K log K + N·K) worst case (one sort, then linear scans) | No — order fixed after initial sort | First compatible group found, in static order |
| 3 — Greedy + Priority Queue | O(N log N + N·K) | **Yes** — heap re-ranks by *current* remaining count after every allocation | *Best* (highest-remaining) compatible group found |

All three share the same O(N·K)-shaped worst case for the pairing-search
term — the asymptotic *class* of the main cost is not actually different
between the three approaches. What differs, and what the measured results
in `docs/test-results.md` demonstrate, is **allocation quality**: Approach
3's adaptive re-prioritization and best-candidate (not first-candidate)
selection produce measurably fewer conflicts and equal-or-better
utilization on unbalanced, realistic inputs, at the cost of a higher
constant factor (draining/rebuilding the heap on every pairing decision)
that shows up as higher wall-clock time in the benchmarks.

**We do not claim Approach 3 is asymptotically faster than Approaches 1–2,
nor that it is globally optimal** — see `docs/algorithm.md`, Section 4 and
8, for the explicit non-optimality statement. The value it adds is
constraint-satisfaction and utilization quality, not raw speed.
