"""
exporters.py — Turns a completed SeatingMatrix into the report outputs
required by the brief (Section 10):
    A. Consolidated Seating Plan
    B. Detailed Block Seating Arrangement
    D. Attendance Sheet
    E. Answer Sheet / Seat Number Sheet
    F. Statistics

Formats: CSV and XLSX are fully supported. PDF export is provided for the
tabular reports via reportlab (simple grid tables) — this is not the same
custom OCR/PDF-parsing scope discussed in input_parser.py; it is one-way
report generation using a well-supported library, not a bespoke pipeline.
"""

from __future__ import annotations

from collections import defaultdict
from typing import List

import pandas as pd

from .metrics import AllocationStats
from .models import ConflictEvent
from .seating_matrix import SeatingMatrix


# ---------------------------------------------------------------------------
# A. Consolidated Seating Plan
# ---------------------------------------------------------------------------

def build_consolidated_plan(matrix: SeatingMatrix) -> pd.DataFrame:
    """
    One row per (branch, division, semester, subject, floor, block) combo,
    with the seat-number range and total student count for that combo.
    """
    groups = defaultdict(list)
    for student, (floor, block_no, bench_no, seat_idx) in matrix.all_placements():
        key = (student.branch, student.division, student.semester, student.subject, floor, block_no)
        groups[key].append((bench_no, seat_idx))

    rows = []
    for (branch, division, semester, subject, floor, block_no), seats in groups.items():
        seat_numbers = sorted(range(1, len(seats) + 1))
        rows.append(
            {
                "Branch": branch,
                "Division": division,
                "Semester": semester,
                "Subject": subject,
                "Seat No. From": seat_numbers[0] if seat_numbers else None,
                "Seat No. To": seat_numbers[-1] if seat_numbers else None,
                "Total Students": len(seats),
                "Floor": floor,
                "Block No.": block_no,
            }
        )
    return pd.DataFrame(rows).sort_values(["Floor", "Block No.", "Branch", "Division"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# B. Detailed Block Seating Arrangement
# ---------------------------------------------------------------------------

def build_detailed_arrangement(matrix: SeatingMatrix) -> pd.DataFrame:
    rows = []
    for student, (floor, block_no, bench_no, seat_idx) in matrix.all_placements():
        rows.append(
            {
                "Floor": floor,
                "Block": block_no,
                "Bench No.": bench_no,
                "Seat No.": "A" if seat_idx == 0 else "B",
                "Student Name": student.name,
                "Roll No.": student.roll_no,
                "Branch": student.branch,
                "Division": student.division,
                "Year": student.year,
                "Semester": student.semester,
                "Subject": student.subject,
            }
        )
    return pd.DataFrame(rows).sort_values(["Floor", "Block", "Bench No.", "Seat No."]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# D. Attendance Sheet
# ---------------------------------------------------------------------------

def build_attendance_sheet(matrix: SeatingMatrix) -> pd.DataFrame:
    detailed = build_detailed_arrangement(matrix)
    attendance = detailed[
        ["Floor", "Block", "Bench No.", "Seat No.", "Student Name", "Roll No.", "Branch", "Division"]
    ].copy()
    attendance["Present (Y/N)"] = ""
    attendance["Signature"] = ""
    return attendance


# ---------------------------------------------------------------------------
# E. Answer Sheet / Seat Number Sheet
# ---------------------------------------------------------------------------

def build_answer_sheet(matrix: SeatingMatrix) -> pd.DataFrame:
    rows = []
    for student, (floor, block_no, bench_no, seat_idx) in matrix.all_placements():
        seat_number = f"{block_no}-{bench_no}-{'A' if seat_idx == 0 else 'B'}"
        rows.append(
            {
                "Roll No.": student.roll_no,
                "Student Name": student.name,
                "Branch": student.branch,
                "Division": student.division,
                "Subject": student.subject,
                "Seat Number": seat_number,
            }
        )
    return pd.DataFrame(rows).sort_values(["Branch", "Division", "Roll No."]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# F. Statistics + conflict log
# ---------------------------------------------------------------------------

def build_stats_dataframe(stats: AllocationStats) -> pd.DataFrame:
    return pd.DataFrame(list(stats.as_dict().items()), columns=["Metric", "Value"])


def build_conflicts_dataframe(conflicts: List[ConflictEvent]) -> pd.DataFrame:
    if not conflicts:
        return pd.DataFrame(
            columns=["type", "group_key", "roll_no", "block_no", "bench_no", "fallback", "reason"]
        )
    return pd.DataFrame([c.as_dict() for c in conflicts])


# ---------------------------------------------------------------------------
# File writers
# ---------------------------------------------------------------------------

def export_to_csv(df: pd.DataFrame, path: str) -> None:
    df.to_csv(path, index=False)


def export_to_xlsx(sheets: dict, path: str) -> None:
    """
    sheets: dict[sheet_name -> DataFrame]. Writes a single workbook with
    one sheet per entry (e.g. {"Consolidated": df1, "Detailed": df2, ...}).
    """
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            # Excel sheet names are capped at 31 characters.
            df.to_excel(writer, sheet_name=sheet_name[:31], index=False)


def export_to_pdf(df: pd.DataFrame, path: str, title: str = "") -> None:
    """
    Simple grid-table PDF export using reportlab. Intended for shorter
    reports (e.g. a single block's arrangement or the stats summary) —
    for very large tables, CSV/XLSX is the more practical format.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    doc = SimpleDocTemplate(path, pagesize=landscape(A4))
    styles = getSampleStyleSheet()
    elements = []

    if title:
        elements.append(Paragraph(title, styles["Title"]))
        elements.append(Spacer(1, 12))

    data = [list(df.columns)] + df.astype(str).values.tolist()
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
            ]
        )
    )
    elements.append(table)
    doc.build(elements)
