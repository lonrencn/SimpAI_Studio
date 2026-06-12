import copy
import time

import shared
import modules.config as config
import modules.model_loader as model_loader
from modules.access_mode import is_local_mode, user_can_download_models


MODEL_CATALOG_CACHE = {}


def invalidate_model_catalog_cache():
    MODEL_CATALOG_CACHE.clear()


def _normalize_list(values):
    result = []
    for item in values or []:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _preset_lora_names(preset_node):
    defaults = {}
    try:
        defaults = (preset_node.get("models_config") or {}).get("defaults") or {}
    except Exception:
        defaults = {}
    names = []
    for item in defaults.get("loras") or []:
        if not isinstance(item, dict):
            continue
        model = item.get("model")
        if model and model != "None":
            names.append(model)
    return names


def get_model_catalog_for_preset(payload):
    if not isinstance(payload, dict):
        return {"ok": False, "error": "payload is not an object"}
    preset_node = payload.get("preset_node") if isinstance(payload.get("preset_node"), dict) else {}
    runtime = preset_node.get("runtime") if isinstance(preset_node.get("runtime"), dict) else {}
    preset = preset_node.get("preset") if isinstance(preset_node.get("preset"), dict) else {}
    use_model_filter = bool(payload.get("use_model_filter", True))
    engine = runtime.get("backend_engine") or preset.get("backend_engine") or "Z-image"
    task_method = runtime.get("task_method") or preset.get("task_method") or None
    if runtime.get("scene_frontend") and task_method and not str(task_method).startswith("scene_"):
        task_method = f"scene_{task_method}"
    signature = (str(engine), str(task_method or ""), use_model_filter)
    force_refresh = bool(payload.get("force_refresh") or payload.get("__force_refresh"))

    if not force_refresh and signature in MODEL_CATALOG_CACHE:
        catalog = copy.deepcopy(MODEL_CATALOG_CACHE[signature])
    else:
        model_filenames, lora_filenames, vae_filenames, clip_filenames = config.update_files(
            engine,
            task_method,
            use_model_filter=use_model_filter,
        )
        catalog = {
            "engine": engine,
            "backend_engine": engine,
            "task_method": task_method,
            "use_model_filter": use_model_filter,
            "model_filenames": _normalize_list(model_filenames),
            "refiner_filenames": ["None"] + _normalize_list(model_filenames),
            "lora_filenames": ["None"] + _normalize_list(lora_filenames),
            "vae_filenames": ["Default (model)"] + _normalize_list(vae_filenames),
            "clip_filenames": ["Default (model)"] + _normalize_list(clip_filenames),
            "upscale_model_filenames": ["default"] + _normalize_list(getattr(config, "upscale_model_filenames", []) or []),
        }
        MODEL_CATALOG_CACHE[signature] = copy.deepcopy(catalog)

    for name in _preset_lora_names(preset_node):
        if name not in catalog["lora_filenames"]:
            catalog["lora_filenames"].append(name)

    return {"ok": True, "catalog": catalog}


def _clean_preset_name(value):
    text = str(value or "").strip().replace("\u2B07", "").strip()
    return text


def _user_did_from_payload(payload):
    context = payload.get("user_context") if isinstance(payload.get("user_context"), dict) else {}
    for key in ("user_did", "owner"):
        value = str(context.get(key) or "").strip()
        if value and value not in ("guest", "multi", "local"):
            return value
    value = str(context.get("user_did") or context.get("owner") or "").strip()
    if value and value != "multi":
        return value
    return "local" if is_local_mode() else ""


def _preset_node_from_payload(payload):
    node = payload.get("preset_node") if isinstance(payload.get("preset_node"), dict) else {}
    return node


def _preset_name_from_node(preset_node):
    preset = preset_node.get("preset") if isinstance(preset_node.get("preset"), dict) else {}
    return _clean_preset_name(preset.get("name") or preset.get("display_name") or preset_node.get("title") or "")


def _raw_model_list_from_node(preset_node):
    requirements = preset_node.get("model_requirements") if isinstance(preset_node.get("model_requirements"), dict) else {}
    raw = requirements.get("model_list")
    if raw is None:
        raw = preset_node.get("model_list")
    if raw is None:
        raw = preset_node.get("model_list_raw")
    return raw if isinstance(raw, list) else []


def _has_model_probe(preset_node, preset_name, raw_model_list, user_did):
    requirements = preset_node.get("model_requirements") if isinstance(preset_node.get("model_requirements"), dict) else {}
    if raw_model_list:
        return True
    if requirements.get("has_model_probe"):
        return True
    try:
        get_cached = getattr(model_loader, "_get_cached_preset_model_list", None)
        if callable(get_cached):
            _, cached_list, _ = get_cached(preset_name, user_did)
            return cached_list is not None
    except Exception:
        pass
    return False


def _missing_models_for_preset(preset_name, raw_model_list, user_did):
    if raw_model_list:
        return preset_name, model_loader.get_missing_model_list_from_entries(
            preset_name,
            raw_model_list,
            user_did=user_did,
        )

    missing = model_loader.get_missing_model_list(preset_name, user_did=user_did)
    if missing:
        return preset_name, missing

    if preset_name and (not preset_name.endswith("_fp4")) and (not preset_name.endswith("_int4")):
        for variant_name in (f"{preset_name}_fp4", f"{preset_name}_int4"):
            variant_missing = model_loader.get_missing_model_list(variant_name, user_did=user_did)
            if variant_missing:
                return variant_name, variant_missing

    return preset_name, []


def _download_status_key(cata, path_file):
    return (str(cata) + "/" + str(path_file)).replace("\\", "/").strip("/")


def _missing_model_dicts(missing_models):
    rows = []
    for item in missing_models or []:
        try:
            cata, path_file, human_size, url, size = item
        except Exception:
            continue
        status_key = _download_status_key(cata, path_file)
        rows.append({
            "cata": str(cata or ""),
            "path_file": str(path_file or ""),
            "human_size": str(human_size or ""),
            "url": str(url or ""),
            "size": int(size or 0) if str(size or "").isdigit() else size,
            "status_key": status_key,
            "download_status": copy.deepcopy(model_loader.get_download_status(status_key) or {}),
        })
    return rows


def get_preset_model_status(payload):
    if not isinstance(payload, dict):
        return {"ok": False, "error": "payload is not an object"}
    preset_node = _preset_node_from_payload(payload)
    preset_name = _preset_name_from_node(preset_node)
    if not preset_name:
        return {"ok": False, "error": "preset name is empty"}

    user_did = _user_did_from_payload(payload)
    raw_model_list = _raw_model_list_from_node(preset_node)
    checked_preset, missing_models = _missing_models_for_preset(preset_name, raw_model_list, user_did)
    missing_rows = _missing_model_dicts(missing_models)
    has_requirements = _has_model_probe(preset_node, checked_preset, raw_model_list, user_did)
    ready = len(missing_rows) == 0
    can_download = user_can_download_models(user_did) and not bool(getattr(shared.args, "disable_backend", False))
    state = "ready" if ready else "missing"
    message = "All required model files are available." if ready else f"{len(missing_rows)} required model file(s) are missing."
    if ready and not has_requirements:
        message = "No missing models found for this preset."
    return {
        "ok": True,
        "preset": preset_name,
        "checked_preset": checked_preset,
        "state": state,
        "ready": ready,
        "has_requirements": bool(has_requirements),
        "missing_count": len(missing_rows),
        "missing_models": missing_rows,
        "can_download": bool(can_download),
        "download_disabled": not bool(can_download),
        "backend_disabled": bool(getattr(shared.args, "disable_backend", False)),
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "message": message,
    }


def queue_preset_model_downloads(payload):
    status = get_preset_model_status(payload)
    if not status.get("ok"):
        return status
    if status.get("ready"):
        return dict(status, queued_count=0, message="All required model files are already available.")
    if not status.get("can_download"):
        return dict(status, ok=False, error="model download is not allowed for the current user or backend mode")

    user_did = _user_did_from_payload(payload)
    single = payload.get("missing_model") if isinstance(payload.get("missing_model"), dict) else None
    if single:
        task_id = model_loader.download_model_entry(
            single.get("cata"),
            single.get("path_file"),
            size=single.get("size") or 0,
            url=single.get("url") or "",
            user_did=user_did,
            async_task=True,
        )
        queued = [task_id] if task_id else []
        return dict(status, ok=True, state="queued", queued_count=len(queued), queued=queued, message=f"Queued {len(queued)} model download task(s).")

    queued = []
    for item in status.get("missing_models") or []:
        task_id = model_loader.download_model_entry(
            item.get("cata"),
            item.get("path_file"),
            size=item.get("size") or 0,
            url=item.get("url") or "",
            user_did=user_did,
            async_task=True,
        )
        if task_id:
            queued.append(task_id)

    return dict(status, ok=True, state="queued", queued_count=len(queued), queued=queued, message=f"Queued {len(queued)} model download task(s).")
