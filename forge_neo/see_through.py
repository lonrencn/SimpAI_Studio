from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
EXTENSION_DIR = ROOT / "forge_neo" / "webui" / "extensions" / "sd-webui-see-through"
SEE_THROUGH_ROOT = EXTENSION_DIR / "see-through"
WORKSPACE_DIR = SEE_THROUGH_ROOT / "workspace"
TEMP_DIR = WORKSPACE_DIR / "temp"
LAYER_OUTPUT_DIR = WORKSPACE_DIR / "layerdiff_output"


@dataclass
class SeeThroughCommand:
    command: list[str]
    cwd: str
    input_path: str
    output_dir: str


def see_through_defaults() -> dict[str, Any]:
    return {
        "resolution": 1024,
        "steps": 30,
        "seed": -1,
        "save_psd": True,
        "quantization": "nf4",
        "lr_split": False,
        "cache_tag_embeds": True,
        "timeout": 1800,
    }


def see_through_status() -> dict[str, Any]:
    inference_script = SEE_THROUGH_ROOT / "inference" / "scripts" / "inference_psd_optimized.py"
    scene_script = SEE_THROUGH_ROOT / "inference" / "scripts" / "scene_segmenter.py"
    return {
        "extension_dir": str(EXTENSION_DIR),
        "source_root": str(SEE_THROUGH_ROOT),
        "workspace_dir": str(WORKSPACE_DIR),
        "output_dir": str(LAYER_OUTPUT_DIR),
        "source_available": SEE_THROUGH_ROOT.is_dir(),
        "inference_script": str(inference_script),
        "inference_script_exists": inference_script.is_file(),
        "scene_script": str(scene_script),
        "scene_script_exists": scene_script.is_file(),
        "defaults": see_through_defaults(),
    }


def _image_from_value(image: object) -> Image.Image | None:
    if isinstance(image, Image.Image):
        return image
    if isinstance(image, dict):
        for key in ("name", "path", "file"):
            value = image.get(key)
            if isinstance(value, str) and Path(value).is_file():
                return Image.open(value)
    if isinstance(image, str) and Path(image).is_file():
        return Image.open(image)
    return None


def _save_input_image(image: object) -> str:
    resolved = _image_from_value(image)
    if resolved is None:
        return ""
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    path = TEMP_DIR / f"forge_neo_input_{int(time.time() * 1000)}.png"
    close_after = resolved is not image
    try:
        resolved.convert("RGB").save(path, "PNG")
    finally:
        if close_after:
            try:
                resolved.close()
            except Exception:
                pass
    return str(path)


def build_see_through_command(
    image: object,
    *,
    save_psd: object = True,
    resolution: object = 1024,
    steps: object = 30,
    seed: object = -1,
    quantization: object = "nf4",
    lr_split: object = False,
    cache_tag_embeds: object = True,
) -> SeeThroughCommand:
    input_path = _save_input_image(image)
    if not input_path:
        raise ValueError("Image is required.")
    script = SEE_THROUGH_ROOT / "inference" / "scripts" / "inference_psd_optimized.py"
    if not script.is_file():
        raise FileNotFoundError(f"See-Through inference script is missing: {script}")
    try:
        resolution_value = int(float(str(resolution)))
    except Exception:
        resolution_value = 1024
    try:
        steps_value = int(float(str(steps)))
    except Exception:
        steps_value = 30
    try:
        seed_value = int(float(str(seed)))
    except Exception:
        seed_value = -1
    quant_mode = "nf4" if str(quantization or "nf4").lower() == "nf4" else "none"
    command = [
        sys.executable,
        str(script),
        "--srcp",
        input_path,
        "--resolution",
        str(max(512, min(resolution_value, 1536))),
        "--num_inference_steps",
        str(max(10, min(steps_value, 50))),
        "--seed",
        str(seed_value),
        "--quant_mode",
        quant_mode,
    ]
    if bool(save_psd):
        command.append("--save_to_psd")
    if bool(lr_split):
        command.append("--tblr_split")
    if bool(cache_tag_embeds):
        command.append("--cache_tag_embeds")
    LAYER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return SeeThroughCommand(command=command, cwd=str(SEE_THROUGH_ROOT), input_path=input_path, output_dir=str(LAYER_OUTPUT_DIR))


def run_see_through(
    image: object,
    *,
    save_psd: object = True,
    resolution: object = 1024,
    steps: object = 30,
    seed: object = -1,
    quantization: object = "nf4",
    lr_split: object = False,
    cache_tag_embeds: object = True,
    timeout: object = 1800,
) -> dict[str, Any]:
    try:
        command = build_see_through_command(
            image,
            save_psd=save_psd,
            resolution=resolution,
            steps=steps,
            seed=seed,
            quantization=quantization,
            lr_split=lr_split,
            cache_tag_embeds=cache_tag_embeds,
        )
    except Exception as exc:
        return {"ok": False, "message": str(exc), "output": "", "command": []}
    try:
        timeout_value = max(30.0, float(timeout or 1800))
    except Exception:
        timeout_value = 1800.0
    try:
        result = subprocess.run(
            command.command,
            cwd=command.cwd,
            capture_output=True,
            text=True,
            timeout=timeout_value,
            encoding="utf-8",
            errors="ignore",
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "message": f"See-Through timed out after {int(timeout_value)} seconds.",
            "output": str(exc.stdout or ""),
            "command": command.command,
            "output_dir": command.output_dir,
        }
    except Exception as exc:
        return {"ok": False, "message": str(exc), "output": "", "command": command.command, "output_dir": command.output_dir}
    output = "\n".join(part for part in [result.stdout, result.stderr] if part)
    return {
        "ok": result.returncode == 0,
        "message": "See-Through finished." if result.returncode == 0 else f"See-Through failed with exit code {result.returncode}.",
        "output": output,
        "command": command.command,
        "output_dir": command.output_dir,
    }
