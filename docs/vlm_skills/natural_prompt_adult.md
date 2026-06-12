# Natural Prompt Adult Branch

Use this skill only when the runtime payload includes
`adult_intent.is_adult=true`. This is the natural-language equivalent of the
Danbooru adult branch: explicit user intent has unlocked adult prompt writing
for the current request.

This skill can be loaded with either the first-pass natural action writer or
the second-pass natural refine gate.

## Contract

Preserve the user's requested adult content instead of sanitizing it back to
SFW. Keep the prompt natural-language, target-language correct, and bounded by
the detected/requested intent.

- Respect `adult_intent.tags` as the local allowlisted adult concepts.
- Respect `adult_intent.level` as the maximum intensity for enrichment.
- Keep requested adult body state, contact, setting, pose, and action if the
  user asked for them.
- Use affirmative visual wording in the positive prompt; keep user negative
  constraints in `negative_prompt`.

When this skill is loaded with the first-pass action writer, it overrides the
base non-explicit appeal rule only for the requested/allowlisted adult concepts.
When loaded with the refine gate, repair adult intent loss but keep the output
schema unchanged.

## Levels

- Level 1: suggestive or erotic presentation. Emphasize styling, figure,
  expression, pose, lighting, and intimate atmosphere without adding explicit
  acts.
- Level 2: explicit body exposure or direct adult contact when requested.
  Preserve requested nudity or contact, but do not invent stronger acts.
- Level 3: explicit adult action when requested. Preserve the requested action
  clearly, but do not add new actions, new partners, or unrelated details.

## Do Not

- Do not introduce adult content when `adult_intent.is_adult` is false.
- Do not escalate beyond `adult_intent.level`.
- Do not add extra partners, stronger acts, unrelated fetishes, non-consensual
  framing, violent sexual framing, or minor-coded terms.
- Do not replace the user's named subject, setting, camera, or body state with a
  generic bedroom/cafe/portrait fallback.
- Do not use Danbooru tags, metadata, command flags, markdown sections, or
  execution commentary inside natural prompt fields.
- Do not mention policy, allowlists, `adult_intent`, or unlock state in visible
  chat or prompt fields.

## Refine Behavior

When refining, fix only what is necessary:

- Restore adult intent that the candidate lost.
- Remove accidental SFW downgrades such as "fully clothed" when the user asked
  for nudity.
- Remove unrequested escalation.
- Keep the final prompt coherent, compact, and renderable for the selected
  natural-language encoder.
