from __future__ import annotations

from collections.abc import Mapping


def normalize_lang(value: object) -> str:
    raw = str(value or "").strip().lower()
    if raw.startswith("en"):
        return "en"
    return "cn"


def state_lang(state: Mapping[str, object] | None, default: str = "cn") -> str:
    if state:
        lang = state.get("__lang") or state.get("lang") or state.get("language")
        if lang:
            return normalize_lang(lang)
        nested = state.get("state")
        if isinstance(nested, Mapping):
            lang = nested.get("__lang") or nested.get("lang") or nested.get("language")
            if lang:
                return normalize_lang(lang)
    return normalize_lang(default)


def t(state: Mapping[str, object] | None, en: str, cn: str) -> str:
    return en if state_lang(state) == "en" else cn
