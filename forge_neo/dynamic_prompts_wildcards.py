from __future__ import annotations

import json
import html as html_lib
import os
import shutil
import time
from pathlib import Path
from typing import Any

import gradio as gr

from forge_neo.dynamic_prompts_compat import DYNAMIC_PROMPTS_EXTENSION_ROOT


LOAD_FILE_ACTION = "load file"
LOAD_TREE_ACTION = "load tree"
MESSAGE_PROCESSING_ACTION = "message processing"
SAVE_FILE_ACTION = "save wildcard"
TEXT_SUFFIXES = {".txt", ".yaml", ".yml"}


def _normalize_lang(value: object | None) -> str:
    return "en" if str(value or "").strip().lower().startswith("en") else "cn"


def _wildcards_label(lang: object | None, en: str, cn: str) -> str:
    return en if _normalize_lang(lang) == "en" else cn


def _wildcards_help_html(lang: object | None) -> str:
    wildcard_dir = html_lib.escape(str(_wildcard_dir()), quote=False)
    if _normalize_lang(lang) == "en":
        items = [
            "Use Collection actions to copy a built-in collection and create a wildcard library.",
            "Select a file in the list below to edit it.",
            "Copy text from the file name input or the Wildcards file textbox to use wildcards in prompts.",
            f"You can also put your own wildcard files in the {wildcard_dir} folder.",
        ]
    else:
        items = [
            "通过“合集操作”中的下拉菜单复制合集选项，创建通配符库。",
            "选择下方列表中的文件来进行编辑。",
            "通过输入文件名或从“通配符文件”文本框中复制文本来在脚本中使用通配符。",
            f"也可以将自己的通配符文件放入 {wildcard_dir} 文件夹。",
        ]
    return "<ol>" + "".join(f"<li>{item}</li>" for item in items) + "</ol>"


def _wildcard_dir() -> Path:
    env_value = os.environ.get("FORGE_NEO_DYNAMIC_PROMPTS_WILDCARD_DIR", "").strip()
    if env_value:
        path = Path(env_value).expanduser()
    else:
        try:
            from modules.shared import opts

            option_value = getattr(opts, "wildcard_dir", None)
        except Exception:
            option_value = None
        path = Path(option_value).expanduser() if option_value else DYNAMIC_PROMPTS_EXTENSION_ROOT / "wildcards"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _collections_dir() -> Path:
    return DYNAMIC_PROMPTS_EXTENSION_ROOT / "collections"


def _collection_dirs() -> dict[str, Path]:
    root = _collections_dir()
    if not root.is_dir():
        return {}
    return {
        item.relative_to(root).as_posix(): item
        for item in sorted(root.iterdir(), key=lambda value: value.name.lower())
        if item.is_dir()
    }


def _payload(*, action: str, success: bool, **values: Any) -> str:
    return json.dumps(
        {
            "id": int(time.time() * 1000),
            "action": action,
            "success": success,
            **values,
        },
        ensure_ascii=False,
    )


def _wildcard_name(path: Path, root: Path) -> str:
    rel = path.relative_to(root).as_posix()
    suffix = path.suffix
    if suffix in TEXT_SUFFIXES:
        rel = rel[: -len(suffix)]
    return rel


def _wrapped_name(name: str) -> str:
    return f"__{name.strip().strip('_')}__"


def _insert_tree_node(nodes: list[dict[str, Any]], parts: list[str], full_name: str) -> None:
    if not parts:
        return
    if len(parts) == 1:
        nodes.append({"name": full_name, "wrappedName": _wrapped_name(full_name), "children": []})
        return
    head = parts[0]
    branch = next((item for item in nodes if item.get("name") == head and item.get("children")), None)
    if branch is None:
        branch = {"name": head, "children": []}
        nodes.append(branch)
    _insert_tree_node(branch["children"], parts[1:], full_name)


def _wildcard_tree() -> tuple[list[dict[str, Any]], int]:
    root = _wildcard_dir()
    nodes: list[dict[str, Any]] = []
    count = 0
    files = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES and not any(part.startswith(".") for part in path.relative_to(root).parts)
    ]
    for path in sorted(files, key=lambda value: value.relative_to(root).as_posix().lower()):
        name = _wildcard_name(path, root)
        _insert_tree_node(nodes, name.split("/"), name)
        count += 1
    return nodes, count


def _safe_relative_name(value: object) -> str:
    name = str(value or "").strip()
    if name.startswith("__") and name.endswith("__") and len(name) > 4:
        name = name[2:-2]
    name = name.replace("\\", "/").strip("/")
    if not name or name.startswith(".") or "/../" in f"/{name}/" or name.startswith("../"):
        raise ValueError("Invalid wildcard name")
    return name


def _wildcard_file(name: object, *, existing: bool = True) -> Path:
    root = _wildcard_dir().resolve()
    clean = _safe_relative_name(name)
    raw = root / clean
    candidates = [raw] if raw.suffix else [raw, raw.with_suffix(".txt"), raw.with_suffix(".yaml"), raw.with_suffix(".yml")]
    for candidate in candidates:
        resolved = candidate.resolve()
        if root not in resolved.parents and resolved != root:
            raise ValueError("Wildcard path is outside wildcard directory")
        if resolved.is_file():
            return resolved
    if existing:
        raise FileNotFoundError(clean)
    target = (raw if raw.suffix else raw.with_suffix(".txt")).resolve()
    if root not in target.parents:
        raise ValueError("Wildcard path is outside wildcard directory")
    return target


def refresh_wildcards_callback() -> str:
    tree, count = _wildcard_tree()
    return _payload(action=LOAD_TREE_ACTION, success=True, tree=tree, collection_count=count)


def handle_load_wildcard(event: dict[str, Any]) -> str:
    path = _wildcard_file(event.get("name"))
    try:
        contents = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        contents = path.read_text(encoding="utf-8", errors="replace")
    name = _wildcard_name(path, _wildcard_dir().resolve())
    return _payload(
        action=LOAD_FILE_ACTION,
        success=True,
        contents=contents,
        can_edit=True,
        name=name,
        wrapped_name=_wrapped_name(name),
    )


def handle_message(event_text: str) -> str:
    try:
        event = json.loads(str(event_text or "{}"))
        action = str(event.get("action") or "")
        if action == LOAD_FILE_ACTION:
            return handle_load_wildcard(event)
        if action == SAVE_FILE_ACTION:
            return save_file_callback(event_text)
        raise ValueError(f"Unknown event: {action}")
    except Exception as exc:
        return _payload(action=MESSAGE_PROCESSING_ACTION, success=False, message=f"{type(exc).__name__}: {exc}")


def save_file_callback(event_text: str) -> str:
    try:
        event = json.loads(str(event_text or "{}"))
        wildcard = event.get("wildcard") if isinstance(event.get("wildcard"), dict) else {}
        path = _wildcard_file(wildcard.get("name"), existing=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(event.get("contents") or "").strip() + "\n", encoding="utf-8")
        return handle_load_wildcard({"name": wildcard.get("name")})
    except Exception as exc:
        return _payload(action=SAVE_FILE_ACTION, success=False, message=f"{type(exc).__name__}: {exc}")


def copy_collection_callback(overwrite: bool, collection: str) -> str:
    try:
        collections = _collection_dirs()
        source = collections.get(str(collection or ""))
        if source is None:
            return _payload(action="copy collection", success=False, message="Collection not found.")
        target_root = _wildcard_dir() / str(collection)
        for source_file in source.rglob("*"):
            if not source_file.is_file():
                continue
            target = target_root / source_file.relative_to(source)
            if target.exists() and not overwrite:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target)
        return refresh_wildcards_callback()
    except Exception as exc:
        return _payload(action="copy collection", success=False, message=f"{type(exc).__name__}: {exc}")


def delete_tree_callback(event_text: str) -> str:
    try:
        event = json.loads(str(event_text or "{}"))
        if not bool(event.get("sure")):
            return _payload(action="delete tree", success=False, message="Delete cancelled.")
        path = _wildcard_dir()
        try:
            from send2trash import send2trash

            send2trash(str(path))
        except Exception:
            deleted = path.with_name(f"{path.name}.deleted-{int(time.time())}")
            if path.exists():
                path.rename(deleted)
        path.mkdir(parents=True, exist_ok=True)
        return refresh_wildcards_callback()
    except Exception as exc:
        return _payload(action="delete tree", success=False, message=f"{type(exc).__name__}: {exc}")


def create_dynamic_prompts_wildcards_tab(*, visible: bool, lang: object | None = None) -> None:
    with gr.Tab(_wildcards_label(lang, "Wildcards Manager", "通配符管理"), id="sddp-wildcard-manager", elem_id="tab_sddp-wildcard-manager", visible=visible):
        with gr.Row(elem_classes=["forge-neo-wildcards-manager"]):
            with gr.Column(scale=3, min_width=360, elem_classes=["forge-neo-wildcards-left"]):
                gr.Textbox(
                    placeholder=_wildcards_label(lang, "Search in wildcard names...", "使用通配符名称检索..."),
                    elem_id="sddp-wildcard-search",
                    label="",
                    lines=1,
                    max_lines=1,
                    show_label=False,
                    container=False,
                )
                gr.HTML("Loading...", elem_id="sddp-wildcard-tree")
                with gr.Accordion(_wildcards_label(lang, "Help", "帮助"), open=True, elem_id="sddp-wildcard-help-accordion"):
                    gr.HTML(_wildcards_help_html(lang), elem_id="sddp-wildcard-help-text")
                with gr.Accordion(_wildcards_label(lang, "Collection actions", "合集操作"), open=True, elem_id="sddp-wildcard-collection-actions"):
                    collection_dropdown = gr.Dropdown(
                        choices=sorted(_collection_dirs()),
                        type="value",
                        label=_wildcards_label(lang, "Select a collection", "选择集合"),
                        elem_id="sddp-wildcard-collection-dropdown",
                    )
                    with gr.Row():
                        collection_copy_button = gr.Button(_wildcards_label(lang, "Copy collection", "复制集合"), scale=1, elem_id="sddp-wildcard-copy-collection-button")
                        overwrite_checkbox = gr.Checkbox(label=_wildcards_label(lang, "Overwrite existing", "覆写已有项"), value=False, elem_id="sddp-wildcard-overwrite-checkbox")
                    with gr.Row():
                        refresh_visible_button = gr.Button(_wildcards_label(lang, "Refresh wildcards", "刷新通配符"), elem_id="sddp-wildcard-refresh-visible-button")
                        delete_button = gr.Button(_wildcards_label(lang, "Delete all wildcards", "删除所有通配符"), elem_id="sddp-wildcard-delete-tree-button")
            with gr.Column(scale=2, min_width=320, elem_classes=["forge-neo-wildcards-right"]):
                file_name = gr.Textbox(
                    "",
                    elem_id="sddp-wildcard-file-name",
                    interactive=False,
                    label=_wildcards_label(lang, "Wildcards file", "通配符文件"),
                )
                file_editor = gr.Textbox(
                    "",
                    elem_id="sddp-wildcard-file-editor",
                    lines=10,
                    interactive=True,
                    label=_wildcards_label(lang, "File editor", "编辑文件"),
                )
                save_button = gr.Button(_wildcards_label(lang, "Save wildcard", "保存通配符"), scale=1, elem_id="sddp-wildcard-save-button")

        client_to_server = gr.Textbox(
            "",
            elem_id="sddp-wildcard-c2s-message-textbox",
            show_label=False,
            elem_classes=["forge-neo-hidden-bridge"],
        )
        server_to_client = gr.Textbox(
            "",
            elem_id="sddp-wildcard-s2c-message-textbox",
            show_label=False,
            elem_classes=["forge-neo-hidden-bridge"],
        )
        action_button = gr.Button("Action", elem_id="sddp-wildcard-c2s-action-button", elem_classes=["forge-neo-hidden-bridge"])
        refresh_button = gr.Button("Refresh wildcards", elem_id="sddp-wildcard-load-tree-button", elem_classes=["forge-neo-hidden-bridge"])

        action_button.click(handle_message, inputs=[client_to_server], outputs=[server_to_client])
        refresh_button.click(refresh_wildcards_callback, inputs=[], outputs=[server_to_client])
        refresh_visible_button.click(refresh_wildcards_callback, inputs=[], outputs=[server_to_client])
        delete_button.click(delete_tree_callback, inputs=[client_to_server], outputs=[server_to_client], js="SDDP.onDeleteTreeClick")
        save_button.click(save_file_callback, inputs=[client_to_server], outputs=[server_to_client], js="SDDP.onSaveFileClick")
        collection_copy_button.click(copy_collection_callback, inputs=[overwrite_checkbox, collection_dropdown], outputs=[server_to_client])
