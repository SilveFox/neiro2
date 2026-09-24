# -*- coding: utf-8 -*-
"""Compare full vs compact prompt: size + live Ollama parse quality."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.parser import call_ollama, clean_json_text, validate_report
from core.prompt import build_system_prompt
from core.prompt_full import build_system_prompt_full

SAMPLE = """Слободянюк, Чуприков
1 заявка по неисправности интернета
СНТ победа 255
3 выкладки запаса кабеля
2 муфты монтаж
Перекидка кабеля между зданиями 30 м
19 сварок 1-7
2 обжима рж 45
"""

OUT = Path(__file__).resolve().parent / "_prompt_compact_test.json"


def check_json(raw: str) -> dict:
    parsed = json.loads(clean_json_text(raw))
    validated = validate_report(parsed)
    workers = validated.get("workers") or []
    jobs = []
    for w in workers:
        for j in w.get("performed_jobs") or []:
            jobs.append(
                {
                    "name": j.get("raw_task_name"),
                    "volume": j.get("volume"),
                    "unit": j.get("unit"),
                    "service_type": j.get("service_type"),
                }
            )
    return {
        "ok": True,
        "workers": len(workers),
        "members": (workers[0].get("members") if workers else []),
        "jobs_count": len(jobs),
        "jobs": jobs,
        "raw_preview": raw[:800],
    }


def run_with_prompt(label: str, prompt: str) -> dict:
    import core.parser as parser_mod
    import core.prompt as prompt_mod

    orig_p = prompt_mod.build_system_prompt
    orig_c = parser_mod.build_system_prompt
    prompt_mod.build_system_prompt = lambda: prompt
    parser_mod.build_system_prompt = lambda: prompt
    t0 = time.perf_counter()
    try:
        raw = call_ollama(SAMPLE, timeout=180)
        elapsed = round(time.perf_counter() - t0, 2)
        try:
            info = check_json(raw)
        except Exception as ve:
            return {
                "ok": False,
                "label": label,
                "prompt_chars": len(prompt),
                "elapsed_sec": elapsed,
                "error": str(ve),
                "raw_preview": raw[:800],
            }
        info["elapsed_sec"] = elapsed
        info["prompt_chars"] = len(prompt)
        info["label"] = label
        return info
    except Exception as exc:
        return {
            "ok": False,
            "label": label,
            "prompt_chars": len(prompt),
            "error": str(exc),
            "elapsed_sec": round(time.perf_counter() - t0, 2),
        }
    finally:
        prompt_mod.build_system_prompt = orig_p
        parser_mod.build_system_prompt = orig_c


def main():
    full = build_system_prompt_full()
    compact = build_system_prompt()
    ratio = round(len(full) / max(len(compact), 1), 2)

    print("FULL chars:", len(full))
    print("COMPACT chars:", len(compact))
    print("RATIO full/compact:", ratio)

    expect_vols = {3, 2, 30, 19}
    results = {
        "sizes": {"full": len(full), "compact": len(compact), "ratio": ratio},
        "sample": SAMPLE,
        "runs": [],
    }

    for label, prompt in (("compact", compact), ("full", full)):
        print(f"\n=== RUN {label} ===")
        info = run_with_prompt(label, prompt)
        printable = {k: v for k, v in info.items() if k != "raw_preview"}
        print(json.dumps(printable, ensure_ascii=False, indent=2))
        if info.get("ok"):
            vols = {j["volume"] for j in info["jobs"]}
            info["quality"] = {
                "brigade_ok": len(info.get("members") or []) >= 2,
                "enough_jobs": info["jobs_count"] >= 4,
                "volumes_hit": sorted(vols & expect_vols),
                "has_19": any(j["volume"] == 19 for j in info["jobs"]),
                "has_30m": any(
                    j["volume"] == 30 and j.get("unit") in ("м", "m") for j in info["jobs"]
                ),
            }
            print("quality:", json.dumps(info["quality"], ensure_ascii=False))
        results["runs"].append(info)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nsaved", OUT)


if __name__ == "__main__":
    main()
