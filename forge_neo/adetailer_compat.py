from __future__ import annotations

import ast
import json
import os
from datetime import datetime, timezone
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
ADETAILER_STATE_SCHEMA_VERSION = 1
ADETAILER_STATE_UNIT_COUNT = 4
ADETAILER_STATE_FILENAME = "forge_neo_adetailer_state.json"
ADETAILER_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
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


def adetailer_state_path(*, create_parent: bool = False) -> Path:
    from forge_neo.bootstrap import ensure_config

    config = ensure_config(test_stub=os.environ.get("FORGE_NEO_TEST_TOKEN_STUB") == "1")
    base = Path(getattr(config, "path_userhome", "") or ".")
    path = base / "forge_neo" / ADETAILER_STATE_FILENAME
    if create_parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def adetailer_sidecar_path(image_path: str | os.PathLike[str]) -> Path:
    return Path(image_path).with_suffix(".adetailer.json")


def adetailer_normalized_args(value: object) -> dict[str, Any]:
    data = dict(value) if isinstance(value, dict) else {}
    normalized = adetailer_default_args(**data)
    guidance_value = data.get("ad_controlnet_guidance_start_end")
    if isinstance(guidance_value, (list, tuple)) and len(guidance_value) >= 2:
        guidance_start_raw, guidance_end_raw = guidance_value[0], guidance_value[1]
    else:
        guidance_start_raw = data.get("ad_controlnet_guidance_start", 0.0)
        guidance_end_raw = data.get("ad_controlnet_guidance_end", 1.0)

    mask_filter_method = str(normalized.get("ad_mask_filter_method") or "Area")
    if mask_filter_method not in {"Area", "Confidence"}:
        mask_filter_method = "Area"
    mask_merge_invert = str(normalized.get("ad_mask_merge_invert") or "None")
    if mask_merge_invert not in {"None", "Merge", "Merge and Invert"}:
        mask_merge_invert = "None"

    normalized["ad_model"] = str(normalized.get("ad_model") or "None")
    normalized["ad_model_classes"] = str(normalized.get("ad_model_classes") or "")
    normalized["ad_tab_enable"] = _bool_value(normalized.get("ad_tab_enable"), True)
    normalized["ad_prompt"] = str(normalized.get("ad_prompt") or "")
    normalized["ad_negative_prompt"] = str(normalized.get("ad_negative_prompt") or "")
    normalized["ad_confidence"] = _clamped_float(normalized.get("ad_confidence", 0.3), 0.3, minimum=0.0, maximum=1.0)
    normalized["ad_mask_filter_method"] = mask_filter_method
    normalized["ad_mask_k"] = _clamped_int(normalized.get("ad_mask_k", 0), 0, minimum=0, maximum=10)
    normalized["ad_mask_min_ratio"] = _clamped_float(normalized.get("ad_mask_min_ratio", 0.0), 0.0, minimum=0.0, maximum=1.0)
    normalized["ad_mask_max_ratio"] = _clamped_float(normalized.get("ad_mask_max_ratio", 1.0), 1.0, minimum=0.0, maximum=1.0)
    normalized["ad_x_offset"] = _clamped_int(normalized.get("ad_x_offset", 0), 0, minimum=-200, maximum=200)
    normalized["ad_y_offset"] = _clamped_int(normalized.get("ad_y_offset", 0), 0, minimum=-200, maximum=200)
    normalized["ad_mask_merge_invert"] = mask_merge_invert
    normalized["ad_mask_blur"] = _clamped_int(normalized.get("ad_mask_blur", 4), 4, minimum=0, maximum=256)
    normalized["ad_dilate_erode"] = _clamped_int(normalized.get("ad_dilate_erode", 4), 4, minimum=-256, maximum=256)
    normalized["ad_denoising_strength"] = _clamped_float(normalized.get("ad_denoising_strength", 0.5), 0.5, minimum=0.0, maximum=1.0)
    normalized["ad_inpaint_only_masked"] = _bool_value(normalized.get("ad_inpaint_only_masked"), True)
    normalized["ad_inpaint_only_masked_padding"] = _clamped_int(normalized.get("ad_inpaint_only_masked_padding", 32), 32, minimum=0, maximum=512)
    normalized["ad_use_inpaint_width_height"] = _bool_value(normalized.get("ad_use_inpaint_width_height"), False)
    normalized["ad_inpaint_width"] = _clamped_int(normalized.get("ad_inpaint_width", 512), 512, minimum=64, maximum=2048)
    normalized["ad_inpaint_height"] = _clamped_int(normalized.get("ad_inpaint_height", 512), 512, minimum=64, maximum=2048)
    normalized["ad_use_steps"] = _bool_value(normalized.get("ad_use_steps"), False)
    normalized["ad_steps"] = _clamped_int(normalized.get("ad_steps", 20), 20, minimum=1, maximum=150)
    normalized["ad_use_cfg_scale"] = _bool_value(normalized.get("ad_use_cfg_scale"), False)
    normalized["ad_cfg_scale"] = _clamped_float(normalized.get("ad_cfg_scale", 4.0), 4.0, minimum=1.0, maximum=24.0)
    normalized["ad_use_checkpoint"] = _bool_value(normalized.get("ad_use_checkpoint"), False)
    normalized["ad_checkpoint"] = str(normalized.get("ad_checkpoint") or "Use same checkpoint")
    normalized["ad_use_vae"] = _bool_value(normalized.get("ad_use_vae"), False)
    normalized["ad_vae"] = str(normalized.get("ad_vae") or "Use same VAE")
    normalized["ad_use_sampler"] = _bool_value(normalized.get("ad_use_sampler"), False)
    normalized["ad_sampler"] = str(normalized.get("ad_sampler") or "Use same sampler")
    normalized["ad_scheduler"] = str(normalized.get("ad_scheduler") or "Use same scheduler")
    normalized["ad_use_noise_multiplier"] = _bool_value(normalized.get("ad_use_noise_multiplier"), False)
    normalized["ad_noise_multiplier"] = _clamped_float(normalized.get("ad_noise_multiplier", 1.0), 1.0, minimum=0.5, maximum=1.5)
    normalized["ad_restore_face"] = _bool_value(normalized.get("ad_restore_face"), False)
    normalized["ad_controlnet_model"] = str(normalized.get("ad_controlnet_model") or "None")
    normalized["ad_controlnet_module"] = str(normalized.get("ad_controlnet_module") or "None")
    normalized["ad_controlnet_weight"] = _clamped_float(normalized.get("ad_controlnet_weight", 1.0), 1.0, minimum=0.0, maximum=1.0)
    normalized["ad_controlnet_guidance_start_end"] = [
        _clamped_float(guidance_start_raw, 0.0, minimum=0.0, maximum=1.0),
        _clamped_float(guidance_end_raw, 1.0, minimum=0.0, maximum=1.0),
    ]
    normalized["is_api"] = True
    return normalized


def adetailer_state_payload(
    *,
    enabled: object,
    skip_img2img: object,
    args: object,
    mode: object = "",
    include_empty_units: bool = False,
) -> dict[str, Any]:
    units = _normalized_units(args)
    if not units and include_empty_units:
        units = [adetailer_default_args(ad_tab_enable=index == 0) for index in range(ADETAILER_STATE_UNIT_COUNT)]
    payload: dict[str, Any] = {
        "schema": ADETAILER_STATE_SCHEMA_VERSION,
        "extension": ADETAILER_EXTENSION_DIRNAME,
        "version": adetailer_version(),
        "enabled": _bool_value(enabled, False),
        "skip_img2img": _bool_value(skip_img2img, False),
        "mode": str(mode or ""),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if units:
        payload["units"] = units[:ADETAILER_STATE_UNIT_COUNT]
    return payload


def adetailer_load_state() -> dict[str, Any]:
    path = adetailer_state_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    units = _normalized_units(data.get("units"))
    result = {
        "schema": ADETAILER_STATE_SCHEMA_VERSION,
        "extension": str(data.get("extension") or ADETAILER_EXTENSION_DIRNAME),
        "version": str(data.get("version") or ""),
        "enabled": _bool_value(data.get("enabled"), False),
        "skip_img2img": _bool_value(data.get("skip_img2img"), False),
        "mode": str(data.get("mode") or ""),
        "updated_at": str(data.get("updated_at") or ""),
    }
    if units:
        result["units"] = units[:ADETAILER_STATE_UNIT_COUNT]
    return result


def adetailer_save_state(
    *,
    enabled: object,
    skip_img2img: object,
    args: object,
    mode: object = "",
) -> Path:
    units = _normalized_units(args)
    if not units:
        existing_units = adetailer_load_state().get("units")
        if isinstance(existing_units, list):
            units = _normalized_units(existing_units)
    payload = adetailer_state_payload(
        enabled=enabled,
        skip_img2img=skip_img2img,
        args=units,
        mode=mode,
    )
    path = adetailer_state_path(create_parent=True)
    _write_json_file(path, payload)
    return path


def adetailer_save_request_state(request: object) -> Path:
    return adetailer_save_state(
        enabled=bool(getattr(request, "adetailer_enabled", False)),
        skip_img2img=bool(getattr(request, "adetailer_skip_img2img", False)),
        args=getattr(request, "adetailer_args", []) or [],
        mode=str(getattr(request, "mode", "") or ""),
    )


def adetailer_reset_state() -> bool:
    path = adetailer_state_path()
    if not path.exists():
        return False
    try:
        path.unlink()
    except OSError:
        return False
    return True


def adetailer_write_image_sidecars(image_paths: list[str] | tuple[str, ...], request: object) -> list[str]:
    if not bool(getattr(request, "adetailer_enabled", False)):
        return []
    args = getattr(request, "adetailer_args", []) or []
    if not _normalized_units(args):
        return []
    payload = adetailer_state_payload(
        enabled=True,
        skip_img2img=bool(getattr(request, "adetailer_skip_img2img", False)),
        args=args,
        mode=str(getattr(request, "mode", "") or ""),
    )
    written: list[str] = []
    for item in list(image_paths or []):
        path = Path(str(item))
        if path.suffix.lower() not in ADETAILER_IMAGE_SUFFIXES or not path.exists():
            continue
        sidecar = adetailer_sidecar_path(path)
        _write_json_file(sidecar, payload)
        written.append(str(sidecar))
    return written


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


def _bool_value(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    return bool(default)


def _clamped_int(value: object, default: int, *, minimum: int, maximum: int) -> int:
    try:
        result = int(float(str(value).strip())) if value not in (None, "") else int(default)
    except Exception:
        result = int(default)
    return max(minimum, min(maximum, result))


def _clamped_float(value: object, default: float, *, minimum: float, maximum: float) -> float:
    try:
        result = float(value) if value not in (None, "") else float(default)
    except Exception:
        result = float(default)
    return max(minimum, min(maximum, result))


def _normalized_units(args: object) -> list[dict[str, Any]]:
    if isinstance(args, dict):
        items = [args]
    elif isinstance(args, (list, tuple)):
        items = [item for item in args if isinstance(item, dict)]
    else:
        items = []
    return [adetailer_normalized_args(item) for item in items]


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


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
