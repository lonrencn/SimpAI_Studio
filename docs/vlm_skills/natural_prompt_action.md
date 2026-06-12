# Natural Prompt Action Writer

Use this skill when the selected text-to-image or video target expects a
natural-language prompt: `qwen_natural`, `flux_t5_en`, `wan_video_cn`,
Qwen-style encoders, FLUX/T5 encoders, or Wan/UMT5 encoders.

Return exactly one generation action JSON object. Do not write markdown,
analysis, a "why this works" section, target explanations, execution reports,
or normal chat around the JSON.

## Action Shape

Use this compact shape:

```json
{"action":"generate_image","prompt":"...","draft_prompt":"...","prompt_intent":{"locked_tags":[],"must_preserve":[],"enrichment_tags":[]},"subject_counts":{"girls":0,"boys":0,"others":0,"total":0},"summary":"...","confidence":0.95}
```

`prompt` is the final natural-language generation prompt. `draft_prompt` is a
compact natural-language scene draft in the same target language. Neither field
is a Danbooru tag list.

Do not use alternate nested schemas such as `prompt_payload`, `visual_payload`,
`safety_override`, `engine_config`, `metadata`, or `system_instructions`. Flatten
the visual description into `prompt` and keep internal routing details out.

## Language

- `flux_t5_en`, FLUX, and T5 targets: English only. Translate Chinese user
  intent into fluent English.
- `wan_video_cn`, Wan, UMT5, and video targets: use Chinese for Chinese
  requests and include visible motion, camera movement, temporal continuity,
  and stable subject details.
- `qwen_natural` and unknown natural targets: preserve the user's language by
  default; Chinese requests should produce coherent Chinese natural language.

## Prompt Content

Preserve the user's explicit named subjects, subject count, relationship,
action, body state, setting, clothing, props, camera, mood, and constraints.

For named characters or role words, keep the requested identity and add visible
anchors: hair, eyes, outfit colors, accessories, body silhouette, pose,
expression, props, and scene context. Build one coherent small scene with
subject design, action, setting, composition, lighting, atmosphere, material
detail, and a clear story beat.

For beauty, cute, sexy, or glamour requests, add visible appeal through styling,
pose, expression, body silhouette, clothing, skin light, and atmosphere. Unless
the dedicated adult branch is loaded, keep the result non-explicit: no nudity or
explicit acts.

## Negative Constraints

Never put negation wording in `prompt` or `draft_prompt`: avoid `no`,
`without`, `avoid`, `not`, `不要`, `别`, `没有`, and similar phrases.

When the user gives a negative constraint, rewrite the positive prompt
affirmatively when useful and put only the forbidden concepts in
`negative_prompt`. Do not invent negative concepts.

## Do Not

- Do not output comma-separated Danbooru tags for natural targets.
- Do not output nested prompt payloads, safety override blocks, policy notes,
  unlock signals, or engine metadata.
- Do not include command flags such as `--ar`, `--style`, `--seed`, `steps`,
  `cfg`, sampler, width, height, or LoRA syntax inside prompt fields.
- Do not add artist names, watermark/signature/text artifacts, metadata,
  markdown headings, numbered prompt instructions, or prompt templates.
- Do not use assistant persona appearance unless the user explicitly asks to
  draw the assistant, a selfie, or an avatar.
