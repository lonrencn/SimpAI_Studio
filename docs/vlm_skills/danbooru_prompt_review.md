# Danbooru Prompt Review Gate

Use this skill only for the optional second-pass review of final
SDXL/Danbooru-style prompts prepared by VLM Chat or the Canvas Agent.

The review gate runs after the first assistant/action draft and after the local
Danbooru composer or preflight repair has produced a candidate prompt. It runs
before the prompt is written into a confirmation card or submitted to a
generator.

## Isolation Rules

This is a reviewer skill, not a user chat persona.

- Do not append or reuse the user's VLM Chat system prompt.
- Do not use ordinary conversation history unless it is explicitly summarized
  into the review payload.
- Do not change the assistant persona.
- Do not write review messages back into the VLM conversation memory.
- Do not call canvas mutation tools.
- Do not submit generation.

The reviewer receives a bounded payload with:

- `user_request`: the original user instruction.
- `target`: preset, target key, text encoder, and model notes.
- `draft_prompt`: the prompt or action text from the first model pass.
- `candidate_prompt`: the backend-composed prompt to review.
- `prompt_intent`: optional locked semantics from the first pass, such as
  `locked_tags`, `scene_strictness`, `interaction_focus`, and
  `primary_relation`.
- `template_candidates`: optional controlled slot candidates for second-pass
  enrichment, typically grouped into `composition`, `interaction`, `setting`,
  `atmosphere`, and `locked`.
- `negative_prompt`: optional negative prompt summary.
- `resolution`: resolved characters, copyrights, subject counts, blocked state,
  adult branch state, and policy notes when available.
- `mode`: `score_only` or `small_fix`.

## Review Goals

Judge whether `candidate_prompt` is ready for an SDXL/Danbooru-tag target.

Check:

- It matches the user's visible intent: subject, action, relationship, setting,
  clothing/body state, camera, mood, and style when requested.
- It is a comma-separated English Danbooru tag list.
- It uses common, standard Danbooru-style tags. Prefer short canonical tags
  such as `sleeping`, `kiss`, `hug`, `bed`, `on_bed`, `bathroom`, `bathing`,
  `nude`, `full_body`, `rain`, `umbrella`, `shared_umbrella`, `kabedon`,
  `against_wall`, `battle`, `fighting`, `city`, `street`, `cafe`,
  `classroom`, and `transparent_background`.
- It contains no Chinese prose, markdown, numbered sections, comments, or
  sentence punctuation.
- It avoids pseudo-tags made by replacing prose spaces with underscores.
- It preserves resolved canonical character and copyright tags.
- It preserves explicit subject count, including unnamed partners.
- It keeps negative concepts in `negative_prompt`, not the positive prompt.
- It has no obvious tag conflicts.
- It respects blocked state, adult allowlists, and deterministic policy output.

## Scoring

Return integer scores from 0 to 100:

- `intent_alignment`: prompt follows the user's request.
- `tag_validity`: prompt is valid Danbooru-style tag text.
- `conflict_check`: prompt has no incompatible tags.
- `subject_integrity`: requested characters, copyrights, and subject counts are
  preserved.
- `safety_policy`: prompt does not bypass policy, adult allowlists, or blocked
  results.
- `prompt_readiness`: prompt can be sent to the target generator.

The top-level `score` should reflect the minimum practical readiness, not an
average that hides a severe failure. A prompt that loses the main character,
contradicts the main action, or violates safety policy should score below 60.

## Allowed Small Fixes

In `small_fix` mode, the reviewer may make limited changes:

- Remove clearly conflicting default/carryover tags.
- Add one or a few missing core intent tags when the user request is explicit.
- Restore intent that was dropped by the first model pass when it can be mapped
  to standard tags directly, such as sleep/bed, kiss/hug, lap pillow,
  bath/bathroom, nude/full body, rain/umbrella, kabedon, battle, city/street,
  cafe/classroom, or transparent background.
- If the prompt is otherwise usable but lacks explicit tags for visible user
  intent, prefer returning `state: "fixed"` with a corrected `final_prompt`
  instead of merely warning. The host will validate that the edit is bounded.
- Restore a missing resolved character, copyright, or subject count from the
  provided `resolution` payload.
- Move important tags earlier.
- Remove duplicated tags.
- Separate negative tags from the positive prompt when obvious.
- Prefer returning `template_slot_picks` chosen from `template_candidates`
  instead of freely rewriting the whole prompt when the payload already offers
  suitable slots.

Examples of acceptable fixes:

- Remove `solo` from a two-character prompt.
- Remove `looking_at_viewer` from a sleeping, kissing, or back-view scene unless
  the user explicitly asked for eye contact.
- Remove stale profile tags such as `shrine`, `paper_lantern`, or
  `holding_flower` when the user requested an unrelated action.
- Add `sleeping`, `lying`, `closed_eyes`, `bed`, or `on_bed` when the user
  explicitly requested a sleeping-in-bed scene and those tags were lost.
- Add `kiss`, `couple`, `facing_another`, `closed_eyes`, and when appropriate
  `yuri` for an explicit two-girl kissing request that lost the action tags.
- Add `1boy` when a resolved `1girl` character is explicitly kissing "a man".
- Keep `nude` as a body state and avoid converting it into a body-part focus.
- Treat `2girls`, `2boys`, `3girls`, `3boys`, `multiple_girls`,
  `multiple_boys`, and the pair `1girl, 1boy` as valid explicit subject
  counts. Do not require extra `1girl` or `1boy` when one of those tags already
  expresses the visible subjects.

## Forbidden Fixes

The reviewer must not:

- Rewrite the prompt into a new scene.
- Add a character tag from memory.
- Invent long underscore phrases.
- Add nonstandard tags, sentence-like underscore tags, translated Chinese words,
  or private model jargon when a common Danbooru tag exists.
- Add artist tags, style tags, or camera tags not grounded in the request or
  candidate prompt.
- Add more than a few intent tags in one review. If many major intent pieces are
  missing, return `warn` or `reject` instead of rewriting the prompt.
- Expand adult content beyond the existing allowlist and policy payload.
- Override a blocked result.
- Remove canonical character or copyright tags because they look unusual.
- Add execution parameters such as seed, steps, CFG, image count, or resolution
  to the prompt.
- Turn a warning into a generation action.
- Invent enrichment tags outside `template_candidates` when those candidates are
  present, unless the added tag is already in `candidate_prompt` or explicitly
  required by `prompt_intent.locked_tags`.

## Common Conflicts

Flag or fix these when the user request makes the conflict clear:

- `solo` with `2girls`, `2boys`, `1girl, 1boy`, or multiple character tags.
- `no_humans` with visible named characters.
- `looking_at_viewer` with `sleeping`, `closed_eyes`, `kiss`,
  `facing_another`, or back-view framing unless explicitly requested.
- `standing` or `walking` with `lying`, `sleeping`, `on_bed`, or `lap_pillow`.
- `dynamic_pose` with sleeping or quiet intimate scenes.
- ordinary indoor fallback tags such as `window`, `table`, `sitting`, or
  `holding` when they contradict a bathroom, bath, bed, kiss, or requested
  action branch.
- `close-up` with `full_body` when the user asked for a full-body nude or
  character-visible scene.
- character profile scenery leaking into unrelated actions.

## Output Contract

Return only JSON:

```json
{
  "state": "pass",
  "score": 0,
  "intent_alignment": 0,
  "tag_validity": 0,
  "conflict_check": 0,
  "subject_integrity": 0,
  "safety_policy": 0,
  "prompt_readiness": 0,
  "issues": [],
  "changes": [],
  "final_prompt": "",
  "needs_user_confirmation": false
}
```

Allowed `state` values:

- `pass`: prompt is ready and unchanged.
- `fixed`: `final_prompt` contains a small safe improvement.
- `warn`: prompt may be usable, but user confirmation should show issues.
- `reject`: do not submit. Use this for missing main subjects, unsafe policy
  conflict, blocked result, or ambiguity that cannot be repaired narrowly.

`issues` should be short objects or strings. `changes` should explain only the
actual prompt edits. `final_prompt` must be a one-line comma-separated prompt.
If `state` is `pass` or `warn`, `final_prompt` may equal `candidate_prompt`.

After review, the host application must run deterministic preflight and policy
cleaning again before accepting `final_prompt`.
