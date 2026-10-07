from __future__ import annotations

import csv
import json
import os
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Sequence


SUPPORTED_FORMATS = (
    "csv",
    "tsv",
    "fasta",
    "bed",
    "xlsx",
    "unique_guides",
    "library",
)


def export_selected(
    rows: Sequence[Dict[str, Any]],
    output_path: str,
    fmt: str,
) -> int:
    fmt = fmt.lower()
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"unsupported export format: {fmt}")
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    if fmt == "csv":
        return _write_delimited(rows, output_path, ",")
    if fmt == "tsv":
        return _write_delimited(rows, output_path, "\t")
    if fmt == "fasta":
        return _write_fasta(rows, output_path)
    if fmt == "bed":
        return _write_bed(rows, output_path)
    if fmt == "xlsx":
        return _write_xlsx(rows, output_path)
    if fmt == "unique_guides":
        return _write_unique_guides(rows, output_path)
    if fmt == "library":
        return _write_library_input(rows, output_path)
    raise ValueError(f"unsupported export format: {fmt}")


def _fieldnames(rows: Sequence[Dict[str, Any]]) -> List[str]:
    if not rows:
        return []
    return list(rows[0].keys())


def _write_delimited(
    rows: Sequence[Dict[str, Any]],
    path: str,
    delimiter: str,
) -> int:
    if not rows:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write("")
        return 0
    fields = _fieldnames(rows)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            delimiter=delimiter,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def _write_fasta(rows: Sequence[Dict[str, Any]], path: str) -> int:
    count = 0
    with open(path, "w", encoding="utf-8", newline="") as handle:
        for index, row in enumerate(rows, start=1):
            sequence = row.get("query_seq") or row.get("sequence") or ""
            if not sequence:
                continue
            name = (
                row.get("query_id")
                or row.get("qid")
                or row.get("seq_id")
                or f"candidate_{index}"
            )
            handle.write(f">{name}\n{sequence}\n")
            count += 1
    return count


def _write_bed(rows: Sequence[Dict[str, Any]], path: str) -> int:
    count = 0
    with open(path, "w", encoding="utf-8", newline="") as handle:
        for index, row in enumerate(rows, start=1):
            seq_id = row.get("seq_id") or row.get("chrom") or ""
            if not seq_id:
                continue
            try:
                start = int(row.get("start")) - 1
                end = int(row.get("end"))
            except (TypeError, ValueError):
                continue
            if start < 0:
                start = 0
            name = (
                row.get("query_id")
                or row.get("qid")
                or f"candidate_{index}"
            )
            strand = row.get("strand") or "."
            if strand not in ("+", "-", "."):
                strand = "."
            handle.write(
                f"{seq_id}\t{start}\t{end}\t{name}\t0\t{strand}\n"
            )
            count += 1
    return count


def _write_xlsx(rows: Sequence[Dict[str, Any]], path: str) -> int:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
    except ImportError as exc:
        raise RuntimeError(
            "openpyxl is required for XLSX output; run: pip install openpyxl"
        ) from exc

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Candidates"
    fields = _fieldnames(rows)
    sheet.append(fields)
    for row in rows:
        sheet.append([row.get(field, "") for field in fields])
    if sheet.max_row >= 1:
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
    workbook.save(path)
    return len(rows)


def _write_unique_guides(rows: Sequence[Dict[str, Any]], path: str) -> int:
    by_sequence: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        sequence = row.get("query_seq") or row.get("sequence") or ""
        if sequence:
            by_sequence[sequence].append(row)

    if not by_sequence:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write("query_id\tquery_seq\toccurrence_count\n")
        return 0

    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["query_id", "query_seq", "occurrence_count"])
        for index, (sequence, matches) in enumerate(by_sequence.items(), start=1):
            name = (
                matches[0].get("query_id")
                or matches[0].get("qid")
                or f"unique_{index}"
            )
            writer.writerow([name, sequence, len(matches)])
    return len(by_sequence)


def _write_library_input(rows: Sequence[Dict[str, Any]], path: str) -> int:
    count = 0
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["qid", "sequence", "positions"])
        for index, row in enumerate(rows, start=1):
            sequence = row.get("query_seq") or row.get("sequence") or ""
            if not sequence:
                continue
            name = (
                row.get("query_id")
                or row.get("qid")
                or f"candidate_{index}"
            )
            positions = row.get("positions_json") or ""
            if not positions and row.get("seq_id"):
                start = int(row.get("start", "0")) - 1
                strand = row.get("strand") or "plus"
                positions = json.dumps([[row["seq_id"], strand, start]])
            writer.writerow([name, sequence, positions])
            count += 1
    return count
