from __future__ import annotations

import html
from pathlib import Path

from forge_neo.i18n import normalize_lang
from forge_neo.models import SOURCE_BRANCH, SOURCE_COMMIT, SOURCE_LICENSE, SOURCE_PROJECT


def _text(lang: object | None, en: str, cn: str) -> str:
    return en if normalize_lang(lang) == "en" else cn


LICENSE_SECTIONS = [
    (
        ("Special Thanks", "特别鸣谢"),
        [
            (
                "comfy",
                "ComfyUI",
                "https://github.com/Comfy-Org/ComfyUI",
                "https://raw.githubusercontent.com/Comfy-Org/ComfyUI/master/LICENSE",
                ("Many inference code and structural optimizations were taken from this repository", "大量推理代码与结构优化参考自此仓库"),
            ),
        ],
    ),
    (
        ("Diffusion Engine", "扩散引擎"),
        [
            (
                "sd1",
                "Stable Diffusion",
                "https://github.com/Stability-AI/stablediffusion",
                "https://raw.githubusercontent.com/Stability-AI/stablediffusion/main/LICENSE",
                ("Inference Code for SD1", "SD1 推理代码"),
            ),
            (
                "sdxl",
                "Generative Models",
                "https://github.com/Stability-AI/generative-models",
                "https://raw.githubusercontent.com/Stability-AI/generative-models/main/LICENSE-CODE",
                ("Inference Code for SDXL", "SDXL 推理代码"),
            ),
            (
                "flux",
                "Flux",
                "https://github.com/black-forest-labs/flux",
                "https://raw.githubusercontent.com/black-forest-labs/flux/main/LICENSE",
                ("Reference Code for Flux", "Flux 参考代码"),
            ),
            (
                "flux2",
                "Flux2",
                "https://github.com/black-forest-labs/flux2",
                "https://raw.githubusercontent.com/black-forest-labs/flux2/main/LICENSE.md",
                ("Reference Code for Flux.2-Klein", "Flux.2-Klein 参考代码"),
            ),
            (
                "qwen",
                "Qwen Image",
                "https://github.com/QwenLM/Qwen-Image",
                "https://raw.githubusercontent.com/QwenLM/Qwen-Image/refs/heads/main/LICENSE",
                ("Reference Code for Qwen Image", "Qwen Image 参考代码"),
            ),
            (
                "lumina",
                "Lumina Image 2.0",
                "https://github.com/Alpha-VLLM/Lumina-Image-2.0",
                "https://raw.githubusercontent.com/Alpha-VLLM/Lumina-Image-2.0/main/LICENSE",
                ("Reference Code for Lumina", "Lumina 参考代码"),
            ),
            (
                "zimage",
                "Z-Image",
                "https://github.com/Tongyi-MAI/Z-Image",
                "https://raw.githubusercontent.com/Tongyi-MAI/Z-Image/main/LICENSE",
                ("Reference Code for Z-Image", "Z-Image 参考代码"),
            ),
        ],
    ),
    (
        ("Misc. Components", "其他组件"),
        [
            (
                "chain",
                "chaiNNer",
                "https://github.com/chaiNNer-org/chaiNNer",
                "https://raw.githubusercontent.com/chaiNNer-org/chaiNNer/main/LICENSE",
                ("Some codes were borrowed and reworked", "部分代码经过参考与改写"),
            ),
            (
                "tfm",
                "transformers",
                "https://github.com/huggingface/transformers",
                "https://raw.githubusercontent.com/huggingface/transformers/main/LICENSE",
                ("Some codes were borrowed and reworked", "部分代码经过参考与改写"),
            ),
            (
                "dot",
                "diffusers",
                "https://github.com/huggingface/diffusers",
                "https://raw.githubusercontent.com/huggingface/diffusers/main/LICENSE",
                ("Some codes were borrowed and reworked", "部分代码经过参考与改写"),
            ),
            (
                "invoke",
                "InvokeAI",
                "https://github.com/invoke-ai/InvokeAI",
                "https://raw.githubusercontent.com/invoke-ai/InvokeAI/main/LICENSE",
                ("Some code for compatibility with OSX was taken from this repository", "部分 OSX 兼容代码参考自此仓库"),
            ),
            (
                "taesd",
                "TAESD",
                "https://github.com/madebyollin/taesd",
                "https://raw.githubusercontent.com/madebyollin/taesd/main/LICENSE",
                ("Tiny AutoEncoder for efficient live previews", "用于高效实时预览的 Tiny AutoEncoder"),
            ),
        ],
    ),
]


def license_notice_path() -> Path:
    return Path(__file__).resolve().parent.parent / "html" / "forge_neo" / "NOTICE.md"


def license_notice_text() -> str:
    path = license_notice_path()
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _notice_markdown_html(markdown: str) -> str:
    parts: list[str] = []
    in_list = False
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            if in_list:
                parts.append("</ul>")
                in_list = False
            continue
        if line.startswith("# "):
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f"<h3>{html.escape(line[2:].strip())}</h3>")
        elif line.startswith("## "):
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f"<h4>{html.escape(line[3:].strip())}</h4>")
        elif line.startswith("- "):
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{html.escape(line[2:].strip())}</li>")
        else:
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f"<p>{html.escape(line)}</p>")
    if in_list:
        parts.append("</ul>")
    return "".join(parts)


def _source_license_item_html(lang: object | None, item: tuple[str, str, str, str, tuple[str, str]]) -> str:
    item_id, title, project_url, license_url, description = item
    expand = _text(lang, "Expand", "展开")
    loading = _text(lang, "License text will load when this section is opened.", "展开后加载许可证文本。")
    return (
        f'<h2><a href="{html.escape(project_url)}" target="_blank" rel="noopener noreferrer">{html.escape(title)}</a></h2>'
        f"<small>{html.escape(_text(lang, description[0], description[1]))}</small>"
        "<details>"
        f"<summary>{html.escape(expand)}</summary>"
        f'<pre id="{html.escape(item_id)}-license-content" data-license-url="{html.escape(license_url)}">{html.escape(loading)}</pre>'
        "</details>"
    )


def source_license_html(lang: object | None = None) -> str:
    parts = ['<div id="licenses" class="forge-neo-license-notice forge-neo-source-licenses">']
    for section_title, items in LICENSE_SECTIONS:
        parts.append(f'<h4 align="center"><i>{html.escape(_text(lang, section_title[0], section_title[1]))}</i></h4>')
        for item in items:
            parts.append(_source_license_item_html(lang, item))
    parts.append("</div>")
    return "".join(parts)


def port_notice_html(lang: object | None = None) -> str:
    notice = license_notice_text()
    rows = [
        (_text(lang, "Source project", "来源项目"), SOURCE_PROJECT),
        (_text(lang, "Branch", "分支"), SOURCE_BRANCH),
        (_text(lang, "Commit", "提交"), SOURCE_COMMIT),
        (_text(lang, "Upstream license", "上游许可证"), SOURCE_LICENSE),
        (_text(lang, "Notice file", "说明文件"), str(license_notice_path())),
    ]
    row_html = "".join(f"<p><span>{html.escape(label)}</span>{html.escape(value)}</p>" for label, value in rows)
    notice_body = _notice_markdown_html(notice) if notice else f"<p>{html.escape(_text(lang, 'NOTICE.md is not available.', 'NOTICE.md 不可用。'))}</p>"
    expand = _text(lang, "Expand", "展开")
    keep_notice = _text(
        lang,
        "Keep the AGPL-3.0 notice with any redistributed Forge Neo runtime code.",
        "重新分发 Forge Neo 运行时代码时需要保留 AGPL-3.0 说明。",
    )
    return (
        '<div class="forge-neo-license-notice forge-neo-port-notice">'
        f'<h4 align="center"><i>{html.escape(_text(lang, "Forge Neo Port Notice", "Forge Neo 迁移说明"))}</i></h4>'
        f'<div class="forge-neo-license-grid">{row_html}</div>'
        f"<small>{html.escape(keep_notice)}</small>"
        "<details>"
        f"<summary>{html.escape(expand)}</summary>"
        f'<div class="forge-neo-license-markdown">{notice_body}</div>'
        "</details>"
        "</div>"
    )


def license_notice_html(lang: object | None = None) -> str:
    return source_license_html(lang) + port_notice_html(lang)
