from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from forge_neo.bootstrap import ensure_config


ROOT = Path(__file__).resolve().parents[1]
BUNDLED_STYLES_PATH = ROOT / "html" / "forge_neo" / "styles.csv"
STYLE_CSV_FIELDS = ("name", "prompt", "negative_prompt")


@dataclass(frozen=True)
class PromptStyle:
    name: str
    prompt: str
    negative_prompt: str = ""
    path: str = ""


def _csv_candidates() -> list[Path]:
    candidates: list[Path] = []
    try:
        config = ensure_config()
        user_style = Path(config.path_userhome) / "forge_neo" / "styles.csv"
        candidates.append(user_style)
    except Exception:
        pass
    candidates.extend([ROOT / "styles.csv", BUNDLED_STYLES_PATH])
    return candidates


def user_styles_path() -> Path:
    try:
        config = ensure_config()
        base = Path(config.path_userhome)
    except Exception:
        base = ROOT / "users"
    path = base / "forge_neo" / "styles.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_csv(path: Path) -> dict[str, PromptStyle]:
    if not path.exists():
        return {}
    styles: dict[str, PromptStyle] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, skipinitialspace=True)
        fields = tuple(reader.fieldnames or ())
        if any(field not in fields for field in STYLE_CSV_FIELDS):
            return {}
        for row in reader:
            raw_name = str(row.get("name") or "")
            name = raw_name.strip()
            if not name or name.startswith("#"):
                continue
            prompt = str(row.get("prompt") or "")
            negative_prompt = str(row.get("negative_prompt") or "")
            styles[name] = PromptStyle(name=raw_name, prompt=prompt, negative_prompt=negative_prompt, path=str(path))
    return styles


def load_styles() -> dict[str, PromptStyle]:
    styles: dict[str, PromptStyle] = {}
    for path in _csv_candidates():
        try:
            for name, style in _load_csv(path).items():
                if name not in styles:
                    styles[name] = style
        except Exception:
            continue
    return styles


def style_choices() -> list[str]:
    return list(load_styles().keys())


def get_style(name: str) -> PromptStyle | None:
    return load_styles().get(str(name or ""))


def apply_styles_to_prompt(prompt: str, style_texts: list[str]) -> str:
    result = str(prompt or "")
    for style_text in style_texts:
        style_text = str(style_text or "")
        if not style_text:
            continue
        if "{prompt}" in style_text:
            result = style_text.replace("{prompt}", result)
        else:
            parts = [part for part in [result.strip(), style_text.strip()] if part]
            result = ", ".join(parts)
    return result


def apply_style_names(prompt: str, negative_prompt: str, names: list[str]) -> tuple[str, str]:
    catalog = load_styles()
    selected = [catalog[name] for name in names or [] if name in catalog]
    return (
        apply_styles_to_prompt(prompt, [style.prompt for style in selected]),
        apply_styles_to_prompt(negative_prompt, [style.negative_prompt for style in selected]),
    )


def save_style(name: str, prompt: str, negative_prompt: str) -> PromptStyle:
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("Style name is empty")
    path = user_styles_path()
    styles = _load_csv(path)
    styles[clean_name] = PromptStyle(clean_name, str(prompt or ""), str(negative_prompt or ""), str(path))
    _write_user_styles(path, styles)
    return styles[clean_name]


def delete_style(name: str) -> None:
    clean_name = str(name or "").strip()
    if not clean_name:
        return
    path = user_styles_path()
    styles = _load_csv(path)
    if clean_name in styles:
        del styles[clean_name]
        _write_user_styles(path, styles)


def _write_user_styles(path: Path, styles: dict[str, PromptStyle]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(STYLE_CSV_FIELDS))
        writer.writeheader()
        for style in styles.values():
            writer.writerow(
                {
                    "name": style.name,
                    "prompt": style.prompt,
                    "negative_prompt": style.negative_prompt,
                }
            )
