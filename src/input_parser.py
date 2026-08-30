"""
input_parser.py — Reads student/block data from CSV, XLSX, or text-based PDF,
and validates it before allocation.

This is the ONLY module allowed to import pandas/openpyxl/pdfplumber for
file I/O. The algorithm core (models/constraints/priority_queue/
greedy_allocator/seating_matrix) never imports this module or its
dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import pandas as pd

from .models import Bench, Block, Student

STUDENT_COLUMNS = ["Student Name", "Roll No", "Branch", "Division", "Year", "Semester", "Subject"]
BLOCK_COLUMNS = ["Floor", "Block No", "Benches", "Seats Per Bench"]


class PDFRequiresOCRError(Exception):
    """Raised when a PDF appears to be scanned/image-based (no extractable text)."""


@dataclass
class ValidationIssue:
    severity: str   # "ERROR" or "WARNING"
    row: int        # 1-indexed row number in the source data, -1 if not row-specific
    message: str


# ---------------------------------------------------------------------------
# Loading — CSV / XLSX
# ---------------------------------------------------------------------------

def _read_table(path: str) -> pd.DataFrame:
    if path.lower().endswith(".csv"):
        return pd.read_csv(path)
    if path.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(path)
    raise ValueError(f"Unsupported file type: {path}")


def load_students_table(path: str) -> pd.DataFrame:
    return _read_table(path)


def load_blocks_table(path: str) -> pd.DataFrame:
    return _read_table(path)


# ---------------------------------------------------------------------------
# Loading — PDF (V1 scope: text/table-based only; see design-amendments #6)
# ---------------------------------------------------------------------------

def load_students_table_from_pdf(path: str) -> pd.DataFrame:
    """
    Extract a student table from a text-based/table-based PDF.

    V1 SCOPE: only PDFs with an extractable text layer are supported. If no
    text can be extracted from any page, this raises PDFRequiresOCRError so
    the caller (UI) can show a clear message instead of silently failing or
    guessing. Building a custom OCR pipeline is explicitly out of scope for
    v1 (see docs/algorithm.md, "Limitations").
    """
    import pdfplumber

    rows = []
    header = None
    any_text_found = False

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text.strip():
                any_text_found = True

            table = page.extract_table()
            if table:
                if header is None:
                    header = table[0]
                    body = table[1:]
                else:
                    body = table
                rows.extend(body)

    if not any_text_found:
        raise PDFRequiresOCRError(
            "This PDF appears to be scanned/image-based. OCR extraction is "
            "not enabled in Version 1. Please upload CSV/XLSX or a "
            "text-based PDF."
        )

    if not rows or header is None:
        raise ValueError(
            "No table could be extracted from this PDF's text layer. "
            "Please upload CSV/XLSX instead, or a PDF with a clear table."
        )

    return pd.DataFrame(rows, columns=header)


# ---------------------------------------------------------------------------
# Conversion: DataFrame -> domain objects
# ---------------------------------------------------------------------------

def students_from_dataframe(df: pd.DataFrame) -> List[Student]:
    students = []
    for _, row in df.iterrows():
        students.append(
            Student(
                roll_no=int(row["Roll No"]),
                name=str(row["Student Name"]).strip(),
                branch=str(row["Branch"]).strip(),
                division=str(row["Division"]).strip(),
                year=str(row["Year"]).strip(),
                semester=str(row["Semester"]).strip(),
                subject=str(row["Subject"]).strip(),
            )
        )
    return students


def blocks_from_dataframe(df: pd.DataFrame) -> List[Block]:
    blocks = []
    for _, row in df.iterrows():
        num_benches = int(row["Benches"])
        seats_per_bench = int(row["Seats Per Bench"])
        benches = [
            Bench(bench_no=i + 1, seats_per_bench=seats_per_bench)
            for i in range(num_benches)
        ]
        blocks.append(
            Block(
                floor=str(row["Floor"]).strip(),
                block_no=str(row["Block No"]).strip(),
                benches=benches,
            )
        )
    return blocks


# ---------------------------------------------------------------------------
# Validation — runs BEFORE allocation
# ---------------------------------------------------------------------------

def validate_students_df(df: pd.DataFrame) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []

    missing_cols = [c for c in STUDENT_COLUMNS if c not in df.columns]
    if missing_cols:
        issues.append(
            ValidationIssue("ERROR", -1, f"Missing required column(s): {missing_cols}")
        )
        return issues  # can't validate rows without the right columns

    seen_roll_group = {}
    for idx, row in df.iterrows():
        excel_row = idx + 2  # +1 for 0-index, +1 for header row

        roll_no = row.get("Roll No")
        branch = row.get("Branch")
        division = row.get("Division")
        year = row.get("Year")

        if pd.isna(roll_no):
            issues.append(ValidationIssue("ERROR", excel_row, "Missing roll number."))
        else:
            try:
                int(roll_no)
                if int(roll_no) <= 0:
                    issues.append(
                        ValidationIssue("ERROR", excel_row, f"Invalid roll number: {roll_no}")
                    )
            except (ValueError, TypeError):
                issues.append(
                    ValidationIssue("ERROR", excel_row, f"Roll number is not numeric: {roll_no}")
                )

        if pd.isna(branch) or str(branch).strip() == "":
            issues.append(ValidationIssue("ERROR", excel_row, "Missing branch."))
        if pd.isna(division) or str(division).strip() == "":
            issues.append(ValidationIssue("ERROR", excel_row, "Missing division."))
        if pd.isna(year) or str(year).strip() == "":
            issues.append(ValidationIssue("ERROR", excel_row, "Missing year/semester."))

        if not pd.isna(roll_no) and not pd.isna(branch) and not pd.isna(division) and not pd.isna(year):
            group_key = f"{branch}-{year}-{division}"
            dup_key = (group_key, int(roll_no)) if str(roll_no).strip() else None
            if dup_key and dup_key in seen_roll_group:
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        excel_row,
                        f"Duplicate roll number {roll_no} within group {group_key} "
                        f"(also seen at row {seen_roll_group[dup_key]}).",
                    )
                )
            elif dup_key:
                seen_roll_group[dup_key] = excel_row

    return issues


def validate_blocks_df(df: pd.DataFrame) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []

    missing_cols = [c for c in BLOCK_COLUMNS if c not in df.columns]
    if missing_cols:
        issues.append(
            ValidationIssue("ERROR", -1, f"Missing required column(s): {missing_cols}")
        )
        return issues

    seen_block_no = {}
    for idx, row in df.iterrows():
        excel_row = idx + 2
        block_no = row.get("Block No")
        benches = row.get("Benches")
        seats = row.get("Seats Per Bench")

        if pd.isna(block_no) or str(block_no).strip() == "":
            issues.append(ValidationIssue("ERROR", excel_row, "Missing block identifier."))
        else:
            key = str(block_no).strip()
            if key in seen_block_no:
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        excel_row,
                        f"Duplicate block identifier '{key}' (also seen at row {seen_block_no[key]}).",
                    )
                )
            else:
                seen_block_no[key] = excel_row

        try:
            b = int(benches)
            if b <= 0:
                issues.append(
                    ValidationIssue("ERROR", excel_row, f"Invalid/negative bench count: {benches}")
                )
        except (ValueError, TypeError):
            issues.append(ValidationIssue("ERROR", excel_row, f"Bench count is not numeric: {benches}"))

        try:
            sp = int(seats)
            if sp not in (1, 2):
                issues.append(
                    ValidationIssue(
                        "ERROR", excel_row, f"Seats per bench must be 1 or 2, got: {seats}"
                    )
                )
        except (ValueError, TypeError):
            issues.append(
                ValidationIssue("ERROR", excel_row, f"Seats per bench is not numeric: {seats}")
            )

    return issues


def has_blocking_errors(issues: List[ValidationIssue]) -> bool:
    return any(issue.severity == "ERROR" for issue in issues)
