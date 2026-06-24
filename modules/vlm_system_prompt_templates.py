import os
import re
from pathlib import Path


DEFAULT_TEMPLATE_DIR = r"I:\dev2\多角色AI推理提示词"
TEMPLATE_DIR_ENV = "SIMPAI_VLM_SYSTEM_PROMPT_TEMPLATE_DIR"
MAX_TEMPLATE_CHARS = 12000


def _template_dir(root=None):
    value = str(root or os.environ.get(TEMPLATE_DIR_ENV) or DEFAULT_TEMPLATE_DIR).strip()
    return Path(value)


def _read_text(path):
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def extract_system_prompt_template(content, max_chars=MAX_TEMPLATE_CHARS):
    text = str(content or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""

    match = re.search(r"(?im)^\s*系统提示词\s*[:：]\s*(.*)$", text)
    if match:
        inline = str(match.group(1) or "").strip()
        body = text[match.end() :].strip()
        text = f"{inline}\n{body}".strip() if inline else body

    stop = re.search(r"(?im)^\s*用户提示词\s*[:：].*$", text)
    if stop:
        text = text[: stop.start()].strip()

    text = re.sub(r"(?:\n\s*)*-{6,}\s*$", "", text).strip()
    if max_chars and len(text) > int(max_chars):
        text = text[: int(max_chars)].rstrip() + "\n..."
    return text


def _template_entry(path, root, max_chars=MAX_TEMPLATE_CHARS):
    stat = path.stat()
    content = extract_system_prompt_template(_read_text(path), max_chars=max_chars)
    return {
        "id": path.name,
        "name": path.stem,
        "filename": path.name,
        "content": content,
        "chars": len(content),
        "size": stat.st_size,
        "mtime": int(stat.st_mtime),
        "source": str(path),
        "template_dir": str(root),
    }


def list_vlm_system_prompt_templates(payload=None, root=None, max_chars=MAX_TEMPLATE_CHARS):
    payload = payload if isinstance(payload, dict) else {}
    root = _template_dir(root or payload.get("template_dir"))
    if not root.exists() or not root.is_dir():
        return {
            "ok": True,
            "templates": [],
            "count": 0,
            "template_dir": str(root),
            "message": "VLM system prompt template directory is not available.",
        }

    templates = []
    for path in sorted(root.glob("*.txt"), key=lambda item: item.name.lower()):
        if not path.is_file():
            continue
        try:
            entry = _template_entry(path, root, max_chars=max_chars)
        except Exception as exc:
            templates.append({
                "id": path.name,
                "name": path.stem,
                "filename": path.name,
                "content": "",
                "chars": 0,
                "source": str(path),
                "error": str(exc),
            })
            continue
        if entry["content"]:
            templates.append(entry)

    return {
        "ok": True,
        "templates": templates,
        "count": len(templates),
        "template_dir": str(root),
    }


def resolve_vlm_system_prompt_template(template_id, payload=None, root=None, max_chars=MAX_TEMPLATE_CHARS):
    target = str(template_id or "").strip()
    if not target:
        return ""
    result = list_vlm_system_prompt_templates(payload=payload, root=root, max_chars=max_chars)
    for item in result.get("templates") or []:
        if target in {str(item.get("id") or ""), str(item.get("name") or ""), str(item.get("filename") or "")}:
            return str(item.get("content") or "").strip()
    return ""
