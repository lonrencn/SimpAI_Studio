import datetime
import mimetypes
import os
import re
import time
from urllib.parse import quote

import shared
from modules.canvas_media_metadata import extract_media_metadata

try:
    from PIL import Image
except Exception:
    Image = None


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXTS = {".webm", ".mp4", ".mov", ".mkv"}
DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _file_preview_url(path):
    if not path:
        return ""
    return f"/file={quote(os.path.abspath(str(path)).replace(os.sep, '/'), safe=':/')}"


def _user_did(state_params=None):
    try:
        user = state_params.get("user") if isinstance(state_params, dict) else None
        if user is not None and hasattr(user, "get_did"):
            did = user.get_did()
            if did:
                return did
    except Exception:
        pass
    try:
        if shared.token is not None:
            return shared.token.get_guest_did()
    except Exception:
        pass
    return "guest"


def _outputs_root(state_params=None):
    import modules.config as config

    return os.path.abspath(config.get_user_path_outputs(_user_did(state_params)))


def _safe_media_type(value):
    text = str(value or "image").strip().lower()
    return "video" if text == "video" else "image"


def _clamped_int(value, default, min_value, max_value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(min_value, min(number, max_value))


def _clamped_float(value, default, min_value, max_value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(min_value, min(number, max_value))


def _media_exts(media_type):
    return VIDEO_EXTS if media_type == "video" else IMAGE_EXTS


def _dated_folders(root):
    if not os.path.isdir(root):
        return []
    folders = []
    for entry in os.scandir(root):
        try:
            if entry.is_dir() and DATE_DIR_RE.match(entry.name):
                folders.append(entry.name)
        except OSError:
            continue
    return sorted(folders, reverse=True)


def _is_allowed_file(path, media_type):
    return os.path.splitext(str(path or ""))[1].lower() in _media_exts(media_type)


def _safe_output_media_path(relative_path, media_type, state_params=None):
    root = os.path.realpath(_outputs_root(state_params))
    rel = str(relative_path or "").strip().replace("\\", "/").strip("/")
    if not rel or os.path.isabs(rel):
        return "", root, "Missing or invalid relative path."
    candidate = os.path.realpath(os.path.abspath(os.path.join(root, rel.replace("/", os.sep))))
    try:
        if os.path.commonpath([root, candidate]) != root:
            return "", root, "Path is outside the outputs folder."
    except Exception:
        return "", root, "Path is outside the outputs folder."
    if not os.path.isfile(candidate):
        return "", root, "File does not exist."
    if not _is_allowed_file(candidate, media_type):
        return "", root, "File type is not allowed."
    return candidate, root, ""


def _read_image_size(path):
    if Image is None:
        return None, None
    try:
        with Image.open(path) as image:
            return image.size
    except Exception:
        return None, None


def _media_item(path, root, media_type, include_dimensions=False, include_metadata=False):
    try:
        stat = os.stat(path)
    except OSError:
        return None
    width = None
    height = None
    if media_type == "image" and include_dimensions:
        width, height = _read_image_size(path)
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    name = os.path.basename(path)
    folder = rel.split("/", 1)[0] if "/" in rel else ""
    mime = mimetypes.guess_type(path)[0] or ("video/mp4" if media_type == "video" else "image/png")
    item = {
        "id": rel,
        "name": name,
        "folder": folder,
        "relative_path": rel,
        "path": os.path.abspath(path),
        "preview_url": _file_preview_url(path),
        "media_type": media_type,
        "mime": mime,
        "size": stat.st_size,
        "updated_at": stat.st_mtime,
        "updated_at_iso": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "width": width,
        "height": height,
    }
    if include_metadata:
        metadata = extract_media_metadata(path, mime=mime)
        if metadata:
            item["generation_metadata"] = metadata
    return item


def list_output_media(payload=None, state_params=None):
    payload = payload if isinstance(payload, dict) else {}
    media_type = _safe_media_type(payload.get("media_type"))
    limit = _clamped_int(payload.get("limit"), 80, 12, 240)
    offset = _clamped_int(payload.get("offset"), 0, 0, 10_000_000)
    folder = str(payload.get("folder") or "").strip().replace("\\", "/").strip("/")
    query = str(payload.get("query") or "").strip().lower()
    include_dimensions = bool(payload.get("include_dimensions", True))
    include_metadata = bool(payload.get("include_metadata", False))
    max_seconds = _clamped_float(payload.get("max_seconds"), 3.0, 0.5, 12.0)
    root = _outputs_root(state_params)
    folders = _dated_folders(root)
    if folder and folder not in folders:
        folder = ""
    scan_folders = [folder] if folder else folders[:16]
    deadline = time.time() + max_seconds
    items = []
    truncated = False
    matched = 0
    target_count = limit + 1

    for folder_name in scan_folders:
        folder_path = os.path.abspath(os.path.join(root, folder_name))
        try:
            if os.path.commonpath([root, folder_path]) != root or not os.path.isdir(folder_path):
                continue
        except Exception:
            continue
        for dirpath, dirnames, filenames in os.walk(folder_path):
            if time.time() > deadline:
                truncated = True
                break
            dirnames.sort(reverse=True)
            filenames = sorted(filenames, reverse=True)
            for filename in filenames:
                if len(items) >= target_count:
                    truncated = True
                    break
                path = os.path.abspath(os.path.join(dirpath, filename))
                if not _is_allowed_file(path, media_type):
                    continue
                if query:
                    rel_text = os.path.relpath(path, root).replace(os.sep, "/").lower()
                    if query not in filename.lower() and query not in rel_text:
                        continue
                if matched < offset:
                    matched += 1
                    continue
                item = _media_item(
                    path,
                    root,
                    media_type,
                    include_dimensions=include_dimensions,
                    include_metadata=include_metadata,
                )
                if item:
                    items.append(item)
                    matched += 1
            if truncated:
                break
        if truncated:
            break

    page_items = items[:limit]
    page_items.sort(key=lambda item: float(item.get("updated_at") or 0), reverse=True)
    has_more = bool(page_items) and (len(items) > limit or truncated)
    next_offset = offset + len(page_items)
    return {
        "ok": True,
        "media_type": media_type,
        "folder": folder,
        "folders": folders[:120],
        "items": page_items,
        "root": root,
        "truncated": truncated,
        "has_more": has_more,
        "offset": offset,
        "next_offset": next_offset if has_more else None,
        "limit": limit,
    }


def delete_output_media(payload=None, state_params=None):
    payload = payload if isinstance(payload, dict) else {}
    media_type = _safe_media_type(payload.get("media_type"))
    raw_ids = payload.get("ids")
    if raw_ids is None:
        raw_ids = payload.get("relative_paths")
    if raw_ids is None:
        raw_ids = payload.get("relative_path") or payload.get("id")
    if isinstance(raw_ids, str):
        ids = [raw_ids]
    elif isinstance(raw_ids, (list, tuple)):
        ids = [str(item or "") for item in raw_ids]
    else:
        ids = []

    deleted = []
    errors = []
    seen = set()
    for rel in ids[:80]:
        rel = str(rel or "").strip().replace("\\", "/").strip("/")
        if not rel or rel in seen:
            continue
        seen.add(rel)
        path, root, error = _safe_output_media_path(rel, media_type, state_params)
        if error:
            errors.append({"id": rel, "error": error})
            continue
        try:
            os.remove(path)
            deleted.append(os.path.relpath(path, root).replace(os.sep, "/"))
        except OSError as exc:
            errors.append({"id": rel, "error": str(exc)})

    return {
        "ok": bool(deleted) and not errors,
        "media_type": media_type,
        "deleted": deleted,
        "errors": errors,
    }
