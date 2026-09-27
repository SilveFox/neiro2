# -*- coding: utf-8 -*-
"""Create empty monthly workbooks from SE_Lukhovitsy template and manage active file."""
from __future__ import annotations

import calendar
import json
import re
import shutil
from datetime import date
from pathlib import Path
from typing import Any

import openpyxl

from core import config

YEAR_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")
_EXTERNAL_REF_RE = re.compile(r"\[\d+\]")


class WorkbookExistsError(FileExistsError):
    pass


def sanitize_workbook(wb: openpyxl.Workbook) -> None:
    """
    Drop external workbook links and names that reference them.

    The SE template carries links to another PC's files. openpyxl can rewrite
    those relationship ids incorrectly, and Excel then reports the book as corrupt.
    Internal named ranges (Прайс, ФИО, …) are kept.
    """
    if hasattr(wb, "_external_links"):
        wb._external_links = []

    for name in list(wb.defined_names):
        try:
            defn = wb.defined_names[name]
        except KeyError:
            continue
        texts: list[str] = []
        if hasattr(defn, "attr_text"):
            texts.append(defn.attr_text or "")
        elif hasattr(defn, "value"):
            texts.append(str(defn.value or ""))
        # DefinedNameDict may store a list for duplicate names
        if isinstance(defn, list):
            texts = [getattr(d, "attr_text", "") or "" for d in defn]
        if any(_EXTERNAL_REF_RE.search(t or "") for t in texts):
            try:
                del wb.defined_names[name]
            except KeyError:
                pass


def month_workbook_path(year: int, month: int) -> Path:
    return config.WORKBOOKS_DIR / f"SE_Lukhovitsy_{year:04d}-{month:02d}.xlsx"


def written_log_for(workbook_path: Path) -> Path:
    return workbook_path.with_suffix(".written.json")


def year_month_from_path(path: Path) -> str | None:
    m = re.search(r"SE_Lukhovitsy_(\d{4}-\d{2})\.xlsx$", path.name)
    return m.group(1) if m else None


def get_active_meta() -> dict[str, Any] | None:
    if not config.ACTIVE_WORKBOOK_META.exists():
        return None
    try:
        data = json.loads(config.ACTIVE_WORKBOOK_META.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    path = Path(data.get("path") or "")
    if not path.is_absolute():
        path = (config.ROOT / path).resolve()
    else:
        path = path.resolve()
    if not path.exists():
        return None
    data["path"] = str(path)
    return data


def set_active_workbook(path: Path, year_month: str | None = None) -> dict[str, Any]:
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(f"Книга не найдена: {path}")
    ym = year_month or year_month_from_path(path) or ""
    meta = {
        "path": str(path),
        "year_month": ym,
        "name": path.name,
    }
    config.ACTIVE_WORKBOOK_META.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return meta


def get_active_workbook() -> Path:
    """Return active workbook path; bootstrap fallback if needed."""
    meta = get_active_meta()
    if meta:
        return Path(meta["path"])

    # Prefer existing monthly files (latest)
    existing = list_month_workbooks()
    if existing:
        path = Path(existing[0]["path"])
        set_active_workbook(path, existing[0].get("year_month"))
        return path

    # Legacy single workbook
    if config.WORKING_WORKBOOK.exists():
        set_active_workbook(config.WORKING_WORKBOOK, year_month_from_path(config.WORKING_WORKBOOK))
        return config.WORKING_WORKBOOK.resolve()

    # Bootstrap: copy source as current calendar month (or as legacy workbook.xlsx)
    if not config.SOURCE_WORKBOOK.exists():
        raise FileNotFoundError(f"Нет исходного Excel: {config.SOURCE_WORKBOOK}")
    today = date.today()
    try:
        path = create_month_workbook(today.year, today.month, activate=True)
        return path
    except WorkbookExistsError:
        path = month_workbook_path(today.year, today.month)
        set_active_workbook(path)
        return path


def list_month_workbooks() -> list[dict[str, Any]]:
    config.WORKBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    active = get_active_meta()
    active_path = Path(active["path"]).resolve() if active else None
    items: list[dict[str, Any]] = []
    for path in sorted(config.WORKBOOKS_DIR.glob("SE_Lukhovitsy_????-??.xlsx"), reverse=True):
        ym = year_month_from_path(path) or ""
        items.append(
            {
                "path": str(path.resolve()),
                "name": path.name,
                "year_month": ym,
                "active": active_path is not None and path.resolve() == active_path,
            }
        )
    return items


def _update_calc_dates(ws, year: int, month: int) -> None:
    """Row 2, cols F.. = days 1..31 for the month."""
    days_in_month = calendar.monthrange(year, month)[1]
    for day in range(1, 32):
        col = 5 + day  # F=6 → day 1
        if day <= days_in_month:
            ws.cell(2, col).value = date(year, month, day)
        else:
            ws.cell(2, col).value = None


def _strip_work_tables(ws) -> None:
    """Remove left-side work blocks (B..J) including borders; keep employee list in K:L."""
    from openpyxl.styles import Border, PatternFill

    no_border = Border()
    no_fill = PatternFill(fill_type=None)
    max_row = max(ws.max_row or 1, 200)
    # B..J — work tables + spacer; leave K:L (ФИО / Наработка)
    col_start, col_end = config.COL_NUM, config.COL_PER_PERSON + 1  # B..J

    to_unmerge = []
    for merged in list(ws.merged_cells.ranges):
        if merged.min_col <= col_end and merged.max_col >= col_start:
            to_unmerge.append(str(merged))
    for ref in to_unmerge:
        ws.unmerge_cells(ref)

    for r in range(1, max_row + 1):
        for c in range(col_start, col_end + 1):
            cell = ws.cell(r, c)
            cell.value = None
            cell.border = no_border
            cell.fill = no_fill


def _reset_day_sheets(wb: openpyxl.Workbook, year: int, month: int) -> None:
    if config.SHEET_TEMPLATE not in wb.sheetnames:
        raise KeyError("В книге нет листа Шаблон")

    template = wb[config.SHEET_TEMPLATE]
    days_in_month = calendar.monthrange(year, month)[1]

    # Source order: 31, 30, ... 01
    for day in range(31, 0, -1):
        name = f"{day:02d}"
        if name not in wb.sheetnames:
            continue
        idx = wb.sheetnames.index(name)
        del wb[name]
        new_ws = wb.copy_worksheet(template)
        new_ws.title = name
        current_idx = wb.sheetnames.index(name)
        offset = idx - current_idx
        if offset:
            wb.move_sheet(new_ws, offset=offset)

        # Drop template work tables; keep ФИО / Наработка on the right
        _strip_work_tables(new_ws)

        if day <= days_in_month:
            new_ws.cell(1, 2).value = f"{day:02d}.{month:02d}.{year}"
        else:
            new_ws.cell(1, 2).value = f"00.{month:02d}.{year}"


def create_month_workbook(
    year: int,
    month: int,
    activate: bool = True,
) -> Path:
    """
    Create an empty monthly workbook from the source template.
    Raises WorkbookExistsError if the target file already exists.
    """
    if not (1 <= month <= 12):
        raise ValueError("month must be 1..12")
    if year < 2000 or year > 2100:
        raise ValueError("year out of range")

    config.WORKBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    dest = month_workbook_path(year, month)
    if dest.exists():
        raise WorkbookExistsError(f"Месяц {year:04d}-{month:02d} уже существует: {dest.name}")

    if not config.SOURCE_WORKBOOK.exists():
        raise FileNotFoundError(f"Нет исходного Excel: {config.SOURCE_WORKBOOK}")

    shutil.copy2(config.SOURCE_WORKBOOK, dest)
    wb = openpyxl.load_workbook(dest)
    try:
        sanitize_workbook(wb)
        _reset_day_sheets(wb, year, month)
        if config.SHEET_CALC in wb.sheetnames:
            _update_calc_dates(wb[config.SHEET_CALC], year, month)
        try:
            wb.calculation.calcMode = "auto"
            wb.calculation.fullCalcOnLoad = True
            wb.calculation.forceFullCalc = True
        except Exception:
            pass
        wb.save(dest)
    finally:
        wb.close()

    written_log_for(dest).write_text(
        json.dumps({"entries": []}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    year_month = f"{year:04d}-{month:02d}"
    if activate:
        set_active_workbook(dest, year_month)
    return dest.resolve()


def activate_year_month(year_month: str) -> dict[str, Any]:
    m = YEAR_MONTH_RE.match(year_month.strip())
    if not m:
        raise ValueError("Ожидается формат YYYY-MM")
    year, month = int(m.group(1)), int(m.group(2))
    path = month_workbook_path(year, month)
    if not path.exists():
        raise FileNotFoundError(f"Нет файла для месяца {year_month}")
    return set_active_workbook(path, year_month)


def ensure_month_workbook(year: int, month: int, activate: bool = True) -> tuple[Path, bool]:
    """
    Return the monthly workbook path, creating an empty month if the file is missing.

    Returns (path, created). When activate=True the book becomes the active one.
    """
    dest = month_workbook_path(year, month)
    year_month = f"{year:04d}-{month:02d}"
    if dest.exists():
        if activate:
            set_active_workbook(dest, year_month)
        return dest.resolve(), False
    try:
        path = create_month_workbook(year, month, activate=activate)
        return path, True
    except WorkbookExistsError:
        if activate:
            set_active_workbook(dest, year_month)
        return dest.resolve(), False


def workbook_for_report_date(report_date: str, activate: bool = True) -> tuple[Path, bool]:
    """Pick / create SE_Lukhovitsy_YYYY-MM.xlsx from report_date (YYYY-MM-DD)."""
    try:
        dt = date.fromisoformat(report_date[:10])
    except ValueError as exc:
        raise ValueError(f"Некорректная report_date: {report_date}") from exc
    return ensure_month_workbook(dt.year, dt.month, activate=activate)
