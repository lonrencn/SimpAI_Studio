from __future__ import annotations

import math
import os
import random
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DYNAMIC_PROMPTS_EXTENSION = "sd-dynamic-prompts"
DYNAMIC_PROMPTS_EXTENSION_ROOT = ROOT / "forge_neo" / "webui" / "extensions" / DYNAMIC_PROMPTS_EXTENSION
DYNAMIC_PROMPTS_SCRIPT_BASE_NAME = "Dynamic Prompts"
DYNAMIC_PROMPTS_ARG_KEYS = (
    "is_enabled",
    "is_combinatorial",
    "combinatorial_batches",
    "is_magic_prompt",
    "is_feeling_lucky",
    "is_attention_grabber",
    "min_attention",
    "max_attention",
    "magic_prompt_length",
    "magic_temp_value",
    "use_fixed_seed",
    "unlink_seed_from_prompt",
    "disable_negative_prompt",
    "enable_jinja_templates",
    "no_image_generation",
    "max_generations",
    "magic_model",
    "magic_blocklist_regex",
)
DYNAMIC_PROMPTS_ARG_LABELS = {
    "is_enabled": "Dynamic Prompts enabled",
    "is_combinatorial": "Combinatorial generation",
    "combinatorial_batches": "Combinatorial batches",
    "is_magic_prompt": "Magic prompt",
    "is_feeling_lucky": "I'm feeling lucky",
    "is_attention_grabber": "Attention grabber",
    "min_attention": "Minimum attention",
    "max_attention": "Maximum attention",
    "magic_prompt_length": "Max magic prompt length",
    "magic_temp_value": "Magic prompt creativity",
    "use_fixed_seed": "Fixed seed",
    "unlink_seed_from_prompt": "Unlink seed from prompt",
    "disable_negative_prompt": "Don't apply to negative prompts",
    "enable_jinja_templates": "Enable Jinja2 templates",
    "no_image_generation": "Don't generate images",
    "max_generations": "Max generations",
    "magic_model": "Magic prompt model",
    "magic_blocklist_regex": "Magic prompt blocklist regex",
}
DYNAMIC_PROMPTS_ARG_DEFAULTS: dict[str, Any] = {
    "is_enabled": False,
    "is_combinatorial": False,
    "combinatorial_batches": 1,
    "is_magic_prompt": False,
    "is_feeling_lucky": False,
    "is_attention_grabber": False,
    "min_attention": 1.1,
    "max_attention": 1.5,
    "magic_prompt_length": 100,
    "magic_temp_value": 0.7,
    "use_fixed_seed": False,
    "unlink_seed_from_prompt": False,
    "disable_negative_prompt": True,
    "enable_jinja_templates": False,
    "no_image_generation": False,
    "max_generations": 0,
    "magic_model": "",
    "magic_blocklist_regex": "",
}
DYNAMIC_PROMPTS_ARG_ALIASES = {
    "enabled": "is_enabled",
    "active": "is_enabled",
    "dynamic_prompts_enabled": "is_enabled",
    "combinatorial": "is_combinatorial",
    "combinatorial_generation": "is_combinatorial",
    "magic_prompt": "is_magic_prompt",
    "feeling_lucky": "is_feeling_lucky",
    "attention_grabber": "is_attention_grabber",
    "fixed_seed": "use_fixed_seed",
    "jinja": "enable_jinja_templates",
    "jinja_templates": "enable_jinja_templates",
    "blocklist_regex": "magic_blocklist_regex",
}
_VARIANT_RE = re.compile(r"\{([^{}]+)\}")
_WILDCARD_RE = re.compile(r"__([A-Za-z0-9_./ -]+)__")
_VERSION_RE = re.compile(r"__version__\s*=\s*[\"']([^\"']+)[\"']")


def dynamic_prompts_version(extension_root: Path | None = None) -> str:
    root = extension_root or DYNAMIC_PROMPTS_EXTENSION_ROOT
    init_path = root / "sd_dynamic_prompts" / "__init__.py"
    try:
        match = _VERSION_RE.search(init_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return match.group(1) if match else ""


def dynamic_prompts_script_title(extension_root: Path | None = None) -> str:
    version = dynamic_prompts_version(extension_root)
    return f"{DYNAMIC_PROMPTS_SCRIPT_BASE_NAME} v{version}" if version else DYNAMIC_PROMPTS_SCRIPT_BASE_NAME


def dynamic_prompts_script_name_matches(name: object) -> bool:
    return str(name or "").strip().casefold().startswith(DYNAMIC_PROMPTS_SCRIPT_BASE_NAME.casefold())


def _bool_value(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().casefold()
        if text in {"1", "true", "yes", "on", "enabled"}:
            return True
        if text in {"0", "false", "no", "off", "disabled"}:
            return False
    return bool(value)


def _int_value(value: Any, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        result = int(float(str(value).strip())) if value is not None else default
    except Exception:
        result = default
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


def _float_value(value: Any, default: float, *, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        result = float(str(value).strip()) if value is not None else default
    except Exception:
        result = default
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


def _text_value(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _apply_mapping(data: dict[str, Any], value: dict[str, Any]) -> None:
    for raw_key, item in value.items():
        key = DYNAMIC_PROMPTS_ARG_ALIASES.get(str(raw_key), str(raw_key))
        if key in data:
            data[key] = item


def _normalize_data(data: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(data)
    for key in (
        "is_enabled",
        "is_combinatorial",
        "is_magic_prompt",
        "is_feeling_lucky",
        "is_attention_grabber",
        "use_fixed_seed",
        "unlink_seed_from_prompt",
        "disable_negative_prompt",
        "enable_jinja_templates",
        "no_image_generation",
    ):
        normalized[key] = _bool_value(normalized.get(key), bool(DYNAMIC_PROMPTS_ARG_DEFAULTS[key]))
    normalized["combinatorial_batches"] = _int_value(normalized.get("combinatorial_batches"), 1, minimum=1, maximum=10)
    normalized["min_attention"] = _float_value(normalized.get("min_attention"), 1.1, minimum=-1.0, maximum=2.0)
    normalized["max_attention"] = _float_value(normalized.get("max_attention"), 1.5, minimum=-1.0, maximum=2.0)
    normalized["magic_prompt_length"] = _int_value(normalized.get("magic_prompt_length"), 100, minimum=30, maximum=300)
    normalized["magic_temp_value"] = _float_value(normalized.get("magic_temp_value"), 0.7, minimum=0.1, maximum=3.0)
    normalized["max_generations"] = _int_value(normalized.get("max_generations"), 0, minimum=0, maximum=1000)
    normalized["magic_model"] = _text_value(normalized.get("magic_model"), "")
    normalized["magic_blocklist_regex"] = _text_value(normalized.get("magic_blocklist_regex"), "")
    return normalized


def dynamic_prompts_arg_dict(value: object = None, *, enabled: bool | None = None, **overrides: Any) -> dict[str, Any]:
    data = dict(DYNAMIC_PROMPTS_ARG_DEFAULTS)
    if isinstance(value, dict):
        _apply_mapping(data, value)
    elif isinstance(value, (list, tuple)):
        for key, item in zip(DYNAMIC_PROMPTS_ARG_KEYS, value):
            data[key] = item
    elif value is not None:
        data["is_enabled"] = value
    _apply_mapping(data, overrides)
    if enabled is not None:
        data["is_enabled"] = enabled
    return _normalize_data(data)


def dynamic_prompts_arg_list(value: object = None, *, enabled: bool | None = None, **overrides: Any) -> list[Any]:
    data = dynamic_prompts_arg_dict(value, enabled=enabled, **overrides)
    return [data[key] for key in DYNAMIC_PROMPTS_ARG_KEYS]


def dynamic_prompts_script_arg_specs() -> list[dict[str, Any]]:
    data = dynamic_prompts_arg_dict()
    specs: list[dict[str, Any]] = []
    for key in DYNAMIC_PROMPTS_ARG_KEYS:
        value = data[key]
        spec: dict[str, Any] = {"label": DYNAMIC_PROMPTS_ARG_LABELS[key], "value": value}
        if key == "combinatorial_batches":
            spec.update({"minimum": 1, "maximum": 10, "step": 1})
        elif key in {"min_attention", "max_attention"}:
            spec.update({"minimum": -1.0, "maximum": 2.0, "step": 0.1})
        elif key == "magic_prompt_length":
            spec.update({"minimum": 30, "maximum": 300, "step": 10})
        elif key == "magic_temp_value":
            spec.update({"minimum": 0.1, "maximum": 3.0, "step": 0.1})
        elif key == "max_generations":
            spec.update({"minimum": 0, "maximum": 1000, "step": 1})
        specs.append(spec)
    return specs


def _wildcard_dirs(extension_root: Path | None = None) -> list[Path]:
    roots: list[Path] = []
    env_value = os.environ.get("FORGE_NEO_DYNAMIC_PROMPTS_WILDCARD_DIR", "").strip()
    if env_value:
        roots.append(Path(env_value).expanduser())
    root = extension_root or DYNAMIC_PROMPTS_EXTENSION_ROOT
    roots.append(root / "wildcards")
    try:
        from modules.shared import opts

        option_value = getattr(opts, "wildcard_dir", None)
        if option_value:
            roots.insert(0, Path(option_value).expanduser())
    except Exception:
        pass
    out: list[Path] = []
    seen: set[str] = set()
    for path in roots:
        key = os.path.normcase(str(path))
        if key not in seen:
            seen.add(key)
            out.append(path)
    return out


def _wildcard_files(name: str, roots: list[Path]) -> list[Path]:
    clean = name.strip().replace("\\", "/").strip("/")
    if not clean:
        return []
    candidates: list[Path] = []
    for root in roots:
        base = root / clean
        candidates.extend([base, base.with_suffix(".txt"), base.with_suffix(".yaml"), base.with_suffix(".yml")])
    return [path for path in candidates if path.is_file()]


def _read_wildcard_choices(name: str, roots: list[Path]) -> list[str]:
    choices: list[str] = []
    for path in _wildcard_files(name, roots):
        try:
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                text = line.strip()
                if text and not text.startswith("#") and not text.startswith("//"):
                    choices.append(text)
        except UnicodeDecodeError:
            try:
                for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    text = line.strip()
                    if text and not text.startswith("#") and not text.startswith("//"):
                        choices.append(text)
            except Exception:
                continue
        except Exception:
            continue
    return choices


def _replace_random(text: str, rng: random.Random, roots: list[Path]) -> str:
    result = str(text or "")
    for _ in range(100):
        match = _VARIANT_RE.search(result)
        if not match:
            break
        options = [item for item in match.group(1).split("|") if item != ""]
        choice = rng.choice(options) if options else ""
        result = result[: match.start()] + choice + result[match.end() :]
    for _ in range(100):
        match = _WILDCARD_RE.search(result)
        if not match:
            break
        choices = _read_wildcard_choices(match.group(1), roots)
        choice = rng.choice(choices) if choices else match.group(0)
        result = result[: match.start()] + choice + result[match.end() :]
    return result


def _expand_all(text: str, roots: list[Path], *, limit: int) -> list[str]:
    values = [str(text or "")]
    while True:
        expanded = False
        next_values: list[str] = []
        for value in values:
            match = _VARIANT_RE.search(value)
            if match:
                options = [item for item in match.group(1).split("|") if item != ""]
                for option in options or [""]:
                    next_values.append(value[: match.start()] + option + value[match.end() :])
                    if len(next_values) >= limit:
                        return next_values
                expanded = True
                continue
            match = _WILDCARD_RE.search(value)
            if match:
                options = _read_wildcard_choices(match.group(1), roots) or [match.group(0)]
                for option in options:
                    next_values.append(value[: match.start()] + option + value[match.end() :])
                    if len(next_values) >= limit:
                        return next_values
                expanded = True
                continue
            next_values.append(value)
            if len(next_values) >= limit:
                return next_values
        values = next_values
        if not expanded:
            return values


def _repeat_to_length(values: list[str], count: int) -> list[str]:
    if count <= 0:
        return []
    if not values:
        return [""] * count
    return [values[index % len(values)] for index in range(count)]


def dynamic_prompt_values(
    prompt: str,
    *,
    count: int,
    seed: int = -1,
    is_combinatorial: bool = False,
    max_generations: int = 0,
    combinatorial_batches: int = 1,
    extension_root: Path | None = None,
) -> list[str]:
    roots = _wildcard_dirs(extension_root)
    count = max(1, int(count or 1))
    if is_combinatorial:
        limit = max_generations if max_generations > 0 else 1000
        values = _expand_all(prompt, roots, limit=limit)
        batches = max(1, int(combinatorial_batches or 1))
        if batches > 1:
            values = [item for item in values for _ in range(batches)]
        return values[:limit]
    base_seed = seed if isinstance(seed, int) and seed >= 0 else random.randint(0, 2**31 - 1)
    return [_replace_random(prompt, random.Random(base_seed + index), roots) for index in range(count)]


def apply_dynamic_prompts_to_processing(p: Any, *args: Any, extension_root: Path | None = None) -> Any:
    data = dynamic_prompts_arg_dict(list(args))
    if not data["is_enabled"]:
        return p

    batch_size = max(1, _int_value(getattr(p, "batch_size", 1), 1, minimum=1))
    batch_count = max(1, _int_value(getattr(p, "n_iter", 1), 1, minimum=1))
    requested_count = batch_size * batch_count
    original_prompt = (list(getattr(p, "all_prompts", []) or []) or [getattr(p, "prompt", "")])[0]
    original_negative = (list(getattr(p, "all_negative_prompts", []) or []) or [getattr(p, "negative_prompt", "")])[0]
    seed = _int_value(getattr(p, "seed", -1), -1)

    prompts = dynamic_prompt_values(
        str(original_prompt or ""),
        count=requested_count,
        seed=seed,
        is_combinatorial=bool(data["is_combinatorial"]),
        max_generations=int(data["max_generations"]),
        combinatorial_batches=int(data["combinatorial_batches"]),
        extension_root=extension_root,
    )
    if data["disable_negative_prompt"]:
        negative_prompts = _repeat_to_length([str(original_negative or "")], len(prompts))
    else:
        negative_prompts = dynamic_prompt_values(
            str(original_negative or ""),
            count=len(prompts),
            seed=seed + 137 if seed >= 0 else -1,
            is_combinatorial=bool(data["is_combinatorial"]),
            max_generations=len(prompts),
            combinatorial_batches=1,
            extension_root=extension_root,
        )
        negative_prompts = _repeat_to_length(negative_prompts, len(prompts))

    if data["no_image_generation"]:
        prompts = prompts[:1]
        negative_prompts = negative_prompts[:1]
        setattr(p, "batch_size", 1)
        batch_size = 1

    setattr(p, "all_prompts", prompts)
    setattr(p, "all_negative_prompts", negative_prompts)
    setattr(p, "n_iter", max(1, math.ceil(len(prompts) / batch_size)))
    setattr(p, "prompt_for_display", str(original_prompt or ""))
    setattr(p, "prompt", str(original_prompt or ""))

    if getattr(p, "enable_hr", False) and hasattr(p, "all_hr_prompts"):
        hr_prompt = (list(getattr(p, "all_hr_prompts", []) or []) or [getattr(p, "hr_prompt", original_prompt)])[0]
        hr_negative = (list(getattr(p, "all_hr_negative_prompts", []) or []) or [getattr(p, "hr_negative_prompt", original_negative)])[0]
        setattr(p, "all_hr_prompts", list(prompts) if hr_prompt == original_prompt else _repeat_to_length([str(hr_prompt or "")], len(prompts)))
        setattr(
            p,
            "all_hr_negative_prompts",
            list(negative_prompts) if hr_negative == original_negative else _repeat_to_length([str(hr_negative or "")], len(prompts)),
        )
    return p
