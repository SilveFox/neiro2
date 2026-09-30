# -*- coding: utf-8 -*-
"""Parse free-text reports via Ollama into workers[] JSON."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests

from core import config
from core.prompt import build_system_prompt

REQUIRED_JOB_KEYS = {"raw_task_name", "job_description", "service_type", "volume", "unit"}

# Units used as work volume (NOT «мм», «кг» — those are specs inside the name)
_UNIT_TOKEN = r"(?:шт\.?|компл\.?|уп\.?|км|м(?![мa-zа-яё])|час(?:а|ов)?|ч(?![а-яa-zё]))"
_NUM = r"(\d+(?:[.,]\d+)?)"

# «работа — 19 шт» / «работа-19шт.»  (НЕ диапазоны вроде «1-7», «8-15»)
_VOLUME_IN_NAME_RE = re.compile(
    rf"(?<!\d)[\s]*[-–—:]\s*{_NUM}\s*({_UNIT_TOKEN})?\s*\.?$",
    flags=re.IGNORECASE,
)
# «работа 30 м» / «работа (2 шт)»
_VOLUME_TRAILING_RE = re.compile(
    rf"[\s(]+{_NUM}\s*({_UNIT_TOKEN})\s*\)?\s*\.?$",
    flags=re.IGNORECASE,
)
# «15 м жгутование…»
_VOLUME_LEADING_UNIT_RE = re.compile(
    rf"^\s*{_NUM}\s*({_UNIT_TOKEN})\b\s+(.+)$",
    flags=re.IGNORECASE,
)
# «3 выкладки…», «19 сварок 1-7»
_VOLUME_LEADING_COUNT_RE = re.compile(
    rf"^\s*(\d+)\s+([A-Za-zА-Яа-яЁё].+)$",
    flags=re.IGNORECASE,
)

# Non-job lines: request headers, addresses, apartment markers
_SKIP_QTY_LINE_RE = re.compile(
    r"(?:"
    r"^\d+\s+заявк"
    r"|^\s*заявк"
    r"|\bснт\b"
    r"|\bул\.?\b"
    r"|\bд\.?\s*\d"
    r"|\d+\s*бр\.?\s*$"
    r"|^\s*ремонт\s*$"
    r"|^\s*подключен\w*\s+чс\s*$"
    r")",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class QtyParseResult:
    """Where the quantity sits relative to the work name."""

    position: str  # "prefix" | "suffix" | "none"
    volume: float | int | None
    unit: str | None
    task_name: str
    original: str
    skipped_reason: str | None = None


def _to_number(num_s: str) -> float | int:
    s = (num_s or "").replace(",", ".").strip()
    return float(s) if "." in s else int(s)


def _norm_unit(unit: str | None) -> str | None:
    if not unit:
        return None
    u = unit.rstrip(".").lower().replace("ё", "е")
    if u.startswith("час") or u == "ч":
        return "ч"
    if u.startswith("компл"):
        return "компл"
    if u.startswith("уп"):
        return "уп"
    if u.startswith("шт"):
        return "шт"
    if u == "км":
        return "км"
    if u == "м":
        return "м"
    return u


def _is_skip_qty_line(text: str) -> str | None:
    t = (text or "").strip()
    if not t:
        return "empty"
    if _SKIP_QTY_LINE_RE.search(t):
        return "header_or_address"
    # Pure people header: only known surnames / commas / «и»
    surnames = {s for s, _ in _employee_surnames()}
    if surnames:
        tokens = re.findall(r"[A-Za-zА-Яа-яЁё]+", t.lower().replace("ё", "е"))
        if tokens and all(tok in surnames or tok == "и" for tok in tokens):
            return "brigade_header"
    return None


def analyze_line_quantity(line: str) -> QtyParseResult:
    """
    Detect whether volume stands before or after the work name.

    Patterns:
      prefix + unit:  «15 м жгутование запаса кабеля»
      prefix count:   «3 выкладки запаса кабеля», «19 сварок 1-7»
      suffix + unit:  «Перекидка кабеля между зданиями 30 м»
      suffix dash:    «отключение—19 шт»

    Specs inside the name stay in task_name (1-7, 24/500 мм, 0.3 кг).
    """
    original = (line or "").strip()
    skip = _is_skip_qty_line(original)
    if skip:
        return QtyParseResult("none", None, None, original, original, skipped_reason=skip)

    text = original

    m = _VOLUME_LEADING_UNIT_RE.match(text)
    if m:
        return QtyParseResult(
            position="prefix",
            volume=_to_number(m.group(1)),
            unit=_norm_unit(m.group(2)),
            task_name=m.group(3).strip(" -–—:"),
            original=original,
        )

    m = _VOLUME_LEADING_COUNT_RE.match(text)
    if m:
        # Reject date-like «1.07.26 …» (leading pattern only allows integer,
        # but still skip if rest starts with a dotted date fragment already consumed)
        rest = m.group(2).strip()
        # «1 заявка…» already skipped; avoid address «49 бр» style without letters enough
        if re.match(r"^\d+[./]", original):
            return QtyParseResult("none", None, None, original, original, skipped_reason="date_like")
        return QtyParseResult(
            position="prefix",
            volume=_to_number(m.group(1)),
            unit="шт",
            task_name=rest,
            original=original,
        )

    for pattern in (_VOLUME_IN_NAME_RE, _VOLUME_TRAILING_RE):
        m = pattern.search(text)
        if not m:
            continue
        name = text[: m.start()].rstrip(" -–—:(").strip()
        if not name:
            continue
        unit = _norm_unit(m.group(2) if m.lastindex and m.lastindex >= 2 else None)
        return QtyParseResult(
            position="suffix",
            volume=_to_number(m.group(1)),
            unit=unit or "шт",
            task_name=name,
            original=original,
        )

    return QtyParseResult("none", None, None, original, original)


def format_qty_canonical(parsed: QtyParseResult) -> str:
    """Rewrite line as «название — N ед» so the model always sees qty after the name."""
    if parsed.position == "none" or parsed.volume is None:
        return parsed.original
    unit = parsed.unit or "шт"
    return f"{parsed.task_name} — {parsed.volume} {unit}"


def collect_qty_hints(source_text: str) -> list[QtyParseResult]:
    hints: list[QtyParseResult] = []
    for line in (source_text or "").splitlines():
        parsed = analyze_line_quantity(line)
        if parsed.position != "none" and parsed.volume is not None and parsed.task_name:
            hints.append(parsed)
    return hints


def _name_similarity(a: str, b: str) -> float:
    def norm(value: str) -> str:
        text = (value or "").lower().replace("ё", "е")
        text = re.sub(r"[«»\"']", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
        return 0.8 + 0.2 * (len(shorter) / max(len(longer), 1))
    ta = set(re.findall(r"[a-zа-я0-9]{3,}", na, flags=re.IGNORECASE))
    tb = set(re.findall(r"[a-zа-я0-9]{3,}", nb, flags=re.IGNORECASE))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def reconcile_volumes_from_source(
    report: dict[str, Any],
    source_text: str,
) -> dict[str, Any]:
    """
    After the model returns JSON, re-check volumes against source lines.

    Uses qty-position analysis of the original report; strong name matches
    overwrite volume/unit (and clean the task name).
    """
    hints = collect_qty_hints(source_text)
    if not hints:
        return report

    used: set[int] = set()
    for worker in report.get("workers") or []:
        jobs = worker.get("performed_jobs") or []
        for job in jobs:
            if not isinstance(job, dict):
                continue
            raw = str(job.get("raw_task_name") or "")
            desc = str(job.get("job_description") or "")
            best_i = -1
            best_score = 0.0
            for i, hint in enumerate(hints):
                if i in used:
                    continue
                score = max(
                    _name_similarity(raw, hint.task_name),
                    _name_similarity(desc, hint.task_name),
                    _name_similarity(raw, hint.original),
                )
                if score > best_score:
                    best_score = score
                    best_i = i
            if best_i < 0 or best_score < 0.55:
                continue
            hint = hints[best_i]
            used.add(best_i)
            job["volume"] = hint.volume
            if hint.unit:
                job["unit"] = hint.unit
            # Prefer cleaned name without embedded qty
            if hint.task_name:
                job["raw_task_name"] = hint.task_name
                job["job_description"] = hint.task_name
    return report


class ParseError(Exception):
    """Raised when the model response cannot be turned into a valid report."""


def source_text_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]


def _employee_surnames() -> list[tuple[str, str]]:
    """Return [(surname_lower, full_name), ...] longest surnames first."""
    if not config.EMPLOYEES_CACHE.exists():
        return []
    data = json.loads(config.EMPLOYEES_CACHE.read_text(encoding="utf-8"))
    pairs: list[tuple[str, str]] = []
    for item in data:
        full = item["name"] if isinstance(item, dict) else str(item)
        surname = full.split()[0].lower().replace("ё", "е")
        if surname:
            pairs.append((surname, full))
    pairs.sort(key=lambda x: len(x[0]), reverse=True)
    return pairs


def _norm_person_key(value: str) -> str:
    text = (value or "").lower().replace("ё", "е")
    text = re.sub(r"[.\s]+", " ", text).strip()
    return text


def resolve_employee_name(raw: str) -> str:
    """
    Expand surname-only (or short) names to штатный ФИО с инициалами.

    Unique surname «Карандак» → «Карандак В.Е.».
    Ambiguous surname (Бирюков, Жмыхов, …) left unchanged unless initials match.
    """
    name = (raw or "").strip()
    if not name:
        return name

    employees = _employee_surnames()
    if not employees:
        return name

    # Already an exact штатный ФИО
    key = _norm_person_key(name)
    for _, full in employees:
        if _norm_person_key(full) == key:
            return full

    parts = name.split()
    surname = parts[0].lower().replace("ё", "е")
    candidates = [full for sur, full in employees if sur == surname]
    if not candidates:
        return name
    if len(candidates) == 1:
        return candidates[0]

    # Several people with same surname — match by given initials if present
    if len(parts) >= 2:
        initials = _norm_person_key(" ".join(parts[1:]))
        # «В.Е.» / «В Е» / «ВЕ»
        compact = initials.replace(" ", "").replace(".", "")
        matched = []
        for full in candidates:
            rest = _norm_person_key(" ".join(full.split()[1:]))
            rest_compact = rest.replace(" ", "").replace(".", "")
            if initials and (initials in rest or rest.startswith(initials) or compact == rest_compact[: len(compact)]):
                matched.append(full)
        if len(matched) == 1:
            return matched[0]

    return name


def resolve_members(members: list[str]) -> list[str]:
    """Resolve each member and drop empty duplicates (keep order)."""
    out: list[str] = []
    seen: set[str] = set()
    for m in members:
        resolved = resolve_employee_name(str(m).strip())
        if not resolved:
            continue
        key = _norm_person_key(resolved)
        if key in seen:
            continue
        seen.add(key)
        out.append(resolved)
    return out


def preprocess_report_text(text: str) -> str:
    """Normalize messy report text before sending to the model.

    - Keep line breaks (multi-block reports).
    - Insert commas between brigade surnames on the first line(s).
    - Rewrite qty-before/qty-after lines to canonical «название — N ед».
    """
    t = (text or "").replace("\u00a0", " ")
    t = t.replace("–", "—").replace("−", "—")
    # «шт.настройка» → separate jobs for the model (new line)
    t = re.sub(r"(шт\.?)\s*(?=[А-Яа-яA-Za-z])", r"\1\n", t, flags=re.IGNORECASE)

    lines = t.splitlines()
    surnames = {s for s, _ in _employee_surnames()}

    def _fix_brigade_commas(line: str) -> str:
        if not surnames:
            return line
        words = line.split()
        head_count = 0
        i = 0
        while i < len(words):
            token = re.sub(r"[^А-Яа-яЁёA-Za-z]", "", words[i]).lower().replace("ё", "е")
            if token in surnames:
                head_count += 1
                i += 1
                continue
            if token == "и" and head_count >= 1:
                i += 1
                continue
            break
        if head_count < 2:
            return line
        rebuilt: list[str] = []
        seen = 0
        for j, w in enumerate(words):
            token = re.sub(r"[^А-Яа-яЁёA-Za-z]", "", w).lower().replace("ё", "е")
            if j < i and token in surnames:
                seen += 1
                clean = re.sub(r"[,;]+$", "", w)
                rebuilt.append(clean + ("," if seen < head_count else ""))
                continue
            if j < i and token == "и":
                continue
            rebuilt.append(w)
        return " ".join(rebuilt)

    out: list[str] = []
    for idx, line in enumerate(lines):
        line = line.strip()
        if not line:
            out.append("")
            continue
        if idx < 3:
            line = _fix_brigade_commas(line)
        parsed = analyze_line_quantity(line)
        out.append(format_qty_canonical(parsed))
    # Collapse runs of blank lines but keep structure
    text_out = "\n".join(out)
    text_out = re.sub(r"\n{3,}", "\n\n", text_out)
    return text_out.strip()


def strip_volume_from_task_fields(
    raw_task_name: str,
    job_description: str,
    volume: float | int,
    unit: str,
) -> tuple[str, str, float | int, str]:
    """Remove qty from names (prefix/suffix); recover volume if only present in the name."""

    def _clean(name: str) -> tuple[str, float | None, str | None]:
        text = (name or "").strip()
        parsed = analyze_line_quantity(text)
        if parsed.position != "none" and parsed.volume is not None:
            cleaned = parsed.task_name
            cleaned = re.sub(
                r"\s*\(не найдено[^)]*\)\s*$", "", cleaned, flags=re.IGNORECASE
            ).strip()
            return cleaned, parsed.volume, parsed.unit

        # Fallback: trailing patterns on strings that were skipped as headers
        found_vol: float | None = None
        found_unit: str | None = None
        for pattern in (_VOLUME_IN_NAME_RE, _VOLUME_TRAILING_RE):
            m = pattern.search(text)
            if not m:
                continue
            found_vol = _to_number(m.group(1))
            if m.lastindex and m.lastindex >= 2 and m.group(2):
                found_unit = _norm_unit(m.group(2))
            text = text[: m.start()].rstrip(" -–—:(").strip()
            break
        text = re.sub(r"\s*\(не найдено[^)]*\)\s*$", "", text, flags=re.IGNORECASE).strip()
        return text, found_vol, found_unit

    raw_clean, vol_raw, unit_raw = _clean(raw_task_name)
    desc_clean, vol_desc, unit_desc = _clean(job_description)
    found_vol = vol_raw if vol_raw is not None else vol_desc
    found_unit = unit_raw or unit_desc
    out_vol = volume
    out_unit = (unit or "шт").strip() or "шт"
    if found_vol is not None and (volume in (None, "", 0) or volume == found_vol):
        out_vol = found_vol
    elif found_vol is not None and volume in (0, 1) and found_vol > 1:
        # Model put real qty only in the name (e.g. name «…-19 шт», volume 1)
        out_vol = found_vol
    elif found_vol is not None and found_vol != volume and found_vol > 0:
        # Prefer quantity extracted from the name when it disagrees with a weak model value
        out_vol = found_vol
    if found_unit:
        if out_unit in {"", "-"} or (
            found_unit != out_unit and found_vol is not None and found_vol == out_vol
        ):
            out_unit = found_unit
    if not desc_clean:
        desc_clean = raw_clean
    return raw_clean or raw_task_name, desc_clean or job_description, out_vol, out_unit


def detect_brigade_from_text(text: str) -> list[str]:
    """Surnames of known employees at the start of the report (brigade header)."""
    surnames = _employee_surnames()
    if not surnames:
        return []
    # Only scan the leading chunk before first digit / colon-heavy jobs list
    head = re.split(r"\d|заявк|настрой|монтаж|проклад|подключ|сварк", text, maxsplit=1, flags=re.IGNORECASE)[
        0
    ]
    words = re.findall(r"[А-Яа-яЁёA-Za-z]+", head)
    found: list[str] = []
    seen: set[str] = set()
    for w in words:
        key = w.lower().replace("ё", "е")
        if key in {"и", "с", "по", "на", "в"}:
            continue
        for surname, full in surnames:
            if key == surname and full not in seen:
                found.append(full)
                seen.add(full)
                break
        else:
            # Stop at first non-surname after we already found people
            if found:
                break
    return found


def expand_brigade_workers(report: dict[str, Any], source_text: str) -> dict[str, Any]:
    """Normalize brigade JSON: one workers[] entry with members[], shared jobs once."""
    return normalize_brigade_workers(report, source_text)


def _jobs_fingerprint(jobs: list[dict[str, Any]]) -> tuple:
    rows = []
    for j in jobs:
        rows.append(
            (
                str(j.get("raw_task_name") or "").strip().lower(),
                str(j.get("volume") or ""),
                str(j.get("unit") or "").strip().lower(),
            )
        )
    return tuple(rows)


def _member_list(worker: dict[str, Any]) -> list[str]:
    members = worker.get("members")
    if isinstance(members, list) and members:
        out = [str(m).strip() for m in members if str(m).strip()]
        if out:
            return out
    name = (worker.get("raw_worker_name") or "").strip()
    if not name:
        return []
    # «А, Б» or «А и Б»
    parts = re.split(r"\s*,\s*|\s+и\s+", name)
    parts = [p.strip() for p in parts if p.strip()]
    return parts or [name]


def normalize_brigade_workers(report: dict[str, Any], source_text: str) -> dict[str, Any]:
    """
    Ensure brigade = one workers[] item with members[].

    - Merge several workers that share identical performed_jobs into one brigade.
    - If source text starts with 2+ known surnames and JSON has one person — fill members.
    """
    workers = list(report.get("workers") or [])
    if not workers:
        return report

    # 1) Merge groups with identical job lists
    groups: dict[tuple, list[dict[str, Any]]] = {}
    order: list[tuple] = []
    for w in workers:
        key = _jobs_fingerprint(w.get("performed_jobs") or [])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(w)

    merged: list[dict[str, Any]] = []
    for key in order:
        group = groups[key]
        members: list[str] = []
        seen: set[str] = set()
        for w in group:
            for m in resolve_members(_member_list(w)):
                if m not in seen:
                    members.append(m)
                    seen.add(m)
        jobs = [dict(j) for j in (group[0].get("performed_jobs") or [])]
        merged.append(
            {
                "raw_worker_name": ", ".join(members),
                "members": members,
                "performed_jobs": jobs,
            }
        )

    # 2) Enrich single-member brigade from source header surnames
    brigade = detect_brigade_from_text(source_text)
    if len(brigade) >= 2 and len(merged) == 1 and len(merged[0]["members"]) < len(brigade):
        existing = {_norm_person_key(m) for m in merged[0]["members"]}
        for full in brigade:
            key = _norm_person_key(full)
            sur = full.split()[0].lower().replace("ё", "е")
            if key not in existing and not any(
                _norm_person_key(m).startswith(sur) for m in merged[0]["members"]
            ):
                merged[0]["members"].append(full)
        merged[0]["members"] = resolve_members(merged[0]["members"])
        merged[0]["raw_worker_name"] = ", ".join(merged[0]["members"])

    # 3) Address/place lines mistaken for workers → fold jobs into previous brigade
    folded: list[dict[str, Any]] = []
    for w in merged:
        label = str(w.get("raw_worker_name") or "")
        members = w.get("members") or []
        looks_place = bool(
            _is_skip_qty_line(label)
            or any(_is_skip_qty_line(str(m)) for m in members)
            or re.search(r"\d", label)
        )
        # Known employee surnames only → keep; pure place/address → fold
        if looks_place and folded:
            prev = folded[-1]
            prev["performed_jobs"] = list(prev.get("performed_jobs") or []) + list(
                w.get("performed_jobs") or []
            )
            continue
        if looks_place and not folded:
            # No previous worker — keep jobs under first source brigade if known
            if brigade:
                w = {
                    "raw_worker_name": ", ".join(brigade),
                    "members": list(brigade),
                    "performed_jobs": list(w.get("performed_jobs") or []),
                }
        folded.append(w)

    report["workers"] = folded
    return report


def clean_json_text(raw: str) -> str:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    # Prefer object that contains "workers"
    workers_match = re.search(
        r"\{[^{}]*\"workers\"\s*:\s*\[.*?\]\s*(?:,\s*\"[^\"]+\"\s*:\s*.+?)?\s*\}",
        text,
        flags=re.DOTALL,
    )
    if workers_match:
        candidate = workers_match.group(0)
        # Expand to outermost braces around workers if nested
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return text[start : end + 1].strip()
        return candidate.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    return text.strip()


def _normalize_legacy(parsed: dict[str, Any]) -> dict[str, Any]:
    """Convert old single-worker schema to workers[]."""
    if "workers" in parsed:
        return parsed
    name = parsed.get("raw_worker_name")
    jobs = parsed.get("performed_jobs")
    if name and isinstance(jobs, list):
        return {
            "report_date": parsed.get("report_date"),
            "workers": [{"raw_worker_name": name, "performed_jobs": jobs}],
        }
    return parsed


def validate_report(parsed: dict[str, Any]) -> dict[str, Any]:
    parsed = _normalize_legacy(parsed)
    workers = parsed.get("workers")
    if not isinstance(workers, list) or not workers:
        raise ParseError("JSON без непустого массива workers")

    clean_workers: list[dict[str, Any]] = []
    for w in workers:
        if not isinstance(w, dict):
            raise ParseError("Элемент workers не объект")
        members = resolve_members(_member_list(w))
        if not members:
            raise ParseError("Пустые members / raw_worker_name")
        name = ", ".join(members)
        jobs = w.get("performed_jobs")
        if not isinstance(jobs, list) or not jobs:
            raise ParseError(f"У {name} нет performed_jobs")
        #(Правка в коде Новиков С.С 29.07)
        clean_jobs = []
        for j in jobs:
            if not isinstance(j, dict):
                raise ParseError(f"Работа у {name} не объект")
            if not REQUIRED_JOB_KEYS.issubset(j.keys()):
                raise ParseError(f"У {name} неполная структура работы: {j}")
            vol = j["volume"]

            # (правка Новиков С.С. 29.07.2026) защита от None и пустых значений от модели
            if vol in (None, "", []):
                # если модель не поставила объём, считаем 0 — работа будет без денег
                # (альтернатива: 1, если по бизнес-логике "1 шт" по умолчанию)
                vol = 0

            if isinstance(vol, str):
                raw_vol = vol
                vol = vol.replace(",", ".").strip()
                try:
                    vol = float(vol) if "." in vol else int(vol)
                except ValueError:
                    # пробуем вытащить первое число из строки, например "4 шт"
                    m = re.search(r"(\d+(?:[.,]\d+)?)", raw_vol)
                    if m:
                        num_s = m.group(1).replace(",", ".")
                        vol = float(num_s) if "." in num_s else int(num_s)
                    else:
                        raise ParseError(f"Некорректный volume у {name}: {j['volume']}")
            if not isinstance(vol, (int, float)):
                raise ParseError(f"volume должен быть числом у {name}")
            if not isinstance(vol, (int, float)):
                raise ParseError(f"volume должен быть числом у {name}")
            raw_name, job_desc, vol, unit = strip_volume_from_task_fields(
                str(j["raw_task_name"]).strip(),
                str(j["job_description"]).strip(),
                vol,
                str(j["unit"]).strip(),
            )
            clean_jobs.append(
                {
                    "raw_task_name": raw_name,
                    "job_description": job_desc,
                    "service_type": str(j.get("service_type") or "Общее").strip(),
                    "volume": vol,
                    "unit": unit,
                }
            )
        clean_workers.append(
            {
                "raw_worker_name": name,
                "members": members,
                "performed_jobs": clean_jobs,
            }
        )

    report_date = parsed.get("report_date")
    if report_date in ("", "null", None):
        report_date = None
    elif isinstance(report_date, str):
        report_date = report_date.strip() or None

    return {"report_date": report_date, "workers": clean_workers}


#(Правка в коде Новиков С.С 29.07)
def apply_service_type_from_sections(
    report: dict[str, Any],
    source_text: str,
) -> dict[str, Any]:
    """
    Постобработка service_type по разделам в исходном тексте.

    Логика простая:
    - если в тексте перед блоком работ явно встречается «заявки по тв»,
      считаем все работы этого работника ТВ;
    - если встречается «заявки по интернету» — считаем Интернет;
    - иначе оставляем то, что поставила модель / "Общее".
    """

    text = (source_text or "").lower().replace("ё", "е")

    # Простые маркеры разделов
    tv_markers = ("заявки по тв", "заявки по телевидению", "заявки по телевизору")
    net_markers = ("заявки по интернету", "заявки по интернет", "заявки по инт")

    workers = report.get("workers")
    if not isinstance(workers, list):
        return report

    for w in workers:
        if not isinstance(w, dict):
            continue
        jobs = w.get("performed_jobs")
        if not isinstance(jobs, list) or not jobs:
            continue

        # Пытаемся найти в исходном тексте фамилию/ФИО работника,
        # чтобы определить, какой раздел ближе всего к его блоку.
        raw_name = str(w.get("raw_worker_name") or "").strip()
        name_key = raw_name.split()[0].lower().replace("ё", "е") if raw_name else ""

        # По умолчанию берём первый раздел, который встречается после имени
        current_service_type = None

        # Ищем позицию имени в тексте
        pos = text.find(name_key) if name_key else -1
        search_start = pos if pos != -1 else 0

        # Берём кусок от имени до конца и ищем в нём маркеры разделов
        tail = text[search_start:]

        tv_pos = min((tail.find(m) for m in tv_markers if m in tail), default=-1)
        net_pos = min((tail.find(m) for m in net_markers if m in tail), default=-1)

        if tv_pos != -1 and (net_pos == -1 or tv_pos <= net_pos):
            current_service_type = "ТВ"
        elif net_pos != -1 and (tv_pos == -1 or net_pos < tv_pos):
            current_service_type = "Интернет"

        # Если никакой раздел не найден, оставляем всё как есть
        if not current_service_type:
            continue

        # Перезаписываем service_type для всех работ этого работника
        for j in jobs:
            if not isinstance(j, dict):
                continue
            j["service_type"] = current_service_type

    return report


def call_ollama(report_text: str, extra_prompt: str = "", timeout: int | None = None) -> str:
    system = build_system_prompt()
    user_parts = []
    if extra_prompt.strip():
        user_parts.append(f"ДОПОЛНИТЕЛЬНАЯ ИНСТРУКЦИЯ:\n{extra_prompt.strip()}")
    user_parts.append(
        "Верни ТОЛЬКО JSON по схеме (workers[]). Без Markdown.\n\n"
        f"ОТЧЕТ:\n{report_text.strip()}"
    )
    user_content = "\n\n".join(user_parts)

    # Prefer chat API + JSON mode — qwen often ignores generate-only prompts.
    from core.model_settings import get_active_model

    model_name = get_active_model()
    chat_url = getattr(config, "OLLAMA_CHAT_URL", None) or "http://localhost:11434/api/chat"
    payload = {
        "model": model_name,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
    }

    try:
        response = requests.post(
            chat_url,
            json=payload,
            timeout=timeout or config.OLLAMA_TIMEOUT_SEC,
        )
    except requests.exceptions.Timeout as exc:
        raise ParseError(f"Таймаут Ollama ({timeout or config.OLLAMA_TIMEOUT_SEC} с)") from exc
    except requests.exceptions.ConnectionError as exc:
        raise ParseError("Не удалось соединиться с Ollama. Проверь, запущен ли сервис.") from exc

    if response.status_code != 200:
        # Fallback to /api/generate with format=json
        gen_payload = {
            "model": model_name,
            "prompt": f"{system}\n\n{user_content}\n\nJSON:",
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
        }
        try:
            response = requests.post(
                config.OLLAMA_URL,
                json=gen_payload,
                timeout=timeout or config.OLLAMA_TIMEOUT_SEC,
            )
        except requests.exceptions.RequestException as exc:
            raise ParseError(f"Ollama недоступна: {exc}") from exc
        if response.status_code != 200:
            raise ParseError(
                f"Ollama статус {response.status_code}: {response.text[:300]}"
            )
        data = response.json()
        raw = data.get("response") or ""
    else:
        data = response.json()
        message = data.get("message") or {}
        raw = message.get("content") or data.get("response") or ""

    if not raw.strip():
        raise ParseError("Пустой ответ от модели")
    return raw


def _parse_json_response(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(clean_json_text(raw))
    except json.JSONDecodeError as exc:
        raise ParseError(f"Модель вернула некорректный JSON: {raw[:300]}") from exc
    if not isinstance(parsed, dict):
        raise ParseError("Корень JSON должен быть объектом")
    return parsed


#(правка Новиков С.С. 29.07.2026)
def parse_report_text(
    report_text: str,
    extra_prompt: str = "",
    report_date: str | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    if not report_text or not report_text.strip():
        raise ParseError("Пустой текст отчёта")

    original_text = report_text.strip()
    prepared = preprocess_report_text(original_text)

    raw = call_ollama(prepared, extra_prompt, timeout=timeout)
    try:
        parsed = _parse_json_response(raw)
        validated = validate_report(parsed)
    except ParseError:
        # One retry with an even stricter nudge
        retry_extra = (
            (extra_prompt + "\n" if extra_prompt else "")
            + "CRITICAL: output MUST be a single JSON object with key workers. "
            "Surnames standing together = ONE workers item with members[] and shared jobs once. "
            "Never put volume inside raw_task_name."
        )
        raw2 = call_ollama(prepared, retry_extra, timeout=timeout)
        parsed = _parse_json_response(raw2)
        validated = validate_report(parsed)

    # НОВЫЙ ШАГ: проставляем service_type по разделам в исходном тексте
    validated = apply_service_type_from_sections(validated, original_text)

    validated = expand_brigade_workers(validated, original_text)

    # Коррекция объёмов по позиции числа в исходных строках (до/после названия)
    validated = reconcile_volumes_from_source(validated, original_text)

    if report_date:
        validated["report_date"] = report_date
    if not validated.get("report_date"):
        validated["report_date"] = date.today().isoformat()

    validated["source_text_hash"] = source_text_hash(original_text)
    validated["parsed_at"] = datetime.now().isoformat(timespec="seconds")
    return validated



def save_report_json(report: dict[str, Any], directory: Path | None = None) -> Path:
    """Optional helper — JSON is not auto-saved in the main flow."""
    directory = Path(directory or config.REPORTS_JSON_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = directory / f"report_{ts}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
