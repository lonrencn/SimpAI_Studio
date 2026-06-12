import csv
import hashlib
import json
import os
import random
import re
from dataclasses import dataclass
from itertools import chain, product
from io import StringIO


XYZ_SCRIPT_NAME = "X/Y/Z plot"
MAX_PREVIEW_VARIANTS = 4096
DEFAULT_GRID_MAX_MP = 220


@dataclass(frozen=True)
class AxisOption:
    label: str
    value_type: str
    apply: str = ""
    format_mode: str = "label"
    cost: float = 0.0
    mode: str = "both"
    choices_kind: str = ""
    prepare: str = ""
    confirm: str = ""

    def to_dict(self, include_choices=False, choices_payload=None):
        data = {
            "label": self.label,
            "type": self.value_type,
            "apply": self.apply,
            "format": self.format_mode,
            "cost": self.cost,
            "mode": self.mode,
            "choices_kind": self.choices_kind,
            "prepare": self.prepare,
            "confirm": self.confirm,
            "has_choices": bool(self.choices_kind),
        }
        if include_choices:
            data["choices"] = _choices_for_kind(self.choices_kind, choices_payload)
        return data


AXIS_OPTIONS = [
    AxisOption("Nothing", "str", "noop", "nothing"),
    AxisOption("Prompt", "str", "prompt", "value"),
    AxisOption("Negative Prompt", "str", "negative_prompt", "value"),
    AxisOption("Seed", "int", "seed"),
    AxisOption("Base Model", "str", "base_model", "remove_path", cost=1.0, choices_kind="checkpoints", confirm="checkpoint"),
    AxisOption("Refiner", "str", "refiner_model", "remove_path", cost=1.0, choices_kind="refiner_checkpoints", confirm="checkpoint_or_none"),
    AxisOption("CLIP", "str", "clip_model", "remove_path", cost=0.7, choices_kind="clip"),
    AxisOption("VAE", "str", "vae", cost=0.7, choices_kind="vae"),
    AxisOption("Upscale Model", "str", "upscale_model", "remove_path", choices_kind="upscalers"),
    AxisOption("Styles", "str", "styles", choices_kind="styles"),
    AxisOption("Resolution Template", "str", "template", choices_kind="resolution_templates"),
    AxisOption("Aspect Ratio", "str", "aspect_ratio", choices_kind="aspect_ratios"),
    AxisOption("Random Size", "str", "random_aspect_ratio", choices_kind="boolean_reverse"),
    AxisOption("Width", "int", "width"),
    AxisOption("Height", "int", "height"),
    AxisOption("Normalize", "int", "quantize", choices_kind="quantize_steps"),
    AxisOption("Resolution Scale", "float", "multiplier"),
    AxisOption("Resolution Edit Mode", "str", "edit_mode", choices_kind="resolution_edit_modes"),
    AxisOption("Guidance Scale", "float", "guidance_scale"),
    AxisOption("Forced Sampling Steps", "int", "overwrite_step"),
    AxisOption("Sampler", "str", "sampler_name", "value", choices_kind="samplers", confirm="sampler"),
    AxisOption("Scheduler", "str", "scheduler_name", choices_kind="schedulers"),
    AxisOption("CLIP Skip", "int", "clip_skip"),
]

AXIS_BY_LABEL = {option.label: option for option in AXIS_OPTIONS}

SIMPAI_XYZ_STATIC_CHOICES = {
    "samplers": [
        "euler",
        "euler_cfg_pp",
        "euler_ancestral",
        "euler_ancestral_cfg_pp",
        "heun",
        "dpm_2",
        "dpm_2_ancestral",
        "lms",
        "dpmpp_2s_ancestral",
        "dpmpp_sde",
        "dpmpp_sde_gpu",
        "dpmpp_2m",
        "dpmpp_2m_cfg_pp",
        "dpmpp_2m_sde",
        "dpmpp_2m_sde_gpu",
        "dpmpp_3m_sde",
        "dpmpp_3m_sde_gpu",
        "lcm",
        "res_multistep",
        "er_sde",
        "ddim",
        "uni_pc",
        "uni_pc_bh2",
    ],
    "samplers_img2img": [
        "euler",
        "euler_cfg_pp",
        "euler_ancestral",
        "euler_ancestral_cfg_pp",
        "heun",
        "dpm_2",
        "dpm_2_ancestral",
        "lms",
        "dpmpp_2s_ancestral",
        "dpmpp_sde",
        "dpmpp_sde_gpu",
        "dpmpp_2m",
        "dpmpp_2m_cfg_pp",
        "dpmpp_2m_sde",
        "dpmpp_2m_sde_gpu",
        "dpmpp_3m_sde",
        "dpmpp_3m_sde_gpu",
        "lcm",
        "res_multistep",
        "er_sde",
        "ddim",
        "uni_pc",
        "uni_pc_bh2",
    ],
    "schedulers": [
        "normal",
        "karras",
        "exponential",
        "sgm_uniform",
        "simple",
        "ddim_uniform",
        "beta",
        "linear_quadratic",
        "kl_optimal",
        "bong_tangent",
        "beta57",
    ],
    "upscalers": ["default"],
    "vae": ["Default (model)"],
    "clip": ["Default (model)"],
    "resolution_templates": ["Preset", "SDXL", "Landscape", "Portrait", "Square"],
    "aspect_ratios": ["1024*1024", "832*1216", "1216*832", "896*1152", "1152*896"],
    "quantize_steps": [1, 8, 16, 32, 64],
    "resolution_edit_modes": ["proportional", "crop", "scale", "pad"],
}

RE_RANGE_INT = re.compile(r"\s*([+-]?\s*\d+)\s*-\s*([+-]?\s*\d+)(?:\s*\(([+-]?\d+)\s*\))?\s*")
RE_COUNT_INT = re.compile(r"\s*([+-]?\s*\d+)\s*-\s*([+-]?\s*\d+)(?:\s*\[(\d+)\s*])?\s*")
RE_RANGE_FLOAT = re.compile(r"\s*([+-]?\s*\d+(?:\.\d*)?)\s*-\s*([+-]?\s*\d+(?:\.\d*)?)(?:\s*\(([+-]?\d+(?:\.\d*)?)\s*\))?\s*")
RE_COUNT_FLOAT = re.compile(r"\s*([+-]?\s*\d+(?:\.\d*)?)\s*-\s*([+-]?\s*\d+(?:\.\d*)?)(?:\s*\[(\d+)\s*])?\s*")


def _safe_list(value):
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def csv_string_to_list_strip(data_str):
    if isinstance(data_str, list):
        return [str(item).strip() for item in data_str if str(item).strip()]
    text = str(data_str or "")
    if not text.strip():
        return []
    return [
        str(item).strip()
        for item in chain.from_iterable(csv.reader(StringIO(text), skipinitialspace=True))
        if str(item).strip()
    ]


def list_to_csv_string(values):
    with StringIO() as output:
        csv.writer(output).writerow([str(item) for item in values])
        return output.getvalue().strip()


def _dedupe_choices(values):
    result = []
    seen = set()
    for value in values or []:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _source_node_from_payload(payload):
    if not isinstance(payload, dict):
        return {}
    for key in ("source_node", "preset_node"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _values_for_keys(value, keys):
    keys = {str(key) for key in keys}
    result = []
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key) in keys:
                if isinstance(item, (list, tuple)):
                    result.extend(item)
                else:
                    result.append(item)
            result.extend(_values_for_keys(item, keys))
    elif isinstance(value, (list, tuple)):
        for item in value:
            result.extend(_values_for_keys(item, keys))
    return _dedupe_choices(result)


def _source_choice_values(payload, *keys):
    node = _source_node_from_payload(payload)
    return _values_for_keys(node, keys)


def _simpai_flag_choices(attr_name):
    try:
        import modules.flags as flags
        return _dedupe_choices(getattr(flags, attr_name, []) or [])
    except Exception:
        return []


def _simpai_config_choices(attr_name, prefix=None):
    try:
        import modules.config as config
        values = []
        if prefix:
            values.extend(prefix)
        values.extend(getattr(config, attr_name, []) or [])
        return _dedupe_choices(values)
    except BaseException:
        return _dedupe_choices(prefix or [])


def _simpai_model_catalog(payload):
    source_node = _source_node_from_payload(payload)
    if not source_node:
        return {}
    try:
        from modules.canvas_workbench_models import get_model_catalog_for_preset
        response = get_model_catalog_for_preset({"preset_node": source_node})
        catalog = response.get("catalog") if isinstance(response, dict) else {}
        return catalog if isinstance(catalog, dict) else {}
    except BaseException:
        return {}


def _int_text(value):
    return str(value).replace(" ", "")


def _float_range(start, end, step):
    if step == 0:
        raise ValueError("range step must not be 0")
    values = []
    current = start
    guard = 0
    if step > 0:
        while current <= end + step / 1000000:
            values.append(current)
            current += step
            guard += 1
            if guard > MAX_PREVIEW_VARIANTS:
                break
    else:
        while current >= end + step / 1000000:
            values.append(current)
            current += step
            guard += 1
            if guard > MAX_PREVIEW_VARIANTS:
                break
    return values


def _linspace(start, end, count):
    count = int(count)
    if count <= 0:
        return []
    if count == 1:
        return [start]
    step = (end - start) / float(count - 1)
    return [start + step * index for index in range(count)]


def _expand_int_values(values):
    expanded = []
    for raw in values:
        text = _int_text(raw)
        if not text:
            continue
        match = RE_RANGE_INT.fullmatch(text)
        count_match = RE_COUNT_INT.fullmatch(text)
        if match:
            start = int(_int_text(match.group(1)))
            end = int(_int_text(match.group(2))) + 1
            step = int(_int_text(match.group(3) or "1"))
            if step == 0:
                raise ValueError("integer range step must not be 0")
            expanded.extend(list(range(start, end, step)))
        elif count_match:
            start = int(_int_text(count_match.group(1)))
            end = int(_int_text(count_match.group(2)))
            count = int(_int_text(count_match.group(3) or "1"))
            expanded.extend([int(item) for item in _linspace(start, end, count)])
        else:
            expanded.append(int(float(text)))
    return expanded


def _expand_float_values(values):
    expanded = []
    for raw in values:
        text = str(raw).replace(" ", "")
        if not text:
            continue
        match = RE_RANGE_FLOAT.fullmatch(text)
        count_match = RE_COUNT_FLOAT.fullmatch(text)
        if match:
            start = float(match.group(1))
            end = float(match.group(2))
            step = float(match.group(3) or "1")
            expanded.extend(_float_range(start, end, step))
        elif count_match:
            start = float(count_match.group(1))
            end = float(count_match.group(2))
            count = int(count_match.group(3) or "1")
            expanded.extend(_linspace(start, end, count))
        else:
            expanded.append(float(text))
    return expanded


def _prompt_files_from_value(values):
    raw_values = _safe_list(values)
    if len(raw_values) == 1:
        candidate = str(raw_values[0] or "").strip().strip('"')
        if candidate and os.path.isdir(candidate):
            return [
                os.path.abspath(os.path.join(candidate, name))
                for name in sorted(os.listdir(candidate))
                if name.lower().endswith(".txt") and os.path.isfile(os.path.join(candidate, name))
            ]
    result = []
    for value in raw_values:
        text = str(value or "").strip().strip('"')
        if text:
            result.append(text)
    return result


def _simpai_resolution_templates():
    try:
        import modules.flags as flags
        ratios = getattr(flags, "available_aspect_ratios_list", {}) or {}
        return _dedupe_choices(["Preset"] + list(ratios.keys()) + SIMPAI_XYZ_STATIC_CHOICES.get("resolution_templates", []))
    except Exception:
        return _dedupe_choices(SIMPAI_XYZ_STATIC_CHOICES.get("resolution_templates", []))


def _simpai_aspect_ratios():
    try:
        import modules.flags as flags
        ratios = getattr(flags, "available_aspect_ratios_list", {}) or {}
        values = []
        for items in ratios.values():
            if isinstance(items, (list, tuple)):
                values.extend(items)
        return _dedupe_choices(values + SIMPAI_XYZ_STATIC_CHOICES.get("aspect_ratios", []))
    except Exception:
        return _dedupe_choices(SIMPAI_XYZ_STATIC_CHOICES.get("aspect_ratios", []))


def _simpai_quantize_steps():
    try:
        import modules.flags as flags
        return _dedupe_choices(getattr(flags, "resolution_quantize_steps", []) or SIMPAI_XYZ_STATIC_CHOICES.get("quantize_steps", []))
    except Exception:
        return _dedupe_choices(SIMPAI_XYZ_STATIC_CHOICES.get("quantize_steps", []))


def _simpai_resolution_edit_modes():
    try:
        import modules.flags as flags
        return _dedupe_choices(getattr(flags, "resolution_edit_modes", []) or SIMPAI_XYZ_STATIC_CHOICES.get("resolution_edit_modes", []))
    except Exception:
        return _dedupe_choices(SIMPAI_XYZ_STATIC_CHOICES.get("resolution_edit_modes", []))


def _choices_for_kind(kind, payload=None):
    if not kind:
        return []
    if kind == "boolean_reverse":
        return ["False", "True"]
    if kind == "refiner_checkpoints":
        catalog = _simpai_model_catalog(payload)
        return _dedupe_choices(
            catalog.get("refiner_filenames")
            or ["None"] + _choices_for_kind("checkpoints", payload)
        )
    if kind in ("samplers", "samplers_img2img"):
        return _dedupe_choices(
            _source_choice_values(payload, "sampler_name", "sampler", "default_sampler", "hr_sampler_name")
            + _simpai_flag_choices("comfy_sampler_list")
            + SIMPAI_XYZ_STATIC_CHOICES.get(kind, [])
        )
    if kind == "schedulers":
        return _dedupe_choices(
            _source_choice_values(payload, "scheduler_name", "scheduler", "default_scheduler", "hr_scheduler_name")
            + _simpai_flag_choices("comfy_scheduler_list")
            + SIMPAI_XYZ_STATIC_CHOICES.get(kind, [])
        )
    if kind == "checkpoints":
        catalog = _simpai_model_catalog(payload)
        return _dedupe_choices(
            _source_choice_values(payload, "base_model", "refiner_model", "checkpoint", "default_model")
            + (catalog.get("model_filenames") or [])
            + _simpai_config_choices("model_filenames")
        )
    if kind == "clip":
        catalog = _simpai_model_catalog(payload)
        return _dedupe_choices(
            _source_choice_values(payload, "clip_model", "clip", "default_clip")
            + (catalog.get("clip_filenames") or [])
            + _simpai_config_choices("clip_filenames", SIMPAI_XYZ_STATIC_CHOICES.get("clip", []))
        )
    if kind == "vae":
        catalog = _simpai_model_catalog(payload)
        return _dedupe_choices(
            _source_choice_values(payload, "vae", "vae_name", "default_vae")
            + (catalog.get("vae_filenames") or [])
            + _simpai_config_choices("vae_filenames", SIMPAI_XYZ_STATIC_CHOICES.get("vae", []))
        )
    if kind == "styles":
        try:
            import modules.sdxl_styles as sdxl_styles
            styles = list(getattr(sdxl_styles, "legal_style_names", []) or [])
        except Exception:
            styles = []
        return _dedupe_choices(_source_choice_values(payload, "style_selections", "styles", "default_styles") + styles)
    if kind == "upscalers":
        catalog = _simpai_model_catalog(payload)
        return _dedupe_choices(
            _source_choice_values(payload, "upscale_model", "hr_upscaler")
            + (catalog.get("upscale_model_filenames") or [])
            + _simpai_config_choices("upscale_model_filenames", SIMPAI_XYZ_STATIC_CHOICES.get("upscalers", []))
        )
    if kind == "resolution_templates":
        return _dedupe_choices(_source_choice_values(payload, "template", "default_template", "available_aspect_ratios_selection") + _simpai_resolution_templates())
    if kind == "aspect_ratios":
        return _dedupe_choices(_source_choice_values(payload, "aspect_ratio", "scene_aspect_ratio", "aspect_ratios_selection") + _simpai_aspect_ratios())
    if kind == "quantize_steps":
        return _simpai_quantize_steps()
    if kind == "resolution_edit_modes":
        return _simpai_resolution_edit_modes()
    return _dedupe_choices(SIMPAI_XYZ_STATIC_CHOICES.get(kind, []))


def _axis_options_for_mode(mode):
    mode = str(mode or "txt2img").lower()
    if mode in ("txt", "t2i", "text2img", "text-to-image"):
        mode = "txt2img"
    if mode in ("img", "i2i", "image2image", "img-to-img"):
        mode = "img2img"
    result = []
    seen = set()
    for option in AXIS_OPTIONS:
        if option.mode not in ("both", mode):
            continue
        key = (option.label, option.mode)
        if key in seen:
            continue
        seen.add(key)
        result.append(option)
    return result


def axis_options(payload=None):
    payload = payload or {}
    mode = payload.get("mode") or _mode_from_node(payload.get("source_node") or payload.get("preset_node") or {})
    include_choices = bool(payload.get("include_choices"))
    options = _axis_options_for_mode(mode)
    return {
        "ok": True,
        "script": XYZ_SCRIPT_NAME,
        "mode": mode or "txt2img",
        "options": [option.to_dict(include_choices=include_choices, choices_payload=payload) for option in options],
    }


def _mode_from_node(node):
    if not isinstance(node, dict):
        return "txt2img"
    node_type = str(node.get("type") or node.get("node_type") or "").lower()
    if node_type == "classic":
        params = node.get("params") if isinstance(node.get("params"), dict) else {}
        mode = str(params.get("classic_mode") or params.get("mode") or "").lower()
        if mode in ("t2i", "txt2img", "text_to_image"):
            return "txt2img"
        return "img2img"
    return "txt2img"


def _axis_option(label, mode):
    wanted = str(label or "Nothing")
    for option in _axis_options_for_mode(mode):
        if option.label == wanted:
            return option
    return AXIS_BY_LABEL.get(wanted) or AXIS_BY_LABEL["Nothing"]


def _format_value(option, value):
    if option.format_mode == "nothing":
        return ""
    if option.format_mode == "value":
        return str(value)
    if option.format_mode == "join_list":
        return ", ".join([str(item) for item in value]) if isinstance(value, (list, tuple)) else str(value)
    if option.format_mode == "remove_path":
        return os.path.basename(str(value))
    if isinstance(value, float):
        text = f"{value:.8f}".rstrip("0").rstrip(".")
    else:
        text = str(value)
    return f"{option.label}: {text}"


def process_axis(axis, mode="txt2img"):
    axis = axis if isinstance(axis, dict) else {}
    option = _axis_option(axis.get("type") or axis.get("label") or "Nothing", mode)
    csv_mode = bool(axis.get("csv_mode"))
    if option.label == "Nothing":
        values = [0]
    elif option.choices_kind and not csv_mode and isinstance(axis.get("values"), list) and axis.get("values"):
        values = [str(item) for item in axis.get("values")]
    elif option.prepare == "prompt_files":
        raw = axis.get("values") if isinstance(axis.get("values"), list) and axis.get("values") else csv_string_to_list_strip(axis.get("values_text") or "")
        values = _prompt_files_from_value(raw)
    else:
        values = csv_string_to_list_strip(axis.get("values_text") if axis.get("values_text") is not None else axis.get("values") or "")

    if option.value_type == "int":
        values = _expand_int_values(values)
    elif option.value_type == "float":
        values = _expand_float_values(values)
    else:
        values = [str(item) for item in values]

    if option.label != "Nothing" and not values:
        raise ValueError(f"{option.label} axis has no values")

    return {
        "axis": axis.get("axis") or "",
        "type": option.label,
        "values_text": axis.get("values_text") or (list_to_csv_string(axis.get("values")) if isinstance(axis.get("values"), list) else str(axis.get("values") or "")),
        "values": values,
        "resolved_values": values,
        "labels": [_format_value(option, value) for value in values],
        "option": option.to_dict(include_choices=False),
    }


def _stable_seed_source(job):
    text = json.dumps(job or {}, ensure_ascii=False, sort_keys=True, default=str)
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


def _resolve_seed_axis(axis, keep_minus_one, rng):
    option = axis.get("option") or {}
    if option.get("label") not in ("Seed", "Var. seed"):
        return axis
    if keep_minus_one:
        return axis
    values = []
    labels = []
    for value in axis.get("values") or []:
        if value in (None, "", -1):
            next_value = int(rng.randrange(4294967294))
        else:
            next_value = int(value)
        values.append(next_value)
        labels.append(_format_value(AXIS_BY_LABEL.get(option.get("label")) or AXIS_BY_LABEL["Seed"], next_value))
    next_axis = dict(axis)
    next_axis["values"] = values
    next_axis["resolved_values"] = values
    next_axis["labels"] = labels
    next_axis["fixed_seed_values"] = values
    return next_axis


def _axis_value_map(x_axis, y_axis, z_axis, ix, iy, iz):
    axes = [("x", x_axis, ix), ("y", y_axis, iy), ("z", z_axis, iz)]
    result = {}
    labels = {}
    for name, axis, index in axes:
        result[name] = {
            "type": axis.get("type"),
            "value": (axis.get("values") or [0])[index],
            "label": (axis.get("labels") or [""])[index],
        }
        labels[name] = result[name]["label"]
    return result, labels


def _variant_seed(base_seed, options, ix, iy, iz, x_len, y_len):
    seed = int(base_seed)
    if seed == -1:
        return -1
    if options.get("vary_seeds_x"):
        seed += ix
    if options.get("vary_seeds_y"):
        seed += iy * (x_len if options.get("vary_seeds_x") else 1)
    if options.get("vary_seeds_z"):
        seed += iz * (x_len if options.get("vary_seeds_x") else 1) * (y_len if options.get("vary_seeds_y") else 1)
    return seed


def _variant_seed_from_axes(base_seed, axes, indices, options, x_len, y_len):
    seed = int(base_seed)
    for axis, index in zip(axes, indices):
        if axis.get("type") == "Seed":
            seed = int((axis.get("values") or [-1])[index])
    return _variant_seed(seed, options, indices[0], indices[1], indices[2], x_len, y_len)


def _bool_value(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _apply_axis_patch(patch, axis_type, value):
    params = patch.setdefault("params", {})
    models = patch.setdefault("models_config", {}).setdefault("overrides", {})
    resolution = patch.setdefault("resolution_config", {}).setdefault("overrides", {})
    generation = patch.setdefault("generation_config", {}).setdefault("overrides", {})
    styles = patch.setdefault("styles_config", {}).setdefault("overrides", {})
    if axis_type in ("Nothing", ""):
        return
    if axis_type == "Prompt":
        params["prompt"] = str(value)
    elif axis_type == "Negative Prompt":
        params["negative_prompt"] = str(value)
    elif axis_type == "Seed":
        params["image_seed"] = int(value)
    elif axis_type == "Base Model":
        models["base_model"] = str(value)
    elif axis_type == "Refiner":
        models["refiner_model"] = str(value)
    elif axis_type == "CLIP":
        models["clip_model"] = str(value)
    elif axis_type == "VAE":
        models["vae"] = str(value)
    elif axis_type == "Upscale Model":
        models["upscale_model"] = str(value)
    elif axis_type == "Styles":
        current = styles.get("style_selections")
        next_styles = csv_string_to_list_strip(value)
        styles["style_selections"] = (current if isinstance(current, list) else []) + next_styles
    elif axis_type == "Resolution Template":
        resolution["template"] = str(value)
    elif axis_type == "Aspect Ratio":
        resolution["aspect_ratio"] = str(value)
    elif axis_type == "Random Size":
        resolution["random_aspect_ratio"] = _bool_value(value)
    elif axis_type == "Width":
        resolution["width"] = int(value)
    elif axis_type == "Height":
        resolution["height"] = int(value)
    elif axis_type == "Normalize":
        resolution["quantize"] = int(value)
    elif axis_type == "Resolution Scale":
        resolution["multiplier"] = float(value)
    elif axis_type == "Resolution Edit Mode":
        resolution["edit_mode"] = str(value)
    elif axis_type == "Guidance Scale":
        generation["guidance_scale"] = float(value)
        params["guidance_scale"] = float(value)
    elif axis_type == "Forced Sampling Steps":
        generation["overwrite_step"] = int(value)
    elif axis_type == "Sampler":
        generation["sampler_name"] = str(value)
    elif axis_type == "Scheduler":
        generation["scheduler_name"] = str(value)
    elif axis_type == "CLIP Skip":
        generation["clip_skip"] = int(value)


def _parse_size(value):
    text = str(value or "").lower().replace(" ", "")
    if "x" not in text:
        raise ValueError(f'Invalid Size "{value}" for X/Y/Z Plot')
    left, right = text.split("x", 1)
    width = int(float(left))
    height = int(float(right))
    if width <= 0 or height <= 0:
        raise ValueError(f'Invalid Size "{value}" for X/Y/Z Plot')
    return width, height


def _merged_resolution(node):
    config = node.get("resolution_config") if isinstance(node.get("resolution_config"), dict) else {}
    defaults = config.get("defaults") if isinstance(config.get("defaults"), dict) else {}
    overrides = config.get("overrides") if isinstance(config.get("overrides"), dict) else {}
    result = dict(defaults)
    result.update(overrides)
    return result


def _preview_size(node):
    resolution = _merged_resolution(node if isinstance(node, dict) else {})
    width = int(float(resolution.get("width") or 1024))
    height = int(float(resolution.get("height") or 1024))
    return max(1, width), max(1, height)


def _build_variant_patch(x_axis, y_axis, z_axis, ix, iy, iz, seed, options):
    patch = {"params": {}, "generation_config": {"overrides": {}}, "models_config": {"overrides": {}}, "resolution_config": {"overrides": {}}, "styles_config": {"overrides": {}}}
    for axis, index in ((x_axis, ix), (y_axis, iy), (z_axis, iz)):
        value = (axis.get("values") or [0])[index]
        _apply_axis_patch(patch, axis.get("type"), value)
    if seed != -1:
        patch.setdefault("params", {})["image_seed"] = seed
    return patch


def _processing_order(x_axis, y_axis, z_axis):
    axes = [
        ("x", x_axis.get("option", {}).get("cost", 0.0)),
        ("y", y_axis.get("option", {}).get("cost", 0.0)),
        ("z", z_axis.get("option", {}).get("cost", 0.0)),
    ]
    axes.sort(key=lambda item: item[1], reverse=True)
    return [item[0] for item in axes]


def preview_job(payload, state_params=None):
    if not isinstance(payload, dict):
        return {"ok": False, "error": "payload is not an object"}
    job = payload.get("job") if isinstance(payload.get("job"), dict) else payload
    source_node = job.get("source_node") if isinstance(job.get("source_node"), dict) else payload.get("source_node") if isinstance(payload.get("source_node"), dict) else {}
    mode = job.get("mode") or payload.get("mode") or _mode_from_node(source_node)
    axes_raw = job.get("axes") if isinstance(job.get("axes"), list) else []
    axes_by_name = {str(axis.get("axis") or "").lower(): axis for axis in axes_raw if isinstance(axis, dict)}
    axes = []
    try:
        for name in ("x", "y", "z"):
            axis = dict(axes_by_name.get(name) or {})
            axis["axis"] = name
            axes.append(process_axis(axis, mode=mode))
    except Exception as exc:
        return {"ok": False, "error": "X/Y/Z axis values are invalid", "details": str(exc)}

    options = {
        "draw_legend": True,
        "include_sub_images": False,
        "include_sub_grids": False,
        "keep_minus_one": False,
        "vary_seeds_x": False,
        "vary_seeds_y": False,
        "vary_seeds_z": False,
        "row_count": 0,
        "margin_size": 0,
        "csv_mode": False,
    }
    if isinstance(job.get("options"), dict):
        options.update(job.get("options"))
    options["keep_minus_one"] = bool(options.get("keep_minus_one"))
    for key in ("draw_legend", "include_sub_images", "include_sub_grids", "vary_seeds_x", "vary_seeds_y", "vary_seeds_z", "csv_mode"):
        options[key] = bool(options.get(key))
    for key in ("row_count", "margin_size"):
        try:
            options[key] = int(float(options.get(key) or 0))
        except Exception:
            options[key] = 0

    rng = random.Random(_stable_seed_source(job))
    axes = [_resolve_seed_axis(axis, options["keep_minus_one"], rng) for axis in axes]
    x_axis, y_axis, z_axis = axes
    total = len(x_axis["values"]) * len(y_axis["values"]) * len(z_axis["values"])
    if total > MAX_PREVIEW_VARIANTS:
        return {"ok": False, "error": f"X/Y/Z plot expands to {total} variants; max preview is {MAX_PREVIEW_VARIANTS}"}

    width, height = _preview_size(source_node)
    grid_mp = round(total * width * height / 1000000)
    max_mp = int(job.get("max_grid_mp") or payload.get("max_grid_mp") or DEFAULT_GRID_MAX_MP)
    if grid_mp >= max_mp:
        return {"ok": False, "error": f"Resulting grid would be too large ({grid_mp} MPixels) (max configured size is {max_mp} MPixels)"}

    base_seed = int(source_node.get("params", {}).get("image_seed", -1) if isinstance(source_node.get("params"), dict) else -1)
    if base_seed == -1 and not options["keep_minus_one"]:
        base_seed = rng.randrange(4294967294)

    variants = []
    for iz, iy, ix in product(range(len(z_axis["values"])), range(len(y_axis["values"])), range(len(x_axis["values"]))):
        axis_values, axis_labels = _axis_value_map(x_axis, y_axis, z_axis, ix, iy, iz)
        seed = _variant_seed_from_axes(base_seed, (x_axis, y_axis, z_axis), (ix, iy, iz), options, len(x_axis["values"]), len(y_axis["values"]))
        patch = _build_variant_patch(x_axis, y_axis, z_axis, ix, iy, iz, seed, options)
        grid_index = ix + iy * len(x_axis["values"]) + iz * len(x_axis["values"]) * len(y_axis["values"])
        variants.append({
            "id": f"xyz_{grid_index + 1:04d}",
            "index": len(variants),
            "grid_index": grid_index,
            "x_index": ix,
            "y_index": iy,
            "z_index": iz,
            "axis_values": axis_values,
            "axis_labels": axis_labels,
            "resolved_seed": seed,
            "node_patch": patch,
            "status": "planned",
        })

    processing_order = _processing_order(x_axis, y_axis, z_axis)
    return {
        "ok": True,
        "script": XYZ_SCRIPT_NAME,
        "mode": mode,
        "source_node_id": source_node.get("id") or job.get("source_node_id") or "",
        "axes": [
            {key: value for key, value in axis.items() if key != "option"}
            for axis in axes
        ],
        "axis_options": [axis.get("option") for axis in axes],
        "options": options,
        "processing_order": processing_order,
        "grid": {
            "x_count": len(x_axis["values"]),
            "y_count": len(y_axis["values"]),
            "z_count": len(z_axis["values"]),
            "variant_count": total,
            "width": width,
            "height": height,
            "megapixels": grid_mp,
        },
        "variants": variants,
        "warnings": [],
    }


def run_job(payload, state_params=None):
    if not os.environ.get("SIMPAI_CANVAS_XYZ_ALLOW_GENERATE"):
        preview = preview_job(payload, state_params)
        preview["ok"] = False
        preview["dry_run"] = True
        preview["error"] = "X/Y/Z real generation requires SIMPAI_CANVAS_XYZ_ALLOW_GENERATE=1"
        return preview
    preview = preview_job(payload, state_params)
    if not preview.get("ok"):
        return preview
    preview["ok"] = False
    preview["error"] = "X/Y/Z queued generation is not enabled in this build; use preview to create a canvas matrix job."
    return preview


def poll_job(payload, state_params=None):
    job_id = payload.get("job_id") if isinstance(payload, dict) else ""
    return {"ok": False, "job_id": job_id or "", "error": "X/Y/Z job registry is not active; use individual canvas runs for live generation."}


def control_job(payload, state_params=None):
    job_id = payload.get("job_id") if isinstance(payload, dict) else ""
    action = payload.get("action") if isinstance(payload, dict) else ""
    return {"ok": False, "job_id": job_id or "", "action": action or "", "error": "X/Y/Z job registry is not active."}


def render_grid(payload, state_params=None):
    preview = preview_job(payload, state_params)
    if not preview.get("ok"):
        return preview
    return {
        "ok": True,
        "script": XYZ_SCRIPT_NAME,
        "grid": preview.get("grid"),
        "axes": preview.get("axes"),
        "options": preview.get("options"),
        "variants": preview.get("variants"),
    }
