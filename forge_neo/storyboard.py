from __future__ import annotations

import json
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image

from forge_neo.runtime import outputs_dir


STORYBOARDS_PER_PAGE = 9
CHARACTERS_PER_PAGE = 6
STORY_SCRIPT_FILENAME = "script.json"
STORY_GENRES = ["奇幻", "科幻", "爱情", "动作", "悬疑", "恐怖", "喜剧", "冒险", "历史", "其他"]


@dataclass
class StoryboardSendResult:
    success: bool
    message: str
    index: int = -1
    total_count: int = 0
    target_page: int = 1
    image_path: str = ""


@dataclass
class StoryboardEditResult:
    success: bool
    message: str
    index: int = -1
    target_page: int = 1


def storyboard_dir() -> Path:
    path = outputs_dir() / "storyboard"
    path.mkdir(parents=True, exist_ok=True)
    (path / "temp_images").mkdir(exist_ok=True)
    (path / "temp_audios").mkdir(exist_ok=True)
    (path / "character_images").mkdir(exist_ok=True)
    (path / "exports").mkdir(exist_ok=True)
    return path


def storyboard_file() -> Path:
    return storyboard_dir() / "storyboard.json"


def story_script_file() -> Path:
    return storyboard_dir() / STORY_SCRIPT_FILENAME


def _source_story_script_file() -> Path:
    return (
        Path(__file__).resolve().parent
        / "webui"
        / "extensions"
        / "sd-webui-Storyboard-Assistant"
        / "scripts"
        / "storyboard_data"
        / STORY_SCRIPT_FILENAME
    )


def _load_json_dict(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _unique_story_key(stories: dict[str, Any], title: str, *, current_key: str = "") -> str:
    base = str(title or "").strip() or "Untitled Story"
    if base == current_key or base not in stories:
        return base
    suffix = 2
    while f"{base} {suffix}" in stories:
        suffix += 1
    return f"{base} {suffix}"


def _normalize_characters(characters: Any) -> dict[str, dict[str, Any]]:
    if isinstance(characters, list):
        source_items = [(str(item.get("name") or ""), item) for item in characters if isinstance(item, dict)]
    elif isinstance(characters, dict):
        source_items = [(str(name or ""), item) for name, item in characters.items() if isinstance(item, dict)]
    else:
        source_items = []

    normalized: dict[str, dict[str, Any]] = {}
    for raw_name, item in source_items:
        name = str(item.get("name") or raw_name).strip()
        if not name:
            continue
        image_path = str(item.get("image_path") or "").strip()
        cleaned: dict[str, Any] = {
            "name": name,
            "content": str(item.get("content") or ""),
            "updated_at": str(item.get("updated_at") or ""),
        }
        if image_path and Path(image_path).is_file():
            cleaned["image_path"] = image_path
        normalized[name] = cleaned
    return normalized


def _normalize_story_scripts(data: dict[str, Any]) -> dict[str, Any]:
    stories = data.get("stories")
    if not isinstance(stories, dict):
        return {"stories": {}}

    normalized_stories: dict[str, dict[str, Any]] = {}
    for raw_key, raw_story in stories.items():
        if not isinstance(raw_story, dict):
            continue
        key_text = str(raw_key or "").strip()
        title = str(raw_story.get("title") or key_text).strip()
        if not title:
            continue
        key = _unique_story_key(normalized_stories, key_text or title)
        genre = str(raw_story.get("genre") or STORY_GENRES[0]).strip() or STORY_GENRES[0]
        normalized_stories[key] = {
            "title": title,
            "genre": genre,
            "script": str(raw_story.get("script") or raw_story.get("content") or ""),
            "updated_at": str(raw_story.get("updated_at") or ""),
            "characters": _normalize_characters(raw_story.get("characters")),
        }
    return {"stories": normalized_stories}


def _write_zip_from_dir(source_dir: Path, zip_path: Path) -> str:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(path for path in source_dir.rglob("*") if path.is_file()):
            archive.write(file_path, file_path.relative_to(source_dir))
    return str(zip_path)


def _safe_export_name(value: object, fallback: str = "story") -> str:
    text = str(value or fallback)
    safe = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in text).strip()
    return safe or fallback


def _copy_export_file(source: object, export_dir: Path, folder: str, preferred_name: object) -> str:
    source_path = Path(str(source or ""))
    if not source_path.is_file():
        return ""
    target_dir = export_dir / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = source_path.suffix or ".bin"
    stem = _safe_export_name(preferred_name, source_path.stem)
    target = target_dir / f"{stem}{suffix}"
    index = 2
    while target.exists():
        target = target_dir / f"{stem}_{index}{suffix}"
        index += 1
    try:
        shutil.copy2(source_path, target)
    except Exception:
        return ""
    return target.relative_to(export_dir).as_posix()


def load_story_scripts() -> dict[str, Any]:
    path = story_script_file()
    if path.is_file():
        return _normalize_story_scripts(_load_json_dict(path))

    source_data = _normalize_story_scripts(_load_json_dict(_source_story_script_file()))
    if source_data.get("stories"):
        save_story_scripts(source_data)
    return source_data


def save_story_scripts(data: dict[str, Any]) -> Path:
    normalized = _normalize_story_scripts(data)
    path = story_script_file()
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def story_script_choices() -> list[str]:
    stories = load_story_scripts().get("stories", {})
    if not isinstance(stories, dict):
        return []
    return list(stories.keys())


def load_story_script(story_key: object = "") -> dict[str, Any]:
    choices = story_script_choices()
    key = str(story_key or "").strip()
    if not key and choices:
        key = choices[0]
    stories = load_story_scripts().get("stories", {})
    if isinstance(stories, dict) and key in stories and isinstance(stories[key], dict):
        story = dict(stories[key])
        story["key"] = key
        return story
    return {"key": "", "title": "", "genre": STORY_GENRES[0], "script": "", "characters": {}}


def create_story_script(base_title: str = "Untitled Story") -> dict[str, Any]:
    data = load_story_scripts()
    stories = data.setdefault("stories", {})
    if not isinstance(stories, dict):
        stories = {}
        data["stories"] = stories
    title = str(base_title or "Untitled Story").strip() or "Untitled Story"
    key = _unique_story_key(stories, title)
    stories[key] = {
        "title": key,
        "genre": STORY_GENRES[0],
        "script": "",
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "characters": {},
    }
    save_story_scripts(data)
    return load_story_script(key)


def save_story_script(story_key: object, title: object, genre: object, script: object) -> dict[str, Any]:
    data = load_story_scripts()
    stories = data.setdefault("stories", {})
    if not isinstance(stories, dict):
        stories = {}
        data["stories"] = stories

    current_key = str(story_key or "").strip()
    title_text = str(title or "").strip()
    if not title_text:
        raise ValueError("Story title is required.")

    old_story = dict(stories.get(current_key) if current_key in stories and isinstance(stories[current_key], dict) else {})
    key = _unique_story_key(stories, title_text, current_key=current_key if current_key in stories else "")
    if current_key and current_key in stories and key != current_key:
        del stories[current_key]

    genre_text = str(genre or STORY_GENRES[0]).strip() or STORY_GENRES[0]
    old_story.update(
        {
            "title": title_text,
            "genre": genre_text,
            "script": str(script or ""),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "characters": _normalize_characters(old_story.get("characters")),
        }
    )
    stories[key] = old_story
    save_story_scripts(data)
    return load_story_script(key)


def delete_story_script(story_key: object) -> dict[str, Any]:
    data = load_story_scripts()
    stories = data.setdefault("stories", {})
    key = str(story_key or "").strip()
    if isinstance(stories, dict) and key in stories:
        del stories[key]
        save_story_scripts(data)
    choices = story_script_choices()
    return load_story_script(choices[0] if choices else "")


def _story_character_items(story_key: object) -> tuple[str, dict[str, dict[str, Any]]]:
    story = load_story_script(story_key)
    key = str(story.get("key") or "").strip()
    characters = story.get("characters") if isinstance(story, dict) else {}
    return key, _normalize_characters(characters)


def _character_page_count(characters: dict[str, dict[str, Any]]) -> int:
    count = len(characters)
    return max(1, ((count - 1) // CHARACTERS_PER_PAGE) + 1) if count else 1


def clamp_character_page(story_key: object, page: object = 1) -> int:
    _key, characters = _story_character_items(story_key)
    total_pages = _character_page_count(characters)
    try:
        value = int(float(str(page).strip()))
    except Exception:
        value = 1
    return max(1, min(value, total_pages))


def story_character_choices(story_key: object, page: object = 1) -> tuple[list[str], int, int, int]:
    _key, characters = _story_character_items(story_key)
    names = list(characters.keys())
    total_pages = _character_page_count(characters)
    current_page = clamp_character_page(story_key, page)
    start = (current_page - 1) * CHARACTERS_PER_PAGE
    end = start + CHARACTERS_PER_PAGE
    return names[start:end], current_page, total_pages, len(names)


def load_story_character(story_key: object, character_name: object = "") -> dict[str, Any]:
    key, characters = _story_character_items(story_key)
    name = str(character_name or "").strip()
    if not name and characters:
        name = next(iter(characters))
    if name and name in characters:
        character = dict(characters[name])
        character["name"] = name
        character["story_key"] = key
        return character
    return {"story_key": key, "name": "", "content": "", "image_path": None, "updated_at": ""}


def _extract_character_name(character_name: object, content: object) -> str:
    selected = str(character_name or "").strip()
    if selected:
        return selected[:64]

    label_names = {"姓名", "名字", "角色", "Name", "Character", "name", "character"}
    ignored = {"年龄", "性别", "职业", "关系", "背景", "性格", "外貌", "能力", "弱点"}
    for raw_line in str(content or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        for separator in ("：", ":"):
            if separator not in line:
                continue
            left, right = (part.strip() for part in line.split(separator, 1))
            if left in label_names and right:
                return right[:64]
            if left and left not in ignored and left not in label_names:
                return left[:64]
        cleaned = line.strip("[]【】#* ")
        if cleaned and cleaned not in ignored and cleaned not in label_names:
            return cleaned[:64]
    return ""


def _save_character_image(image: object, character_name: object) -> str:
    resolved = _image_from_source(image)
    if resolved is None:
        return ""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_name = _safe_export_name(character_name, "character")
    path = storyboard_dir() / "character_images" / f"{safe_name}_{timestamp}.jpg"
    converted = resolved.convert("RGB")
    resample_filter = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.BICUBIC)
    converted.thumbnail((512, 512), resample_filter)
    converted.save(path, "JPEG", quality=88)
    if resolved is not image and hasattr(resolved, "close"):
        try:
            resolved.close()
        except Exception:
            pass
    return str(path)


def save_story_character(story_key: object, character_name: object, content: object, image: object = None) -> dict[str, Any]:
    key = str(story_key or "").strip()
    if not key:
        raise ValueError("Story is required.")

    data = load_story_scripts()
    stories = data.setdefault("stories", {})
    if not isinstance(stories, dict) or key not in stories or not isinstance(stories[key], dict):
        raise ValueError("Story is required.")

    content_text = str(content or "")
    name = _extract_character_name(character_name, content_text)
    if not name:
        raise ValueError("Character name is required.")

    story = dict(stories[key])
    characters = _normalize_characters(story.get("characters"))
    old_name = str(character_name or "").strip()
    old_character = dict(characters.get(old_name) or characters.get(name) or {})
    if old_name and old_name in characters and old_name != name:
        del characters[old_name]

    image_path = str(old_character.get("image_path") or "")
    if image is not None:
        saved_image = _save_character_image(image, name)
        if saved_image:
            image_path = saved_image

    character: dict[str, Any] = {
        "name": name,
        "content": content_text,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if image_path and Path(image_path).is_file():
        character["image_path"] = image_path
    characters[name] = character
    story["characters"] = characters
    stories[key] = story
    save_story_scripts(data)
    return load_story_character(key, name)


def delete_story_character_image(story_key: object, character_name: object) -> dict[str, Any]:
    key = str(story_key or "").strip()
    name = str(character_name or "").strip()
    if not key or not name:
        return load_story_character(key, name)

    data = load_story_scripts()
    stories = data.setdefault("stories", {})
    if not isinstance(stories, dict) or key not in stories or not isinstance(stories[key], dict):
        return load_story_character(key, name)
    story = dict(stories[key])
    characters = _normalize_characters(story.get("characters"))
    if name in characters:
        characters[name].pop("image_path", None)
        characters[name]["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        story["characters"] = characters
        stories[key] = story
        save_story_scripts(data)
    return load_story_character(key, name)


def delete_story_character(story_key: object, character_name: object) -> dict[str, Any]:
    key = str(story_key or "").strip()
    name = str(character_name or "").strip()
    if not key or not name:
        return load_story_character(key, name)

    data = load_story_scripts()
    stories = data.setdefault("stories", {})
    if isinstance(stories, dict) and key in stories and isinstance(stories[key], dict):
        story = dict(stories[key])
        characters = _normalize_characters(story.get("characters"))
        if name in characters:
            del characters[name]
            story["characters"] = characters
            stories[key] = story
            save_story_scripts(data)

    choices, _page, _total_pages, _total = story_character_choices(key, 1)
    return load_story_character(key, choices[0] if choices else "")


def export_story_script(story_key: object) -> str:
    story = load_story_script(story_key)
    if not story.get("key"):
        return ""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    title = str(story.get("title") or story.get("key") or "story")
    safe_title = _safe_export_name(title, "story")
    export_dir = storyboard_dir() / "exports" / f"script_{safe_title}_{timestamp}"
    export_dir.mkdir(parents=True, exist_ok=True)
    character_image_refs: dict[str, str] = {}
    characters = _normalize_characters(story.get("characters"))
    for name, character in characters.items():
        copied_path = _copy_export_file(character.get("image_path"), export_dir, "character_images", name)
        if copied_path:
            character_image_refs[name] = copied_path

    lines = [
        f"故事标题: {title}",
        f"题材类型: {story.get('genre') or STORY_GENRES[0]}",
        f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]
    if characters:
        lines.append("【角色小传】")
        for name, character in characters.items():
            lines.extend(["", f"### {name}"])
            if character_image_refs.get(name):
                lines.append(f"图片: {character_image_refs[name]}")
            content = str(character.get("content") or "").strip()
            lines.append(content or "（无角色小传）")
        lines.append("")
    lines.extend(["【完整剧本】", "", str(story.get("script") or "")])
    text_path = export_dir / f"{safe_title}.txt"
    text_path.write_text("\n".join(lines), encoding="utf-8")
    zip_path = export_dir.with_suffix(".zip")
    return _write_zip_from_dir(export_dir, zip_path)


def load_storyboards() -> list[dict[str, Any]]:
    path = storyboard_file()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    items: list[dict[str, Any]] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        cleaned = dict(item)
        cleaned["id"] = index
        items.append(cleaned)
    return items


def save_storyboards(items: list[dict[str, Any]]) -> Path:
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        cleaned = dict(item)
        cleaned["id"] = index
        normalized.append(cleaned)
    path = storyboard_file()
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _target_page(index: int) -> int:
    if index < 0:
        return 1
    return (index // STORYBOARDS_PER_PAGE) + 1


def page_count(items: list[dict[str, Any]] | None = None) -> int:
    count = len(items if items is not None else load_storyboards())
    return max(1, ((count - 1) // STORYBOARDS_PER_PAGE) + 1) if count else 1


def clamp_page(page: object, items: list[dict[str, Any]] | None = None) -> int:
    try:
        value = int(float(str(page).strip()))
    except Exception:
        value = 1
    return max(1, min(value, page_count(items)))


def _empty_storyboard_item(index: int, *, description: str = "") -> dict[str, Any]:
    return {
        "id": index,
        "image_path": None,
        "audio_path": None,
        "aspect_ratio": "",
        "description": str(description or ""),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _ensure_storyboard_index(items: list[dict[str, Any]], index: int) -> None:
    while len(items) <= index:
        items.append(_empty_storyboard_item(len(items)))


def _global_cell_index(page: object, cell_index: object, items: list[dict[str, Any]] | None = None) -> int:
    current_page = clamp_page(page, items)
    try:
        cell = int(float(str(cell_index).strip()))
    except Exception:
        cell = 0
    cell = max(0, min(cell, STORYBOARDS_PER_PAGE - 1))
    return (current_page - 1) * STORYBOARDS_PER_PAGE + cell


def _one_based_index(value: object, *, maximum: int | None = None) -> int:
    try:
        index = int(float(str(value).strip()))
    except Exception as exc:
        raise ValueError("Invalid storyboard index.") from exc
    if index < 1:
        raise ValueError("Invalid storyboard index.")
    if maximum is not None and index > maximum:
        raise ValueError("Invalid storyboard index.")
    return index - 1


def _image_from_source(image: object) -> Image.Image | None:
    if isinstance(image, Image.Image):
        return image
    if isinstance(image, dict):
        for key in ("name", "path", "file", "url"):
            value = image.get(key)
            if isinstance(value, str) and Path(value).is_file():
                return Image.open(value)
    if isinstance(image, (list, tuple)) and image:
        return _image_from_source(image[0])
    if isinstance(image, str) and Path(image).is_file():
        return Image.open(image)
    return None


def _file_path_from_source(source: object) -> str:
    if isinstance(source, dict):
        for key in ("name", "path", "file", "url"):
            value = source.get(key)
            if isinstance(value, str) and Path(value).is_file():
                return value
    if isinstance(source, (list, tuple)) and source:
        return _file_path_from_source(source[0])
    if isinstance(source, str) and Path(source).is_file():
        return source
    name = getattr(source, "name", None)
    if isinstance(name, str) and Path(name).is_file():
        return name
    return ""


def _save_storyboard_image(image: object) -> str:
    resolved = _image_from_source(image)
    if resolved is None:
        return ""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = storyboard_dir() / "temp_images" / f"storyboard_{timestamp}.png"
    converted = resolved.convert("RGB")
    converted.save(path, "PNG")
    if resolved is not image and hasattr(resolved, "close"):
        try:
            resolved.close()
        except Exception:
            pass
    return str(path)


def _save_storyboard_audio(audio: object) -> str:
    source = _file_path_from_source(audio)
    if not source:
        return ""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    suffix = Path(source).suffix or ".wav"
    path = storyboard_dir() / "temp_audios" / f"storyboard_audio_{timestamp}{suffix}"
    try:
        shutil.copy2(source, path)
    except Exception:
        return ""
    return str(path)


def send_image_to_storyboard(
    image: object,
    *,
    description: str = "",
    position: str | None = "end",
    current_index: object = None,
) -> StoryboardSendResult:
    image_path = _save_storyboard_image(image)
    if not image_path:
        return StoryboardSendResult(False, "No valid image for storyboard.")

    items = load_storyboards()
    position_text = str(position or "end")
    if position_text == "first":
        insert_index = 0
    elif position_text == "current":
        try:
            selected = int(float(str(current_index).strip()))
        except Exception:
            selected = len(items) - 1
        if not items:
            insert_index = 0
        else:
            selected = max(0, min(selected, len(items) - 1))
            insert_index = selected + 1
    else:
        insert_index = len(items)

    image_size = ""
    try:
        with Image.open(image_path) as img:
            image_size = f"{img.width}x{img.height}"
    except Exception:
        pass

    item = {
        "id": insert_index,
        "image_path": image_path,
        "audio_path": None,
        "aspect_ratio": image_size,
        "description": str(description or ""),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    items.insert(insert_index, item)
    save_storyboards(items)
    total = len(items)
    return StoryboardSendResult(
        True,
        f"Added to storyboard #{insert_index + 1}.",
        index=insert_index,
        total_count=total,
        target_page=_target_page(insert_index),
        image_path=image_path,
    )


def add_blank_storyboard(description: str = "") -> StoryboardSendResult:
    items = load_storyboards()
    insert_index = len(items)
    items.append(_empty_storyboard_item(insert_index, description=description))
    save_storyboards(items)
    return StoryboardSendResult(
        True,
        f"Added blank storyboard #{insert_index + 1}.",
        index=insert_index,
        total_count=len(items),
        target_page=_target_page(insert_index),
    )


def clear_storyboards() -> int:
    count = len(load_storyboards())
    path = storyboard_file()
    if path.exists():
        path.unlink()
    return count


def export_storyboards() -> str:
    items = load_storyboards()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_dir = storyboard_dir() / "exports" / f"storyboard_{timestamp}"
    export_dir.mkdir(parents=True, exist_ok=True)

    exported_items: list[dict[str, Any]] = []
    text_lines = [
        f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"分镜数量: {len(items)}",
        "",
    ]
    for index, item in enumerate(items):
        cleaned = dict(item)
        frame_no = index + 1
        image_ref = _copy_export_file(item.get("image_path"), export_dir, "images", f"frame_{frame_no:03d}")
        audio_ref = _copy_export_file(item.get("audio_path"), export_dir, "audios", f"frame_{frame_no:03d}")
        if image_ref:
            cleaned["export_image_path"] = image_ref
        if audio_ref:
            cleaned["export_audio_path"] = audio_ref
        exported_items.append(cleaned)
        text_lines.extend(
            [
                f"#{frame_no}",
                f"注释: {str(item.get('description') or '').strip() or '无'}",
                f"图片: {image_ref or str(item.get('image_path') or '') or '无'}",
                f"音频: {audio_ref or str(item.get('audio_path') or '') or '无'}",
                "",
            ]
        )

    (export_dir / "storyboard.json").write_text(json.dumps(exported_items, ensure_ascii=False, indent=2), encoding="utf-8")
    (export_dir / "storyboard_content.txt").write_text("\n".join(text_lines), encoding="utf-8")
    zip_path = export_dir.with_suffix(".zip")
    return _write_zip_from_dir(export_dir, zip_path)


def storyboard_page_items(page: object = 1) -> tuple[list[dict[str, Any]], int, int, int]:
    items = load_storyboards()
    total_pages = page_count(items)
    current_page = clamp_page(page, items)
    start = (current_page - 1) * STORYBOARDS_PER_PAGE
    end = start + STORYBOARDS_PER_PAGE
    return items[start:end], current_page, total_pages, len(items)


def storyboard_cell_values(page: object = 1) -> tuple[list[str | None], list[str | None], list[str], list[str], int, int, int]:
    items = load_storyboards()
    current_page = clamp_page(page, items)
    total_pages = page_count(items)
    total_count = len(items)
    start = (current_page - 1) * STORYBOARDS_PER_PAGE
    images: list[str | None] = []
    audios: list[str | None] = []
    descriptions: list[str] = []
    labels: list[str] = []

    for offset in range(STORYBOARDS_PER_PAGE):
        global_index = start + offset
        label = f'<div class="forge-neo-storyboard-cell-label">#{global_index + 1}</div>'
        labels.append(label)
        if global_index >= len(items):
            images.append(None)
            audios.append(None)
            descriptions.append("")
            continue

        item = items[global_index]
        image_path = str(item.get("image_path") or "")
        audio_path = str(item.get("audio_path") or "")
        images.append(image_path if image_path and Path(image_path).is_file() else None)
        audios.append(audio_path if audio_path and Path(audio_path).is_file() else None)
        descriptions.append(str(item.get("description") or ""))

    return images, audios, descriptions, labels, current_page, total_pages, total_count


def update_storyboard_cell_image(page: object, cell_index: object, image: object) -> StoryboardEditResult:
    items = load_storyboards()
    global_index = _global_cell_index(page, cell_index, items)
    _ensure_storyboard_index(items, global_index)
    item = dict(items[global_index])
    if image is None:
        item["image_path"] = None
        item["aspect_ratio"] = ""
    else:
        image_path = _save_storyboard_image(image)
        if not image_path:
            return StoryboardEditResult(False, "No valid image.", index=global_index, target_page=_target_page(global_index))
        item["image_path"] = image_path
        try:
            with Image.open(image_path) as img:
                item["aspect_ratio"] = f"{img.width}x{img.height}"
        except Exception:
            item["aspect_ratio"] = ""
    item["id"] = global_index
    item["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    items[global_index] = item
    save_storyboards(items)
    return StoryboardEditResult(True, "Image updated.", index=global_index, target_page=_target_page(global_index))


def update_storyboard_cell_audio(page: object, cell_index: object, audio: object) -> StoryboardEditResult:
    items = load_storyboards()
    global_index = _global_cell_index(page, cell_index, items)
    _ensure_storyboard_index(items, global_index)
    item = dict(items[global_index])
    if audio is None:
        item["audio_path"] = None
    else:
        audio_path = _save_storyboard_audio(audio)
        if not audio_path:
            return StoryboardEditResult(False, "No valid audio.", index=global_index, target_page=_target_page(global_index))
        item["audio_path"] = audio_path
    item["id"] = global_index
    item["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    items[global_index] = item
    save_storyboards(items)
    return StoryboardEditResult(True, "Audio updated.", index=global_index, target_page=_target_page(global_index))


def update_storyboard_cell_description(page: object, cell_index: object, description: object) -> StoryboardEditResult:
    items = load_storyboards()
    global_index = _global_cell_index(page, cell_index, items)
    _ensure_storyboard_index(items, global_index)
    item = dict(items[global_index])
    item["id"] = global_index
    item["description"] = str(description or "")
    item["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    items[global_index] = item
    save_storyboards(items)
    return StoryboardEditResult(True, "Annotation updated.", index=global_index, target_page=_target_page(global_index))


def clear_storyboard_cell(page: object, cell_index: object) -> StoryboardEditResult:
    items = load_storyboards()
    global_index = _global_cell_index(page, cell_index, items)
    if global_index >= len(items):
        return StoryboardEditResult(False, "No storyboard frame at this position.", index=global_index, target_page=_target_page(global_index))
    items[global_index] = _empty_storyboard_item(global_index)
    save_storyboards(items)
    return StoryboardEditResult(True, "Storyboard frame cleared.", index=global_index, target_page=_target_page(global_index))


def move_storyboard_frame(source_index: object, target_index: object) -> StoryboardEditResult:
    items = load_storyboards()
    if not items:
        return StoryboardEditResult(False, "No storyboard frames.")
    try:
        source = _one_based_index(source_index, maximum=len(items))
        target = _one_based_index(target_index, maximum=len(items))
    except ValueError:
        return StoryboardEditResult(False, "Invalid storyboard index.")
    if source == target:
        return StoryboardEditResult(False, "Source and target are the same.", index=source, target_page=_target_page(source))
    item = items.pop(source)
    items.insert(target, item)
    save_storyboards(items)
    return StoryboardEditResult(True, "Storyboard frame moved.", index=target, target_page=_target_page(target))


def delete_storyboard_frame(source_index: object) -> StoryboardEditResult:
    items = load_storyboards()
    if not items:
        return StoryboardEditResult(False, "No storyboard frames.")
    try:
        source = _one_based_index(source_index, maximum=len(items))
    except ValueError:
        return StoryboardEditResult(False, "Invalid storyboard index.")
    items.pop(source)
    save_storyboards(items)
    target = min(source, max(0, len(items) - 1))
    return StoryboardEditResult(True, "Storyboard frame deleted.", index=target, target_page=_target_page(target))


def move_storyboard_audio(source_index: object, target_index: object) -> StoryboardEditResult:
    items = load_storyboards()
    if not items:
        return StoryboardEditResult(False, "No storyboard frames.")
    try:
        source = _one_based_index(source_index, maximum=len(items))
        target = _one_based_index(target_index, maximum=len(items))
    except ValueError:
        return StoryboardEditResult(False, "Invalid storyboard index.")
    if source == target:
        return StoryboardEditResult(False, "Source and target are the same.", index=source, target_page=_target_page(source))
    audio_path = items[source].get("audio_path")
    if not audio_path:
        return StoryboardEditResult(False, "No audio on source frame.", index=source, target_page=_target_page(source))
    items[source]["audio_path"] = items[target].get("audio_path")
    items[target]["audio_path"] = audio_path
    save_storyboards(items)
    return StoryboardEditResult(True, "Storyboard audio moved.", index=target, target_page=_target_page(target))


def delete_storyboard_audio(source_index: object) -> StoryboardEditResult:
    items = load_storyboards()
    if not items:
        return StoryboardEditResult(False, "No storyboard frames.")
    try:
        source = _one_based_index(source_index, maximum=len(items))
    except ValueError:
        return StoryboardEditResult(False, "Invalid storyboard index.")
    items[source]["audio_path"] = None
    save_storyboards(items)
    return StoryboardEditResult(True, "Storyboard audio deleted.", index=source, target_page=_target_page(source))


def storyboard_gallery_values(page: object = 1) -> list[tuple[str, str]]:
    page_items, _current_page, _total_pages, _total = storyboard_page_items(page)
    values: list[tuple[str, str]] = []
    for item in page_items:
        image_path = str(item.get("image_path") or "")
        if not image_path or not Path(image_path).is_file():
            continue
        label = f"#{int(item.get('id', 0)) + 1}"
        description = str(item.get("description") or "").strip()
        if description:
            label = f"{label} {description[:40]}"
        values.append((image_path, label))
    return values
