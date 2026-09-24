# -*- coding: utf-8 -*-
"""System prompt for multi-worker / brigade report parsing (compact ~4x shorter)."""
from __future__ import annotations

import json
from pathlib import Path

from core import config


def _load_names(path: Path, limit: int | None = None) -> list[str]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    names = [x["name"] if isinstance(x, dict) else x for x in data]
    return names[:limit] if limit else names


def build_system_prompt() -> str:
    """
    Compact system prompt (~1/4 of the archived full version).

    Full original: core/prompt_full.py → build_system_prompt_full().
    Switch via config.USE_FULL_PROMPT = True if needed.
    """
    if getattr(config, "USE_FULL_PROMPT", False):
        from core.prompt_full import build_system_prompt_full

        return build_system_prompt_full()

    employees = _load_names(config.EMPLOYEES_CACHE)
    emps = "; ".join(employees)

    return f"""Разбор сменных отчётов монтажников → ОДИН JSON-объект, без Markdown и текста вокруг.
Схема: {{"report_date":null|"YYYY-MM-DD","workers":[{{"raw_worker_name":"…","members":["ФИО"],"performed_jobs":[{{"raw_task_name":"…","job_description":"…","service_type":"Интернет"|"ТВ"|"Комбо"|"Общее","volume":число,"unit":"шт"|"м"|"км"|"ч"}}]}}]}}
У каждой работы ОБЯЗАТЕЛЬНЫ все 5 полей. job_description = raw_task_name, если нет уточнения. volume — только число, unit — отдельно.

Бригада: 2+ фамилии подряд (запятая/«и»/пробел) = один worker, members из списка, performed_jobs один раз. Отдельные workers только при «Иванов: …».

Работы: volume/unit НЕ писать в названия. Число в начале или в конце с ед.изм. = volume: «4 разделки…»→4 шт; «…30 м»→30 м; «19 сварок 1-7»→19 шт (хвост «1-7» в имени); «1 муфта монтаж»→1 шт. Несколько работ в строке → отдельные performed_jobs. Пропускай адреса («СНТ…», «…49 бр») и заголовки «1 заявка по…» / «Ремонт» без числа работ — не включать в performed_jobs. Раздел «Заявки по тв/интернету» → service_type; иначе «Общее».

Сотрудники: {emps}
"""


SYSTEM_PROMPT = build_system_prompt()
