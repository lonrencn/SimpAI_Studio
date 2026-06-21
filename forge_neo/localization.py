from __future__ import annotations

import ast
import html
import json
from pathlib import Path

from forge_neo.bootstrap import ensure_config
from forge_neo.i18n import normalize_lang
from forge_neo.settings import SETTINGS_SCHEMA


CALL_ARG_POSITIONS = {
    "_label": (0, 1),
    "_label_for_lang": (1, 2),
    "_status": (1, 2),
    "_text": (1, 2),
    "t": (1, 2),
}


def _text(lang: object | None, en: str, cn: str) -> str:
    return en if normalize_lang(lang) == "en" else cn


def _const_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _function_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _source_paths() -> list[Path]:
    base = Path(__file__).resolve().parent
    return [base / "ui.py", base / "extensions.py", base / "settings.py"]


def _add_pair(pairs: list[tuple[str, str]], seen: set[str], en: str | None, cn: str | None) -> None:
    if not en or cn is None or en in seen:
        return
    seen.add(en)
    pairs.append((en, cn))


class _LocalizationCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.pairs: list[tuple[str, str]] = []
        self.seen: set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:
        name = _function_name(node.func)
        positions = CALL_ARG_POSITIONS.get(name)
        if positions and len(node.args) > max(positions):
            en = _const_str(node.args[positions[0]])
            cn = _const_str(node.args[positions[1]])
            _add_pair(self.pairs, self.seen, en, cn)
        elif name == "_localized_value_choices" and node.args:
            self._collect_localized_value_choices(node.args[0])
        self.generic_visit(node)

    def _collect_localized_value_choices(self, node: ast.AST) -> None:
        if not isinstance(node, (ast.List, ast.Tuple)):
            return
        for item in node.elts:
            if not isinstance(item, (ast.List, ast.Tuple)) or len(item.elts) < 2:
                continue
            en = _const_str(item.elts[0])
            cn = _const_str(item.elts[1])
            _add_pair(self.pairs, self.seen, en, cn)


def collect_localization_pairs(paths: list[Path] | None = None) -> list[tuple[str, str]]:
    collector = _LocalizationCollector()
    for info in SETTINGS_SCHEMA:
        _add_pair(collector.pairs, collector.seen, info.label_en, info.label_cn)
    for path in paths or _source_paths():
        if not path.exists():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        collector.visit(tree)
    return collector.pairs


def build_localization_template(lang: object | None = None) -> dict[str, str]:
    target_lang = normalize_lang(lang)
    return {en: (en if target_lang == "en" else cn) for en, cn in collect_localization_pairs()}


def localization_template_path() -> Path:
    config = ensure_config()
    base = Path(getattr(config, "path_userhome", "") or ".") / "forge_neo"
    base.mkdir(parents=True, exist_ok=True)
    return base / "forge_neo_localization_template.json"


def save_localization_template(lang: object | None = None) -> tuple[Path, dict[str, str]]:
    template = build_localization_template(lang)
    path = localization_template_path()
    path.write_text(json.dumps(template, ensure_ascii=False, indent=4), encoding="utf-8")
    return path, template


def localization_template_html(template: dict[str, str] | None = None, lang: object | None = None, path: str | Path | None = None) -> str:
    data = template or {}
    count = len(data)
    if data:
        state = _text(lang, "Localization template ready.", "本地化模板已生成。")
    else:
        state = _text(lang, "Click Download localization template to generate a JSON file.", "点击下载本地化模板生成 JSON 文件。")
    rows = []
    for key, value in list(data.items())[:12]:
        rows.append(
            "<tr>"
            f"<td>{html.escape(key)}</td>"
            f"<td>{html.escape(value)}</td>"
            "</tr>"
        )
    if not rows:
        rows.append(
            '<tr><td colspan="2" class="forge-neo-localization-empty">'
            f"{html.escape(_text(lang, 'No template entries have been generated yet.', '尚未生成模板条目。'))}"
            "</td></tr>"
        )
    path_text = str(path or "")
    path_html = f'<p><span>{html.escape(_text(lang, "File", "文件"))}</span>{html.escape(path_text)}</p>' if path_text else ""
    return (
        '<div class="forge-neo-localization-template">'
        f"<p><span>{html.escape(_text(lang, 'Status', '状态'))}</span>{html.escape(state)}</p>"
        f"<p><span>{html.escape(_text(lang, 'Entries', '条目'))}</span>{count}</p>"
        f"{path_html}"
        '<div class="forge-neo-extension-table-wrap">'
        '<table id="forge_neo_settings_localization_template_table" class="forge-neo-extension-table">'
        f"<thead><tr><th>{html.escape(_text(lang, 'Source text', '原文'))}</th><th>{html.escape(_text(lang, 'Translation', '译文'))}</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        "</div>"
        "</div>"
    )
