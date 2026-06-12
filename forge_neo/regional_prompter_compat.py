from __future__ import annotations

from typing import Any


REGIONAL_PROMPTER_SCRIPT_NAME = "Regional Prompter"
DIFFERENTIAL_REGIONAL_PROMPTER_SCRIPT_NAME = "Differential Regional Prompter"

REGIONAL_PROMPTER_OPTION_NOT_CHANGE_AND = "disable convert 'AND' to 'BREAK'"
REGIONAL_PROMPTER_OPTION_USE_LOHA = "Use LoHa or other"
REGIONAL_PROMPTER_OPTION_USE_BREAK = "Use BREAK to change chunks"
REGIONAL_PROMPTER_OPTION_FLIP_PROMPTS = "Flip prompts"
REGIONAL_PROMPTER_OPTION_COMMENT_OUT = "Comment Out `#`"
REGIONAL_PROMPTER_OPTION_HIRES_ONLY = "Enabled only in Hires Fix"
REGIONAL_PROMPTER_OPTION_HIRES_DISABLED = "Disabled in Hires Fix"
REGIONAL_PROMPTER_OPTION_CHOICES = (
    REGIONAL_PROMPTER_OPTION_NOT_CHANGE_AND,
    REGIONAL_PROMPTER_OPTION_USE_LOHA,
    REGIONAL_PROMPTER_OPTION_USE_BREAK,
    REGIONAL_PROMPTER_OPTION_FLIP_PROMPTS,
    REGIONAL_PROMPTER_OPTION_COMMENT_OUT,
    REGIONAL_PROMPTER_OPTION_HIRES_ONLY,
    REGIONAL_PROMPTER_OPTION_HIRES_DISABLED,
    "debug",
    "debug2",
)

REGIONAL_PROMPTER_ARG_KEYS = (
    "active",
    "debug",
    "rp_selected_tab",
    "matrix_mode",
    "mask_mode",
    "prompt_mode",
    "ratios",
    "base_ratios",
    "use_base",
    "use_common",
    "use_common_negative",
    "calculation_mode",
    "options",
    "lora_negative_textencoder",
    "lora_negative_unet",
    "threshold",
    "mask",
    "lora_stop_step",
    "lora_hires_stop_step",
    "flip",
)

REGIONAL_PROMPTER_ARG_LABELS = {
    "active": "Active",
    "debug": "Debug",
    "rp_selected_tab": "Mode",
    "matrix_mode": "Matrix mode",
    "mask_mode": "Mask mode",
    "prompt_mode": "Prompt mode",
    "ratios": "Ratios",
    "base_ratios": "Base Ratios",
    "use_base": "Use Base",
    "use_common": "Use Common",
    "use_common_negative": "Use Neg-Common",
    "calculation_mode": "Calculation Mode",
    "options": "Options",
    "lora_negative_textencoder": "LoRA Textencoder",
    "lora_negative_unet": "LoRA U-Net",
    "threshold": "Threshold",
    "mask": "Mask",
    "lora_stop_step": "LoRA stop step",
    "lora_hires_stop_step": "LoRA Hires stop step",
    "flip": "Flip",
}

REGIONAL_PROMPTER_ARG_DEFAULTS: dict[str, Any] = {
    "active": False,
    "debug": False,
    "rp_selected_tab": "Matrix",
    "matrix_mode": "Columns",
    "mask_mode": "Mask",
    "prompt_mode": "Prompt",
    "ratios": "1,1",
    "base_ratios": "0.2",
    "use_base": False,
    "use_common": False,
    "use_common_negative": False,
    "calculation_mode": "Attention",
    "options": [],
    "lora_negative_textencoder": "0",
    "lora_negative_unet": "0",
    "threshold": "0.4",
    "mask": "",
    "lora_stop_step": "0",
    "lora_hires_stop_step": "0",
    "flip": False,
}

REGIONAL_PROMPTER_ARG_ALIASES = {
    "enabled": "active",
    "a_debug": "debug",
    "rp_selected_tab": "rp_selected_tab",
    "selected_tab": "rp_selected_tab",
    "tab": "rp_selected_tab",
    "mode": "rp_selected_tab",
    "mmode": "matrix_mode",
    "matrix": "matrix_mode",
    "matrix_submode": "matrix_mode",
    "xmode": "mask_mode",
    "mask_submode": "mask_mode",
    "pmode": "prompt_mode",
    "prompt_submode": "prompt_mode",
    "aratios": "ratios",
    "divide_ratio": "ratios",
    "bratios": "base_ratios",
    "base_ratio": "base_ratios",
    "usebase": "use_base",
    "usecom": "use_common",
    "usencom": "use_common_negative",
    "calcmode": "calculation_mode",
    "calc": "calculation_mode",
    "polymask": "mask",
    "lstop": "lora_stop_step",
    "lstop_hr": "lora_hires_stop_step",
    "flipper": "flip",
}

REGIONAL_PROMPTER_MODE_ALIASES = {
    "matrix": ("Matrix", None),
    "columns": ("Matrix", "Columns"),
    "colums": ("Matrix", "Columns"),
    "horizontal": ("Matrix", "Horizontal"),
    "rows": ("Matrix", "Rows"),
    "vertical": ("Matrix", "Vertical"),
    "random": ("Matrix", "Random"),
    "mask": ("Mask", "Mask"),
    "prompt": ("Prompt", "Prompt"),
    "prompt-ex": ("Prompt", "Prompt-Ex"),
}


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


def _text_value(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _option_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, bool):
        return [REGIONAL_PROMPTER_OPTION_NOT_CHANGE_AND] if value else []
    if isinstance(value, str):
        text = value.strip()
        if not text or text == "No Options":
            return []
        if text.casefold() in {"true", "yes", "on", "1"}:
            return [REGIONAL_PROMPTER_OPTION_NOT_CHANGE_AND]
        if text.casefold() in {"false", "no", "off", "0"}:
            return []
        values = [item.strip() for item in text.split(",")]
    elif isinstance(value, (list, tuple, set)):
        values = [str(item).strip() for item in value]
    else:
        values = [str(value).strip()]
    return [item for item in values if item in REGIONAL_PROMPTER_OPTION_CHOICES]


def _apply_mode(data: dict[str, Any], value: Any) -> None:
    text = str(value or "").strip()
    if not text:
        return
    tab, submode = REGIONAL_PROMPTER_MODE_ALIASES.get(text.casefold(), (text, None))
    data["rp_selected_tab"] = tab
    if submode is None:
        return
    if tab == "Matrix":
        data["matrix_mode"] = submode
    elif tab == "Mask":
        data["mask_mode"] = submode
    elif tab == "Prompt":
        data["prompt_mode"] = submode


def _apply_mapping(data: dict[str, Any], value: dict[str, Any]) -> None:
    for raw_key, item in value.items():
        key = REGIONAL_PROMPTER_ARG_ALIASES.get(str(raw_key), str(raw_key))
        if key == "rp_selected_tab":
            _apply_mode(data, item)
        elif key in data:
            data[key] = item


def _normalize_data(data: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(data)
    normalized["active"] = _bool_value(normalized.get("active"), False)
    normalized["debug"] = _bool_value(normalized.get("debug"), False)
    normalized["rp_selected_tab"] = _text_value(normalized.get("rp_selected_tab"), "Matrix")
    normalized["matrix_mode"] = _text_value(normalized.get("matrix_mode"), "Columns")
    normalized["mask_mode"] = _text_value(normalized.get("mask_mode"), "Mask")
    normalized["prompt_mode"] = _text_value(normalized.get("prompt_mode"), "Prompt")
    normalized["ratios"] = _text_value(normalized.get("ratios"), "1,1")
    normalized["base_ratios"] = _text_value(normalized.get("base_ratios"), "0.2")
    normalized["use_base"] = _bool_value(normalized.get("use_base"), False)
    normalized["use_common"] = _bool_value(normalized.get("use_common"), False)
    normalized["use_common_negative"] = _bool_value(normalized.get("use_common_negative"), False)
    normalized["calculation_mode"] = _text_value(normalized.get("calculation_mode"), "Attention")
    normalized["options"] = _option_values(normalized.get("options"))
    normalized["lora_negative_textencoder"] = _text_value(normalized.get("lora_negative_textencoder"), "0")
    normalized["lora_negative_unet"] = _text_value(normalized.get("lora_negative_unet"), "0")
    normalized["threshold"] = _text_value(normalized.get("threshold"), "0.4")
    normalized["mask"] = normalized.get("mask") or ""
    normalized["lora_stop_step"] = _text_value(normalized.get("lora_stop_step"), "0")
    normalized["lora_hires_stop_step"] = _text_value(normalized.get("lora_hires_stop_step"), "0")
    normalized["flip"] = _bool_value(normalized.get("flip"), False)
    return normalized


def regional_prompter_args_active(value: Any) -> bool:
    if isinstance(value, dict):
        for key in ("active", "enabled"):
            if key in value:
                return _bool_value(value.get(key), False)
        return bool(value)
    if isinstance(value, (list, tuple)):
        return _bool_value(value[0], False) if value else False
    return False


def regional_prompter_arg_dict(value: Any = None, *, enabled: bool | None = None) -> dict[str, Any]:
    data = dict(REGIONAL_PROMPTER_ARG_DEFAULTS)
    if isinstance(value, dict):
        _apply_mapping(data, value)
    elif isinstance(value, (list, tuple)):
        for key, item in zip(REGIONAL_PROMPTER_ARG_KEYS, value):
            data[key] = item
    if enabled is not None:
        data["active"] = bool(enabled)
    return _normalize_data(data)


def regional_prompter_arg_list(value: Any = None, *, enabled: bool | None = None) -> list[Any]:
    data = regional_prompter_arg_dict(value, enabled=enabled)
    return [data[key] for key in REGIONAL_PROMPTER_ARG_KEYS]


def regional_prompter_default_args(*, enabled: bool = False) -> list[Any]:
    return regional_prompter_arg_list(enabled=enabled)


def regional_prompter_script_arg_specs() -> list[dict[str, Any]]:
    values = regional_prompter_default_args()
    specs: list[dict[str, Any]] = []
    for key, value in zip(REGIONAL_PROMPTER_ARG_KEYS, values):
        choices: list[Any] | None = None
        if key == "rp_selected_tab":
            choices = ["Matrix", "Mask", "Prompt"]
        elif key == "matrix_mode":
            choices = ["Columns", "Rows", "Horizontal", "Vertical", "Random"]
        elif key == "mask_mode":
            choices = ["Mask"]
        elif key == "prompt_mode":
            choices = ["Prompt", "Prompt-Ex"]
        elif key == "calculation_mode":
            choices = ["Attention", "Latent"]
        elif key == "options":
            choices = list(REGIONAL_PROMPTER_OPTION_CHOICES)
        specs.append({"label": REGIONAL_PROMPTER_ARG_LABELS[key], "value": value, "choices": choices})
    return specs


def regional_prompter_schema_payload() -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for key, value in regional_prompter_arg_dict().items():
        properties[key] = {
            "title": REGIONAL_PROMPTER_ARG_LABELS[key],
            "default": value,
            "type": _json_schema_type(value),
        }
    return {
        "title": "RegionalPrompterArgs",
        "type": "object",
        "additionalProperties": True,
        "properties": properties,
        "args_order": list(REGIONAL_PROMPTER_ARG_KEYS),
    }


def _json_schema_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if value is None:
        return "null"
    if isinstance(value, (list, tuple)):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"
