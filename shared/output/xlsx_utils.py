#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TSV to XLSX conversion helpers."""

import csv
import os


def tsv_to_xlsx(tsv_path, xlsx_path, sheet_name="Results"):
    """Convert a tab-separated file into an xlsx workbook."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
    except ImportError:
        raise RuntimeError(
            "openpyxl is required for XLSX output; run: pip install openpyxl"
        )

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_name[:31] or "Results"
    with open(tsv_path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        for row in reader:
            sheet.append(row)
    if sheet.max_row >= 1:
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
    os.makedirs(os.path.dirname(os.path.abspath(xlsx_path)), exist_ok=True)
    workbook.save(xlsx_path)
