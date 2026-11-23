# -*- coding: utf-8 -*-
"""SQLite reports browser: sites and filters."""
from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core import config
from core.report_db import (
    create_site,
    init_db,
    list_sites,
    load_reports_for_excel,
    query_db_rows,
    save_report,
    delete_report,
    delete_report_job,
    update_report_header,
    update_report_job,
)


REPORT = {
    "report_date": "2026-06-15",
    "workers": [
        {
            "raw_worker_name": "Карандак В.Е.",
            "performed_jobs": [
                {
                    "raw_task_name": "Выкладка запаса",
                    "volume": 2,
                    "unit": "шт",
                }
            ],
        },
        {
            "raw_worker_name": "Лошкомойников С.И.",
            "performed_jobs": [
                {
                    "raw_task_name": "Обжим RJ-45",
                    "volume": 1,
                    "unit": "шт",
                }
            ],
        },
    ],
}


class ReportDbBrowserTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._old = config.REPORTS_DB
        config.REPORTS_DB = Path(self._tmp.name) / "reports.db"

    def tearDown(self):
        config.REPORTS_DB = self._old
        self._tmp.cleanup()

    def test_create_site_and_filter_rows(self):
        north = create_site("  Север  ")
        south = create_site("Юг")
        self.assertEqual(north["name"], "Север")
        with self.assertRaises(ValueError):
            create_site("север")

        save_report(REPORT, site_id=north["id"])
        other = dict(REPORT)
        other["report_date"] = "2026-07-02"
        save_report(other, site_id=south["id"])
        save_report(
            {
                "report_date": "2026-06-20",
                "workers": [
                    {
                        "raw_worker_name": "Карандак В.Е.",
                        "performed_jobs": [{"raw_task_name": "Муфта", "volume": 1, "unit": "шт"}],
                    }
                ],
            }
        )

        overview = list_sites()
        self.assertEqual(overview["reports_total"], 3)
        self.assertEqual(overview["unassigned_count"], 1)
        names = [s["name"] for s in overview["sites"]]
        self.assertEqual(names, ["Север", "Юг"])

        by_site = query_db_rows(site_id=north["id"])
        self.assertEqual(by_site["summary"]["reports"], 1)
        self.assertEqual(by_site["summary"]["jobs"], 2)
        self.assertTrue(all(r["site_name"] == "Север" for r in by_site["rows"]))

        by_fio = query_db_rows(fio="лошкомойников")
        self.assertEqual(len(by_fio["rows"]), 2)
        self.assertTrue(all("Лошкомойников" in r["worker_name"] for r in by_fio["rows"]))

        by_date = query_db_rows(date_from="2026-07-01", date_to="2026-07-31")
        self.assertEqual(by_date["summary"]["reports"], 1)
        self.assertEqual(by_date["rows"][0]["site_name"], "Юг")

        bare = query_db_rows(unassigned=True, fio="Карандак")
        self.assertEqual(len(bare["rows"]), 1)
        self.assertIsNone(bare["rows"][0]["site_name"])

        with self.assertRaises(ValueError):
            query_db_rows(date_from="2026-08-01", date_to="2026-07-01")
        with self.assertRaises(ValueError):
            save_report(REPORT, site_id=999)

    def test_migrates_old_reports_table(self):
        path = config.REPORTS_DB
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.execute(
            """
            CREATE TABLE reports (
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
            )
            """
        )
        conn.commit()
        conn.close()

        init_db()
        site = create_site("Гарантия")
        saved = save_report(REPORT, site_id=site["id"])
        self.assertEqual(saved["site_name"], "Гарантия")
        rows = query_db_rows(site_id=site["id"])
        self.assertEqual(rows["summary"]["jobs"], 2)

    def test_skips_jobs_missing_from_price(self):
        saved = save_report(
            REPORT,
            calculation={
                "grand_total": 100,
                "unmatched_count": 1,
                "workers": [
                    {
                        "raw_worker_name": "Карандак В.Е.",
                        "members": ["Карандак В.Е."],
                        "headcount": 1,
                        "total": 100,
                        "per_person": 100,
                        "jobs": [
                            {
                                "raw_task_name": "Выкладка запаса",
                                "job_description": "Выкладка запаса",
                                "matched": True,
                                "matched_name": "Выкладка запаса кабеля",
                                "volume": 2,
                                "unit": "шт",
                                "unit_price": 50,
                                "amount": 100,
                            },
                            {
                                "raw_task_name": "Несуществующая работа",
                                "job_description": "Несуществующая работа",
                                "matched": False,
                                "matched_name": None,
                                "volume": 4,
                                "unit": "шт",
                                "unit_price": None,
                                "amount": None,
                            },
                        ],
                    },
                    {
                        "raw_worker_name": "Без работ в прайсе",
                        "members": ["Без работ в прайсе"],
                        "headcount": 1,
                        "total": 0,
                        "per_person": 0,
                        "jobs": [
                            {
                                "raw_task_name": "Тоже нет в прайсе",
                                "matched": False,
                                "volume": 1,
                                "unit": "шт",
                            }
                        ],
                    },
                ],
            },
        )
        self.assertEqual(saved["jobs_count"], 1)
        self.assertEqual(saved["workers_count"], 1)
        self.assertEqual(saved["skipped_unpriced"], 2)
        self.assertEqual(saved["grand_total"], 100)
        self.assertNotIn("Несуществующая", saved["jobs_summary"])
        self.assertNotIn("Без работ", saved["workers_names"])
        rows = query_db_rows()
        self.assertEqual(len(rows["rows"]), 1)
        self.assertEqual(rows["rows"][0]["task_name"], "Выкладка запаса кабеля")
        self.assertEqual(rows["rows"][0]["matched"], 1)
        self.assertEqual(rows["rows"][0]["report_id"], saved["id"])
        self.assertEqual(rows["reports"][0]["jobs"][0]["report_id"], saved["id"])

        empty = save_report(
            REPORT,
            calculation={
                "workers": [
                    {
                        "raw_worker_name": "Карандак В.Е.",
                        "members": ["Карандак В.Е."],
                        "jobs": [
                            {"raw_task_name": "Нет в прайсе", "matched": False, "volume": 1, "unit": "шт"}
                        ],
                    }
                ],
            },
        )
        self.assertEqual(empty["jobs_count"], 0)
        folders = query_db_rows()["reports"]
        folder = next(item for item in folders if item["id"] == empty["id"])
        self.assertEqual(folder["jobs"], [])
        self.assertIn("15.06.2026", folder["title"])
        self.assertEqual(folder["id"], empty["id"])

    def test_edit_report_and_job(self):
        site = create_site("Север")
        other = create_site("Юг")
        saved = save_report(
            REPORT,
            site_id=site["id"],
            calculation={
                "workers": [
                    {
                        "raw_worker_name": "Карандак В.Е.",
                        "members": ["Карандак В.Е."],
                        "total": 100,
                        "per_person": 100,
                        "jobs": [
                            {
                                "raw_task_name": "Выкладка",
                                "matched": True,
                                "matched_name": "Выкладка запаса кабеля",
                                "volume": 2,
                                "unit": "шт",
                                "unit_price": 50,
                                "amount": 100,
                            }
                        ],
                    }
                ]
            },
        )
        job_id = query_db_rows()["rows"][0]["job_id"]
        updated = update_report_job(
            job_id,
            worker_name="Моисеев А.Д.",
            task_name="Прокладка по стояку",
            volume=3,
            unit="м",
            unit_price=17,
        )
        self.assertEqual(updated["amount"], 51)
        self.assertEqual(updated["report_id"], saved["id"])
        folder = query_db_rows()["reports"][0]
        self.assertEqual(folder["jobs"][0]["worker_name"], "Моисеев А.Д.")
        self.assertEqual(folder["amount"], 51)
        self.assertIn("Моисеев", folder["title"])

        moved = update_report_header(
            saved["id"],
            report_date="2026-11-02",
            site_id=other["id"],
            site_set=True,
        )
        self.assertEqual(moved["report_date"], "2026-11-02")
        self.assertEqual(moved["site_name"], "Юг")
        self.assertIn("02.11.2026", moved["title"])
        cleared = update_report_header(saved["id"], site_id=None, site_set=True)
        self.assertIsNone(cleared["site_name"])

        removed_job = delete_report_job(job_id)
        self.assertEqual(removed_job["report_id"], saved["id"])
        left = query_db_rows()["reports"]
        folder_left = next(item for item in left if item["id"] == saved["id"])
        self.assertEqual(folder_left["jobs"], [])

        delete_report(saved["id"])
        self.assertFalse(any(item["id"] == saved["id"] for item in query_db_rows()["reports"]))
        with self.assertRaises(ValueError):
            delete_report(saved["id"])

    def test_load_reports_for_excel_requires_ids(self):
        saved = save_report(REPORT)
        loaded = load_reports_for_excel([saved["id"]])
        self.assertEqual(loaded[0]["report_date"], "2026-06-15")
        self.assertEqual(len(loaded[0]["workers"]), 2)
        with self.assertRaises(ValueError):
            load_reports_for_excel([])
        with self.assertRaises(ValueError):
            load_reports_for_excel([999999])


if __name__ == "__main__":
    unittest.main()
