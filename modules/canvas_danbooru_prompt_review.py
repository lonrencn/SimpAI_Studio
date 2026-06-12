import json
import logging
import hashlib
import os
import re

import modules.canvas_danbooru_preflight as canvas_danbooru_preflight
import modules.canvas_danbooru_service as canvas_danbooru_service
import modules.canvas_vlm_prompt_pipeline as canvas_vlm_prompt_pipeline

logger = logging.getLogger(__name__)

REVIEW_SKILL_FILE = "danbooru_prompt_review.md"
REVIEW_SCHEMA_VERSION = 1
REVIEW_STATES = {"pass", "fixed", "warn", "reject", "disabled", "skipped", "error"}
REVIEW_STATE_ALIASES = {
    "ok": "pass",
    "ready": "pass",
    "valid": "pass",
    "resolved": "fixed",
    "repaired": "fixed",
    "repair": "fixed",
}
IMAGE_ACTIONS = {"generate_image", "text_to_image", "edit_image", "outpaint_image", "erase_image", "replace_image", "upscale_image"}
COUNT_TAGS = {
    "1girl", "1boy", "2girls", "2boys", "3girls", "3boys", "4girls", "4boys", "5girls", "5boys", "6girls", "6boys",
    "multiple_girls", "multiple_boys", "multiple_others",
}
BATHING_INTENT_PATTERNS = (r"\bbath(?:room|ing)?\b", "\u6d74\u5ba4", "\u6d17\u6fa1", "\u6c90\u6d74", "\u6ce1\u6fa1")
BATHING_SCENE_TAGS = {"bathroom", "bathing", "showering", "bathtub", "shower_head", "onsen", "wet"}
BATHING_CONFLICT_TAGS = {
    "outdoors", "shrine", "torii", "paper_lantern", "lantern", "night", "moonlight",
    "butterfly", "fire", "pyrokinesis", "holding_flower", "reaching_towards_viewer",
    "dynamic_pose", "smile", "window", "curtains", "table", "desk", "teacup", "tea",
    "cup", "holding_cup", "drinking", "book", "holding_book", "reading", "office",
    "paper", "papers", "holding_pen", "writing", "bedroom", "bed", "on_bed", "pillow",
    "blanket", "sitting", "standing", "walking", "sunlight", "backlighting", "cafe",
}
BEACH_INTENT_PATTERNS = (r"\bbeach\b", r"\bseaside\b", r"\bocean\b", "\u6d77\u8fb9", "\u6d77\u6ee9", "\u6c99\u6ee9")
SWIMSUIT_INTENT_PATTERNS = (r"\bswimsuits?\b", r"\bbikini\b", "\u6cf3\u88c5", "\u6cf3\u8863", "\u6bd4\u57fa\u5c3c")
PLAY_INTENT_PATTERNS = (r"\bplay(?:ing)?\b", r"\bplaying around\b", "一起玩", "陪.{0,8}玩", "玩耍", "嬉戏", "玩水")
GROUP_OTHER_PEOPLE_PATTERNS = (
    r"小朋友们|孩子们|儿童们|幼儿们|同学们|朋友们|大家",
    r"一群(?:小朋友|孩子|儿童|幼儿|同学|朋友|人)",
    r"(?:和|跟|与|陪).{0,14}(?:小朋友|孩子|儿童|幼儿|同学|朋友).{0,8}(?:一起)?",
    r"\bwith\s+(?:children|kids|classmates|friends|students|a\s+group\s+of\s+people)\b",
)
KINDERGARTEN_INTENT_PATTERNS = (r"幼儿园|托儿所|学前班", r"\bkindergarten\b|\bpreschool\b|\bnursery\s+school\b")
BEACH_CONFLICT_TAGS = {
    "indoors", "classroom", "office", "library", "cafe", "teahouse",
    "bedroom", "bed", "on_bed", "pillow", "blanket", "window", "curtains",
    "table", "desk", "paper", "papers", "holding_pen", "writing", "book",
    "holding_book", "reading", "teacup", "tea", "cup", "holding_cup",
    "drinking", "shrine", "torii", "paper_lantern", "lantern",
}
STREET_INTENT_PATTERNS = (r"\bstreet\b", r"\bcity\b", r"\bwalking\b", r"\bholding\s+hands\b", "\u8857", "\u8857\u4e0a", "\u8857\u9053", "\u7275\u624b", "\u624b\u7275\u624b", "\u8d70\u8def", "\u884c\u8d70")
STREET_CONFLICT_TAGS = {
    "indoors", "classroom", "office", "library", "teahouse", "bedroom",
    "bed", "on_bed", "pillow", "blanket", "window", "curtains", "desk",
    "table", "paper", "papers", "holding_pen", "writing", "book", "holding_book",
    "reading", "teacup", "tea", "cup", "holding_cup", "drinking",
}
BED_INTENT_PATTERNS = (r"\bbed(?:room)?\b", r"\bon bed\b", "\u5e8a", "\u5367\u5ba4")
BED_SCENE_TAGS = {"bedroom", "bed", "on_bed"}
BED_CONFLICT_TAGS = {
    "outdoors", "sky", "cloud", "clouds", "blue_sky", "cloudy_sky",
    "city", "street", "road", "alley", "beach", "ocean", "sea",
    "forest", "park", "garden", "grass", "mountain", "hills",
    "shrine", "torii", "paper_lantern", "lantern",
}
DEFEATED_INTENT_PATTERNS = (
    r"\bknock(?:ed)?\s+down\b", r"\bdefeat(?:ed)?\b", r"\bfall(?:en)?\s+(?:down|over)\b",
    "\u6218\u8d25", "\u6230\u6557", "\u8d25\u5317", "\u6557\u5317", "\u843d\u8d25", "\u843d\u6557",
    "\u88ab.{0,8}(?:\u51fb\u5012|\u64ca\u5012|\u6253\u5012|\u6253\u8d25|\u6253\u6557)",
    "\u5012\u5730", "\u8db4\u5730", "\u8eba\u5730",
)
DEFEATED_DOWN_INTENT_PATTERNS = (
    r"\bknock(?:ed)?\s+down\b", r"\bfall(?:en)?\s+(?:down|over)\b", r"\bcollapsed?\b",
    "\u88ab.{0,8}(?:\u51fb\u5012|\u64ca\u5012|\u6253\u5012|\u6253\u8d25|\u6253\u6557)",
    "\u5012\u5730", "\u8db4\u5730", "\u8eba\u5730",
)
KNEELING_INTENT_PATTERNS = (r"\bkneel(?:ing)?\b", r"\bon\s+one\s+knee\b", "\u8dea", "\u8dea\u5730", "\u5355\u819d", "\u55ae\u819d")
PASSIVE_ATTACK_INTENT_PATTERNS = (
    r"\u88ab[^，。,.!?]{0,8}(?:\u6253|\u63cd|\u653b\u51fb|\u653b\u64ca|\u6bb4\u6253|\u6253\u4f24|\u6253\u50b7|\u638c\u63b4|\u62f3\u51fb)",
    r"\b(?:being\s+)?(?:hit|beaten|attacked|punched|slapped)\b",
)
DEFEATED_SCENE_TAGS = {"on_ground", "injury", "rolling_eyes", "white_eyes", "empty_eyes", "torn_clothes"}
PASSIVE_ATTACK_SCENE_TAGS = {"facing_another", "fighting", "hitting", "punching", "slapping", "injury"}
PASSIVE_ATTACK_CONFLICT_TAGS = {
    "solo", "looking_at_viewer", "facing_viewer", "smile", "closed_mouth_smile",
    "gentle_smile", "light_smile", "standing", "walking", "sitting",
    "holding_hands", "hug", "eating", "feeding", "sharing_food",
}
DEFEATED_CONFLICT_TAGS = {
    "looking_at_viewer", "facing_viewer", "smile", "closed_mouth_smile",
    "gentle_smile", "light_smile", "standing", "walking", "running",
    "jumping", "sitting", "dynamic_pose", "reaching_towards_viewer",
    "from_below", "casting_spell", "pyrokinesis", "magic", "magic_circle",
    "fire", "embers", "sparks", "holding_hands", "hug",
}
REVIEW_TEMPLATE_SLOT_POOLS = {
    "generic": {
        "composition": ("full_body", "upper_body", "portrait", "close-up"),
        "interaction": ("facing_another", "looking_at_another", "group_focus"),
        "setting": ("outdoors", "indoors", "city", "street", "garden", "bedroom"),
        "atmosphere": ("day", "night", "sunlight", "backlighting", "soft_lighting"),
    },
    "battle": {
        "composition": ("full_body", "dynamic_pose", "from_below"),
        "interaction": ("facing_another", "reaching_towards_viewer"),
        "setting": ("outdoors", "city", "street", "battlefield"),
        "atmosphere": ("smoke", "cinematic_lighting"),
    },
    "kiss": {
        "composition": ("close-up", "upper_body", "full_body"),
        "interaction": ("kiss", "couple", "facing_another", "closed_eyes"),
        "setting": ("indoors", "bedroom", "window", "curtains"),
        "atmosphere": ("soft_lighting", "backlighting", "sunset"),
    },
    "romance": {
        "composition": ("full_body", "upper_body", "close-up"),
        "interaction": ("couple", "holding_hands", "looking_at_another", "facing_another"),
        "setting": ("outdoors", "city", "street", "park", "cafe"),
        "atmosphere": ("sunset", "backlighting", "soft_lighting"),
    },
    "sleep": {
        "composition": ("full_body", "upper_body", "close-up"),
        "interaction": ("sleeping", "lying", "closed_eyes"),
        "setting": ("bedroom", "bed", "on_bed", "pillow", "blanket"),
        "atmosphere": ("soft_lighting", "night", "moonlight"),
    },
    "bathing": {
        "composition": ("full_body", "upper_body", "close-up"),
        "interaction": ("bathing", "wet"),
        "setting": ("indoors", "bathroom", "bathtub", "onsen"),
        "atmosphere": ("soft_lighting", "steam", "backlighting"),
    },
    "beach": {
        "composition": ("full_body", "upper_body", "wide_shot"),
        "interaction": ("playing", "walking", "looking_at_another"),
        "setting": ("outdoors", "beach", "ocean", "shore"),
        "atmosphere": ("sunlight", "day", "sunset"),
    },
    "street": {
        "composition": ("full_body", "upper_body", "wide_shot"),
        "interaction": ("walking", "facing_another", "looking_at_another"),
        "setting": ("outdoors", "city", "street", "alley"),
        "atmosphere": ("day", "night", "rain", "sunset"),
    },
}
REVIEW_ENRICHMENT_FORBIDDEN = {
    "office", "desk", "paper", "papers", "holding_pen", "writing",
    "shrine", "torii", "paper_lantern", "lantern",
}
REVIEW_NEGATIVE_IN_POSITIVE = {
    "lowres", "blurry", "bad_anatomy", "worst_quality", "low_quality",
    "signature", "watermark", "text", "artist_name",
}
REVIEW_LLM_ADULT_ADDITION_TAGS = {
    "nude", "sex", "penetration", "doggystyle", "missionary", "girl_on_top",
    "cowgirl_position", "oral/fellatio", "fellatio", "handjob", "masturbation",
    "anal", "cum", "cum_inside", "penis", "pussy/vaginal", "nipples",
}
INVALID_PROMPT_TAGS = {"none", "null", "nil", "na", "n/a", "undefined"}
CONTEXTUAL_PROMPT_TAGS = {"green_blood"}

TRANSPARENT_BACKGROUND_INTENT_PATTERNS = (
    r"\btransparent\s+background\b",
    r"\bno\s+background\b",
    "\u900f\u660e\u80cc\u666f",
    "\u80cc\u666f.{0,6}\u900f\u660e",
    "\u900f\u660e\u5e95",
    "\u900f\u660e\u5e95\u8272",
    "\u65e0\u80cc\u666f",
    "\u53bb\u80cc\u666f",
    "\u62a0\u56fe",
    "\u6263\u56fe",
)


def _bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() not in {"0", "false", "no", "off", ""}


def _skills_dir():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "vlm_skills")


def _read_review_skill():
    path = os.path.join(_skills_dir(), REVIEW_SKILL_FILE)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except Exception as exc:
        logger.warning("Danbooru review skill skipped: %s", exc)
        return ""


def _tag_list(prompt):
    tags = []
    seen = set()
    for raw in str(prompt or "").split(","):
        tag = canvas_danbooru_service._canvas_clean_prompt_tag_name(raw)
        if not tag or tag in INVALID_PROMPT_TAGS or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
    return tags


def _has_explicit_subject_count(tags):
    tag_set = set(tags or [])
    return bool(tag_set.intersection(COUNT_TAGS) or ("1girl" in tag_set and "1boy" in tag_set))


def _explicit_subject_count_tags(tags):
    return [tag for tag in tags or [] if tag in COUNT_TAGS]


def _join_tags(tags):
    output = []
    for tag in tags or []:
        clean = canvas_danbooru_service._canvas_clean_prompt_tag_name(tag)
        if clean and clean not in INVALID_PROMPT_TAGS and clean not in output:
            output.append(clean)
    return ", ".join(output)


def _user_requested_green_blood(text):
    return bool(re.search(r"(?:green\s*blood|\u7eff\u8840|\u7eff\u8272\u8840|\u7eff\u8272\u8840\u6db2|\u8840\u6db2.{0,8}\u7eff)", str(text or ""), re.I))


def _filter_contextual_tags(prompt, review_payload):
    user_prompt = str((review_payload or {}).get("user_request") or "")
    blocked = set()
    if not _user_requested_green_blood(user_prompt):
        blocked.add("green_blood")
    if not blocked:
        return _join_tags(_tag_list(prompt)) or str(prompt or "").strip()
    return _join_tags([tag for tag in _tag_list(prompt) if tag not in blocked]) or str(prompt or "").strip()


def _contains_chinese(text):
    return bool(re.search(r"[\u3400-\u9fff]", str(text or "")))


def _text_has_any(text, patterns):
    source = str(text or "")
    return any(_has_positive_pattern(source, pattern) for pattern in patterns)


def _match_is_negated(source, match):
    if match is None:
        return False
    start = int(match.start() or 0)
    prefix = str(source or "")[max(0, start - 14):start].lower()
    return bool(re.search(
        r"(?:不(?:要|想|用|带|帶|画|畫|是|给|給)?|别|別|勿|禁止|无需|無需|no|not|without)\s*(?:给我|給我|老是|再|只|太|那么|那麼)?\s*$",
        prefix,
        re.I,
    ) or re.search(r"(?:不要|不想|别|別|禁止|no|not|without).{0,8}$", prefix, re.I))


def _has_positive_pattern(text, pattern):
    source = str(text or "")
    return any(not _match_is_negated(source, match) for match in re.finditer(pattern, source, re.I))


def _is_danbooru_target(target):
    if not isinstance(target, dict):
        return False
    text = " ".join(
        str(target.get(key) or "")
        for key in ("key", "name", "backend_engine", "task_method", "text_encoder")
    ).lower()
    return any(term in text for term in ("sdxl_danbooru", "danbooru", "illustrious", "noob", "pony", "animagine", "sdxl", "sd15"))


def _action_prompt(action):
    if not isinstance(action, dict):
        return ""
    for key in ("prompt", "image_prompt", "recommended_prompt", "final_prompt"):
        value = str(action.get(key) or "").strip()
        if value:
            return value
    return ""


def _draft_prompt(action):
    if not isinstance(action, dict):
        return ""
    value = str(action.get("draft_prompt") or "").strip()
    if value:
        return value
    return _action_prompt(action)


def _review_prompt_intent(review_payload):
    return canvas_vlm_prompt_pipeline.normalize_structured_prompt_intent(
        (review_payload or {}).get("prompt_intent")
    )


def _review_template_candidates(review_payload):
    payload = review_payload if isinstance(review_payload, dict) else {}
    candidate_prompt = str(payload.get("candidate_prompt") or "").strip()
    tags = _tag_list(candidate_prompt)
    tag_set = set(tags)
    user_prompt = str(payload.get("user_request") or "")
    branch = _review_branch(user_prompt, tags)
    prompt_intent = _review_prompt_intent(payload)
    slots = REVIEW_TEMPLATE_SLOT_POOLS.get(branch, REVIEW_TEMPLATE_SLOT_POOLS["generic"])
    output = {}
    for slot, values in (slots or {}).items():
        allowed = []
        for tag in values or ():
            clean = str(tag or "").strip()
            if not clean or clean in tag_set or clean in REVIEW_ENRICHMENT_FORBIDDEN:
                continue
            if clean in allowed:
                continue
            allowed.append(clean)
        if allowed:
            output[slot] = allowed[:8]
    if prompt_intent.get("locked_tags"):
        output["locked"] = [tag for tag in prompt_intent.get("locked_tags") if tag not in tag_set][:8]
    return {
        "branch": branch,
        "slots": output,
    }


def _sanitize_template_slot_picks(template_slot_picks, review_payload):
    allowed = (_review_template_candidates(review_payload).get("slots") or {})
    if not isinstance(template_slot_picks, dict) or not allowed:
        return {}
    output = {}
    total = 0
    for slot, allowed_tags in allowed.items():
        raw = template_slot_picks.get(slot)
        if raw is None:
            continue
        values = raw if isinstance(raw, list) else [raw]
        cleaned = []
        for item in values:
            tag = str(item or "").strip()
            if not tag or tag not in set(allowed_tags) or tag in cleaned:
                continue
            cleaned.append(tag)
            total += 1
            if len(cleaned) >= (2 if slot != "locked" else 4) or total >= 8:
                break
        if cleaned:
            output[slot] = cleaned
        if total >= 8:
            break
    return output


def _template_slot_pick_tags(template_slot_picks):
    output = []
    for slot in ("locked", "composition", "interaction", "setting", "atmosphere"):
        for tag in (template_slot_picks or {}).get(slot) or []:
            clean = str(tag or "").strip()
            if clean and clean not in output:
                output.append(clean)
    return output


def _compose_prompt_from_template_slot_picks(base_prompt, template_slot_picks, review_payload):
    tags = _tag_list(base_prompt)
    if not tags:
        return str(base_prompt or "").strip(), []
    additions = _template_slot_pick_tags(_sanitize_template_slot_picks(template_slot_picks, review_payload))
    if not additions:
        return _join_tags(tags) or str(base_prompt or "").strip(), []
    next_tags = list(tags)
    changes = []
    for tag in additions:
        if tag in next_tags:
            continue
        next_tags.append(tag)
        changes.append({"type": "template_pick", "tag": tag, "reason": "selected from template_candidates"})
    if not changes:
        return _join_tags(tags) or str(base_prompt or "").strip(), []
    return _join_tags(next_tags), changes


def _resolved_tags(resolution):
    if not isinstance(resolution, dict):
        return [], []
    if str(resolution.get("state") or "").strip().lower() != "resolved":
        return [], []
    characters = [
        str(item.get("tag") or "").strip()
        for item in resolution.get("resolved") or []
        if isinstance(item, dict) and item.get("tag")
    ]
    copyrights = [
        str(item.get("tag") or "").strip()
        for item in resolution.get("copyright_candidates") or []
        if isinstance(item, dict) and item.get("tag")
    ]
    return characters, copyrights


def _known_prompt_identity_tags(tags):
    try:
        index = canvas_danbooru_service._canvas_load_danbooru_character_index()
        character_set = set(index.get("character_tags") or set())
        copyright_set = set(index.get("copyright_tags") or set())
    except Exception:
        character_set = set()
        copyright_set = set()
    characters = []
    copyrights = []
    for tag in tags or []:
        clean = str(tag or "").strip()
        if not clean:
            continue
        if clean in character_set and clean not in characters:
            characters.append(clean)
        elif clean in copyright_set and clean not in copyrights:
            copyrights.append(clean)
    return characters, copyrights


def _review_character_tags(tags, resolution=None):
    resolved_characters, _ = _resolved_tags(resolution)
    prompt_characters, _ = _known_prompt_identity_tags(tags)
    output = []
    for tag in list(resolved_characters) + list(prompt_characters):
        clean = str(tag or "").strip()
        if clean and clean not in output:
            output.append(clean)
    return output


def _expected_subject_count_tags(tags, user_prompt="", resolution=None):
    character_tags = _review_character_tags(tags, resolution)
    try:
        pipeline = getattr(canvas_danbooru_preflight, "canvas_vlm_prompt_pipeline", None)
        counter = getattr(pipeline, "_subject_count_tags", None)
        if callable(counter):
            expected = counter(user_prompt, _join_tags(tags), character_tags, _review_branch(user_prompt, tags))
            expected = [str(tag or "").strip() for tag in expected or [] if str(tag or "").strip()]
            tag_set = set(tags or [])
            if expected == ["multiple_others"] and "yuri" in tag_set:
                return ["2girls"]
            if expected == ["multiple_others"] and "yaoi" in tag_set:
                return ["2boys"]
            if expected and (len(character_tags) >= 2 or "multiple_others" in expected):
                return expected
    except Exception:
        pass
    if len(character_tags) < 2:
        return []
    tag_set = set(tags or [])
    if "yuri" in tag_set:
        return ["2girls"]
    if "yaoi" in tag_set:
        return ["2boys"]
    return ["multiple_others"]


def build_review_payload(action, payload, params, user_prompt, candidate_prompt):
    data = payload if isinstance(payload, dict) else {}
    agent_context = data.get("agent_context") if isinstance(data.get("agent_context"), dict) else {}
    targets = agent_context.get("prompt_generation_targets") if isinstance(agent_context.get("prompt_generation_targets"), dict) else {}
    target = targets.get("text_to_image") if isinstance(targets.get("text_to_image"), dict) else {}
    effective_user_prompt = str(user_prompt or params.get("prompt") or "").strip()
    resolution = canvas_danbooru_service._canvas_requested_character_resolution(effective_user_prompt, candidate_prompt)
    preflight = canvas_danbooru_preflight.prompt_preflight_check({
        "prompt": candidate_prompt,
        "user_prompt": effective_user_prompt,
        "prompt_target": target,
        "target_key": target.get("key") or "",
        "action": action.get("action") if isinstance(action, dict) else "",
    })
    mode = str(params.get("danbooru_review_mode") or "repair_and_enrich").strip() or "repair_and_enrich"
    prompt_intent = _review_prompt_intent(action if isinstance(action, dict) else {})
    try:
        association_context = canvas_vlm_prompt_pipeline.build_association_review_context(
            effective_user_prompt,
            candidate_prompt,
            prompt_intent=prompt_intent,
            resolution=resolution,
        )
    except Exception as exc:
        logger.warning("Danbooru association review context skipped: %s", exc)
        association_context = {}
    llm_enabled = (
        _bool(params.get("enable_danbooru_review_llm"), False)
        or _bool(params.get("danbooru_review_use_llm"), False)
        or mode.lower().startswith("llm")
        or mode.lower().endswith("_llm")
    )
    return {
        "schema": "simpai.danbooru_prompt_review.v1",
        "user_request": effective_user_prompt,
        "target": target,
        "draft_prompt": _draft_prompt(action),
        "candidate_prompt": str(candidate_prompt or "").strip(),
        "original_llm_draft": str((action or {}).get("original_llm_draft") or "")[:1800],
        "canonicalized_prompt": str((action or {}).get("canonicalized_prompt") or "")[:1800],
        "llm_draft_canonicalization": (action or {}).get("llm_draft_canonicalization") if isinstance((action or {}).get("llm_draft_canonicalization"), dict) else {},
        "intent_hints": (
            ((action or {}).get("llm_draft_canonicalization") or {}).get("unmatched_hints")
            if isinstance((action or {}).get("llm_draft_canonicalization"), dict)
            else []
        ),
        "negative_prompt": str(
            (action or {}).get("negative_prompt")
            or (action or {}).get("negativePrompt")
            or (action or {}).get("negative")
            or ""
        ).strip(),
        "prompt_intent": prompt_intent,
        "template_candidates": _review_template_candidates({
            "user_request": effective_user_prompt,
            "candidate_prompt": str(candidate_prompt or "").strip(),
            "prompt_intent": prompt_intent,
        }),
        "association_context": association_context,
        "resolution": resolution,
        "preflight": preflight,
        "mode": mode,
        "llm_enabled": llm_enabled,
        "post_review_repair": _bool(params.get("danbooru_review_post_repair"), False),
        "threshold": int(float(params.get("danbooru_review_threshold") or 75)),
    }


def build_review_messages(review_payload):
    skill = _read_review_skill()
    system = (
        "You are the isolated SimpAI Danbooru prompt review gate. "
        "Do not use the user's chat system prompt, persona, or conversation memory. "
        "Review only the provided payload and return JSON only. "
        "Reject only hard blocks; for ordinary quality, tag-style, or richness issues prefer fixed or warn. "
        "In repair_and_enrich mode, prefer returning template_slot_picks chosen from template_candidates instead of rewriting the whole prompt."
    )
    if skill:
        system += "\n\nDedicated review skill:\n" + skill[:9000]
    user = (
        "Review this SDXL/Danbooru prompt payload. Return only the required JSON object.\n\n"
        + json.dumps(review_payload or {}, ensure_ascii=False, indent=2)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_compact_review_messages(review_payload):
    payload = review_payload if isinstance(review_payload, dict) else {}
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    resolution = payload.get("resolution") if isinstance(payload.get("resolution"), dict) else {}
    preflight = payload.get("preflight") if isinstance(payload.get("preflight"), dict) else {}
    checks = preflight.get("checks") if isinstance(preflight.get("checks"), list) else []
    compact = {
        "user_request": str(payload.get("user_request") or "")[:1200],
        "draft_prompt": str(payload.get("draft_prompt") or "")[:1200],
        "candidate_prompt": str(payload.get("candidate_prompt") or "")[:1800],
        "original_llm_draft": str(payload.get("original_llm_draft") or "")[:1200],
        "canonicalized_prompt": str(payload.get("canonicalized_prompt") or "")[:1800],
        "llm_draft_canonicalization": payload.get("llm_draft_canonicalization") if isinstance(payload.get("llm_draft_canonicalization"), dict) else {},
        "intent_hints": payload.get("intent_hints") if isinstance(payload.get("intent_hints"), list) else [],
        "negative_prompt": str(payload.get("negative_prompt") or "")[:500],
        "prompt_intent": _review_prompt_intent(payload),
        "template_candidates": _review_template_candidates(payload),
        "association_context": _compact_association_review_context(_association_review_context(payload)),
        "target": {
            "key": target.get("key"),
            "name": target.get("name"),
            "backend_engine": target.get("backend_engine"),
            "text_encoder": target.get("text_encoder"),
        },
        "resolution": {
            "state": resolution.get("state"),
            "resolved": resolution.get("resolved"),
            "copyright_candidates": resolution.get("copyright_candidates"),
            "blocked": resolution.get("blocked"),
        },
        "preflight": {
            "state": preflight.get("state"),
            "summary": preflight.get("summary"),
            "checks": checks[:6],
        },
        "mode": payload.get("mode") or "repair_and_enrich",
    }
    system = (
        "You are an isolated SDXL/Danbooru prompt review gate. Return JSON only. "
        "Do not use chat persona or memory. In repair_and_enrich mode first remove conflicting tags, "
        "then you may add only a few safe tags chosen from template_candidates.slots. "
        "Treat original_llm_draft and intent_hints as intent evidence, but keep final_prompt database-like and compact. "
        "If prompt_intent contains locked_tags or scene_strictness=high, preserve them and avoid free enrichment. "
        "Never invent enrichment tags outside template_candidates unless they are already present in candidate_prompt or directly required by prompt_intent.locked_tags. "
        "Use compact local Danbooru-style tags, e.g. sleeping, closed_eyes, lying, bed, on_bed, "
        "kiss, couple, facing_another, yuri, hug, lap_pillow, bathroom, bathing, nude, full_body, "
        "rain, umbrella, shared_umbrella, kabedon, against_wall, battle, fighting, city, street, beach, "
        "ocean, swimsuit, playing, cafe, "
        "classroom, transparent_background. Tag standardness is advisory only: do not reject solely because "
        "a tag is uncommon, nonstandard, or has a preferred synonym if the prompt is otherwise coherent. "
        "Never invent long underscore prose, translated Chinese tags, artist tags, character tags from memory, "
        "or execution parameters. Reject only hard blocks such as empty/unparseable prompt or safety-policy conflict; "
        "otherwise prefer fixed or warn. If many major pieces are missing, warn. "
        "Output schema: {state,score,intent_alignment,tag_validity,conflict_check,subject_integrity,"
        "safety_policy,prompt_readiness,issues,changes,final_prompt,template_slot_picks,needs_user_confirmation}. "
        "Prefer template_slot_picks over free final_prompt rewrites when template_candidates are available."
    )
    user = "Review this compact payload:\n" + json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_review_response(text):
    source = str(text or "").strip()
    if not source:
        return {}
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", source, re.I)
    candidates = [fenced.group(1).strip()] if fenced else []
    candidates.append(source)
    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            pass
        for index, char in enumerate(candidate):
            if char != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(candidate[index:])
            except Exception:
                continue
            return parsed if isinstance(parsed, dict) else {}
    return {}


def _intent_restoration_tags(user_prompt, tags, include_enrichment=False):
    tag_set = set(tags or [])
    additions = []

    def add(tag, reason, blocked_by=()):
        if not tag or tag in tag_set or tag_set.intersection(set(blocked_by or ())):
            return
        if tag in {item[0] for item in additions}:
            return
        additions.append((tag, reason))

    def add_enrichment(tag, reason, blocked_by=()):
        if include_enrichment:
            add(tag, reason, blocked_by=blocked_by)

    quiet_scene = bool(tag_set.intersection({"sleeping", "lying", "lap_pillow", "on_ground"}) or _text_has_any(user_prompt, DEFEATED_INTENT_PATTERNS))
    if _text_has_any(user_prompt, [r"\bsleep(?:ing|y)?\b", r"\basleep\b", r"\bnap\b", "\u7761", "\u5165\u7761"]):
        add("sleeping", "restore explicit sleeping intent")
        add("closed_eyes", "restore sleeping expression")
        add("lying", "restore sleeping pose", blocked_by={"standing", "walking"})
    if _text_has_any(user_prompt, BED_INTENT_PATTERNS):
        add("bed", "restore bed setting")
        add("on_bed", "restore on-bed placement")
        add("bedroom", "restore bedroom setting")
        add_enrichment("pillow", "restore bedding prop")
        add_enrichment("blanket", "restore bedding prop")
        add_enrichment("soft_lighting", "restore quiet bed-scene atmosphere")
        add_enrichment("depth_of_field", "restore image depth")
        add_enrichment("blurry_background", "restore image depth")
    if _text_has_any(user_prompt, [r"\bkiss(?:ing)?\b", "\u63a5\u543b", "\u4eb2\u543b", "\u4eb2\u5634", "\u4eb2\u4e00\u4e0b", "\u4eb2\u4e00\u53e3", "\u4eb2\u4eb2"]):
        add("kiss", "restore explicit kissing intent")
        add("couple", "restore relationship intent")
        add("facing_another", "restore kissing composition")
        add("closed_eyes", "restore kissing expression")
        add_enrichment("indoors", "restore bounded kissing scene setting")
        add_enrichment("window", "restore bounded kissing scene setting")
        add_enrichment("soft_lighting", "restore kissing atmosphere")
        add_enrichment("depth_of_field", "restore image depth")
        add_enrichment("blurry_background", "restore image depth")
        if "2girls" in tag_set:
            add("yuri", "restore two-girl romance intent")
    if _text_has_any(user_prompt, [r"\bhug(?:ging)?\b", r"\bembrace\b", "\u62e5\u62b1"]):
        add("hug", "restore explicit hug intent")
        add("couple", "restore relationship intent")
    if _text_has_any(user_prompt, [r"\blap[_ -]?pillow\b", "\u819d\u6795"]):
        add("lap_pillow", "restore lap-pillow intent")
        add("lying", "restore lap-pillow pose")
    if _text_has_any(user_prompt, BATHING_INTENT_PATTERNS):
        add("bathroom", "restore bathroom setting")
        add("bathing", "restore bathing action")
        add("wet", "restore bathing/wet context")
        add_enrichment("soft_lighting", "restore bathing atmosphere")
        add_enrichment("depth_of_field", "restore image depth")
        add_enrichment("blurry_background", "restore image depth")
    if _text_has_any(user_prompt, BEACH_INTENT_PATTERNS):
        add("outdoors", "restore beach/outdoor setting")
        add("beach", "restore beach setting")
        add("ocean", "restore seaside context")
        add_enrichment("sunlight", "restore beach lighting")
        add_enrichment("depth_of_field", "restore image depth")
        add_enrichment("blurry_background", "restore image depth")
    if _text_has_any(user_prompt, SWIMSUIT_INTENT_PATTERNS):
        add("swimsuit", "restore swimsuit outfit intent")
    if _text_has_any(user_prompt, PLAY_INTENT_PATTERNS):
        add("playing", "restore explicit play action")
    if _text_has_any(user_prompt, GROUP_OTHER_PEOPLE_PATTERNS):
        add("looking_at_another", "restore group interaction composition")
    if _text_has_any(user_prompt, KINDERGARTEN_INTENT_PATTERNS):
        add("indoors", "restore kindergarten indoor setting")
        add("kindergarten", "restore kindergarten setting")
        add("classroom", "restore classroom-like setting")
        add("school", "restore school context")
    if _text_has_any(user_prompt, [r"\bnude\b", "\u88f8"]):
        add("nude", "restore explicit body-state intent")
    if _text_has_any(user_prompt, [r"\bfull[_ -]?body\b", "\u5168\u8eab"]):
        add("full_body", "restore full-body composition")
    if _text_has_any(user_prompt, [r"\bshared[_ -]?umbrella\b", "\u76f8\u5408\u4f1e", "\u5171\u6491"]):
        add("shared_umbrella", "restore shared-umbrella intent")
        add("umbrella", "restore umbrella prop")
    elif _text_has_any(user_prompt, [r"\bumbrella\b", "\u4f1e"]):
        add("umbrella", "restore umbrella prop")
    if _text_has_any(user_prompt, [r"\brain(?:y)?\b", "\u4e0b\u96e8", "\u96e8\u5929"]):
        add("rain", "restore rain setting")
    if _text_has_any(user_prompt, [r"\bkabedon\b", "\u58c1\u549a"]):
        add("kabedon", "restore kabedon action")
        add("against_wall", "restore wall composition")
    if _text_has_any(user_prompt, [r"\bbattle\b", r"\bfight(?:ing)?\b", "\u6218\u6597", "\u6253\u6597"]):
        add("battle", "restore battle setting")
        add("fighting", "restore battle action")
        if not quiet_scene:
            add("dynamic_pose", "restore battle pose")
    if _text_has_any(user_prompt, PASSIVE_ATTACK_INTENT_PATTERNS):
        add("facing_another", "restore passive attack relation")
        add("fighting", "restore passive attack action")
        add("hitting", "restore passive attack contact")
        add("injury", "restore passive attack state")
    if _text_has_any(user_prompt, DEFEATED_INTENT_PATTERNS):
        if _text_has_any(user_prompt, KNEELING_INTENT_PATTERNS) or not _text_has_any(user_prompt, DEFEATED_DOWN_INTENT_PATTERNS):
            add("kneeling", "restore defeated kneeling pose")
        else:
            add("lying", "restore knocked-down pose")
        add("on_ground", "restore knocked-down placement")
        add("injury", "restore defeated/injured state")
    if _text_has_any(user_prompt, [r"\broll(?:ed|ing)?\s+eyes?\b", "\u7ffb\u767d\u773c"]):
        add("rolling_eyes", "restore rolling-eyes expression")
        add("white_eyes", "restore rolling-eyes expression")
        add("empty_eyes", "restore vacant-eye expression")
    if _text_has_any(user_prompt, [r"\btorn\s+clothes?\b", r"\bripped\s+clothes?\b", "\u8863\u670d.{0,6}(?:\u7834\u788e|\u7834\u635f|\u7834\u88c2|\u6495\u88c2)", "\u7834\u8863", "\u7834\u70c2\u8863\u670d"]):
        add("torn_clothes", "restore torn-clothes state")
    if _text_has_any(user_prompt, [r"\bcity\b", "\u57ce\u5e02"]):
        add("outdoors", "restore city/outdoor setting")
        add("city", "restore city setting")
    if _text_has_any(user_prompt, [r"\bstreet\b", "\u8857\u9053", "\u8857\u4e0a"]):
        add("outdoors", "restore street/outdoor setting")
        add("city", "restore street city context")
        add("street", "restore street setting")
    if _text_has_any(user_prompt, [r"\bholding\s+hands\b", "\u7275\u624b", "\u624b\u7275\u624b"]):
        add("holding_hands", "restore hand-holding action")
        add("couple", "restore two-character interaction")
        add("looking_at_another", "restore interaction composition")
    if _text_has_any(user_prompt, [r"\bwalking\b", r"\bwalk\b", "\u8d70\u8def", "\u884c\u8d70"]):
        add("walking", "restore walking action")
    if _text_has_any(user_prompt, [r"\bcafe\b", r"\bcaf[e\u00e9]\b", "\u5496\u5561"]):
        add("cafe", "restore cafe setting")
    if _text_has_any(user_prompt, [r"\bclassroom\b", "\u6559\u5ba4"]):
        add("classroom", "restore classroom setting")
    if _text_has_any(user_prompt, TRANSPARENT_BACKGROUND_INTENT_PATTERNS):
        add("transparent_background", "restore transparent background request")
        add("full_body", "restore transparent asset composition", blocked_by={"upper_body", "portrait", "cowboy_shot", "close-up"})
        add("standing", "restore transparent asset pose")
    return additions[:12]


def _locked_prompt_intent_issues(review_payload, tags):
    tag_set = set(tags or [])
    issues = []
    for tag in _review_prompt_intent(review_payload).get("locked_tags") or []:
        if tag not in tag_set:
            issues.append({
                "code": "missing_locked_intent_tag",
                "tag": tag,
                "message": f"restore locked prompt_intent tag: {tag}",
            })
    return issues


def _missing_intent_issues(user_prompt, tags):
    return [
        {"code": "missing_core_intent_tag", "tag": tag, "message": reason}
        for tag, reason in _intent_restoration_tags(user_prompt, tags)
    ]


def _conflict_issues(tags, user_prompt="", resolution=None):
    tag_set = set(tags)
    issues = []
    if "solo" in tag_set and ({"2girls", "2boys", "1girl", "1boy"} & tag_set and ("2girls" in tag_set or "2boys" in tag_set or ("1girl" in tag_set and "1boy" in tag_set))):
        issues.append({"code": "solo_multi_subject_conflict", "message": "solo conflicts with a multi-subject count."})
    character_tags = _review_character_tags(tags, resolution)
    expected_count_tags = _expected_subject_count_tags(tags, user_prompt=user_prompt, resolution=resolution)
    if expected_count_tags:
        expected_set = set(expected_count_tags)
        current_counts = tag_set.intersection(COUNT_TAGS)
        wrong_counts = sorted(current_counts.difference(expected_set))
        solo_conflict = "solo" in tag_set and (len(expected_count_tags) > 1 or not expected_set.intersection({"1girl", "1boy"}))
        if wrong_counts or solo_conflict:
            issues.append({
                "code": "named_character_subject_count_conflict",
                "message": "Visible named character count conflicts with resolved character tags.",
                "expected": expected_count_tags,
                "tags": wrong_counts + (["solo"] if solo_conflict else []),
            })
    if "no_humans" in tag_set and character_tags:
        issues.append({"code": "no_humans_named_character", "message": "no_humans conflicts with resolved named character tags."})
    if tag_set.intersection({"looking_at_viewer", "facing_viewer"}) and tag_set.intersection({"sleeping", "closed_eyes", "kiss", "facing_another", "looking_at_another"}):
        issues.append({"code": "viewer_gaze_action_conflict", "message": "viewer-facing tags conflict with the requested closed-eye or facing-another action."})
    if tag_set.intersection({"standing", "walking"}) and tag_set.intersection({"lying", "sleeping", "on_bed", "lap_pillow"}):
        issues.append({"code": "pose_conflict", "message": "standing/walking conflicts with lying, sleeping, bed, or lap-pillow tags."})
    if "dynamic_pose" in tag_set and tag_set.intersection({"sleeping", "lying", "lap_pillow"}):
        issues.append({"code": "dynamic_quiet_scene_conflict", "message": "dynamic_pose conflicts with a quiet lying/sleeping scene."})
    if (_text_has_any(user_prompt, DEFEATED_INTENT_PATTERNS) or tag_set.intersection(DEFEATED_SCENE_TAGS)):
        conflicting = sorted(tag_set.intersection(DEFEATED_CONFLICT_TAGS))
        if conflicting:
            issues.append({
                "code": "defeated_state_conflict",
                "message": "Tags conflict with the requested knocked-down or defeated state: " + ", ".join(conflicting[:12]),
                "tags": conflicting,
            })
    if _text_has_any(user_prompt, PASSIVE_ATTACK_INTENT_PATTERNS) or tag_set.intersection({"hitting", "punching", "slapping"}):
        conflicting = sorted(tag_set.intersection(PASSIVE_ATTACK_CONFLICT_TAGS))
        if conflicting:
            issues.append({
                "code": "passive_attack_conflict",
                "message": "Tags conflict with the requested passive attack event: " + ", ".join(conflicting[:12]),
                "tags": conflicting,
            })
    if "close-up" in tag_set and "full_body" in tag_set and _text_has_any(user_prompt, [r"\bnude\b", "\u88f8", "\u5168\u8eab"]):
        issues.append({"code": "closeup_fullbody_conflict", "message": "close-up conflicts with full_body for a character-visible nude request."})
    indoor_scene_tags = {"indoors", "classroom", "kindergarten", "office", "library", "bedroom", "bathroom", "cafe", "teahouse", "restaurant", "kitchen"}
    outdoor_scene_tags = {"outdoors", "beach", "ocean", "city", "street", "forest", "park", "garden", "mountain", "shrine"}
    if ("indoors" in tag_set and tag_set.intersection(outdoor_scene_tags)) or ("outdoors" in tag_set and tag_set.intersection(indoor_scene_tags)):
        issues.append({"code": "indoor_outdoor_mixed", "message": "indoors and outdoors are both present."})
    if _text_has_any(user_prompt, BED_INTENT_PATTERNS) or tag_set.intersection(BED_SCENE_TAGS):
        conflicting = sorted(tag_set.intersection(BED_CONFLICT_TAGS))
        if conflicting:
            issues.append({
                "code": "bed_scene_conflict",
                "message": "Tags conflict with the requested bed/bedroom scene: " + ", ".join(conflicting[:12]),
                "tags": conflicting,
            })
    if _text_has_any(user_prompt, BATHING_INTENT_PATTERNS):
        conflicting = sorted(tag_set.intersection(BATHING_CONFLICT_TAGS))
        if conflicting:
            issues.append({
                "code": "bathing_scene_conflict",
                "message": "Tags conflict with the requested bathing/bathroom scene: " + ", ".join(conflicting[:12]),
                "tags": conflicting,
            })
    if _text_has_any(user_prompt, BEACH_INTENT_PATTERNS) or tag_set.intersection({"beach", "ocean"}):
        beach_conflicts = set(BEACH_CONFLICT_TAGS)
        if _text_has_any(user_prompt, PLAY_INTENT_PATTERNS) or "playing" in tag_set:
            beach_conflicts.update({"holding", "sitting"})
        conflicting = sorted(tag_set.intersection(beach_conflicts))
        if conflicting:
            issues.append({
                "code": "beach_scene_conflict",
                "message": "Tags conflict with the requested beach/seaside scene: " + ", ".join(conflicting[:12]),
                "tags": conflicting,
            })
    if _text_has_any(user_prompt, STREET_INTENT_PATTERNS) or tag_set.intersection({"city", "street"}):
        conflicting = sorted(tag_set.intersection(STREET_CONFLICT_TAGS))
        if conflicting:
            issues.append({
                "code": "street_scene_conflict",
                "message": "Tags conflict with the requested city/street scene: " + ", ".join(conflicting[:12]),
                "tags": conflicting,
            })
    return issues


def _review_branch(user_prompt, tags):
    tag_set = set(tags or [])
    if _text_has_any(user_prompt, BATHING_INTENT_PATTERNS) or tag_set.intersection(BATHING_SCENE_TAGS):
        return "bathing"
    if _text_has_any(user_prompt, BEACH_INTENT_PATTERNS) or tag_set.intersection({"beach", "ocean"}):
        return "beach"
    if _text_has_any(user_prompt, STREET_INTENT_PATTERNS) or tag_set.intersection({"city", "street"}):
        return "street"
    if _text_has_any(user_prompt, [r"\bsleep(?:ing)?\b", r"\basleep\b", "\u7761"]) or tag_set.intersection({"sleeping", "bed", "on_bed"}):
        return "sleep"
    if _text_has_any(user_prompt, [r"\bkiss(?:ing)?\b", "\u63a5\u543b", "\u4eb2\u543b", "\u4eb2\u5634", "\u4eb2\u4e00\u4e0b", "\u4eb2\u4e00\u53e3", "\u4eb2\u4eb2"]) or "kiss" in tag_set:
        return "kiss"
    if _text_has_any(user_prompt, [r"\bhug(?:ging)?\b", r"\bholding\s+hands\b", "\u62e5\u62b1", "\u7275\u624b"]) or tag_set.intersection({"hug", "holding_hands"}):
        return "romance"
    if _text_has_any(user_prompt, [r"\bbattle\b", r"\bfight(?:ing)?\b", "\u6218\u6597", "\u6253\u6597"]) or _text_has_any(user_prompt, PASSIVE_ATTACK_INTENT_PATTERNS) or tag_set.intersection({"battle", "fighting", "hitting", "punching", "slapping"}):
        return "battle"
    return "generic"


def _enrichment_additions(tags, review_payload):
    # Deterministic review no longer performs free/random enrichment.
    # Enrichment candidates are exposed to the optional review LLM via template_candidates.
    return []


def _association_review_context(review_payload):
    context = (review_payload or {}).get("association_context")
    return context if isinstance(context, dict) else {}


def _association_review_tag(value):
    tags = _tag_list(value)
    return tags[0] if tags else ""


def _association_review_enrich_enabled(mode):
    clean = str(mode or "").strip().lower()
    return clean in {"repair_and_enrich", "deterministic_association", "association_review", "association"} or "association" in clean


def _compact_association_review_context(context):
    if not isinstance(context, dict) or not context:
        return {}
    return {
        "adult": bool(context.get("adult")),
        "adult_focus": bool(context.get("adult_focus")),
        "adult_level": int(context.get("adult_level") or 0),
        "adult_tags": (context.get("adult_tags") or [])[:12] if isinstance(context.get("adult_tags"), list) else [],
        "branch": str(context.get("branch") or "")[:80],
        "triggers": context.get("triggers") if isinstance(context.get("triggers"), list) else [],
        "selected_additions": (context.get("selected_additions") or [])[:8] if isinstance(context.get("selected_additions"), list) else [],
        "explicit_additions": (context.get("explicit_additions") or [])[:6] if isinstance(context.get("explicit_additions"), list) else [],
        "negative_conflicts": (context.get("negative_conflicts") or [])[:12] if isinstance(context.get("negative_conflicts"), list) else [],
    }


def _apply_small_fixes(tags, issues, review_payload):
    next_tags = list(tags)
    tag_set = set(next_tags)
    changes = []
    user_prompt = str((review_payload or {}).get("user_request") or "")
    mode = str((review_payload or {}).get("mode") or "small_fix").strip().lower()
    resolution = (review_payload or {}).get("resolution") if isinstance((review_payload or {}).get("resolution"), dict) else {}
    character_tags, copyright_tags = _resolved_tags(resolution)

    def remove(tag, reason):
        nonlocal next_tags, tag_set
        if tag in tag_set:
            next_tags = [item for item in next_tags if item != tag]
            tag_set = set(next_tags)
            changes.append({"type": "remove", "tag": tag, "reason": reason})

    def add_after_counts(tag, reason):
        nonlocal next_tags, tag_set
        if not tag or tag in tag_set:
            return
        insert_at = 0
        identity_set = set(character_tags or []) | set(copyright_tags or [])
        while (
            insert_at < len(next_tags)
            and (
                re.match(r"^\d+(?:girl|boy|girls|boys)$|^solo$|^no_humans$", next_tags[insert_at])
                or next_tags[insert_at] in identity_set
            )
        ):
            insert_at += 1
        next_tags.insert(insert_at, tag)
        tag_set = set(next_tags)
        changes.append({"type": "add", "tag": tag, "reason": reason})

    def add_count(tag, reason):
        nonlocal next_tags, tag_set
        if not tag or tag in tag_set:
            return
        insert_at = 0
        while insert_at < len(next_tags) and next_tags[insert_at] in COUNT_TAGS.union({"solo"}):
            insert_at += 1
        next_tags.insert(insert_at, tag)
        tag_set = set(next_tags)
        changes.append({"type": "add", "tag": tag, "reason": reason})

    def append_tag(tag, reason):
        nonlocal next_tags, tag_set
        if not tag or tag in tag_set:
            return
        next_tags.append(tag)
        tag_set = set(next_tags)
        changes.append({"type": "add", "tag": tag, "reason": reason})

    for issue in issues:
        code = str(issue.get("code") if isinstance(issue, dict) else issue)
        if code == "solo_multi_subject_conflict":
            remove("solo", "multi-subject prompt")
        elif code == "missing_locked_intent_tag":
            add_after_counts(str(issue.get("tag") or "").strip(), "restore locked prompt_intent tag")
        elif code == "named_character_subject_count_conflict":
            expected = set(issue.get("expected") or []) if isinstance(issue, dict) else set()
            for tag in list(COUNT_TAGS):
                if tag in tag_set and tag not in expected:
                    remove(tag, "resolved named character count")
            if "solo" in tag_set:
                remove("solo", "resolved named character count")
        elif code == "no_humans_named_character":
            remove("no_humans", "named character is visible")
        elif code == "viewer_gaze_action_conflict":
            remove("looking_at_viewer", "closed-eye or facing-another action")
            remove("facing_viewer", "closed-eye or facing-another action")
        elif code == "pose_conflict":
            if tag_set.intersection({"lying", "sleeping", "on_bed", "lap_pillow"}):
                remove("standing", "lying/sleeping scene")
                remove("walking", "lying/sleeping scene")
        elif code == "dynamic_quiet_scene_conflict":
            remove("dynamic_pose", "quiet lying/sleeping scene")
        elif code == "defeated_state_conflict":
            conflict_tags = issue.get("tags") if isinstance(issue, dict) and isinstance(issue.get("tags"), list) else sorted(tag_set.intersection(DEFEATED_CONFLICT_TAGS))
            for tag in conflict_tags:
                remove(str(tag or "").strip(), "requested knocked-down/defeated state")
        elif code == "passive_attack_conflict":
            conflict_tags = issue.get("tags") if isinstance(issue, dict) and isinstance(issue.get("tags"), list) else sorted(tag_set.intersection(PASSIVE_ATTACK_CONFLICT_TAGS))
            for tag in conflict_tags:
                remove(str(tag or "").strip(), "requested passive attack event")
        elif code == "closeup_fullbody_conflict":
            remove("close-up", "full-body nude request")
        elif code == "indoor_outdoor_mixed":
            if tag_set.intersection({"classroom", "kindergarten", "office", "library", "bedroom", "bathroom", "cafe", "indoors"}):
                remove("outdoors", "explicit indoor setting")
            elif tag_set.intersection({"beach", "ocean", "city", "street", "forest", "park", "garden"}):
                remove("indoors", "explicit outdoor setting")
        elif code == "bathing_scene_conflict":
            conflict_tags = issue.get("tags") if isinstance(issue, dict) and isinstance(issue.get("tags"), list) else sorted(tag_set.intersection(BATHING_CONFLICT_TAGS))
            for tag in conflict_tags:
                remove(str(tag or "").strip(), "requested bathing/bathroom scene")
        elif code == "bed_scene_conflict":
            conflict_tags = issue.get("tags") if isinstance(issue, dict) and isinstance(issue.get("tags"), list) else sorted(tag_set.intersection(BED_CONFLICT_TAGS))
            for tag in conflict_tags:
                remove(str(tag or "").strip(), "requested bed/bedroom scene")
        elif code == "beach_scene_conflict":
            beach_conflicts = set(BEACH_CONFLICT_TAGS)
            if _text_has_any(user_prompt, PLAY_INTENT_PATTERNS) or "playing" in tag_set:
                beach_conflicts.update({"holding", "sitting"})
            conflict_tags = issue.get("tags") if isinstance(issue, dict) and isinstance(issue.get("tags"), list) else sorted(tag_set.intersection(beach_conflicts))
            for tag in conflict_tags:
                remove(str(tag or "").strip(), "requested beach/seaside scene")
        elif code == "street_scene_conflict":
            conflict_tags = issue.get("tags") if isinstance(issue, dict) and isinstance(issue.get("tags"), list) else sorted(tag_set.intersection(STREET_CONFLICT_TAGS))
            for tag in conflict_tags:
                remove(str(tag or "").strip(), "requested city/street scene")
    for tag in character_tags + copyright_tags:
        add_after_counts(tag, "restore resolved identity tag")
    expected_count_tags = _expected_subject_count_tags(next_tags, user_prompt=user_prompt, resolution=resolution)
    if expected_count_tags:
        expected = set(expected_count_tags)
        for tag in list(COUNT_TAGS):
            if tag in tag_set and tag not in expected:
                remove(tag, "resolved named character count")
        if "solo" in tag_set and (len(expected_count_tags) > 1 or not expected.intersection({"1girl", "1boy"})):
            remove("solo", "resolved named character count")
        for tag in expected_count_tags:
            add_count(tag, "restore visible named character count")
    elif character_tags and not tag_set.intersection({"1girl", "1boy", "2girls", "2boys", "no_humans"}):
        count = "1girl"
        if _text_has_any(user_prompt, [r"\bman\b", r"\bmale\b", "\u7537\u4eba", "\u7537\u6027"]):
            count = "1boy" if not character_tags else "1girl"
        next_tags.insert(0, count)
        tag_set = set(next_tags)
        changes.append({"type": "add", "tag": count, "reason": "restore visible subject count"})
    association_context = _association_review_context(review_payload)
    protected_tags = {
        _association_review_tag(tag)
        for tag in (
            list((association_context or {}).get("protected_tags") or [])
            + list(_review_prompt_intent(review_payload).get("locked_tags") or [])
            + list(character_tags or [])
            + list(copyright_tags or [])
        )
        if _association_review_tag(tag)
    }
    adult_tags = {
        _association_review_tag(tag)
        for tag in ((association_context.get("adult_tags") or []) if isinstance(association_context, dict) else [])
        if _association_review_tag(tag)
    }
    if adult_tags.intersection(getattr(canvas_vlm_prompt_pipeline, "ADULT_PARTNER_REQUIRED_TAGS", set())):
        if "solo" in tag_set:
            remove("solo", "adult partner-required action")
        has_girl = bool(tag_set.intersection({"1girl", "2girls", "3girls", "4girls", "5girls", "6girls", "multiple_girls"}) or character_tags)
        has_boy = bool(tag_set.intersection({"1boy", "2boys", "3boys", "4boys", "5boys", "6boys", "multiple_boys"}))
        if has_girl and not has_boy:
            add_count("1boy", "adult partner-required action")
        elif has_boy and not has_girl:
            add_count("1girl", "adult partner-required action")
        elif not has_girl and not has_boy:
            add_count("1girl", "adult partner-required action")
            add_count("1boy", "adult partner-required action")
    for row in (association_context.get("negative_conflicts") or []) if isinstance(association_context, dict) else []:
        if not isinstance(row, dict):
            continue
        removed = _association_review_tag(row.get("removed"))
        if not removed or removed not in tag_set or removed in protected_tags:
            continue
        reason = str(row.get("reason") or "association negative conflict").strip()
        kept = _association_review_tag(row.get("kept"))
        detail = f"association evidence: {reason}"
        if kept:
            detail += f"; kept {kept}"
        remove(removed, detail)
    for row in (association_context.get("explicit_additions") or []) if isinstance(association_context, dict) else []:
        if not isinstance(row, dict):
            continue
        tag = _association_review_tag(row.get("tag"))
        if not tag or tag in tag_set:
            continue
        reason = str(row.get("reason") or "explicit user request").strip()
        append_tag(tag, f"restore explicit request: {reason}")
    if _association_review_enrich_enabled(mode):
        added = 0
        add_limit = 6 if bool(association_context.get("adult_focus")) else 4
        for row in (association_context.get("selected_additions") or []) if isinstance(association_context, dict) else []:
            if not isinstance(row, dict):
                continue
            tag = _association_review_tag(row.get("tag"))
            if not tag or tag in tag_set:
                continue
            slot = str(row.get("slot") or "").strip()
            reason = str(row.get("reason") or row.get("source") or "association positive evidence").strip()
            append_tag(tag, f"association evidence: {reason}" + (f"; slot={slot}" if slot else ""))
            added += 1
            if added >= add_limit:
                break
    for tag, reason in _intent_restoration_tags(user_prompt, next_tags, include_enrichment=(mode == "repair_and_enrich")):
        next_tags.append(tag)
        changes.append({"type": "add", "tag": tag, "reason": reason})
        tag_set = set(next_tags)
    for item in _enrichment_additions(next_tags, review_payload):
        tag = item.get("tag")
        if tag and tag not in tag_set:
            next_tags.append(tag)
            changes.append({"type": "enrich", "tag": tag, "reason": item.get("reason")})
            tag_set = set(next_tags)
    if tag_set.intersection({"holding_hands", "looking_at_another", "facing_another"}) and "looking_at_viewer" in tag_set:
        remove("looking_at_viewer", "two-character interaction composition")
    if tag_set.intersection({"holding_hands", "looking_at_another", "facing_another"}) and "facing_viewer" in tag_set:
        remove("facing_viewer", "two-character interaction composition")
    deduped = []
    seen = set()
    for tag in next_tags:
        if tag and tag not in seen:
            deduped.append(tag)
            seen.add(tag)
    return deduped, changes


def deterministic_review(review_payload):
    candidate = str((review_payload or {}).get("candidate_prompt") or "").strip()
    user_prompt = str((review_payload or {}).get("user_request") or "").strip()
    target = (review_payload or {}).get("target") if isinstance((review_payload or {}).get("target"), dict) else {}
    mode = str((review_payload or {}).get("mode") or "small_fix").strip()
    tags = _tag_list(candidate)
    issues = []
    if not candidate:
        issues.append({"code": "empty_prompt", "message": "Prompt is empty."})
    if not _is_danbooru_target(target):
        return {"state": "skipped", "score": 100, "issues": [], "changes": [], "final_prompt": candidate}
    if _contains_chinese(candidate):
        issues.append({"code": "contains_chinese", "message": "Danbooru prompt contains Chinese characters."})
    if candidate.count(",") < 1:
        issues.append({"code": "not_comma_tags", "message": "Prompt is not comma-separated Danbooru tags."})
    if re.search(r"[。！？.!?]\s*$", candidate):
        issues.append({"code": "sentence_punctuation", "message": "Prompt looks like sentence prose."})
    for tag in tags:
        if tag.count("_") >= 4 and not re.search(r"\([^)]+\)", tag):
            issues.append({"code": "pseudo_long_tag", "message": f"Possible fabricated long tag: {tag}"})
    resolution = (review_payload or {}).get("resolution") if isinstance((review_payload or {}).get("resolution"), dict) else {}
    issues.extend(_conflict_issues(tags, user_prompt=user_prompt, resolution=resolution))
    issues.extend(_locked_prompt_intent_issues(review_payload, tags))
    issues.extend(_missing_intent_issues(user_prompt, tags))

    fixed_tags = tags
    changes = []
    if mode != "score_only" and tags:
        fixed_tags, changes = _apply_small_fixes(tags, issues, review_payload)
    final_prompt = _join_tags(fixed_tags) if fixed_tags else candidate
    remaining_issues = (
        _conflict_issues(fixed_tags, user_prompt=user_prompt, resolution=resolution)
        + _missing_intent_issues(user_prompt, fixed_tags)
        if fixed_tags else issues
    )
    severe_codes = {"empty_prompt", "contains_chinese", "not_comma_tags", "pseudo_long_tag"}
    severe = any((issue.get("code") if isinstance(issue, dict) else issue) in severe_codes for issue in issues)
    base = 95
    base -= 24 * len([issue for issue in issues if (issue.get("code") if isinstance(issue, dict) else issue) in severe_codes])
    base -= 10 * len([issue for issue in issues if (issue.get("code") if isinstance(issue, dict) else issue) not in severe_codes])
    if changes:
        base = max(base, 78 if not severe else base)
    if remaining_issues:
        base -= 8 * len(remaining_issues)
    score = max(0, min(100, int(base)))
    if severe and not changes:
        state = "reject"
    elif changes:
        state = "fixed"
    elif issues:
        state = "warn"
    else:
        state = "pass"
    return {
        "state": state,
        "score": score,
        "intent_alignment": score,
        "tag_validity": 55 if severe else 95,
        "conflict_check": 100 if not remaining_issues else max(40, 100 - len(remaining_issues) * 20),
        "subject_integrity": 92,
        "safety_policy": 92,
        "prompt_readiness": score,
        "issues": remaining_issues if changes else issues,
        "changes": changes,
        "final_prompt": final_prompt,
        "needs_user_confirmation": state in {"warn", "fixed"},
        "hard_block_reason": "prompt_structure_unrecoverable" if state == "reject" else "",
        "source": "deterministic",
    }


def _normalize_review(review, fallback_payload):
    candidate = str((fallback_payload or {}).get("candidate_prompt") or "").strip()
    if not isinstance(review, dict):
        review = {}
    state = str(review.get("state") or "").strip().lower()
    state = REVIEW_STATE_ALIASES.get(state, state)
    if state not in REVIEW_STATES:
        state = "warn" if review else "error"
    score = _review_numeric_score(review.get("score", 0), 0)
    final_prompt = str(review.get("final_prompt") or candidate).strip()
    template_slot_picks = _sanitize_template_slot_picks(review.get("template_slot_picks"), fallback_payload)
    return {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "state": state,
        "score": max(0, min(100, score)),
        "intent_alignment": _review_numeric_score(review.get("intent_alignment", score), score),
        "tag_validity": _review_numeric_score(review.get("tag_validity", score), score),
        "conflict_check": _review_numeric_score(review.get("conflict_check", score), score),
        "subject_integrity": _review_numeric_score(review.get("subject_integrity", score), score),
        "safety_policy": _review_numeric_score(review.get("safety_policy", score), score),
        "prompt_readiness": _review_numeric_score(review.get("prompt_readiness", score), score),
        "issues": review.get("issues") if isinstance(review.get("issues"), list) else [],
        "changes": review.get("changes") if isinstance(review.get("changes"), list) else [],
        "final_prompt": final_prompt,
        "template_slot_picks": template_slot_picks,
        "needs_user_confirmation": bool(review.get("needs_user_confirmation", state in {"warn", "fixed"})),
        "hard_block_reason": str(review.get("hard_block_reason") or "").strip(),
        "warn_only": bool(review.get("warn_only", False)),
        "source": str(review.get("source") or "llm").strip(),
    }


def _coerce_review_state(review, issue_code="review_state_invalid"):
    if not isinstance(review, dict):
        review = {}
    raw_state = review.get("state")
    state = raw_state.strip().lower() if isinstance(raw_state, str) else ""
    alias_state = REVIEW_STATE_ALIASES.get(state)
    if alias_state:
        coerced = dict(review)
        coerced["state"] = alias_state
        return coerced, alias_state, None
    if state in REVIEW_STATES:
        return review, state, None
    if not review:
        return review, "error", None
    issue = {
        "code": issue_code,
        "message": "Review state was not a supported string; treating this review as degraded output.",
        "state_type": type(raw_state).__name__,
    }
    preview = repr(raw_state).strip()
    if preview:
        issue["state_preview"] = preview[:160]
    coerced = dict(review)
    issues = list(coerced.get("issues") or []) if isinstance(coerced.get("issues"), list) else []
    issues.append(issue)
    coerced["issues"] = issues
    coerced["state"] = "warn"
    coerced["needs_user_confirmation"] = True
    return coerced, "warn", issue


def _review_numeric_score(value, fallback=0):
    if isinstance(value, bool):
        return 100 if value else 0
    if isinstance(value, (int, float)):
        if value != value:
            return int(fallback or 0)
        return max(0, min(100, int(round(float(value)))))
    text = str(value if value is not None else "").strip().lower()
    if not text:
        return max(0, min(100, int(fallback or 0)))
    aliases = {
        "excellent": 95,
        "perfect": 95,
        "very high": 92,
        "high": 85,
        "good": 80,
        "ok": 70,
        "okay": 70,
        "medium": 60,
        "moderate": 60,
        "fair": 55,
        "warn": 45,
        "warning": 45,
        "low": 25,
        "poor": 20,
        "bad": 10,
        "none": 0,
        "zero": 0,
        "pass": 90,
        "fixed": 85,
        "reject": 0,
    }
    if text in aliases:
        return aliases[text]
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if match:
        try:
            return max(0, min(100, int(round(float(match.group(0))))))
        except Exception:
            pass
    return max(0, min(100, int(fallback or 0)))


def _issue_text(issue):
    if isinstance(issue, dict):
        return " ".join(str(issue.get(key) or "") for key in ("code", "message", "reason", "tag")).lower()
    return str(issue or "").lower()


def _is_soft_copyright_redundancy_issue(issue):
    text = _issue_text(issue)
    if not text:
        return False
    has_copyright_marker = any(term in text for term in ("copyright", "genshin_impact", "copyright tag", "source tag", "series tag"))
    has_soft_marker = any(term in text for term in ("redundant", "generic", "could be", "valid", "already", "specific character"))
    return has_copyright_marker and has_soft_marker


def _llm_reject_is_soft_copyright_redundancy(review):
    issues = review.get("issues") if isinstance(review, dict) and isinstance(review.get("issues"), list) else []
    if not issues:
        return False
    return all(_is_soft_copyright_redundancy_issue(issue) for issue in issues)


def _is_nonblocking_tag_style_issue(issue):
    text = _issue_text(issue)
    if not text:
        return False
    has_style_marker = any(term in text for term in (
        "not standard", "non-standard", "nonstandard", "standard danbooru",
        "danbooru style", "danbooru-style", "preferred synonym", "prefer synonym",
        "uncommon tag", "tag style",
    ))
    if not has_style_marker:
        return False
    hard_markers = (
        "wrong character", "unknown character", "unresolved", "unsafe",
        "forbidden", "policy", "minor", "child",
    )
    return not any(term in text for term in hard_markers)


def _llm_reject_is_nonblocking_tag_style(review):
    issues = review.get("issues") if isinstance(review, dict) and isinstance(review.get("issues"), list) else []
    if not issues:
        return False
    return all(_is_nonblocking_tag_style_issue(issue) or _is_soft_copyright_redundancy_issue(issue) for issue in issues)


def _is_subject_count_false_positive(issue):
    text = _issue_text(issue)
    if not text:
        return False
    markers = ("subject_count", "subject count", "count missing", "missing count", "1girl", "1boy", "2girls", "2boys")
    return any(marker in text for marker in markers)


def _is_redundant_subject_count_change(change, tags):
    if isinstance(change, dict):
        tag = str(change.get("tag") or "").strip()
        if tag in COUNT_TAGS and tag in tags and _is_subject_count_false_positive(change):
            return True
    text = _issue_text(change)
    if not text:
        return False
    if not any(tag in text for tag in tags if tag in COUNT_TAGS):
        return False
    return _is_subject_count_false_positive(change) and any(marker in text for marker in ("add", "added", "restore", "restored"))


def _sanitize_subject_count_review(normalized, candidate):
    if str((normalized or {}).get("source") or "").startswith("deterministic"):
        return normalized
    tags = _tag_list(normalized.get("final_prompt") or candidate)
    if not _has_explicit_subject_count(tags):
        return normalized
    issues = list(normalized.get("issues") or [])
    changes = list(normalized.get("changes") or [])
    filtered_issues = [item for item in issues if not _is_subject_count_false_positive(item)]
    filtered_changes = [item for item in changes if not _is_redundant_subject_count_change(item, tags)]
    if len(filtered_issues) == len(issues) and len(filtered_changes) == len(changes):
        return normalized
    normalized = dict(normalized)
    normalized["issues"] = filtered_issues
    normalized["changes"] = filtered_changes
    if not filtered_issues and not filtered_changes and normalized.get("state") == "warn":
        normalized["state"] = "pass"
        normalized["score"] = max(int(normalized.get("score") or 0), 90)
        normalized["intent_alignment"] = max(int(normalized.get("intent_alignment") or 0), 90)
        normalized["tag_validity"] = max(int(normalized.get("tag_validity") or 0), 90)
        normalized["conflict_check"] = max(int(normalized.get("conflict_check") or 0), 90)
        normalized["subject_integrity"] = max(int(normalized.get("subject_integrity") or 0), 90)
        normalized["prompt_readiness"] = max(int(normalized.get("prompt_readiness") or 0), 90)
        normalized["needs_user_confirmation"] = False
    return normalized


def _has_inline_prompt_control(text):
    return bool(re.search(
        r"\b(?:aspect[_\s-]*ratio|ratio|resolution[_\s-]*scale|scale|steps?|cfg(?:_scale)?|guidance(?:_scale)?|seed|width|height)\s*[:=：]",
        str(text or ""),
        re.I,
    ))


def _llm_prompt_contract_guard(candidate_prompt, final_prompt, review_payload):
    candidate_tags = _tag_list(candidate_prompt)
    final_tags = _tag_list(final_prompt)
    final_set = set(final_tags)
    issues = []
    if not final_tags:
        issues.append("final prompt is empty")
        return issues
    if _contains_chinese(final_prompt):
        issues.append("final prompt contains Chinese text")
    if "," not in str(final_prompt or "") or len(final_tags) < 3:
        issues.append("final prompt is not a compact comma-separated tag list")
    if re.search(r"[。！？.!?]\s*$", str(final_prompt or "")):
        issues.append("final prompt looks like sentence prose")
    if _has_inline_prompt_control(final_prompt):
        issues.append("generation controls leaked into final prompt")
    for tag in final_tags:
        if tag in REVIEW_NEGATIVE_IN_POSITIVE:
            issues.append(f"negative tag leaked into positive prompt: {tag}")
        if tag.count("_") >= 5 and not re.search(r"\([^)]+\)", tag):
            issues.append(f"possible fabricated long tag: {tag}")
    resolution = (review_payload or {}).get("resolution") if isinstance((review_payload or {}).get("resolution"), dict) else {}
    expected_count_tags = _expected_subject_count_tags(candidate_tags or final_tags, user_prompt=str((review_payload or {}).get("user_request") or ""), resolution=resolution)
    for tag in expected_count_tags or []:
        if tag not in final_set:
            issues.append(f"missing expected subject count tag: {tag}")
    if _has_explicit_subject_count(candidate_tags) and not _has_explicit_subject_count(final_tags):
        issues.append("explicit subject count was dropped")
    for tag in _explicit_subject_count_tags(candidate_tags):
        if tag not in final_set:
            issues.append(f"explicit subject count changed or was dropped: {tag}")
    candidate_count_set = set(_explicit_subject_count_tags(candidate_tags))
    if candidate_count_set:
        changed_counts = sorted(set(_explicit_subject_count_tags(final_tags)).difference(candidate_count_set))
        if changed_counts:
            issues.append(f"explicit subject count changed: {', '.join(changed_counts)}")
    for tag in _review_prompt_intent(review_payload).get("locked_tags") or []:
        if tag not in final_set:
            issues.append(f"missing locked prompt_intent tag: {tag}")
    character_tags, copyright_tags = _resolved_tags(resolution)
    for tag in character_tags + copyright_tags:
        if tag and tag not in final_set:
            issues.append(f"missing resolved identity tag: {tag}")
    user_prompt = str((review_payload or {}).get("user_request") or "")
    if ("transparent_background" in set(candidate_tags) or _text_has_any(user_prompt, TRANSPARENT_BACKGROUND_INTENT_PATTERNS)) and "transparent_background" not in final_set:
        issues.append("transparent background hard lock was dropped")
    for tag, _reason in _intent_restoration_tags(user_prompt, candidate_tags or final_tags):
        if tag not in final_set:
            issues.append(f"missing explicit intent tag: {tag}")
    return issues[:12]


def _is_safe_llm_small_fix(candidate_prompt, final_prompt, review_payload):
    candidate_tags = _tag_list(candidate_prompt)
    final_tags = _tag_list(final_prompt)
    if not candidate_tags or not final_tags or final_tags == candidate_tags:
        return False, final_prompt, []
    if _contains_chinese(final_prompt):
        return False, final_prompt, ["final prompt contains Chinese text"]
    if re.search(r"[。！？；]\s*$", str(final_prompt or "")):
        return False, final_prompt, ["final prompt looks like sentence prose"]
    candidate_set = set(candidate_tags)
    final_set = set(final_tags)
    added = [tag for tag in final_tags if tag not in candidate_set]
    removed = [tag for tag in candidate_tags if tag not in final_set]
    if len(added) > 10 or len(removed) > 4:
        return False, final_prompt, ["llm edit is too large to accept safely"]
    if set(added).intersection(REVIEW_LLM_ADULT_ADDITION_TAGS):
        return False, final_prompt, ["llm edit added adult tags outside the local allowlist"]
    if _has_explicit_subject_count(candidate_tags) and not _has_explicit_subject_count(final_tags):
        return False, final_prompt, ["explicit subject count was dropped"]
    candidate_count_set = set(_explicit_subject_count_tags(candidate_tags))
    final_count_set = set(_explicit_subject_count_tags(final_tags))
    if candidate_count_set and not candidate_count_set.issubset(final_count_set):
        return False, final_prompt, ["explicit subject count changed or was dropped"]
    if candidate_count_set and final_count_set.difference(candidate_count_set):
        return False, final_prompt, ["explicit subject count changed"]
    user_prompt = str((review_payload or {}).get("user_request") or "")
    if ("transparent_background" in candidate_set or _text_has_any(user_prompt, TRANSPARENT_BACKGROUND_INTENT_PATTERNS)) and "transparent_background" not in final_set:
        return False, final_prompt, ["transparent background hard lock was dropped"]
    resolution = (review_payload or {}).get("resolution") if isinstance((review_payload or {}).get("resolution"), dict) else {}
    character_tags, copyright_tags = _resolved_tags(resolution)
    for tag in character_tags + copyright_tags:
        if tag and tag not in final_set:
            return False, final_prompt, [f"missing resolved identity tag: {tag}"]
    for tag in candidate_tags:
        if re.search(r"\([^)]+\)", tag) and tag not in final_set:
            return False, final_prompt, [f"missing canonical identity tag: {tag}"]
    for tag in final_tags:
        if tag.count("_") >= 5 and not re.search(r"\([^)]+\)", tag):
            return False, final_prompt, [f"possible fabricated long tag: {tag}"]
    guard_issues = _llm_prompt_contract_guard(candidate_prompt, final_prompt, review_payload)
    if guard_issues:
        return False, final_prompt, guard_issues
    return True, _join_tags(final_tags), []


def _review_threshold(review_payload):
    try:
        return max(0, min(100, int(float((review_payload or {}).get("threshold", 75)))))
    except Exception:
        return 75


def _review_readiness_score(normalized):
    values = []
    for key in ("score", "intent_alignment", "prompt_readiness"):
        values.append(_review_numeric_score(normalized.get(key, 0), 0))
    return min(values) if values else 0


def _escalate_unfixed_low_score(normalized, review_payload, final_prompt, candidate):
    if normalized.get("state") in {"reject", "disabled", "skipped", "error"}:
        return normalized
    if str(final_prompt or "").strip() != str(candidate or "").strip():
        return normalized
    threshold = _review_threshold(review_payload)
    readiness = _review_readiness_score(normalized)
    if readiness >= threshold:
        return normalized
    normalized = dict(normalized)
    normalized["state"] = "warn"
    normalized["needs_user_confirmation"] = True
    normalized["warn_only"] = True
    normalized["issues"] = list(normalized.get("issues") or []) + [{
        "code": "review_below_threshold_warn_only",
        "message": f"Review readiness {readiness}/100 is below threshold {threshold}/100, but no hard block was found; keeping this as a warning.",
    }]
    normalized["final_prompt"] = candidate
    return normalized


def _downgrade_unaccepted_llm_fix_when_deterministic_ok(normalized, deterministic, candidate):
    if not isinstance(deterministic, dict) or deterministic.get("state") not in {"pass", "warn", "fixed"}:
        return normalized
    if str(normalized.get("final_prompt") or "").strip() != str(candidate or "").strip():
        return normalized
    text_parts = []
    for key in ("issues", "changes"):
        for item in normalized.get(key) or []:
            text_parts.append(_issue_text(item))
    text = " ".join(text_parts)
    if not text:
        return normalized
    if not any(term in text for term in ("missing", "conflict", "contradict", "replace", "remove", "added", "removed", "缺", "冲突")):
        return normalized
    next_review = dict(deterministic, source="deterministic_after_unaccepted_llm_fix")
    next_review["issues"] = list(deterministic.get("issues") or []) + [{
        "code": "llm_claimed_fix_without_prompt_downgraded",
        "message": "The optional LLM review claimed prompt fixes but did not return an accepted modified final_prompt; using deterministic review instead.",
        "llm_issues": list(normalized.get("issues") or [])[:4],
    }]
    next_review["needs_user_confirmation"] = deterministic.get("state") in {"warn", "fixed"}
    return next_review


def _review_claims_unfixed_blocking_issue(normalized, final_prompt, candidate):
    if normalized.get("state") not in {"warn", "fixed"}:
        return False
    if str(final_prompt or "").strip() != str(candidate or "").strip():
        return False
    text_parts = []
    for key in ("issues", "changes"):
        for item in normalized.get(key) or []:
            if isinstance(item, dict):
                text_parts.append(" ".join(str(item.get(part) or "") for part in ("code", "message", "reason", "tag", "type")))
            else:
                text_parts.append(str(item or ""))
    text = " ".join(text_parts).lower()
    if not text:
        return False
    return any(term in text for term in (
        "conflict", "contradict", "inconsistent", "missing", "replace", "replaced",
        "remove", "removed", "not align", "misalign", "冲突", "矛盾", "缺少", "替换", "删除",
    ))


def _escalate_unfixed_claimed_issue(normalized, final_prompt, candidate):
    if not _review_claims_unfixed_blocking_issue(normalized, final_prompt, candidate):
        return normalized
    normalized = dict(normalized)
    normalized["state"] = "warn"
    normalized["needs_user_confirmation"] = True
    normalized["warn_only"] = True
    normalized["issues"] = list(normalized.get("issues") or []) + [{
        "code": "review_claimed_fix_without_final_prompt_change_warn_only",
        "message": "Review reported prompt issues or changes, but did not return an accepted modified final_prompt; keeping this as a warning.",
    }]
    normalized["final_prompt"] = candidate
    return normalized


def apply_review_result(candidate_prompt, review, review_payload):
    candidate = str(candidate_prompt or "").strip()
    normalized = _normalize_review(review, review_payload)
    normalized = _sanitize_subject_count_review(normalized, candidate)
    slot_prompt, slot_changes = _compose_prompt_from_template_slot_picks(
        candidate,
        normalized.get("template_slot_picks"),
        review_payload,
    )
    if slot_changes and normalized.get("state") in {"pass", "warn", "fixed"}:
        slot_guard_issues = _llm_prompt_contract_guard(candidate, slot_prompt, review_payload)
        if not slot_guard_issues:
            normalized["final_prompt"] = slot_prompt
            normalized["changes"] = list(normalized.get("changes") or []) + slot_changes
            normalized["source"] = str(normalized.get("source") or "llm").strip() or "llm"
            if normalized.get("state") in {"pass", "warn"}:
                normalized["state"] = "fixed"
            normalized["needs_user_confirmation"] = False
        else:
            normalized["issues"] = list(normalized.get("issues") or []) + [{
                "code": "template_slot_picks_contract_guard_failed",
                "message": "Template slot picks drifted away from locked intent or prompt contract; falling back to the original candidate prompt.",
                "guard_issues": slot_guard_issues[:6],
            }]
            normalized["needs_user_confirmation"] = True
    final_prompt = str(normalized.get("final_prompt") or candidate).strip()
    if normalized["state"] in {"pass", "warn"}:
        safe_fix, canonical_final, guard_issues = _is_safe_llm_small_fix(candidate, final_prompt, review_payload)
        if safe_fix:
            final_prompt = canonical_final
            normalized["state"] = "fixed"
            normalized["changes"] = list(normalized.get("changes") or []) + [{
                "type": "accept_llm_final_prompt",
                "reason": "review supplied a bounded final_prompt that restores explicit user intent",
            }]
            normalized["needs_user_confirmation"] = False
            normalized["score"] = max(int(normalized.get("score") or 0), 88)
            normalized["prompt_readiness"] = max(int(normalized.get("prompt_readiness") or 0), 88)
        else:
            if str(final_prompt or "").strip() != str(candidate or "").strip():
                normalized["issues"] = list(normalized.get("issues") or []) + [{
                    "code": "llm_final_prompt_contract_guard_failed",
                    "message": "Optional LLM final_prompt drifted away from the local prompt contract; keeping the original candidate prompt.",
                    "guard_issues": guard_issues[:6],
                }]
            final_prompt = candidate
    elif normalized["state"] == "reject":
        final_prompt = candidate
    elif normalized["state"] == "fixed":
        if str(normalized.get("source") or "").startswith("deterministic"):
            final_prompt = _join_tags(_tag_list(final_prompt)) or candidate
            normalized["needs_user_confirmation"] = False
        else:
            safe_fix, canonical_final, guard_issues = _is_safe_llm_small_fix(candidate, final_prompt, review_payload)
            if safe_fix:
                final_prompt = canonical_final
            else:
                if str(final_prompt or "").strip() != str(candidate or "").strip():
                    normalized["issues"] = list(normalized.get("issues") or []) + [{
                        "code": "llm_fixed_prompt_contract_guard_failed",
                        "message": "Optional LLM fixed prompt drifted away from the local prompt contract; falling back to the original candidate prompt.",
                        "guard_issues": guard_issues[:6],
                    }]
                final_prompt = candidate
    should_post_review_repair = (
        normalized["state"] == "fixed"
        and str(normalized.get("source") or "").startswith("deterministic")
        and str((review_payload or {}).get("mode") or "").strip().lower() == "repair_and_enrich"
        and _bool((review_payload or {}).get("post_review_repair"), False)
    )
    if should_post_review_repair:
        deterministic_final = canvas_danbooru_preflight.repair_sdxl_named_character_prompt(
            final_prompt or candidate,
            (review_payload or {}).get("user_request") or "",
            prompt_intent=(review_payload or {}).get("prompt_intent"),
        )
        if deterministic_final and deterministic_final != final_prompt:
            final_prompt = deterministic_final
            normalized["state"] = "fixed"
            normalized["needs_user_confirmation"] = False
            normalized["changes"] = list(normalized.get("changes") or []) + [{
                "type": "deterministic_post_review_repair",
                "reason": "post-review preflight restored locked identity and story facets",
            }]
    if final_prompt and final_prompt != candidate:
        preflight = canvas_danbooru_preflight.prompt_preflight_check({
            "prompt": final_prompt,
            "user_prompt": (review_payload or {}).get("user_request") or "",
            "prompt_target": (review_payload or {}).get("target") or {},
            "target_key": ((review_payload or {}).get("target") or {}).get("key") or "",
        })
        if preflight.get("state") == "block":
            final_tags = set(_tag_list(final_prompt))
            checks = preflight.get("checks") if isinstance(preflight.get("checks"), list) else []
            block_codes = {
                str(item.get("code") or "")
                for item in checks
                if isinstance(item, dict) and item.get("level") == "block"
            }
            subject_count_ok = _has_explicit_subject_count(final_tags)
            ignorable_subject_count_block = block_codes == {"danbooru_subject_count_missing"} and subject_count_ok
            if ignorable_subject_count_block:
                preflight = dict(preflight, state="warning", summary="Prompt preflight accepted multi-subject count after review.")
            else:
                normalized["state"] = "warn"
                normalized["issues"] = list(normalized.get("issues") or []) + [{
                    "code": "post_review_preflight_block",
                    "message": preflight.get("summary") or "Reviewed prompt was blocked by deterministic preflight.",
                }]
                final_prompt = candidate
        normalized["post_preflight"] = preflight
    normalized = _escalate_unfixed_claimed_issue(normalized, final_prompt, candidate)
    normalized = _escalate_unfixed_low_score(normalized, review_payload, final_prompt, candidate)
    final_prompt = _filter_contextual_tags(final_prompt, review_payload)
    normalized["original_prompt"] = candidate
    normalized["final_prompt"] = final_prompt
    changes = list(normalized.get("changes") or [])
    normalized["fixes"] = [
        item for item in changes
        if isinstance(item, dict) and str(item.get("type") or "").strip().lower() != "enrich"
    ]
    normalized["enrichments"] = [
        item for item in changes
        if isinstance(item, dict) and str(item.get("type") or "").strip().lower() == "enrich"
    ]
    if normalized.get("state") == "warn" and not normalized.get("hard_block_reason"):
        normalized["warn_only"] = True
    if normalized.get("state") == "reject" and not normalized.get("hard_block_reason"):
        normalized["hard_block_reason"] = "review_rejected_after_deterministic_check"
    association_context = _compact_association_review_context(_association_review_context(review_payload))
    if association_context:
        normalized["association_context"] = association_context
    return normalized


def review_danbooru_prompt(review_payload, llm_fn=None):
    candidate = str((review_payload or {}).get("candidate_prompt") or "").strip()
    target = (review_payload or {}).get("target") if isinstance((review_payload or {}).get("target"), dict) else {}
    if not candidate or not _is_danbooru_target(target):
        return apply_review_result(candidate, {"state": "skipped", "score": 100, "final_prompt": candidate, "source": "skipped"}, review_payload)
    deterministic = deterministic_review(review_payload)
    deterministic, deterministic_state, _deterministic_state_issue = _coerce_review_state(
        deterministic,
        issue_code="deterministic_state_invalid",
    )
    review = {}
    if callable(llm_fn) and _bool((review_payload or {}).get("llm_enabled"), False):
        try:
            raw = llm_fn(build_review_messages(review_payload), review_payload)
            if isinstance(raw, str) and raw.strip().lower().startswith(("error:", "error during inference")):
                raise RuntimeError(raw.strip()[:500])
            review = parse_review_response(raw)
            if review:
                review["source"] = review.get("source") or "llm"
            else:
                review = {
                    "state": "warn",
                    "score": 70,
                    "issues": [{"code": "llm_review_parse_failed", "message": "Review model did not return parseable JSON."}],
                    "final_prompt": candidate,
                    "source": "llm_parse_failed",
                }
        except Exception as exc:
            logger.warning("Danbooru prompt LLM review failed: %s", exc)
            review = {
                "state": "warn",
                "score": 70,
                "issues": [{"code": "llm_review_failed", "message": str(exc)}],
                "final_prompt": candidate,
                "source": "llm_error",
            }
    if not review:
        review = deterministic
    elif str(review.get("source") or "") in {"llm_parse_failed", "llm_error"}:
        review = dict(deterministic, source="deterministic_after_llm_error")
    review, review_state, review_state_issue = _coerce_review_state(review)
    if review_state_issue and str(review.get("source") or "").startswith("llm"):
        review = dict(deterministic, source="deterministic_after_invalid_llm_state")
        review["issues"] = list(deterministic.get("issues") or []) + [{
            "code": "llm_invalid_state_downgraded",
            "message": "The optional LLM review returned an invalid review.state payload; using deterministic review result instead.",
            "llm_state_issue": review_state_issue,
        }]
        review["needs_user_confirmation"] = deterministic_state in {"warn", "fixed"}
        review_state = deterministic_state
    elif (
        review_state == "reject"
        and _review_readiness_score(_normalize_review(review, review_payload)) >= min(75, _review_threshold(review_payload))
        and _llm_reject_is_soft_copyright_redundancy(review)
        and deterministic_state in {"pass", "warn", "fixed"}
    ):
        review_issues = review.get("issues") if isinstance(review.get("issues"), list) else []
        review = dict(deterministic, source="deterministic_after_soft_copyright_overreject")
        review["issues"] = list(deterministic.get("issues") or []) + [{
            "code": "llm_soft_copyright_redundancy_downgraded",
            "message": "The optional LLM review treated a valid copyright tag as redundant; keeping canonical character/copyright tags.",
            "llm_issues": review_issues[:4],
        }]
        review["needs_user_confirmation"] = deterministic_state in {"warn", "fixed"}
        review_state = deterministic_state
    elif (
        review_state == "reject"
        and _review_readiness_score(_normalize_review(review, review_payload)) >= min(75, _review_threshold(review_payload))
        and _llm_reject_is_nonblocking_tag_style(review)
        and deterministic_state in {"pass", "warn", "fixed"}
    ):
        review_issues = review.get("issues") if isinstance(review.get("issues"), list) else []
        review = dict(deterministic, source="deterministic_after_tag_style_overreject")
        review["issues"] = list(deterministic.get("issues") or []) + [{
            "code": "llm_tag_style_overreject_downgraded",
            "message": "The optional LLM review treated tag style/synonym preference as blocking; keeping the local deterministic prompt.",
            "llm_issues": review_issues[:4],
        }]
        review["needs_user_confirmation"] = deterministic_state in {"warn", "fixed"}
        review_state = deterministic_state
    elif review_state == "reject" and deterministic_state in {"pass", "warn", "fixed"}:
        review_issues = review.get("issues") if isinstance(review.get("issues"), list) else []
        review = dict(deterministic, source="deterministic_after_llm_overreject")
        review["issues"] = list(deterministic.get("issues") or []) + [{
            "code": "llm_reject_downgraded",
            "message": "The optional LLM review rejected a prompt that passed deterministic checks; using deterministic review result instead.",
            "llm_issues": review_issues[:4],
        }]
        review["needs_user_confirmation"] = deterministic_state in {"warn", "fixed"}
        review_state = deterministic_state
    elif deterministic_state in {"fixed", "reject"} and review_state in {"pass", "warn"}:
        normalized_review = _normalize_review(review, review_payload)
        if deterministic_state == "reject" or _review_readiness_score(normalized_review) >= _review_threshold(review_payload):
            review = deterministic
            review_state = deterministic_state
    review, review_state, _review_state_issue = _coerce_review_state(review)
    result = apply_review_result(candidate, review, review_payload)
    if result.get("state") == "fixed" and result.get("final_prompt") == candidate:
        result["state"] = "warn"
    if result.get("state") == "reject":
        normalized_review = _normalize_review(review, review_payload)
        downgraded = _downgrade_unaccepted_llm_fix_when_deterministic_ok(normalized_review, deterministic, candidate)
        if downgraded is not normalized_review:
            result = apply_review_result(candidate, downgraded, review_payload)
    return result


def should_review_action(action, payload, params):
    data = params or {}
    if not (_bool(data.get("enable_prompt_review"), False) or _bool(data.get("enable_danbooru_review"), False)):
        return False
    if str(data.get("danbooru_review_mode") or "small_fix").strip().lower() == "off":
        return False
    name = str((action or {}).get("action") or (action or {}).get("type") or "").strip().lower().replace("-", "_")
    if name not in IMAGE_ACTIONS:
        return False
    target_key = canvas_danbooru_preflight.payload_text_to_image_target_key(payload if isinstance(payload, dict) else {})
    return target_key in {"sdxl_danbooru", "danbooru", "illustrious", "noob", "pony", "animagine"} or target_key.startswith("sdxl")


def review_action(action, payload, params, user_prompt, llm_fn=None):
    prompt = _action_prompt(action)
    review_payload = build_review_payload(action if isinstance(action, dict) else {}, payload if isinstance(payload, dict) else {}, params if isinstance(params, dict) else {}, user_prompt, prompt)
    result = review_danbooru_prompt(review_payload, llm_fn=llm_fn)
    item = dict(action or {})
    final_prompt = _join_tags(_tag_list(result.get("final_prompt") or prompt)) or str(result.get("final_prompt") or prompt).strip()
    if final_prompt and final_prompt != prompt and result.get("state") == "fixed":
        for key in ("prompt", "recommended_prompt", "final_prompt"):
            item[key] = final_prompt
        item["_backend_repaired"] = "true"
        item["_canonical_locked"] = "true"
    item["prompt_review"] = {
        key: result.get(key)
        for key in (
            "schema_version", "state", "score", "intent_alignment", "tag_validity",
            "conflict_check", "subject_integrity", "safety_policy", "prompt_readiness",
            "issues", "changes", "original_prompt", "final_prompt", "needs_user_confirmation",
            "source", "fixes", "enrichments", "warn_only", "hard_block_reason",
            "association_context",
        )
    }
    if result.get("state") == "reject":
        item["_prompt_review_rejected"] = "true"
    return item
