# SeatMatrix 
### Greedy-Based Constraint-Aware Examination Seating Arrangement

SeatMatrix is an algorithm-driven examination seating arrangement system
that automates the allocation of students across examination blocks,
benches, and seats.

The project focuses on the **Analysis of Algorithms (AOA)** aspects of
examination seating rather than merely providing a management interface.
It uses a **Greedy Method with a Priority Queue (Max Heap)**, sequential
student allocation, matrix-based seat representation, and explicit
constraint checking to generate feasible and efficient seating
arrangements.

**Status:** Core algorithm, all three comparison approaches, full test
suite (46/46 passing), sample datasets, and documentation are implemented.
See `docs/test-results.md` for real, measured benchmark numbers.

---

## ▶ Problem Statement

Colleges often receive examination student lists in spreadsheets and
manually prepare seating arrangements across multiple classrooms and
blocks. The arrangement must simultaneously satisfy:

- Student strength of different classes
- Roll-number sequence
- Branch, division/class, academic year/semester
- Number of available blocks, benches per block, seats per bench
  (one-seater or two-seater)
- Efficient utilisation of available seating capacity

SeatMatrix automates this using an algorithmic approach.

## ▶ Core Idea

Student groups are treated as ordered streams according to roll number.
For a two-seater bench, two compatible streams are allocated in parallel:

```
Bench 01    Comp SE-B 01    |    Elec TE-A 01
Bench 02    Comp SE-B 02    |    Elec TE-A 02
Bench 03    Comp SE-B 03    |    Elec TE-A 03
Bench 04    Comp SE-B 04    |    Elec TE-A 04
...
```

Students remain strictly sequential within their own class (the
**Sequential Allocation Invariant** — see `docs/algorithm.md`) while
pairing satisfies the defined hard constraints. When a block reaches
capacity, remaining students continue into the next suitable block.
One-seater benches are handled independently since no pairing constraint
applies to them.

## ▶ Algorithms & Data Structures

1. **Greedy Method** — at every step, the algorithm selects the best
   feasible *local* allocation given current priorities and constraints.
   Global optimality is never claimed (see `docs/algorithm.md`, Section 4/8).
2. **Priority Queue (Max Heap)** — prioritizes student groups by current
   remaining strength, re-ranking adaptively after every allocation.
3. **Sequential Allocation** — students within a group are never shuffled;
   enforced structurally by `GroupStream` (see `src/models.py`).
4. **Constraint Checking** — explicit hard constraints (different branch /
   division / year-semester for bench-mates) checked before every pairing.
5. **Matrix-Based Representation** — `Block → Bench → Seat`, with O(1)
   bidirectional lookup (`Student ↔ Location`) via `SeatingMatrix`.

## ▶ System Workflow

```
   Student Data (Excel / CSV / PDF)
             │
             ▼
   Data Extraction & Validation  (input_parser.py)
             │
             ▼
        Group Students            (GroupStream, models.py)
             │
             ▼
      Calculate Strengths
             │
             ▼
   Priority Queue (Max Heap)      (priority_queue.py)
             │
             ▼
     Greedy Allocation            (greedy_allocator.py)
             │
             ▼
    Constraint Checking           (constraints.py)
             │
             ▼
   Seating Matrix Creation        (seating_matrix.py)
             │
             ▼
    Block Capacity Check
             │
       ┌─────┴─────┐
       │           │
    Capacity     Remaining
      Full        Students
       │           │
       └─────┬─────┘
             ▼
      Next Suitable Block
             │
             ▼
       Final Arrangement
             │
      ┌──────┼────────┐
      ▼      ▼        ▼
   Seating  Search  Reports      (exporters.py, search.py, metrics.py)
    Sheet
```

## ▶ Input

| Field | Description |
|---|---|
| Student Name | Student's name |
| Roll No. | Examination/student roll number |
| Branch | Academic branch |
| Division | Class/division |
| Year | Academic year |
| Semester | Current semester |
| Subject | Examination subject |

| Field | Description |
|---|---|
| Floor | Floor number/name |
| Block No. | Classroom/block identifier |
| Benches | Number of available benches |
| Seats/Bench | 1 or 2 |

Supported formats: `.csv`, `.xlsx`, `.xls`, and text/table-based `.pdf`
(scanned/image-only PDFs are detected and clearly rejected — OCR is a
future improvement, not part of v1; see `docs/algorithm.md` §8).

## ▶ Outputs

- **A. Consolidated Seating Plan** — branch/division/semester/subject with
  seat-number range and totals, per floor/block.
- **B. Detailed Block Seating Arrangement** — every student's exact seat.
- **C. Student Search** — by name, roll number, branch, or division.
- **D. Attendance Sheet** — block-wise/student-wise, with sign-off columns.
- **E. Answer Sheet / Seat Number Sheet** — roll-to-seat-number mapping.
- **F. Statistics** — total/occupied/empty seats, blocks/benches used,
  conflicts, utilization %, execution time.

Export formats: Excel (all sheets in one workbook), CSV, and PDF (via
`reportlab`, for shorter tabular reports).

## ▶ Constraints

**Hard constraints** (see `docs/algorithm.md` §5 for the full H1–H8 table):
seat/allocation uniqueness, block capacity, sequential roll order, and
different branch / division / year-semester for bench-mates.

**Soft preferences** (used only to break ties among already-valid
candidates): prefer the largest remaining compatible group, better bench
utilization, fewer block switches, deterministic tie-break by group key.

## ▶ Analysis of Algorithms

Three approaches, all operating on identical models for a fair comparison
(`src/baselines.py`, `src/greedy_allocator.py`):

| Approach | Description |
|---|---|
| 1 — Sequential | Fixed group order, first compatible partner found. Baseline. |
| 2 — Sort-Then-Allocate | Groups sorted once by initial strength; static order thereafter. |
| 3 — Greedy + Priority Queue | **Main approach.** Adaptive re-prioritization; best compatible partner selected every time. |

See `docs/complexity.md` for the full time/space complexity table and
`docs/test-results.md` for real measured results — Approach 3 achieves
measurably fewer conflicts and equal-or-better utilization on unbalanced
data, at a higher (but still practical) execution-time cost.

## ▶ Tech Stack

- **Language:** Python 3.12
- **Core concepts:** Greedy algorithms, Priority Queue / Max Heap,
  sorting, matrix/grid representation, constraint satisfaction, searching,
  complexity analysis
- **Data processing:** pandas, openpyxl, pdfplumber
- **Reports:** reportlab (PDF), openpyxl (Excel)
- **Interface:** Streamlit
- **Development:** VS Code, Git, GitHub

## ▶ Project Structure

```
seat-matrix/
│
├── README.md
├── requirements.txt
├── .gitignore
│
├── data/
│   ├── sample_students.csv
│   ├── sample_blocks.csv
│   ├── demo_sequential_students.csv    # required demonstration scenario
│   └── demo_sequential_blocks.csv
│
├── scripts/
│   └── benchmark.py                    # generates docs/test-results.md numbers
│
├── src/
│   ├── main.py              # Streamlit UI + orchestration ONLY
│   ├── models.py            # Student, Bench, Block, GroupStream, config
│   ├── input_parser.py      # CSV/XLSX/PDF parsing + validation
│   ├── priority_queue.py    # Max-heap wrapper over heapq
│   ├── greedy_allocator.py  # Approach 3 — the main algorithm
│   ├── baselines.py         # Approaches 1 & 2 — for AOA comparison
│   ├── constraints.py       # Hard constraints + soft preference ranking
│   ├── seating_matrix.py    # Block/Bench/Seat grid + bidirectional lookup
│   ├── search.py            # Student search
│   ├── exporters.py         # Excel/CSV/PDF report generation
│   └── metrics.py           # Statistics + timing
│
├── tests/
│   ├── test_constraints.py
│   ├── test_priority_queue.py
│   ├── test_allocator.py
│   └── test_edge_cases.py
│
└── docs/
    ├── algorithm.md
    ├── complexity.md
    └── test-results.md
```

## ▶ Getting Started

See **"How to run this in VS Code"** below for full setup steps.

```bash
pip install -r requirements.txt
python3 -m unittest discover -s tests -v   # run the test suite
python3 scripts/benchmark.py               # reproduce benchmark numbers
streamlit run src/main.py                  # launch the UI
```

## ▶ Future Improvements

- OCR-based scanned PDF processing
- More sophisticated soft-preference optimization (e.g. lookahead
  scheduling instead of single-step greedy ranking)
- Multiple concurrent examination sessions
- Automatic block selection based on physical proximity
- Visualization of classroom seating layout
- Additional baseline algorithms for comparison (e.g. bipartite matching)

## ▶ Academic Focus

SeatMatrix was developed primarily as an Analysis of Algorithms project.
The central focus is the application and analysis of:

**Greedy Method + Priority Queue + Constraint Checking + Sequential Allocation**

The interface, file processing, search, and report generation are
supporting components around this core algorithm — see `docs/algorithm.md`
for the complete design rationale, and `docs/complexity.md` /
`docs/test-results.md` for the formal and empirical analysis expected in
an AOA submission.
