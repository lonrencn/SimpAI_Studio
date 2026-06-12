import base64
import io
import json
import os
from typing import Any
from typing import Iterable
from typing import Tuple
import uuid

import numpy as np
from PIL import Image

from enhanced import sam3_comfy31

SAM3_CHECKPOINT_URL = sam3_comfy31.SAM31_CHECKPOINT_URL
SAM3_CHECKPOINT_FILENAME = sam3_comfy31.SAM31_CHECKPOINT_FILENAME


def _repo_root() -> str:
    here = os.path.abspath(os.path.dirname(__file__))
    return os.path.abspath(os.path.join(here, ".."))


def _resolve_sam3_checkpoint(model_path: str | None, *, allow_download: bool) -> str | None:
    try:
        return sam3_comfy31.resolve_sam31_checkpoint(model_path, allow_download=allow_download)
    except FileNotFoundError:
        return None


def ensure_sam3_image_model_loaded(*, model_path: str | None = None) -> None:
    sam3_comfy31.ensure_sam31_loaded(model_path)


def offload_sam3_image_model_to_cpu() -> None:
    sam3_comfy31.unload_sam31()


def _normalize_points(points: Iterable[dict[str, Any]] | None) -> list[list[float]]:
    out: list[list[float]] = []
    if not points:
        return out
    for p in points:
        if not isinstance(p, dict):
            continue
        x = float(p.get("x", 0.0))
        y = float(p.get("y", 0.0))
        x = max(0.0, min(1.0, x))
        y = max(0.0, min(1.0, y))
        out.append([x, y])
    return out


def run_sam3_image_mask_from_points(
    image_rgb: Image.Image,
    *,
    positive_points: Iterable[dict[str, Any]] | None,
    negative_points: Iterable[dict[str, Any]] | None,
    threshold: float = 0.3,
    mask_threshold: float = 0.4,
    model_path: str | None = None,
) -> np.ndarray:
    return sam3_comfy31.image_mask_from_points(
        image_rgb,
        positive_points=positive_points,
        negative_points=negative_points,
        mask_threshold=0.0,
        refine_iterations=2,
        model_path=model_path,
    )


def decode_data_url_to_pil(data_url: str) -> Tuple[Image.Image, Image.Image | None]:
    if not data_url or "," not in str(data_url):
        raise ValueError("Invalid image data URL")

    raw_b64 = str(data_url).split(",", 1)[1]
    img_data = base64.b64decode(raw_b64)
    img = Image.open(io.BytesIO(img_data))

    alpha = None
    if img.mode == "RGBA":
        alpha = img.split()[3]
        img = img.convert("RGB")
    elif img.mode != "RGB":
        img = img.convert("RGB")

    return img, alpha


def pil_to_data_url(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def mask_u8_to_data_url(mask_u8: np.ndarray) -> str:
    if mask_u8.ndim != 2:
        raise ValueError("mask_u8 must be 2D")
    img = Image.fromarray(mask_u8.astype(np.uint8), mode="L")
    return pil_to_data_url(img)


def fill_mask_holes(mask_u8: np.ndarray) -> np.ndarray:
    if mask_u8.ndim != 2:
        return mask_u8
    try:
        import cv2  # noqa: E402

        m = (mask_u8 > 127).astype(np.uint8) * 255
        inv = 255 - m
        padded = np.pad(inv, ((1, 1), (1, 1)), mode="constant", constant_values=255)
        h, w = padded.shape
        flood_mask = np.zeros((h + 2, w + 2), np.uint8)
        cv2.floodFill(padded, flood_mask, (0, 0), 0)
        holes = padded[1:-1, 1:-1]
        filled = np.clip(m + holes, 0, 255).astype(np.uint8)
        return filled
    except Exception:
        return mask_u8


def close_mask(mask_u8: np.ndarray, *, radius: int) -> np.ndarray:
    if mask_u8.ndim != 2:
        return mask_u8
    r = int(radius)
    if r <= 0:
        return mask_u8
    try:
        import cv2  # noqa: E402

        m = (mask_u8 > 127).astype(np.uint8) * 255
        k = 2 * r + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        closed = cv2.morphologyEx(m, cv2.MORPH_CLOSE, kernel)
        return closed.astype(np.uint8)
    except Exception:
        return mask_u8


def compute_point_hits(
    mask_u8: np.ndarray,
    *,
    positive_points: Iterable[dict[str, Any]] | None,
    negative_points: Iterable[dict[str, Any]] | None,
    radius: int = 2,
) -> tuple[list[bool], list[bool]]:
    if mask_u8.ndim != 2:
        return [], []

    h, w = mask_u8.shape
    r = max(0, int(radius))
    pos = _normalize_points(positive_points)
    neg = _normalize_points(negative_points)

    def _hit_foreground(x01: float, y01: float) -> bool:
        x = int(round(float(x01) * max(1, w - 1)))
        y = int(round(float(y01) * max(1, h - 1)))
        x0 = max(0, x - r)
        x1 = min(w, x + r + 1)
        y0 = max(0, y - r)
        y1 = min(h, y + r + 1)
        patch = mask_u8[y0:y1, x0:x1]
        return bool(patch.size > 0 and int(patch.max()) > 127)

    def _hit_background(x01: float, y01: float) -> bool:
        x = int(round(float(x01) * max(1, w - 1)))
        y = int(round(float(y01) * max(1, h - 1)))
        x0 = max(0, x - r)
        x1 = min(w, x + r + 1)
        y0 = max(0, y - r)
        y1 = min(h, y + r + 1)
        patch = mask_u8[y0:y1, x0:x1]
        return bool(patch.size > 0 and int(patch.max()) <= 127)

    pos_hit = [_hit_foreground(x, y) for x, y in pos]
    neg_hit = [_hit_background(x, y) for x, y in neg]
    return pos_hit, neg_hit


def apply_mask_to_image(
    image_rgb: Image.Image, mask_u8: np.ndarray, *, original_alpha: Image.Image | None
) -> Image.Image:
    if mask_u8.ndim != 2:
        raise ValueError("mask_u8 must be 2D")
    if image_rgb.mode != "RGB":
        image_rgb = image_rgb.convert("RGB")

    h, w = mask_u8.shape
    if (w, h) != image_rgb.size:
        mask_img = Image.fromarray(mask_u8.astype(np.uint8), mode="L").resize(
            image_rgb.size, resample=Image.NEAREST
        )
        mask_u8 = np.array(mask_img, dtype=np.uint8)

    out = image_rgb.convert("RGBA")
    mask_alpha = mask_u8.astype(np.uint8)

    if original_alpha is not None:
        oa = np.array(original_alpha.resize(out.size, resample=Image.NEAREST), dtype=np.uint8)
        mask_alpha = np.minimum(mask_alpha, oa).astype(np.uint8)

    out.putalpha(Image.fromarray(mask_alpha, mode="L"))
    return out


def build_sam3_image_response(
    *,
    image_data_url: str,
    positive_points: Iterable[dict[str, Any]] | None,
    negative_points: Iterable[dict[str, Any]] | None,
    threshold: float = 0.3,
    fill_holes: bool = False,
    mask_threshold: float = 0.4,
    close_radius: int = 1,
) -> dict[str, Any]:
    image_rgb, original_alpha = decode_data_url_to_pil(image_data_url)
    mask_u8 = run_sam3_image_mask_from_points(
        image_rgb,
        positive_points=positive_points,
        negative_points=negative_points,
        threshold=threshold,
        mask_threshold=mask_threshold,
    )
    mask_u8 = close_mask(mask_u8, radius=int(close_radius))
    if bool(fill_holes):
        mask_u8 = fill_mask_holes(mask_u8)
    cutout = apply_mask_to_image(image_rgb, mask_u8, original_alpha=original_alpha)
    pos_hit, neg_hit = compute_point_hits(
        mask_u8,
        positive_points=positive_points,
        negative_points=negative_points,
        radius=2,
    )

    return {
        "mask": mask_u8_to_data_url(mask_u8),
        "cutout_image": pil_to_data_url(cutout),
        "width": int(image_rgb.width),
        "height": int(image_rgb.height),
        "pos_hit": pos_hit,
        "neg_hit": neg_hit,
        "id": uuid.uuid4().hex,
    }
