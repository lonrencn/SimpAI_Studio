# Danbooru Tag Prompting

Use this skill only for SDXL/Danbooru-style image targets such as Illustrious,
Noob, Pony, Animagine, and anime SDXL workflows where the positive prompt should
be a compact tag list.

This skill is not a natural-language captioning guide. For Danbooru targets,
the JSON `prompt` field is a comma-separated English tag list, not prose.

## Output Contract

Return one JSON action object for an image request:

```json
{"action":"generate_image","prompt":"1girl, solo, ...","draft_prompt":"1girl, solo, ...","prompt_intent":{"locked_tags":[],"must_preserve":[]},"subject_counts":{"girls":1,"boys":0,"others":0,"total":1},"summary":"...","confidence":0.95}
```

Rules:

- `draft_prompt` is the first-pass visual skeleton.
- `prompt_intent.locked_tags` contains compact canonical tags that must survive
  backend repair.
- `prompt_intent.must_preserve` contains short semantic constraints, especially
  actions, relations, props, and scene facts that are hard to express as one tag.
- Put aspect ratio, image count, size, seed, steps, and cfg only in JSON control
  fields when the user explicitly requests them.

## Tag Format

Use Danbooru-style English tags from the canonical style used by
`tags/danbooru_all.csv`: snake_case, comma separated, no Chinese. Put important
content first, then composition, action, setting, atmosphere, and quality.

Do not write markdown, numbered sections, execution reports, comments, Chinese
prose, or sentence punctuation inside `prompt` or `draft_prompt`.

Avoid fabricated long tags made by replacing prose with underscores. Prefer
compact atoms for count, subject, action, setting, prop, and lighting.

## Local Lookup

When Danbooru lookup results are available, prefer the returned canonical tags
over guessed synonyms. Use the tag exactly as returned.

Named character and copyright tags must come from the local lookup layer, not
model memory. SimpAI resolves characters and series offline from:

- `tags/character_glossary.csv`
- `tags/danbooru_all.csv`
- ComfyUI-Danbooru-Gallery `tags_cache.db` seed when present

If lookup returns one clear character, use that canonical tag and its copyright
tag when available. If lookup is ambiguous or missing, do not invent a romanized
or long underscore tag.

## Hard Locks

Preserve user hard intent:

- explicit subject count and relationship
- resolved character canonical tags
- copyright/source tags when locally resolved
- transparent background / simple asset requests
- explicit action, relation, prop, setting, and composition

If the user specifies a visible count or relationship, use exactly compatible
subject-count tags and do not include conflicting `solo`, `1girl`, `2girls`,
`3girls`, `1boy`, `2boys`, or `no_humans`.

For image actions, always include:

```json
{"girls":0,"boys":0,"others":0,"total":0}
```

Use `others` for visible unnamed extra subjects. If `subject_counts.others > 0`,
the prompt should normally include an extra-subject signal such as
`multiple_others`.

## Adult Branch

Use adult tags only when local prompt locks, `resolution`, or policy payload
already indicate an adult branch for the current user request. Preserve the
allowlisted adult body state or action, but do not infer adult content from
ordinary beauty, sexy styling, or glamour wording alone.

Do not escalate beyond the provided adult tags or policy level. Do not add
extra partners, stronger acts, unrelated fetishes, non-consensual framing,
violent sexual framing, minor-coded terms, or policy commentary.

## Persona Scope

Persona traits are subject-scoped. Use assistant persona appearance only when
the user explicitly asks to draw the assistant, the assistant's selfie/avatar,
or a scene where the assistant is a visible participant.

For persona/selfie/show-me requests, convert stable persona traits from the
active system prompt into compact tags. Because users can customize the system
prompt, persona traits are not globally fixed.

For third-party characters, objects, and pure scenery, do not inject assistant
persona traits. The resolved canonical character tag already carries the
character's default design, so do not pad the prompt with guessed hair color,
eye color, outfit, or accessory tags unless the user asks for those details.

## Final Check

Before finalizing:

- prompt is comma-separated English tags
- no Chinese characters
- no prose-like pseudo-tags
- no generation controls inside the prompt
- no negative tags in the positive prompt
- persona traits appear only when persona is the requested subject
- pure scenery/background/wallpaper uses scenery tags and `no_humans`
- transparent background requests keep `transparent_background`
- explicit subject count and canonical identity are preserved
