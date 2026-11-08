# -*- coding: utf-8 -*-
"""SQLite reports browser: sites and filters."""
from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core import config
from core.report_db import create_site, init_db, list_sites, query_db_rows, save_report


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


if __name__ == "__main__":
    unittest.main()
