# SeatMatrix — Algorithm Documentation

## 1. Architecture

SeatMatrix is split into four layers, enforced in the folder structure and
in the imports each module is allowed to make:

```
UI Layer (src/main.py, Streamlit)
        │
Orchestration Layer (also src/main.py — wiring only, no algorithm logic)
        │
Algorithm Core (models.py, constraints.py, priority_queue.py,
                greedy_allocator.py, baselines.py, seating_matrix.py)
        │
I/O & Support Layer (input_parser.py, search.py, exporters.py, metrics.py)
```

**Hard rule:** the Algorithm Core never imports Streamlit, pandas, or any
file-handling code. It consumes and returns plain Python objects
(`Student`, `Block`, `SeatingMatrix`, `ConflictEvent`). This is what makes
`tests/test_allocator.py` runnable with zero UI or file dependencies, and
what makes the core independently explainable in a viva.

## 2. Data Structures

| Structure | Purpose |
|---|---|
| `Student` (dataclass) | One student record; `group_key` property derives `f"{branch}-{year}-{division}"`. |
| `Bench` | One physical bench; `seats: list[Optional[Student]]` of length 1 or 2; tracks `fallback_closed` (see Section 6). |
| `Block` | A room; holds a list of `Bench`; `next_open_bench()` returns the next bench available for a *new* allocation decision. |
| `GroupStream` | Wraps one academic group's students as a **sorted, pointer-based stream** — this is where the Sequential Allocation Invariant lives (Section 3). |
| `GroupPriorityQueue` | Max-heap over `GroupStream.remaining()`, built on Python's `heapq` (a min-heap) by negating the key, with a `group_key` tie-breaker for determinism. |
| `SeatingMatrix` | Wraps `Block → Bench → Seat` and maintains O(1) bidirectional lookup: `Student ↔ (floor, block_no, bench_no, seat_index)`. |
| `AllocationConfig` | Runtime knobs: `allow_single_seat_fallback`, `pairing_enabled`, `preferred_block_order`. `preserve_roll_sequence` is a fixed invariant and cannot be disabled (raises `ValueError` if attempted). |
| `ConflictEvent` | A recorded conflict/fallback event: type, group, roll number, location, fallback kind, and a human-readable reason. |

## 3. The Sequential Allocation Invariant

This is a **hard invariant**, enforced entirely inside `GroupStream`
(`models.py`), and never bypassed anywhere else in the codebase:

1. `GroupStream.students` is sorted by `roll_no` ascending exactly once,
   at construction (`__post_init__`), and is never reordered afterwards.
2. Only `students[pointer]` may ever be consumed.
3. `pointer` only ever increases, and only via `pop()` — which always
   reads index `pointer`, returns it, and increments by exactly 1. There
   is no code path that reads any other index or advances by more than 1.
4. `peek()` never mutates `pointer` — it is safe to call any number of
   times during compatibility search (`find_compatible_group`) without
   side effects, so speculative "does this group have a compatible next
   student?" checks never accidentally consume a student.
5. Consequently: if student *i+1* of a group has been allocated, student
   *i* must already have been allocated — there is no mechanism to skip
   ahead.

`greedy_allocator.py` and `baselines.py` only ever call `.peek()` and
`.pop()` on a `GroupStream` — they never touch `.students` directly. This
is verified in `tests/test_priority_queue.py::TestGroupStream` and in the
required demonstration scenario below.

### Required demonstration scenario

`data/demo_sequential_students.csv` + `data/demo_sequential_blocks.csv`
encode exactly:

```
Comp-SE-B: 1, 2, 3, 4, 5
Elec-TE-A: 1, 2, 3, 4, 5
```
with 5 two-seat benches and no other groups. `tests/test_allocator.py::TestDemonstrationScenario`
asserts the exact resulting pairing is:

```
Bench 1: Comp-SE-B-1 ↔ Elec-TE-A-1
Bench 2: Comp-SE-B-2 ↔ Elec-TE-A-2
Bench 3: Comp-SE-B-3 ↔ Elec-TE-A-3
Bench 4: Comp-SE-B-4 ↔ Elec-TE-A-4
Bench 5: Comp-SE-B-5 ↔ Elec-TE-A-5
```

## 4. Greedy Choice Strategy

At every step:

1. **Which group goes next?** The `GroupPriorityQueue` always pops the
   group with the **highest remaining student count**. Rationale: groups
   with many students left are the ones most likely to cause
   fragmentation or unpairable leftovers later, so they are worked down
   first, while the pool of potential partners is still large.

2. **Who pairs with them?** For a 2-seater bench, `find_compatible_group`
   drains the queue, filters to groups whose *next* student
   (`.peek()`, never `.pop()`) satisfies every hard constraint against the
   anchor student, and — among the survivors — picks the one with the
   largest remaining count (the refined soft-preference hierarchy,
   Section 5).

**Explicit non-claim:** this is a *local* greedy choice. It does **not**
guarantee a globally minimal conflict count or globally optimal
utilization. Section 7 (Algorithm Comparison) shows a real, measured
scenario where the greedy approach still incurs conflicts that a
differently-ordered (but non-adaptive, hindsight-only) allocation could
in principle avoid — the greedy choice is provably locally optimal at
each decision point given the current queue state, not globally optimal.

## 5. Hard Constraints and Soft Preferences

### Hard constraints (never violated)

| ID | Constraint | Where enforced |
|---|---|---|
| H1 | Student allocated at most once | `SeatingMatrix.place()` raises on duplicate `(group_key, roll_no)` |
| H2 | Seat holds exactly one student | `SeatingMatrix.place()` raises if seat occupied |
| H3 | Block capacity not exceeded | `Block.next_open_bench()` / `is_full()` gate the main loop |
| H4 | Roll numbers stay sequential within a group | `GroupStream` (Section 3) |
| H5 | Bench-mates: different branch | `constraints.satisfies_hard_constraints` |
| H6 | Bench-mates: different division | `constraints.satisfies_hard_constraints` |
| H7 | Bench-mates: different (year, semester) | `constraints.satisfies_hard_constraints` |
| H8 | 1-seat benches: no pairing constraint | Separate code branch in `allocate_seating` |

### Soft preferences (only ever break ties among already-hard-constraint-valid candidates)

Refined hierarchy (a candidate must pass H5–H7 before this is even consulted):

1. Prefer the compatible candidate with the highest remaining group size.
2. (Approximated by #1) Prefer the choice that reduces the likelihood of
   future unmatched students — a larger group paired now leaves smaller
   groups more room to be matched later while partners still exist.
3. Prefer better current bench/seat utilization — handled by the
   allocator's block/bench visiting order, not the pairing-score function.
4. Prefer fewer unnecessary block switches — also handled by block
   visiting order (`_order_blocks`, stable sort by floor/block_no or an
   explicit `preferred_block_order`).
5. Deterministic `group_key` tie-breaker (`constraints.rank_candidates`).

A soft preference can **never** override a hard constraint — candidates
are filtered by hard constraints first, and only the survivors are ranked.

**Removed preference:** an earlier draft preference ("prefer different
branch/division/year") was removed because it was redundant — any
candidate reaching the ranking step has already passed H5–H7.

## 6. Fallback Policy (Configurable)

Controlled by `AllocationConfig.allow_single_seat_fallback` (default `True`).

**When enabled (default):** if no hard-constraint-compatible partner
exists for a 2-seater bench, the anchor student is seated alone at the
bench's open seat, a `ConflictEvent(type="NO_COMPATIBLE_PAIR",
fallback="SINGLE_SEAT_FALLBACK")` is recorded, and — critically — the
bench is marked `fallback_closed = True`.

**Why `fallback_closed` matters:** without it, the bench would still
report "not full" (only one of two seats occupied) and could be handed
back out by `next_open_bench()` for an unrelated *future* pairing decision
between two completely different groups — silently breaking the "second
seat left empty" guarantee and, worse, attempting to seat two new students
into a bench with only one physical seat left. `Block.next_open_bench()`
and `Block.is_full()` both check `Bench.is_available_for_allocation()`
(`not is_full() and not fallback_closed`), so a fallback-closed bench is
permanently skipped from then on. This is covered by a dedicated
regression test (`tests/test_allocator.py::test_18_...`) built from the
exact large-scale dataset that originally surfaced this bug during
benchmarking.

**When disabled:** the student is **not** force-paired and the pointer is
**not** advanced (the student remains the next-in-line for that group). A
`ConflictEvent(fallback="DEFERRED")` is recorded, and the group is
re-queued. If the algorithm determines no other active group will *ever*
be able to pair with it (i.e. it is the only remaining group), the
remaining students of that group are reported as
`UNRESOLVED_NO_PAIR_POSSIBLE` rather than looping forever.

## 7. Algorithm Comparison

Three approaches operate on identical `Student`/`Block` models so results
are directly comparable (see `docs/test-results.md` for real measured
numbers):

- **Approach 1 — Sequential** (`baselines.sequential_allocate`): groups
  visited in a fixed group_key order; for each 2-seater bench, a linear
  scan finds the *first* compatible partner (not the best one). No
  priority queue, no adaptive reprioritization.
- **Approach 2 — Sort-Then-Allocate** (`baselines.sort_then_allocate`):
  groups sorted once, up front, by initial remaining strength; then
  processed in that fixed order for the entire run. Priorities are never
  recomputed as groups shrink.
- **Approach 3 — Greedy + Priority Queue** (`greedy_allocator.allocate_seating`,
  the main algorithm): adaptively re-prioritizes by *current* remaining
  strength after every allocation, and picks the *best* (highest-remaining)
  compatible partner rather than the first one found.

Measured result (see `docs/test-results.md`): Approach 3 consistently
produces fewer conflicts and equal-or-better utilization than both
baselines on unbalanced data, at the cost of higher execution time (driven
by the O(K) compatible-group search per pairing decision).

## 8. Limitations

- The greedy choice is locally, not globally, optimal (Section 4).
- PDF input support (v1) is limited to text/table-based PDFs; scanned or
  image-only PDFs are explicitly detected and rejected with a clear
  message rather than attempting unreliable extraction (see
  `input_parser.PDFRequiresOCRError`). A custom OCR pipeline is out of
  scope for v1 (see README "Future Improvements").
- `find_compatible_group` drains and rebuilds the entire priority queue on
  every pairing decision (O(K) per decision, K = number of active
  groups). This is a deliberate, documented trade-off — `heapq` has no
  built-in "search without popping everything" operation — and remains
  practical because K (distinct academic groups) is small relative to N
  (total students) in real college settings.
- Determinism relies on Python's stable sort and the explicit tie-breakers
  described above; it does not rely on dict/set iteration order anywhere
  in the allocation path.
