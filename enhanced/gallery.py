import gradio as gr
import os
import math
import json
import copy
import subprocess
import modules.util as util
import modules.config as config
import modules.meta_parser as meta_parser
import modules.canvas_workbench_media_gallery as canvas_workbench_media_gallery
import enhanced.toolbox as toolbox
import re
import shared
import shutil
from lxml import etree
import logging
import threading
import time
from PIL import Image
from enhanced.logger import format_name
from ui.update_helpers import dropdown_update, gr_update, skip_update
logger = logging.getLogger(format_name(__name__))

# app context
images_list = {}
images_list_keys = {} #[]
images_prompt = {}
images_prompt_keys = {} #[]
images_ads = {}

videos_list = {}

image_types = ['.png', '.jpg', '.jpeg', '.webp'] 
video_types = ['.webm', '.mp4']
output_images_regex = re.compile(r'\d{4}-\d{2}-\d{2}')
_output_list_cache = {}
_output_list_cache_lock = threading.Lock()
_output_list_inflight = set()
_output_catalog_dir_cache = {}
_gallery_media_switch_request_lock = threading.Lock()
_gallery_media_switch_latest = {}
_main_gallery_browser_request_lock = threading.Lock()
_main_gallery_browser_invalidated_after = {}


def _gallery_media_switch_noop_response():
    return [skip_update()] * 12


def _parse_gallery_media_switch_marker(marker, fallback_mode=None):
    text = str(marker or "").strip()
    if not text:
        return None
    parts = text.split(":")
    if len(parts) < 3:
        return None
    try:
        started_at = int(parts[0])
        seq = int(parts[1])
    except Exception:
        return None
    mode = "video" if parts[2] == "video" else "image"
    if fallback_mode in ("image", "video") and mode != fallback_mode:
        mode = fallback_mode
    return (started_at, seq, mode, text)


def _gallery_media_switch_user_key(state_params):
    try:
        user = state_params.get("user") if isinstance(state_params, dict) else None
        did = user.get_did() if user is not None and hasattr(user, "get_did") else None
        return str(did or "guest")
    except Exception:
        return "guest"


def _main_gallery_browser_user_key(state_params):
    return _gallery_media_switch_user_key(state_params)


def invalidate_main_gallery_browser_requests(state_params, reason="preset_switch"):
    key = _main_gallery_browser_user_key(state_params)
    invalidated_at = time.monotonic()
    with _main_gallery_browser_request_lock:
        _main_gallery_browser_invalidated_after[key] = invalidated_at
    util.log_ui_trace(
        logger,
        "[UI-TRACE] gallery_browser.invalidate | user=%r, reason=%r",
        key,
        reason,
    )
    return invalidated_at


def _main_gallery_browser_request_context(state_params):
    return {
        "user_key": _main_gallery_browser_user_key(state_params),
        "started_at": time.monotonic(),
    }


def _main_gallery_browser_request_is_stale(context):
    if not isinstance(context, dict):
        return False
    user_key = context.get("user_key")
    started_at = context.get("started_at")
    if user_key is None or started_at is None:
        return False
    with _main_gallery_browser_request_lock:
        invalidated_at = _main_gallery_browser_invalidated_after.get(user_key)
    return bool(invalidated_at and invalidated_at > started_at)


def _gallery_browser_stale_state_json(payload=None):
    payload = payload or {}
    return _main_gallery_browser_state_json(
        ok=False,
        stale=True,
        media_type=payload.get("media_type"),
        folder=payload.get("folder"),
        request_id=payload.get("request_id"),
        error="Gallery browser request expired.",
    )


def _gallery_browser_load_stale_response(payload=None, state_params=None):
    util.log_ui_trace(
        logger,
        "[UI-TRACE] gallery_browser.stale_load_skip | preset=%r, request_id=%r",
        state_params.get("__preset") if isinstance(state_params, dict) else None,
        (payload or {}).get("request_id"),
    )
    return [_gallery_browser_stale_state_json(payload)] + [skip_update() for _ in range(10)]


def _gallery_browser_native_stale_response(state_params=None, request_name="gallery_browser_native"):
    util.log_ui_trace(
        logger,
        "[UI-TRACE] gallery_browser.stale_native_skip | preset=%r, request=%r",
        state_params.get("__preset") if isinstance(state_params, dict) else None,
        request_name,
    )
    return [skip_update() for _ in range(15)]


def _register_gallery_media_switch_request(marker, target_engine_type, state_params):
    parsed = _parse_gallery_media_switch_marker(marker, target_engine_type)
    if parsed is None:
        return True
    key = _gallery_media_switch_user_key(state_params)
    token = parsed[:2]
    with _gallery_media_switch_request_lock:
        current = _gallery_media_switch_latest.get(key)
        if current and token < current["token"]:
            return False
        _gallery_media_switch_latest[key] = {
            "token": token,
            "mode": parsed[2],
            "marker": parsed[3],
        }
    return True


def _is_gallery_media_switch_request_current(marker, target_engine_type, state_params):
    parsed = _parse_gallery_media_switch_marker(marker, target_engine_type)
    if parsed is None:
        return True
    key = _gallery_media_switch_user_key(state_params)
    token = parsed[:2]
    with _gallery_media_switch_request_lock:
        current = _gallery_media_switch_latest.get(key)
    if not current:
        return True
    return token >= current["token"] and parsed[2] == current["mode"]


def _should_show_image_toolbox(image_tools_checkbox, state_params):
    if not state_params:
        return False
    return bool(state_params.get("gallery_preview_open") and image_tools_checkbox)


def _hide_image_toolbox_for_gallery_grid(state_params, reason):
    if isinstance(state_params, dict):
        state_params["gallery_preview_open"] = False
    return gr_update(visible=False)


def _empty_gallery_welcome_update(state_params):
    try:
        preset = state_params.get("__preset") or state_params.get("preset")
        is_mobile = bool(state_params.get("__is_mobile") or state_params.get("is_mobile"))
        return gr_update(value=meta_parser.get_welcome_image(preset, is_mobile), visible=True)
    except Exception as e:
        logger.exception("Failed to restore welcome preview for empty gallery: %s", e)
        return gr_update(visible=True)


def get_gallery_engine_type(state_params):
    if not isinstance(state_params, dict):
        return "image"
    gallery_engine_type = state_params.get("__gallery_engine_type")
    if gallery_engine_type in ("image", "video"):
        return gallery_engine_type
    engine_type = state_params.get("engine_type") or state_params.get("default_engine", {}).get("engine_type")
    return "video" if engine_type == "video" else "image"


def _gallery_lang(state_params):
    if isinstance(state_params, dict):
        lang = str(state_params.get("__lang") or "").strip().lower()
        if lang.startswith("en"):
            return "en"
    return "cn"


def _gallery_media_label(media_type, state_params):
    if _gallery_lang(state_params) == "en":
        return "Finished Videos" if media_type == "video" else "Finished Images"
    return "已完成视频" if media_type == "video" else "已完成图片"


def _gallery_browser_count_status(count, media_type, state_params):
    try:
        count = int(count or 0)
    except Exception:
        count = 0
    if _gallery_lang(state_params) == "en":
        return "{} {}".format(count, "videos" if media_type == "video" else "items")
    return "{} {}".format(count, "个视频" if media_type == "video" else "张图片")


def clear_post_generation_compare_state(state_params):
    if not isinstance(state_params, dict):
        return state_params
    state_params["__post_generation_compare_input_ok"] = False
    state_params["__post_generation_compare_visible"] = False
    state_params["__post_generation_compare_ready"] = False
    state_params["__post_generation_compare_cleared"] = True
    state_params.pop("__post_generation_compare_choice", None)
    state_params.pop("__post_generation_image_url", None)
    return state_params


def clear_post_generation_output_state(state_params):
    if not isinstance(state_params, dict):
        return state_params
    for key in (
        "__post_generation_has_output",
        "__post_generation_gallery_output",
        "__post_generation_video_output",
    ):
        state_params.pop(key, None)
    return state_params


def clear_post_generation_result_state(state_params):
    state_params = clear_post_generation_compare_state(state_params)
    return clear_post_generation_output_state(state_params)


def should_preserve_post_generation_compare_for_choice(state_params, choice):
    if not isinstance(state_params, dict):
        return False
    if not state_params.get("__post_generation_compare_ready"):
        return False
    if not state_params.get("__post_generation_compare_visible"):
        return False
    if state_params.get("__post_generation_compare_cleared"):
        return False
    compare_choice = state_params.get("__post_generation_compare_choice")
    if compare_choice is None:
        output_list = state_params.get("__output_list") or []
        compare_choice = output_list[0] if output_list else None
    return str(compare_choice or "") == str(choice or "")


def normalize_gallery_selected_index(selected):
    if isinstance(selected, (list, tuple)):
        selected = selected[0] if selected else 0
    try:
        return max(0, int(selected))
    except Exception:
        return 0


def set_selected_gallery_media_path(state_params, media_path):
    if not isinstance(state_params, dict):
        return None
    if media_path:
        state_params["__selected_gallery_media_path"] = media_path
        return media_path
    state_params.pop("__selected_gallery_media_path", None)
    return None


def remember_selected_gallery_media_path(choice, selected, state_params):
    if not isinstance(state_params, dict):
        return normalize_gallery_selected_index(selected), None
    selected_index = normalize_gallery_selected_index(selected)
    media_path = None
    try:
        if state_params.get("gallery_state") == "main_browser":
            media_path = get_main_gallery_browser_selected_path(state_params, selected_index)
        else:
            if choice is None and "__output_list" in state_params and len(state_params["__output_list"]) > 0:
                choice = state_params["__output_list"][0]
            media_path = get_media_path_from_gallery_index(
                choice,
                selected_index,
                state_params.get("__max_per_page", 18),
                state_params["user"].get_did(),
                get_gallery_engine_type(state_params),
            )
    except Exception as e:
        util.log_ui_trace(
            logger,
            "[UI-TRACE] gallery.remember_selected_media.failed | choice=%r, selected=%r, error=%r",
            choice,
            selected,
            e,
        )
        media_path = None
    set_selected_gallery_media_path(state_params, media_path)
    return selected_index, media_path


def gallery_preview_open(image_tools_checkbox, state_params):
    state_params = state_params or {}
    state_params["gallery_preview_open"] = True
    return gr_update(visible=_should_show_image_toolbox(image_tools_checkbox, state_params)), state_params


def gallery_preview_close(state_params):
    state_params = state_params or {}
    state_params["gallery_preview_open"] = False
    clear_post_generation_compare_state(state_params)
    return gr_update(visible=False), state_params


def sync_image_toolbox_visibility(image_tools_checkbox, state_params):
    return gr_update(visible=_should_show_image_toolbox(image_tools_checkbox, state_params))

def invalidate_output_list_cache(user_did=None, engine_type=None):
    user_key = None if user_did is None else str(user_did)
    engine_key = None if engine_type is None else str(engine_type)
    with _output_list_cache_lock:
        if user_key is None and engine_key is None:
            _output_list_cache.clear()
        else:
            for cache_key in list(_output_list_cache.keys()):
                key_user, key_engine = cache_key[0], cache_key[1]
                if (user_key is None or key_user == user_key) and (engine_key is None or key_engine == engine_key):
                    _output_list_cache.pop(cache_key, None)
    if user_key is None:
        _output_catalog_dir_cache.clear()
    else:
        for cache_key in list(_output_catalog_dir_cache.keys()):
            if cache_key and cache_key[0] == user_key:
                _output_catalog_dir_cache.pop(cache_key, None)


def _catalog_choice_from_folder(folder_name):
    return folder_name[2:] if isinstance(folder_name, str) and folder_name.startswith("20") else folder_name


def _folder_from_catalog_choice(choice):
    choice = str(choice or "")
    return choice if choice.startswith("20") else "20{}".format(choice)


def _paginate_catalog_choices(catalogs, max_per_page, max_catalog):
    output_list = []
    for choice in sorted(catalogs.keys(), reverse=True):
        item_count = len(catalogs.get(choice) or [])
        if item_count <= 0:
            continue
        if item_count > max_per_page:
            max_page_no = math.ceil(item_count / max_per_page)
            width = len(str(max_page_no))
            for page_no in range(1, max_page_no + 1):
                output_list.append("{}/{}".format(choice, str(page_no).zfill(width)))
        else:
            output_list.append(choice)
    return output_list[:max_catalog]


def _slice_catalog_page(items, choice, max_per_page):
    if not items:
        return []
    parts = str(choice or "").split("/")
    page = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    if page <= 0 or len(items) <= max_per_page:
        return items
    page = abs(page - math.ceil(len(items) / max_per_page)) + 1
    if page * max_per_page < len(items):
        return items[(page - 1) * max_per_page:page * max_per_page]
    return items[len(items) - max_per_page:]


def _get_video_catalog(choice, user_did=None):
    global videos_list

    if not user_did:
        user_did = shared.token.get_guest_did()
    if user_did not in videos_list:
        videos_list[user_did] = {}

    base_choice = str(choice or "").split("/")[0]
    if not base_choice:
        return []

    cached = videos_list[user_did].get(base_choice)
    if isinstance(cached, list):
        return cached
    if isinstance(cached, str):
        return [cached]

    user_path_outputs = config.get_user_path_outputs(user_did)
    folder_name = _folder_from_catalog_choice(base_choice)
    folder_path = os.path.join(user_path_outputs, folder_name)
    if not os.path.isdir(folder_path):
        return []

    video_files = sorted(
        util.get_files_from_folder(folder_path, video_types, None),
        reverse=True
    )
    rel_paths = [os.path.join(folder_name, video_file) for video_file in video_files]
    videos_list[user_did][base_choice] = rel_paths
    return rel_paths


def get_videos_from_gallery_index(choice, max_per_page, user_did=None):
    if choice is None:
        return []
    rel_paths = _get_video_catalog(choice, user_did)
    rel_paths = _slice_catalog_page(rel_paths, choice, max_per_page)
    if not user_did:
        user_did = shared.token.get_guest_did()
    user_path_outputs = config.get_user_path_outputs(user_did)
    return [os.path.join(user_path_outputs, rel_path) for rel_path in rel_paths]


def get_video_rel_path_from_gallery_index(choice, selected, max_per_page, user_did=None):
    return _get_video_rel_path_from_gallery_index(choice, selected, max_per_page, user_did)


def refresh_videos_catalog(choice, passthrough=False, user_did=None):
    if not user_did:
        user_did = shared.token.get_guest_did()
    if user_did not in videos_list:
        videos_list[user_did] = {}

    base_choice = str(choice or "").split("/")[0]
    if not base_choice:
        return []
    if passthrough:
        videos_list[user_did].pop(base_choice, None)
    return _get_video_catalog(base_choice, user_did)


def _get_video_rel_path_from_gallery_index(choice, selected, max_per_page, user_did=None):
    rel_paths = _get_video_catalog(choice, user_did)
    rel_paths = _slice_catalog_page(rel_paths, choice, max_per_page)
    if not rel_paths:
        return None
    try:
        selected = int(selected)
    except Exception:
        selected = 0
    selected = max(0, min(selected, len(rel_paths) - 1))
    return rel_paths[selected]

def refresh_output_list(max_per_page, max_catalog, user_did=None, engine_type='image'):
    global image_types, images_list, images_list_keys, images_prompt, images_prompt_keys, images_ads, videos_list, _output_catalog_dir_cache

    cache_key = (str(user_did), str(engine_type), int(max_per_page), int(max_catalog))
    with _output_list_cache_lock:
        cached = _output_list_cache.get(cache_key)
        if cache_key in _output_list_inflight:
            return cached if cached is not None else ([], 0, 0)
        _output_list_inflight.add(cache_key)

    start_perf = time.perf_counter()
    deadline = time.monotonic() + 2.5

    def _check_deadline():
        if time.monotonic() > deadline:
            raise TimeoutError()

    def _walk_files_with_deadline(folder_path, extensions):
        if not os.path.isdir(folder_path):
            return []
        filenames = []
        for root, _, files in os.walk(folder_path, topdown=False):
            _check_deadline()
            relative_path = os.path.relpath(root, folder_path)
            if relative_path == ".":
                relative_path = ""
            for filename in sorted(files, key=lambda s: s.casefold()):
                _check_deadline()
                _, file_extension = os.path.splitext(filename)
                if extensions is None or file_extension.lower() in extensions:
                    filenames.append(os.path.join(relative_path, filename) if relative_path else filename)
        return filenames

    def _list_files_quick(folder_path, extensions):
        try:
            _check_deadline()
            has_dirs = False
            files = []
            for entry in os.scandir(folder_path):
                _check_deadline()
                try:
                    if entry.is_dir():
                        has_dirs = True
                        continue
                    if not entry.is_file():
                        continue
                    _, ext = os.path.splitext(entry.name)
                    if ext.lower() in extensions:
                        files.append(entry.name)
                except OSError:
                    continue
            if files or not has_dirs:
                return files
        except Exception:
            pass
        try:
            return _walk_files_with_deadline(folder_path, extensions)
        except Exception:
            return []

    def _has_any_files_quick(folder_path, extensions):
        try:
            _check_deadline()
            has_dirs = False
            for entry in os.scandir(folder_path):
                _check_deadline()
                try:
                    if entry.is_dir():
                        has_dirs = True
                        continue
                    if not entry.is_file():
                        continue
                    _, ext = os.path.splitext(entry.name)
                    if ext.lower() in extensions:
                        return True
                except OSError:
                    continue
            if not has_dirs:
                return False
        except Exception:
            pass
        try:
            return len(_walk_files_with_deadline(folder_path, extensions)) > 0
        except Exception:
            return False

    try:
        user_path_outputs = config.get_user_path_outputs(user_did)
        if not os.path.exists(user_path_outputs):
            logger.info(f'[Gallery] Makedirs for new user: {user_path_outputs}')
            os.makedirs(user_path_outputs, exist_ok=True)

        listdirs = []
        for entry in os.scandir(user_path_outputs):
            _check_deadline()
            try:
                if not entry.is_dir():
                    continue
                name = entry.name
                if output_images_regex.findall(name):
                    listdirs.append(name)
            except OSError:
                continue
        if not listdirs:
            result = ([], 0, 0)
            with _output_list_cache_lock:
                _output_list_cache[cache_key] = result
            return result

        listdirs1 = []
        total_nums = 0
        video_catalogs = {}
        scanned_dirs = 0
        reused_dirs = 0
        for index in listdirs:
            _check_deadline()
            path_gallery = os.path.join(user_path_outputs, index)
            try:
                stat = os.stat(path_gallery)
                dir_signature = (stat.st_mtime_ns, stat.st_size)
            except OSError:
                continue

            dir_cache_key = (str(user_did), os.path.abspath(path_gallery))
            cached_dir = _output_catalog_dir_cache.get(dir_cache_key)
            if cached_dir and cached_dir.get("signature") == dir_signature:
                reused_dirs += 1
                nums = cached_dir.get("image_count", 0)
                cached_videos = cached_dir.get("videos", [])
                if isinstance(cached_videos, dict):
                    cached_videos = list(cached_videos.values())
            else:
                scanned_dirs += 1
                image_files = _list_files_quick(path_gallery, image_types)
                video_names = _list_files_quick(path_gallery, video_types)
                nums = len(image_files)
                cached_videos = [os.path.join(index, v) for v in sorted(video_names, reverse=True)]
                _output_catalog_dir_cache[dir_cache_key] = {
                    "signature": dir_signature,
                    "image_count": nums,
                    "videos": cached_videos,
                    "last_seen": time.monotonic(),
                }

            if nums <= 0 and not cached_videos:
                continue

            total_nums += nums
            if nums > 0:
                listdirs1.append(index)
            if nums > max_per_page:
                max_page_no = math.ceil(nums/max_per_page)
                for i in range(1, max_page_no + 1):
                    _check_deadline()
                    listdirs1.append("{}/{}".format(index, str(i).zfill(len(str(max_page_no)))))
                listdirs1.remove(index)
            if cached_videos:
                video_catalogs[_catalog_choice_from_folder(index)] = cached_videos

        stale_cutoff = time.monotonic() - 600
        if len(_output_catalog_dir_cache) > 256:
            for old_key, old_value in list(_output_catalog_dir_cache.items()):
                if old_value.get("last_seen", 0) < stale_cutoff:
                    _output_catalog_dir_cache.pop(old_key, None)

        if not listdirs1 and not video_catalogs:
            result = ([], 0, 0)
            with _output_list_cache_lock:
                _output_list_cache[cache_key] = result
            return result

        videos_list[user_did] = video_catalogs
        if engine_type == 'video':
            output_list = _paginate_catalog_choices(video_catalogs, max_per_page, max_catalog)
            total_nums = sum(len(items) for items in video_catalogs.values())
            output_list = output_list[:max_catalog]
            result = (output_list, total_nums, len(output_list))
            with _output_list_cache_lock:
                _output_list_cache[cache_key] = result
            elapsed_s = time.perf_counter() - start_perf
            if elapsed_s >= 0.2:
                logger.info(f"[Gallery] refresh_output_list elapsed_s={elapsed_s:.2f}, user_did={user_did}, engine_type={engine_type}, total={total_nums}, pages={result[2]}, scanned_dirs={scanned_dirs}, reused_dirs={reused_dirs}")
            return result

        output_list = sorted([f[2:] for f in listdirs1], reverse=True)
        pages = len(output_list)
        display_max_pages = max_catalog
        logger.info(f'Refresh_output_catalog: A total of {total_nums} images and {pages} pages, displaying the latest {pages if pages<display_max_pages else display_max_pages} pages.')
        output_list = output_list[:display_max_pages]

        if user_did not in images_list:
            images_list[user_did] = {}
        if user_did not in images_list_keys:
            images_list_keys[user_did] = []
        if user_did not in images_prompt:
            images_prompt[user_did] = {}
        if user_did not in images_prompt_keys:
            images_prompt_keys[user_did] = []
        if user_did not in images_ads:
            images_ads[user_did] = {}

        result = (output_list, total_nums, pages)
        with _output_list_cache_lock:
            _output_list_cache[cache_key] = result
        elapsed_s = time.perf_counter() - start_perf
        if elapsed_s >= 0.2:
            logger.info(f"[Gallery] refresh_output_list elapsed_s={elapsed_s:.2f}, user_did={user_did}, engine_type={engine_type}, total={total_nums}, pages={pages}, scanned_dirs={scanned_dirs}, reused_dirs={reused_dirs}")
        return result
    except TimeoutError:
        elapsed_s = time.perf_counter() - start_perf
        logger.warning(f"[Gallery] refresh_output_list timeout, returning cached: waited_s={elapsed_s:.2f}, user_did={user_did}, engine_type={engine_type}")
        return cached if cached is not None else ([], 0, 0)
    finally:
        with _output_list_cache_lock:
            _output_list_inflight.discard(cache_key)


def refresh_finished_nums_pages_for_browser(state_params, media_type):
    if not isinstance(state_params, dict):
        return "0,0"
    media_type = "video" if media_type == "video" else "image"
    state_params.setdefault("__max_per_page", 18)
    state_params.setdefault("__max_catalog", config.default_image_catalog_max_number)
    try:
        user = state_params.get("user")
        user_did = user.get_did() if user is not None and hasattr(user, "get_did") else None
        invalidate_output_list_cache(user_did, media_type)
        output_list, finished_nums, finished_pages = refresh_output_list(
            state_params["__max_per_page"],
            state_params["__max_catalog"],
            user_did,
            media_type,
        )
        state_params["__gallery_engine_type"] = media_type
        state_params["__output_list"] = output_list
        state_params["__finished_nums_pages"] = f"{finished_nums},{finished_pages}"
    except Exception as e:
        logger.exception("Refresh finished catalog stat failed: media_type=%r, error=%s", media_type, e)
        state_params.setdefault("__finished_nums_pages", "0,0")
    return state_params.get("__finished_nums_pages", "0,0")


def images_list_update(choice, image_tools_checkbox, state_params):
    util.log_ui_trace(
        logger,
        "[UI-TRACE] gallery.images_list_update.enter | choice=%r, tools=%r, has_output_list=%s, infobox_state=%r, gallery_state=%r, engine_type=%r",
        choice,
        image_tools_checkbox,
        "__output_list" in state_params.keys(),
        state_params.get("infobox_state"),
        state_params.get("gallery_state"),
        get_gallery_engine_type(state_params),
    )
    if "__output_list" not in state_params.keys():
        util.log_ui_trace(logger, "[UI-TRACE] gallery.images_list_update.no_output_list | choice=%r", choice)
        return [
            gr_update(visible=False),
            gr_update(visible=False),
            gr_update(visible=False),
            gr_update(visible=False),
            gr_update(visible=False),
            gr_update(visible=False),
            gr_update(visible=False),
            skip_update(),
            skip_update(),
            gr_update(visible=False),
            gr_update(visible=False),
            gr_update(visible=False),
            gr_update(visible=False),
            gr_update(visible=False),
            gr_update(visible=False),
            gr_update(visible=False),
            gr_update(visible=False),
        ]
    # state_params.update({"infobox_state": 0})
    state_params.update({"note_box_state": ['',0,0]})
    state_params["gallery_preview_open"] = False
    if not should_preserve_post_generation_compare_for_choice(state_params, choice):
        clear_post_generation_result_state(state_params)
    state_params['identity_dialog'] = False
    index_type = get_gallery_engine_type(state_params)
    output_list = state_params["__output_list"]
    if choice is None:
        util.log_ui_trace(logger, "[UI-TRACE] gallery.images_list_update.empty_choice | output_count=%s", len(output_list or []))
        return [gr_update(visible=False), skip_update()] + \
               [gr_update(visible=True), gr_update(visible=False)] + \
               [gr_update(visible=False)] * 3 + \
               [gr.skip(), gr.skip(), gr_update(visible=False)] + \
               [gr_update(visible="hidden")] * 7
    user_did = state_params["user"].get_did()
    state_params.update({"gallery_state": 'finished_index'})
    progress_window_update = skip_update()
    progress_gallery_update = skip_update()
    toolbox_update = gr_update(visible=False)
    if index_type == 'image':
        try:
            image_paths = get_images_from_gallery_index(choice, state_params["__max_per_page"], user_did)
        except Exception as e:
            logger.exception(f'Selected_gallery_catalog: failed to load image catalog:{choice}, error={e}')
            image_paths = []
        if image_paths:
            toolbox_update = _hide_image_toolbox_for_gallery_grid(state_params, "images_list_update.image_grid")
            gallery_result = [gr_update(value=None, visible=False), gr_update(visible=False)]
            progress_window_update = skip_update()
            progress_gallery_update = skip_update()
            util.log_ui_trace(
                logger,
                "[UI-TRACE] gallery.images_list_update.image_paths | choice=%r, images=%s, first=%r, keep_current_preview=True, defer_value=True",
                choice,
                len(image_paths),
                image_paths[0] if image_paths else None,
            )
        else:
            gallery_result = [gr_update(value=None, visible=False), gr_update(visible=False)]
            progress_window_update = skip_update()
            progress_gallery_update = skip_update()
            util.log_ui_trace(
                logger,
                "[UI-TRACE] gallery.images_list_update.no_images | choice=%r, keep_existing_preview=True",
                choice,
            )
        logger.info(f'Selected_gallery_catalog: change image catalog:{choice}, images={len(image_paths)}.')
    elif index_type == 'video':
        try:
            video_paths = get_videos_from_gallery_index(choice, state_params["__max_per_page"], user_did)
        except Exception as e:
            logger.exception(f'Selected_gallery_video: failed to load video catalog:{choice}, error={e}')
            video_paths = []
        gallery_result = [gr_update(visible=False), gr_update(visible=False, value=None)]
        if video_paths:
            toolbox_update = _hide_image_toolbox_for_gallery_grid(state_params, "images_list_update.video_grid")
            progress_window_update = skip_update()
            progress_gallery_update = skip_update()
            util.log_ui_trace(
                logger,
                "[UI-TRACE] gallery.images_list_update.video_paths | choice=%r, videos=%s, first=%r, keep_current_preview=True, defer_value=True",
                choice,
                len(video_paths),
                video_paths[0] if video_paths else None,
            )
        else:
            progress_gallery_update = skip_update()
            util.log_ui_trace(logger, "[UI-TRACE] gallery.images_list_update.no_videos | choice=%r, keep_existing_preview=True", choice)
    else:
        gallery_result = [gr_update(value=None, visible=False), gr_update(visible=False)]
    state_params.update({"prompt_info": [choice, 0]})
    remember_selected_gallery_media_path(choice, 0, state_params)

    infobox_state = state_params.get("infobox_state", False)
    try:
        prompt_meta = get_images_prompt(choice, 0, state_params["__max_per_page"], user_did=user_did, media_type=index_type)
        prompt_info_value = toolbox.make_infobox_markdown(prompt_meta, state_params['__theme'])
    except Exception as e:
        logger.exception(f'Selected_gallery_catalog: failed to load prompt metadata:{choice}, error={e}')
        prompt_info_value = toolbox.make_infobox_markdown(None, state_params['__theme'])

    infobox_updates = [
        gr_update(value=prompt_info_value, visible=infobox_state),
        gr_update(visible=infobox_state),
        gr_update(visible=infobox_state)
    ]
    util.log_ui_trace(
        logger,
        "[UI-TRACE] gallery.images_list_update.exit | choice=%r, index_type=%r, infobox_state=%r, prompt_info_len=%s, output_count=%s",
        choice,
        index_type,
        infobox_state,
        len(prompt_info_value or ""),
        len(output_list or []),
    )

    return gallery_result + [gr_update(visible=len(output_list)>0), toolbox_update] + infobox_updates + [progress_gallery_update, progress_window_update, gr_update(visible=False)] + [gr_update(visible="hidden")] * 7


def images_list_select(choice, image_tools_checkbox, state_params, evt: gr.EventData):
    util.log_ui_trace(
        logger,
        "[UI-TRACE] gallery.images_list_select.enter | choice=%r, evt_index=%r, evt_value=%r",
        choice,
        getattr(evt, "index", None),
        getattr(evt, "value", None),
    )
    return images_list_update(choice, image_tools_checkbox, state_params)


def images_list_fill_gallery(choice, state_params):
    user_did = state_params["user"].get_did()
    engine_type = get_gallery_engine_type(state_params)
    if not choice or engine_type not in ("image", "video"):
        util.log_ui_trace(
            logger,
            "[UI-TRACE] gallery.images_list_fill_gallery.skip | choice=%r, engine_type=%r",
            choice,
            engine_type,
        )
        return gr.skip(), gr.skip()
    try:
        media_paths = (
            get_videos_from_gallery_index(choice, state_params["__max_per_page"], user_did)
            if engine_type == "video"
            else get_images_from_gallery_index(choice, state_params["__max_per_page"], user_did)
        )
    except Exception as e:
        logger.exception(f'Selected_gallery_catalog: failed to fill media catalog:{choice}, engine_type={engine_type}, error={e}')
        media_paths = []
    if not media_paths:
        util.log_ui_trace(logger, "[UI-TRACE] gallery.images_list_fill_gallery.empty | choice=%r, engine_type=%r", choice, engine_type)
        return skip_update(), skip_update()
    util.log_ui_trace(
        logger,
        "[UI-TRACE] gallery.images_list_fill_gallery.exit | choice=%r, engine_type=%r, media=%s, first=%r",
        choice,
        engine_type,
        len(media_paths),
        media_paths[0],
    )
    label = _gallery_media_label(engine_type, state_params)
    return gr_update(value=media_paths, visible=True, label=label, allow_preview=True, preview=False, selected_index=None, fit_columns=False), gr_update(visible=False)


def switch_gallery_engine_type(target_engine_type, *args):
    if len(args) == 3:
        request_marker, image_tools_checkbox, state_params = args
    elif len(args) == 2:
        request_marker = None
        image_tools_checkbox, state_params = args
    else:
        raise TypeError("switch_gallery_engine_type expects image_tools_checkbox and state_params")
    target_engine_type = "video" if target_engine_type == "video" else "image"
    if not _register_gallery_media_switch_request(request_marker, target_engine_type, state_params):
        return _gallery_media_switch_noop_response()

    state_params = dict(state_params or {})
    state_params["__gallery_media_switch_request"] = request_marker
    target_engine_type = "video" if target_engine_type == "video" else "image"
    if "__max_per_page" not in state_params:
        state_params["__max_per_page"] = 18
    if "__max_catalog" not in state_params:
        state_params["__max_catalog"] = config.default_image_catalog_max_number

    max_per_page = state_params["__max_per_page"]
    max_catalog = state_params["__max_catalog"]
    user_did = state_params["user"].get_did()
    state_params["__gallery_engine_type"] = target_engine_type
    state_params["gallery_preview_open"] = False
    state_params["gallery_state"] = "finished_index"
    state_params["identity_dialog"] = False
    clear_post_generation_result_state(state_params)
    state_params.update({"note_box_state": ['', 0, 0]})

    output_list, finished_nums, finished_pages = refresh_output_list(
        max_per_page,
        max_catalog,
        user_did,
        target_engine_type,
    )
    state_params["__output_list"] = output_list
    state_params["__finished_nums_pages"] = f"{finished_nums},{finished_pages}"

    choice = output_list[0] if output_list else None
    media_paths = []
    if choice:
        try:
            media_paths = (
                get_videos_from_gallery_index(choice, max_per_page, user_did)
                if target_engine_type == "video"
                else get_images_from_gallery_index(choice, max_per_page, user_did)
            )
        except Exception as e:
            logger.exception(
                "Switch gallery failed to load media: choice=%r, engine_type=%r, error=%s",
                choice,
                target_engine_type,
                e,
            )
            media_paths = []

    has_media = bool(media_paths)
    state_params["prompt_info"] = [choice, 0]
    set_selected_gallery_media_path(state_params, media_paths[0] if media_paths else None)
    state_params["gallery_preview_open"] = False
    label = _gallery_media_label(target_engine_type, state_params)
    gallery_update = gr_update(value=None, visible=False)
    toolbox_update = _hide_image_toolbox_for_gallery_grid(state_params, "media_switch.grid")

    prompt_info_value = toolbox.make_infobox_markdown(None, state_params.get("__theme", "dark"))
    if has_media:
        try:
            prompt_meta = get_images_prompt(
                choice,
                0,
                max_per_page,
                user_did=user_did,
                media_type=target_engine_type,
            )
            prompt_info_value = toolbox.make_infobox_markdown(prompt_meta, state_params.get("__theme", "dark"))
        except Exception as e:
            logger.exception("Switch gallery failed to load metadata: choice=%r, error=%s", choice, e)

    infobox_state = state_params.get("infobox_state", False)
    progress_window_update = skip_update() if has_media else _empty_gallery_welcome_update(state_params)
    if not _is_gallery_media_switch_request_current(request_marker, target_engine_type, state_params):
        return _gallery_media_switch_noop_response()
    return [
        dropdown_update(choices=output_list, value=choice, visible=bool(output_list)),
        gr_update(visible=True, open=True),
        gr_update(value=media_paths, visible=has_media, label=label, allow_preview=True, preview=False, selected_index=None, fit_columns=False),
        progress_window_update,
        gallery_update,
        gr_update(visible=False),
        toolbox_update,
        gr_update(value=prompt_info_value, visible=infobox_state),
        gr_update(visible=infobox_state),
        gr_update(visible=infobox_state),
        state_params,
        state_params["__finished_nums_pages"],
    ]


def canvas_refresh_after_run(image_tools_checkbox, state_params):
    state_params = state_params or {}
    target_engine_type = get_gallery_engine_type(state_params)
    if "__max_per_page" not in state_params:
        state_params["__max_per_page"] = 18
    if "__max_catalog" not in state_params:
        state_params["__max_catalog"] = config.default_image_catalog_max_number

    max_per_page = state_params["__max_per_page"]
    max_catalog = state_params["__max_catalog"]
    user_did = state_params["user"].get_did()
    state_params["__gallery_engine_type"] = target_engine_type
    state_params["gallery_preview_open"] = False
    state_params["gallery_state"] = "finished_index"
    state_params["identity_dialog"] = False
    clear_post_generation_result_state(state_params)
    state_params.update({"note_box_state": ['', 0, 0]})

    invalidate_output_list_cache(user_did, target_engine_type)
    output_list, finished_nums, finished_pages = refresh_output_list(
        max_per_page,
        max_catalog,
        user_did,
        target_engine_type,
    )
    state_params["__output_list"] = output_list
    state_params["__finished_nums_pages"] = f"{finished_nums},{finished_pages}"

    choice = output_list[0] if output_list else None
    media_paths = []
    if choice:
        try:
            if target_engine_type == "video":
                media_paths = get_videos_from_gallery_index(choice, max_per_page, user_did)
            else:
                output_index = str(choice).split("/")[0]
                refresh_images_catalog(output_index, True, user_did)
                media_paths = get_images_from_gallery_index(choice, max_per_page, user_did)
        except Exception as e:
            logger.exception(
                "Canvas gallery refresh failed to load media: choice=%r, engine_type=%r, error=%s",
                choice,
                target_engine_type,
                e,
            )
            media_paths = []

    has_media = bool(media_paths)
    state_params["prompt_info"] = [choice, 0]
    set_selected_gallery_media_path(state_params, media_paths[0] if media_paths else None)
    state_params["gallery_preview_open"] = False
    toolbox_update = _hide_image_toolbox_for_gallery_grid(state_params, "canvas_refresh.grid")

    prompt_info_value = toolbox.make_infobox_markdown(None, state_params.get("__theme", "dark"))
    if has_media:
        try:
            prompt_meta = get_images_prompt(
                choice,
                0,
                max_per_page,
                user_did=user_did,
                media_type=target_engine_type,
            )
            prompt_info_value = toolbox.make_infobox_markdown(prompt_meta, state_params.get("__theme", "dark"))
        except Exception as e:
            logger.exception("Canvas gallery refresh failed to load metadata: choice=%r, error=%s", choice, e)

    util.log_ui_trace(
        logger,
        "[UI-TRACE] canvas.gallery_refresh.exit | choice=%r, engine_type=%r, media=%s, output_count=%s",
        choice,
        target_engine_type,
        len(media_paths or []),
        len(output_list or []),
    )

    infobox_state = state_params.get("infobox_state", False)
    label = _gallery_media_label(target_engine_type, state_params)
    progress_window_update = skip_update() if has_media else _empty_gallery_welcome_update(state_params)
    return [
        dropdown_update(choices=output_list, value=choice, visible=bool(output_list)),
        gr_update(visible=True, open=True),
        gr_update(value=media_paths, visible=has_media, label=label, allow_preview=True, preview=False, selected_index=None, fit_columns=False),
        progress_window_update,
        gr_update(value=None, visible=False),
        gr_update(visible=False),
        toolbox_update,
        gr_update(value=prompt_info_value, visible=infobox_state),
        gr_update(visible=infobox_state),
        gr_update(visible=infobox_state),
        state_params,
        state_params["__finished_nums_pages"],
    ]


def _parse_main_gallery_browser_payload(payload_json):
    if isinstance(payload_json, dict):
        payload = payload_json
    else:
        try:
            payload = json.loads(payload_json or "{}")
        except Exception:
            payload = {}
    if not isinstance(payload, dict):
        payload = {}
    media_type = "video" if str(payload.get("media_type") or "").lower() == "video" else "image"
    try:
        limit = int(payload.get("limit") or 36)
    except Exception:
        limit = 36
    try:
        offset = int(payload.get("offset") or 0)
    except Exception:
        offset = 0
    limit = max(12, min(limit, 120))
    offset = max(0, offset)
    folder = str(payload.get("folder") or "").strip().replace("\\", "/").strip("/")
    if folder and not folder.startswith("20"):
        folder = _folder_from_catalog_choice(folder)
    query = str(payload.get("query") or "").strip()
    request_id = payload.get("request_id")
    reset = bool(payload.get("reset", True))
    return {
        "media_type": media_type,
        "folder": folder,
        "query": query,
        "offset": offset,
        "limit": limit,
        "request_id": request_id,
        "reset": reset,
    }


def _main_gallery_browser_state_json(**kwargs):
    payload = {"ok": True}
    payload.update(kwargs)
    return json.dumps(payload, ensure_ascii=False)


def get_main_gallery_browser_selected_path(state_params, selected=None):
    if not isinstance(state_params, dict) or state_params.get("gallery_state") != "main_browser":
        return None
    paths = state_params.get("__main_gallery_browser_paths")
    if not isinstance(paths, list) or not paths:
        return None
    if selected is None:
        prompt_info = state_params.get("prompt_info") or [None, 0]
        selected = prompt_info[1] if len(prompt_info) > 1 else 0
    try:
        index = int(selected)
    except Exception:
        index = 0
    if index < 0 or index >= len(paths):
        return None
    path = paths[index]
    return path if path and os.path.isfile(path) else None


def get_main_gallery_browser_selected_metadata(state_params, selected=None):
    path = get_main_gallery_browser_selected_path(state_params, selected)
    if not path:
        return None
    return read_embedded_metadata_from_file(path, get_gallery_engine_type(state_params))


def load_main_gallery_browser_page(payload_json, image_tools_checkbox, state_params):
    state_params = state_params or {}
    request_context = _main_gallery_browser_request_context(state_params)
    payload = _parse_main_gallery_browser_payload(payload_json)
    media_type = payload["media_type"]

    folder = payload["folder"]
    folders = []
    first_probe = None
    if not folder:
        first_probe = canvas_workbench_media_gallery.list_output_media(
            {
                "media_type": media_type,
                "folder": "",
                "query": payload["query"],
                "offset": 0,
                "limit": 1,
                "include_dimensions": False,
                "include_metadata": False,
                "max_seconds": 3.0,
            },
            state_params,
        )
        folders = first_probe.get("folders") or []
        first_items = first_probe.get("items") or []
        if first_items:
            folder = str(first_items[0].get("folder") or "").strip()
        elif folders:
            folder = str(folders[0] or "").strip()

    result = canvas_workbench_media_gallery.list_output_media(
        {
            "media_type": media_type,
            "folder": folder,
            "query": payload["query"],
            "offset": payload["offset"],
            "limit": payload["limit"],
            "include_dimensions": False,
            "include_metadata": False,
            "max_seconds": 3.0,
        },
        state_params,
    )
    if _main_gallery_browser_request_is_stale(request_context):
        return _gallery_browser_load_stale_response(payload, state_params)

    clear_post_generation_result_state(state_params)
    state_params["__gallery_engine_type"] = media_type
    state_params.setdefault("__max_per_page", 18)
    state_params.setdefault("__max_catalog", config.default_image_catalog_max_number)
    if payload["reset"] or "__finished_nums_pages" not in state_params:
        finished_nums_pages = refresh_finished_nums_pages_for_browser(state_params, media_type)
    else:
        finished_nums_pages = state_params.get("__finished_nums_pages", "0,0")
    if not result.get("ok"):
        state_json = _main_gallery_browser_state_json(
            ok=False,
            media_type=media_type,
            folder=folder,
            folders=folders,
            request_id=payload.get("request_id"),
            error=result.get("error") or "Media browser request failed.",
            details=result.get("details") or "",
        )
        return [
            state_json,
            skip_update(),
            skip_update(),
            skip_update(),
            skip_update(),
            skip_update(),
            skip_update(),
            skip_update(),
            skip_update(),
            state_params,
            finished_nums_pages,
        ]

    folders = result.get("folders") or folders
    folder = result.get("folder") or folder
    items = result.get("items") or []
    previous_key = state_params.get("__main_gallery_browser_key")
    browser_key = "{}|{}|{}".format(media_type, folder, payload["query"])
    existing_paths = state_params.get("__main_gallery_browser_paths") or []
    if payload["reset"] or previous_key != browser_key or not isinstance(existing_paths, list):
        existing_paths = []
    seen = set(existing_paths)
    new_paths = []
    for item in items:
        path = item.get("path") if isinstance(item, dict) else None
        if path and path not in seen:
            new_paths.append(path)
            seen.add(path)
    media_paths = existing_paths + new_paths

    state_params["__main_gallery_browser_key"] = browser_key
    state_params["__main_gallery_browser_paths"] = media_paths
    state_params["__main_gallery_browser_folder"] = folder
    state_params["__main_gallery_browser_next_offset"] = result.get("next_offset")
    state_params["__main_gallery_browser_has_more"] = bool(result.get("has_more"))
    state_params["gallery_state"] = "main_browser"
    state_params["gallery_preview_open"] = False
    state_params["identity_dialog"] = False
    state_params.update({"note_box_state": ["", 0, 0]})

    choice = _catalog_choice_from_folder(folder) if folder else None
    state_params["prompt_info"] = [choice, 0]
    set_selected_gallery_media_path(state_params, media_paths[0] if media_paths else None)
    infobox_state = state_params.get("infobox_state", False)
    prompt_meta = read_embedded_metadata_from_file(media_paths[0], media_type) if media_paths else None
    prompt_info_value = toolbox.make_infobox_markdown(prompt_meta, state_params.get("__theme", "dark"))
    label = _gallery_media_label(media_type, state_params)
    state_json = _main_gallery_browser_state_json(
        media_type=media_type,
        folder=folder,
        folders=folders,
        request_id=payload.get("request_id"),
        loaded=len(media_paths),
        received=len(items),
        offset=result.get("offset", payload["offset"]),
        next_offset=result.get("next_offset"),
        has_more=bool(result.get("has_more")),
        truncated=bool(result.get("truncated")),
        query=payload["query"],
    )
    progress_window_update = skip_update() if media_paths else _empty_gallery_welcome_update(state_params)
    return [
        state_json,
        gr_update(value=media_paths, visible=bool(media_paths), label=label, allow_preview=True, preview=False, selected_index=None, fit_columns=False),
        progress_window_update,
        gr_update(value=None, visible=False),
        gr_update(visible=False),
        gr_update(visible=_should_show_image_toolbox(image_tools_checkbox, state_params)),
        gr_update(value=prompt_info_value, visible=infobox_state),
        gr_update(visible=infobox_state),
        gr_update(visible=infobox_state),
        state_params,
        state_params.get("__finished_nums_pages", finished_nums_pages),
    ]


def _load_main_gallery_browser_native(folder, image_tools_checkbox, state_params, offset=0, reset=True):
    state_params = state_params or {}
    request_context = _main_gallery_browser_request_context(state_params)
    media_type = get_gallery_engine_type(state_params)
    limit = 36
    folder = str(folder or state_params.get("__main_gallery_browser_folder") or "").strip().replace("\\", "/").strip("/")
    if folder and not folder.startswith("20"):
        folder = _folder_from_catalog_choice(folder)
    try:
        offset = int(offset or 0)
    except Exception:
        offset = 0
    offset = max(0, offset)
    if reset:
        offset = 0

    result = canvas_workbench_media_gallery.list_output_media(
        {
            "media_type": media_type,
            "folder": folder,
            "offset": offset,
            "limit": limit,
            "include_dimensions": False,
            "include_metadata": False,
            "max_seconds": 3.0,
        },
        state_params,
    )
    folders = result.get("folders") or []
    if _main_gallery_browser_request_is_stale(request_context):
        return _gallery_browser_native_stale_response(state_params, "_load_main_gallery_browser_native")

    if reset or "__finished_nums_pages" not in state_params:
        finished_nums_pages = refresh_finished_nums_pages_for_browser(state_params, media_type)
    else:
        finished_nums_pages = state_params.get("__finished_nums_pages", "0,0")
    if not result.get("ok"):
        clear_post_generation_result_state(state_params)
        status = "Load failed" if _gallery_lang(state_params) == "en" else "加载失败"
        prev_update, next_update = _main_gallery_browser_nav_updates(folders, folder)
        return [
            dropdown_update(choices=folders, value=folder or None),
            prev_update,
            next_update,
            gr_update(value=status),
            gr_update(interactive=False),
            skip_update(),
            skip_update(),
            skip_update(),
            skip_update(),
            skip_update(),
            skip_update(),
            skip_update(),
            skip_update(),
            state_params,
            finished_nums_pages,
        ]

    folder = result.get("folder") or folder
    if not folder and folders:
        folder = folders[0]
        result = canvas_workbench_media_gallery.list_output_media(
            {
                "media_type": media_type,
                "folder": folder,
                "offset": 0,
                "limit": limit,
                "include_dimensions": False,
                "include_metadata": False,
                "max_seconds": 3.0,
            },
            state_params,
        )
        folders = result.get("folders") or folders

    if _main_gallery_browser_request_is_stale(request_context):
        return _gallery_browser_native_stale_response(state_params, "_load_main_gallery_browser_native")

    clear_post_generation_result_state(state_params)
    prev_update, next_update = _main_gallery_browser_nav_updates(folders, folder)
    items = result.get("items") or []
    previous_key = state_params.get("__main_gallery_browser_key")
    browser_key = "{}|{}".format(media_type, folder)
    existing_paths = state_params.get("__main_gallery_browser_paths") or []
    if reset or previous_key != browser_key or not isinstance(existing_paths, list):
        existing_paths = []
    seen = set(existing_paths)
    new_paths = []
    for item in items:
        path = item.get("path") if isinstance(item, dict) else None
        if path and path not in seen:
            new_paths.append(path)
            seen.add(path)
    media_paths = existing_paths + new_paths

    state_params["__main_gallery_browser_key"] = browser_key
    state_params["__main_gallery_browser_paths"] = media_paths
    state_params["__main_gallery_browser_folder"] = folder
    state_params["__main_gallery_browser_next_offset"] = result.get("next_offset")
    state_params["__main_gallery_browser_has_more"] = bool(result.get("has_more"))
    state_params["gallery_state"] = "main_browser"
    state_params["gallery_preview_open"] = False
    state_params["identity_dialog"] = False
    state_params.update({"note_box_state": ["", 0, 0]})

    choice = _catalog_choice_from_folder(folder) if folder else None
    state_params["prompt_info"] = [choice, 0]
    set_selected_gallery_media_path(state_params, media_paths[0] if media_paths else None)
    infobox_state = state_params.get("infobox_state", False)
    prompt_meta = read_embedded_metadata_from_file(media_paths[0], media_type) if media_paths else None
    prompt_info_value = toolbox.make_infobox_markdown(prompt_meta, state_params.get("__theme", "dark"))
    label = _gallery_media_label(media_type, state_params)
    status = _gallery_browser_count_status(len(media_paths), media_type, state_params)
    progress_window_update = skip_update() if media_paths else _empty_gallery_welcome_update(state_params)

    return [
        dropdown_update(choices=folders, value=folder or None),
        prev_update,
        next_update,
        gr_update(value=status),
        gr_update(interactive=bool(result.get("has_more"))),
        gr_update(value=media_paths, visible=bool(media_paths), label=label, allow_preview=True, preview=False, selected_index=None, fit_columns=False),
        progress_window_update,
        gr_update(value=None, visible=False),
        gr_update(visible=False),
        gr_update(visible=_should_show_image_toolbox(image_tools_checkbox, state_params)),
        gr_update(value=prompt_info_value, visible=infobox_state),
        gr_update(visible=infobox_state),
        gr_update(visible=infobox_state),
        state_params,
        state_params.get("__finished_nums_pages", finished_nums_pages),
    ]


def _main_gallery_browser_nav_updates(folders, folder):
    folders = [str(item or "") for item in (folders or []) if item]
    folder = str(folder or "")
    try:
        index = folders.index(folder)
    except ValueError:
        index = -1
    has_newer = index > 0
    has_older = index >= 0 and index + 1 < len(folders)
    return gr_update(interactive=has_newer), gr_update(interactive=has_older)


def _step_main_gallery_browser_folder(folder, image_tools_checkbox, state_params, delta):
    state_params = state_params or {}
    media_type = get_gallery_engine_type(state_params)
    current = str(folder or state_params.get("__main_gallery_browser_folder") or "").strip().replace("\\", "/").strip("/")
    if current and not current.startswith("20"):
        current = _folder_from_catalog_choice(current)
    try:
        result = canvas_workbench_media_gallery.list_output_media(
            {
                "media_type": media_type,
                "folder": "",
                "offset": 0,
                "limit": 12,
                "include_dimensions": False,
                "include_metadata": False,
                "max_seconds": 0.75,
            },
            state_params,
        )
        folders = result.get("folders") or []
    except Exception:
        folders = []
    if not folders:
        return _load_main_gallery_browser_native(current, image_tools_checkbox, state_params, offset=0, reset=True)
    try:
        index = folders.index(current)
    except ValueError:
        index = 0
    target_index = max(0, min(len(folders) - 1, index + int(delta or 0)))
    return _load_main_gallery_browser_native(folders[target_index], image_tools_checkbox, state_params, offset=0, reset=True)


def previous_main_gallery_browser_folder(folder, image_tools_checkbox, state_params):
    return _step_main_gallery_browser_folder(folder, image_tools_checkbox, state_params, -1)


def next_main_gallery_browser_folder(folder, image_tools_checkbox, state_params):
    return _step_main_gallery_browser_folder(folder, image_tools_checkbox, state_params, 1)


def refresh_main_gallery_browser(folder, image_tools_checkbox, state_params):
    return _load_main_gallery_browser_native(folder, image_tools_checkbox, state_params, offset=0, reset=True)


def load_main_gallery_browser_folder(folder, image_tools_checkbox, state_params):
    return _load_main_gallery_browser_native(folder, image_tools_checkbox, state_params, offset=0, reset=True)


def load_more_main_gallery_browser(folder, image_tools_checkbox, state_params):
    next_offset = 0
    if isinstance(state_params, dict):
        next_offset = state_params.get("__main_gallery_browser_next_offset") or len(state_params.get("__main_gallery_browser_paths") or [])
    return _load_main_gallery_browser_native(folder, image_tools_checkbox, state_params, offset=next_offset, reset=False)


def select_index(choice, image_tools_checkbox, state_params, evt: gr.EventData):
    if "__output_list" in state_params.keys():
        state_params.update({"infobox_state": 0})
        state_params.update({"note_box_state": ['',0,0]})
    logger.info(f'Selected_gallery_catalog: change image catalog:{choice}.')
    state_params.update({"gallery_state": 'finished_index'})
    state_params["gallery_preview_open"] = False
    clear_post_generation_result_state(state_params)
    state_params['identity_dialog'] = False
    index_type = get_gallery_engine_type(state_params)

    infobox_state = state_params.get("infobox_state", False)
    infobox_updates = [
        gr_update(visible=infobox_state),
        gr_update(visible=infobox_state),
        gr_update(visible=infobox_state)
    ]
    return [gr_update(visible=index_type=='image'), gr_update(visible=index_type=='video')] + [gr_update(visible=False)] + infobox_updates + [gr_update(visible=False)] * 4 + [gr_update(visible="hidden")] * 7


def select_gallery(choice, image_tools_checkbox, state_params, backfill_prompt, evt: gr.EventData):
    if "__output_list" not in state_params.keys():
        return [skip_update() for _ in range(13)] + [state_params]
    state_params.update({"note_box_state": ['',0,0]})
    state_params["gallery_preview_open"] = False
    selected_index = normalize_gallery_selected_index(getattr(evt, "index", 0))
    if choice is None and len(state_params["__output_list"]) > 0:
        choice = state_params["__output_list"][0]
    state_params.update({"prompt_info": [choice, selected_index]})
    remember_selected_gallery_media_path(choice, selected_index, state_params)
    result = get_images_prompt(choice, selected_index, state_params["__max_per_page"], True, state_params["user"].get_did(), media_type="image")
    prompt_value = _metadata_prompt_value(result, "Prompt", "prompt")
    negative_value = _metadata_prompt_value(result, "Negative Prompt", "negative_prompt")
    if backfill_prompt and prompt_value is not None:
        gr_prompt_results =  [gr_update(value=prompt_value), gr_update(value=negative_value or "")]
    else:
        gr_prompt_results = [skip_update(), skip_update()]

    infobox_state = state_params.get("infobox_state", False)
    infobox_updates = [
        gr_update(value=toolbox.make_infobox_markdown(result, state_params['__theme']), visible=infobox_state),
        gr_update(visible=infobox_state),
        gr_update(visible=infobox_state)
    ]
    toolbox_update = _hide_image_toolbox_for_gallery_grid(state_params, "select_gallery.grid")
    return infobox_updates + gr_prompt_results + [gr_update(visible="hidden")] * 7 + [toolbox_update, state_params]

def _prompt_backfill_updates(result, backfill_prompt, allow_backfill=True):
    prompt_value = _metadata_prompt_value(result, "Prompt", "prompt")
    negative_value = _metadata_prompt_value(result, "Negative Prompt", "negative_prompt")
    if allow_backfill and backfill_prompt and prompt_value is not None:
        return [gr_update(value=prompt_value), gr_update(value=negative_value or "")]
    return [skip_update(), skip_update()]


def _metadata_prompt_value(result, *keys):
    if not isinstance(result, dict):
        return None
    empty_value = None
    for key in keys:
        value = result.get(key)
        if isinstance(value, str):
            if value.strip():
                return value
            if empty_value is None:
                empty_value = value
    return empty_value


def select_gallery_progress(image_tools_checkbox, state_params, backfill_prompt, evt: gr.EventData):
    state_params.update({"note_box_state": ['',0,0]})
    state_params["gallery_preview_open"] = False

    selected_index = normalize_gallery_selected_index(getattr(evt, "index", 0))
    if state_params.get("gallery_state") == "main_browser":
        clear_post_generation_result_state(state_params)
        choice = state_params.get("__main_gallery_browser_folder")
        if choice:
            choice = _catalog_choice_from_folder(choice)
        state_params.update({"prompt_info": [choice, selected_index]})
        remember_selected_gallery_media_path(choice, selected_index, state_params)
        result = get_main_gallery_browser_selected_metadata(state_params, selected_index) or {}
        infobox_state = state_params.get("infobox_state", False)
        infobox_updates = [
            gr_update(value=toolbox.make_infobox_markdown(result, state_params['__theme']), visible=infobox_state),
            gr_update(visible=infobox_state),
            gr_update(visible=infobox_state)
        ]
        toolbox_update = _hide_image_toolbox_for_gallery_grid(state_params, "select_gallery_progress.main_browser_grid")
        return infobox_updates + _prompt_backfill_updates(result, backfill_prompt) + [gr_update(visible="hidden")] * 7 + [toolbox_update, state_params]

    choice = None
    if state_params.get("gallery_state") == "finished_index":
        choice = state_params.get("prompt_info", [None, 0])[0]
    if choice is None and "__output_list" in state_params and len(state_params["__output_list"]) > 0:
        choice = state_params["__output_list"][0]

    state_params.update({"prompt_info": [choice, selected_index]})
    remember_selected_gallery_media_path(choice, selected_index, state_params)
    result = get_images_prompt(choice, selected_index, state_params["__max_per_page"], user_did=state_params["user"].get_did(), media_type=get_gallery_engine_type(state_params))

    infobox_state = state_params.get("infobox_state", False)
    infobox_updates = [
        gr_update(value=toolbox.make_infobox_markdown(result, state_params['__theme']), visible=infobox_state),
        gr_update(visible=infobox_state),
        gr_update(visible=infobox_state)
    ]
    toolbox_update = _hide_image_toolbox_for_gallery_grid(state_params, "select_gallery_progress.finished_grid")
    allow_backfill = not bool(state_params.get("__post_generation_has_output"))
    return infobox_updates + _prompt_backfill_updates(result, backfill_prompt, allow_backfill=allow_backfill) + [gr_update(visible="hidden")] * 7 + [toolbox_update, state_params]


def get_images_from_gallery_index(choice, max_per_page, user_did=None):
    global images_list

    if choice is None:
        return []
    if not user_did:
        user_did = shared.token.get_guest_did()
    if user_did not in images_list:
        images_list[user_did]={}

    page = 0
    _page = choice.split("/")
    if len(_page) > 1:
        choice = _page[0]
        page = int(_page[1])

    images_gallery = refresh_images_catalog(choice, user_did=user_did)
    nums = len(images_gallery)
    if nums == 0:
        return []
    if page > 0:
        page = abs(page-math.ceil(nums/max_per_page))+1
        if page*max_per_page < nums:
            images_gallery = images_list[user_did][choice][(page-1)*max_per_page:page*max_per_page]
        else:
            images_gallery = images_list[user_did][choice][nums-max_per_page:]
    user_path_outputs = config.get_user_path_outputs(user_did)
    images_gallery = [os.path.join(os.path.join(user_path_outputs, "20{}".format(choice)), f) for f in images_gallery]
    return images_gallery


def get_media_path_from_gallery_index(choice, selected, max_per_page, user_did=None, media_type=None):
    if choice is None:
        return None
    if not user_did:
        user_did = shared.token.get_guest_did()
    try:
        selected = int(selected)
    except Exception:
        selected = 0

    if media_type == "video":
        video_rel_path = _get_video_rel_path_from_gallery_index(choice, selected, max_per_page, user_did)
        if not video_rel_path:
            return None
        return os.path.join(config.get_user_path_outputs(user_did), video_rel_path)

    image_paths = get_images_from_gallery_index(choice, max_per_page, user_did)
    if not image_paths:
        return None
    selected = max(0, min(selected, len(image_paths) - 1))
    return image_paths[selected]


def _get_ffmpeg_exe():
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except Exception:
        pass
    return shutil.which("ffmpeg")


def _unescape_ffmetadata(value):
    result = []
    escaped = False
    for char in str(value or ""):
        if escaped:
            result.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        else:
            result.append(char)
    if escaped:
        result.append("\\")
    return "".join(result)


def _read_video_ffmetadata(file_path):
    ffmpeg_exe = _get_ffmpeg_exe()
    if not ffmpeg_exe:
        return {}
    try:
        proc = subprocess.run(
            [ffmpeg_exe, "-v", "error", "-i", file_path, "-f", "ffmetadata", "-"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except Exception as e:
        logger.info("Read embedded video metadata failed: file=%s err=%s", file_path, e)
        return {}
    if not proc.stdout:
        return {}

    fields = {}
    for raw_line in proc.stdout.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        fields[_unescape_ffmetadata(key)] = _unescape_ffmetadata(value)
    return fields


def _normalize_embedded_parameters(parameters, metadata_scheme, file_path):
    if parameters is None:
        return None

    try:
        parsed = meta_parser.normalize_metadata_parameters(parameters, metadata_scheme)
    except Exception as e:
        logger.info("Read embedded metadata parser fallback: file=%s scheme=%s err=%s", file_path, metadata_scheme, e)
        parsed = copy.deepcopy(parameters) if isinstance(parameters, dict) else None

    if not isinstance(parsed, dict):
        return None
    parsed.setdefault("Filename", os.path.basename(file_path))
    return parsed


def _read_image_embedded_metadata(file_path):
    try:
        with Image.open(file_path) as image:
            parameters, metadata_scheme = meta_parser.read_info_from_image(image)
        return _normalize_embedded_parameters(parameters, metadata_scheme, file_path)
    except Exception as e:
        logger.info("Read embedded image metadata failed: file=%s err=%s", file_path, e)
    return None


def _read_video_embedded_metadata(file_path):
    fields = _read_video_ffmetadata(file_path)
    if not fields:
        return None
    metadata_scheme = fields.get("metadata_scheme") or fields.get("fooocus_scheme")
    for key in ("simpleai_metadata", "prompt", "comment"):
        raw = fields.get(key)
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = raw
        if isinstance(parsed, dict) and isinstance(parsed.get("prompt"), dict):
            parsed = parsed.get("prompt")
        normalized = _normalize_embedded_parameters(parsed, metadata_scheme or "simple", file_path)
        if normalized:
            return normalized
    return None


def read_embedded_metadata_from_file(file_path, media_type=None):
    if not file_path or not os.path.isfile(file_path):
        return None
    ext = os.path.splitext(file_path)[1].lower()
    if media_type == "video" or ext in video_types:
        metadata = _read_video_embedded_metadata(file_path)
    else:
        metadata = _read_image_embedded_metadata(file_path)
    if metadata is None:
        metadata = {"Filename": os.path.basename(file_path)}
    return metadata


def get_embedded_media_metadata(choice, selected, max_per_page, user_did=None, media_type=None):
    media_path = get_media_path_from_gallery_index(choice, selected, max_per_page, user_did, media_type)
    return read_embedded_metadata_from_file(media_path, media_type)


def refresh_images_catalog(choice: str, passthrough = False, user_did=None):
    global images_list, images_list_keys, image_types

    if not user_did:
        user_did = shared.token.get_guest_did()
    if user_did not in images_list:
        images_list[user_did]={}
    if user_did not in images_list_keys:
        images_list_keys[user_did]=[]

    if not passthrough and choice in images_list_keys[user_did]:
        images_list_keys[user_did].remove(choice)
        images_list_keys[user_did].append(choice)
        return images_list[user_did][choice]
    user_path_outputs = config.get_user_path_outputs(user_did)
    images_list_new = sorted([f for f in util.get_files_from_folder(os.path.join(user_path_outputs, "20{}".format(choice)), image_types, None)], reverse=True)
    if len(images_list_new)==0:
        if choice in images_list_keys[user_did]:
            images_list_keys[user_did].pop(images_list_keys[user_did].index(choice))
            images_list[user_did].pop(choice)
        return []
    if choice in images_list_keys[user_did]:
        images_list_keys[user_did].pop(images_list_keys[user_did].index(choice))
    if len(images_list[user_did].keys())>15:
        images_list[user_did].pop(images_list_keys[user_did].pop(0))
    images_list[user_did].update({choice: images_list_new})
    images_list_keys[user_did].append(choice)
    logger.info(f'Refresh_images_catalog: loaded {len(images_list[user_did][choice])} image_items of {choice}.')
    return images_list[user_did][choice]


def get_images_prompt(choice, selected, max_per_page, display_index=False, user_did=None, media_type=None):
    if choice is None:
        return None
    if not user_did:
        user_did = shared.token.get_guest_did()

    media_path = get_media_path_from_gallery_index(choice, selected, max_per_page, user_did, media_type)
    metainfo = read_embedded_metadata_from_file(media_path, media_type) if media_path else None
    if display_index:
        logger.info(
            "The media selected: catalog=%s, selected=%s, media_type=%s, file=%s, metadata_keys=%s",
            choice,
            selected,
            media_type or "image",
            media_path,
            len(metainfo or {}),
        )
    return metainfo or {}


def parse_html_log(choice: str, passthrough = False, user_did=None):
    global images_prompt, images_prompt_keys, images_ads
    
    if not user_did:
        user_did = shared.token.get_guest_did()
    if user_did not in images_prompt:
        images_prompt[user_did]={}
    if user_did not in images_prompt_keys:
        images_prompt_keys[user_did]=[]
    if user_did not in images_ads:
        images_ads[user_did]={}

    choice = choice.split('/')[0]
    if not passthrough and choice in images_prompt_keys[user_did] and images_prompt[user_did].get(choice):
        images_prompt_keys[user_did].remove(choice)
        images_prompt_keys[user_did].append(choice)
        return
    user_path_outputs = config.get_user_path_outputs(user_did)
    gallery_dir = os.path.join(user_path_outputs, "20{}".format(choice))
    html_file = os.path.join(gallery_dir, 'log.html')
    html_files = []
    if os.path.exists(html_file):
        html_files.append(html_file)
    if os.path.isdir(gallery_dir):
        try:
            archived_logs = [
                os.path.join(gallery_dir, entry.name)
                for entry in os.scandir(gallery_dir)
                if entry.is_file() and entry.name.startswith('log_') and entry.name.lower().endswith('.html')
            ]
            html_files.extend(sorted(archived_logs, reverse=True))
        except OSError:
            pass
    if not html_files:
        return
    prompt_infos = []
    for html_file in html_files:
        try:
            html = etree.parse(html_file, etree.HTMLParser(encoding='utf-8'))
            prompt_infos.extend((html_file, info) for info in html.xpath('/html/body/div'))
        except Exception as e:
            logger.warning(f'Parse_html_log: failed to parse {html_file}: {e}')
    images_prompt_list = {}
    images_prompt_list[user_did] = {}
    for html_file, info in prompt_infos:
        text = info.xpath('.//p//text()')
        #print(f'log_parse_text1:{text}')
        if len(text)>20:
            def standardized(x):
                if x.startswith(', '):
                    x=x[2:]
                if x.endswith(': '):
                    x=x[:-2]
                if x==' ':
                    x=''
                return x
            text = list(map(standardized, info.xpath('.//p//text()')))
            if text[6]!='':
                text.insert(6, '')
            if text[8]=='':
                text.insert(8, '')
            info_dict={"Filename":text[0]}
            if text[3]=='':
                info_dict[text[1]] = text[2]
                info_dict[text[4]] = text[5]
                info_dict[text[7]] = text[8]
                for i in range(0,int(len(text)/2)-5):
                    info_dict[text[10+i*2]] = text[11+i*2]
            else:
                if text[4]!='Fooocus V2 Expansion':
                    del text[6]
                else:
                    text.insert(4, '')
                    if text[6]=='Styles':
                        text.insert(6, '')
                        del text[8]
                    else:
                        del text[7]
                for i in range(0,int(len(text)/2)-1):
                    info_dict[text[1+i*2]] = text[2+i*2]
        else:
            text = info.xpath('.//td//text()')
            #print(f'log_parse_text2:{text}')
            if len(text)>10:
                if text[2]=='\n' or text[2]=='\r\n':
                    text.insert(2, '')
                if text[5]=='\n' or text[5]=='\r\n':
                    text.insert(5, '')
                if text[8]=='\n' or text[8]=='\r\n':
                    text.insert(8, '')
                if text[29]=='\n' or text[29]=='\r\n':
                    text.insert(29, '')
                if text[32]=='\n' or text[32]=='\r\n':
                    text.insert(32, '')
                if text[35]=='\n' or text[35]=='\r\n':
                    text.insert(35, '')
                if text[41]=='\n' or text[41]=='\r\n':
                    text.insert(41, '')
                info_dict={"Filename":text[0]}
                for i in range(0,int(len(text)/3)):
                    key = text[1+i*3].strip()
                    value = text[2+i*3].strip()
                    if key == '' or key is None or key == 'Full raw prompt' or key == 'Positive' or key == 'Negative':
                        continue
                    info_dict[key] = value
            else:
                if 'Upscale (Fast)' not in text:
                    logger.info(f'Parse_html_log: Parse error for {choice}, file={html_file}\ntext:{info.xpath(".//text()")}')
                info_dict={"Filename":text[1]}
                info_dict[text[2]] = text[3]
        #print(f'{len(text)},info_dict={info_dict}')
        images_prompt_list[user_did].update({info_dict["Filename"]: info_dict})
    if len(images_prompt_list[user_did].keys())==0:
        if choice in images_prompt[user_did].keys():
            images_prompt_keys[user_did].pop(images_prompt_keys[user_did].index(choice))
            images_prompt[user_did].pop(choice)
            if choice in images_ads[user_did].keys():
                images_ads[user_did].pop(choice)
        return
    if choice in images_prompt_keys[user_did]:
        images_prompt_keys[user_did].pop(images_prompt_keys[user_did].index(choice))
    if len(images_prompt[user_did].keys())>15:
        key = images_prompt_keys[user_did].pop(0)
        images_prompt[user_did].pop(key)
        if key in images_ads[user_did].keys():
            images_ads[user_did].pop(key)
    images_prompt[user_did].update({choice: images_prompt_list[user_did]})
    images_prompt_keys[user_did].append(choice)
    
    dirname, filename = os.path.split(html_file)
    log_name = os.path.join(dirname, "log_ads.json")
    log_ext = {}
    if os.path.exists(log_name):
        with open(log_name, "r", encoding="utf-8") as log_file:
            log_ext.update(json.load(log_file))
    images_ads[user_did].update({choice: log_ext})
    
    logger.info(f'Parse_html_log: loaded {len(images_prompt[user_did][choice])} image_infos of {choice}.')
    return
