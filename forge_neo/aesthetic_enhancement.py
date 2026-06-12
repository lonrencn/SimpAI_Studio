from __future__ import annotations

import importlib.util
import html
import time
from pathlib import Path
from typing import Any

from PIL import Image


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ROOT = Path(__file__).resolve().parents[1]
EXTENSION_DIR = ROOT / "forge_neo" / "webui" / "extensions" / "sd-webui-AestheticEnhancement"
ASSET_ROOT = EXTENSION_DIR / "Aesthetic-Enhancement"
SCRIPTS_DIR = EXTENSION_DIR / "scripts"
QWEN_ANALYSIS_SOURCE = SCRIPTS_DIR / "qwen_analysis_ui.py"
QWEN_ANALYSIS_OUTPUT_DIR = ROOT / "forge_neo" / "webui" / "outputs" / "aesthetic-analysis"
QWEN_ANALYSIS_MODELS = (
    "qwen3.5:9b",
    "qwen3.5:4b",
    "qwen3.5:2b",
    "huihui_ai/qwen3.5-abliterated:9B",
    "huihui_ai/qwen3.5-abliterated:4B",
    "huihui_ai/qwen3.5-abliterated:2B",
)
QWEN_ANALYSIS_TYPES = (
    ("Comprehensive", "comprehensive"),
    ("Composition", "composition"),
    ("Lighting", "lighting"),
    ("Shot", "shot"),
)
_QWEN_ANALYSIS_MODULE: Any = None


def aesthetic_asset_root() -> Path:
    return ASSET_ROOT


def aesthetic_qwen_analysis_defaults() -> dict[str, Any]:
    return {
        "available": QWEN_ANALYSIS_SOURCE.is_file(),
        "source_module": str(QWEN_ANALYSIS_SOURCE),
        "output_dir": str(QWEN_ANALYSIS_OUTPUT_DIR),
        "models": list(QWEN_ANALYSIS_MODELS),
        "default_model": "qwen3.5:4b",
        "analysis_types": [{"label": label, "value": value} for label, value in QWEN_ANALYSIS_TYPES],
        "default_analysis_type": "comprehensive",
        "default_mode": "image",
        "default_frame_interval": 30,
    }


def _load_qwen_analysis_module() -> Any:
    global _QWEN_ANALYSIS_MODULE
    if _QWEN_ANALYSIS_MODULE is not None:
        return _QWEN_ANALYSIS_MODULE
    if not QWEN_ANALYSIS_SOURCE.is_file():
        raise FileNotFoundError(f"Aesthetic Qwen analysis module is missing: {QWEN_ANALYSIS_SOURCE}")
    spec = importlib.util.spec_from_file_location("_forge_neo_aesthetic_qwen_analysis", QWEN_ANALYSIS_SOURCE)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load Aesthetic Qwen analysis module: {QWEN_ANALYSIS_SOURCE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _QWEN_ANALYSIS_MODULE = module
    return module


def _source_path_from_value(value: object) -> str:
    if isinstance(value, str) and Path(value).is_file():
        return value
    if isinstance(value, dict):
        for key in ("name", "path", "file"):
            candidate = value.get(key)
            if isinstance(candidate, str) and Path(candidate).is_file():
                return candidate
    if isinstance(value, Image.Image):
        QWEN_ANALYSIS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path = QWEN_ANALYSIS_OUTPUT_DIR / f"input_{time.strftime('%Y%m%d_%H%M%S')}.png"
        value.save(path)
        return str(path)
    return ""


def aesthetic_qwen_connection_status() -> dict[str, Any]:
    try:
        module = _load_qwen_analysis_module()
        ok, message = module.test_ollama_connection()
        return {"ok": bool(ok), "message": str(message or ""), "available": True}
    except Exception as exc:
        return {"ok": False, "message": f"Qwen analysis is unavailable: {exc}", "available": False}


def aesthetic_qwen_analyze(
    *,
    model: object,
    mode: object,
    analysis_type: object,
    image: object = None,
    video: object = None,
    frame_interval: object = 30,
) -> dict[str, Any]:
    try:
        module = _load_qwen_analysis_module()
    except Exception as exc:
        return {"ok": False, "message": f"Qwen analysis is unavailable: {exc}", "analysis": "", "frames": []}

    selected_model = str(model or aesthetic_qwen_analysis_defaults()["default_model"]).strip()
    selected_type = str(analysis_type or "comprehensive").strip()
    selected_mode = str(mode or "image").strip().lower()
    if selected_mode == "video":
        video_path = _source_path_from_value(video)
        if not video_path:
            return {"ok": False, "message": "Video is required.", "analysis": "", "frames": []}
        try:
            interval = max(0, int(float(str(frame_interval or 30))))
        except Exception:
            interval = 30
        QWEN_ANALYSIS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        frame_paths = module.extract_video_frames(video_path, str(QWEN_ANALYSIS_OUTPUT_DIR), interval)
        if not frame_paths:
            return {"ok": False, "message": "Video frame extraction failed.", "analysis": "", "frames": []}
        analysis = module.batch_analyze_images(frame_paths, selected_type, selected_model)
        return {"ok": True, "message": f"Analyzed {len(frame_paths)} frame(s).", "analysis": str(analysis or ""), "frames": frame_paths}

    image_path = _source_path_from_value(image)
    if not image_path:
        return {"ok": False, "message": "Image is required.", "analysis": "", "frames": []}
    result = module.analyze_single_image(image_path, selected_type, selected_model)
    analysis = str(result.get("analysis") or result.get("error") or "")
    return {
        "ok": bool(result.get("success")),
        "message": "Analysis finished." if result.get("success") else "Analysis failed.",
        "analysis": analysis,
        "frames": [],
    }


def _image_files(path: Path) -> list[Path]:
    if not path.is_dir():
        return []
    return sorted(item for item in path.iterdir() if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS)


def _label_from_path(path: Path) -> str:
    return path.stem.rstrip(".").strip() or path.name


def composition_images() -> list[dict[str, str]]:
    values: list[dict[str, str]] = []
    for path in _image_files(ASSET_ROOT / "构图技巧"):
        values.append({"path": str(path), "name": _label_from_path(path), "group": "composition"})
    return values


def lighting_images() -> list[dict[str, str]]:
    values: list[dict[str, str]] = []
    for path in _image_files(ASSET_ROOT / "打光技巧"):
        values.append({"path": str(path), "name": _label_from_path(path), "group": "lighting"})
    return values


def artist_images() -> list[dict[str, str]]:
    artists_root = ASSET_ROOT / "画师百科"
    if not artists_root.is_dir():
        return []
    values: list[dict[str, str]] = []
    for style_dir in sorted(item for item in artists_root.iterdir() if item.is_dir()):
        for path in _image_files(style_dir):
            values.append({"path": str(path), "name": _label_from_path(path), "group": style_dir.name})
    return values


def aesthetic_counts() -> dict[str, Any]:
    artists = artist_images()
    styles = sorted({item["group"] for item in artists})
    return {
        "artists": len(artists),
        "artist_styles": len(styles),
        "composition": len(composition_images()),
        "lighting": len(lighting_images()),
        "styles": styles,
    }


def aesthetic_gallery_values(kind: str) -> list[tuple[str, str]]:
    if kind == "composition":
        rows = composition_images()
    elif kind == "lighting":
        rows = lighting_images()
    else:
        rows = artist_images()
    values: list[tuple[str, str]] = []
    for row in rows:
        caption = row["name"] if kind in {"composition", "lighting"} else f"{row['group']} / {row['name']}"
        values.append((row["path"], caption))
    return values


def aesthetic_summary_html() -> str:
    counts = aesthetic_counts()
    if not ASSET_ROOT.is_dir():
        return '<div class="forge-neo-aesthetic-summary">Aesthetic Enhancement assets are unavailable.</div>'
    parts = [
        ("Artist styles", counts["artist_styles"]),
        ("Artists", counts["artists"]),
        ("Composition", counts["composition"]),
        ("Lighting", counts["lighting"]),
    ]
    items = "".join(
        f"<span><strong>{html.escape(label)}</strong>{html.escape(str(value))}</span>"
        for label, value in parts
    )
    return f'<div class="forge-neo-aesthetic-summary">{items}</div>'
