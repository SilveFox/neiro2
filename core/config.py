# -*- coding: utf-8 -*-
"""Project paths and settings."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
SAMPLES_DIR = ROOT / "samples" / "reports"
REPORTS_JSON_DIR = ROOT / "reports_json"
DATA_DIR = ROOT / "data"
WEB_DIR = ROOT / "web"
STATIC_DIR = WEB_DIR / "static"

#SE_test_2026-07.xlsx
#SE_Lukhovitsy_iyun.xlsx
SOURCE_WORKBOOK = DOCS_DIR / "SE_Lukhovitsy_iyun.xlsx" # SE_test_2026-07.xlsx
WORKING_WORKBOOK = DATA_DIR / "workbook.xlsx"  # legacy fallback
WORKBOOKS_DIR = DATA_DIR / "workbooks"
ACTIVE_WORKBOOK_META = DATA_DIR / "active_workbook.json"
PRICE_CACHE = DATA_DIR / "price_list.json"
EMPLOYEES_CACHE = DATA_DIR / "employees.json"
JOB_ALIASES_CACHE = DATA_DIR / "job_aliases.json" # список наименования работы
WRITTEN_LOG = DATA_DIR / "written_reports.json"  # legacy; per-workbook preferred

SHEET_DATA = "Данные"
SHEET_CALC = "Расчет"
SHEET_TEMPLATE = "Шаблон"

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
# CPU-only сервер: 3b (~2 GB) — баланс скорость/качество JSON+русский.
# Слабый CPU: qwen2.5:1.5b. Есть GPU: можно вернуть qwen2.5:7b.
# Активная модель может быть переопределена в Настройках (data/model_settings.json).
MODEL_NAME = "qwen2.5:3b"
MODEL_SETTINGS_CACHE = DATA_DIR / "model_settings.json"
OLLAMA_TIMEOUT_SEC = 180
# False = compact prompt (~1/4); True = archived full prompt in prompt_full.py
USE_FULL_PROMPT = False

# Данные!B:C — VLOOKUP прайса (новое)
PRICE_NAME_COL = 2  # B
PRICE_VALUE_COL = 3  # C (новое)
PRICE_UNIT_COL = 5  # E
PRICE_START_ROW = 4

# Дневной лист / шаблон блока
DAY_DATE_CELL = (1, 2)  # B1
COL_NUM = 2  # B
COL_PEOPLE = 3  # C
COL_WORK = 4  # D
COL_QTY = 5  # E
COL_UNIT = 6  # F
COL_TARIFF = 7  # G
COL_WAGE = 8  # H
COL_PER_PERSON = 9  # I

# Правый блок "ФИО / Наработка"
COL_PEOPLE_SUM_NAME = 11  # колонка K
COL_PEOPLE_SUM_WAGE = 12  # колонка L
SUM_PEOPLE_START_ROW = 5
SUM_PEOPLE_END_ROW = 40
DAY_PEOPLE_SUM_RANGE = (SUM_PEOPLE_START_ROW, SUM_PEOPLE_END_ROW)

for d in (REPORTS_JSON_DIR, DATA_DIR, SAMPLES_DIR, STATIC_DIR, WORKBOOKS_DIR):
    d.mkdir(parents=True, exist_ok=True)
