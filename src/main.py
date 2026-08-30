"""
main.py — Streamlit UI / orchestration layer.

Rule enforced throughout this file: NO algorithmic logic lives here. This
module only (a) reads uploaded files via input_parser, (b) calls the
algorithm core (greedy_allocator / baselines), and (c) hands results to
exporters/search/metrics for display and download. If you find yourself
writing a `for` loop that checks a constraint or manipulates a GroupStream
here, that logic belongs in src/, not main.py.

Run with:  streamlit run src/main.py
"""

from __future__ import annotations

import io
import os
import sys
import tempfile

import pandas as pd
import streamlit as st

# This file can be launched two ways:
#   1. `streamlit run src/main.py`  — Python treats it as a standalone
#      script, NOT part of the `src` package, so relative imports fail.
#   2. `python -m src.main`         — runs as part of the package, where
#      relative imports work fine.
# To support both (Streamlit's own docs recommend #1), we make the project
# root importable and fall back to absolute `src.xxx` imports if the
# relative form fails.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from . import baselines, exporters, input_parser, metrics, search
    from .greedy_allocator import allocate_seating
    from .models import AllocationConfig
except ImportError:
    from src import baselines, exporters, input_parser, metrics, search
    from src.greedy_allocator import allocate_seating
    from src.models import AllocationConfig

st.set_page_config(page_title="SeatMatrix", layout="wide")
st.title("🪑 SeatMatrix — Examination Seating Arrangement")
st.caption("Greedy Method + Priority Queue (Max Heap) + Constraint-Aware Bench Pairing")

# ---------------------------------------------------------------------------
# Sidebar: configuration
# ---------------------------------------------------------------------------

st.sidebar.header("Allocation Configuration")
allow_fallback = st.sidebar.checkbox(
    "Allow single-seat fallback",
    value=True,
    help="If no compatible bench-partner exists, seat the student alone "
    "and leave the second seat empty (recommended). If disabled, the "
    "student is deferred instead of force-paired.",
)
pairing_enabled = st.sidebar.checkbox("Enable bench pairing constraints", value=True)
algorithm_choice = st.sidebar.selectbox(
    "Algorithm",
    ["Approach 3 — Greedy + Priority Queue (main)", "Approach 2 — Sort-Then-Allocate", "Approach 1 — Sequential"],
)

config = AllocationConfig(
    allow_single_seat_fallback=allow_fallback,
    pairing_enabled=pairing_enabled,
)

# ---------------------------------------------------------------------------
# Step 1: Upload data
# ---------------------------------------------------------------------------

st.header("1. Upload Data")
col1, col2 = st.columns(2)

with col1:
    student_file = st.file_uploader(
        "Student data (CSV / XLSX / PDF)", type=["csv", "xlsx", "xls", "pdf"]
    )
with col2:
    block_file = st.file_uploader("Block/room configuration (CSV / XLSX)", type=["csv", "xlsx", "xls"])

students_df, blocks_df = None, None

if student_file is not None:
    with tempfile.NamedTemporaryFile(delete=False, suffix="_" + student_file.name) as tmp:
        tmp.write(student_file.getbuffer())
        tmp_path = tmp.name

    try:
        if student_file.name.lower().endswith(".pdf"):
            students_df = input_parser.load_students_table_from_pdf(tmp_path)
        else:
            students_df = input_parser.load_students_table(tmp_path)
    except input_parser.PDFRequiresOCRError:
        st.error(
            "This PDF appears to be scanned/image-based.\n\n"
            "OCR extraction is not enabled in Version 1.\n\n"
            "Please upload CSV/XLSX or a text-based PDF."
        )
    except Exception as exc:  # noqa: BLE001 — surface any parse failure to the user
        st.error(f"Could not read student file: {exc}")

if block_file is not None:
    with tempfile.NamedTemporaryFile(delete=False, suffix="_" + block_file.name) as tmp:
        tmp.write(block_file.getbuffer())
        tmp_path = tmp.name
    try:
        blocks_df = input_parser.load_blocks_table(tmp_path)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not read block file: {exc}")

# ---------------------------------------------------------------------------
# Step 2: Preview + validate
# ---------------------------------------------------------------------------

allocation_ready = False

if students_df is not None and blocks_df is not None:
    st.header("2. Preview & Validation")

    st.subheader("Student data preview")
    st.dataframe(students_df.head(20), use_container_width=True)

    st.subheader("Block configuration preview")
    st.dataframe(blocks_df, use_container_width=True)

    student_issues = input_parser.validate_students_df(students_df)
    block_issues = input_parser.validate_blocks_df(blocks_df)
    all_issues = student_issues + block_issues

    if all_issues:
        st.subheader("Validation issues")
        issues_df = pd.DataFrame(
            [{"Severity": i.severity, "Row": i.row, "Message": i.message} for i in all_issues]
        )
        st.dataframe(issues_df, use_container_width=True)

    if input_parser.has_blocking_errors(all_issues):
        st.error("Please fix the ERROR-level issues above before running the algorithm.")
    else:
        allocation_ready = True
        if all_issues:
            st.warning("Only WARNING-level issues found — you may proceed.")
        else:
            st.success("No validation issues found.")

# ---------------------------------------------------------------------------
# Step 3: Run allocation
# ---------------------------------------------------------------------------

if allocation_ready and st.button("Run Seating Allocation", type="primary"):
    students = input_parser.students_from_dataframe(students_df)
    blocks = input_parser.blocks_from_dataframe(blocks_df)

    if algorithm_choice.startswith("Approach 3"):
        allocate_fn = allocate_seating
    elif algorithm_choice.startswith("Approach 2"):
        allocate_fn = baselines.sort_then_allocate
    else:
        allocate_fn = baselines.sequential_allocate

    (matrix, conflicts), elapsed = metrics.timed_run(allocate_fn, students, blocks, config)
    stats = metrics.compute_stats(len(students), matrix, conflicts, elapsed)

    st.session_state["matrix"] = matrix
    st.session_state["conflicts"] = conflicts
    st.session_state["stats"] = stats

# ---------------------------------------------------------------------------
# Step 4: Results
# ---------------------------------------------------------------------------

if "matrix" in st.session_state:
    matrix = st.session_state["matrix"]
    conflicts = st.session_state["conflicts"]
    stats = st.session_state["stats"]

    st.header("3. Results")

    tab_stats, tab_consolidated, tab_detailed, tab_search, tab_export = st.tabs(
        ["Statistics", "Consolidated Plan", "Detailed Arrangement", "Search", "Export"]
    )

    with tab_stats:
        st.dataframe(exporters.build_stats_dataframe(stats), use_container_width=True)
        if conflicts:
            st.subheader(f"Conflicts / fallback events ({len(conflicts)})")
            st.dataframe(exporters.build_conflicts_dataframe(conflicts), use_container_width=True)

    with tab_consolidated:
        consolidated_df = exporters.build_consolidated_plan(matrix)
        st.dataframe(consolidated_df, use_container_width=True)

    with tab_detailed:
        detailed_df = exporters.build_detailed_arrangement(matrix)
        st.dataframe(detailed_df, use_container_width=True)

    with tab_search:
        st.subheader("Search students")
        c1, c2, c3, c4 = st.columns(4)
        q_name = c1.text_input("Name")
        q_roll = c2.text_input("Roll No.")
        q_branch = c3.text_input("Branch")
        q_division = c4.text_input("Division")

        results = search.search_students(
            matrix,
            name=q_name or None,
            roll_no=int(q_roll) if q_roll.strip().isdigit() else None,
            branch=q_branch or None,
            division=q_division or None,
        )
        if results:
            rows = [
                {
                    "Name": r["student"].name,
                    "Roll No.": r["student"].roll_no,
                    "Branch": r["student"].branch,
                    "Division": r["student"].division,
                    "Floor": r["floor"],
                    "Block": r["block_no"],
                    "Bench": r["bench_no"],
                    "Seat": "A" if r["seat_index"] == 0 else "B",
                }
                for r in results
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
        else:
            st.info("No matching students, or no search terms entered yet.")

    with tab_export:
        consolidated_df = exporters.build_consolidated_plan(matrix)
        detailed_df = exporters.build_detailed_arrangement(matrix)
        attendance_df = exporters.build_attendance_sheet(matrix)
        answer_df = exporters.build_answer_sheet(matrix)
        stats_df = exporters.build_stats_dataframe(stats)

        xlsx_buffer = io.BytesIO()
        with pd.ExcelWriter(xlsx_buffer, engine="openpyxl") as writer:
            consolidated_df.to_excel(writer, sheet_name="Consolidated Plan", index=False)
            detailed_df.to_excel(writer, sheet_name="Detailed Arrangement", index=False)
            attendance_df.to_excel(writer, sheet_name="Attendance Sheet", index=False)
            answer_df.to_excel(writer, sheet_name="Answer Sheet", index=False)
            stats_df.to_excel(writer, sheet_name="Statistics", index=False)

        st.download_button(
            "⬇️ Download full report (Excel, all sheets)",
            data=xlsx_buffer.getvalue(),
            file_name="seatmatrix_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        st.download_button(
            "⬇️ Download Detailed Arrangement (CSV)",
            data=detailed_df.to_csv(index=False).encode("utf-8"),
            file_name="detailed_arrangement.csv",
            mime="text/csv",
        )
