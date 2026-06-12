from __future__ import annotations

import importlib.util
import os
import sys
import time
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
EXTENSION_DIR = ROOT / "forge_neo" / "webui" / "extensions" / "sd-webui-sam-matting"
SCRIPTS_DIR = EXTENSION_DIR / "scripts"
SOURCE_WEBUI_ROOT = ROOT / "forge_neo" / "webui"
REMBG_MODEL_DIR = SOURCE_WEBUI_ROOT / "models" / "rembg"
SAM_MODEL_DIR = SOURCE_WEBUI_ROOT / "models" / "sams"
CLEANER_MODEL_DIR = SOURCE_WEBUI_ROOT / "models" / "cleaner"
MATTING_OUTPUT_DIR = SOURCE_WEBUI_ROOT / "outputs" / "image-matting"
SAM_OUTPUT_DIR = SOURCE_WEBUI_ROOT / "outputs" / "segment-anything" / "forge_neo"
CLEANER_OUTPUT_DIR = SOURCE_WEBUI_ROOT / "outputs" / "cleaner"

REMBG_MODELS = {
    "u2net (general)": "u2net",
}
SAM_MODELS = {
    "sam_vit_h_4b8939": "vit_h",
    "sam_vit_l_0b3195": "vit_l",
}


def _dependency_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def sam_matting_defaults() -> dict[str, Any]:
    return {
        "rembg_model": "u2net",
        "background_mode": "transparent",
        "background_color": "#FFFFFF",
        "sam_model": "vit_h",
        "sam_mode": "limited",
        "sam_max_masks": 6,
    }


def sam_matting_status() -> dict[str, Any]:
    dependencies = {
        "rembg": _dependency_available("rembg"),
        "onnxruntime": _dependency_available("onnxruntime"),
        "segment_anything": _dependency_available("segment_anything"),
        "litelama": _dependency_available("litelama"),
        "cv2": _dependency_available("cv2"),
    }
    sam_models = {
        "vit_h": str(SAM_MODEL_DIR / "sam_vit_h_4b8939.pth"),
        "vit_l": str(SAM_MODEL_DIR / "sam_vit_l_0b3195.pth"),
    }
    return {
        "extension_dir": str(EXTENSION_DIR),
        "scripts_dir": str(SCRIPTS_DIR),
        "source_available": EXTENSION_DIR.is_dir(),
        "dependencies": dependencies,
        "sam_model_dir": str(SAM_MODEL_DIR),
        "sam_models": {name: {"path": path, "exists": Path(path).is_file()} for name, path in sam_models.items()},
        "rembg_model_dir": str(REMBG_MODEL_DIR),
        "cleaner_model_dir": str(CLEANER_MODEL_DIR),
        "capabilities": {
            "background_removal": True,
            "sam_auto_segmentation": True,
            "sam_point_segmentation": (SCRIPTS_DIR / "segment_anything_ui.py").is_file(),
            "cleaner": True,
        },
        "output_dirs": {
            "matting": str(MATTING_OUTPUT_DIR),
            "sam": str(SAM_OUTPUT_DIR),
            "cleaner": str(CLEANER_OUTPUT_DIR),
        },
        "defaults": sam_matting_defaults(),
    }


def _source_module(module_name: str):
    if not SCRIPTS_DIR.is_dir():
        raise FileNotFoundError(f"SAM Matting scripts directory is missing: {SCRIPTS_DIR}")
    module_path = SCRIPTS_DIR / f"{module_name}.py"
    if not module_path.is_file():
        raise FileNotFoundError(f"SAM Matting source module is missing: {module_path}")
    cache_key = f"forge_neo_sam_matting_source_{module_name}"
    if cache_key in sys.modules:
        return sys.modules[cache_key]
    spec = importlib.util.spec_from_file_location(cache_key, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load SAM Matting source module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    added_paths: list[str] = []
    for path in (str(EXTENSION_DIR), str(SCRIPTS_DIR)):
        if path not in sys.path:
            sys.path.insert(0, path)
            added_paths.append(path)
    try:
        sys.modules[cache_key] = module
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(cache_key, None)
        raise
    finally:
        for path in added_paths:
            try:
                sys.path.remove(path)
            except ValueError:
                pass
    return module


def _image_from_value(value: object) -> Image.Image | None:
    if isinstance(value, Image.Image):
        return value
    if isinstance(value, dict):
        for key in ("background", "image", "composite"):
            image = _image_from_value(value.get(key))
            if image is not None:
                return image
        for key in ("name", "path", "file"):
            path = value.get(key)
            if isinstance(path, str) and Path(path).is_file():
                return Image.open(path)
    if isinstance(value, (list, tuple)):
        for item in value:
            image = _image_from_value(item)
            if image is not None:
                return image
    if isinstance(value, str) and Path(value).is_file():
        return Image.open(value)
    return None


def _mask_from_editor(value: object) -> Image.Image | None:
    if isinstance(value, dict):
        mask = _image_from_value(value.get("mask"))
        if mask is not None:
            return mask
        layers = value.get("layers")
        if isinstance(layers, list) and layers:
            layer = _image_from_value(layers[-1])
            if layer is not None:
                if layer.mode == "RGBA":
                    return layer.getchannel("A")
                return layer.convert("L")
    return None


def _save_images(images: object, output_dir: Path, prefix: str) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    if images is None:
        return []
    if not isinstance(images, list):
        images = [images]
    saved: list[str] = []
    stamp = int(time.time() * 1000)
    for index, item in enumerate(images, start=1):
        image = _image_from_value(item)
        if image is None:
            continue
        path = output_dir / f"{prefix}_{stamp}_{index}.png"
        close_after = image is not item
        try:
            image.save(path, "PNG")
            saved.append(str(path))
        finally:
            if close_after:
                try:
                    image.close()
                except Exception:
                    pass
    return saved


def _points_from_value(value: object) -> list[list[int]]:
    if not isinstance(value, list):
        return []
    points: list[list[int]] = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        try:
            points.append([int(round(float(item[0]))), int(round(float(item[1])))])
        except Exception:
            continue
    return points


def remove_background(image: object, background_mode: object = "transparent", background_color: object = "#FFFFFF", model_name: object = "u2net") -> dict[str, Any]:
    source = _image_from_value(image)
    if source is None:
        return {"ok": False, "message": "Image is required.", "images": [], "output_dir": str(MATTING_OUTPUT_DIR)}
    try:
        from rembg import new_session, remove
    except Exception as exc:
        return {"ok": False, "message": f"rembg is not available: {exc}", "images": [], "output_dir": str(MATTING_OUTPUT_DIR)}
    REMBG_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    os.environ["U2NET_HOME"] = str(REMBG_MODEL_DIR)
    actual_model = str(model_name or "u2net")
    if actual_model not in set(REMBG_MODELS.values()):
        actual_model = "u2net"
    try:
        session = new_session(actual_model)
        result = remove(source.convert("RGBA"), session=session)
        if str(background_mode or "transparent") != "transparent":
            background = Image.new("RGBA", result.size, str(background_color or "#FFFFFF"))
            background.paste(result, (0, 0), result)
            result = background.convert("RGB")
        saved = _save_images([result], MATTING_OUTPUT_DIR, f"rembg_{actual_model}")
    except Exception as exc:
        return {"ok": False, "message": f"Background removal failed: {exc}", "images": [], "output_dir": str(MATTING_OUTPUT_DIR)}
    return {
        "ok": bool(saved),
        "message": f"Background removal finished. {len(saved)} image(s) saved.",
        "images": saved,
        "output_dir": str(MATTING_OUTPUT_DIR),
    }


def run_sam_auto_segmentation(image: object, model_type: object = "vit_h", mode: object = "limited", max_masks: object = 6) -> dict[str, Any]:
    source = _image_from_value(image)
    if source is None:
        return {"ok": False, "message": "Image is required.", "images": [], "output_dir": str(SAM_OUTPUT_DIR)}
    try:
        import numpy as np

        module = _source_module("segment_anything_ui")
    except Exception as exc:
        return {"ok": False, "message": f"Segment Anything is not available: {exc}", "images": [], "output_dir": str(SAM_OUTPUT_DIR)}
    if not getattr(module, "SAM_AVAILABLE", False):
        return {"ok": False, "message": "segment_anything is not installed.", "images": [], "output_dir": str(SAM_OUTPUT_DIR)}
    actual_model = str(model_type or "vit_h")
    if actual_model not in {"vit_h", "vit_l"}:
        actual_model = "vit_h"
    actual_mode = "all" if str(mode or "limited") == "all" else "limited"
    try:
        limit = max(1, min(int(float(str(max_masks or 6))), 24))
    except Exception:
        limit = 6
    try:
        result_images = module.random_segmentation(np.array(source.convert("RGB")), actual_model, actual_mode, limit)
        saved = _save_images(result_images, SAM_OUTPUT_DIR, f"sam_{actual_model}")
    except Exception as exc:
        return {"ok": False, "message": f"SAM segmentation failed: {exc}", "images": [], "output_dir": str(SAM_OUTPUT_DIR)}
    return {
        "ok": bool(saved),
        "message": f"SAM segmentation finished. {len(saved)} image(s) saved.",
        "images": saved,
        "output_dir": str(SAM_OUTPUT_DIR),
    }


def run_sam_point_segmentation(image: object, points: object, model_type: object = "vit_h") -> dict[str, Any]:
    source = _image_from_value(image)
    point_values = _points_from_value(points)
    if source is None:
        return {"ok": False, "message": "Image is required.", "images": [], "output_dir": str(SAM_OUTPUT_DIR)}
    if not point_values:
        return {"ok": False, "message": "At least one point is required.", "images": [], "output_dir": str(SAM_OUTPUT_DIR)}
    try:
        import numpy as np

        module = _source_module("segment_anything_ui")
    except Exception as exc:
        return {"ok": False, "message": f"Segment Anything is not available: {exc}", "images": [], "output_dir": str(SAM_OUTPUT_DIR)}
    if not getattr(module, "SAM_AVAILABLE", False):
        return {"ok": False, "message": "segment_anything is not installed.", "images": [], "output_dir": str(SAM_OUTPUT_DIR)}
    actual_model = str(model_type or "vit_h")
    if actual_model not in {"vit_h", "vit_l"}:
        actual_model = "vit_h"
    try:
        source_array = np.array(source.convert("RGB"))
        module.original_image = source_array.copy()
        result_images = module.point_segmentation(source_array, point_values, actual_model)
        saved = _save_images(result_images, SAM_OUTPUT_DIR, f"sam_point_{actual_model}")
    except Exception as exc:
        return {"ok": False, "message": f"SAM point segmentation failed: {exc}", "images": [], "output_dir": str(SAM_OUTPUT_DIR)}
    return {
        "ok": bool(saved),
        "message": f"SAM point segmentation finished. {len(saved)} image(s) saved.",
        "images": saved,
        "output_dir": str(SAM_OUTPUT_DIR),
    }


def run_cleaner(image_editor_value: object) -> dict[str, Any]:
    image = _image_from_value(image_editor_value)
    mask = _mask_from_editor(image_editor_value)
    if image is None or mask is None:
        return {"ok": False, "message": "Image and mask are required.", "images": [], "output_dir": str(CLEANER_OUTPUT_DIR)}
    try:
        module = _source_module("cleaner_ui")
    except Exception as exc:
        return {"ok": False, "message": f"LiteLama cleaner is not available: {exc}", "images": [], "output_dir": str(CLEANER_OUTPUT_DIR)}
    if not getattr(module, "CLEANER_AVAILABLE", False):
        return {"ok": False, "message": "litelama is not installed.", "images": [], "output_dir": str(CLEANER_OUTPUT_DIR)}
    try:
        result_images = module.clean_object(image, mask)
        saved = _save_images(result_images, CLEANER_OUTPUT_DIR, "cleaner")
    except Exception as exc:
        return {"ok": False, "message": f"Cleaner failed: {exc}", "images": [], "output_dir": str(CLEANER_OUTPUT_DIR)}
    return {
        "ok": bool(saved),
        "message": f"Cleaner finished. {len(saved)} image(s) saved.",
        "images": saved,
        "output_dir": str(CLEANER_OUTPUT_DIR),
    }
