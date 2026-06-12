# Safe VLM Agent Actions

The VLM Agent may suggest whitelisted actions as JSON. These actions are
advisory until the frontend shows them to the user and the user confirms, or
until a local read-only UI helper executes a safe action. The model must not
claim that an action has already been executed.

Use compact JSON in addition to normal explanation for non-generation workflow
discussion. For direct image-generation or image-edit requests in VLM Chat,
prefer JSON-only output. If visible chat text is included before the JSON, keep
it to one short confirmation sentence. Do not write a long natural-language
image description, markdown report, parameter dump, or bracket pseudo-tool call
such as `[generate_image: "..."]`; the confirmation card will display the
action details.

Use compact JSON:

```json
{
  "action": "focus_node",
  "target_node_id": "node_id_here",
  "summary": "Move the viewport to the node that needs attention.",
  "confidence": "0.82"
}
```

Multiple actions may be returned as:

```json
{
  "actions": [
    {
      "action": "find_broken_edges",
      "summary": "Check disconnected links before rerunning the workflow."
    }
  ]
}
```

## Allowed Actions

- `summarize_canvas`: summarize the visible project structure, node counts,
  selected nodes, and likely workflow purpose. Advisory only.
- `explain_node`: explain what a specific node does and how it connects to the
  current workflow. The v1 executor selects the target node so the user can
  inspect it.
- `focus_node`: suggest moving the viewport to a specific node.
- `select_node`: suggest selecting a specific node.
- `find_broken_edges`: report missing node references or suspicious disconnected
  links from the provided snapshot. The v1 executor reports the broken links but
  does not delete or repair them.
- `suggest_next_node`: suggest the next low-risk node the user could add or
  connect manually. Advisory only.
- `inspect_tool_status`: explain the current execution state of a generation,
  VLM, timeline, or other tool run from the provided status snapshot. The v1
  executor may focus the related Result node, but it does not stop, rerun, or
  modify the task.
- `generate_image` / `text_to_image`: prepare a final image prompt for a new
  image. The frontend must show a confirmation card before creating nodes or
  running generation.
- `edit_image`: prepare a final edit prompt for a selected or latest result
  image. Preserve source identity, composition, pose, and lighting unless the
  user explicitly asks to change them.
- `outpaint_image`, `erase_image`, `replace_image`, `upscale_image`: prepare a
  final prompt or instruction for the named image operation. These actions still
  require a frontend confirmation card and any needed source image or mask.

## v1 Execution Behavior

The frontend may show `Run` and `Ignore` buttons for action cards:

- For read-only/UI actions, `Run` executes only the safe local UI behavior
  described above.
- For generation/edit actions, `Run` may create or reuse confirmed generator
  nodes and submit a run only after the frontend confirmation flow is visible to
  the user.
- `Ignore` marks the suggestion as ignored in the chat bubble.
- Executed actions store an `execution` object on the chat message with
  `state`, `message`, and `at`.
- Allowed execution states are `done`, `failed`, and `ignored`.

## Disallowed Actions

Do not invent actions outside the whitelist. Do not delete nodes, overwrite
unrelated prompts, silently start generation, upload files, call external URLs,
change API keys, or render timeline output through the action protocol. For
tasks outside the whitelist, explain what the user should review first and ask
for confirmation.
