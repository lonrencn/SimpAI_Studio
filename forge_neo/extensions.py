from __future__ import annotations

import configparser
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

import args_manager
from forge_neo.bootstrap import ensure_config
from forge_neo.models import SOURCE_BRANCH, SOURCE_COMMIT, SOURCE_PROJECT


@dataclass
class ForgeNeoExtensionInfo:
    name: str
    path: str
    source: str
    enabled: bool
    remote: str = ""
    branch: str = ""
    version: str = ""
    date: str = ""
    metadata_name: str = ""


@dataclass
class ForgeNeoAvailableExtension:
    name: str
    url: str
    description: str = ""
    tags: tuple[str, ...] = ()
    added: str = ""
    updated: str = ""
    stars: int = 0
    source_index: int = 0
    installed: bool = False
    dirname: str = ""
    branch: str = ""


class ForgeNeoExtensionInstallError(RuntimeError):
    def __init__(self, message: str, preview: dict[str, object] | None = None):
        super().__init__(message)
        self.preview = preview or {}


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _extension_dir_has_entries(path: Path) -> bool:
    if not path.is_dir():
        return False
    try:
        return any(item.is_dir() and not item.name.startswith(".") for item in path.iterdir())
    except OSError:
        return False


def _source_reference_root() -> Path | None:
    repo_root = _repo_root().resolve()
    source_name = SOURCE_PROJECT.rsplit("/", 1)[-1]
    candidates: list[Path] = []
    for env_name in ("FORGE_NEO_SOURCE_ROOT", "SD_WEBUI_FORGE_NEO_ROOT", "SD_WEBUI_FORGE_CLASSIC_ROOT"):
        value = os.environ.get(env_name, "").strip()
        if value:
            candidates.append(Path(value))
            candidates.append(Path(value) / "webui")
    candidates.extend(
        [
            repo_root.parent / "sd-webui-forge-neo-v3" / "webui",
            repo_root.parent.parent / "sd-webui-forge-neo-v3" / "webui",
            repo_root.parent / "sd-webui-forge-neo-v3",
            repo_root.parent.parent / "sd-webui-forge-neo-v3",
            repo_root.parent / source_name,
            repo_root.parent.parent / source_name,
        ]
    )
    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        key = os.path.normcase(str(resolved))
        if key in seen or resolved == repo_root:
            continue
        seen.add(key)
        if _extension_dir_has_entries(resolved / "extensions-builtin") or _extension_dir_has_entries(resolved / "extensions"):
            return resolved
    return None


def extension_scan_root() -> tuple[Path, str]:
    repo_root = _repo_root()
    webui_root = repo_root / "forge_neo" / "webui"
    if webui_root.is_dir():
        return webui_root, "forge-neo-webui"
    if _extension_dir_has_entries(repo_root / "extensions-builtin") or _extension_dir_has_entries(repo_root / "extensions"):
        return repo_root, "local"
    reference_root = _source_reference_root()
    if reference_root is not None:
        return reference_root, "source-reference"
    return repo_root, "local"


def _read_git_config(path: Path) -> tuple[str, str]:
    config_path = path / ".git" / "config"
    if not config_path.exists():
        return "", ""
    parser = configparser.ConfigParser()
    try:
        parser.read(config_path, encoding="utf-8")
    except Exception:
        return "", ""
    remote = ""
    branch = ""
    if parser.has_section('remote "origin"'):
        remote = parser.get('remote "origin"', "url", fallback="")
    for section in parser.sections():
        if section.startswith('branch "') and section.endswith('"'):
            branch = section[len('branch "') : -1]
            break
    return remote, branch


def _read_head(path: Path) -> str:
    head_path = path / ".git" / "HEAD"
    if not head_path.exists():
        return ""
    try:
        head = head_path.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        return ""
    if head.startswith("ref:"):
        ref = head.split(" ", 1)[-1].strip()
        ref_path = path / ".git" / ref
        if ref_path.exists():
            try:
                return ref_path.read_text(encoding="utf-8", errors="ignore").strip()[:8]
            except Exception:
                return ""
        return ""
    return head[:8]


def _read_commit_date(path: Path) -> str:
    if not (path / ".git").exists():
        return ""
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "log", "-1", "--format=%cd", "--date=format:%Y-%m-%d %H:%M:%S"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3.0,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def _read_metadata_name(path: Path, fallback: str) -> str:
    metadata_path = path / "metadata.ini"
    if not metadata_path.exists():
        return fallback
    parser = configparser.ConfigParser()
    try:
        parser.read(metadata_path, encoding="utf-8")
    except Exception:
        return fallback
    return parser.get("Extension", "Name", fallback=fallback)


def _extension_runtime_options() -> tuple[set[str], str]:
    try:
        config = ensure_config()
        data = getattr(config, "config_dict", {}) or {}
    except Exception:
        data = {}
    disabled_raw = data.get("disabled_extensions", []) if isinstance(data, dict) else []
    if isinstance(disabled_raw, str):
        disabled = {item.strip() for item in disabled_raw.replace(";", ",").split(",") if item.strip()}
    elif isinstance(disabled_raw, (list, tuple, set)):
        disabled = {str(item).strip() for item in disabled_raw if str(item).strip()}
    else:
        disabled = set()
    disable_all = str(data.get("disable_all_extensions", "none") if isinstance(data, dict) else "none").strip().lower()
    if disable_all not in {"none", "extra", "all"}:
        disable_all = "none"
    return disabled, disable_all


def _scan_extension_dir(root: Path, source: str, disabled_extensions: set[str] | None = None, disable_all_extensions: str = "none") -> list[ForgeNeoExtensionInfo]:
    if not root.is_dir():
        return []
    items: list[ForgeNeoExtensionInfo] = []
    disabled = {str(item).lower() for item in disabled_extensions or set()}
    disable_all = str(disable_all_extensions or "none").lower()
    for item in sorted(root.iterdir(), key=lambda value: value.name.lower()):
        if not item.is_dir() or item.name.startswith("."):
            continue
        remote, branch = _read_git_config(item)
        version = _read_head(item)
        enabled = item.name.lower() not in disabled
        if disable_all == "all" or (disable_all == "extra" and source != "built-in"):
            enabled = False
        items.append(
            ForgeNeoExtensionInfo(
                name=item.name,
                path=str(item),
                source=source,
                enabled=enabled,
                remote=remote or ("built-in" if source == "built-in" else ""),
                branch=branch,
                version=version,
                date=_read_commit_date(item),
                metadata_name=_read_metadata_name(item, item.name),
            )
        )
    return items


def list_extensions() -> list[ForgeNeoExtensionInfo]:
    root, _root_mode = extension_scan_root()
    disabled_extensions, disable_all_extensions = _extension_runtime_options()
    return [
        *_scan_extension_dir(root / "extensions-builtin", "built-in", disabled_extensions, disable_all_extensions),
        *_scan_extension_dir(root / "extensions", "user", disabled_extensions, disable_all_extensions),
    ]


def _is_en(lang: object | None = None) -> bool:
    value = str(lang if lang is not None else getattr(args_manager.args, "language", "cn")).lower()
    return value.startswith("en")


def _text(lang: object | None, en: str, cn: str) -> str:
    return en if _is_en(lang) else cn


ADAPTED_AVAILABLE_EXTENSION_SOURCE = "forge-neo://adapted-extension-profiles"

DEFAULT_AVAILABLE_EXTENSION_TAGS: tuple[tuple[str, str, str], ...] = (
    ("adapted", "Adapted", "已适配"),
    ("prompt-helper", "Prompt helper", "提示词辅助"),
    ("image-interrogation", "Image tagging", "图片反推"),
    ("generation-hook", "Generation hook", "生成扩展"),
    ("ui-tab", "UI tab", "独立页面"),
    ("ui-route", "UI route", "页面路由"),
    ("api-adapter", "API adapter", "API 适配"),
    ("installed", "installed", "已安装"),
)

AVAILABLE_EXTENSION_TAG_LABELS: tuple[tuple[str, str, str], ...] = (
    *DEFAULT_AVAILABLE_EXTENSION_TAGS,
    ("first-batch", "First batch", "首批适配"),
    ("priority-profile", "Priority", "重点适配"),
    ("runtime-adapter", "Runtime adapter", "运行适配"),
    ("prompt-resource", "Prompt resource", "提示词资源"),
    ("alwayson-args", "Alwayson args", "Alwayson 参数"),
    ("api-route", "API route", "API 路由"),
    ("ui-helper", "UI helper", "界面辅助"),
    ("image-browser", "Image browser", "图片浏览"),
    ("external-client", "External client", "外部客户端"),
    ("storyboard", "Storyboard", "分镜"),
    ("analysis-ui", "Analysis UI", "分析页面"),
    ("multimodal-tools", "Multimodal tools", "多模态工具"),
    ("vision-chat", "Vision chat", "视觉对话"),
    ("segmentation", "Segmentation", "分割抠图"),
    ("layer-decomposition", "Layer decomposition", "图层分解"),
    ("3d-generation", "3D generation", "3D 生成"),
    ("prompt-style", "Prompt style", "提示词样式"),
    ("script", "script", "脚本"),
    ("ads", "ads", "广告"),
    ("localization", "localization", "本地化"),
)


def _known_available_tag_label(tag: object, lang: object | None = None) -> str:
    tag_text = str(tag or "").strip()
    tag_key = tag_text.lower()
    for value, en, cn in AVAILABLE_EXTENSION_TAG_LABELS:
        if tag_key == value:
            return _text(lang, en, cn)
    return tag_text


def _update_row_by_name(update_preview: dict[str, object] | None = None) -> dict[str, dict[str, object]]:
    rows = {}
    if not isinstance(update_preview, dict):
        return rows
    for raw in update_preview.get("rows", []) or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name", "") or "")
        if name:
            rows[name] = raw
    return rows


def extension_update_candidate_names(update_preview: dict[str, object] | None = None) -> list[str]:
    names = []
    if not isinstance(update_preview, dict):
        return names
    for raw in update_preview.get("rows", []) or []:
        if not isinstance(raw, dict):
            continue
        if raw.get("status") == "update-available":
            name = str(raw.get("name", "") or "")
            if name:
                names.append(name)
    return names


def extension_table(
    infos: list[ForgeNeoExtensionInfo] | None = None,
    lang: object | None = None,
    update_preview: dict[str, object] | None = None,
) -> str:
    items = list_extensions() if infos is None else list(infos)
    update_rows = _update_row_by_name(update_preview)
    rows = []
    all_enabled = bool(items) and all(item.enabled for item in items)
    for item in items:
        remote_label = item.remote or "local"
        remote = html.escape(remote_label)
        if item.remote.startswith("http://") or item.remote.startswith("https://"):
            remote = f'<a href="{html.escape(item.remote)}" target="_blank">{html.escape(item.remote)}</a>'
        checked = " checked" if item.enabled else ""
        update_row = update_rows.get(item.name, {})
        update_status = str(update_row.get("status", "") or "")
        update_label = ""
        update_checkbox = ""
        if update_status == "update-available":
            behind = int(update_row.get("behind_count", 0) or 0)
            update_label = _text(lang, "Update available", "发现更新")
            if behind:
                update_label = f"{update_label} (-{behind})"
            update_checkbox = f'<input class="gr-check-radio gr-checkbox forge-neo-extension-update-toggle" name="update_{html.escape(item.name)}" type="checkbox" checked>'
        elif update_status == "diverged":
            update_label = _text(lang, "Diverged; manual review", "已分叉；需人工确认")
        elif update_status == "ahead":
            update_label = _text(lang, "Local commits ahead", "本地提交超前")
        elif update_status == "up-to-date":
            update_label = _text(lang, "Up to date", "已是最新")
        elif update_status == "fetch-error":
            update_label = _text(lang, "Fetch failed", "Fetch 失败")
        elif update_status == "tracking-missing":
            update_label = _text(lang, "No upstream branch", "没有上游分支")
        elif update_status == "git-error":
            update_label = _text(lang, "Git check failed", "Git 检查失败")
        elif update_status == "skipped":
            update_label = _text(lang, "Skipped", "已跳过")
        update_cell = f"<label>{update_checkbox}{html.escape(update_label)}</label>" if update_checkbox else html.escape(update_label)
        branch = item.branch or ("None" if item.source == "built-in" or item.remote == "built-in" else "")
        rows.append(
            "<tr>"
            f'<td><label><input class="gr-check-radio gr-checkbox forge-neo-extension-toggle" name="enable_{html.escape(item.name)}" type="checkbox"{checked}>{html.escape(item.name)}</label></td>'
            f"<td>{remote}</td>"
            f"<td>{html.escape(branch)}</td>"
            f"<td>{html.escape(item.version or '')}</td>"
            f"<td>{html.escape(item.date or '')}</td>"
            f"<td>{update_cell}</td>"
            "</tr>"
        )
    if not rows:
        rows.append(
            '<tr><td colspan="6" class="forge-neo-extension-empty">'
            f"{html.escape(_text(lang, 'No A1111/Forge extension directories were found in this SimpAI package.', '当前 SimpAI 包内没有 A1111/Forge 扩展目录。'))}"
            "</td></tr>"
        )
    headers = [
        _text(lang, "Extension", "扩展"),
        "URL",
        _text(lang, "Branch", "分支"),
        _text(lang, "Version", "版本"),
        _text(lang, "Date", "日期"),
        _text(lang, "Update", "更新"),
    ]
    master_checked = " checked" if all_enabled else ""
    first_header = (
        '<label><input class="gr-check-radio gr-checkbox forge-neo-extension-master-toggle" '
        f'type="checkbox" data-forge-neo-extension-master="1"{master_checked}>'
        f"<span>{html.escape(headers[0])}</span></label>"
    )
    header_cells = [f"<th>{first_header}</th>", *[f"<th>{html.escape(label)}</th>" for label in headers[1:]]]
    return (
        f"<!-- {time.time()} -->"
        '<div class="forge-neo-extension-table-wrap">'
        '<table id="forge_neo_extensions_installed_table" class="forge-neo-extension-table forge-neo-extension-installed-table">'
        "<colgroup>"
        '<col class="forge-neo-extension-col-name">'
        '<col class="forge-neo-extension-col-url">'
        '<col class="forge-neo-extension-col-branch">'
        '<col class="forge-neo-extension-col-version">'
        '<col class="forge-neo-extension-col-date">'
        '<col class="forge-neo-extension-col-update">'
        "</colgroup>"
        f"<thead><tr>{''.join(header_cells)}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        "</div>"
    )


def _string_value(data: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        if isinstance(value, (list, tuple, set, dict)):
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        digits = "".join(ch for ch in value if ch.isdigit())
        if digits:
            return int(digits)
    return 0


def _tag_values(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        raw = [item.strip() for item in value.replace(";", ",").split(",")]
    elif isinstance(value, (list, tuple, set)):
        raw = [str(item).strip() for item in value]
    else:
        raw = [str(value).strip()]
    return tuple(item for item in raw if item)


def _payload_items(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, list):
        source = payload
    elif isinstance(payload, dict):
        source = (
            payload.get("extensions")
            or payload.get("items")
            or payload.get("data")
            or payload.get("results")
            or []
        )
    else:
        source = []
    return [item for item in source if isinstance(item, dict)]


_AVAILABLE_EXTENSION_CACHE: dict[str, object] = {"source": "", "payload": None}


def _adapted_available_extension_payload() -> dict[str, object]:
    try:
        from forge_neo.extension_adapter import extension_profile_catalog_payload

        catalog = extension_profile_catalog_payload()
    except Exception:
        catalog = {}
    if not isinstance(catalog, dict):
        catalog = {}
    raw_nodes = catalog.get("nodes")
    if not isinstance(raw_nodes, list):
        raw_nodes = []
    raw_profiles = catalog.get("profiles")
    if not isinstance(raw_profiles, list):
        raw_profiles = []
    profiles_by_id = {
        _string_value(profile, "name", "id"): profile
        for profile in raw_profiles
        if isinstance(profile, dict) and _string_value(profile, "name", "id")
    }
    extensions: list[dict[str, object]] = []
    for index, node in enumerate(raw_nodes):
        if not isinstance(node, dict):
            continue
        url = _string_value(node, "remote_url", "url", "repository", "repo")
        if not url:
            continue
        profile_id = _string_value(node, "id", "name")
        name = _string_value(node, "display_name", "name", "id") or profile_id or extension_dirname_from_url(url)
        dirname = _string_value(node, "extension_dirname", "name", "id") or extension_dirname_from_url(url)
        branch = _string_value(node, "source_branch", "branch")
        family = _string_value(node, "family")
        support_level = _string_value(node, "support_level")
        adapter_scope = _string_value(node, "adapter_scope")
        tags = ["adapted"]
        for value in (family, support_level, adapter_scope):
            if value and value not in tags:
                tags.append(value)
        profile = profiles_by_id.get(profile_id, {})
        notes = profile.get("notes") if isinstance(profile, dict) else None
        note_text = ""
        if isinstance(notes, list):
            note_text = " ".join(str(item).strip() for item in notes[:2] if str(item).strip())
        description = _string_value(node, "description", "summary") or note_text
        if not description:
            description = f"Forge Neo adapted extension: {family or 'extension'} / {adapter_scope or 'runtime'}"
        commit_date = _string_value(node, "source_commit_date", "updated", "added")
        extensions.append(
            {
                "name": name,
                "url": url,
                "description": description,
                "tags": tags,
                "added": commit_date,
                "updated": commit_date,
                "stars": 0,
                "source_index": index,
                "extension_dirname": dirname,
                "branch": branch,
                "profile_id": profile_id,
            }
        )
    declared_tags: dict[str, str] = {}
    for value, en, _cn in DEFAULT_AVAILABLE_EXTENSION_TAGS:
        declared_tags[value] = en
    for item in extensions:
        for tag in _tag_values(item.get("tags")):
            declared_tags.setdefault(tag, _known_available_tag_label(tag, "en"))
    return {
        "schema_version": 1,
        "kind": "forge-neo-adapted-extension-index",
        "source": ADAPTED_AVAILABLE_EXTENSION_SOURCE,
        "tags": declared_tags,
        "extensions": extensions,
    }


def _available_extension_payload(refresh: bool = True) -> dict[str, object]:
    if (
        not refresh
        and _AVAILABLE_EXTENSION_CACHE.get("source") == ADAPTED_AVAILABLE_EXTENSION_SOURCE
        and isinstance(_AVAILABLE_EXTENSION_CACHE.get("payload"), dict)
    ):
        return _AVAILABLE_EXTENSION_CACHE["payload"]  # type: ignore[return-value]
    payload = _adapted_available_extension_payload()
    _AVAILABLE_EXTENSION_CACHE["source"] = ADAPTED_AVAILABLE_EXTENSION_SOURCE
    _AVAILABLE_EXTENSION_CACHE["payload"] = payload
    return payload


def _payload_declared_tags(payload: object) -> tuple[str, ...]:
    if not isinstance(payload, dict):
        return ()
    raw_tags = payload.get("tags")
    if isinstance(raw_tags, dict):
        return tuple(str(key).strip() for key in raw_tags if str(key).strip())
    if isinstance(raw_tags, (list, tuple, set)):
        return tuple(str(item).strip() for item in raw_tags if str(item).strip())
    return ()


def available_extension_tag_choices(
    payload: object | None = None,
    lang: object | None = None,
    installed_infos: list[ForgeNeoExtensionInfo] | None = None,
) -> list[tuple[str, str]]:
    ordered: list[str] = []
    seen: set[str] = set()

    def add_tag(value: object) -> None:
        tag = str(value or "").strip()
        key = tag.lower()
        if not tag or key in seen:
            return
        seen.add(key)
        ordered.append(tag)

    for value, _, _ in DEFAULT_AVAILABLE_EXTENSION_TAGS:
        add_tag(value)
    for tag in _payload_declared_tags(payload):
        add_tag(tag)

    installed_names, installed_urls = _installed_extension_refs(installed_infos)
    for raw in _payload_items(payload):
        tags = list(_tag_values(raw.get("tags") or raw.get("tag") or raw.get("categories") or raw.get("category")))
        url = _string_value(raw, "url", "html_url", "git_url", "repository", "repo")
        installed = _clean_extension_dirname(url).lower() in installed_names or normalize_git_url(url).lower() in installed_urls
        if installed:
            tags.append("installed")
        for tag in tags:
            add_tag(tag)

    return [(_known_available_tag_label(tag, lang), tag) for tag in ordered]


def cached_available_extension_tag_choices(index_url: str, lang: object | None = None) -> list[tuple[str, str]]:
    _unused = index_url
    return available_extension_tag_choices(_available_extension_payload(refresh=False), lang=lang)


def _installed_extension_refs(infos: list[ForgeNeoExtensionInfo] | None = None) -> tuple[set[str], set[str]]:
    items = list_extensions() if infos is None else list(infos)
    names = {item.name.lower() for item in items}
    urls = {
        normalize_git_url(item.remote).lower()
        for item in items
        if item.remote and item.remote not in {"built-in", "local"}
    }
    return names, urls


def _tag_match(tags: tuple[str, ...], selected_tags: set[str], filtering_type: object) -> bool:
    if not selected_tags:
        return False
    tag_set = {tag.lower() for tag in tags}
    matched_count = len(tag_set.intersection(selected_tags))
    return matched_count == len(selected_tags) if str(filtering_type or "or").lower() == "and" else matched_count > 0


def _available_extensions_from_payload(
    payload: object,
    selected_tags: list[str] | tuple[str, ...] | None = None,
    showing_type: str = "hide",
    filtering_type: str = "or",
    sort_column: str = "newest first",
    search: str = "",
    limit: int | None = 120,
    installed_infos: list[ForgeNeoExtensionInfo] | None = None,
) -> list[ForgeNeoAvailableExtension]:
    selected_tag_set = {str(tag).strip().lower() for tag in selected_tags or [] if str(tag).strip()}
    search_text = str(search or "").strip().lower()
    installed_names, installed_urls = _installed_extension_refs(installed_infos)
    items: list[ForgeNeoAvailableExtension] = []
    for index, raw in enumerate(_payload_items(payload)):
        tags = _tag_values(raw.get("tags") or raw.get("tag") or raw.get("categories") or raw.get("category"))
        name = _string_value(raw, "name", "title", "full_name", "repo", "repository")
        url = _string_value(raw, "url", "html_url", "git_url", "repository", "repo")
        description = _string_value(raw, "description", "desc", "summary", "github_description")
        if not name and url:
            name = url.rstrip("/").rsplit("/", 1)[-1]
        if not name:
            continue
        dirname = _string_value(raw, "extension_dirname", "dirname", "directory", "install_dirname")
        branch = _string_value(raw, "branch", "source_branch", "branch_name")
        installed = _clean_extension_dirname(url).lower() in installed_names or normalize_git_url(url).lower() in installed_urls
        if dirname and _clean_extension_dirname(dirname).lower() in installed_names:
            installed = True
        if installed and "installed" not in {tag.lower() for tag in tags}:
            tags = (*tags, "installed")
        matched_tags = _tag_match(tags, selected_tag_set, filtering_type)
        if selected_tag_set:
            if str(showing_type or "hide").lower() == "show":
                if not matched_tags:
                    continue
            elif matched_tags:
                continue
        haystack = " ".join([name, url, description, " ".join(tags)]).lower()
        if search_text and search_text not in haystack:
            continue
        items.append(
            ForgeNeoAvailableExtension(
                name=name,
                url=url,
                description=description,
                tags=tags,
                added=_string_value(raw, "added", "created_at", "create_time", "created"),
                updated=_string_value(raw, "updated", "pushed_at", "commit_time", "update_time", "last_update"),
                stars=_int_value(raw.get("stars") or raw.get("stargazers_count") or raw.get("star_count")),
                source_index=_int_value(raw.get("source_index")) if "source_index" in raw else index,
                installed=installed,
                dirname=dirname,
                branch=branch,
            )
        )

    sort_key = str(sort_column or "newest first").lower()
    if sort_key == "a-z":
        items.sort(key=lambda item: item.name.lower())
    elif sort_key == "z-a":
        items.sort(key=lambda item: item.name.lower(), reverse=True)
    elif sort_key == "oldest first":
        items.sort(key=lambda item: (item.added or item.updated, item.source_index))
    elif sort_key == "update time":
        items.sort(key=lambda item: (item.updated or item.added, item.source_index), reverse=True)
    elif sort_key == "create time":
        items.sort(key=lambda item: (item.added or item.updated, item.source_index), reverse=True)
    elif sort_key == "stars":
        items.sort(key=lambda item: (item.stars, item.name.lower()), reverse=True)
    elif sort_key == "internal order":
        items.sort(key=lambda item: item.source_index)
    else:
        items.sort(key=lambda item: (item.added or item.updated, item.source_index), reverse=True)
    if limit is None:
        return items
    return items[: max(1, int(limit or 120))]


def available_extension_filter_counts(
    index_url: str,
    selected_tags: list[str] | tuple[str, ...] | None = None,
    showing_type: str = "hide",
    filtering_type: str = "or",
    sort_column: str = "newest first",
    search: str = "",
) -> dict[str, int]:
    _unused = index_url
    payload = _available_extension_payload(refresh=False)
    total_items = _available_extensions_from_payload(
        payload,
        selected_tags=[],
        showing_type="hide",
        filtering_type="or",
        sort_column="internal order",
        search="",
        limit=None,
    )
    shown_items = _available_extensions_from_payload(
        payload,
        selected_tags=selected_tags,
        showing_type=showing_type,
        filtering_type=filtering_type,
        sort_column=sort_column,
        search=search,
        limit=None,
    )
    total_count = len(total_items)
    shown_count = len(shown_items)
    return {
        "total": total_count,
        "visible": shown_count,
        "hidden": max(0, total_count - shown_count),
    }


def _read_index_text(index_url: str) -> str:
    source = str(index_url or "").strip()
    if not source:
        raise ValueError("Extension index URL is empty.")
    parsed = urlparse(source)
    if parsed.scheme == "file":
        file_path = unquote(parsed.path)
        if len(file_path) >= 4 and file_path[0] == "/" and file_path[2] == ":":
            file_path = file_path[1:]
        path = Path(file_path)
        if len(parsed.netloc) == 2 and parsed.netloc.endswith(":"):
            path = Path(f"{parsed.netloc}{file_path}")
        return path.read_text(encoding="utf-8")
    path = Path(source)
    if path.exists():
        return path.read_text(encoding="utf-8")
    request = Request(source, headers={"User-Agent": "SimpAI-Forge-Neo-Gradio6"})
    with urlopen(request, timeout=15) as response:
        return response.read().decode("utf-8")


def load_available_extensions(
    index_url: str,
    selected_tags: list[str] | tuple[str, ...] | None = None,
    showing_type: str = "hide",
    filtering_type: str = "or",
    sort_column: str = "newest first",
    search: str = "",
    limit: int = 120,
    refresh: bool = True,
) -> list[ForgeNeoAvailableExtension]:
    _unused = index_url
    payload = _available_extension_payload(refresh=refresh)
    return _available_extensions_from_payload(
        payload,
        selected_tags=selected_tags,
        showing_type=showing_type,
        filtering_type=filtering_type,
        sort_column=sort_column,
        search=search,
        limit=limit,
    )


def available_extension_table(
    infos: list[ForgeNeoAvailableExtension] | None = None,
    lang: object | None = None,
    source_url: str = "",
    message: str = "",
    filter_counts: dict[str, int] | None = None,
) -> str:
    items = list(infos or [])
    rows = []
    for item in items:
        name = html.escape(item.name)
        if item.url.startswith("http://") or item.url.startswith("https://"):
            name = f'<a href="{html.escape(item.url)}" target="_blank" rel="noreferrer">{name}</a>'
        tags = "".join(f"<span>{html.escape(tag)}</span>" for tag in item.tags)
        if not tags:
            tags = html.escape(_text(lang, "None", "无"))
        if item.installed:
            action = f'<button type="button" class="lg secondary gradio-button custom-button forge-neo-extension-index-install" disabled>{html.escape(_text(lang, "Installed", "已安装"))}</button>'
        elif not item.url:
            action = f'<button type="button" class="lg secondary gradio-button custom-button forge-neo-extension-index-install" disabled>{html.escape(_text(lang, "Unavailable", "不可安装"))}</button>'
        else:
            url_arg = html.escape(json.dumps(item.url, ensure_ascii=False), quote=True)
            dirname_arg = html.escape(json.dumps(item.dirname, ensure_ascii=False), quote=True)
            branch_arg = html.escape(json.dumps(item.branch, ensure_ascii=False), quote=True)
            action = (
                '<button type="button" '
                'class="lg secondary gradio-button custom-button forge-neo-extension-index-install" '
                f'onclick="window.forgeNeoInstallExtensionFromIndex(this, {url_arg}, {dirname_arg}, {branch_arg})">'
                f"{html.escape(_text(lang, 'Install', '安装'))}"
                "</button>"
            )
        rows.append(
            "<tr>"
            f"<td>{name}</td>"
            f'<td><div class="forge-neo-extension-description">{html.escape(item.description)}</div></td>'
            f'<td><div class="forge-neo-extension-tags">{tags}</div></td>'
            f"<td>{item.stars}</td>"
            f"<td>{html.escape(item.added)}</td>"
            f"<td>{html.escape(item.updated)}</td>"
            f"<td>{action}</td>"
            "</tr>"
        )
    if not rows:
        empty_message = message or _text(lang, "No available extensions match the current filters.", "没有匹配当前筛选条件的可用扩展。")
        rows.append(f'<tr><td colspan="7" class="forge-neo-extension-empty">{html.escape(empty_message)}</td></tr>')
    headers = [
        _text(lang, "Extension", "扩展"),
        _text(lang, "Description", "说明"),
        _text(lang, "Tags", "标签"),
        _text(lang, "Stars", "星标"),
        _text(lang, "Added", "添加时间"),
        _text(lang, "Updated", "更新时间"),
        _text(lang, "Action", "动作"),
    ]
    source_note = ""
    if source_url:
        source_label = _source_url_label(source_url, lang)
        source_note = (
            '<div class="forge-neo-extension-source">'
            f"{html.escape(_text(lang, 'Source', '来源'))}: "
            f'<span title="{html.escape(source_url)}">{html.escape(source_label)}</span>'
            "</div>"
        )
    filter_note = ""
    if filter_counts:
        hidden = int(filter_counts.get("hidden", 0) or 0)
        visible = int(filter_counts.get("visible", len(items)) or 0)
        total = int(filter_counts.get("total", visible + hidden) or 0)
        filter_note = (
            '<div class="forge-neo-extension-filter-summary">'
            f"{html.escape(_text(lang, 'Visible', '显示'))}: {visible} / {total}"
        )
        if hidden > 0:
            filter_note += f" · {html.escape(_text(lang, 'Extension hidden', '已隐藏扩展'))}: {hidden}"
        filter_note += "</div>"
    return (
        f"<!-- {time.time()} -->"
        '<div class="forge-neo-extension-table-wrap">'
        f"{source_note}"
        f"{filter_note}"
        '<table id="forge_neo_extensions_available_table" class="forge-neo-extension-table forge-neo-extension-available-table">'
        f"<thead><tr>{''.join(f'<th>{html.escape(label)}</th>' for label in headers)}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        "</div>"
    )


def _source_url_label(source_url: object, lang: object | None = None) -> str:
    value = str(source_url or "").strip()
    if value == ADAPTED_AVAILABLE_EXTENSION_SOURCE:
        return _text(lang, "SimpAI adapted extension list", "SimpAI 已适配扩展清单")
    if value.startswith("data:"):
        return _text(lang, "inline data index", "内嵌数据索引")
    if len(value) <= 120:
        return value
    return f"{value[:82]}...{value[-30:]}"


def extension_summary() -> dict[str, object]:
    root, root_mode = extension_scan_root()
    items = list_extensions()
    return {
        "source_project": SOURCE_PROJECT,
        "source_branch": SOURCE_BRANCH,
        "source_commit": SOURCE_COMMIT,
        "installed_count": len(items),
        "builtin_count": sum(1 for item in items if item.source == "built-in"),
        "user_count": sum(1 for item in items if item.source == "user"),
        "scan_root": str(root),
        "scan_root_mode": root_mode,
        "extensions_builtin_dir": str(root / "extensions-builtin"),
        "extensions_dir": str(root / "extensions"),
        "local_extensions_builtin_dir": str(_repo_root() / "extensions-builtin"),
        "local_extensions_dir": str(_repo_root() / "extensions"),
        "forge_neo_webui_extensions_builtin_dir": str(_repo_root() / "forge_neo" / "webui" / "extensions-builtin"),
        "forge_neo_webui_extensions_dir": str(_repo_root() / "forge_neo" / "webui" / "extensions"),
        "forge_neo_backend_extensions_builtin_dir": str(_repo_root() / "forge_neo" / "webui" / "extensions-builtin"),
        "forge_neo_backend_extensions_dir": str(_repo_root() / "forge_neo" / "webui" / "extensions"),
        "source_reference_root": str(_source_reference_root() or ""),
        "config_states_dir": str(extension_config_states_dir()),
        "config_state_count": len(list_extension_config_states()),
        "mode": "read-only",
    }


def extension_config_states_dir() -> Path:
    config = ensure_config()
    base = Path(getattr(config, "path_userhome", "") or ".")
    path = base / "config" / "forge_neo_extension_states"
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_extension_config_states() -> list[Path]:
    root = extension_config_states_dir()
    return sorted(root.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)


def extension_config_choices(lang: object | None = None) -> list[tuple[str, str] | str]:
    return [(_text(lang, "Current", "当前"), "Current"), *[item.name for item in list_extension_config_states()]]


def _clean_config_name(name: str) -> str:
    base = Path(str(name or "Config")).name
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", base).strip(" ._")
    return (cleaned or "Config")[:80]


def _current_webui_state() -> dict[str, object]:
    scan_root, scan_root_mode = extension_scan_root()
    return {
        "source_project": SOURCE_PROJECT,
        "branch": SOURCE_BRANCH,
        "commit_hash": SOURCE_COMMIT,
        "repo_root": str(_repo_root()),
        "extension_scan_root": str(scan_root),
        "extension_scan_root_mode": scan_root_mode,
    }


def current_extension_config_state(name: str = "Current") -> dict[str, object]:
    _disabled_extensions, disable_all_extensions = _extension_runtime_options()
    scan_root, scan_root_mode = extension_scan_root()
    extensions = {}
    for item in list_extensions():
        extensions[item.name] = {
            "enabled": item.enabled,
            "source": item.source,
            "remote": item.remote,
            "branch": item.branch,
            "version": item.version,
            "date": item.date,
            "path": item.path,
            "metadata_name": item.metadata_name,
        }
    return {
        "name": str(name or "Current"),
        "created_at": time.time(),
        "filepath": "",
        "mode": "read-only",
        "extension_scan_root": str(scan_root),
        "extension_scan_root_mode": scan_root_mode,
        "disable_all_extensions": disable_all_extensions,
        "webui": _current_webui_state(),
        "extensions": extensions,
    }


def save_extension_config_state(name: str = "") -> tuple[Path, dict[str, object]]:
    config_name = _clean_config_name(name)
    timestamp = datetime.now().strftime("%Y_%m_%d-%H_%M_%S")
    path = extension_config_states_dir() / f"{timestamp}_{config_name}.json"
    data = current_extension_config_state(config_name)
    data["filepath"] = str(path)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path, data


def _resolve_config_state_path(selection: object) -> Path | None:
    value = str(selection or "").strip()
    if not value or value == "Current":
        return None
    path = Path(value)
    if path.exists():
        return path
    candidate = extension_config_states_dir() / Path(value).name
    if candidate.exists():
        return candidate
    raise FileNotFoundError(value)


def load_extension_config_state(selection: object = "Current") -> dict[str, object]:
    path = _resolve_config_state_path(selection)
    if path is None:
        return current_extension_config_state("Current")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Config state must be a JSON object.")
    data.setdefault("filepath", str(path))
    return data


def extension_config_download_path(selection: object = "Current") -> str | None:
    path = _resolve_config_state_path(selection)
    return str(path) if path is not None else None


def _format_created_at(value: object) -> str:
    try:
        return datetime.fromtimestamp(float(value)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(value or "")


def extension_config_state_table(selection: object = "Current", lang: object | None = None) -> str:
    try:
        data = load_extension_config_state(selection)
    except Exception as exc:
        return (
            '<div class="forge-neo-extension-config-state">'
            f"<h3>{html.escape(_text(lang, 'Config Backup', '配置快照'))}</h3>"
            f'<p class="forge-neo-extension-empty">{html.escape(_text(lang, "This config state cannot be read.", "这个配置快照无法读取。"))}</p>'
            f'<p class="forge-neo-extensions-detail">{html.escape(str(exc))}</p>'
            "</div>"
        )

    webui = data.get("webui") if isinstance(data.get("webui"), dict) else {}
    extensions = data.get("extensions") if isinstance(data.get("extensions"), dict) else {}
    name = str(data.get("name", "Current") or "Current")
    filepath = str(data.get("filepath", "") or "")
    detail_rows = [
        (_text(lang, "Filepath", "文件路径"), filepath or _text(lang, "Current runtime state", "当前运行状态")),
        (_text(lang, "Created at", "创建时间"), _format_created_at(data.get("created_at"))),
    ]
    webui_headers = ["URL", _text(lang, "Branch", "分支"), _text(lang, "Commit", "提交"), _text(lang, "Date", "日期")]
    webui_rows = [
        "<tr>"
        f"<td>{html.escape(str(webui.get('source_project', '') or ''))}</td>"
        f"<td>{html.escape(str(webui.get('branch', '') or ''))}</td>"
        f"<td>{html.escape(str(webui.get('commit_hash', '') or ''))}</td>"
        "<td></td>"
        "</tr>"
    ]
    extension_rows = []
    for ext_name, ext_data in sorted(extensions.items(), key=lambda item: item[0].lower()):
        ext_details = ext_data if isinstance(ext_data, dict) else {}
        raw_remote = str(ext_details.get("remote", "") or "")
        remote_label = "" if raw_remote == "built-in" or ext_details.get("source") == "built-in" else raw_remote
        remote = html.escape(remote_label)
        if remote_label.startswith(("http://", "https://")):
            remote = f'<a href="{html.escape(remote_label)}" target="_blank" rel="noreferrer">{html.escape(remote_label)}</a>'
        extension_rows.append(
            "<tr>"
            f'<td><label><input class="gr-check-radio gr-checkbox" type="checkbox" disabled {"checked" if ext_details.get("enabled", True) else ""}>{html.escape(ext_name)}</label></td>'
            f"<td>{remote}</td>"
            f"<td>{html.escape(str(ext_details.get('branch', '') or ''))}</td>"
            f"<td>{html.escape(str(ext_details.get('version', '') or ''))}</td>"
            f"<td>{html.escape(str(ext_details.get('date', '') or ''))}</td>"
            "</tr>"
        )
    if not extension_rows:
        extension_rows.append(
            '<tr><td colspan="5" class="forge-neo-extension-empty">'
            f"{html.escape(_text(lang, 'No extension entries are recorded in this config state.', '这个配置快照里没有扩展条目。'))}"
            "</td></tr>"
        )
    extension_headers = [
        _text(lang, "Extension", "扩展"),
        "URL",
        _text(lang, "Branch", "分支"),
        _text(lang, "Commit", "提交"),
        _text(lang, "Date", "日期"),
    ]
    return (
        '<div class="forge-neo-extension-config-state">'
        f"<h3>{html.escape(_text(lang, 'Config Backup', '配置快照'))}: {html.escape(name)}</h3>"
        '<div class="forge-neo-extension-config-details">'
        + "".join(f"<p><strong>{html.escape(label)}:</strong> {html.escape(value)}</p>" for label, value in detail_rows if value)
        + "</div>"
        f"<h3>{html.escape(_text(lang, 'WebUI State', 'WebUI 状态'))}</h3>"
        '<div class="forge-neo-extension-table-wrap">'
        '<table id="forge_neo_extensions_config_webui_state_table" class="forge-neo-extension-table forge-neo-extension-config-table">'
        f"<thead><tr>{''.join(f'<th>{html.escape(label)}</th>' for label in webui_headers)}</tr></thead>"
        f"<tbody>{''.join(webui_rows)}</tbody></table>"
        + "</div>"
        f"<h3>{html.escape(_text(lang, 'Extension State', '扩展状态'))}</h3>"
        '<div class="forge-neo-extension-table-wrap">'
        '<table id="forge_neo_extensions_config_state_table" class="forge-neo-extension-table forge-neo-extension-config-table">'
        f"<thead><tr>{''.join(f'<th>{html.escape(label)}</th>' for label in extension_headers)}</tr></thead>"
        f"<tbody>{''.join(extension_rows)}</tbody></table>"
        "</div>"
        "</div>"
    )


def _state_extension_map(data: dict[str, object]) -> dict[str, dict[str, object]]:
    raw = data.get("extensions") if isinstance(data.get("extensions"), dict) else {}
    return {str(name): value for name, value in raw.items() if isinstance(value, dict)}


def build_extension_config_diff(selection: object = "Current", restore_type: object = "extensions") -> dict[str, object]:
    selected = load_extension_config_state(selection)
    current = current_extension_config_state("Current")
    selected_name = str(selected.get("name", selection or "Current") or "Current")
    mode = str(restore_type or "extensions").lower()
    if mode not in {"extensions", "webui", "both"}:
        mode = "extensions"

    webui_rows = []
    selected_webui = selected.get("webui") if isinstance(selected.get("webui"), dict) else {}
    current_webui = current.get("webui") if isinstance(current.get("webui"), dict) else {}
    for key, label in (
        ("source_project", "Source"),
        ("branch", "Branch"),
        ("commit_hash", "Commit"),
        ("repo_root", "Repo root"),
    ):
        current_value = str(current_webui.get(key, "") or "")
        selected_value = str(selected_webui.get(key, "") or "")
        webui_rows.append(
            {
                "field": key,
                "label": label,
                "current": current_value,
                "selected": selected_value,
                "changed": current_value != selected_value,
            }
        )

    current_extensions = _state_extension_map(current)
    selected_extensions = _state_extension_map(selected)
    extension_rows = []
    for name in sorted(set(current_extensions) | set(selected_extensions), key=str.lower):
        current_ext = current_extensions.get(name)
        selected_ext = selected_extensions.get(name)
        if current_ext is None:
            status = "saved-only"
            changed_fields = ["presence"]
        elif selected_ext is None:
            status = "current-only"
            changed_fields = ["presence"]
        else:
            changed_fields = [
                key
                for key in ("enabled", "source", "remote", "branch", "version", "path")
                if str(current_ext.get(key, "") or "") != str(selected_ext.get(key, "") or "")
            ]
            status = "different" if changed_fields else "same"
        extension_rows.append(
            {
                "name": name,
                "status": status,
                "current": current_ext or {},
                "selected": selected_ext or {},
                "changed_fields": changed_fields,
                "changed": status != "same",
            }
        )

    webui_active = mode in {"webui", "both"}
    extensions_active = mode in {"extensions", "both"}
    active_webui_changes = sum(1 for row in webui_rows if row["changed"]) if webui_active else 0
    active_extension_changes = sum(1 for row in extension_rows if row["changed"]) if extensions_active else 0
    return {
        "mode": "read-only-restore-preview",
        "selection": str(selection or "Current"),
        "name": selected_name,
        "restore_type": mode,
        "filepath": str(selected.get("filepath", "") or ""),
        "created_at": selected.get("created_at", ""),
        "webui_rows": webui_rows,
        "extension_rows": extension_rows,
        "webui_changed_count": sum(1 for row in webui_rows if row["changed"]),
        "extension_changed_count": sum(1 for row in extension_rows if row["changed"]),
        "active_changed_count": active_webui_changes + active_extension_changes,
        "webui_active": webui_active,
        "extensions_active": extensions_active,
        "writes_config": False,
        "restarts_ui": False,
    }


def extension_config_diff_table(diff: dict[str, object] | None = None, lang: object | None = None) -> str:
    data = diff or build_extension_config_diff("Current", "extensions")
    restore_type = str(data.get("restore_type", "extensions"))
    restore_label = {
        "extensions": _text(lang, "extensions", "仅扩展"),
        "webui": _text(lang, "webui", "仅 WebUI"),
        "both": _text(lang, "both", "全部"),
    }.get(restore_type, restore_type)
    summary_rows = [
        (_text(lang, "Selected config", "所选配置"), str(data.get("name", "") or "")),
        (_text(lang, "Created at", "创建时间"), _format_created_at(data.get("created_at"))),
        (_text(lang, "Filepath", "文件路径"), str(data.get("filepath", "") or _text(lang, "Current runtime state", "当前运行状态"))),
        (_text(lang, "Restore range", "恢复范围"), restore_label),
        (_text(lang, "Active changes", "将影响的差异"), str(data.get("active_changed_count", 0))),
        (_text(lang, "Mode", "模式"), _text(lang, "read-only preview", "只读预览")),
    ]
    summary_html = "".join(
        f"<p><span>{html.escape(label)}</span>{html.escape(value)}</p>"
        for label, value in summary_rows
        if value
    )

    webui_rows = []
    for row in data.get("webui_rows", []) or []:
        item = row if isinstance(row, dict) else {}
        cls = ' class="is-different"' if item.get("changed") else ""
        webui_rows.append(
            f"<tr{cls}>"
            f"<td>{html.escape(str(item.get('label', item.get('field', ''))))}</td>"
            f"<td>{html.escape(str(item.get('current', '') or ''))}</td>"
            f"<td>{html.escape(str(item.get('selected', '') or ''))}</td>"
            f"<td>{html.escape(_text(lang, 'Different', '不同') if item.get('changed') else _text(lang, 'Same', '相同'))}</td>"
            "</tr>"
        )
    if not webui_rows:
        webui_rows.append(
            '<tr><td colspan="4" class="forge-neo-extension-empty">'
            f"{html.escape(_text(lang, 'No WebUI state fields are available.', '没有可比较的 WebUI 状态字段。'))}"
            "</td></tr>"
        )

    extension_rows = []
    for row in data.get("extension_rows", []) or []:
        item = row if isinstance(row, dict) else {}
        current_ext = item.get("current") if isinstance(item.get("current"), dict) else {}
        selected_ext = item.get("selected") if isinstance(item.get("selected"), dict) else {}
        status = str(item.get("status", "same"))
        status_label = {
            "same": _text(lang, "Same", "相同"),
            "different": _text(lang, "Different", "不同"),
            "current-only": _text(lang, "Current only", "仅当前存在"),
            "saved-only": _text(lang, "Saved only", "仅快照存在"),
        }.get(status, status)
        field_text = ", ".join(str(value) for value in item.get("changed_fields", []) or [])
        cls = ' class="is-different"' if item.get("changed") else ""
        current_summary = " / ".join(
            str(current_ext.get(key, "") or "")
            for key in ("source", "remote", "branch", "version")
            if str(current_ext.get(key, "") or "")
        )
        selected_summary = " / ".join(
            str(selected_ext.get(key, "") or "")
            for key in ("source", "remote", "branch", "version")
            if str(selected_ext.get(key, "") or "")
        )
        extension_rows.append(
            f"<tr{cls}>"
            f"<td>{html.escape(str(item.get('name', '') or ''))}</td>"
            f"<td>{html.escape(status_label)}</td>"
            f"<td>{html.escape(current_summary)}</td>"
            f"<td>{html.escape(selected_summary)}</td>"
            f"<td>{html.escape(field_text)}</td>"
            "</tr>"
        )
    if not extension_rows:
        extension_rows.append(
            '<tr><td colspan="5" class="forge-neo-extension-empty">'
            f"{html.escape(_text(lang, 'No extension entries are available for comparison.', '没有可比较的扩展条目。'))}"
            "</td></tr>"
        )

    webui_notice = "" if data.get("webui_active") else f'<p class="forge-neo-extension-state-note">{html.escape(_text(lang, "WebUI rows are shown for reference; this restore range does not apply them.", "WebUI 行仅作参考，当前恢复范围不会应用它们。"))}</p>'
    extension_notice = "" if data.get("extensions_active") else f'<p class="forge-neo-extension-state-note">{html.escape(_text(lang, "Extension rows are shown for reference; this restore range does not apply them.", "扩展行仅作参考，当前恢复范围不会应用它们。"))}</p>'
    return (
        '<div class="forge-neo-extension-config-diff">'
        f"<h3>{html.escape(_text(lang, 'Restore Preview', '恢复预览'))}</h3>"
        '<div class="forge-neo-extension-config-grid">'
        f"{summary_html}"
        "</div>"
        f"<h3>{html.escape(_text(lang, 'WebUI State Diff', 'WebUI 状态差异'))}</h3>"
        f"{webui_notice}"
        '<div class="forge-neo-extension-table-wrap">'
        '<table id="forge_neo_extensions_config_webui_diff_table" class="forge-neo-extension-table forge-neo-extension-diff-table">'
        f"<thead><tr><th>{html.escape(_text(lang, 'Field', '字段'))}</th><th>{html.escape(_text(lang, 'Current', '当前'))}</th><th>{html.escape(_text(lang, 'Saved', '快照'))}</th><th>{html.escape(_text(lang, 'Status', '状态'))}</th></tr></thead>"
        f"<tbody>{''.join(webui_rows)}</tbody></table>"
        "</div>"
        f"<h3>{html.escape(_text(lang, 'Extension State Diff', '扩展状态差异'))}</h3>"
        f"{extension_notice}"
        '<div class="forge-neo-extension-table-wrap">'
        '<table id="forge_neo_extensions_config_diff_table" class="forge-neo-extension-table forge-neo-extension-diff-table">'
        f"<thead><tr><th>{html.escape(_text(lang, 'Extension', '扩展'))}</th><th>{html.escape(_text(lang, 'Status', '状态'))}</th><th>{html.escape(_text(lang, 'Current', '当前'))}</th><th>{html.escape(_text(lang, 'Saved', '快照'))}</th><th>{html.escape(_text(lang, 'Changed fields', '差异字段'))}</th></tr></thead>"
        f"<tbody>{''.join(extension_rows)}</tbody></table>"
        "</div>"
        "</div>"
    )


def _extension_user_config_path() -> Path:
    config = ensure_config()
    userhome = str(getattr(config, "path_userhome", "") or "").strip()
    if userhome:
        return Path(userhome) / "config.txt"
    config_path = str(getattr(config, "config_path", "") or "").strip()
    if config_path:
        return Path(config_path)
    return _repo_root() / "users" / "config.txt"


def _read_extension_user_config() -> dict[str, object]:
    path = _extension_user_config_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_extension_user_config(data: dict[str, object]) -> Path:
    path = _extension_user_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
    try:
        config = ensure_config()
        config_dict = getattr(config, "config_dict", None)
        if isinstance(config_dict, dict):
            config_dict.clear()
            config_dict.update(data)
    except Exception:
        pass
    return path


def apply_extension_config_state(selection: object, restore_type: object = "extensions") -> dict[str, object]:
    selected = load_extension_config_state(selection)
    mode = str(restore_type or "extensions").lower()
    if mode not in {"extensions", "webui", "both"}:
        mode = "extensions"
    if mode == "webui":
        return {
            "status": "skipped",
            "selection": str(selection or "Current"),
            "restore_type": mode,
            "changed_count": 0,
            "disabled_extensions": sorted(_extension_runtime_options()[0]),
            "config_path": str(_extension_user_config_path()),
            "message": "WebUI restore preview does not change extension config.",
        }

    selected_extensions = _state_extension_map(selected)
    current_extensions = _state_extension_map(current_extension_config_state("Current"))
    config_data = _read_extension_user_config()
    disabled_raw = config_data.get("disabled_extensions", [])
    if isinstance(disabled_raw, str):
        disabled = {item.strip() for item in disabled_raw.replace(";", ",").split(",") if item.strip()}
    elif isinstance(disabled_raw, (list, tuple, set)):
        disabled = {str(item).strip() for item in disabled_raw if str(item).strip()}
    else:
        disabled = set()

    rows: list[dict[str, object]] = []
    for name in sorted(current_extensions, key=str.lower):
        selected_entry = selected_extensions.get(name)
        target_enabled = bool(selected_entry.get("enabled", False)) if selected_entry is not None else False
        was_disabled = name in disabled
        if target_enabled:
            disabled.discard(name)
        else:
            disabled.add(name)
        rows.append(
            {
                "name": name,
                "target_enabled": target_enabled,
                "was_disabled": was_disabled,
                "now_disabled": name in disabled,
                "source": "selected" if selected_entry is not None else "missing-in-snapshot",
                "changed": was_disabled != (name in disabled),
            }
        )

    selected_disable_all = str(selected.get("disable_all_extensions", "none") or "none").strip().lower()
    if selected_disable_all not in {"none", "extra", "all"}:
        selected_disable_all = "none"
    previous_disable_all = str(config_data.get("disable_all_extensions", "none") or "none").strip().lower()
    config_data["disabled_extensions"] = sorted(disabled, key=str.lower)
    config_data["disable_all_extensions"] = selected_disable_all
    path = _write_extension_user_config(config_data)
    changed_count = sum(1 for row in rows if row["changed"]) + int(previous_disable_all != selected_disable_all)
    return {
        "status": "applied",
        "selection": str(selection or "Current"),
        "restore_type": mode,
        "changed_count": changed_count,
        "disabled_extensions": sorted(disabled, key=str.lower),
        "disable_all_extensions": selected_disable_all,
        "config_path": str(path),
        "rows": rows,
        "restart_required": True,
    }


def normalize_git_url(url: object) -> str:
    normalized = str(url or "").strip().rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    return normalized


def _clean_extension_dirname(name: object) -> str:
    raw = str(name or "").strip().replace("\\", "/").rstrip("/")
    base = normalize_git_url(raw).rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._-")
    return cleaned[:80]


def extension_dirname_from_url(url: object) -> str:
    normalized = normalize_git_url(url)
    if not normalized:
        return ""
    without_query = normalized.split("?", 1)[0].split("#", 1)[0]
    return _clean_extension_dirname(without_query)


def build_extension_install_preview(dirname: object, url: object, branch: object = "", infos: list[ForgeNeoExtensionInfo] | None = None) -> dict[str, object]:
    raw_url = str(url or "").strip()
    if not raw_url:
        raise ValueError("Extension repository URL is required.")
    normalized_url = normalize_git_url(raw_url)
    resolved_dirname = _clean_extension_dirname(dirname) or extension_dirname_from_url(raw_url)
    if not resolved_dirname:
        raise ValueError("Local directory name cannot be resolved from the URL.")
    target_dir = _extensions_root() / resolved_dirname
    items = list_extensions() if infos is None else list(infos)
    installed_by_name = any(item.name.lower() == resolved_dirname.lower() for item in items)
    installed_by_url = any(
        normalized_url and normalize_git_url(item.remote).lower() == normalized_url.lower()
        for item in items
        if item.remote and item.remote not in {"built-in", "local"}
    )
    path_exists = target_dir.exists()
    reasons = []
    if installed_by_name:
        reasons.append("name")
    if installed_by_url:
        reasons.append("url")
    if path_exists:
        reasons.append("path")
    return {
        "mode": "already-installed" if reasons else "install-ready",
        "install_allowed": not bool(reasons),
        "url": raw_url,
        "normalized_url": normalized_url,
        "dirname": resolved_dirname,
        "branch": str(branch or "").strip(),
        "target_dir": str(target_dir),
        "already_installed": bool(reasons),
        "existing_reasons": reasons,
    }


def _extensions_root() -> Path:
    root, _mode = extension_scan_root()
    return root / "extensions"


def _extension_install_tmp_root() -> Path:
    return _repo_root() / "users" / "tmp" / "forge_neo_extension_installs"


def _remove_tree_force(path: Path) -> None:
    if not path.exists():
        return
    for item in sorted(path.rglob("*"), key=lambda value: len(value.parts), reverse=True):
        try:
            item.chmod(0o700 if item.is_dir() else 0o600)
        except OSError:
            pass
    try:
        path.chmod(0o700)
    except OSError:
        pass
    shutil.rmtree(path, ignore_errors=True)


def _is_inside_directory(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def _run_extension_installer(path: Path, *, timeout: float = 180.0) -> dict[str, object]:
    installer = path / "install.py"
    if not installer.is_file():
        return {
            "installer_status": "missing",
            "installer_ran": False,
            "installer_returncode": None,
            "installer_stdout": "",
            "installer_stderr": "",
        }
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{_repo_root()}{os.pathsep}{env.get('PYTHONPATH', '')}"
    try:
        result = subprocess.run(
            [sys.executable, str(installer)],
            cwd=str(_repo_root()),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
            check=False,
        )
    except Exception as exc:
        return {
            "installer_status": "error",
            "installer_ran": True,
            "installer_returncode": None,
            "installer_stdout": "",
            "installer_stderr": str(exc),
        }
    return {
        "installer_status": "success" if result.returncode == 0 else "error",
        "installer_ran": True,
        "installer_returncode": result.returncode,
        "installer_stdout": (result.stdout or "").strip()[-2000:],
        "installer_stderr": (result.stderr or "").strip()[-2000:],
    }


def _tail_process_output(value: object, limit: int = 4000) -> str:
    return str(value or "").strip()[-limit:]


def _extension_install_failed_preview(
    preview: dict[str, object],
    *,
    stage: str,
    message: str,
    command: list[str] | None = None,
    returncode: int | None = None,
    stdout: object = "",
    stderr: object = "",
    error: object = "",
) -> dict[str, object]:
    data = dict(preview)
    error_text = str(error or message or "").strip()
    data.update(
        {
            "mode": "install-failed",
            "install_allowed": False,
            "installed": False,
            "writes_files": False,
            "message": str(message or error_text or "Extension installation failed."),
            "failure_stage": stage,
            "error": error_text,
        }
    )
    if command:
        data["command"] = subprocess.list2cmdline([str(part) for part in command])
    if returncode is not None:
        data["returncode"] = returncode
    if stdout:
        data["stdout"] = _tail_process_output(stdout)
    if stderr:
        data["stderr"] = _tail_process_output(stderr)
    return data


def install_extension_from_url(dirname: object, url: object, branch: object = "", *, timeout: float = 180.0) -> dict[str, object]:
    preview = build_extension_install_preview(dirname, url, branch)
    target_dir = Path(str(preview["target_dir"]))
    extensions_root = _extensions_root()
    if not _is_inside_directory(target_dir, extensions_root):
        raise ValueError("Resolved extension target is outside the extensions directory.")
    if preview.get("already_installed") or target_dir.exists():
        preview.update(
            {
                "mode": "already-installed",
                "install_allowed": False,
                "installed": False,
                "writes_files": False,
                "message": "Extension already exists.",
            }
        )
        return preview

    extensions_root.mkdir(parents=True, exist_ok=True)
    tmp_root = _extension_install_tmp_root()
    tmp_root.mkdir(parents=True, exist_ok=True)
    tmp_dir = tmp_root / f"{target_dir.name}-{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns()}"
    command = ["git", "clone", "--filter=blob:none"]
    branch_text = str(branch or "").strip()
    if branch_text:
        command.extend(["--branch", branch_text])
    command.extend([str(preview["url"]), str(tmp_dir)])
    try:
        result = subprocess.run(
            command,
            cwd=str(_repo_root()),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        _remove_tree_force(tmp_dir)
        failed_preview = _extension_install_failed_preview(
            preview,
            stage="git clone",
            message=str(exc),
            command=command,
            error=str(exc),
        )
        raise ForgeNeoExtensionInstallError(str(exc), failed_preview) from exc
    if result.returncode != 0:
        _remove_tree_force(tmp_dir)
        output = (result.stderr or result.stdout or "").strip()
        message = output or f"git clone failed with exit code {result.returncode}"
        failed_preview = _extension_install_failed_preview(
            preview,
            stage="git clone",
            message=message,
            command=command,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            error=output,
        )
        raise ForgeNeoExtensionInstallError(message, failed_preview)

    submodule_command = ["git", "submodule", "update", "--init", "--recursive"]
    try:
        submodule_result = subprocess.run(
            submodule_command,
            cwd=str(tmp_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        _remove_tree_force(tmp_dir)
        failed_preview = _extension_install_failed_preview(
            preview,
            stage="git submodule update",
            message=str(exc),
            command=submodule_command,
            error=str(exc),
        )
        raise ForgeNeoExtensionInstallError(str(exc), failed_preview) from exc
    if submodule_result.returncode != 0:
        _remove_tree_force(tmp_dir)
        output = (submodule_result.stderr or submodule_result.stdout or "").strip()
        message = output or f"git submodule update failed with exit code {submodule_result.returncode}"
        failed_preview = _extension_install_failed_preview(
            preview,
            stage="git submodule update",
            message=message,
            command=submodule_command,
            returncode=submodule_result.returncode,
            stdout=submodule_result.stdout,
            stderr=submodule_result.stderr,
            error=output,
        )
        raise ForgeNeoExtensionInstallError(message, failed_preview)

    try:
        tmp_dir.rename(target_dir)
    except OSError:
        shutil.move(str(tmp_dir), str(target_dir))
    finally:
        _remove_tree_force(tmp_dir)

    installer_result = _run_extension_installer(target_dir, timeout=timeout)
    remote, cloned_branch = _read_git_config(target_dir)
    preview.update(
        {
            "mode": "installed",
            "install_allowed": False,
            "installed": True,
            "writes_files": True,
            "target_dir": str(target_dir),
            "remote": remote,
            "branch": branch_text or cloned_branch,
            "version": _read_head(target_dir),
            "message": "Extension installed.",
            "stdout": (result.stdout or "").strip()[-2000:],
            "stderr": (result.stderr or "").strip()[-2000:],
            "submodules_checked": True,
            "submodule_stdout": (submodule_result.stdout or "").strip()[-2000:],
            "submodule_stderr": (submodule_result.stderr or "").strip()[-2000:],
            **installer_result,
        }
    )
    return preview


def extension_install_preview_html(preview: dict[str, object] | None = None, lang: object | None = None, message: str = "") -> str:
    data = preview or {}
    mode = str(data.get("mode", "") or "")
    if mode == "installed":
        mode_label = _text(lang, "installed", "已安装")
    elif mode == "install-failed":
        mode_label = _text(lang, "failed", "失败")
    elif data.get("install_allowed"):
        mode_label = _text(lang, "ready to install", "可安装")
    elif mode == "already-installed":
        mode_label = _text(lang, "already installed", "已存在")
    else:
        mode_label = _text(lang, "preview only", "仅预览")
    rows = [
        (_text(lang, "Repository URL", "仓库 URL"), str(data.get("url", "") or "")),
        (_text(lang, "Normalized URL", "规范化 URL"), str(data.get("normalized_url", "") or "")),
        (_text(lang, "Local directory", "本地目录"), str(data.get("dirname", "") or "")),
        (_text(lang, "Branch", "分支"), str(data.get("branch", "") or _text(lang, "Default branch", "默认分支"))),
        (_text(lang, "Commit", "提交"), str(data.get("version", "") or "")),
        (_text(lang, "Target path", "目标路径"), str(data.get("target_dir", "") or "")),
        (_text(lang, "Mode", "模式"), mode_label),
    ]
    if data.get("submodules_checked"):
        rows.append((_text(lang, "Submodules", "子模块"), _text(lang, "checked", "已检查")))
    installer_status = str(data.get("installer_status", "") or "")
    if installer_status:
        installer_label = {
            "missing": _text(lang, "no install.py", "没有 install.py"),
            "success": _text(lang, "install.py completed", "install.py 已完成"),
            "error": _text(lang, "install.py failed", "install.py 失败"),
        }.get(installer_status, installer_status)
        rows.append((_text(lang, "Installer", "安装脚本"), installer_label))
    if mode == "install-failed":
        rows.extend(
            [
                (_text(lang, "Failure stage", "失败阶段"), str(data.get("failure_stage", "") or "")),
                (_text(lang, "Return code", "返回码"), str(data.get("returncode", "") or "")),
                (_text(lang, "Command", "命令"), str(data.get("command", "") or "")),
                (_text(lang, "Error", "错误"), str(data.get("error", "") or "")),
            ]
        )
    if data:
        if mode == "installed":
            state = _text(lang, "Extension installed. Restart the UI to load it.", "扩展已安装。重启 UI 后加载。")
        elif mode == "install-failed":
            state = str(data.get("message", "") or message or _text(lang, "Extension installation failed.", "扩展安装失败。"))
        elif data.get("already_installed"):
            state = _text(lang, "Already installed or target path exists.", "可能已安装或目标路径已存在。")
        elif data.get("install_allowed"):
            state = _text(lang, "Ready to install from this repository.", "可以从这个仓库安装。")
        else:
            state = _text(lang, "Install preview ready.", "安装预览已生成。")
    else:
        state = message or _text(lang, "Enter a repository URL and click Install.", "输入仓库 URL 后点击安装。")
    reason_text = ", ".join(str(item) for item in data.get("existing_reasons", []) or [])
    if reason_text:
        rows.append((_text(lang, "Matched by", "匹配原因"), reason_text))
    visible_rows = "".join(
        f"<p><span>{html.escape(label)}</span>{html.escape(value)}</p>"
        for label, value in rows
        if value
    )
    log_rows = [
        (_text(lang, "Git stdout", "Git 标准输出"), str(data.get("stdout", "") or "")),
        (_text(lang, "Git stderr", "Git 错误输出"), str(data.get("stderr", "") or "")),
        (_text(lang, "Submodule stdout", "子模块标准输出"), str(data.get("submodule_stdout", "") or "")),
        (_text(lang, "Submodule stderr", "子模块错误输出"), str(data.get("submodule_stderr", "") or "")),
        (_text(lang, "Installer stdout", "安装脚本标准输出"), str(data.get("installer_stdout", "") or "")),
        (_text(lang, "Installer stderr", "安装脚本错误输出"), str(data.get("installer_stderr", "") or "")),
    ]
    log_blocks = "".join(
        f'<details class="forge-neo-extension-install-log"{" open" if mode == "install-failed" else ""}>'
        f"<summary>{html.escape(label)}</summary>"
        f"<pre>{html.escape(value)}</pre>"
        "</details>"
        for label, value in log_rows
        if value
    )
    return (
        '<div class="forge-neo-extension-install-preview">'
        f"<h3>{html.escape(_text(lang, 'Install Preview', '安装预览'))}</h3>"
        f'<p class="forge-neo-extension-install-state">{html.escape(state)}</p>'
        f'<div class="forge-neo-extension-install-grid">{visible_rows}</div>'
        f"{log_blocks}"
        "</div>"
    )


def _extension_has_remote(item: ForgeNeoExtensionInfo) -> bool:
    remote = str(item.remote or "").strip()
    if not remote or remote in {"built-in", "local"}:
        return False
    return remote.startswith(("http://", "https://", "git@")) or ".git" in remote


def _git_output(path: Path, *args: str, timeout: float = 4.0) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        return False, str(exc)
    output = (result.stdout or "").strip()
    error = (result.stderr or "").strip()
    if result.returncode != 0:
        return False, error or output
    return True, output


def _short_commit(value: object) -> str:
    text = str(value or "").strip()
    return text[:8] if text else ""


def _extension_update_row(item: ForgeNeoExtensionInfo, *, fetch: bool = False) -> dict[str, object]:
    path = Path(item.path)
    row: dict[str, object] = {
        "name": item.name,
        "source": item.source,
        "remote": item.remote,
        "branch": item.branch,
        "version": _short_commit(item.version),
        "path": item.path,
        "status": "unknown",
        "reason": "",
        "local_commit": _short_commit(item.version),
        "upstream": "",
        "upstream_commit": "",
        "ahead_count": 0,
        "behind_count": 0,
        "checked": False,
        "fetched": False,
    }
    if item.source == "built-in" or item.remote == "built-in":
        row.update(status="skipped", reason="built-in")
        return row
    if not path.is_dir():
        row.update(status="skipped", reason="path-missing")
        return row
    if not _extension_has_remote(item):
        row.update(status="skipped", reason="local")
        return row
    if not (path / ".git").exists():
        row.update(status="skipped", reason="no-git")
        return row

    ok, branch = _git_output(path, "rev-parse", "--abbrev-ref", "HEAD")
    if ok and branch and branch != "HEAD":
        row["branch"] = item.branch or branch
    ok, local_commit = _git_output(path, "rev-parse", "HEAD")
    if ok:
        row["local_commit"] = _short_commit(local_commit)
        row["version"] = _short_commit(local_commit)
    else:
        row.update(status="git-error", reason=local_commit, checked=True)
        return row

    ok, upstream = _git_output(path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if not ok or not upstream:
        row.update(status="tracking-missing", reason=upstream or "no upstream branch", checked=True)
        return row
    row["upstream"] = upstream

    if fetch:
        ok, fetch_output = _git_output(path, "fetch", "--prune", timeout=45.0)
        row["fetched"] = bool(ok)
        if not ok:
            row.update(status="fetch-error", reason=fetch_output, checked=True)
            return row

    ok, upstream_commit = _git_output(path, "rev-parse", "@{u}")
    if not ok:
        row.update(status="git-error", reason=upstream_commit, checked=True)
        return row
    row["upstream_commit"] = _short_commit(upstream_commit)

    ok, counts = _git_output(path, "rev-list", "--left-right", "--count", "HEAD...@{u}")
    if ok:
        parts = counts.split()
        if len(parts) >= 2:
            try:
                row["ahead_count"] = int(parts[0])
                row["behind_count"] = int(parts[1])
            except ValueError:
                row["ahead_count"] = 0
                row["behind_count"] = 0

    ahead = int(row.get("ahead_count", 0) or 0)
    behind = int(row.get("behind_count", 0) or 0)
    if behind > 0 and ahead > 0:
        status = "diverged"
    elif behind > 0:
        status = "update-available"
    elif ahead > 0:
        status = "ahead"
    elif row["local_commit"] == row["upstream_commit"]:
        status = "up-to-date"
    else:
        status = "unknown"
    row.update(status=status, checked=True)
    return row


def _normalize_disable_mode(value: object) -> str:
    mode = str(value or "none").strip().lower()
    mapping = {
        "none": "none",
        "不禁用": "none",
        "extra": "extra",
        "仅禁用第三方": "extra",
        "all": "all",
        "禁用全部": "all",
    }
    return mapping.get(mode, "none")


def build_extension_apply_preview(disable_all: object, infos: list[ForgeNeoExtensionInfo] | None = None) -> dict[str, object]:
    mode = _normalize_disable_mode(disable_all)
    items = list_extensions() if infos is None else list(infos)
    rows = []
    for item in items:
        will_disable = mode == "all" or (mode == "extra" and item.source != "built-in")
        if will_disable:
            status = "would-disable"
        elif item.enabled:
            status = "stay-enabled"
        else:
            status = "stay-disabled"
        rows.append(
            {
                "name": item.name,
                "source": item.source,
                "enabled": item.enabled,
                "remote": item.remote,
                "path": item.path,
                "status": status,
                "will_disable": will_disable,
            }
        )
    return {
        "mode": "read-only-apply-preview",
        "disable_all": mode,
        "writes_config": False,
        "restarts_ui": False,
        "total_count": len(rows),
        "affected_count": sum(1 for row in rows if row["will_disable"]),
        "rows": rows,
    }


def apply_extension_disable_mode(disable_all: object, infos: list[ForgeNeoExtensionInfo] | None = None) -> dict[str, object]:
    mode = _normalize_disable_mode(disable_all)
    preview = build_extension_apply_preview(mode, infos)
    config_data = _read_extension_user_config()
    previous = str(config_data.get("disable_all_extensions", "none") or "none").strip().lower()
    if previous not in {"none", "extra", "all"}:
        previous = "none"
    config_data["disable_all_extensions"] = mode
    path = _write_extension_user_config(config_data)
    preview.update(
        {
            "mode": "applied-disable-mode",
            "writes_config": True,
            "restarts_ui": False,
            "restart_required": True,
            "config_path": str(path),
            "previous_disable_all": previous,
            "changed_count": int(previous != mode),
        }
    )
    return preview


def _parse_extension_name_list(value: object) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = [item.strip() for item in text.replace(";", ",").split(",")]
    else:
        parsed = value
    if isinstance(parsed, str):
        parsed = [parsed]
    if not isinstance(parsed, (list, tuple, set)):
        return []
    names = []
    seen = set()
    for item in parsed:
        name = str(item or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def _update_extension_from_upstream(item: ForgeNeoExtensionInfo, *, timeout: float = 180.0) -> dict[str, object]:
    path = Path(item.path)
    row = {
        "name": item.name,
        "path": item.path,
        "source": item.source,
        "remote": item.remote,
        "branch": item.branch,
        "status": "skipped",
        "reason": "",
        "before_commit": "",
        "after_commit": "",
        "upstream": "",
        "upstream_commit": "",
        "updated": False,
    }
    extensions_root = _extensions_root()
    if item.source == "built-in":
        row.update(reason="built-in")
        return row
    if not _is_inside_directory(path, extensions_root):
        row.update(reason="outside-extensions-dir")
        return row
    before_status = _extension_update_row(item, fetch=True)
    row.update(
        status=str(before_status.get("status", "unknown") or "unknown"),
        reason=str(before_status.get("reason", "") or ""),
        before_commit=str(before_status.get("local_commit", "") or ""),
        upstream=str(before_status.get("upstream", "") or ""),
        upstream_commit=str(before_status.get("upstream_commit", "") or ""),
        branch=str(before_status.get("branch", item.branch) or item.branch or ""),
    )
    if before_status.get("status") != "update-available":
        row["status"] = f"skipped-{before_status.get('status', 'unknown')}"
        return row

    upstream_ref = str(before_status.get("upstream", "") or "@{u}")
    ok, reset_output = _git_output(path, "reset", "--hard", upstream_ref, timeout=timeout)
    row["output"] = reset_output[-2000:]
    if not ok:
        row.update(status="update-error", reason=reset_output)
        return row

    ok, after_commit = _git_output(path, "rev-parse", "HEAD")
    if ok:
        row["after_commit"] = _short_commit(after_commit)
    else:
        row["after_commit"] = row["upstream_commit"]
    row.update(status="updated", reason="", updated=True)
    return row


def apply_extension_changes(
    disabled_names: object,
    update_names: object,
    disable_all: object,
    infos: list[ForgeNeoExtensionInfo] | None = None,
    *,
    timeout: float = 180.0,
) -> dict[str, object]:
    mode = _normalize_disable_mode(disable_all)
    items = list_extensions() if infos is None else list(infos)
    disabled = _parse_extension_name_list(disabled_names)
    update_requested = _parse_extension_name_list(update_names)

    config_data = _read_extension_user_config()
    previous_disabled = _parse_extension_name_list(config_data.get("disabled_extensions", []))
    previous_disable_all = str(config_data.get("disable_all_extensions", "none") or "none").strip().lower()
    if previous_disable_all not in {"none", "extra", "all"}:
        previous_disable_all = "none"
    config_data["disabled_extensions"] = sorted(disabled, key=str.lower)
    config_data["disable_all_extensions"] = mode
    config_path = _write_extension_user_config(config_data)

    update_set = set(update_requested)
    backup_path = ""
    update_rows: list[dict[str, object]] = []
    if update_set:
        try:
            backup_path = str(save_extension_config_state("Backup (pre-update)")[0])
        except Exception as exc:
            update_rows.append(
                {
                    "name": "Backup (pre-update)",
                    "status": "backup-error",
                    "reason": str(exc),
                    "updated": False,
                }
            )
    item_by_name = {item.name: item for item in items}
    for name in update_requested:
        item = item_by_name.get(name)
        if item is None:
            update_rows.append({"name": name, "status": "skipped-missing", "reason": "extension not found", "updated": False})
            continue
        update_rows.append(_update_extension_from_upstream(item, timeout=timeout))

    rows = []
    for item in items:
        disabled_after = item.name in disabled
        will_disable = mode == "all" or (mode == "extra" and item.source != "built-in") or disabled_after
        if will_disable:
            status = "would-disable"
        elif item.enabled:
            status = "stay-enabled"
        else:
            status = "stay-disabled"
        rows.append(
            {
                "name": item.name,
                "source": item.source,
                "enabled": item.enabled,
                "remote": item.remote,
                "path": item.path,
                "status": status,
                "will_disable": will_disable,
            }
        )

    changed_count = int(previous_disable_all != mode or sorted(previous_disabled, key=str.lower) != sorted(disabled, key=str.lower))
    return {
        "mode": "applied-extension-changes",
        "disable_all": mode,
        "disabled_extensions": sorted(disabled, key=str.lower),
        "previous_disabled_extensions": sorted(previous_disabled, key=str.lower),
        "previous_disable_all": previous_disable_all,
        "writes_config": True,
        "writes_files": bool(update_requested),
        "restarts_ui": False,
        "restart_required": True,
        "config_path": str(config_path),
        "backup_path": backup_path,
        "changed_count": changed_count,
        "total_count": len(rows),
        "affected_count": sum(1 for row in rows if row["will_disable"]),
        "updates_requested_count": len(update_requested),
        "updated_count": sum(1 for row in update_rows if row.get("updated")),
        "failed_count": sum(1 for row in update_rows if str(row.get("status", "")).endswith("error")),
        "skipped_update_count": sum(1 for row in update_rows if str(row.get("status", "")).startswith("skipped")),
        "rows": rows,
        "update_rows": update_rows,
    }


def extension_apply_preview_table(preview: dict[str, object] | None = None, lang: object | None = None) -> str:
    data = preview or build_extension_apply_preview("none", [])
    rows = []
    applied = bool(data.get("writes_config"))
    for item in data.get("rows", []) or []:
        row = item if isinstance(item, dict) else {}
        source = {"built-in": _text(lang, "built-in", "内置"), "user": _text(lang, "user", "用户")}.get(str(row.get("source", "")), str(row.get("source", "")))
        current = _text(lang, "Enabled", "已启用") if row.get("enabled", True) else _text(lang, "Disabled", "已禁用")
        if applied and row.get("status") == "would-disable":
            status = _text(lang, "Disabled after restart", "重启后禁用")
        elif row.get("status") == "would-disable":
            status = _text(lang, "Would be disabled", "将禁用")
        elif applied and row.get("status") == "stay-disabled":
            status = _text(lang, "Remains disabled", "保持禁用")
        elif row.get("status") == "stay-disabled":
            status = _text(lang, "Would stay disabled", "保持禁用")
        elif applied:
            status = _text(lang, "Enabled after restart", "重启后启用")
        else:
            status = _text(lang, "Would stay enabled", "保持启用")
        location = str(row.get("remote", "") or row.get("path", "") or "")
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(row.get('name', '') or ''))}</td>"
            f"<td>{html.escape(source)}</td>"
            f"<td>{html.escape(current)}</td>"
            f"<td>{html.escape(status)}</td>"
            f"<td>{html.escape(location)}</td>"
            "</tr>"
        )
    if not rows:
        rows.append(
            '<tr><td colspan="5" class="forge-neo-extension-empty">'
            f"{html.escape(_text(lang, 'No extension entries are available for apply preview.', '没有可用于启停预览的扩展。'))}"
            "</td></tr>"
        )
    headers = [
        _text(lang, "Extension", "扩展"),
        _text(lang, "Type", "类型"),
        _text(lang, "Current", "当前"),
        _text(lang, "Preview", "预览"),
        _text(lang, "Location", "位置"),
    ]
    mode_label = {
        "none": _text(lang, "disable none", "不禁用"),
        "extra": _text(lang, "disable user extensions", "禁用第三方"),
        "all": _text(lang, "disable all", "禁用全部"),
    }.get(str(data.get("disable_all", "none")), str(data.get("disable_all", "none")))
    heading = _text(lang, "Applied extension disable mode", "已应用扩展禁用模式") if applied else _text(lang, "Read-only apply preview", "只读启停预览")
    restart_label = _text(lang, "required", "需要") if data.get("restart_required") else _text(lang, "disabled", "禁用")
    summary = (
        f"{html.escape(heading)}: "
        f"{html.escape(mode_label)}, "
        f"{html.escape(_text(lang, 'affected', '影响'))} {int(data.get('affected_count', 0))}, "
        f"{html.escape(_text(lang, 'restart', '重启'))}: {html.escape(restart_label)}"
    )
    config_path = str(data.get("config_path", "") or "")
    if config_path:
        summary += f", {html.escape(_text(lang, 'config', '配置'))}: {html.escape(config_path)}"
    update_rows = []
    for raw in data.get("update_rows", []) or []:
        row = raw if isinstance(raw, dict) else {}
        status_key = str(row.get("status", "") or "")
        if status_key == "updated":
            status = _text(lang, "Updated", "已更新")
        elif status_key == "update-error":
            status = _text(lang, "Update failed", "更新失败")
        elif status_key == "backup-error":
            status = _text(lang, "Backup failed", "备份失败")
        elif status_key == "skipped-missing":
            status = _text(lang, "Skipped: missing", "已跳过：不存在")
        elif status_key.startswith("skipped-"):
            status = _text(lang, "Skipped", "已跳过") + f": {status_key[8:]}"
        else:
            status = status_key or _text(lang, "Skipped", "已跳过")
        update_rows.append(
            "<tr>"
            f"<td>{html.escape(str(row.get('name', '') or ''))}</td>"
            f"<td>{html.escape(status)}</td>"
            f"<td>{html.escape(str(row.get('before_commit', '') or ''))}</td>"
            f"<td>{html.escape(str(row.get('after_commit', '') or row.get('upstream_commit', '') or ''))}</td>"
            f"<td>{html.escape(str(row.get('reason', '') or row.get('path', '') or ''))}</td>"
            "</tr>"
        )
    if update_rows:
        update_headers = [
            _text(lang, "Extension", "扩展"),
            _text(lang, "Update result", "更新结果"),
            _text(lang, "Before", "更新前"),
            _text(lang, "After", "更新后"),
            _text(lang, "Detail", "详情"),
        ]
        backup_path = str(data.get("backup_path", "") or "")
        update_summary = (
            f"<p>{html.escape(_text(lang, 'Extension updates', '扩展更新'))}: "
            f"{html.escape(_text(lang, 'updated', '已更新'))} {int(data.get('updated_count', 0))}, "
            f"{html.escape(_text(lang, 'failed', '失败'))} {int(data.get('failed_count', 0))}, "
            f"{html.escape(_text(lang, 'skipped', '已跳过'))} {int(data.get('skipped_update_count', 0))}"
            f"{', ' + html.escape(_text(lang, 'backup', '备份')) + ': ' + html.escape(backup_path) if backup_path else ''}</p>"
        )
        update_section = (
            '<div class="forge-neo-extension-table-wrap">'
            f"{update_summary}"
            '<table id="forge_neo_extensions_update_apply_table" class="forge-neo-extension-table">'
            f"<thead><tr>{''.join(f'<th>{html.escape(label)}</th>' for label in update_headers)}</tr></thead>"
            f"<tbody>{''.join(update_rows)}</tbody></table>"
            "</div>"
        )
    else:
        update_section = ""
    return (
        '<div class="forge-neo-extension-apply-preview">'
        f"<p>{summary}</p>"
        '<div class="forge-neo-extension-table-wrap">'
        '<table id="forge_neo_extensions_apply_preview_table" class="forge-neo-extension-table">'
        f"<thead><tr>{''.join(f'<th>{html.escape(label)}</th>' for label in headers)}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        "</div>"
        f"{update_section}"
        "</div>"
    )


def build_extension_update_preview(infos: list[ForgeNeoExtensionInfo] | None = None, *, fetch: bool = False) -> dict[str, object]:
    items = list_extensions() if infos is None else list(infos)
    rows = [_extension_update_row(item, fetch=fetch) for item in items]
    checked_count = sum(1 for row in rows if row.get("checked"))
    skipped_count = sum(1 for row in rows if row.get("status") == "skipped")
    fetched_count = sum(1 for row in rows if row.get("fetched"))
    update_available_count = sum(1 for row in rows if row.get("status") in {"update-available", "diverged"})
    return {
        "mode": "git-fetch-update-check" if fetch else "local-git-update-check",
        "online_fetch": bool(fetch),
        "total_count": len(rows),
        "checked_count": checked_count,
        "checkable_count": checked_count,
        "update_available_count": update_available_count,
        "skipped_count": skipped_count,
        "fetched_count": fetched_count,
        "rows": rows,
    }


def extension_update_preview_table(preview: dict[str, object] | None = None, lang: object | None = None) -> str:
    data = preview or build_extension_update_preview([])
    rows = []
    for item in data.get("rows", []) or []:
        row = item if isinstance(item, dict) else {}
        remote_value = str(row.get("remote", "") or "local")
        remote = html.escape(remote_value)
        if remote_value.startswith(("http://", "https://")):
            remote = f'<a href="{html.escape(remote_value)}" target="_blank" rel="noreferrer">{html.escape(remote_value)}</a>'
        source = {"built-in": _text(lang, "built-in", "内置"), "user": _text(lang, "user", "用户")}.get(str(row.get("source", "")), str(row.get("source", "")))
        status_key = str(row.get("status", "unknown"))
        reason = str(row.get("reason", "") or "")
        if status_key == "up-to-date":
            status = _text(lang, "Up to date", "已是最新")
        elif status_key == "update-available":
            status = _text(lang, "Update available", "发现更新")
        elif status_key == "ahead":
            status = _text(lang, "Local commits ahead", "本地提交超前")
        elif status_key == "diverged":
            status = _text(lang, "Local and upstream diverged", "本地与上游分叉")
        elif status_key == "tracking-missing":
            status = _text(lang, "No upstream branch", "没有上游分支")
        elif status_key == "git-error":
            status = _text(lang, "Git check failed", "Git 检查失败")
        elif status_key == "fetch-error":
            status = _text(lang, "Fetch failed", "Fetch 失败")
        elif reason == "built-in":
            status = _text(lang, "Skipped: built-in", "已跳过：内置")
        elif reason == "path-missing":
            status = _text(lang, "Skipped: path missing", "已跳过：路径不存在")
        elif reason == "no-git":
            status = _text(lang, "Skipped: no Git repository", "已跳过：没有 Git 仓库")
        else:
            status = _text(lang, "Skipped: local", "已跳过：本地")
        ahead = int(row.get("ahead_count", 0) or 0)
        behind = int(row.get("behind_count", 0) or 0)
        if ahead or behind:
            status = f"{status} (+{ahead}/-{behind})"
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(row.get('name', '') or ''))}</td>"
            f"<td>{html.escape(source)}</td>"
            f"<td>{remote}</td>"
            f"<td>{html.escape(str(row.get('branch', '') or ''))}</td>"
            f"<td>{html.escape(str(row.get('local_commit', '') or row.get('version', '') or ''))}</td>"
            f"<td>{html.escape(str(row.get('upstream_commit', '') or row.get('upstream', '') or ''))}</td>"
            f"<td>{html.escape(status)}</td>"
            "</tr>"
        )
    if not rows:
        rows.append(
            '<tr><td colspan="7" class="forge-neo-extension-empty">'
            f"{html.escape(_text(lang, 'No extensions are available for update preview.', '没有可用于更新预览的扩展。'))}"
            "</td></tr>"
        )
    headers = [
        _text(lang, "Extension", "扩展"),
        _text(lang, "Type", "类型"),
        "URL",
        _text(lang, "Branch", "分支"),
        _text(lang, "Local", "本地"),
        _text(lang, "Upstream", "上游"),
        _text(lang, "Status", "状态"),
    ]
    title = _text(lang, "Git fetch update check", "Git fetch 更新检查") if data.get("online_fetch") else _text(lang, "Local Git update check", "本地 Git 更新检查")
    summary = (
        f"{html.escape(title)}: "
        f"{html.escape(_text(lang, 'checked', '已检查'))} {int(data.get('checked_count', data.get('checkable_count', 0)))}, "
        f"{html.escape(_text(lang, 'updates', '可更新'))} {int(data.get('update_available_count', 0))}, "
        f"{html.escape(_text(lang, 'skipped', '已跳过'))} {int(data.get('skipped_count', 0))}, "
        f"{html.escape(_text(lang, 'fetched', '已 fetch'))} {int(data.get('fetched_count', 0))}"
    )
    return (
        '<div class="forge-neo-extension-update-preview">'
        f"<p>{summary}</p>"
        '<div class="forge-neo-extension-table-wrap">'
        '<table id="forge_neo_extensions_update_preview_table" class="forge-neo-extension-table">'
        f"<thead><tr>{''.join(f'<th>{html.escape(label)}</th>' for label in headers)}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        "</div>"
        "</div>"
    )


def config_state_table(lang: object | None = None) -> str:
    summary = extension_summary()
    mode = _text(lang, "read-only", "只读") if summary["mode"] == "read-only" else str(summary["mode"])
    scan_mode = str(summary.get("scan_root_mode", "local"))
    scan_mode_label = _text(lang, "local project", "本项目") if scan_mode == "local" else _text(lang, "source reference", "源项目参考")
    return (
        '<div class="forge-neo-extension-state">'
        f"<h3>{html.escape(_text(lang, 'Forge Neo Extension State', 'Forge Neo 扩展状态'))}</h3>"
        f"<p>{html.escape(_text(lang, 'Mode', '模式'))}: {html.escape(mode)}</p>"
        f"<p>{html.escape(_text(lang, 'Scan root', '扫描来源'))}: {html.escape(scan_mode_label)}</p>"
        f"<p>{html.escape(_text(lang, 'Installed', '已安装'))}: {summary['installed_count']} "
        f"({_text(lang, 'built-in', '内置')}: {summary['builtin_count']}, {_text(lang, 'user', '用户')}: {summary['user_count']})</p>"
        f"<p>{html.escape(_text(lang, 'Source', '来源'))}: {html.escape(SOURCE_PROJECT)} / {html.escape(SOURCE_BRANCH)} / {html.escape(SOURCE_COMMIT)}</p>"
        f"<p>{html.escape(_text(lang, 'Built-in dir', '内置目录'))}: {html.escape(str(summary['extensions_builtin_dir']))}</p>"
        f"<p>{html.escape(_text(lang, 'User dir', '用户目录'))}: {html.escape(str(summary['extensions_dir']))}</p>"
        "</div>"
    )
