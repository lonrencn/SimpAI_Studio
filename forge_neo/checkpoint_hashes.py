from __future__ import annotations

import hashlib
import html
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from forge_neo.bootstrap import ensure_config
from forge_neo.i18n import normalize_lang


CHECKPOINT_EXTENSIONS = {
    ".ckpt",
    ".pt",
    ".pth",
    ".safetensors",
    ".gguf",
}


def _text(lang: object | None, en: str, cn: str) -> str:
    return en if normalize_lang(lang) == "en" else cn


def checkpoint_roots() -> list[Path]:
    config = ensure_config()
    roots = []
    for catalog in ("diffusion_models", "checkpoints"):
        for raw in (getattr(config, "model_cata_map", {}) or {}).get(catalog, []) or []:
            path = Path(raw)
            resolved = path.resolve()
            if resolved not in roots:
                roots.append(resolved)
    return roots


def list_checkpoint_files(roots: list[str | Path] | None = None) -> list[Path]:
    candidates = [Path(item).resolve() for item in (roots or checkpoint_roots())]
    files: list[Path] = []
    seen: set[Path] = set()
    for root in candidates:
        if root.is_file():
            iterable = [root]
        elif root.is_dir():
            iterable = (item for item in root.rglob("*") if item.is_file())
        else:
            continue
        for path in iterable:
            if path.suffix.lower() not in CHECKPOINT_EXTENSIONS:
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(resolved)
    return sorted(files, key=lambda item: str(item).lower())


def _display_name(path: Path, roots: list[Path]) -> str:
    for root in roots:
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            continue
    return path.name


def _hash_file(path: Path, roots: list[Path]) -> dict[str, object]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    sha256 = digest.hexdigest()
    return {
        "name": _display_name(path, roots),
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": sha256,
        "short_hash": sha256[:10],
        "status": "calculated",
        "error": "",
    }


def _hash_file_safe(path: Path, roots: list[Path]) -> dict[str, object]:
    try:
        return _hash_file(path, roots)
    except Exception as exc:
        return {
            "name": _display_name(path, roots),
            "path": str(path),
            "size_bytes": 0,
            "sha256": "",
            "short_hash": "",
            "status": "error",
            "error": str(exc),
        }


def _thread_count(value: object) -> int:
    try:
        count = int(value)
    except Exception:
        count = 1
    return max(1, min(count, 32, os.cpu_count() or 1))


def calculate_checkpoint_hashes(max_workers: object = 1, roots: list[str | Path] | None = None) -> dict[str, object]:
    started = time.perf_counter()
    resolved_roots = [Path(item).resolve() for item in (roots or checkpoint_roots())]
    files = list_checkpoint_files(resolved_roots)
    workers = min(_thread_count(max_workers), max(1, len(files)))
    rows: list[dict[str, object]] = []
    if files:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(_hash_file_safe, path, resolved_roots) for path in files]
            for future in as_completed(futures):
                rows.append(future.result())
        rows.sort(key=lambda row: str(row.get("name", "")).lower())
    return {
        "mode": "checkpoint-hash",
        "roots": [str(item) for item in resolved_roots],
        "thread_count": workers,
        "total_count": len(files),
        "calculated_count": sum(1 for row in rows if row.get("status") == "calculated"),
        "error_count": sum(1 for row in rows if row.get("status") == "error"),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "rows": rows,
    }


def _format_size(size: object) -> str:
    try:
        value = float(size)
    except Exception:
        value = 0.0
    units = ["B", "KB", "MB", "GB", "TB"]
    unit = units[0]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            break
        value /= 1024
    return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"


def checkpoint_hashes_html(result: dict[str, object] | None = None, lang: object | None = None) -> str:
    data = result or {
        "thread_count": 1,
        "total_count": 0,
        "calculated_count": 0,
        "error_count": 0,
        "elapsed_seconds": 0,
        "rows": [],
    }
    rows = []
    for item in data.get("rows", []) or []:
        row = item if isinstance(item, dict) else {}
        status = _text(lang, "Calculated", "已计算") if row.get("status") == "calculated" else _text(lang, "Error", "错误")
        detail = str(row.get("error", "") or row.get("path", "") or "")
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(row.get('name', '') or ''))}</td>"
            f"<td>{html.escape(_format_size(row.get('size_bytes', 0)))}</td>"
            f"<td>{html.escape(str(row.get('short_hash', '') or ''))}</td>"
            f"<td>{html.escape(str(row.get('sha256', '') or ''))}</td>"
            f"<td>{html.escape(status)}</td>"
            f"<td>{html.escape(detail)}</td>"
            "</tr>"
        )
    if not rows:
        rows.append(
            '<tr><td colspan="6" class="forge-neo-checkpoint-hash-empty">'
            f"{html.escape(_text(lang, 'No checkpoint files have been calculated yet.', '尚未计算模型哈希。'))}"
            "</td></tr>"
        )
    headers = [
        _text(lang, "Checkpoint", "模型"),
        _text(lang, "Size", "大小"),
        _text(lang, "Short hash", "短哈希"),
        "SHA256",
        _text(lang, "Status", "状态"),
        _text(lang, "Path / Error", "路径 / 错误"),
    ]
    summary = (
        f"{html.escape(_text(lang, 'Checkpoint hash calculation', '模型哈希计算'))}: "
        f"{html.escape(_text(lang, 'files', '文件'))} {int(data.get('total_count', 0))}, "
        f"{html.escape(_text(lang, 'calculated', '已计算'))} {int(data.get('calculated_count', 0))}, "
        f"{html.escape(_text(lang, 'errors', '错误'))} {int(data.get('error_count', 0))}, "
        f"{html.escape(_text(lang, 'threads', '线程'))} {int(data.get('thread_count', 1))}, "
        f"{html.escape(_text(lang, 'seconds', '秒'))} {float(data.get('elapsed_seconds', 0)):.3f}"
    )
    return (
        '<div class="forge-neo-checkpoint-hash-result">'
        f"<p>{summary}</p>"
        '<div class="forge-neo-extension-table-wrap">'
        '<table id="forge_neo_settings_checkpoint_hash_table" class="forge-neo-extension-table">'
        f"<thead><tr>{''.join(f'<th>{html.escape(label)}</th>' for label in headers)}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        "</div>"
        "</div>"
    )
