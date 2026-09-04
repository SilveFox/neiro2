# -*- coding: utf-8 -*-
"""FastAPI web shell for report → JSON → calc → Excel pipeline."""
from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core import config
from core.excel_writer import append_calc_to_workbook, ensure_working_workbook, get_written_log
from core.parser import ParseError, parse_report_text, validate_report
from core.pricing import (
    PriceList,
    calculate_report,
    load_aliases_document,
    save_aliases_document,
    save_price_items,
)
from core.workbook_factory import (
    WorkbookExistsError,
    activate_year_month,
    create_month_workbook,
    get_active_meta,
    list_month_workbooks,
    set_active_workbook,
    year_month_from_path,
)

app = FastAPI(title="МонтажПро", version="1.0.0")

STATIC = config.STATIC_DIR
STATIC.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


class ParseRequest(BaseModel):
    report_text: str = Field(..., min_length=1)
    extra_prompt: str = ""
    report_date: str | None = None


class ExcelRequest(BaseModel):
    report: dict[str, Any]
    skip_duplicates: bool = True
    report_date: str | None = None


class NewMonthRequest(BaseModel):
    year: int
    month: int
    activate: bool = True


class ActivateRequest(BaseModel):
    year_month: str | None = None
    path: str | None = None


class PriceSaveRequest(BaseModel):
    items: list[dict[str, Any]]


class AliasesSaveRequest(BaseModel):
    aliases: list[dict[str, Any]]
    readme: list[str] | None = None


class EmployeesSaveRequest(BaseModel):
    employees: list[str]


def _extract_upload_text(filename: str, data: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith((".txt", ".csv", ".md", ".log")):
        for enc in ("utf-8", "cp1251", "latin-1"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    if name.endswith(".xlsx"):
        import io

        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
        lines: list[str] = []
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
                if cells:
                    lines.append(" ".join(cells))
        wb.close()
        return "\n".join(lines)

    if name.endswith(".docx"):
        import io
        import zipfile
        from xml.etree import ElementTree as ET

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("word/document.xml")
        root = ET.fromstring(xml)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        texts = [t.text for t in root.findall(".//w:t", ns) if t.text]
        return "".join(texts)

    raise HTTPException(
        422,
        "Поддерживаются .txt, .csv, .docx, .xlsx. Для .doc вставьте текст вручную.",
    )


@app.get("/")
def index():
    index_path = STATIC / "index.html"
    if not index_path.exists():
        raise HTTPException(500, "Нет static/index.html")
    return FileResponse(index_path)


@app.get("/api/health")
def health():
    active = get_active_meta()
    price_count = 0
    if config.PRICE_CACHE.exists():
        try:
            price_count = len(json.loads(config.PRICE_CACHE.read_text(encoding="utf-8")))
        except Exception:
            price_count = 0
    return {
        "ok": True,
        "workbook": str(ensure_working_workbook()),
        "active": active,
        "model": config.MODEL_NAME,
        "price_items": price_count,
    }


@app.get("/api/workbook/list")
def api_workbook_list():
    ensure_working_workbook()
    return {
        "ok": True,
        "active": get_active_meta(),
        "items": list_month_workbooks(),
    }


@app.post("/api/workbook/new")
def api_workbook_new(body: NewMonthRequest):
    try:
        path = create_month_workbook(body.year, body.month, activate=body.activate)
        return {
            "ok": True,
            "path": str(path),
            "year_month": f"{body.year:04d}-{body.month:02d}",
            "active": get_active_meta(),
            "message": f"Создан пустой месяц {body.year:04d}-{body.month:02d}",
        }
    except WorkbookExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/workbook/activate")
def api_workbook_activate(body: ActivateRequest):
    try:
        if body.year_month:
            meta = activate_year_month(body.year_month)
        elif body.path:
            path = Path(body.path)
            if not path.is_absolute():
                path = (config.ROOT / path).resolve()
            meta = set_active_workbook(path, year_month_from_path(path))
        else:
            raise HTTPException(400, "Укажите year_month или path")
        return {"ok": True, "active": meta}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/parse")
def api_parse(body: ParseRequest):
    try:
        report = parse_report_text(
            body.report_text,
            extra_prompt=body.extra_prompt,
            report_date=body.report_date,
        )
        calc = calculate_report(report)
        return {
            "ok": True,
            "report": report,
            "calculation": calc.to_dict(),
        }
    except ParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{exc}\n{traceback.format_exc()}") from exc


@app.post("/api/parse-file")
async def api_parse_file(
    file: UploadFile = File(...),
    report_date: str | None = None,
    extra_prompt: str = "",
):
    data = await file.read()
    if not data:
        raise HTTPException(422, "Пустой файл")
    text = _extract_upload_text(file.filename or "report.txt", data).strip()
    if not text:
        raise HTTPException(422, "Не удалось извлечь текст из файла")
    try:
        report = parse_report_text(
            text,
            extra_prompt=extra_prompt or "",
            report_date=report_date or None,
        )
        calc = calculate_report(report)
        return {
            "ok": True,
            "report": report,
            "calculation": calc.to_dict(),
            "extracted_text": text,
        }
    except ParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{exc}\n{traceback.format_exc()}") from exc


@app.post("/api/calculate")
def api_calculate(body: ExcelRequest):
    try:
        report = validate_report(body.report)
        if body.report.get("source_text_hash"):
            report["source_text_hash"] = body.report["source_text_hash"]
        if body.report_date:
            report["report_date"] = body.report_date
        elif body.report.get("report_date"):
            report["report_date"] = body.report["report_date"]
        calc = calculate_report(report)
        return {"ok": True, "calculation": calc.to_dict()}
    except ParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/excel")
def api_excel(body: ExcelRequest):
    try:
        report = validate_report(body.report)
        if body.report.get("source_text_hash"):
            report["source_text_hash"] = body.report["source_text_hash"]
        if body.report_date:
            report["report_date"] = body.report_date
        elif body.report.get("report_date"):
            report["report_date"] = body.report["report_date"]
        calc = calculate_report(report)
        result = append_calc_to_workbook(calc, skip_duplicates=body.skip_duplicates)
        return {"ok": result.get("ok", False), **result, "calculation": calc.to_dict()}
    except ParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/download-excel")
def download_excel():
    path = ensure_working_workbook()
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/api/price")
def api_price_get():
    try:
        pl = PriceList.from_cache()
        return {"ok": True, "items": pl.to_cache_list()}
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@app.put("/api/price")
def api_price_put(body: PriceSaveRequest):
    try:
        items = save_price_items(body.items)
        return {"ok": True, "items": items, "count": len(items)}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@app.get("/api/aliases")
def api_aliases_get():
    try:
        doc = load_aliases_document()
        return {"ok": True, **doc}
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@app.put("/api/aliases")
def api_aliases_put(body: AliasesSaveRequest):
    try:
        payload: dict[str, Any] = {"aliases": body.aliases}
        existing = load_aliases_document()
        if "_readme" in existing and body.readme is None:
            payload["_readme"] = existing["_readme"]
        if body.readme is not None:
            payload["_readme"] = body.readme
        saved = save_aliases_document(payload)
        return {"ok": True, **saved}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@app.get("/api/employees")
def api_employees_get():
    path = config.EMPLOYEES_CACHE
    if not path.exists():
        return {"ok": True, "employees": []}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        employees = [str(x) for x in raw]
    elif isinstance(raw, dict) and isinstance(raw.get("employees"), list):
        employees = [str(x) for x in raw["employees"]]
    else:
        employees = []
    return {"ok": True, "employees": employees}


@app.put("/api/employees")
def api_employees_put(body: EmployeesSaveRequest):
    employees = [str(x).strip() for x in body.employees if str(x).strip()]
    config.EMPLOYEES_CACHE.write_text(
        json.dumps(employees, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"ok": True, "employees": employees, "count": len(employees)}


@app.get("/api/excel-log")
def api_excel_log():
    try:
        ensure_working_workbook()
        return {"ok": True, **get_written_log()}
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


def main():
    import uvicorn

    uvicorn.run("web.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
