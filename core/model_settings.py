# -*- coding: utf-8 -*-
"""Runtime AI model selection for Ollama (persisted in data/model_settings.json)."""
from __future__ import annotations

import json
from typing import Any

import requests

from core import config

# Presets shown in Settings even if not yet pulled in Ollama.
MODEL_PRESETS: list[dict[str, str]] = [
    {
        "name": "qwen2.5:3b",
        "label": "qwen2.5:3b — CPU (рекомендуется)",
    },
    {
        "name": "qwen2.5:1.5b",
        "label": "qwen2.5:1.5b — слабый CPU",
    },
    {
        "name": "qwen2.5:7b",
        "label": "qwen2.5:7b — качество (лучше с GPU)",
    },
    {
        "name": "qwen3:1.7b",
        "label": "qwen3:1.7b — эксперимент",
    },
    {
        "name": "llama3.2:3b",
        "label": "llama3.2:3b — альтернатива",
    },
]


def _default_model() -> str:
    return str(getattr(config, "MODEL_NAME", "qwen2.5:3b") or "qwen2.5:3b").strip()


def _load_settings() -> dict[str, Any]:
    path = config.MODEL_SETTINGS_CACHE
    if not path.exists():
        return {"model": _default_model()}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"model": _default_model()}
    if not isinstance(data, dict):
        return {"model": _default_model()}
    model = str(data.get("model") or "").strip()
    if not model:
        model = _default_model()
    return {"model": model}


def _save_settings(model: str) -> dict[str, Any]:
    path = config.MODEL_SETTINGS_CACHE
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"model": model}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def get_active_model() -> str:
    """Model name used for Ollama parse calls."""
    return _load_settings()["model"]


def set_active_model(model: str) -> dict[str, Any]:
    name = str(model or "").strip()
    if not name:
        raise ValueError("Укажите имя модели Ollama")
    if len(name) > 120 or any(ch in name for ch in ("\n", "\r", "\t", " ")):
        raise ValueError("Некорректное имя модели")
    return _save_settings(name)


def list_ollama_models(timeout: float = 3.0) -> list[dict[str, Any]]:
    """Return models installed in local Ollama (empty list if unavailable)."""
    base = getattr(config, "OLLAMA_CHAT_URL", "") or "http://localhost:11434/api/chat"
    tags_url = base.replace("/api/chat", "/api/tags")
    if tags_url == base:
        tags_url = "http://localhost:11434/api/tags"
    try:
        resp = requests.get(tags_url, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError, TypeError):
        return []
    out: list[dict[str, Any]] = []
    for item in data.get("models") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("model") or "").strip()
        if not name:
            continue
        out.append(
            {
                "name": name,
                "size": item.get("size"),
                "modified_at": item.get("modified_at"),
            }
        )
    return out


def model_settings_payload() -> dict[str, Any]:
    active = get_active_model()
    installed = list_ollama_models()
    installed_names = {m["name"] for m in installed}
    # Also match tags without digest suffix (name:tag)
    installed_base = {n.split(":")[0] + (":" + n.split(":")[1] if ":" in n else "") for n in installed_names}

    options: list[dict[str, Any]] = []
    seen: set[str] = set()

    for preset in MODEL_PRESETS:
        name = preset["name"]
        options.append(
            {
                "name": name,
                "label": preset["label"],
                "installed": name in installed_names or name in installed_base,
                "preset": True,
            }
        )
        seen.add(name)

    for m in installed:
        name = m["name"]
        if name in seen:
            continue
        options.append(
            {
                "name": name,
                "label": name,
                "installed": True,
                "preset": False,
            }
        )
        seen.add(name)

    if active not in seen:
        options.insert(
            0,
            {
                "name": active,
                "label": f"{active} (текущая)",
                "installed": active in installed_names,
                "preset": False,
            },
        )

    return {
        "ok": True,
        "model": active,
        "default_model": _default_model(),
        "ollama_ok": bool(installed),
        "options": options,
        "installed": installed,
    }
