from __future__ import annotations

import base64
import io
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image


OLLAMA_DEFAULT_HOST = "http://localhost:11434"
VISION_MODEL_CHOICES = [
    "qwen3.5:9b",
    "qwen3.5:4b",
    "qwen3.5:2b",
    "qwen3-vl:8b",
    "qwen3-vl:4b",
    "qwen3-vl:2b",
]
LANGUAGE_MODEL_CHOICES = ["qwen3:latest", "qwen3.5:4b", "qwen3.5:9b"]


def qwen_vision_chat_defaults() -> dict[str, Any]:
    return {
        "ollama_host": OLLAMA_DEFAULT_HOST,
        "vision_models": list(VISION_MODEL_CHOICES),
        "language_models": list(LANGUAGE_MODEL_CHOICES),
        "default_vision_model": "qwen3.5:4b",
        "default_language_model": "qwen3:latest",
        "timeout": 120,
    }


def _normal_host(host: object) -> str:
    value = str(host or OLLAMA_DEFAULT_HOST).strip() or OLLAMA_DEFAULT_HOST
    return value.rstrip("/")


def _image_to_base64(image: object) -> str:
    if image is None:
        return ""
    if isinstance(image, Image.Image):
        resolved = image
    elif isinstance(image, dict):
        path = next((image.get(key) for key in ("name", "path", "file") if image.get(key)), "")
        resolved = Image.open(path) if path and Path(path).is_file() else None
    elif isinstance(image, str) and Path(image).is_file():
        resolved = Image.open(image)
    else:
        resolved = None
    if resolved is None:
        return ""
    close_after = resolved is not image
    try:
        with io.BytesIO() as buffer:
            resolved.convert("RGB").save(buffer, "PNG")
            return base64.b64encode(buffer.getvalue()).decode("ascii")
    finally:
        if close_after:
            try:
                resolved.close()
            except Exception:
                pass


def qwen_vision_chat_payload(
    *,
    prompt: object,
    model_type: object,
    vision_model: object,
    language_model: object,
    image: object = None,
    ollama_host: object = None,
) -> dict[str, Any]:
    text = str(prompt or "").strip()
    if not text:
        return {"ok": False, "message": "Prompt is empty.", "content": ""}
    is_vision = str(model_type or "vision").strip().lower() == "vision"
    model = str(vision_model if is_vision else language_model or "").strip()
    if not model:
        return {"ok": False, "message": "Model is empty.", "content": ""}
    message: dict[str, Any] = {"role": "user", "content": text}
    image_data = _image_to_base64(image) if is_vision else ""
    if image_data:
        message["images"] = [image_data]
    return {
        "ok": True,
        "host": _normal_host(ollama_host),
        "endpoint": f"{_normal_host(ollama_host)}/api/chat",
        "payload": {"model": model, "messages": [message], "stream": False},
        "uses_image": bool(image_data),
    }


def qwen_vision_chat_request(
    *,
    prompt: object,
    model_type: object,
    vision_model: object,
    language_model: object,
    image: object = None,
    ollama_host: object = None,
    timeout: object = None,
) -> dict[str, Any]:
    prepared = qwen_vision_chat_payload(
        prompt=prompt,
        model_type=model_type,
        vision_model=vision_model,
        language_model=language_model,
        image=image,
        ollama_host=ollama_host,
    )
    if not prepared.get("ok"):
        return prepared
    try:
        timeout_value = max(1.0, float(timeout or qwen_vision_chat_defaults()["timeout"]))
    except Exception:
        timeout_value = float(qwen_vision_chat_defaults()["timeout"])
    data = json.dumps(prepared["payload"]).encode("utf-8")
    request = urllib.request.Request(
        str(prepared["endpoint"]),
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_value) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        return {
            "ok": False,
            "message": f"Ollama request failed: {exc}",
            "content": "",
            "endpoint": prepared["endpoint"],
        }
    except Exception as exc:
        return {
            "ok": False,
            "message": f"Ollama response error: {exc}",
            "content": "",
            "endpoint": prepared["endpoint"],
        }
    content = ""
    if isinstance(result, dict):
        message = result.get("message")
        if isinstance(message, dict):
            content = str(message.get("content") or "")
    return {
        "ok": bool(content),
        "message": "ok" if content else "Ollama returned an empty response.",
        "content": content,
        "raw": result,
        "endpoint": prepared["endpoint"],
        "uses_image": prepared.get("uses_image", False),
    }
