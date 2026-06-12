import html as _html
import math
import re


_PROGRESS_STEP_RE = re.compile(r"(?:采样步数|Sampling\s+steps?|Steps?)\s*[:：]?\s*(\d+)\s*/\s*(\d+)", re.I)
_PROGRESS_IMAGE_RE = re.compile(r"(?:图片|Image)\s*[:：]?\s*(\d+)\s*/\s*(\d+)", re.I)
_PROGRESS_ETA_RE = re.compile(
    r"(?:ETA|预计剩余|剩余)\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?\s*(?:s|sec|secs|second|seconds|秒|m|min|mins|minute|minutes|分钟|h|hr|hrs|hour|hours|小时)?(?:\s+[0-9]+(?:\.[0-9]+)?\s*(?:s|秒))?)",
    re.I,
)


def normalize_progress_number(number):
    try:
        value = float(number)
    except (TypeError, ValueError):
        value = 0.0
    if not math.isfinite(value):
        value = 0.0
    return max(0.0, min(100.0, value))


def parse_generation_progress_text(text):
    value = str(text or "")
    status = {
        "step": None,
        "total_steps": None,
        "image_index": None,
        "image_count": None,
        "eta_text": None,
    }

    step_match = _PROGRESS_STEP_RE.search(value)
    if step_match:
        step = int(step_match.group(1))
        total_steps = max(1, int(step_match.group(2)))
        status["step"] = max(0, step)
        status["total_steps"] = max(status["step"], total_steps)

    image_match = _PROGRESS_IMAGE_RE.search(value)
    if image_match:
        image_index = int(image_match.group(1))
        image_count = max(1, int(image_match.group(2)))
        status["image_index"] = max(1, image_index)
        status["image_count"] = max(status["image_index"], image_count)

    eta_match = _PROGRESS_ETA_RE.search(value)
    if eta_match:
        eta_text = eta_match.group(1).strip()
        if eta_text:
            status["eta_text"] = f"ETA:{eta_text}"

    return status


def progress_number_from_text(number, text):
    status = parse_generation_progress_text(text)
    step = status.get("step")
    total_steps = status.get("total_steps")
    if step is not None and total_steps:
        return normalize_progress_number((float(step) / float(total_steps)) * 100.0)
    return normalize_progress_number(number)


def make_progress_html(number, text, eta_text=None):
    progress_value = progress_number_from_text(number, text)
    if eta_text is None:
        eta_text = parse_generation_progress_text(text).get("eta_text")
    progress_style_value = f"{progress_value:.4f}%"
    progress_label = f"{progress_value:.0f}%"
    moving_label = progress_label
    if eta_text:
        moving_label = f"{progress_label} {str(eta_text).strip()}"

    safe_text = _html.escape(str(text or ""), quote=True)
    safe_label = _html.escape(moving_label, quote=True)
    aria_value = f"{progress_value:.0f}"

    return f'''
<div class="loader-container sai-generation-progress" style="--sai-progress: {progress_style_value};">
  <div class="loader"></div>
  <div class="progress-container sai-progress-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="{aria_value}" aria-label="Generation progress">
    <div class="sai-progress-fill"></div>
    <div class="sai-progress-marker"><span>{safe_label}</span></div>
  </div>
  <span class="sai-progress-status" title="{safe_text}">{safe_text}</span>
</div>
'''
