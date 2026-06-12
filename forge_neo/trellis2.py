from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
EXTENSION_DIR = ROOT / "forge_neo" / "webui" / "extensions" / "sd-webui-trellis2"
SCRIPTS_DIR = EXTENSION_DIR / "scripts"
TRELLIS2_ROOT = EXTENSION_DIR / "TRELLIS.2"
NVDIFFREC_DIR = EXTENSION_DIR / "nvdiffrec"
OUTPUT_DIR = EXTENSION_DIR / "outputs"
MODEL_DIR = ROOT / "models" / "trellis2" / "TRELLIS.2-4B"


def _dependency_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def trellis2_defaults() -> dict[str, Any]:
    return {
        "seed": 42,
        "randomize_seed": False,
        "guidance_scale": 5.0,
        "steps": 50,
        "octree_resolution": "1024",
        "simplify_ratio": 0.9,
        "texture_resolution": 2048,
        "env_map": "none",
        "use_flash_attn": _dependency_available("flash_attn"),
    }


def trellis2_status() -> dict[str, Any]:
    dependencies = {
        "torch": _dependency_available("torch"),
        "transformers": _dependency_available("transformers"),
        "diffusers": _dependency_available("diffusers"),
        "huggingface_hub": _dependency_available("huggingface_hub"),
        "flash_attn": _dependency_available("flash_attn"),
        "nvdiffrast": _dependency_available("nvdiffrast"),
        "nvdiffrec": _dependency_available("nvdiffrec") or NVDIFFREC_DIR.is_dir(),
        "cumesh": _dependency_available("cumesh"),
        "flex_gemm": _dependency_available("flex_gemm"),
        "utils3d": _dependency_available("utils3d"),
    }
    return {
        "extension_dir": str(EXTENSION_DIR),
        "source_root": str(TRELLIS2_ROOT),
        "source_available": TRELLIS2_ROOT.is_dir(),
        "script": str(SCRIPTS_DIR / "trellis2_script.py"),
        "script_exists": (SCRIPTS_DIR / "trellis2_script.py").is_file(),
        "model_dir": str(MODEL_DIR),
        "pipeline_config": str(MODEL_DIR / "pipeline.json"),
        "pipeline_config_exists": (MODEL_DIR / "pipeline.json").is_file(),
        "output_dir": str(OUTPUT_DIR),
        "dependencies": dependencies,
        "defaults": trellis2_defaults(),
    }


def _source_module():
    module_path = SCRIPTS_DIR / "trellis2_script.py"
    if not module_path.is_file():
        raise FileNotFoundError(f"TRELLIS.2 source script is missing: {module_path}")
    cache_key = "forge_neo_trellis2_source_script"
    if cache_key in sys.modules:
        return sys.modules[cache_key]
    spec = importlib.util.spec_from_file_location(cache_key, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load TRELLIS.2 source script: {module_path}")
    module = importlib.util.module_from_spec(spec)
    added_paths: list[str] = []
    for path in (str(EXTENSION_DIR), str(SCRIPTS_DIR), str(TRELLIS2_ROOT), str(NVDIFFREC_DIR)):
        if Path(path).exists() and path not in sys.path:
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
        for key in ("image", "background", "composite"):
            image = _image_from_value(value.get(key))
            if image is not None:
                return image
        for key in ("name", "path", "file"):
            path = value.get(key)
            if isinstance(path, str) and Path(path).is_file():
                return Image.open(path)
    if isinstance(value, str) and Path(value).is_file():
        return Image.open(value)
    return None


def generate_trellis2_3d(
    image: object,
    seed: object = 42,
    randomize_seed: object = False,
    guidance_scale: object = 5.0,
    steps: object = 50,
    octree_resolution: object = "1024",
    simplify_ratio: object = 0.9,
    texture_resolution: object = 2048,
    env_map: object = "none",
    use_flash_attn: object = False,
) -> dict[str, Any]:
    source_image = _image_from_value(image)
    if source_image is None:
        return {"ok": False, "message": "Image is required.", "model": None, "preview": None}
    try:
        module = _source_module()
    except Exception as exc:
        return {"ok": False, "message": f"TRELLIS.2 source is not available: {exc}", "model": None, "preview": None}
    env_map_label = {"none": "无", "forest": "森林", "sunset": "日落"}.get(str(env_map or "none"), str(env_map or "无"))
    try:
        status, model_path, preview = module.generate_3d_from_image(
            source_image,
            int(float(str(seed or 42))),
            bool(randomize_seed),
            float(guidance_scale or 5.0),
            int(float(str(steps or 50))),
            str(octree_resolution or "1024"),
            float(simplify_ratio or 0.9),
            int(float(str(texture_resolution or 2048))),
            env_map_label,
            bool(use_flash_attn),
        )
    except Exception as exc:
        return {"ok": False, "message": f"TRELLIS.2 generation failed: {exc}", "model": None, "preview": None}
    return {
        "ok": bool(model_path),
        "message": str(status or ""),
        "model": model_path,
        "preview": preview,
        "output_dir": str(OUTPUT_DIR),
    }
