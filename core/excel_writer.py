# -*- coding: utf-8 -*-
"""
Append report data into SE_Lukhovitsy day sheets (01..31).

Writes into the monthly workbook that matches report_date (YYYY-MM).
If that file does not exist, an empty month is created and activated.

Brigade = one block:
  C = ФИО участников (по одному в строке, сверху блока)
  D = наименование работы (общий список один раз)
  E = volume, F = unit
  G = VLOOKUP tariff, H = G*E
  I = H / N  (ЗП 1 сотруднику — деление поровну на бригаду)

Для наработки K:L (SUMIF по C) после работ пишется строка на каждого
участника с I = сумма блока / N.
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import openpyxl

from core import config
from core.pricing import CalcResult, WorkerCalc
from core.workbook_factory import (
    get_active_workbook,
    sanitize_workbook,
    workbook_for_report_date,
    written_log_for,
    year_month_from_path,
)


def ensure_working_workbook() -> Path:
    """Return the currently active monthly workbook (creates/bootstraps if needed)."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.WORKBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    return get_active_workbook()


def _written_log_path(workbook_path: Path | None = None) -> Path:
    path = workbook_path or ensure_working_workbook()
    log_path = written_log_for(path)
    # migrate legacy global log only when using legacy workbook.xlsx
    if (
        not log_path.exists()
        and path.resolve() == config.WORKING_WORKBOOK.resolve()
        and config.WRITTEN_LOG.exists()
    ):
        return config.WRITTEN_LOG
    return log_path


def _load_written(workbook_path: Path | None = None) -> dict[str, Any]:
    log_path = _written_log_path(workbook_path)
    if log_path.exists():
        return json.loads(log_path.read_text(encoding="utf-8"))
    return {"entries": []}


def get_written_log(workbook_path: Path | None = None) -> dict[str, Any]:
    """Public read of per-workbook Excel write history."""
    data = _load_written(workbook_path)
    path = workbook_path or ensure_working_workbook()
    return {
        "workbook": str(path),
        "log_path": str(_written_log_path(path)),
        "entries": list(data.get("entries") or []),
    }


def _save_written(data: dict[str, Any], workbook_path: Path | None = None) -> None:
    log_path = _written_log_path(workbook_path)
    log_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _day_sheet_name(report_date: str) -> str:
    try:
        dt = datetime.strptime(report_date[:10], "%Y-%m-%d")
        return f"{dt.day:02d}"
    except ValueError as exc:
        raise ValueError(f"Некорректная report_date: {report_date}") from exc


def _next_free_row(ws) -> int:
    last = 1
    for r in range(1, (ws.max_row or 1) + 1):
        if any(ws.cell(r, c).value is not None for c in range(2, 10)):
            last = r
    return last + 2


def _set_date(ws, report_date: str) -> None:
    try:
        dt = datetime.strptime(report_date[:10], "%Y-%m-%d")
        ws.cell(*config.DAY_DATE_CELL).value = dt.strftime("%d.%m.%Y")
    except ValueError:
        ws.cell(*config.DAY_DATE_CELL).value = report_date


def _atomic_save(wb: openpyxl.Workbook, path: Path) -> None:
    """Save workbook via temp file. Closes wb to release Windows file locks."""
    import os

    sanitize_workbook(wb)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(suffix=".xlsx", dir=str(path.parent))
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        wb.save(tmp_path)
        wb.close()
        os.replace(tmp_path, path)
    except Exception:
        wb.close()
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


#(Правка кода Новиков С.С 29.07.2026)
def _write_worker_block(
    ws,
    start_row: int,
    worker: WorkerCalc,
) -> tuple[int, int, int]:
    """
    One Excel block per brigade (or solo worker).

    ФИО бригады — в первой строке блока в C; работы по строкам; I = H/N (поровну).
    """
    members = [m for m in (worker.members or []) if m] or [worker.raw_worker_name]
    n_people = max(1, len(members))
    jobs = list(worker.jobs)

    r = start_row
    ws.cell(r, config.COL_NUM).value = "№ п/п"
    ws.cell(r, config.COL_PEOPLE).value = "кол. человек"
    ws.cell(r, config.COL_WORK).value = "Наименование работ"
    ws.cell(r, config.COL_QTY).value = "Кол-во работы"
    ws.cell(r, config.COL_UNIT).value = "ЕД измер"
    ws.cell(r, config.COL_TARIFF).value = "Тариф"
    ws.cell(r, config.COL_WAGE).value = "Заработная плата руб"
    ws.cell(r, config.COL_PER_PERSON).value = "ЗП 1 сотруднику"
    r += 1

    data_start = r
    filled = 0
    block_rows = max(len(jobs), 1)

    for i in range(block_rows):
        # ФИО только в первой строке блока (в виде списка через запятую)
        if i == 0:
            ws.cell(r, config.COL_PEOPLE).value = ", ".join(members)

        if i < len(jobs):
            job = jobs[i]
            filled += 1
            ws.cell(r, config.COL_NUM).value = i + 1

            # Правка Новиков С.С. (28.07.2026)
            if job.matched and job.matched_name:
                work_name = job.matched_name  # official из прайса
            else:
                base = (job.raw_task_name or job.job_description or "Без названия").strip()
                work_name = f"{base} (не найдено в прайсе)"
            ws.cell(r, config.COL_WORK).value = work_name

            ws.cell(r, config.COL_QTY).value = float(job.volume)
            ws.cell(r, config.COL_UNIT).value = job.unit or "шт"
            ws.cell(r, config.COL_TARIFF).value = (
                f"=IFERROR(VLOOKUP(D{r},Данные!$B$4:$C$355,2,FALSE),0)"
            )
            ws.cell(r, config.COL_WAGE).value = f"=G{r}*E{r}"
            ws.cell(r, config.COL_PER_PERSON).value = f"=IFERROR(H{r}/{n_people},0)"
        elif filled == 0 and i == 0:
            ws.cell(r, config.COL_NUM).value = 1
            ws.cell(r, config.COL_WORK).value = "(нет сопоставленных работ)"
        r += 1

    data_end = r - 1
    ws.cell(r, config.COL_PEOPLE).value = n_people
    ws.cell(r, config.COL_TARIFF).value = "Итог:"
    ws.cell(r, config.COL_WAGE).value = f"=SUM(H{data_start}:H{data_end})"
    return start_row, r, filled


def append_calc_to_workbook(
    calc: CalcResult,
    workbook_path: Path | None = None,
    skip_duplicates: bool = True,
) -> dict[str, Any]:
    if not calc.report_date:
        raise ValueError("Для записи в Excel нужна report_date")

    created = False
    if workbook_path is None:
        path, created = workbook_for_report_date(calc.report_date, activate=True)
    else:
        path = Path(workbook_path)

    year_month = year_month_from_path(path)

    report_id = f"{calc.report_date}:{calc.source_text_hash or ''}"
    written = _load_written(path)
    if skip_duplicates and any(e.get("report_id") == report_id for e in written["entries"]):
        return {
            "ok": False,
            "duplicate": True,
            "report_id": report_id,
            "workbook": str(path),
            "year_month": year_month,
            "workbook_created": created,
            "message": "Этот отчёт уже был записан в Excel",
        }

    day_name = _day_sheet_name(calc.report_date)
    wb = openpyxl.load_workbook(path)
    if day_name not in wb.sheetnames:
        raise KeyError(f"В книге нет листа дня '{day_name}'")

    day_ws = wb[day_name]
    _set_date(day_ws, calc.report_date)

    blocks_written = []
    unmatched_jobs = []
    cursor = _next_free_row(day_ws)

    for worker in calc.workers:
        for job in worker.unmatched:
            unmatched_jobs.append(
                {
                    "worker": worker.raw_worker_name,
                    "job": job.job_description or job.raw_task_name,
                }
            )
        start, end, filled = _write_worker_block(day_ws, cursor, worker)
        blocks_written.append(
            {
                "worker": worker.raw_worker_name,
                "members": worker.members,
                "headcount": worker.headcount,
                "rows": [start, end],
                "filled_jobs": filled,
                "total": worker.total,
                "per_person": worker.per_person,
            }
        )
        cursor = end + 2

    # --- НОВЫЙ БЛОК: суммарная выработка по сотрудникам (правый столбец) ---

    # Собираем суммарную выработку по каждому сотруднику
    per_person_totals: dict[str, float] = {}
    for block in blocks_written:
        members = block.get("members") or []
        per_person = float(block.get("per_person") or 0.0)
        for m in members:
            if not m:
                continue
            key = str(m).strip()
            per_person_totals[key] = per_person_totals.get(key, 0.0) + per_person

    # Заполняем правую таблицу ФИО / Наработка по словарю
    start_row, end_row = config.DAY_PEOPLE_SUM_RANGE
    for r in range(start_row, end_row + 1):
        name_cell = day_ws.cell(r, config.COL_PEOPLE_SUM_NAME)
        wage_cell = day_ws.cell(r, config.COL_PEOPLE_SUM_WAGE)
        name = str(name_cell.value or "").strip()
        if not name:
            continue
        total = per_person_totals.get(name)
        wage_cell.value = float(total) if total is not None else 0.0

    # --- КОНЕЦ НОВОГО БЛОКА ---

    _atomic_save(wb, path)

    entry = {
        "report_id": report_id,
        "report_date": calc.report_date,
        "day_sheet": day_name,
        "written_at": datetime.now().isoformat(timespec="seconds"),
        "blocks": blocks_written,
        "unmatched_jobs": unmatched_jobs,
        "grand_total": calc.grand_total,
    }
    written["entries"].append(entry)
    _save_written(written, path)

    return {
        "ok": True,
        "duplicate": False,
        "report_id": report_id,
        "workbook": str(path),
        "year_month": year_month,
        "workbook_created": created,
        "day_sheet": day_name,
        "blocks": blocks_written,
        "unmatched_jobs": unmatched_jobs,
        "grand_total": calc.grand_total,
        "message": f"Записано на лист {day_name}",
    }
