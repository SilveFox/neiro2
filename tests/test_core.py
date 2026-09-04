# -*- coding: utf-8 -*-
"""Unit tests for validation, pricing, excel append (no Ollama required)."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from core import config
from core.excel_writer import append_calc_to_workbook
from core.parser import (
    ParseError,
    clean_json_text,
    detect_brigade_from_text,
    normalize_brigade_workers,
    preprocess_report_text,
    resolve_employee_name,
    strip_volume_from_task_fields,
    validate_report,
)
from core.pricing import PriceList, calculate_report, normalize_text


SAMPLE_REPORT = {
    "report_date": "2026-06-15",
    "source_text_hash": "testhash001",
    "workers": [
        {
            "raw_worker_name": "Карандак В.Е.",
            "performed_jobs": [
                {
                    "raw_task_name": "Заявки по неисправности интернета",
                    "job_description": "Заявки по неисправности Интернета",
                    "service_type": "Интернет",
                    "volume": 7,
                    "unit": "шт",
                },
                {
                    "raw_task_name": "обжим рж45",
                    "job_description": "Обжим коннектора RJ-45, BNC",
                    "service_type": "Интернет",
                    "volume": 2,
                    "unit": "шт",
                },
            ],
        },
        {
            "raw_worker_name": "Лошкомойников С.И.",
            "performed_jobs": [
                {
                    "raw_task_name": "Выкладка запаса",
                    "job_description": "Выкладка запаса кабеля",
                    "service_type": "Общее",
                    "volume": 1,
                    "unit": "шт",
                }
            ],
        },
    ],
}


class ParserTests(unittest.TestCase):
    def test_validate_workers(self):
        out = validate_report(SAMPLE_REPORT)
        self.assertEqual(len(out["workers"]), 2)
        self.assertEqual(out["workers"][0]["raw_worker_name"], "Карандак В.Е.")

    def test_legacy_schema(self):
        legacy = {
            "raw_worker_name": "Тибуков С.А.",
            "performed_jobs": [
                {
                    "raw_task_name": "Обмер",
                    "job_description": "Обмер",
                    "service_type": "Общее",
                    "volume": 1,
                    "unit": "шт",
                }
            ],
        }
        out = validate_report(legacy)
        self.assertEqual(len(out["workers"]), 1)

    def test_reject_empty_workers(self):
        with self.assertRaises(ParseError):
            validate_report({"workers": []})

    def test_strip_volume_from_name(self):
        raw, desc, vol, unit = strip_volume_from_task_fields(
            "Заявки по тв: отключение—19 шт",
            "Заявки по тв: отключение-19 шт",
            19,
            "шт",
        )
        self.assertEqual(raw, "Заявки по тв: отключение")
        self.assertEqual(desc, "Заявки по тв: отключение")
        self.assertEqual(vol, 19)
        self.assertEqual(unit, "шт")

    def test_strip_volume_recovers_qty(self):
        raw, _, vol, _ = strip_volume_from_task_fields(
            "настройка ЦТВ-1 шт",
            "настройка ЦТВ-1 шт",
            1,
            "шт",
        )
        self.assertEqual(raw, "настройка ЦТВ")
        self.assertEqual(vol, 1)

    def test_strip_keeps_fiber_range_in_name(self):
        """«сварок 1-7» must not treat «-7» as volume."""
        raw, desc, vol, unit = strip_volume_from_task_fields(
            "сварок 1-7",
            "сварок 1-7",
            19,
            "шт",
        )
        self.assertEqual(raw, "сварок 1-7")
        self.assertEqual(desc, "сварок 1-7")
        self.assertEqual(vol, 19)
        self.assertEqual(unit, "шт")

        from core.pricing import PriceList, calculate_report

        report = {
            "report_date": "2026-07-30",
            "workers": [
                {
                    "raw_worker_name": "Слободянюк А.М.",
                    "members": ["Слободянюк А.М."],
                    "performed_jobs": [
                        {
                            "raw_task_name": "сварок 1-7",
                            "job_description": "сварок 1-7",
                            "service_type": "Интернет",
                            "volume": 19,
                            "unit": "шт",
                        }
                    ],
                }
            ],
        }
        calc = calculate_report(report, PriceList.from_cache())
        job = calc.workers[0].jobs[0]
        self.assertTrue(job.matched)
        self.assertEqual(job.matched_name, "Сварка 1-7 волокон в муфте, кроссе")
        self.assertEqual(job.volume, 19)

    def test_analyze_qty_prefix_and_suffix(self):
        from core.parser import analyze_line_quantity, preprocess_report_text, reconcile_volumes_from_source

        p = analyze_line_quantity("3 выкладки запаса кабеля")
        self.assertEqual(p.position, "prefix")
        self.assertEqual(p.volume, 3)
        self.assertEqual(p.unit, "шт")
        self.assertIn("выкладки", p.task_name.lower())

        p = analyze_line_quantity("19 сварок 1-7")
        self.assertEqual(p.volume, 19)
        self.assertIn("1-7", p.task_name)

        p = analyze_line_quantity("Перекидка кабеля между зданиями 30 м")
        self.assertEqual(p.position, "suffix")
        self.assertEqual(p.volume, 30)
        self.assertEqual(p.unit, "м")

        p = analyze_line_quantity("1 сверление в бетоне до 24/500 мм")
        self.assertEqual(p.volume, 1)
        self.assertIn("24/500", p.task_name)

        p = analyze_line_quantity("1 заявка по неисправности интернета")
        self.assertEqual(p.position, "none")

        p = analyze_line_quantity("Калинина 49 бр")
        self.assertEqual(p.position, "none")

        prepared = preprocess_report_text("3 выкладки запаса кабеля\nПерекидка кабеля 30 м")
        self.assertIn("— 3 шт", prepared)
        self.assertIn("— 30 м", prepared)

        report = {
            "workers": [
                {
                    "raw_worker_name": "Слободянюк",
                    "members": ["Слободянюк"],
                    "performed_jobs": [
                        {
                            "raw_task_name": "выкладки запаса кабеля",
                            "job_description": "выкладки запаса кабеля",
                            "service_type": "Интернет",
                            "volume": 1,
                            "unit": "шт",
                        }
                    ],
                }
            ]
        }
        fixed = reconcile_volumes_from_source(report, "3 выкладки запаса кабеля")
        self.assertEqual(fixed["workers"][0]["performed_jobs"][0]["volume"], 3)

    def test_validate_strips_volume_in_names(self):
        report = {
            "workers": [
                {
                    "raw_worker_name": "Пищулин С.В.",
                    "performed_jobs": [
                        {
                            "raw_task_name": "отключение-19 шт",
                            "job_description": "отключение-19 шт",
                            "service_type": "ТВ",
                            "volume": 19,
                            "unit": "шт",
                        }
                    ],
                }
            ]
        }
        out = validate_report(report)
        job = out["workers"][0]["performed_jobs"][0]
        self.assertEqual(job["raw_task_name"], "отключение")
        self.assertEqual(job["volume"], 19)

    def test_preprocess_brigade_and_glued_units(self):
        text = (
            "Карелин Пищулин заявки по тв: отключение—19 шт."
            "настройка спутниковой антенны—1 шт.настройка ЦТВ—1 шт."
        )
        out = preprocess_report_text(text)
        self.assertIn("Карелин,", out)
        self.assertIn("Пищулин", out)
        # glued «шт.настройка» splits onto a new line / separate job hint
        self.assertTrue("шт" in out.lower())
        self.assertIn("настройка", out.lower())

    def test_detect_and_expand_brigade(self):
        text = "Карелин Пищулин заявки по тв: отключение—19 шт"
        self.assertEqual(
            detect_brigade_from_text(text),
            ["Карелин А.С.", "Пищулин С.В."],
        )
        report = {
            "workers": [
                {
                    "raw_worker_name": "Пищулин С.В.",
                    "performed_jobs": [
                        {
                            "raw_task_name": "отключение",
                            "job_description": "отключение",
                            "service_type": "ТВ",
                            "volume": 19,
                            "unit": "шт",
                        }
                    ],
                }
            ]
        }
        merged = normalize_brigade_workers(report, text)
        self.assertEqual(len(merged["workers"]), 1)
        self.assertEqual(
            merged["workers"][0]["members"],
            ["Пищулин С.В.", "Карелин А.С."],
        )
        self.assertEqual(merged["workers"][0]["performed_jobs"][0]["volume"], 19)

    def test_merge_identical_workers_into_brigade(self):
        jobs = [
            {
                "raw_task_name": "Настройка ТВ",
                "job_description": "Настройка ТВ",
                "service_type": "ТВ",
                "volume": 2,
                "unit": "шт",
            }
        ]
        report = {
            "workers": [
                {"raw_worker_name": "Жмыхов С.П.", "performed_jobs": jobs},
                {"raw_worker_name": "Вакульский М.", "performed_jobs": jobs},
            ]
        }
        out = validate_report(normalize_brigade_workers(report, "Жмыхов Вакульский"))
        self.assertEqual(len(out["workers"]), 1)
        self.assertEqual(out["workers"][0]["members"], ["Жмыхов С.П.", "Вакульский М."])
        calc = calculate_report(out)
        self.assertEqual(calc.workers[0].headcount, 2)
        self.assertEqual(calc.workers[0].per_person, round(calc.workers[0].total / 2, 2))

    def test_resolve_surname_to_initials(self):
        self.assertEqual(resolve_employee_name("Карандак"), "Карандак В.Е.")
        self.assertEqual(resolve_employee_name("Лошкомойников"), "Лошкомойников С.И.")
        self.assertEqual(resolve_employee_name("Карандак В.Е."), "Карандак В.Е.")
        # Ambiguous surname without initials — leave as is
        self.assertEqual(resolve_employee_name("Бирюков"), "Бирюков")
        self.assertEqual(resolve_employee_name("Бирюков А.И."), "Бирюков А.И.")

    def test_validate_expands_surnames(self):
        report = {
            "workers": [
                {
                    "raw_worker_name": "Карандак",
                    "members": ["Карандак", "Лошкомойников"],
                    "performed_jobs": [
                        {
                            "raw_task_name": "Обмер",
                            "job_description": "Обмер",
                            "service_type": "Общее",
                            "volume": 1,
                            "unit": "шт",
                        }
                    ],
                }
            ]
        }
        out = validate_report(report)
        self.assertEqual(
            out["workers"][0]["members"],
            ["Карандак В.Е.", "Лошкомойников С.И."],
        )
        self.assertEqual(
            out["workers"][0]["raw_worker_name"],
            "Карандак В.Е., Лошкомойников С.И.",
        )

    def test_clean_json_fence(self):
        raw = '```json\n{"workers":[]}\n```'
        self.assertTrue(clean_json_text(raw).startswith("{"))


class PricingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pl = PriceList.from_cache()

    def test_exact_match(self):
        item, score = self.pl.match("Обжим коннектора RJ-45, BNC")
        self.assertIsNotNone(item)
        self.assertEqual(score, 1.0)

    def test_alias_match(self):
        item, score = self.pl.match("обжим рж45")
        self.assertIsNotNone(item)
        self.assertIn("RJ-45", item.name)

    def test_alias_match_ignores_job_service_type(self):
        """Price «Общее» must match jobs tagged Интернет/ТВ (e.g. сварок 1-7)."""
        for st in ("Общее", "Интернет", "ТВ", "Комбо"):
            item, score = self.pl.match("сварок 1-7", "сварок 1-7", service_type=st)
            self.assertIsNotNone(item, msg=st)
            self.assertEqual(item.name, "Сварка 1-7 волокон в муфте, кроссе")
            self.assertEqual(score, 1.0)

    def test_calculate_totals(self):
        calc = calculate_report(SAMPLE_REPORT, self.pl)
        self.assertEqual(calc.unmatched_count, 0)
        self.assertEqual(len(calc.workers), 2)
        self.assertGreater(calc.grand_total, 0)
        # 7 * price(internet tickets) + 2 * price(rj45) + 1 * price(reserve)
        self.assertGreater(calc.workers[0].total, 0)

    def test_unmatched_job(self):
        report = {
            "report_date": "2026-06-15",
            "workers": [
                {
                    "raw_worker_name": "Тестов Т.Т.",
                    "performed_jobs": [
                        {
                            "raw_task_name": "Полёт на Марс",
                            "job_description": "Полёт на Марс",
                            "service_type": "Общее",
                            "volume": 1,
                            "unit": "шт",
                        }
                    ],
                }
            ],
        }
        calc = calculate_report(report, self.pl)
        self.assertEqual(calc.unmatched_count, 1)
        self.assertEqual(calc.grand_total, 0)

    def test_normalize(self):
        self.assertEqual(normalize_text("  Ёлка  "), "елка")


class ExcelTests(unittest.TestCase):
    def test_append_and_dedup(self):
        src = config.SOURCE_WORKBOOK
        self.assertTrue(src.exists())
        with tempfile.TemporaryDirectory() as tmp:
            wb_path = Path(tmp) / "test.xlsx"
            shutil.copy2(src, wb_path)
            from core.workbook_factory import written_log_for

            written_log_for(wb_path).write_text('{"entries":[]}', encoding="utf-8")
            calc = calculate_report(SAMPLE_REPORT)
            r1 = append_calc_to_workbook(calc, workbook_path=wb_path, skip_duplicates=True)
            self.assertTrue(r1["ok"])
            self.assertEqual(r1["day_sheet"], "15")
            r2 = append_calc_to_workbook(calc, workbook_path=wb_path, skip_duplicates=True)
            self.assertTrue(r2.get("duplicate"))


if __name__ == "__main__":
    unittest.main()
