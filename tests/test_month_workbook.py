# -*- coding: utf-8 -*-
"""Tests for empty month workbook creation."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import openpyxl

from core import config
from core.workbook_factory import (
    WorkbookExistsError,
    create_month_workbook,
    sanitize_workbook,
    written_log_for,
)


class MonthWorkbookTests(unittest.TestCase):
    def test_create_empty_month(self):
        self.assertTrue(config.SOURCE_WORKBOOK.exists())
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            old_dir = config.WORKBOOKS_DIR
            old_meta = config.ACTIVE_WORKBOOK_META
            config.WORKBOOKS_DIR = tmp_path / "workbooks"
            config.WORKBOOKS_DIR.mkdir()
            config.ACTIVE_WORKBOOK_META = tmp_path / "active_workbook.json"
            try:
                path = create_month_workbook(2026, 7, activate=True)
                self.assertTrue(path.exists())
                self.assertEqual(path.name, "SE_Lukhovitsy_2026-07.xlsx")
                self.assertTrue(written_log_for(path).exists())

                wb = openpyxl.load_workbook(path, data_only=False)
                try:
                    self.assertIn("Данные", wb.sheetnames)
                    self.assertIn("01", wb.sheetnames)
                    self.assertIn("Шаблон", wb.sheetnames)
                    ws01 = wb["01"]
                    self.assertEqual(ws01.cell(1, 2).value, "01.07.2026")
                    # Work tables cleared; employee list kept on the right
                    self.assertIsNone(ws01.cell(3, 4).value)  # D header gone
                    self.assertIsNone(ws01.cell(4, 4).value)
                    # No leftover borders from template tables
                    b = ws01.cell(4, 4).border

                    def _no_side(side):
                        return side is None or side.style is None or side.style == "none"

                    self.assertTrue(
                        _no_side(b.left)
                        and _no_side(b.right)
                        and _no_side(b.top)
                        and _no_side(b.bottom)
                    )
                    self.assertEqual(ws01.cell(1, 11).value, "ФИО")
                    self.assertIsNotNone(ws01.cell(3, 11).value)
                    qty_values = [
                        ws01.cell(r, config.COL_QTY).value
                        for r in range(1, min(200, (ws01.max_row or 1) + 1))
                    ]
                    numeric_qty = [v for v in qty_values if isinstance(v, (int, float))]
                    self.assertEqual(numeric_qty, [])

                    calc_ws = wb["Расчет"]
                    self.assertEqual(calc_ws.cell(2, 6).value.date(), date(2026, 7, 1))
                    self.assertEqual(calc_ws.cell(2, 36).value.date(), date(2026, 7, 31))
                finally:
                    wb.close()

                with self.assertRaises(WorkbookExistsError):
                    create_month_workbook(2026, 7, activate=False)

                meta = json.loads(config.ACTIVE_WORKBOOK_META.read_text(encoding="utf-8"))
                self.assertEqual(meta["year_month"], "2026-07")
                self.assertTrue(Path(meta["path"]).exists())

                # Template external links must be stripped (they break Excel after rewrite)
                wb2 = openpyxl.load_workbook(path)
                try:
                    self.assertFalse(getattr(wb2, "_external_links", None))
                    for dn in wb2.defined_names.values():
                        text = getattr(dn, "attr_text", "") or ""
                        self.assertNotRegex(text, r"\[\d+\]")
                finally:
                    wb2.close()
            finally:
                config.WORKBOOKS_DIR = old_dir
                config.ACTIVE_WORKBOOK_META = old_meta

    def test_sanitize_drops_external_names(self):
        self.assertTrue(config.SOURCE_WORKBOOK.exists())
        wb = openpyxl.load_workbook(config.SOURCE_WORKBOOK)
        try:
            before = list(getattr(wb, "_external_links", []) or [])
            self.assertTrue(before)  # template has external links
            sanitize_workbook(wb)
            self.assertEqual(list(getattr(wb, "_external_links", []) or []), [])
            for dn in wb.defined_names.values():
                text = getattr(dn, "attr_text", "") or ""
                self.assertNotRegex(text, r"\[\d+\]")
        finally:
            wb.close()


if __name__ == "__main__":
    unittest.main()
