# -*- coding: utf-8 -*-
"""Create empty monthly workbooks from SE_Lukhovitsy template and manage active file."""
from __future__ import annotations

import calendar
import json
import re
import shutil
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

import openpyxl

from core import config

YEAR_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")
_EXTERNAL_REF_RE = re.compile(r"\[\d+\]")
# <title>_YYYY-MM.xlsx | YYYY-MM.xlsx | legacy SE_Lukhovitsy[_title]_YYYY-MM.xlsx
_BOOK_NAME_RE = re.compile(
    r"^(?:SE_Lukhovitsy_)?(?:(?P<title>.+)_)?(?P<ym>\d{4}-\d{2})\.xlsx$",
    re.IGNORECASE,
)
_TITLE_SAFE_RE = re.compile(r"[^A-Za-zА-Яа-яЁё0-9_-]+")


class WorkbookExistsError(FileExistsError):
    pass


def sanitize_workbook_title(title: str | None) -> str:
    """
    Optional human title for the file name (no path, no extension).
    Empty → default file YYYY-MM.xlsx; with title → <title>_YYYY-MM.xlsx.
    """
    raw = (title or "").strip()
    if not raw:
        return ""
    # Drop extension if user pasted a full filename
    if raw.lower().endswith(".xlsx"):
        raw = raw[:-5]
    raw = raw.replace("\\", "_").replace("/", "_").replace("..", "_")
    # Collapse spaces/punctuation to underscore
    slug = _TITLE_SAFE_RE.sub("_", raw).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    # Drop legacy prefix if pasted into the name field
    while slug.lower().startswith("se_lukhovitsy_"):
        slug = slug[14:].lstrip("_")
    if slug.lower() == "se_lukhovitsy":
        raise ValueError("Укажите своё название файла без SE_Lukhovitsy")
    if not slug:
        raise ValueError("Название файла пустое после очистки")
    if len(slug) > 60:
        slug = slug[:60].rstrip("_")
    # Avoid colliding with bare month token
    if YEAR_MONTH_RE.match(slug):
        raise ValueError("Название не должно быть только датой ГГГГ-ММ")
    return slug


def title_from_workbook_name(name: str) -> str:
    """Extract custom title from basename, or '' for default month books."""
    m = _BOOK_NAME_RE.match(Path(name).name)
    if not m:
        return ""
    return (m.group("title") or "").strip("_")


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


def month_workbook_path(year: int, month: int, title: str | None = None) -> Path:
    """Default or titled monthly path under data/workbooks: [title_]YYYY-MM.xlsx."""
    ym = f"{year:04d}-{month:02d}"
    slug = sanitize_workbook_title(title) if title else ""
    if slug:
        return config.WORKBOOKS_DIR / f"{slug}_{ym}.xlsx"
    return config.WORKBOOKS_DIR / f"{ym}.xlsx"


def written_log_for(workbook_path: Path) -> Path:
    return workbook_path.with_suffix(".written.json")


def year_month_from_path(path: Path) -> str | None:
    """Extract YYYY-MM from monthly workbook filename (UI label / routing key)."""
    m = _BOOK_NAME_RE.match(path.name)
    if m:
        return m.group("ym")
    m2 = re.search(r"(?:^|_)(\d{4}-\d{2})\.xlsx$", path.name, flags=re.IGNORECASE)
    return m2.group(1) if m2 else None


def workbook_label(
    year_month: str | None,
    path: Path | str | None = None,
    title: str | None = None,
) -> str:
    """Human-facing table name: YYYY-MM or YYYY-MM — Title."""
    ym = (year_month or "").strip()
    if not YEAR_MONTH_RE.match(ym) and path is not None:
        extracted = year_month_from_path(Path(path))
        if extracted:
            ym = extracted
    slug = (title or "").strip()
    if not slug and path is not None:
        slug = title_from_workbook_name(Path(path).name)
    if YEAR_MONTH_RE.match(ym):
        return f"{ym} — {slug}" if slug else ym
    return ym or slug or (Path(path).name if path else "")


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
    ym = data.get("year_month") or year_month_from_path(path) or ""
    title = data.get("title") or title_from_workbook_name(path.name)
    data["year_month"] = ym
    data["title"] = title
    data["name"] = path.name
    data["label"] = workbook_label(ym, path, title)
    return data


def set_active_workbook(path: Path, year_month: str | None = None) -> dict[str, Any]:
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(f"Книга не найдена: {path}")
    ym = year_month or year_month_from_path(path) or ""
    title = title_from_workbook_name(path.name)
    meta = {
        "path": str(path),
        "year_month": ym,
        "title": title,
        "name": path.name,
        "label": workbook_label(ym, path, title),
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
    for path in sorted(config.WORKBOOKS_DIR.glob("*.xlsx"), reverse=True):
        if not _BOOK_NAME_RE.match(path.name):
            continue
        ym = year_month_from_path(path) or ""
        title = title_from_workbook_name(path.name)
        items.append(
            {
                "path": str(path.resolve()),
                "name": path.name,
                "year_month": ym,
                "title": title,
                "label": workbook_label(ym, path, title),
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
    title: str | None = None,
) -> Path:
    """
    Create an empty monthly workbook from the source template.
    Optional title → <title>_YYYY-MM.xlsx; without title → YYYY-MM.xlsx.
    Raises WorkbookExistsError if the target file already exists.
    """
    if not (1 <= month <= 12):
        raise ValueError("month must be 1..12")
    if year < 2000 or year > 2100:
        raise ValueError("year out of range")

    slug = sanitize_workbook_title(title) if title else ""
    config.WORKBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    dest = month_workbook_path(year, month, slug or None)
    if dest.exists():
        label = f"{slug}_{year:04d}-{month:02d}" if slug else f"{year:04d}-{month:02d}"
        raise WorkbookExistsError(f"Таблица {label} уже существует")

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


def find_workbooks_for_month(year_month: str) -> list[Path]:
    """All month books for YYYY-MM (bare YYYY-MM.xlsx first, then titled / legacy)."""
    m = YEAR_MONTH_RE.match(year_month.strip())
    if not m:
        raise ValueError("Ожидается формат YYYY-MM")
    year, month = int(m.group(1)), int(m.group(2))
    ym = f"{year:04d}-{month:02d}"
    default = month_workbook_path(year, month)
    found: list[Path] = []
    if default.exists():
        found.append(default.resolve())
    # Titled: Name_YYYY-MM.xlsx; legacy: SE_Lukhovitsy[_Name]_YYYY-MM.xlsx
    for path in sorted(config.WORKBOOKS_DIR.glob(f"*_{ym}.xlsx")):
        if not _BOOK_NAME_RE.match(path.name):
            continue
        resolved = path.resolve()
        if resolved not in found:
            found.append(resolved)
    legacy_bare = config.WORKBOOKS_DIR / f"SE_Lukhovitsy_{ym}.xlsx"
    if legacy_bare.exists():
        resolved = legacy_bare.resolve()
        if resolved not in found:
            found.append(resolved)
    return found


def activate_year_month(year_month: str) -> dict[str, Any]:
    paths = find_workbooks_for_month(year_month)
    if not paths:
        raise FileNotFoundError(f"Нет файла для месяца {year_month}")
    # Prefer default unnamed book if several share the month
    return set_active_workbook(paths[0], year_month)


def activate_workbook_name(name: str) -> dict[str, Any]:
    """Activate by basename inside data/workbooks (path traversal blocked)."""
    base = Path(name).name
    if base != name.replace("\\", "/").split("/")[-1]:
        raise ValueError("Укажите только имя файла")
    path = (config.WORKBOOKS_DIR / base).resolve()
    try:
        path.relative_to(config.WORKBOOKS_DIR.resolve())
    except ValueError as exc:
        raise ValueError("Разрешены только файлы внутри data/workbooks") from exc
    if not _BOOK_NAME_RE.match(path.name):
        raise ValueError("Недопустимое имя книги")
    if not path.is_file():
        raise FileNotFoundError(f"Книга не найдена: {base}")
    return set_active_workbook(path, year_month_from_path(path))


def ensure_month_workbook(year: int, month: int, activate: bool = True) -> tuple[Path, bool]:
    """
    Return the monthly workbook path, creating an empty month if none exists.

    Preference:
      1) active book for this YYYY-MM (incl. titled, e.g. Гарантия_2026-10.xlsx)
      2) any existing book for the month (bare YYYY-MM.xlsx first, then titled)
      3) create bare YYYY-MM.xlsx

    Returns (path, created). When activate=True the chosen book becomes active.
    """
    year_month = f"{year:04d}-{month:02d}"

    meta = get_active_meta()
    if meta and meta.get("year_month") == year_month:
        active_path = Path(meta["path"])
        if active_path.is_file():
            return active_path.resolve(), False

    existing = find_workbooks_for_month(year_month)
    if existing:
        path = existing[0]
        if activate:
            set_active_workbook(path, year_month)
        return path.resolve(), False

    dest = month_workbook_path(year, month)
    try:
        path = create_month_workbook(year, month, activate=activate)
        return path, True
    except WorkbookExistsError:
        if activate:
            set_active_workbook(dest, year_month)
        return dest.resolve(), False


def workbook_for_report_date(report_date: str, activate: bool = True) -> tuple[Path, bool]:
    """Pick existing month book (titled or bare) or create YYYY-MM.xlsx from report_date."""
    try:
        dt = date.fromisoformat(report_date[:10])
    except ValueError as exc:
        raise ValueError(f"Некорректная report_date: {report_date}") from exc
    return ensure_month_workbook(dt.year, dt.month, activate=activate)


_DAY_SHEET_RE = re.compile(r"^(\d{2})$")


def export_workbook_period(
    workbook_path: Path,
    date_from: date,
    date_to: date,
    dest: Path | None = None,
) -> Path:
    """
    Build a downloadable Excel with only day sheets in [date_from, date_to].

    Drops «Данные», «Расчет», «Шаблон» and day sheets outside the range.
    Period must fall within the workbook's YYYY-MM.
    Returns path to the written file (temp if dest is None).
    """
    if date_from > date_to:
        raise ValueError("Дата «с» не может быть позже даты «по»")

    path = Path(workbook_path)
    if not path.is_file():
        raise FileNotFoundError(f"Книга не найдена: {path.name}")

    ym = year_month_from_path(path)
    if not ym or not YEAR_MONTH_RE.match(ym):
        raise ValueError("Не удалось определить месяц книги (ожидается …YYYY-MM.xlsx)")
    book_year, book_month = int(ym[:4]), int(ym[5:7])
    days_in_month = calendar.monthrange(book_year, book_month)[1]
    month_start = date(book_year, book_month, 1)
    month_end = date(book_year, book_month, days_in_month)

    if date_from < month_start or date_to > month_end:
        raise ValueError(
            f"Период должен быть внутри месяца книги {ym} "
            f"({month_start.isoformat()}…{month_end.isoformat()})"
        )

    # Inclusive day list: 27..29 → {27, 28, 29}
    keep_days = [f"{d:02d}" for d in range(date_from.day, date_to.day + 1)]
    keep_set = set(keep_days)

    wb = openpyxl.load_workbook(path)
    try:
        sanitize_workbook(wb)

        # Ensure every day in the range exists (create from «Шаблон» if missing)
        template = wb[config.SHEET_TEMPLATE] if config.SHEET_TEMPLATE in wb.sheetnames else None
        for day_name in keep_days:
            if day_name in wb.sheetnames:
                continue
            day_num = int(day_name)
            if template is not None:
                new_ws = wb.copy_worksheet(template)
                new_ws.title = day_name
                _strip_work_tables(new_ws)
                new_ws.cell(1, 2).value = f"{day_num:02d}.{book_month:02d}.{book_year}"
            else:
                new_ws = wb.create_sheet(day_name)
                new_ws.cell(1, 2).value = f"{day_num:02d}.{book_month:02d}.{book_year}"

        # Drop service sheets and days outside the period
        for name in list(wb.sheetnames):
            if name in keep_set:
                continue
            del wb[name]

        remaining = [n for n in keep_days if n in wb.sheetnames]
        if not remaining:
            raise ValueError("В книге нет дневных листов за выбранный период")
        if set(remaining) != keep_set:
            missing = ", ".join(d for d in keep_days if d not in remaining)
            raise ValueError(f"Не удалось сформировать листы: {missing}")

        # Chronological tab order: 27, 28, 29, …
        for i, name in enumerate(remaining):
            current = wb.sheetnames.index(name)
            if current != i:
                wb.move_sheet(wb[name], offset=i - current)

        if dest is None:
            stem = path.stem
            out_name = f"{stem}_{date_from.day:02d}-{date_to.day:02d}.xlsx"
            dest = Path(tempfile.gettempdir()) / out_name
        else:
            dest = Path(dest)

        dest.parent.mkdir(parents=True, exist_ok=True)
        wb.save(dest)
    finally:
        wb.close()

    return dest.resolve()
