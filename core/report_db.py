# -*- coding: utf-8 -*-
"""Persist parsed reports into a local SQLite database (readable rows)."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from core import config
from core.model_settings import get_active_model


def db_path() -> Path:
    path = getattr(config, "REPORTS_DB", None) or (config.DATA_DIR / "reports.db")
    return Path(path)


def _fold(value: object) -> str:
    """Unicode casefold for Cyrillic-aware search (SQLite NOCASE is ASCII-only)."""
    return str(value or "").casefold()


def _like_contains(raw: str) -> str:
    escaped = (
        str(raw)
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    return f"%{escaped}%"


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.create_function("fold", 1, _fold, deterministic=True)
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> None:
    own = conn is None
    if own:
        conn = connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_date TEXT,
                workers_names TEXT,
                jobs_summary TEXT,
                source_text TEXT,
                source_text_hash TEXT,
                report_json TEXT,
                calculation_json TEXT,
                grand_total REAL,
                unmatched_count INTEGER DEFAULT 0,
                workers_count INTEGER DEFAULT 0,
                jobs_count INTEGER DEFAULT 0,
                model_name TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS report_workers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                worker_no INTEGER NOT NULL,
                worker_name TEXT NOT NULL,
                members TEXT,
                headcount INTEGER DEFAULT 1,
                total REAL,
                per_person REAL,
                FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS report_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                worker_id INTEGER,
                worker_no INTEGER,
                worker_name TEXT,
                job_no INTEGER NOT NULL,
                task_name TEXT NOT NULL,
                job_description TEXT,
                service_type TEXT,
                volume REAL,
                unit TEXT,
                matched INTEGER DEFAULT 0,
                matched_name TEXT,
                unit_price REAL,
                amount REAL,
                FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE,
                FOREIGN KEY(worker_id) REFERENCES report_workers(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS sites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_reports_date ON reports(report_date);
            CREATE INDEX IF NOT EXISTS idx_reports_created ON reports(created_at);
            CREATE INDEX IF NOT EXISTS idx_report_workers_report ON report_workers(report_id);
            CREATE INDEX IF NOT EXISTS idx_report_jobs_report ON report_jobs(report_id);
            CREATE INDEX IF NOT EXISTS idx_report_jobs_worker_name ON report_jobs(worker_name);
            CREATE INDEX IF NOT EXISTS idx_report_jobs_task ON report_jobs(task_name);
            """
        )
        # Миграция старых БД без читаемых колонок и участка
        cols = {r[1] for r in conn.execute("PRAGMA table_info(reports)").fetchall()}
        if "workers_names" not in cols:
            conn.execute("ALTER TABLE reports ADD COLUMN workers_names TEXT")
        if "jobs_summary" not in cols:
            conn.execute("ALTER TABLE reports ADD COLUMN jobs_summary TEXT")
        if "site_id" not in cols:
            conn.execute("ALTER TABLE reports ADD COLUMN site_id INTEGER")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reports_site ON reports(site_id)")
        conn.commit()
    finally:
        if own:
            conn.close()


def list_sites() -> dict[str, Any]:
    """Sites plus how many reports point at each, and the unassigned count."""
    init_db()
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT s.id, s.name, s.created_at, COUNT(r.id) AS reports_count
            FROM sites s
            LEFT JOIN reports r ON r.site_id = s.id
            GROUP BY s.id
            ORDER BY fold(s.name), s.id
            """
        ).fetchall()
        unassigned = conn.execute(
            "SELECT COUNT(*) FROM reports WHERE site_id IS NULL"
        ).fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
        return {
            "sites": [dict(r) for r in rows],
            "unassigned_count": int(unassigned or 0),
            "reports_total": int(total or 0),
        }
    finally:
        conn.close()


def create_site(name: str) -> dict[str, Any]:
    cleaned = " ".join(str(name or "").split())
    if not cleaned:
        raise ValueError("Укажите название участка")
    if len(cleaned) > 80:
        raise ValueError("Название участка не длиннее 80 символов")

    init_db()
    conn = connect()
    try:
        existing = conn.execute("SELECT id, name FROM sites").fetchall()
        for row in existing:
            if _fold(row["name"]) == _fold(cleaned):
                raise ValueError(f"Участок «{row['name']}» уже есть")
        created_at = datetime.now().isoformat(timespec="seconds")
        cur = conn.execute(
            "INSERT INTO sites (name, created_at) VALUES (?, ?)",
            (cleaned, created_at),
        )
        conn.commit()
        return {
            "ok": True,
            "id": int(cur.lastrowid),
            "name": cleaned,
            "created_at": created_at,
            "reports_count": 0,
            "message": f"Участок «{cleaned}» создан",
        }
    finally:
        conn.close()


def _site_name(conn: sqlite3.Connection, site_id: int | None) -> str | None:
    if site_id is None:
        return None
    try:
        sid = int(site_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("Некорректный участок") from exc
    if sid <= 0:
        raise ValueError("Некорректный участок")
    row = conn.execute("SELECT name FROM sites WHERE id = ?", (sid,)).fetchone()
    if not row:
        raise ValueError(f"Участок id={sid} не найден")
    return str(row["name"])


def _worker_display_name(worker: dict[str, Any]) -> str:
    members = worker.get("members")
    if isinstance(members, list):
        names = [str(m).strip() for m in members if str(m).strip()]
        if names:
            return ", ".join(names)
    raw = str(worker.get("raw_worker_name") or "").strip()
    return raw or "Без имени"


def _job_display_name(job: dict[str, Any], calc_job: dict[str, Any] | None = None) -> str:
    if calc_job:
        for key in ("matched_name", "raw_task_name", "job_description"):
            val = calc_job.get(key)
            if val:
                return str(val).strip()
    for key in ("raw_task_name", "job_description"):
        val = job.get(key)
        if val:
            return str(val).strip()
    return "Без названия"


def _calc_workers_index(calculation: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not calculation or not isinstance(calculation, dict):
        return []
    workers = calculation.get("workers")
    return workers if isinstance(workers, list) else []


def _flatten_for_save(
    report: dict[str, Any],
    calculation: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, str]:
    """Build readable worker/job rows + summary strings."""
    calc_workers = _calc_workers_index(calculation)
    report_workers = report.get("workers") or []
    # Если есть расчёт — берём работы из него (там matched_name, тариф, сумма).
    # Пустой список после отсечения работ вне прайса не подменяется исходным отчётом.
    use_calc_jobs = isinstance(calculation, dict)

    worker_rows: list[dict[str, Any]] = []
    job_rows: list[dict[str, Any]] = []
    all_names: list[str] = []
    summary_parts: list[str] = []

    source_workers = calc_workers if use_calc_jobs else report_workers

    for worker in source_workers:
        if not isinstance(worker, dict):
            continue

        # Имена: из расчёта members/raw, иначе из исходного report
        if use_calc_jobs:
            members = worker.get("members") if isinstance(worker.get("members"), list) else []
            names = [str(m).strip() for m in members if str(m).strip()]
            w_name = ", ".join(names) if names else str(worker.get("raw_worker_name") or "").strip() or "Без имени"
            headcount = int(worker.get("headcount") or max(1, len(names) or 1))
            members_s = ", ".join(names) if names else w_name
            try:
                total_f = float(worker["total"]) if worker.get("total") is not None else None
            except (TypeError, ValueError):
                total_f = None
            try:
                per_f = float(worker["per_person"]) if worker.get("per_person") is not None else None
            except (TypeError, ValueError):
                per_f = None
            jobs = worker.get("jobs") or []
        else:
            w_name = _worker_display_name(worker)
            members = worker.get("members") if isinstance(worker.get("members"), list) else []
            members_s = ", ".join(str(m).strip() for m in members if str(m).strip()) or w_name
            headcount = max(1, len([m for m in members if str(m).strip()]) or 1)
            total_f = None
            per_f = None
            jobs = worker.get("performed_jobs") or []

        if not isinstance(jobs, list):
            jobs = []

        kept_jobs: list[dict[str, Any]] = []
        for job in jobs:
            if not isinstance(job, dict):
                continue
            # Расчёт уже знает, есть ли работа в прайсе. Чужие строки в базу не пишем.
            if use_calc_jobs and not job.get("matched"):
                continue
            kept_jobs.append(job)
        if not kept_jobs:
            continue

        worker_rows.append(
            {
                "worker_no": len(worker_rows) + 1,
                "worker_name": w_name,
                "members": members_s,
                "headcount": headcount,
                "total": total_f,
                "per_person": per_f,
            }
        )
        all_names.append(w_name)
        worker_no = len(worker_rows)

        for j_i, job in enumerate(kept_jobs):
            if use_calc_jobs:
                matched_name = job.get("matched_name")
                matched = 1 if job.get("matched") else 0
                task_name = str(matched_name or job.get("raw_task_name") or job.get("job_description") or "Без названия").strip()
                try:
                    unit_price = float(job["unit_price"]) if job.get("unit_price") is not None else None
                except (TypeError, ValueError):
                    unit_price = None
                try:
                    amount = float(job["amount"]) if job.get("amount") is not None else None
                except (TypeError, ValueError):
                    amount = None
                try:
                    volume = float(job["volume"]) if job.get("volume") is not None else None
                except (TypeError, ValueError):
                    volume = None
                unit = str(job.get("unit") or "").strip() or None
                service_type = str(job.get("service_type") or "").strip() or None
                job_description = str(job.get("job_description") or job.get("raw_task_name") or "").strip() or None
            else:
                task_name = _job_display_name(job)
                matched_name = None
                matched = 0
                unit_price = None
                amount = None
                try:
                    volume = float(job.get("volume")) if job.get("volume") is not None else None
                except (TypeError, ValueError):
                    volume = None
                unit = str(job.get("unit") or "").strip() or None
                service_type = str(job.get("service_type") or "").strip() or None
                job_description = str(job.get("job_description") or "").strip() or None

            job_rows.append(
                {
                    "worker_no": worker_no,
                    "worker_name": w_name,
                    "job_no": j_i + 1,
                    "task_name": task_name,
                    "job_description": job_description,
                    "service_type": service_type,
                    "volume": volume,
                    "unit": unit,
                    "matched": matched,
                    "matched_name": str(matched_name).strip() if matched_name else None,
                    "unit_price": unit_price,
                    "amount": amount,
                }
            )
            vol_s = f"{volume:g}" if isinstance(volume, (int, float)) else "?"
            unit_s = unit or ""
            summary_parts.append(f"{w_name}: {task_name} — {vol_s} {unit_s}".strip())

    workers_names = "; ".join(all_names)
    jobs_summary = " | ".join(summary_parts)
    return worker_rows, job_rows, workers_names, jobs_summary


def _calculation_without_unpriced(
    calculation: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    """Drop jobs the price list did not match. Returns (calc, skipped count)."""
    skipped = 0
    workers: list[dict[str, Any]] = []
    grand = 0.0
    for worker in calculation.get("workers") or []:
        if not isinstance(worker, dict):
            continue
        kept: list[dict[str, Any]] = []
        for job in worker.get("jobs") or []:
            if isinstance(job, dict) and job.get("matched"):
                kept.append(job)
            else:
                skipped += 1
        if not kept:
            continue
        item = dict(worker)
        item["jobs"] = kept
        item["unmatched"] = []
        try:
            grand += float(item.get("total") or 0)
        except (TypeError, ValueError):
            pass
        workers.append(item)
    out = dict(calculation)
    out["workers"] = workers
    out["unmatched_count"] = 0
    out["grand_total"] = round(grand, 2)
    return out, skipped


def save_report(
    report: dict[str, Any],
    calculation: dict[str, Any] | None = None,
    source_text: str | None = None,
    site_id: int | None = None,
) -> dict[str, Any]:
    """
    Save report (+ optional calculation) into SQLite as readable rows.
    Tables: reports, report_workers, report_jobs. Optional site_id → sites.
    """
    if not isinstance(report, dict):
        raise ValueError("report должен быть объектом JSON")
    workers = report.get("workers")
    if not isinstance(workers, list) or not workers:
        raise ValueError("В отчёте нет workers[]")

    report_date = report.get("report_date")
    if report_date in ("", "null", None):
        report_date = None
    else:
        report_date = str(report_date).strip() or None

    source_hash = report.get("source_text_hash")
    if source_hash is not None:
        source_hash = str(source_hash)

    calc = calculation if isinstance(calculation, dict) else None
    skipped_unpriced = 0
    if calc is not None:
        calc, skipped_unpriced = _calculation_without_unpriced(calc)

    worker_rows, job_rows, workers_names, jobs_summary = _flatten_for_save(report, calc)
    if not workers_names:
        workers_names = _names_from_report(report)
    report_to_store = report
    if calc is not None:
        report_to_store = dict(report)
        report_to_store["workers"] = [
            {
                "raw_worker_name": wr["worker_name"],
                "members": [p.strip() for p in str(wr["members"] or "").split(",") if p.strip()],
                "performed_jobs": [
                    {
                        "raw_task_name": jr["task_name"],
                        "job_description": jr["job_description"] or jr["task_name"],
                        "service_type": jr["service_type"] or "Общее",
                        "volume": jr["volume"] if jr["volume"] is not None else 0,
                        "unit": jr["unit"] or "",
                    }
                    for jr in job_rows
                    if jr["worker_no"] == wr["worker_no"]
                ],
            }
            for wr in worker_rows
        ]

    grand_total = None
    unmatched_count = 0
    if calc is not None:
        try:
            grand_total = float(calc.get("grand_total") or 0)
        except (TypeError, ValueError):
            grand_total = 0.0
        if worker_rows:
            grand_total = round(
                sum(float(w["total"] or 0) for w in worker_rows),
                2,
            )
    created_at = datetime.now().isoformat(timespec="seconds")
    model_name = get_active_model()
    workers_count = len(worker_rows)
    jobs_count = len(job_rows)

    init_db()
    conn = connect()
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        site_name = _site_name(conn, site_id)
        if site_id is not None:
            site_id = int(site_id)
        cur = conn.execute(
            """
            INSERT INTO reports (
                report_date, workers_names, jobs_summary,
                source_text, source_text_hash,
                report_json, calculation_json,
                grand_total, unmatched_count, workers_count, jobs_count,
                model_name, created_at, site_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_date,
                workers_names,
                jobs_summary,
                source_text,
                source_hash,
                json.dumps(report_to_store, ensure_ascii=False),
                json.dumps(calc, ensure_ascii=False) if calc is not None else None,
                grand_total,
                unmatched_count,
                workers_count,
                jobs_count,
                model_name,
                created_at,
                None if site_id is None else int(site_id),
            ),
        )
        report_id = int(cur.lastrowid)

        worker_id_by_no: dict[int, int] = {}
        for wr in worker_rows:
            wcur = conn.execute(
                """
                INSERT INTO report_workers (
                    report_id, worker_no, worker_name, members,
                    headcount, total, per_person
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    wr["worker_no"],
                    wr["worker_name"],
                    wr["members"],
                    wr["headcount"],
                    wr["total"],
                    wr["per_person"],
                ),
            )
            worker_id_by_no[wr["worker_no"]] = int(wcur.lastrowid)

        for jr in job_rows:
            conn.execute(
                """
                INSERT INTO report_jobs (
                    report_id, worker_id, worker_no, worker_name,
                    job_no, task_name, job_description, service_type,
                    volume, unit, matched, matched_name, unit_price, amount
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    worker_id_by_no.get(jr["worker_no"]),
                    jr["worker_no"],
                    jr["worker_name"],
                    jr["job_no"],
                    jr["task_name"],
                    jr["job_description"],
                    jr["service_type"],
                    jr["volume"],
                    jr["unit"],
                    jr["matched"],
                    jr["matched_name"],
                    jr["unit_price"],
                    jr["amount"],
                ),
            )

        conn.commit()
    finally:
        conn.close()

    return {
        "ok": True,
        "id": report_id,
        "report_date": report_date,
        "workers_names": workers_names,
        "jobs_summary": jobs_summary,
        "grand_total": grand_total,
        "unmatched_count": unmatched_count,
        "workers_count": workers_count,
        "jobs_count": jobs_count,
        "model_name": model_name,
        "created_at": created_at,
        "site_id": site_id,
        "site_name": site_name,
        "db_path": str(db_path()),
        "message": (
            f"Отчёт сохранён в БД (id={report_id}, работ={jobs_count}"
            + (f", участок «{site_name}»" if site_name else "")
            + (
                f", без прайса не записано: {skipped_unpriced}"
                if skipped_unpriced
                else ""
            )
            + ")"
        ),
        "skipped_unpriced": skipped_unpriced,
    }


def _rebuild_report_rollups(conn: sqlite3.Connection, report_id: int) -> None:
    """Пересобрать сотрудников и итог отчёта по текущим строкам работ."""
    jobs = conn.execute(
        """
        SELECT id, worker_name, task_name, volume, unit, amount
        FROM report_jobs
        WHERE report_id = ?
        ORDER BY worker_no, job_no, id
        """,
        (report_id,),
    ).fetchall()
    conn.execute("UPDATE report_jobs SET worker_id = NULL WHERE report_id = ?", (report_id,))
    conn.execute("DELETE FROM report_workers WHERE report_id = ?", (report_id,))
    groups: list[tuple[str, list[sqlite3.Row]]] = []
    index: dict[str, int] = {}
    for job in jobs:
        name = " ".join(str(job["worker_name"] or "").split()) or "Без имени"
        if name not in index:
            index[name] = len(groups)
            groups.append((name, []))
        groups[index[name]][1].append(job)

    names: list[str] = []
    summary: list[str] = []
    grand = 0.0
    for worker_no, (name, group) in enumerate(groups, start=1):
        total = round(sum(float(job["amount"] or 0) for job in group), 2)
        cur = conn.execute(
            """
            INSERT INTO report_workers (
                report_id, worker_no, worker_name, members, headcount, total, per_person
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (report_id, worker_no, name, name, 1, total, total),
        )
        worker_id = int(cur.lastrowid)
        for job_no, job in enumerate(group, start=1):
            conn.execute(
                """
                UPDATE report_jobs
                SET worker_id = ?, worker_no = ?, job_no = ?, worker_name = ?
                WHERE id = ?
                """,
                (worker_id, worker_no, job_no, name, job["id"]),
            )
            volume = job["volume"]
            vol_s = f"{float(volume):g}" if isinstance(volume, (int, float)) else "?"
            summary.append(f"{name}: {job['task_name']} — {vol_s} {job['unit'] or ''}".strip())
        names.append(name)
        grand += total

    if names:
        conn.execute(
            """
            UPDATE reports
            SET workers_names = ?, jobs_summary = ?, grand_total = ?,
                workers_count = ?, jobs_count = ?
            WHERE id = ?
            """,
            ("; ".join(names), " | ".join(summary), round(grand, 2), len(groups), len(jobs), report_id),
        )
    else:
        conn.execute(
            """
            UPDATE reports
            SET jobs_summary = '', grand_total = 0, workers_count = 0, jobs_count = 0
            WHERE id = ?
            """,
            (report_id,),
        )


def update_report_header(
    report_id: int,
    *,
    report_date: str | None = None,
    site_id: int | None = None,
    site_set: bool = False,
) -> dict[str, Any]:
    """Изменить дату и участок отчёта. Строки работ остаются в этой папке."""
    init_db()
    conn = connect()
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        row = conn.execute("SELECT id, workers_names FROM reports WHERE id = ?", (report_id,)).fetchone()
        if not row:
            raise ValueError(f"Отчёт id={report_id} не найден")
        sets: list[str] = []
        params: list[Any] = []
        if report_date is not None:
            cleaned = _iso_date(report_date, "report_date")
            if not cleaned:
                raise ValueError("Укажите дату отчёта")
            sets.append("report_date = ?")
            params.append(cleaned)
        if site_set:
            site_name = _site_name(conn, site_id)
            sets.append("site_id = ?")
            params.append(None if site_id is None else int(site_id))
        else:
            site_name = None
        if not sets:
            raise ValueError("Нечего изменять")
        params.append(int(report_id))
        conn.execute(f"UPDATE reports SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()
        saved = conn.execute(
            """
            SELECT r.id, r.report_date, r.workers_names, r.site_id, s.name AS site_name, r.grand_total
            FROM reports r
            LEFT JOIN sites s ON s.id = r.site_id
            WHERE r.id = ?
            """,
            (report_id,),
        ).fetchone()
        return {
            "ok": True,
            "id": int(saved["id"]),
            "report_date": saved["report_date"],
            "site_id": saved["site_id"],
            "site_name": saved["site_name"],
            "title": _report_folder_title(int(saved["id"]), saved["report_date"], saved["workers_names"]),
            "grand_total": saved["grand_total"],
            "message": "Отчёт обновлён",
        }
    finally:
        conn.close()


def update_report_job(
    job_id: int,
    *,
    worker_name: str,
    task_name: str,
    volume: float,
    unit: str,
    unit_price: float,
) -> dict[str, Any]:
    """Изменить строку работы. Сумма = объём × тариф, итог папки пересчитывается."""
    name = " ".join(str(worker_name or "").split())
    task = " ".join(str(task_name or "").split())
    if not name:
        raise ValueError("Укажите ФИО")
    if len(name) > 200:
        raise ValueError("ФИО не длиннее 200 символов")
    if not task:
        raise ValueError("Укажите работу")
    if len(task) > 400:
        raise ValueError("Название работы не длиннее 400 символов")
    try:
        vol = float(volume)
        price = float(unit_price)
    except (TypeError, ValueError) as exc:
        raise ValueError("Объём и тариф должны быть числами") from exc
    if vol < 0 or price < 0:
        raise ValueError("Объём и тариф не могут быть отрицательными")
    unit_s = " ".join(str(unit or "").split()) or "шт"
    if len(unit_s) > 20:
        raise ValueError("Единица не длиннее 20 символов")
    amount = round(vol * price, 2)

    init_db()
    conn = connect()
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        job = conn.execute(
            "SELECT id, report_id FROM report_jobs WHERE id = ?",
            (int(job_id),),
        ).fetchone()
        if not job:
            raise ValueError(f"Строка id={job_id} не найдена")
        report_id = int(job["report_id"])
        conn.execute(
            """
            UPDATE report_jobs
            SET worker_name = ?, task_name = ?, job_description = ?,
                matched_name = ?, volume = ?, unit = ?, unit_price = ?, amount = ?,
                matched = 1
            WHERE id = ?
            """,
            (name, task, task, task, vol, unit_s, price, amount, int(job_id)),
        )
        _rebuild_report_rollups(conn, report_id)
        conn.commit()
        return {
            "ok": True,
            "id": int(job_id),
            "report_id": report_id,
            "worker_name": name,
            "task_name": task,
            "volume": vol,
            "unit": unit_s,
            "unit_price": price,
            "amount": amount,
            "message": "Строка обновлена",
        }
    finally:
        conn.close()


def delete_report(report_id: int) -> dict[str, Any]:
    """Удалить отчёт вместе со всеми его строками."""
    init_db()
    conn = connect()
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        row = conn.execute("SELECT id FROM reports WHERE id = ?", (int(report_id),)).fetchone()
        if not row:
            raise ValueError(f"Отчёт id={report_id} не найден")
        conn.execute("DELETE FROM reports WHERE id = ?", (int(report_id),))
        conn.commit()
        return {"ok": True, "id": int(report_id), "message": "Отчёт удалён"}
    finally:
        conn.close()


def delete_report_job(job_id: int) -> dict[str, Any]:
    """Удалить одну строку. Папка отчёта остаётся."""
    init_db()
    conn = connect()
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        job = conn.execute(
            "SELECT id, report_id FROM report_jobs WHERE id = ?",
            (int(job_id),),
        ).fetchone()
        if not job:
            raise ValueError(f"Строка id={job_id} не найдена")
        report_id = int(job["report_id"])
        conn.execute("DELETE FROM report_jobs WHERE id = ?", (int(job_id),))
        _rebuild_report_rollups(conn, report_id)
        conn.commit()
        return {
            "ok": True,
            "id": int(job_id),
            "report_id": report_id,
            "message": "Строка удалена",
        }
    finally:
        conn.close()


def list_reports(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT r.id, r.report_date, r.workers_names, r.jobs_summary,
                   r.grand_total, r.unmatched_count,
                   r.workers_count, r.jobs_count, r.model_name, r.created_at,
                   r.site_id, s.name AS site_name
            FROM reports r
            LEFT JOIN sites s ON s.id = r.site_id
            ORDER BY r.id DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 500)),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_report_details(report_id: int) -> dict[str, Any] | None:
    """Readable header + workers + jobs for one report."""
    init_db()
    conn = connect()
    try:
        head = conn.execute(
            """
            SELECT r.id, r.report_date, r.workers_names, r.jobs_summary,
                   r.grand_total, r.unmatched_count, r.workers_count, r.jobs_count,
                   r.model_name, r.created_at, r.source_text,
                   r.site_id, s.name AS site_name
            FROM reports r
            LEFT JOIN sites s ON s.id = r.site_id
            WHERE r.id = ?
            """,
            (report_id,),
        ).fetchone()
        if not head:
            return None
        workers = conn.execute(
            """
            SELECT worker_no, worker_name, members, headcount, total, per_person
            FROM report_workers
            WHERE report_id = ?
            ORDER BY worker_no
            """,
            (report_id,),
        ).fetchall()
        jobs = conn.execute(
            """
            SELECT worker_name, job_no, task_name, job_description, service_type,
                   volume, unit, matched, matched_name, unit_price, amount
            FROM report_jobs
            WHERE report_id = ?
            ORDER BY worker_no, job_no
            """,
            (report_id,),
        ).fetchall()
        return {
            "report": dict(head),
            "workers": [dict(r) for r in workers],
            "jobs": [dict(r) for r in jobs],
        }
    finally:
        conn.close()


def _names_from_report(report: dict[str, Any]) -> str:
    names: list[str] = []
    for worker in report.get("workers") or []:
        if not isinstance(worker, dict):
            continue
        name = _worker_display_name(worker)
        if name and name not in names:
            names.append(name)
    return "; ".join(names)


def _report_folder_title(report_id: int, report_date: str | None, workers_names: str | None) -> str:
    date_s = ""
    raw = str(report_date or "")[:10]
    parts = raw.split("-")
    if len(parts) == 3 and all(parts):
        date_s = f"{parts[2]}.{parts[1]}.{parts[0]}"
    who = " ".join(str(workers_names or "").split())
    if date_s and who:
        return f"{date_s} — {who}"
    return date_s or who or f"Отчёт {report_id}"


def _iso_date(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    raw = raw[:10]
    try:
        datetime.strptime(raw, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"Некорректная дата «{field}»: ожидается ГГГГ-ММ-ДД") from exc
    return raw


def load_reports_for_excel(report_ids: list[int]) -> list[dict[str, Any]]:
    """Reports with worker blocks and jobs, in the requested order, for Excel export."""
    if not isinstance(report_ids, list) or not report_ids:
        raise ValueError("Выберите хотя бы один отчёт")
    ids: list[int] = []
    seen: set[int] = set()
    for raw in report_ids:
        try:
            rid = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("Некорректный номер отчёта") from exc
        if rid <= 0:
            raise ValueError("Некорректный номер отчёта")
        if rid in seen:
            continue
        seen.add(rid)
        ids.append(rid)
    if len(ids) > 200:
        raise ValueError("За один раз можно скачать не больше 200 отчётов")

    init_db()
    conn = connect()
    try:
        marks = ",".join("?" for _ in ids)
        heads = conn.execute(
            f"SELECT id, report_date FROM reports WHERE id IN ({marks})",
            ids,
        ).fetchall()
        found = {int(row["id"]): row for row in heads}
        missing = [str(rid) for rid in ids if rid not in found]
        if missing:
            raise ValueError("Отчёты не найдены: " + ", ".join(missing))
        undated = [str(rid) for rid in ids if not str(found[rid]["report_date"] or "").strip()]
        if undated:
            raise ValueError("У отчётов нет даты: " + ", ".join(undated))

        worker_rows = conn.execute(
            f"""
            SELECT report_id, worker_no, worker_name, members, headcount, total, per_person
            FROM report_workers
            WHERE report_id IN ({marks})
            ORDER BY report_id, worker_no
            """,
            ids,
        ).fetchall()
        job_rows = conn.execute(
            f"""
            SELECT
                report_id, worker_no, job_no, task_name, job_description, service_type,
                volume, unit, matched, matched_name, unit_price, amount
            FROM report_jobs
            WHERE report_id IN ({marks})
            ORDER BY report_id, worker_no, job_no, id
            """,
            ids,
        ).fetchall()
    finally:
        conn.close()

    jobs_by: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for job in job_rows:
        jobs_by.setdefault((int(job["report_id"]), int(job["worker_no"])), []).append(dict(job))

    workers_by: dict[int, list[dict[str, Any]]] = {}
    for worker in worker_rows:
        item = dict(worker)
        item["jobs"] = jobs_by.get((int(worker["report_id"]), int(worker["worker_no"])), [])
        workers_by.setdefault(int(worker["report_id"]), []).append(item)

    reports: list[dict[str, Any]] = []
    for rid in ids:
        reports.append(
            {
                "id": rid,
                "report_date": str(found[rid]["report_date"])[:10],
                "workers": workers_by.get(rid, []),
            }
        )
    return reports


def query_db_rows(
    *,
    site_id: int | None = None,
    unassigned: bool = False,
    date_from: str | None = None,
    date_to: str | None = None,
    fio: str | None = None,
    limit: int = 1000,
) -> dict[str, Any]:
    """
    Reports as folders, job lines nested inside each report.
    Filters: site (or unassigned), report date range, worker name substring.
    """
    if unassigned and site_id is not None:
        raise ValueError("Укажите либо участок, либо «без участка»")

    d_from = _iso_date(date_from, "from")
    d_to = _iso_date(date_to, "to")
    if d_from and d_to and d_from > d_to:
        raise ValueError("Дата «с» позже даты «по»")

    fio_raw = " ".join(str(fio or "").split())
    if len(fio_raw) > 120:
        raise ValueError("ФИО для поиска не длиннее 120 символов")

    where = ["1 = 1"]
    params: list[Any] = []
    if unassigned:
        where.append("r.site_id IS NULL")
    elif site_id is not None:
        try:
            sid = int(site_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("Некорректный участок") from exc
        if sid <= 0:
            raise ValueError("Некорректный участок")
        where.append("r.site_id = ?")
        params.append(sid)

    if d_from:
        where.append("r.report_date >= ?")
        params.append(d_from)
    if d_to:
        where.append("r.report_date <= ?")
        params.append(d_to)

    cap = max(1, min(int(limit), 2000))
    sql_where = " AND ".join(where)
    fio_pattern = _like_contains(_fold(fio_raw)) if fio_raw else None
    init_db()
    conn = connect()
    try:
        total_reports = conn.execute(
            f"SELECT COUNT(*) FROM reports r WHERE {sql_where}",
            params,
        ).fetchone()[0]
        heads = conn.execute(
            f"""
            SELECT
                r.id AS report_id,
                r.report_date,
                r.created_at,
                r.workers_names,
                r.site_id,
                s.name AS site_name
            FROM reports r
            LEFT JOIN sites s ON s.id = r.site_id
            WHERE {sql_where}
            ORDER BY r.report_date DESC, r.id DESC
            LIMIT ?
            """,
            (*params, cap),
        ).fetchall()
        ids = [int(h["report_id"]) for h in heads]
        jobs_by_report: dict[int, list[dict[str, Any]]] = {i: [] for i in ids}
        if ids:
            marks = ",".join("?" for _ in ids)
            job_where = f"j.report_id IN ({marks})"
            job_params: list[Any] = list(ids)
            if fio_pattern:
                job_where += " AND fold(j.worker_name) LIKE ? ESCAPE '\\'"
                job_params.append(fio_pattern)
            job_rows = conn.execute(
                f"""
                SELECT
                    j.id AS job_id,
                    j.report_id,
                    j.worker_name,
                    j.task_name,
                    j.job_description,
                    j.service_type,
                    j.volume,
                    j.unit,
                    j.matched,
                    j.matched_name,
                    j.unit_price,
                    j.amount
                FROM report_jobs j
                WHERE {job_where}
                ORDER BY j.report_id, j.worker_no, j.job_no
                """,
                job_params,
            ).fetchall()
            for job in job_rows:
                jobs_by_report.setdefault(int(job["report_id"]), []).append(dict(job))

        reports: list[dict[str, Any]] = []
        flat: list[dict[str, Any]] = []
        for head in heads:
            rid = int(head["report_id"])
            jobs = jobs_by_report.get(rid, [])
            title_names = head["workers_names"] or ""
            if fio_pattern and not jobs and fio_raw.casefold() not in _fold(title_names):
                continue
            amount = round(sum(float(j["amount"] or 0) for j in jobs), 2)
            folder = {
                "id": rid,
                "title": _report_folder_title(rid, head["report_date"], title_names),
                "report_date": head["report_date"],
                "created_at": head["created_at"],
                "site_id": head["site_id"],
                "site_name": head["site_name"],
                "workers_names": title_names,
                "jobs_count": len(jobs),
                "amount": amount,
                "jobs": jobs,
            }
            reports.append(folder)
            for job in jobs:
                flat.append({
                    **job,
                    "report_id": rid,
                    "report_date": head["report_date"],
                    "created_at": head["created_at"],
                    "site_id": head["site_id"],
                    "site_name": head["site_name"],
                })

        worker_names = {j["worker_name"] for j in flat if j.get("worker_name")}
        return {
            "reports": reports,
            "rows": flat,
            "summary": {
                "reports": len(reports),
                "jobs": len(flat),
                "workers": len(worker_names),
                "amount": round(sum(float(j["amount"] or 0) for j in flat), 2),
                "truncated": int(total_reports or 0) > len(heads),
            },
            "filters": {
                "site_id": None if unassigned or site_id is None else int(site_id),
                "unassigned": bool(unassigned),
                "date_from": d_from,
                "date_to": d_to,
                "fio": fio_raw,
            },
        }
    finally:
        conn.close()
