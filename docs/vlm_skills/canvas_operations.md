# Infinite Canvas Operations

SimpAI Studio uses an infinite canvas made of nodes and typed edges. A node can
hold media, text, generation settings, a generation workflow, analysis output,
or timeline edits. An edge connects an output from one node into a compatible
input slot on another node.

## Common Node Types

- `image`, `video`, `audio`: imported media assets.
- `text`: reusable prompt or note text that can be connected into generators.
- `note`: visual note for planning; not normally used as a generation input.
- `preset`: SCENE preset generation node.
- `classic`: CLASSIC generation node with richer Fooocus-style controls.
- `config`: external model, resolution, or detection-region configuration.
- `result`: generated or materialized output asset.
- `wd14`: image tagging node.
- `vlm`: vision-language model analysis or chat node.
- `mask`: mask extraction and refinement node.
- `compare`: image comparison node.
- `timeline`: media timeline node for clip layout and rendering.

## Edge Types

- `upload`: media input into `preset` or `classic`.
- `config`: config node into `preset` or `classic`.
- `text`: text, translation, tag cart, or VLM output into prompt-like inputs.
- `image`: image-like source into VLM, WD14, or mask nodes.
- `compare`: image-like source into compare slots.
- `timeline`: media source into a timeline clip.
- `generate`: generator or timeline output into a result node.

## Agent Behavior

When a user asks about the canvas, first use the canvas snapshot. Prefer concrete
node ids and titles from the snapshot over guessing. If selected nodes are
present, treat them as the user's current focus. If the request asks "what is
wrong", check broken edges, ignored nodes, missing inputs, failed statuses, and
empty prompt fields before suggesting bigger workflow changes.

For operation advice, explain the next manual step clearly. If a safe action
would help, suggest it with the action protocol from `safe_actions.md`.
