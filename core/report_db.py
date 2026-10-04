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


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
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

            CREATE INDEX IF NOT EXISTS idx_reports_date ON reports(report_date);
            CREATE INDEX IF NOT EXISTS idx_reports_created ON reports(created_at);
            CREATE INDEX IF NOT EXISTS idx_report_workers_report ON report_workers(report_id);
            CREATE INDEX IF NOT EXISTS idx_report_jobs_report ON report_jobs(report_id);
            CREATE INDEX IF NOT EXISTS idx_report_jobs_worker_name ON report_jobs(worker_name);
            CREATE INDEX IF NOT EXISTS idx_report_jobs_task ON report_jobs(task_name);
            """
        )
        # Миграция старых БД без читаемых колонок
        cols = {r[1] for r in conn.execute("PRAGMA table_info(reports)").fetchall()}
        if "workers_names" not in cols:
            conn.execute("ALTER TABLE reports ADD COLUMN workers_names TEXT")
        if "jobs_summary" not in cols:
            conn.execute("ALTER TABLE reports ADD COLUMN jobs_summary TEXT")
        conn.commit()
    finally:
        if own:
            conn.close()


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
    use_calc_jobs = bool(calc_workers)

    worker_rows: list[dict[str, Any]] = []
    job_rows: list[dict[str, Any]] = []
    all_names: list[str] = []
    summary_parts: list[str] = []

    source_workers = calc_workers if use_calc_jobs else report_workers

    for w_i, worker in enumerate(source_workers):
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

        worker_rows.append(
            {
                "worker_no": w_i + 1,
                "worker_name": w_name,
                "members": members_s,
                "headcount": headcount,
                "total": total_f,
                "per_person": per_f,
            }
        )
        all_names.append(w_name)

        if not isinstance(jobs, list):
            jobs = []

        for j_i, job in enumerate(jobs):
            if not isinstance(job, dict):
                continue

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
                    "worker_no": w_i + 1,
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


def save_report(
    report: dict[str, Any],
    calculation: dict[str, Any] | None = None,
    source_text: str | None = None,
) -> dict[str, Any]:
    """
    Save report (+ optional calculation) into SQLite as readable rows.
    Tables: reports, report_workers, report_jobs.
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
    grand_total = None
    unmatched_count = 0
    if calc is not None:
        try:
            grand_total = float(calc.get("grand_total") or 0)
        except (TypeError, ValueError):
            grand_total = 0.0
        try:
            unmatched_count = int(calc.get("unmatched_count") or 0)
        except (TypeError, ValueError):
            unmatched_count = 0

    worker_rows, job_rows, workers_names, jobs_summary = _flatten_for_save(report, calc)
    created_at = datetime.now().isoformat(timespec="seconds")
    model_name = get_active_model()
    workers_count = len(worker_rows)
    jobs_count = len(job_rows)

    init_db()
    conn = connect()
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.execute(
            """
            INSERT INTO reports (
                report_date, workers_names, jobs_summary,
                source_text, source_text_hash,
                report_json, calculation_json,
                grand_total, unmatched_count, workers_count, jobs_count,
                model_name, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_date,
                workers_names,
                jobs_summary,
                source_text,
                source_hash,
                json.dumps(report, ensure_ascii=False),
                json.dumps(calc, ensure_ascii=False) if calc is not None else None,
                grand_total,
                unmatched_count,
                workers_count,
                jobs_count,
                model_name,
                created_at,
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
        "db_path": str(db_path()),
        "message": f"Отчёт сохранён в БД (id={report_id}, работ={jobs_count})",
    }


def list_reports(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT id, report_date, workers_names, jobs_summary,
                   grand_total, unmatched_count,
                   workers_count, jobs_count, model_name, created_at
            FROM reports
            ORDER BY id DESC
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
            SELECT id, report_date, workers_names, jobs_summary,
                   grand_total, unmatched_count, workers_count, jobs_count,
                   model_name, created_at, source_text
            FROM reports WHERE id = ?
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
