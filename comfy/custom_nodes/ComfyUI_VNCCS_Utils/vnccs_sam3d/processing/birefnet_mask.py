"""Auto-mask fallback using BiRefNet.

Used when the ComfyUI node graph does not provide a MASK input.
The model snapshot is stored under <ComfyUI>/models/birefnet/BiRefNet_lite.
"""

import hashlib
import os
import threading

import cv2
import numpy as np
from PIL import Image
import requests

import folder_paths

from .. import progress

_MODEL_SOURCE = "ModelScope windecay/SimpAI_dev SimpleModels/birefnet/BiRefNet_lite"
_MODEL_BASE_URL = "https://www.modelscope.cn/models/windecay/SimpAI_dev/resolve/master/SimpleModels/birefnet/BiRefNet_lite"
_MODEL_DIR = os.path.join(folder_paths.models_dir, "birefnet", "BiRefNet_lite")
_MODEL_FILES = (
    ("BiRefNet_config.py", 298, "e7b8c2a74f6cea6a59553d517f71d47f2c1d90e670a13416af17c25fe2f3dc52"),
    ("birefnet.py", 92134, "af8568b5be406bf4d2a68a7ed6d72e40f73b37a1fb6fc9ebd71b5b3cbcd069c9"),
    ("config.json", 410, "9dc8614fccddd40c601aeadc69b9db6dd820598179b2a2198492e6ffa016a824"),
    ("model.safetensors", 177634392, "4417d89795250e698c3cb0ae8df15743810065f646f48a694fdfa7ca052d0815"),
)
_MODEL_LOCK = threading.Lock()
_MODEL = None
_DEVICE = None


def _file_size_matches(path, expected_size):
    return os.path.isfile(path) and os.path.getsize(path) == int(expected_size)


def _calculate_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_complete():
    return all(
        _file_size_matches(os.path.join(_MODEL_DIR, rel_path), expected_size)
        for rel_path, expected_size, _sha256 in _MODEL_FILES
    )


def _download_model_file(rel_path, expected_size, expected_sha256):
    url = f"{_MODEL_BASE_URL}/{rel_path}"
    final_path = os.path.join(_MODEL_DIR, rel_path)
    partial_path = final_path + ".partial"
    os.makedirs(os.path.dirname(final_path), exist_ok=True)

    if _file_size_matches(final_path, expected_size):
        return

    if os.path.exists(partial_path):
        os.remove(partial_path)

    response = requests.get(url, stream=True, timeout=(30, 120))
    response.raise_for_status()
    with open(partial_path, "wb") as file:
        for chunk in response.iter_content(1024 * 1024):
            if chunk:
                file.write(chunk)

    downloaded_size = os.path.getsize(partial_path)
    if downloaded_size != int(expected_size):
        os.remove(partial_path)
        raise RuntimeError(
            f"[SAM3DBody] BiRefNet file size mismatch for {rel_path}: "
            f"expected {expected_size}, got {downloaded_size}"
        )

    downloaded_sha256 = _calculate_sha256(partial_path)
    if downloaded_sha256.lower() != expected_sha256.lower():
        os.remove(partial_path)
        raise RuntimeError(
            f"[SAM3DBody] BiRefNet SHA256 mismatch for {rel_path}: "
            f"expected {expected_sha256}, got {downloaded_sha256}"
        )

    os.replace(partial_path, final_path)


def _ensure_snapshot():
    os.makedirs(_MODEL_DIR, exist_ok=True)
    if _snapshot_complete():
        return _MODEL_DIR

    print(f"[SAM3DBody] BiRefNet model not found. Downloading from {_MODEL_SOURCE} to {_MODEL_DIR} ...")
    progress.update("Step 3/6: Downloading BiRefNet mask model. This is only needed once.", 38)
    with progress.download_phase("Step 3/6: Downloading BiRefNet mask model files...", 38, 12):
        for rel_path, expected_size, expected_sha256 in _MODEL_FILES:
            _download_model_file(rel_path, expected_size, expected_sha256)
    if not _snapshot_complete():
        raise RuntimeError(f"[SAM3DBody] BiRefNet download completed but required files are missing under {_MODEL_DIR}")
    print("[SAM3DBody] BiRefNet model download complete.")
    progress.update("Step 3/6: BiRefNet mask model download complete.", 50)
    return _MODEL_DIR


def _load_model():
    global _MODEL, _DEVICE
    with _MODEL_LOCK:
        if _MODEL is not None:
            return _MODEL, _DEVICE or "cpu"

        import torch
        from transformers import AutoModelForImageSegmentation

        torch.set_float32_matmul_precision("high")
        model_dir = _ensure_snapshot()
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[SAM3DBody] Loading BiRefNet from {model_dir} on {device}")
        progress.update(f"Step 3/6: Loading BiRefNet mask model on {device.upper()}...", 52)
        model = AutoModelForImageSegmentation.from_pretrained(
            model_dir,
            trust_remote_code=True,
            local_files_only=True,
        )
        model.to(device)
        model.eval()
        if device == "cuda":
            model.half()

        _MODEL = model
        _DEVICE = device
        return model, device


def _bbox_from_mask(mask_2d):
    rows = np.any(mask_2d > 0, axis=1)
    cols = np.any(mask_2d > 0, axis=0)
    if not rows.any() or not cols.any():
        return None
    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]
    return np.array([[cmin, rmin, cmax, rmax]], dtype=np.float32)


def _largest_component(mask_2d):
    num, labels, stats, _ = cv2.connectedComponentsWithStats(mask_2d.astype(np.uint8), connectivity=8)
    if num <= 1:
        return mask_2d.astype(np.uint8)
    best = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return (labels == best).astype(np.uint8)


def auto_mask_bgr(img_bgr, confidence_threshold=0.5):
    import torch
    from torchvision import transforms

    if img_bgr is None or img_bgr.size == 0:
        raise RuntimeError("[SAM3DBody] BiRefNet received an empty image")

    progress.update("Step 3/6: Segmenting the person and finding the body bounds...", 40)
    model, device = _load_model()
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    pil_image = Image.fromarray(rgb)
    width, height = pil_image.size

    tfm = transforms.Compose([
        transforms.Resize((1024, 1024)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    input_tensor = tfm(pil_image).unsqueeze(0).to(device)
    if device == "cuda":
        input_tensor = input_tensor.half()

    with torch.no_grad():
        pred = model(input_tensor)[-1].sigmoid().float().cpu().numpy()[0, 0]

    mask_img = Image.fromarray(np.clip(pred * 255.0, 0.0, 255.0).astype(np.uint8), mode="L")
    score_map = np.asarray(mask_img.resize((width, height), Image.BILINEAR), dtype=np.float32) / 255.0
    mask = (score_map >= float(confidence_threshold)).astype(np.uint8)
    if not mask.any():
        raise RuntimeError("[SAM3DBody] BiRefNet produced an empty mask")
    mask = _largest_component(mask)
    bbox = _bbox_from_mask(mask)
    if bbox is None:
        raise RuntimeError("[SAM3DBody] BiRefNet mask bbox is empty")
    progress.update("Step 3/6: Segmentation complete. Body bounds detected.", 54)
    return mask.astype(np.uint8), bbox
