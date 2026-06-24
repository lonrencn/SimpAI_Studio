import csv
import json
import os
import random
import re

import modules.canvas_danbooru_service as canvas_danbooru_service


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECOMMENDATIONS_DIR = os.path.join(ROOT_DIR, "presets", "scene_prompt_recommendations")
RANDOM_PROMPT_ASSOCIATIONS_FILE = os.path.join(RECOMMENDATIONS_DIR, "random_prompt_associations.csv")
RANDOM_PROMPT_NOISE_FILE = os.path.join(RECOMMENDATIONS_DIR, "random_prompt_noise.csv")
RANDOM_PROMPT_CHARACTERS_FILE = os.path.join(RECOMMENDATIONS_DIR, "random_prompt_characters.csv")

_random_prompt_association_cache = None
_random_prompt_noise_cache = None
_random_prompt_character_cache = None
RANDOM_CHARACTER_SAMPLE_POOL = 600

PROMPT_TARGETS = {
    "positive_prompt": "positive_prompt",
    "prompt": "positive_prompt",
    "main": "positive_prompt",
    "scene_additional_prompt": "scene_additional_prompt",
    "additional_prompt": "scene_additional_prompt",
    "scene_additional_prompt_2": "scene_additional_prompt_2",
    "additional_prompt_2": "scene_additional_prompt_2",
}

PROMPT_MODES = {"replace", "append"}

SHARED_RECOMMENDATION_FILES = {
    "text_to_video": "_text_to_video.csv",
    "image_to_video": "_image_to_video.csv",
    "image_edit": "_image_edit.csv",
}

IMAGE_EDIT_SHARED_PRESETS = {
    "Bernini-ImageEdit",
    "Flux2-KleinEdit",
    "QwenEdit+",
    "NunQwenEdit+_fp4",
    "NunQwenEdit+_int4",
    "QwenNSFW",
}

RANDOM_QUALITY_TAGS = [
    "masterpiece",
    "best_quality",
    "highres",
    "absurdres",
    "highly_detailed",
]

RANDOM_STYLE_GROUPS = [
    ["anime_style", "illustration", "clean_lineart"],
    ["cinematic_lighting", "depth_of_field", "detailed_background"],
    ["painterly", "soft_shading", "atmospheric_perspective"],
    ["vibrant_colors", "sharp_focus", "rich_details"],
]

RANDOM_SUBJECT_PROFILES = [
    {
        "id": "solo_girl",
        "tags": ["1girl", "solo"],
        "appearance": [
            ["long_hair", "hair_ornament", "blue_eyes"],
            ["short_hair", "bob_cut", "brown_eyes"],
            ["ponytail", "black_hair", "ribbon"],
            ["silver_hair", "green_eyes", "hair_between_eyes"],
        ],
        "outfit": [
            ["school_uniform", "pleated_skirt", "loafers"],
            ["dress", "frills", "detached_sleeves"],
            ["hoodie", "shorts", "sneakers"],
            ["coat", "scarf", "boots"],
        ],
        "action": [
            ["walking", "looking_at_viewer", "gentle_smile"],
            ["sitting", "holding_book", "soft_smile"],
            ["turning_around", "looking_back", "wind"],
            ["standing", "hand_on_chest", "serious"],
        ],
        "lookup_terms": ["school uniform", "long hair", "gentle smile", "walking"],
    },
    {
        "id": "solo_boy",
        "tags": ["1boy", "solo"],
        "appearance": [
            ["short_hair", "messy_hair", "brown_eyes"],
            ["black_hair", "blue_eyes", "hair_between_eyes"],
            ["white_hair", "red_eyes", "serious"],
            ["medium_hair", "green_eyes", "earrings"],
        ],
        "outfit": [
            ["jacket", "shirt", "pants"],
            ["hoodie", "cargo_pants", "sneakers"],
            ["suit", "necktie", "gloves"],
            ["coat", "scarf", "boots"],
        ],
        "action": [
            ["standing", "hands_in_pockets", "looking_at_viewer"],
            ["walking", "looking_away", "wind"],
            ["sitting", "holding_cup", "relaxed"],
            ["running", "dynamic_pose", "determined"],
        ],
        "lookup_terms": ["jacket", "hands in pockets", "dynamic pose", "walking"],
    },
    {
        "id": "duo",
        "tags": ["2girls"],
        "appearance": [
            ["long_hair", "short_hair", "contrasting_hair"],
            ["twin_tails", "bob_cut", "hair_ribbon"],
            ["black_hair", "blonde_hair", "smile"],
            ["white_hair", "brown_hair", "looking_at_each_other"],
        ],
        "outfit": [
            ["school_uniform", "matching_outfit", "pleated_skirt"],
            ["dress", "capelet", "boots"],
            ["jacket", "shorts", "sneakers"],
            ["kimono", "wide_sleeves", "hair_ornament"],
        ],
        "action": [
            ["walking_together", "holding_hands", "smile"],
            ["sitting", "sharing_food", "laughing"],
            ["standing", "looking_at_viewer", "peace_sign"],
            ["running", "dynamic_pose", "motion_blur"],
        ],
        "lookup_terms": ["2girls", "holding hands", "matching outfit", "laughing"],
    },
    {
        "id": "animal_focus",
        "tags": ["animal_focus"],
        "appearance": [
            ["cat", "fluffy", "green_eyes"],
            ["dog", "collar", "wagging_tail"],
            ["fox", "fluffy_tail", "orange_fur"],
            ["rabbit", "long_ears", "soft_fur"],
        ],
        "outfit": [
            ["ribbon", "tiny_hat"],
            ["collar", "bell"],
            ["scarf", "small_bag"],
            ["flower_crown"],
        ],
        "action": [
            ["sitting", "looking_at_viewer"],
            ["sleeping", "curled_up"],
            ["jumping", "motion_blur"],
            ["playing", "pawing_at_object"],
        ],
        "lookup_terms": ["cat", "animal focus", "ribbon", "sitting"],
    },
    {
        "id": "scenery",
        "tags": ["scenery", "no_humans"],
        "appearance": [
            ["wide_shot", "clouds", "distant_mountains"],
            ["river", "stone_path", "trees"],
            ["cityscape", "street_lights", "reflection"],
            ["room", "window", "sunbeam"],
        ],
        "outfit": [[]],
        "action": [
            ["still_water", "floating_leaves"],
            ["wind", "falling_leaves"],
            ["rain", "wet_ground"],
            ["sunlight", "dust_particles"],
        ],
        "lookup_terms": ["scenery", "cityscape", "sunlight", "rain"],
    },
]

RANDOM_SCENE_PROFILES = [
    {
        "id": "rainy_neon_street",
        "tags": ["city", "street", "rain", "wet_ground", "reflection", "neon_lights"],
        "details": [
            ["umbrella", "puddle", "shopfront"],
            ["street_lamp", "traffic_light", "mist"],
            ["raindrops", "window_reflection", "steam"],
            ["crosswalk", "backlighting", "crowd_blur"],
        ],
        "lighting": [
            ["night", "rim_lighting", "glowing_sign"],
            ["blue_light", "pink_light", "backlighting"],
            ["soft_focus", "bokeh", "reflected_light"],
        ],
        "lookup_terms": ["rain", "neon lights", "city street", "reflection"],
    },
    {
        "id": "sunlit_forest_path",
        "tags": ["forest", "path", "trees", "flowers", "sunlight"],
        "details": [
            ["dappled_sunlight", "moss", "wildflowers"],
            ["butterfly", "fallen_leaves", "tree_roots"],
            ["stream", "rocks", "fern"],
            ["wooden_bridge", "mist", "bird"],
        ],
        "lighting": [
            ["morning", "god_rays", "soft_shadows"],
            ["golden_hour", "warm_light", "lens_flare"],
            ["overcast", "diffused_light", "calm"],
        ],
        "lookup_terms": ["forest", "flowers", "sunlight", "mist"],
    },
    {
        "id": "quiet_library",
        "tags": ["library", "bookshelf", "window", "wooden_floor"],
        "details": [
            ["book_stack", "desk", "teacup"],
            ["ladder", "old_books", "curtains"],
            ["paper", "ink_bottle", "dust_particles"],
            ["reading_nook", "lamp", "soft_shadow"],
        ],
        "lighting": [
            ["sunbeam", "warm_light", "soft_focus"],
            ["lamplight", "cozy", "shallow_depth_of_field"],
            ["late_afternoon", "golden_light", "quiet"],
        ],
        "lookup_terms": ["library", "bookshelf", "sunbeam", "book"],
    },
    {
        "id": "seaside_evening",
        "tags": ["ocean", "beach", "waves", "clouds", "horizon"],
        "details": [
            ["sunset", "seafoam", "wet_sand"],
            ["lighthouse", "distant_ship", "seagull"],
            ["pier", "fishing_net", "rope"],
            ["wind", "flowing_clothes", "sparkling_water"],
        ],
        "lighting": [
            ["sunset", "orange_sky", "backlighting"],
            ["blue_hour", "soft_light", "silhouette"],
            ["moonlight", "silver_light", "calm"],
        ],
        "lookup_terms": ["ocean", "sunset", "wind", "waves"],
    },
    {
        "id": "fantasy_ruins",
        "tags": ["ruins", "overgrown", "ancient", "stone", "glowing"],
        "details": [
            ["vines", "broken_pillar", "magic_circle"],
            ["crystal", "floating_particles", "moss"],
            ["statue", "cracked_wall", "flowers"],
            ["archway", "waterfall", "mist"],
        ],
        "lighting": [
            ["mysterious_light", "volumetric_lighting", "blue_glow"],
            ["moonlight", "fog", "soft_shadow"],
            ["sunlight", "god_rays", "atmospheric_perspective"],
        ],
        "lookup_terms": ["ruins", "glowing", "magic circle", "mist"],
    },
    {
        "id": "cozy_room",
        "tags": ["bedroom", "window", "curtains", "plants", "wooden_floor"],
        "details": [
            ["desk", "book", "coffee"],
            ["bed", "blanket", "pillow"],
            ["cat", "chair", "sunbeam"],
            ["poster", "string_lights", "small_shelf"],
        ],
        "lighting": [
            ["morning", "soft_light", "warm_color_palette"],
            ["evening", "lamplight", "cozy"],
            ["rainy_day", "window_light", "muted_colors"],
        ],
        "lookup_terms": ["bedroom", "coffee", "plants", "window"],
    },
]

RANDOM_COMPOSITION_GROUPS = {
    "character": [
        ["cowboy_shot", "eye_level", "depth_of_field"],
        ["upper_body", "from_side", "shallow_depth_of_field"],
        ["full_body", "dynamic_angle", "motion_blur"],
        ["portrait", "center_composition", "detailed_face"],
        ["wide_shot", "rule_of_thirds", "detailed_background"],
    ],
    "scenery": [
        ["wide_shot", "establishing_shot", "atmospheric_perspective"],
        ["panorama", "vanishing_point", "depth_of_field"],
        ["low_angle", "dramatic_perspective", "detailed_background"],
        ["overhead_view", "leading_lines", "sharp_focus"],
    ],
}

RANDOM_ATMOSPHERE_GROUPS = [
    ["calm", "peaceful", "gentle_wind"],
    ["dramatic", "high_contrast", "cinematic_shadow"],
    ["dreamy", "floating_particles", "soft_focus"],
    ["melancholy", "muted_colors", "lonely"],
    ["energetic", "motion_blur", "dynamic_pose"],
]

RANDOM_BAD_LOOKUP_TAGS = {
    "mouth",
    "pose",
    "soft_serve",
    "lighting_cigarette",
    "kiss",
    "softboiled_egg",
    "open_clothes",
    "open_fly",
    "pov",
    "windowboxed",
    "street_fighter",
}

RANDOM_FALLBACK_CHARACTERS = [
    {"character_tag": "hatsune_miku", "copyright_tag": "vocaloid", "subject_hint": "1girl", "score": "100"},
    {"character_tag": "artoria_pendragon_(fate)", "copyright_tag": "fate_(series)", "subject_hint": "1girl", "score": "96"},
    {"character_tag": "ganyu_(genshin_impact)", "copyright_tag": "genshin_impact", "subject_hint": "1girl", "score": "94"},
    {"character_tag": "raiden_shogun", "copyright_tag": "genshin_impact", "subject_hint": "1girl", "score": "92"},
    {"character_tag": "frieren_(sousou_no_frieren)", "copyright_tag": "sousou_no_frieren", "subject_hint": "1girl", "score": "90"},
    {"character_tag": "makima", "copyright_tag": "chainsaw_man", "subject_hint": "1girl", "score": "88"},
    {"character_tag": "hoshino_ai", "copyright_tag": "oshi_no_ko", "subject_hint": "1girl", "score": "86"},
    {"character_tag": "saber_alter", "copyright_tag": "fate/stay_night", "subject_hint": "1girl", "score": "84"},
    {"character_tag": "zhongli_(genshin_impact)", "copyright_tag": "genshin_impact", "subject_hint": "1boy", "score": "82"},
    {"character_tag": "venti_(genshin_impact)", "copyright_tag": "genshin_impact", "subject_hint": "1boy", "score": "80"},
    {"character_tag": "mario", "copyright_tag": "mario_(series)", "subject_hint": "1boy", "score": "78"},
    {"character_tag": "uzumaki_naruto", "copyright_tag": "naruto_(series)", "subject_hint": "1boy", "score": "78"},
    {"character_tag": "monkey_d._luffy", "copyright_tag": "one_piece", "subject_hint": "1boy", "score": "76"},
    {"character_tag": "gojo_satoru", "copyright_tag": "jujutsu_kaisen", "subject_hint": "1boy", "score": "74"},
    {"character_tag": "levi_(shingeki_no_kyojin)", "copyright_tag": "shingeki_no_kyojin", "subject_hint": "1boy", "score": "72"},
    {"character_tag": "edogawa_conan", "copyright_tag": "detective_conan", "subject_hint": "1boy", "score": "70"},
    {"character_tag": "kirito", "copyright_tag": "sword_art_online", "subject_hint": "1boy", "score": "68"},
    {"character_tag": "link", "copyright_tag": "the_legend_of_zelda", "subject_hint": "1boy", "score": "66"},
    {"character_tag": "sakata_gintoki", "copyright_tag": "gintama", "subject_hint": "1boy", "score": "64"},
    {"character_tag": "kaito_(vocaloid)", "copyright_tag": "vocaloid", "subject_hint": "1boy", "score": "62"},
]


def _clean_text(value):
    return str(value or "").strip()


def _clean_lang(value):
    lang = _clean_text(value).lower()
    return "en" if lang.startswith("en") else "cn"


def _safe_prompt_file_name(preset_name):
    name = _clean_text(preset_name)
    if not name:
        return ""
    name = os.path.basename(name)
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().strip(".")
    return name


def _preset_json_path(preset_name):
    safe = _safe_prompt_file_name(preset_name)
    if not safe:
        return ""
    return os.path.join(ROOT_DIR, "presets", f"{safe}.json")


def _load_preset_scene_frontend(preset_name):
    path = _preset_json_path(preset_name)
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    default_engine = data.get("default_engine") if isinstance(data, dict) else {}
    scene_frontend = default_engine.get("scene_frontend") if isinstance(default_engine, dict) else {}
    return scene_frontend if isinstance(scene_frontend, dict) else {}


def _scene_value_candidates(value):
    if isinstance(value, dict):
        return [_clean_text(item) for item in value.values() if _clean_text(item)]
    if isinstance(value, (list, tuple, set)):
        return [_clean_text(item) for item in value if _clean_text(item)]
    clean = _clean_text(value)
    return [clean] if clean else []


def _scene_director_capability(scene_frontend):
    capability = scene_frontend.get("director_capability") if isinstance(scene_frontend, dict) else {}
    return capability if isinstance(capability, dict) else {}


def _has_i2v_marker(value):
    clean = _clean_text(value).lower()
    if not clean or "ai2v" in clean or "ia2v" in clean:
        return False
    normalized = re.sub(r"[^a-z0-9]+", "_", clean).strip("_")
    parts = [part for part in normalized.split("_") if part]
    return "(i2v)" in clean or "i2v" in parts or normalized.endswith("i2v")


def _has_image_to_video_phrase(value):
    clean = _clean_text(value).lower().replace("_", " ").replace("-", " ")
    return "image to video" in clean


def _scene_prompt_supports_shared_image_to_video(preset_name, scene_frontend, task_methods, capability):
    image_policy = _clean_text(capability.get("image_policy")).lower()
    video_policy = _clean_text(capability.get("video_policy")).lower()
    audio_policy = _clean_text(capability.get("audio_policy")).lower()
    if image_policy != "required" or video_policy not in {"", "forbidden"} or audio_policy not in {"", "forbidden"}:
        return False

    image_modes = [item.lower() for item in _scene_value_candidates(capability.get("image_modes"))]
    has_image_input = _safe_int(capability.get("max_images"), 0) > 0 or any(
        mode in {"first_frame", "first_last", "reference_set"} for mode in image_modes
    )
    if not has_image_input:
        return False

    marker_values = [preset_name, scene_frontend.get("theme_title")]
    marker_values.extend(task_methods)
    marker_values.extend(_scene_value_candidates(scene_frontend.get("theme")))
    return any(_has_i2v_marker(item) or _has_image_to_video_phrase(item) for item in marker_values)


def _scene_prompt_shared_keys(preset_name):
    keys = []
    if _safe_prompt_file_name(preset_name) in IMAGE_EDIT_SHARED_PRESETS:
        keys.append("image_edit")

    scene_frontend = _load_preset_scene_frontend(preset_name)
    if not scene_frontend:
        return keys
    task_methods = [item.lower() for item in _scene_value_candidates(scene_frontend.get("task_method"))]
    capability = _scene_director_capability(scene_frontend)
    image_policy = _clean_text(capability.get("image_policy")).lower()
    video_policy = _clean_text(capability.get("video_policy")).lower()
    audio_policy = _clean_text(capability.get("audio_policy")).lower()
    if _scene_prompt_supports_shared_image_to_video(preset_name, scene_frontend, task_methods, capability):
        keys.append("image_to_video")
    no_media_input = (
        image_policy in {"", "forbidden"}
        and video_policy in {"", "forbidden"}
        and audio_policy in {"", "forbidden"}
    )
    if no_media_input and any("t2v" in method for method in task_methods):
        keys.append("text_to_video")
    return keys


def _candidate_prompt_files(preset_name):
    safe = _safe_prompt_file_name(preset_name)
    result = []
    if safe:
        result.append(os.path.join(RECOMMENDATIONS_DIR, f"{safe}.csv"))
    for key in _scene_prompt_shared_keys(preset_name):
        shared_name = SHARED_RECOMMENDATION_FILES.get(key)
        if shared_name:
            result.append(os.path.join(RECOMMENDATIONS_DIR, shared_name))
    result.append(os.path.join(RECOMMENDATIONS_DIR, "_default.csv"))
    seen = set()
    unique = []
    for path in result:
        if path in seen:
            continue
        seen.add(path)
        if os.path.isfile(path):
            unique.append(path)
    return unique


def _relative_prompt_file(path):
    return os.path.relpath(path, ROOT_DIR).replace("\\", "/")


def _read_prompt_rows(path):
    rows = []
    if not os.path.isfile(path):
        return rows
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(line for line in f if not line.lstrip().startswith("#"))
        for index, row in enumerate(reader):
            if not isinstance(row, dict):
                continue
            prompt = _clean_text(row.get("prompt"))
            if not prompt:
                continue
            target = PROMPT_TARGETS.get(_clean_text(row.get("target")).lower(), "positive_prompt")
            mode = _clean_text(row.get("mode")).lower()
            if mode not in PROMPT_MODES:
                mode = "replace"
            item = {
                "id": _clean_text(row.get("id")) or f"{os.path.basename(path)}:{index + 1}",
                "scene_theme": _clean_text(row.get("scene_theme")) or "*",
                "target": target,
                "mode": mode,
                "title_en": _clean_text(row.get("title_en")),
                "title_cn": _clean_text(row.get("title_cn")),
                "prompt": prompt,
                "seed_terms": _split_terms(row.get("seed_terms")),
                "weight": _safe_int(row.get("weight"), 100),
                "source_file": _relative_prompt_file(path),
            }
            rows.append(item)
    return rows


def _safe_int(value, default=0):
    try:
        return int(float(value))
    except Exception:
        return default


def _split_terms(value):
    terms = []
    for item in re.split(r"[|,;]", str(value or "")):
        clean = item.strip()
        if clean and clean not in terms:
            terms.append(clean)
    return terms


def _scene_theme_matches(row_theme, scene_theme):
    wanted = _clean_text(scene_theme).lower()
    current = _clean_text(row_theme).lower()
    if not current or current == "*":
        return True
    if not wanted:
        return True
    return current == wanted


def _recommendation_title(row, lang):
    if _clean_lang(lang) == "en":
        return row.get("title_en") or row.get("title_cn") or row.get("id")
    return row.get("title_cn") or row.get("title_en") or row.get("id")


def _dedupe_prompt_rows(rows):
    result = []
    seen_ids = set()
    seen_prompts = set()
    for row in rows:
        item_id = _clean_text(row.get("id")).lower()
        prompt_key = re.sub(r"\s+", "", _clean_text(row.get("prompt")).lower())
        if item_id and item_id in seen_ids:
            continue
        if prompt_key and prompt_key in seen_prompts:
            continue
        if item_id:
            seen_ids.add(item_id)
        if prompt_key:
            seen_prompts.add(prompt_key)
        result.append(row)
    return result


def list_prompt_recommendations(preset_name, scene_theme="", lang="cn", limit=12):
    rows = []
    for path in _candidate_prompt_files(preset_name):
        rows.extend(_read_prompt_rows(path))
    rows = [row for row in rows if _scene_theme_matches(row.get("scene_theme"), scene_theme)]
    rows = _dedupe_prompt_rows(rows)
    rows.sort(key=lambda row: (-_safe_int(row.get("weight"), 100), str(row.get("id") or "")))
    max_limit = max(1, min(_safe_int(limit, 12), 50))
    preset = _clean_text(preset_name)
    return [
        {
            **row,
            "title": _recommendation_title(row, lang),
            "preset": preset,
        }
        for row in rows[:max_limit]
    ]


def recommendation_payload(preset_name, scene_theme="", lang="cn", limit=12):
    candidate_files = [_relative_prompt_file(path) for path in _candidate_prompt_files(preset_name)]
    return {
        "ok": True,
        "preset": _clean_text(preset_name),
        "scene_theme": _clean_text(scene_theme),
        "items": list_prompt_recommendations(preset_name, scene_theme=scene_theme, lang=lang, limit=limit),
        "source_dir": os.path.relpath(RECOMMENDATIONS_DIR, ROOT_DIR).replace("\\", "/"),
        "source_files": candidate_files,
    }


def _safe_danbooru_tag(tag):
    return canvas_danbooru_service._canvas_prompt_safe_danbooru_tag(tag)


def _prompt_lookup_norm(value):
    return re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _read_csv_dict_rows(path):
    if not path or not os.path.isfile(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _random_prompt_noise_tags():
    global _random_prompt_noise_cache
    if _random_prompt_noise_cache is not None:
        return _random_prompt_noise_cache
    noise = set()
    for row in _read_csv_dict_rows(RANDOM_PROMPT_NOISE_FILE):
        tag = _prompt_lookup_norm(row.get("tag"))
        reason = _clean_text(row.get("reason")).lower()
        if tag and reason in {"adult", "artist", "copyright", "bad_pattern", "low_value", "unwanted"}:
            noise.add(tag)
    _random_prompt_noise_cache = noise
    return noise


def _random_prompt_association_rows():
    global _random_prompt_association_cache
    if _random_prompt_association_cache is not None:
        return _random_prompt_association_cache
    by_trigger = {}
    for row in _read_csv_dict_rows(RANDOM_PROMPT_ASSOCIATIONS_FILE):
        trigger = _prompt_lookup_norm(row.get("trigger"))
        related = _prompt_lookup_norm(row.get("related"))
        slot = _clean_text(row.get("slot")).lower()
        if not trigger or not related or not slot:
            continue
        item = {
            "trigger": trigger,
            "related": related,
            "slot": slot,
            "support": _safe_int(row.get("support"), 0),
            "lift": _safe_float(row.get("lift"), 0.0),
            "score": _safe_float(row.get("score"), 0.0),
        }
        by_trigger.setdefault(trigger, []).append(item)
    for rows in by_trigger.values():
        rows.sort(key=lambda item: (-item["score"], -item["support"], item["related"]))
    _random_prompt_association_cache = by_trigger
    return by_trigger


def _random_prompt_character_rows():
    global _random_prompt_character_cache
    if _random_prompt_character_cache is not None:
        return _random_prompt_character_cache
    csv_rows = _read_csv_dict_rows(RANDOM_PROMPT_CHARACTERS_FILE)
    source_rows = list(csv_rows) + list(RANDOM_FALLBACK_CHARACTERS) if csv_rows else RANDOM_FALLBACK_CHARACTERS
    rows = []
    seen = set()
    for row in source_rows:
        character = _safe_danbooru_tag(row.get("character_tag"))
        copyright_tag = _safe_danbooru_tag(row.get("copyright_tag"))
        if not character:
            continue
        key = (character.lower(), copyright_tag.lower())
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "character_tag": character,
                "copyright_tag": copyright_tag,
                "subject_hint": _prompt_lookup_norm(row.get("subject_hint")),
                "score": _safe_float(row.get("score"), 0.0),
            }
        )
    rows.sort(key=lambda item: (-item["score"], item["character_tag"], item["copyright_tag"]))
    _random_prompt_character_cache = rows
    return rows


def _prompt_lookup_tag_is_visual(tag):
    raw = str(tag or "").strip().lower()
    if raw.startswith("@") or "\\" in raw:
        return False
    if re.search(r"[,/&!:\\]|\(|\)|\[|\]", raw):
        return False
    clean = _prompt_lookup_norm(tag)
    if not clean or clean in RANDOM_BAD_LOOKUP_TAGS or clean in _random_prompt_noise_tags() or "kiss" in clean:
        return False
    if len(clean) > 48:
        return False
    if clean.count("_") > 5:
        return False
    return True


def _prompt_lookup_relevance(tag, query, fallback_tags=None):
    tag_norm = _prompt_lookup_norm(tag)
    query_norm = _prompt_lookup_norm(query)
    fallback_norms = {_prompt_lookup_norm(item) for item in fallback_tags or []}
    if not tag_norm or not query_norm:
        return 0
    if tag_norm in fallback_norms:
        return 120
    if tag_norm == query_norm:
        return 110
    if "_" not in query_norm:
        return 0
    if tag_norm.startswith(f"{query_norm}_"):
        suffix_parts = [part for part in tag_norm[len(query_norm) + 1:].split("_") if part]
        if len(suffix_parts) <= 1:
            return 92
        return 0
    if query_norm.startswith(f"{tag_norm}_") and len(tag_norm) >= max(6, int(len(query_norm) * 0.7)):
        return 76
    query_parts = [part for part in query_norm.split("_") if len(part) >= 3]
    tag_parts = tag_norm.split("_")
    if len(query_parts) >= 2 and len(tag_parts) <= len(query_parts) + 1 and all(part in tag_parts for part in query_parts):
        return 72
    return 0


def _lookup_prompt_tags(query, fallback_tags=None, source_mode="all", rng=None, max_count=1):
    fallbacks = [_safe_danbooru_tag(item) for item in fallback_tags or [] if _safe_danbooru_tag(item)]
    try:
        matches = canvas_danbooru_service._canvas_lookup_danbooru_tags(
            query,
            limit=12,
            source_mode=source_mode,
        )
    except Exception:
        matches = []
    candidates = []
    for item in matches or []:
        tag = _safe_danbooru_tag(item.get("tag") if isinstance(item, dict) else item)
        category = _clean_text(item.get("category") if isinstance(item, dict) else "").lower()
        if category in {"artist", "character", "copyright"}:
            continue
        if not tag or not _prompt_lookup_tag_is_visual(tag):
            continue
        relevance = _prompt_lookup_relevance(tag, query, fallback_tags=fallbacks)
        if relevance <= 0:
            continue
        count = _safe_int(item.get("count"), 0) if isinstance(item, dict) else 0
        candidates.append((relevance, count, tag))
    candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))
    if candidates and rng is not None:
        top = candidates[: min(len(candidates), 5)]
        rng.shuffle(top)
        candidates = top + candidates[min(len(candidates), 5):]
    result = []
    for _relevance, _count, tag in candidates:
        if tag not in result:
            result.append(tag)
        if len(result) >= max_count:
            break
    for tag in fallbacks:
        if tag and tag not in result:
            result.append(tag)
        if len(result) >= max_count:
            break
    return result[:max(1, max_count)]


def _random_prompt_association_tags(current_tags, rng, max_count=5):
    by_trigger = _random_prompt_association_rows()
    if not by_trigger:
        return []
    current_norms = {_prompt_lookup_norm(tag) for tag in current_tags if _prompt_lookup_norm(tag)}
    picked = []
    picked_slots = set()
    candidates = []
    for trigger in current_norms:
        for row in by_trigger.get(trigger, [])[:18]:
            related = row.get("related")
            slot = row.get("slot")
            if not _random_prompt_related_tag_allowed(related, current_norms):
                continue
            candidates.append(row)
    rng.shuffle(candidates)
    candidates.sort(key=lambda item: (-item.get("score", 0.0), -item.get("support", 0), item.get("related", "")))
    for row in candidates:
        related = row.get("related")
        slot = row.get("slot")
        if not related or related in current_norms or related in picked:
            continue
        if slot in picked_slots and len(picked_slots) < 4:
            continue
        picked.append(_safe_danbooru_tag(related))
        picked_slots.add(slot)
        if len(picked) >= max_count:
            break
    return picked


def _random_prompt_related_tag_allowed(related, current_norms):
    related_norm = _prompt_lookup_norm(related)
    if not related_norm or related_norm in current_norms or related_norm in _random_prompt_noise_tags():
        return False
    if related_norm in RANDOM_BAD_LOOKUP_TAGS or "kiss" in related_norm:
        return False
    if related_norm == "male_focus" and "1boy" not in current_norms:
        return False
    if related_norm == "female_focus" and not current_norms.intersection({"1girl", "2girls"}):
        return False
    if "no_humans" in current_norms:
        if related_norm in {"male_focus", "female_focus", "pov", "solo_focus"}:
            return False
        if related_norm.startswith(("holding_", "looking_", "hand_", "arm_", "leg_")):
            return False
    return True


def _subject_accepts_character(subject_id):
    return _prompt_lookup_norm(subject_id) in {"solo_girl", "solo_boy", "duo"}


def _character_subject_matches(row, subject_id):
    hint = _prompt_lookup_norm(row.get("subject_hint"))
    subject = _prompt_lookup_norm(subject_id)
    if not hint:
        return True
    if subject == "solo_boy":
        return hint == "1boy"
    if subject in {"solo_girl", "duo"}:
        return hint in {"1girl", "2girls", "multiple_girls"}
    return False


def _pick_random_character_tags(rng, subject_id):
    if not _subject_accepts_character(subject_id):
        return []
    rows = [row for row in _random_prompt_character_rows() if _character_subject_matches(row, subject_id)]
    if not rows:
        rows = _random_prompt_character_rows()
    if not rows:
        return []
    top = rows[: min(len(rows), RANDOM_CHARACTER_SAMPLE_POOL)]
    picked = rng.choice(top)
    tags = [picked.get("character_tag")]
    if picked.get("copyright_tag"):
        tags.append(picked.get("copyright_tag"))
    return [tag for tag in tags if tag]


def _dedupe_tags(tags):
    output = []
    seen = set()
    for tag in tags:
        clean = _safe_danbooru_tag(tag)
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(clean)
    return output


def _pick_group(rng, groups):
    if not groups:
        return []
    picked = rng.choice(groups)
    return list(picked or [])


def _extend_tag_group(tags, slots, slot_name, values):
    clean_values = [item for item in values or [] if _clean_text(item)]
    if not clean_values:
        return
    tags.extend(clean_values)
    slots.append({"slot": slot_name, "values": clean_values})


def _random_prompt_lookup_terms(rng, subject, scene):
    terms = []
    for value in list(subject.get("lookup_terms") or []) + list(scene.get("lookup_terms") or []):
        clean = _clean_text(value)
        if clean and clean not in terms:
            terms.append(clean)
    rng.shuffle(terms)
    return terms[:3]


def compose_random_prompt(preset_name="", scene_theme="", lang="cn", seed=None, source_mode="all"):
    rng = random.Random(seed) if seed is not None else random.Random()
    subject = rng.choice(RANDOM_SUBJECT_PROFILES)
    scene = rng.choice(RANDOM_SCENE_PROFILES)
    scenery_only = "no_humans" in subject.get("tags", [])
    composition_key = "scenery" if scenery_only else "character"
    picked_slots = []
    lookup_terms = []
    prompt_tags = []

    _extend_tag_group(prompt_tags, picked_slots, "subject", subject.get("tags"))
    character_tags = _pick_random_character_tags(rng, subject.get("id"))
    _extend_tag_group(prompt_tags, picked_slots, "character", character_tags)
    _extend_tag_group(prompt_tags, picked_slots, "appearance", _pick_group(rng, subject.get("appearance")))
    _extend_tag_group(prompt_tags, picked_slots, "outfit", _pick_group(rng, subject.get("outfit")))
    _extend_tag_group(prompt_tags, picked_slots, "action", _pick_group(rng, subject.get("action")))
    _extend_tag_group(prompt_tags, picked_slots, "setting", scene.get("tags"))
    _extend_tag_group(prompt_tags, picked_slots, "scene_detail", _pick_group(rng, scene.get("details")))
    _extend_tag_group(prompt_tags, picked_slots, "lighting", _pick_group(rng, scene.get("lighting")))
    _extend_tag_group(prompt_tags, picked_slots, "composition", _pick_group(rng, RANDOM_COMPOSITION_GROUPS.get(composition_key)))
    _extend_tag_group(prompt_tags, picked_slots, "atmosphere", _pick_group(rng, RANDOM_ATMOSPHERE_GROUPS))
    _extend_tag_group(prompt_tags, picked_slots, "style", _pick_group(rng, RANDOM_STYLE_GROUPS))

    for term in _random_prompt_lookup_terms(rng, subject, scene):
        tags = _lookup_prompt_tags(term, source_mode=source_mode, rng=rng, max_count=1)
        if tags:
            lookup_terms.append(term)
            _extend_tag_group(prompt_tags, picked_slots, "danbooru_related", tags)

    association_tags = _random_prompt_association_tags(prompt_tags, rng, max_count=5)
    _extend_tag_group(prompt_tags, picked_slots, "association_stats", association_tags)

    prompt_tags.extend(RANDOM_QUALITY_TAGS)

    prompt = ", ".join(_dedupe_tags(prompt_tags))
    return {
        "ok": True,
        "preset": _clean_text(preset_name),
        "scene_theme": _clean_text(scene_theme),
        "item": {
            "id": "local_random_danbooru",
            "target": "positive_prompt",
            "mode": "replace",
            "title": "Random Prompt" if _clean_lang(lang) == "en" else "随机提示词",
            "prompt": prompt,
            "seed_terms": lookup_terms,
            "slots": picked_slots,
            "recipe": {
                "subject": subject.get("id"),
                "scene": scene.get("id"),
                "character": character_tags[:1],
            },
            "source": "local_prompt_recipe_danbooru_lookup",
        },
    }
