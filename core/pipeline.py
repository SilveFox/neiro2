# -*- coding: utf-8 -*-
"""End-to-end orchestration: text → JSON → price calc → Excel append."""
from __future__ import annotations

from typing import Any

from core.excel_writer import append_calc_to_workbook, ensure_working_workbook
from core.parser import parse_report_text, validate_report
from core.pricing import CalcResult, PriceList, calculate_report


def parse_only(
    report_text: str,
    extra_prompt: str = "",
    report_date: str | None = None,
) -> dict[str, Any]:
    report = parse_report_text(report_text, extra_prompt=extra_prompt, report_date=report_date)
    return {"report": report}


def calculate_only(report: dict[str, Any]) -> dict[str, Any]:
    validated = validate_report(report)
    # keep hash/date from input if present
    if report.get("source_text_hash"):
        validated["source_text_hash"] = report["source_text_hash"]
    if report.get("report_date"):
        validated["report_date"] = report["report_date"]
    calc = calculate_report(validated)
    return calc.to_dict()


def write_excel(calc_dict: dict[str, Any] | CalcResult, skip_duplicates: bool = True) -> dict[str, Any]:
    ensure_working_workbook()
    if isinstance(calc_dict, CalcResult):
        calc = calc_dict
    else:
        # rebuild CalcResult via calculate_report from a minimal report-like structure
        report = {
            "report_date": calc_dict.get("report_date"),
            "source_text_hash": calc_dict.get("source_text_hash"),
            "workers": [
                {
                    "raw_worker_name": w["raw_worker_name"],
                    "members": w.get("members")
                    or [w["raw_worker_name"]],
                    "performed_jobs": [
                        {
                            "raw_task_name": j.get("raw_task_name") or "",
                            "job_description": j.get("matched_name") or j.get("job_description") or "",
                            "service_type": j.get("service_type") or "Общее",
                            "volume": j.get("volume") or 0,
                            "unit": j.get("unit") or "",
                        }
                        for j in w.get("jobs") or []
                    ],
                }
                for w in calc_dict.get("workers") or []
            ],
        }
        calc = calculate_report(report)
        calc.report_date = calc_dict.get("report_date") or calc.report_date
        calc.source_text_hash = calc_dict.get("source_text_hash") or calc.source_text_hash
    return append_calc_to_workbook(calc, skip_duplicates=skip_duplicates)


def run_pipeline(
    report_text: str,
    extra_prompt: str = "",
    report_date: str | None = None,
    write_to_excel: bool = True,
    skip_duplicates: bool = True,
) -> dict[str, Any]:
    parsed = parse_only(report_text, extra_prompt=extra_prompt, report_date=report_date)
    report = parsed["report"]
    calc = calculate_report(report)
    result: dict[str, Any] = {
        "report": report,
        "calculation": calc.to_dict(),
        "excel": None,
    }
    if write_to_excel:
        result["excel"] = append_calc_to_workbook(calc, skip_duplicates=skip_duplicates)
    return result


def price_catalog() -> list[dict[str, Any]]:
    return [
        {"name": i.name, "price": i.price, "unit": i.unit}
        for i in PriceList.from_cache().items
    ]
