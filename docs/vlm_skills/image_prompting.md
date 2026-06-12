# Image Prompting And Text Encoder Targets

Use this skill whenever the user asks to generate, draw, make an image,
prepare an illustration, create a poster, edit an image, outpaint, erase,
replace, upscale, or generate video. The goal is to produce a final prompt that
matches the selected preset, workflow, task method, and text encoder.

## Target Selection

Choose the prompt format in this order:

1. Explicit user preset or selected preset.
2. Preset `backend_engine`, `task_method`, workflow filename, and text encoder.
3. Current Agent queues when no target is known: text-to-image defaults to
   `Z-imageT`, image editing defaults to `Flux2-KleinEdit`, video defaults to Wan.

If the selected workflow `task_method` ends with `_cn`, the target supports
Chinese natural-language prompts. Prefer Chinese for Chinese user requests.

The actual text encoder wins over the marketing family name. If a Flux-family
workflow uses a `qwen*` text encoder, write a Qwen-style natural-language
prompt. If a workflow uses `t5xxl`, write English natural language.

## Universal Prompt Quality

For story illustration and "draw a picture for this scene" requests, first
choose one visible moment from the story. Then describe visual cause and effect:
who is doing what, where it happens, what emotion or conflict is visible, and
how the camera sees it.

Do not output a loose element pile such as "girl, night, sword, rain" unless
the target is an SDXL/Danbooru-tag model. For natural-language encoders, write a
coherent scene or motion description.

Keep execution parameters such as aspect ratio, resolution scale, seed, model,
or preset out of the prompt unless the visual meaning itself matters. Those
belong in structured execution payloads.

For generation or edit action JSON, the `prompt` field must contain the final
prompt that should be submitted by the confirmation card.
When a canvas confirmation card is available, do not print the full prompt,
negative prompt, parameter list, or JSON schema as normal chat text. Put those
details in the action JSON only; the visible reply should be short and describe
the intended image.

For VLM Chat image actions, prefer JSON-only output. If visible chat text is
included before the JSON, it must be at most one short confirmation sentence
(under about 24 Chinese characters or 16 English words). Do not write a long
story paragraph, generated-image description, execution report, markdown
section, or bracket tool call such as `[generate_image: "..."]`. The
confirmation card hides action details and handles user confirmation, so extra
visible prose only increases local-model format drift.

For random / surprise requests such as "随便", "随机", "随意", "来个惊喜",
"随便来个色图", "random character", or "surprise me", prepare exactly one
generation action instead of asking for clarification. Treat the user's intent
as permission to choose subject, scene, camera, lighting, pose, props, and
composition creatively. Do not fall back to a bland portrait or a tiny fixed
template. The backend random Composer owns the open Danbooru database sampling,
random SDXL size selection, and safety filtering, so your JSON should preserve
the random intent and provide a concise runnable prompt in the target format.
Unless the user explicitly requests a size, do not invent width/height; the
backend will choose one of 832x1216, 1216x832, or 1024x1024 for random image
generation.

## Z-image / Qwen Text Encoders

Targets include `Z-image`, `Z-imageT`, `qwen_3_4b`, `qwen3_8b`, and other
Qwen-style text encoders.

Use Chinese or English natural language. If the user writes Chinese and does
not request English, Chinese is preferred. Write one compact paragraph with:

- main subject and action
- story moment or visual conflict
- environment and important props
- composition, camera distance, lighting, mood, and style when relevant

Example:

```text
夜雨中的旧城屋檐下，年轻女剑客回头望向追来的黑衣人，左手护住怀里的信件，右手握着半出鞘的长剑，街灯在积水中反射，近景低机位，紧张悬疑的电影感光影。
```

## Wan / UMT5 Video Encoders

Targets include `Wan`, `Wan(T2V)`, `Wan(I2V)`, `Wan-Extent`, `Wan-Remover`,
`wan*_cn`, and `umt5-xxl`.

Use Chinese or English natural language. For `_cn` task methods or Chinese user
requests, Chinese is preferred. Video prompts must emphasize temporal change:
motion, action progression, camera movement, continuity, and what remains
stable.

Avoid static lists of objects, still-image quality tags, or style-only prompts.
Mention style only after the motion is clear.

Example:

```text
镜头缓慢前推，拍摄雨夜街口的女孩从背对镜头转身看向路灯方向，风吹动她的外套和发梢，地面积水映出霓虹光，背景车辆从远处缓慢驶过，整体保持冷色电影感。
```

## FLUX.1 / T5XXL Encoders

Targets include `Flux1-dev`, `flux_aio`, `flux_base`, `FLUX.1`, and workflows
whose text encoder is `t5xxl`.

The final prompt must be English natural language. If the user writes Chinese,
translate and rewrite the meaning into English in the final `prompt` or
`recommended_prompt`; do not rely on backend Chinese translation. Do not output
Chinese characters in the final FLUX.1/t5xxl prompt.

Write one concise paragraph with subject, action, setting, composition,
lighting, camera, and style. For image editing, preserve source identity,
composition, pose, and lighting unless the user explicitly asks to change them.

Example:

```text
A detective in a dark trench coat stands under a flickering street lamp on a rainy night, reading a torn letter while neon reflections ripple across the wet pavement, cinematic low-angle composition, tense noir atmosphere, realistic lighting.
```

## SDXL / SD15 / Danbooru-Tag Encoders

Targets include `SDXL`, `SD15`, `Fooocus`, `Illustrious`, `Noob`, anime SDXL
checkpoints, and workflows where natural-language prompting is weak.

Use Danbooru-style English tags from the canonical style used by
`tags/danbooru_all.csv`: snake_case, comma separated, no Chinese. Put important
content first, then composition and style. Use common quality tags only when
they match the model style.

When Danbooru lookup results are available, prefer the returned canonical tags
over guessed synonyms. Agent lookup uses the curated `tags/weilin_tagcart.csv`
plus user custom tags by default, not the full `tags/danbooru_all.csv`, because
the full database contains many noisy fragments that are poor prompt candidates.
Use the tag exactly as returned. If a canonical tag contains literal
parentheses, escape them for A1111/Fooocus-style syntax:
`character_\(series\)`.

Named character and copyright tags are stricter than ordinary visual tags. They
must come from the local lookup layer, not model memory. SimpAI resolves
characters and series offline from `tags/character_glossary.csv`,
`tags/danbooru_all.csv`, and the read-only ComfyUI-Danbooru-Gallery
`py/shared/data/tags_cache.db` seed when present. The curated tag cart remains
the default for ordinary general tags. If lookup returns one clear character,
use that canonical tag and its copyright tag when available. If lookup is
ambiguous or missing, do not invent a romanized or long underscore tag; ask the
user to confirm, use generic visual traits, or add the term to the character
glossary.

The character glossary is a local first-priority wordbook for names the model
often gets wrong. Treat the user's existing translations in local CSV files as
manual data. Future imports may add new tags, but must not overwrite existing
translation fields without review. Gallery translation sources such as
`all_tags_cn.json`, `wai_characters.csv`, and `danbooru.csv` are only seed data:
they can fill missing translations and improve lookup, but they do not replace
local manual translations.

For canvas Agent actions, the JSON `prompt` field is a tag-list output, not a
caption. It must be one comma-separated line. Do not put markdown, numbered
sections, execution reports, comments, or Chinese prose inside the prompt field.

For image-generation requests in VLM Chat, the whole reply should normally be
only one JSON action object. The minimal form is:

```json
{"action":"generate_image","prompt":"1girl, solo, ...","subject_counts":{"girls":1,"boys":0,"others":0,"total":1},"summary":"...","confidence":0.95}
```

When the request has a strict relation or composition that must not be lost,
the action may additionally include:

- `draft_prompt`: the first-pass visual draft from the LLM, before local
  Danbooru canonicalization
- `prompt_intent`: a compact structured intent object used to preserve locked
  semantics during backend repair/review, for example:

```json
{
  "action": "generate_image",
  "prompt": "2girls, 1boy, nahida_(genshin_impact), klee_(genshin_impact), ...",
  "draft_prompt": "2girls, 1boy, nahida_(genshin_impact), klee_(genshin_impact), full_body, holding, facing_another",
  "prompt_intent": {
    "locked_tags": ["facing_another", "full_body"],
    "must_preserve": ["male holds both girls", "three visible characters"],
    "scene_strictness": "high",
    "interaction_focus": true,
    "primary_relation": "holding"
  },
  "subject_counts": {"girls": 2, "boys": 1, "others": 0, "total": 3},
  "summary": "...",
  "confidence": 0.95
}
```

Use `prompt_intent.locked_tags` only for compact Danbooru-style tags that the
backend should preserve. Keep `must_preserve` short, semantic, and human
readable; it is for review guidance, not direct prompt emission.

For image-generation actions, `draft_prompt` should normally be present even
when the request is simple. Treat it as a structured first-pass skeleton:

- comma-separated English tags only
- no Chinese, no sentence punctuation, no markdown
- no aspect ratio or parameter text inside the prompt
- no prose converted into long underscore pseudo-tags
- ordered roughly as: subject count, identity, composition, action/expression,
  setting, lighting/rendering, quality
- every important tag must be grounded in the current user request, local
  lookup context, or explicit target metadata; do not copy example tags as a
  default visual profile

First-pass draft failure guards:

- If the user names a character, the draft must preserve the resolved
  character/copyright tags when lookup provides them.
- If the user specifies a visible count or relationship, use exactly the
  compatible subject-count tags and do not include conflicting `solo`,
  `1girl`, `2girls`, `3girls`, `1boy`, `2boys`, or `no_humans` tags.
- If the user gives a core action, prop, food, relationship, or setting, it
  must appear in `draft_prompt` and in `prompt_intent.locked_tags` or
  `prompt_intent.must_preserve`.
- A syntactically valid prompt that falls back to unrelated profile traits is
  still a failed draft.

Do not use bracket pseudo-tools like `[generate_image: "..."]`. They are kept
only as a backend compatibility fallback, not as the desired model output.

For image actions, always include `subject_counts` as
`{"girls":0,"boys":0,"others":0,"total":0}`:

- `girls`: visible female characters or women
- `boys`: visible male characters or men
- `others`: visible unnamed extra people or characters that are still part of
  the scene
- `total`: the total visible subject count, which should be at least
  `girls + boys + others`

Use `others` when the user describes extra visible subjects without naming them.
For example, if the user asks for Nahida and Klee being held by another visible
person, the structured action should prefer:

```json
{"action":"generate_image","prompt":"2girls, multiple_others, nahida_(genshin_impact), klee_(genshin_impact), genshin_impact, ...","subject_counts":{"girls":2,"boys":0,"others":1,"total":3},"summary":"...","confidence":0.95}
```

Do not silently collapse unnamed visible subjects into the named characters. If
`subject_counts.others > 0`, the SDXL/Danbooru prompt should normally include an
extra-subject signal such as `multiple_others`.

Keep execution controls out of the prompt. Use JSON fields for `aspect_ratio`,
`width`, `height`, `image_number`, `seed`, `seed_random`, `steps`, `cfg_scale`,
and `resolution_scale` only when the user explicitly requested them.

Before finalizing an SDXL/Danbooru action, run this internal check:

- target format is comma-separated English tags
- no Chinese characters and no sentence ending punctuation
- no pseudo-tags made by replacing prose spaces with underscores
- negative tags are in `negative_prompt`, not in the positive prompt
- persona/selfie requests preserve stable identity traits
- pure scenery/background/wallpaper requests use scenery tags and `no_humans`
  unless the user asked for a person
- multiple requested images are one action with `image_number`, not many actions

Recommended order:

```text
subject count / multiple_others / no_humans, character/persona identity, body/camera/composition, pose/action/expression, clothes/accessories, setting/background, lighting/rendering, quality/model tags
```

Here `character/persona identity` is an ordering label, not a literal tag. Do
not write placeholder tags such as `character`, `female`, `male`, `person`, or
`human` for a visible named character. Use `1girl`/`1boy`/`solo`/`multiple_others`
plus the resolved canonical character tag when appropriate.

Avoid `halo` in positive prompts unless the user explicitly asks for a halo.
Anime checkpoints can over-associate it with Blue Archive-style character
features and add unwanted halos to unrelated characters.

Examples in this document demonstrate format only. They are never default
content for the current request.

Do not write a full Chinese sentence for SDXL/Danbooru targets. If the user
request is Chinese, convert it into appropriate English tags.

Avoid fabricated long tags made by replacing a sentence with underscores.
Prefer compact canonical atoms for count, subject, action, setting, prop, and
lighting.

Do not use bare color/property fragments as final tags. Tags like `black`,
`green`, `eyes`, `school`, `city`, `portrait`, `illustration`, and `lighting`
are too weak and can override or blur the intended trait. Use complete visual
attributes only when the current user request or local lookup context actually
provides them.

Persona traits are subject-scoped, not a global style prefix. For
persona/selfie/show-me requests such as "给我看看你的样子", convert the assistant's
stable persona traits from the system prompt into compact canonical tags before
scene details. Preserve only the traits that are actually part of the requested
visible subject; do not let persona appearance leak into third-party character
or scenery requests.

For named third-party characters, objects, and pure scenery, do not inject the
assistant persona. The resolved canonical character tag already carries the
character's default design, so do not pad the prompt with guessed hair color, eye
color, outfit, dress, skirt, or accessory tags unless the user explicitly asks to
change or emphasize those details. For example, a Genshin character prompt should
start from `ganyu_(genshin_impact), genshin_impact` or
`nahida_(genshin_impact), genshin_impact`, then spend the remaining tags on the
requested composition, action, setting, atmosphere, and lighting.
For character requests such as Ganyu, Saber, Hatsune Miku, or a user glossary
name, the final positive prompt must include the resolved canonical character
tag. If preflight reports a resolved character that is missing from the final
prompt, fix the prompt before submission. Do not add `no_humans` to any prompt
with a visible named character, and do not add `halo` unless requested.

### Tag Weighting

Use weights sparingly and only for the most important visual ideas:

```text
(tag)        # about 1.1x stronger
((tag))      # stronger again
(tag:1.2)    # explicit multiplier
(tag:0.8)    # weaker
```

Do not use weights to compensate for a vague prompt. First choose better tags
and place important tags earlier.

### Illustrious Notes

Illustrious-family presets prefer focused comma-separated Danbooru tags. The
local `Illustrious` style adds a positive quality suffix similar to:

```text
masterpiece, best quality, absurdres, newest, very aesthetic, amazing quality, highres
```

Local Illustrious presets already contain default negative prompts such as
`lowres`, `bad anatomy`, `bad hands`, `watermark`, `signature`, and related
artifact tags. Do not put those negative tags into the positive prompt.

### NoobAI / NAI-XL Notes

NoobAI / NAI-XL models use Danbooru-style caption ordering. A common structure
is:

```text
1girl/1boy, character, series, artist/style tags, description tags, quality tags
```

Common positive quality tags are:

```text
masterpiece, best quality, newest, absurdres, highres
```

Some v-pred derivatives work best with very light or empty negative prompts,
while local SimpAI presets may provide their own negative prompt. Prefer the
selected preset's default negative prompt instead of inventing a long negative
block in the Agent action.
