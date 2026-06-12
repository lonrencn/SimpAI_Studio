from __future__ import annotations

import ast
import hashlib
import html
import json
import os
import sys
import tokenize
import warnings
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import args_manager
from forge_neo.bootstrap import ensure_config


@dataclass(frozen=True)
class ForgeNeoScriptBody:
    name: str
    title: str
    source: str
    path: str
    size: int
    modified: str
    sha256: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        try:
            key = str(path.resolve()).lower()
        except OSError:
            key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _reference_root_candidates(root: Path) -> list[Path]:
    values: list[str] = []
    env_roots = os.environ.get("FORGE_NEO_SCRIPT_ROOTS") or os.environ.get("FORGE_NEO_REFERENCE_ROOTS")
    if env_roots:
        values.extend(item for item in env_roots.split(os.pathsep) if item.strip())
    config_module = sys.modules.get("modules.config")
    if config_module is not None:
        config_dict = getattr(config_module, "config_dict", {}) or {}
        raw = config_dict.get("forge_neo_script_roots") or config_dict.get("forge_neo_reference_roots") or []
        if isinstance(raw, str):
            values.extend(item for item in raw.split(os.pathsep) if item.strip())
        elif isinstance(raw, (list, tuple, set)):
            values.extend(str(item) for item in raw if str(item).strip())
    if os.environ.get("FORGE_NEO_AUTO_REFERENCE_ROOTS", "1") != "0":
        values.extend(
            [
                str(root.parent / "sd-webui-forge-neo-v3" / "webui"),
                str(root.parent / "sd-webui-forge-neo-v3"),
                str(root.parent / "sd-webui-forge-classic"),
            ]
        )
    return _unique_paths([Path(value).expanduser() for value in values if str(value).strip()])


def _scan_roots(repo_root: Path | None = None) -> list[tuple[str, Path]]:
    if repo_root is not None:
        return [("local", repo_root)]
    root = _repo_root()
    roots: list[tuple[str, Path]] = []
    webui_root = root / "forge_neo" / "webui"
    if webui_root.is_dir():
        roots.append(("forge-neo-webui", webui_root))
    roots.append(("local", root))
    for reference in _reference_root_candidates(root):
        if reference.is_dir():
            roots.append((f"reference:{reference.name}", reference))
    return roots


def _script_roots(repo_root: Path | None = None) -> list[tuple[str, Path]]:
    roots: list[tuple[str, Path]] = []
    for root_label, root in _scan_roots(repo_root):
        roots.append((f"{root_label}:scripts", root / "scripts"))
        for dirname, source_label in (("extensions-builtin", "built-in"), ("extensions", "user")):
            extensions_root = root / dirname
            if not extensions_root.is_dir():
                continue
            for item in sorted(extensions_root.iterdir(), key=lambda value: value.name.lower()):
                if item.is_dir() and not item.name.startswith("."):
                    roots.append((f"{root_label}:{source_label}:{item.name}", item / "scripts"))
    return roots


def _literal_script_title(path: Path) -> str:
    module = _parse_script_ast(path)
    if module is None:
        return ""
    for class_node in [node for node in module.body if isinstance(node, ast.ClassDef)]:
        title = _class_literal_title(class_node)
        if title:
            return title
    return ""


def _parse_script_ast(path: Path) -> ast.Module | None:
    try:
        with tokenize.open(path) as handle:
            source = handle.read()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            return ast.parse(source)
    except Exception:
        return None


def _class_literal_title(class_node: ast.ClassDef) -> str:
    for child in class_node.body:
        if not isinstance(child, ast.FunctionDef) or child.name != "title":
            continue
        for statement in child.body:
            if isinstance(statement, ast.Return) and isinstance(statement.value, ast.Constant) and isinstance(statement.value.value, str):
                return statement.value.value.strip()
    return ""


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _inherits_postprocessing(class_node: ast.ClassDef) -> bool:
    for base in class_node.bases:
        dotted = _dotted_name(base)
        if dotted.endswith("ScriptPostprocessing"):
            return True
    return False


def _show_mode_from_expr(node: ast.AST | None) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return "both" if node.value else "hidden"
    if isinstance(node, ast.Name) and node.id == "is_img2img":
        return "img"
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        operand = node.operand
        if isinstance(operand, ast.Name) and operand.id == "is_img2img":
            return "txt"
    dotted = _dotted_name(node) if node is not None else ""
    if dotted.endswith("AlwaysVisible"):
        return "hidden"
    return "both"


def _class_show_mode(class_node: ast.ClassDef) -> str:
    for child in class_node.body:
        if not isinstance(child, ast.FunctionDef) or child.name != "show":
            continue
        for statement in child.body:
            if isinstance(statement, ast.Return):
                return _show_mode_from_expr(statement.value)
        return "both"
    return "both"


def _selectable_script_roots(repo_root: Path | None = None) -> list[tuple[str, Path]]:
    return [(f"{root_label}:scripts", root / "scripts") for root_label, root in _scan_roots(repo_root)]


def _mode_matches(show_mode: str, is_img2img: bool) -> bool:
    if show_mode == "hidden":
        return False
    if show_mode == "img":
        return is_img2img
    if show_mode == "txt":
        return not is_img2img
    return True


def _selectable_titles_from_path(path: Path, *, is_img2img: bool) -> list[str]:
    module = _parse_script_ast(path)
    if module is None:
        return []
    titles: list[str] = []
    for class_node in [node for node in module.body if isinstance(node, ast.ClassDef)]:
        if _inherits_postprocessing(class_node):
            continue
        title = _class_literal_title(class_node)
        if not title:
            continue
        if _mode_matches(_class_show_mode(class_node), is_img2img):
            titles.append(title)
    return titles


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_script_bodies(repo_root: Path | None = None, *, include_hash: bool = True) -> list[ForgeNeoScriptBody]:
    rows: list[ForgeNeoScriptBody] = []
    for source, root in _script_roots(repo_root):
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py"), key=lambda value: str(value).lower()):
            if "__pycache__" in path.parts or path.name.startswith("."):
                continue
            stat = path.stat()
            rows.append(
                ForgeNeoScriptBody(
                    name=path.stem,
                    title=_literal_script_title(path) or path.stem,
                    source=source,
                    path=str(path),
                    size=int(stat.st_size),
                    modified=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                    sha256=_file_sha256(path) if include_hash else "",
                )
            )
    return rows


def script_dropdown_choices(repo_root: Path | None = None, *, is_img2img: bool = False) -> list[str]:
    choices: list[str] = []
    seen: set[str] = set()
    for _, root in _selectable_script_roots(repo_root):
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.py"), key=lambda value: value.name.lower()):
            if path.name.startswith("."):
                continue
            for title in _selectable_titles_from_path(path, is_img2img=is_img2img):
                key = title.casefold()
                if key in seen:
                    continue
                seen.add(key)
                choices.append(title)
    return choices


def script_body_cache_path() -> Path:
    config = ensure_config()
    base = Path(getattr(config, "path_userhome", "") or ".")
    path = base / "config" / "forge_neo_script_bodies.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def refresh_script_body_index(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or _repo_root()
    rows = discover_script_bodies(root)
    path = script_body_cache_path()
    data: dict[str, Any] = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(root),
        "cache_path": str(path),
        "root_count": len(_script_roots(root)),
        "script_count": len(rows),
        "scripts": [asdict(item) for item in rows],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def _is_en(lang: object | None = None) -> bool:
    value = str(lang if lang is not None else getattr(args_manager.args, "language", "cn")).lower()
    return value.startswith("en")


def _text(lang: object | None, en: str, cn: str) -> str:
    return en if _is_en(lang) else cn


def _short_hash(value: object) -> str:
    return str(value or "")[:10]


def script_body_index_html(data: dict[str, Any] | None = None, lang: object | None = None) -> str:
    result = data or refresh_script_body_index()
    scripts = list(result.get("scripts", []) or [])
    rows: list[str] = []
    for item in scripts:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('name', '')))}</td>"
            f"<td>{html.escape(str(item.get('source', '')))}</td>"
            f"<td>{html.escape(str(item.get('size', 0)))}</td>"
            f"<td><code>{html.escape(_short_hash(item.get('sha256')))}</code></td>"
            f"<td>{html.escape(str(item.get('path', '')))}</td>"
            "</tr>"
        )
    if rows:
        table_body = "".join(rows)
    else:
        empty = _text(lang, "No script body files found.", "没有找到脚本体文件。")
        table_body = f'<tr><td colspan="5" class="forge-neo-script-body-empty">{html.escape(empty)}</td></tr>'

    title = _text(lang, "Reload custom script bodies", "重新读取自定义脚本体")
    note = _text(
        lang,
        "Script body index refreshed without importing third-party scripts.",
        "脚本体索引已刷新，未导入第三方脚本。",
    )
    root_label = _text(lang, "Scanned roots", "扫描目录")
    count_label = _text(lang, "Scripts", "脚本数量")
    cache_label = _text(lang, "Cache", "缓存")
    return (
        '<div class="forge-neo-script-body-index">'
        f"<strong>{html.escape(title)}</strong>"
        f"<p>{html.escape(note)}</p>"
        '<div class="forge-neo-script-body-summary">'
        f"<span>{html.escape(root_label)}: {html.escape(str(result.get('root_count', 0)))}</span>"
        f"<span>{html.escape(count_label)}: {html.escape(str(result.get('script_count', 0)))}</span>"
        f"<span>{html.escape(cache_label)}: {html.escape(str(result.get('cache_path', '')))}</span>"
        "</div>"
        '<div class="forge-neo-script-body-table-wrap">'
        '<table id="forge_neo_settings_script_body_table" class="forge-neo-script-body-table">'
        "<thead><tr>"
        f"<th>{html.escape(_text(lang, 'Name', '名称'))}</th>"
        f"<th>{html.escape(_text(lang, 'Source', '来源'))}</th>"
        f"<th>{html.escape(_text(lang, 'Size', '大小'))}</th>"
        f"<th>{html.escape(_text(lang, 'Hash', '哈希'))}</th>"
        f"<th>{html.escape(_text(lang, 'Path', '路径'))}</th>"
        "</tr></thead>"
        f"<tbody>{table_body}</tbody>"
        "</table></div>"
        "</div>"
    )
