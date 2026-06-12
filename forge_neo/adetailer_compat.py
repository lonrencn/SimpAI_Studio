from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
ADETAILER_EXTENSION_DIRNAME = "ADetailer-Neo"
ADETAILER_EXTENSION_ROOT = ROOT / "forge_neo" / "webui" / "extensions" / ADETAILER_EXTENSION_DIRNAME
ADETAILER_MODEL_DIRS = (
    ROOT / "models" / "adetailer",
    ROOT / "forge_neo" / "webui" / "models" / "adetailer",
    ADETAILER_EXTENSION_ROOT / "models",
)
ADETAILER_MODEL_EXTENSIONS = (".pt", ".tflite", ".task")
ADETAILER_BUILTIN_MODELS = (
    "face_yolov8n.pt",
    "face_yolov8s.pt",
    "hand_yolov8n.pt",
    "hand_yolov8s.pt",
    "person_yolov8n-seg.pt",
    "person_yolov8s-seg.pt",
    "yolov8x-worldv2.pt",
    "mediapipe_face_short.tflite",
    "mediapipe_face_full.tflite",
    "face_landmarker.task",
)
ADETAILER_MODELSCOPE_BASE_URL = "https://modelscope.cn/models/windecay/SimpAI_dev/resolve/master/SimpleModels/adetailer"
ADETAILER_MODEL_DOWNLOAD_URLS = {
    model_name: f"{ADETAILER_MODELSCOPE_BASE_URL}/{model_name}"
    for model_name in ADETAILER_BUILTIN_MODELS
}
ADETAILER_ARG_LABELS = (
    ("ad_model", "ADetailer model"),
    ("ad_model_classes", "ADetailer model classes"),
    ("ad_tab_enable", "ADetailer tab enable"),
    ("ad_prompt", "ADetailer prompt"),
    ("ad_negative_prompt", "ADetailer negative prompt"),
    ("ad_confidence", "ADetailer confidence"),
    ("ad_mask_filter_method", "ADetailer method to decide top k masks"),
    ("ad_mask_k", "ADetailer mask only top k"),
    ("ad_mask_min_ratio", "ADetailer mask min ratio"),
    ("ad_mask_max_ratio", "ADetailer mask max ratio"),
    ("ad_x_offset", "ADetailer x offset"),
    ("ad_y_offset", "ADetailer y offset"),
    ("ad_dilate_erode", "ADetailer dilate erode"),
    ("ad_mask_merge_invert", "ADetailer mask merge invert"),
    ("ad_mask_blur", "ADetailer mask blur"),
    ("ad_denoising_strength", "ADetailer denoising strength"),
    ("ad_inpaint_only_masked", "ADetailer inpaint only masked"),
    ("ad_inpaint_only_masked_padding", "ADetailer inpaint padding"),
    ("ad_use_inpaint_width_height", "ADetailer use inpaint width height"),
    ("ad_inpaint_width", "ADetailer inpaint width"),
    ("ad_inpaint_height", "ADetailer inpaint height"),
    ("ad_use_steps", "ADetailer use separate steps"),
    ("ad_steps", "ADetailer steps"),
    ("ad_use_cfg_scale", "ADetailer use separate CFG scale"),
    ("ad_cfg_scale", "ADetailer CFG scale"),
    ("ad_use_checkpoint", "ADetailer use separate checkpoint"),
    ("ad_checkpoint", "ADetailer checkpoint"),
    ("ad_use_vae", "ADetailer use separate VAE"),
    ("ad_vae", "ADetailer VAE"),
    ("ad_use_sampler", "ADetailer use separate sampler"),
    ("ad_sampler", "ADetailer sampler"),
    ("ad_scheduler", "ADetailer scheduler"),
    ("ad_use_noise_multiplier", "ADetailer use separate noise multiplier"),
    ("ad_noise_multiplier", "ADetailer noise multiplier"),
    ("ad_restore_face", "ADetailer restore face"),
    ("ad_controlnet_model", "ADetailer ControlNet model"),
    ("ad_controlnet_module", "ADetailer ControlNet module"),
    ("ad_controlnet_weight", "ADetailer ControlNet weight"),
    ("ad_controlnet_guidance_start_end", "ADetailer ControlNet guidance start/end"),
)
ADETAILER_ARG_DEFAULTS: dict[str, Any] = {
    "ad_model": "None",
    "ad_model_classes": "",
    "ad_tab_enable": True,
    "ad_prompt": "",
    "ad_negative_prompt": "",
    "ad_confidence": 0.3,
    "ad_mask_filter_method": "Area",
    "ad_mask_k": 0,
    "ad_mask_min_ratio": 0.0,
    "ad_mask_max_ratio": 1.0,
    "ad_x_offset": 0,
    "ad_y_offset": 0,
    "ad_dilate_erode": 4,
    "ad_mask_merge_invert": "None",
    "ad_mask_blur": 4,
    "ad_denoising_strength": 0.5,
    "ad_inpaint_only_masked": True,
    "ad_inpaint_only_masked_padding": 32,
    "ad_use_inpaint_width_height": False,
    "ad_inpaint_width": 512,
    "ad_inpaint_height": 512,
    "ad_use_steps": False,
    "ad_steps": 20,
    "ad_use_cfg_scale": False,
    "ad_cfg_scale": 4.0,
    "ad_use_checkpoint": False,
    "ad_checkpoint": None,
    "ad_use_vae": False,
    "ad_vae": None,
    "ad_use_sampler": False,
    "ad_sampler": "Use same sampler",
    "ad_scheduler": "Use same scheduler",
    "ad_use_noise_multiplier": False,
    "ad_noise_multiplier": 1.0,
    "ad_restore_face": False,
    "ad_controlnet_model": "None",
    "ad_controlnet_module": "None",
    "ad_controlnet_weight": 1.0,
    "ad_controlnet_guidance_start_end": [0.0, 1.0],
    "is_api": True,
}


def adetailer_default_args(**overrides: Any) -> dict[str, Any]:
    data = dict(ADETAILER_ARG_DEFAULTS)
    for key, value in overrides.items():
        if key in data:
            data[key] = value
    return data


def adetailer_model_names(*, include_none: bool = True) -> list[str]:
    names: list[str] = ["None"] if include_none else []
    for model in ADETAILER_BUILTIN_MODELS:
        if model not in names:
            names.append(model)
    for root in ADETAILER_MODEL_DIRS:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*"), key=lambda item: item.name.lower()):
            if not path.is_file() or path.suffix.lower() not in ADETAILER_MODEL_EXTENSIONS:
                continue
            if path.name not in names:
                names.append(path.name)
    return names


def adetailer_primary_model_dir() -> Path:
    return ROOT / "forge_neo" / "webui" / "models" / "adetailer"


def adetailer_model_download_url(model_name: object) -> str:
    name = _adetailer_model_basename(model_name)
    return ADETAILER_MODEL_DOWNLOAD_URLS.get(name, "")


def adetailer_find_model_path(model_name: object) -> Path | None:
    name = _adetailer_model_basename(model_name)
    if not name:
        return None
    for root in ADETAILER_MODEL_DIRS:
        path = root / name
        if path.is_file():
            return path
    return None


def adetailer_ensure_model(model_name: object, *, download: bool = True, target_dir: Path | None = None) -> dict[str, Any]:
    name = _adetailer_model_basename(model_name)
    if not name or name == "None":
        return {"ok": True, "model": name or "None", "skipped": True, "reason": "empty"}

    existing = adetailer_find_model_path(name)
    if existing is not None:
        return {"ok": True, "model": name, "downloaded": False, "path": str(existing)}

    url = adetailer_model_download_url(name)
    if not url:
        return {"ok": False, "model": name, "downloaded": False, "error": "model_url_not_configured"}
    if not download:
        return {"ok": False, "model": name, "downloaded": False, "url": url, "error": "model_missing"}

    root = Path(target_dir) if target_dir is not None else adetailer_primary_model_dir()
    root.mkdir(parents=True, exist_ok=True)
    target = root / name
    temp = target.with_name(f"{target.name}.download")
    try:
        with urllib.request.urlopen(url, timeout=180) as response, temp.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
        os.replace(temp, target)
    finally:
        if temp.exists():
            try:
                temp.unlink()
            except OSError:
                pass
    return {"ok": True, "model": name, "downloaded": True, "path": str(target), "url": url}


def adetailer_preferred_model() -> str:
    for name in adetailer_model_names(include_none=False):
        if name != "None":
            return name
    return "None"


def adetailer_schema_payload() -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for attr, label in ADETAILER_ARG_LABELS:
        default = ADETAILER_ARG_DEFAULTS.get(attr)
        properties[attr] = {
            "title": label,
            "default": default,
            "type": _json_schema_type(default),
        }
    properties["is_api"] = {"title": "is_api", "default": True, "type": "boolean"}
    return {
        "title": "ADetailerArgs",
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
    }


def adetailer_version() -> str:
    path = ADETAILER_EXTENSION_ROOT / "lib_adetailer" / "__init__.py"
    if not path.exists():
        return "forge-neo-adapter"
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return "forge-neo-adapter"
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__version__":
                    value = getattr(node, "value", None)
                    if isinstance(value, ast.Constant) and value.value:
                        return str(value.value)
    return "forge-neo-adapter"


def _adetailer_model_basename(model_name: object) -> str:
    name = str(model_name or "").strip()
    if not name:
        return ""
    basename = Path(name).name
    if basename != name or "/" in name or "\\" in name:
        return ""
    return basename


def _json_schema_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if value is None:
        return "null"
    if isinstance(value, (list, tuple)):
        return "array"
    return "string"
