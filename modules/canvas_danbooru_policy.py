import re


FORBIDDEN_POSITIVE_TAGS = {
    "clean_background",
    "halo",
}


SUBSTITUTE_CHARACTER_PROMPT_PATTERNS = (
    r"\bresembling\b",
    r"\binspired[_\s-]+by\b",
    r"\bbased[_\s-]+on\b",
    r"\blookalike\b",
    r"\btatarin\b",
    r"\bnarucare\b",
)


NAMED_CHARACTER_FORBIDDEN_TAGS = {
    "character",
    "female",
    "male",
    "person",
    "human",
    "humans",
    "no_humans",
    "ganyu",
    "genshin_impact_character",
}


ASSISTANT_PERSONA_VISUAL_TAGS = {
    "catgirl",
    "cat_ears",
    "animal_ears",
    "wolf_ears",
    "wolf_tail",
    "fox_ears",
    "fox_tail",
    "black_hair",
    "twintails",
    "twin_tails",
    "green_eyes",
    "streaked_hair",
    "white_streaked_hair",
    "ear_fluff",
    "white_fur",
    "white_fur_patches_on_ears",
    "white_fur_patch_on_ears",
    "fur_horn",
    "tail",
}


REPAIR_TAG_ALIASES = {
    "first-person_perspective": "pov",
    "first_person_perspective": "pov",
    "first-person_view": "pov",
    "first_person_view": "pov",
    "point_of_view": "pov",
    "office_setting": "office",
    "professional_attire": "formal",
    "formal_dress": "dress",
    "high_quality": "best_quality",
    "genshin_impact_character": "genshin_impact",
    "hatsune_miku_character": "hatsune_miku",
    "large_emerald_eyes": "green_eyes",
    "emerald_eyes": "green_eyes",
    "bust_portrait": "upper_body",
    "document": "paper",
    "documents": "paper",
    "room": "bedroom",
}


NAMED_CHARACTER_SAFE_SOURCE_TAGS = {
    "upper_body",
    "portrait",
    "cowboy_shot",
    "close-up",
    "looking_at_viewer",
    "facing_viewer",
    "smile",
    "closed_mouth_smile",
    "serious",
    "serious_expression",
    "sitting",
    "standing",
    "outdoors",
    "indoors",
    "forest",
    "garden",
    "grass",
    "flowers",
    "office",
    "desk",
    "documents",
    "stage",
    "microphone",
    "spotlight",
    "night",
    "sunlight",
    "soft_lighting",
    "cinematic_lighting",
    "depth_of_field",
    "blurry_background",
    "simple_background",
}


USER_PROMPT_TAG_RULES = (
    (r"\u534a\u8eab|\u534a\u8eab\u7167|\u4e0a\u534a\u8eab|\bbust\b|\bupper[-_\s]?body\b", ("upper_body",)),
    (r"\u5168\u8eab|\bfull[-_\s]?body\b", ("full_body",)),
    (r"\u8096\u50cf|\u5934\u50cf|\bportrait\b", ("portrait",)),
    (r"\u770b\u7740\u955c\u5934|\u6b63\u9762|\blooking at viewer\b|\bfacing viewer\b", ("looking_at_viewer",)),
    (r"\u5fae\u7b11|\u7b11|\bsmile\b", ("smile",)),
    (r"\u4e25\u8083|\u8ba4\u771f|\bserious\b", ("serious",)),
    (r"\u68ee\u6797|\u6811\u6797|\bforest\b", ("forest", "outdoors")),
    (r"\u82b1\u56ed|\bgarden\b", ("garden", "flowers", "outdoors")),
    (r"\u8349\u5730|\u8349\u576a|\bmeadow\b|\bgrass\b", ("grass", "outdoors")),
    (r"\u529e\u516c\u5ba4|\boffice\b", ("office", "indoors")),
    (r"\u6587\u4ef6|\bdocument\b|\bdocuments\b", ("documents",)),
    (r"\u821e\u53f0|\bstage\b", ("stage", "spotlight")),
    (r"\u591c|\u591c\u665a|\bnight\b", ("night",)),
    (r"\u67d4\u548c\u5149|\u67d4\u5149|\bsoft lighting\b", ("soft_lighting",)),
    (r"\u7535\u5f71\u611f|\bcinematic\b", ("cinematic_lighting",)),
)


NAMED_CHARACTER_DEFAULT_PROMPT_TAGS = ()
QUALITY_TAGS = ("masterpiece", "best_quality")


def clean_prompt_tag_name(tag):
    clean = str(tag or "").strip().lower()
    clean = clean.strip("`\"'")
    clean = clean.replace("\\(", "(").replace("\\)", ")")
    while clean.startswith("(") and clean.endswith(")") and ":" not in clean:
        clean = clean[1:-1].strip()
    clean = re.sub(r"^\(([^:()]+):[0-9.]+\)$", r"\1", clean)
    clean = re.sub(r"\s+", "_", clean)
    clean = re.sub(r"_+", "_", clean).strip("_")
    return clean


def is_forbidden_positive_tag(tag):
    clean = clean_prompt_tag_name(tag)
    return clean in FORBIDDEN_POSITIVE_TAGS or clean.startswith("halo")


def has_substitute_character_language(text):
    source = str(text or "").lower()
    return any(re.search(pattern, source, re.I) for pattern in SUBSTITUTE_CHARACTER_PROMPT_PATTERNS)


def bare_character_tags(resolved_tags):
    output = set()
    for tag in resolved_tags or []:
        clean = clean_prompt_tag_name(tag)
        if not clean:
            continue
        first = re.split(r"[_()]+", clean, maxsplit=1)[0]
        if len(first) >= 3:
            output.add(first)
        flattened = re.sub(r"[()]+", "", clean)
        flattened = re.sub(r"_+", "_", flattened).strip("_")
        if flattened and flattened != clean:
            output.add(flattened)
    return output


def is_named_character_leak_tag(tag):
    clean = clean_prompt_tag_name(tag)
    if clean in ASSISTANT_PERSONA_VISUAL_TAGS:
        return True
    leak_fragments = (
        "cat_ear", "catgirl", "animal_ear", "wolf_ear", "wolf_tail",
        "fox_ear", "fox_tail", "twintail", "twin_tail", "ear_fluff",
        "white_fur",
    )
    return any(fragment in clean for fragment in leak_fragments)


def is_named_character_default_detail_tag(tag):
    clean = clean_prompt_tag_name(tag)
    if not clean:
        return False
    detail_fragments = (
        "hair", "eyes", "eye", "skin", "dress", "skirt", "shirt", "blouse",
        "outfit", "clothes", "clothing", "uniform", "sleeves", "sleeve",
        "boots", "shoes", "hat", "crown", "hair_ornament", "ornament",
        "ribbon", "bow", "bangs", "side_bangs", "twintails", "twin_tails",
    )
    return any(fragment in clean for fragment in detail_fragments)


def _append_unique(output, tags):
    for tag in tags or []:
        clean = REPAIR_TAG_ALIASES.get(clean_prompt_tag_name(tag), clean_prompt_tag_name(tag))
        if clean and clean not in output:
            output.append(clean)


def drop_redundant_copyright_tags(resolved_tags=None, copyright_tags=None):
    resolved = [
        REPAIR_TAG_ALIASES.get(clean_prompt_tag_name(tag), clean_prompt_tag_name(tag))
        for tag in (resolved_tags or [])
        if clean_prompt_tag_name(tag)
    ]
    copyright = [
        REPAIR_TAG_ALIASES.get(clean_prompt_tag_name(tag), clean_prompt_tag_name(tag))
        for tag in (copyright_tags or [])
        if clean_prompt_tag_name(tag)
    ]
    if not resolved or not copyright:
        return copyright
    scoped_copyright = set()
    for tag in resolved:
        match = re.search(r"_\(([^()]+)\)$", tag)
        if not match:
            return copyright
        scoped = REPAIR_TAG_ALIASES.get(clean_prompt_tag_name(match.group(1)), clean_prompt_tag_name(match.group(1)))
        if scoped:
            scoped_copyright.add(scoped)
    return [tag for tag in copyright if tag not in scoped_copyright]


def _user_prompt_tags(user_prompt):
    source = str(user_prompt or "").lower()
    output = []
    for pattern, tags in USER_PROMPT_TAG_RULES:
        if re.search(pattern, source, re.I):
            _append_unique(output, tags)
    return output


def _safe_source_tags_for_named_character(source_prompt):
    output = []
    for raw in str(source_prompt or "").split(","):
        clean = REPAIR_TAG_ALIASES.get(clean_prompt_tag_name(raw), clean_prompt_tag_name(raw))
        if not clean or clean in QUALITY_TAGS:
            continue
        if clean in NAMED_CHARACTER_SAFE_SOURCE_TAGS:
            _append_unique(output, [clean])
    return output


def build_named_character_prompt(user_prompt, source_prompt, resolved_tags=None, copyright_tags=None):
    resolved_tags = [clean_prompt_tag_name(tag) for tag in (resolved_tags or []) if clean_prompt_tag_name(tag)]
    copyright_tags = drop_redundant_copyright_tags(resolved_tags, copyright_tags)
    if not resolved_tags:
        return repair_tag_list(source_prompt, resolved_tags=resolved_tags, copyright_tags=copyright_tags)

    output = []
    _append_unique(output, ["solo"])
    _append_unique(output, resolved_tags)
    _append_unique(output, copyright_tags)

    explicit_tags = _user_prompt_tags(user_prompt)
    _append_unique(output, explicit_tags)

    if "upper_body" in output:
        output = [tag for tag in output if tag != "full_body"]

    source_tags = _safe_source_tags_for_named_character(source_prompt)
    if "upper_body" in output:
        source_tags = [tag for tag in source_tags if tag != "full_body"]
    _append_unique(output, source_tags)

    _append_unique(output, NAMED_CHARACTER_DEFAULT_PROMPT_TAGS)
    return ", ".join(output)


def repair_tag_list(source_prompt, resolved_tags=None, copyright_tags=None, unknown_tags=None, named_source_terms=None):
    source_prompt = str(source_prompt or "").strip()
    if not source_prompt:
        return source_prompt

    resolved_tags = [clean_prompt_tag_name(tag) for tag in (resolved_tags or []) if clean_prompt_tag_name(tag)]
    copyright_tags = [clean_prompt_tag_name(tag) for tag in (copyright_tags or []) if clean_prompt_tag_name(tag)]
    protected = []
    if resolved_tags:
        for tag in ["1girl", "solo"] + resolved_tags + copyright_tags:
            if tag and tag not in protected:
                protected.append(tag)

    remove_tags = set(FORBIDDEN_POSITIVE_TAGS)
    if resolved_tags:
        remove_tags.update(NAMED_CHARACTER_FORBIDDEN_TAGS)
        remove_tags.update(ASSISTANT_PERSONA_VISUAL_TAGS)
        remove_tags.update(bare_character_tags(resolved_tags))
    remove_tags.update(clean_prompt_tag_name(tag) for tag in (unknown_tags or []))
    if not resolved_tags:
        remove_tags.update(clean_prompt_tag_name(tag) for tag in (named_source_terms or []))

    kept = []
    for raw in source_prompt.split(","):
        clean = clean_prompt_tag_name(raw)
        clean = REPAIR_TAG_ALIASES.get(clean, clean)
        if resolved_tags and is_named_character_leak_tag(clean):
            continue
        if resolved_tags and is_named_character_default_detail_tag(clean):
            continue
        if resolved_tags and re.search(r"\b\d+[-_]*\d*cm\b|height", clean):
            continue
        if not clean or clean in remove_tags or is_forbidden_positive_tag(clean) or clean in protected:
            continue
        kept.append(clean)

    output = []
    for tag in protected + kept:
        if tag and tag not in output:
            output.append(tag)
    return ", ".join(output)
