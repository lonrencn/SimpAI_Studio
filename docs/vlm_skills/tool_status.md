# Tool Execution Status

This document explains how the VLM Agent should judge tool execution state from
the canvas snapshot. It applies to text-to-image generation, CLASSIC / SCENE
nodes, timeline rendering, and future tool calls that report run state.

## Runtime Fields

The frontend sends `agent_context.tool_status` during VLM Chat:

- `active_states`: states that are still in progress or waiting.
- `terminal_states`: states that should not be polled as active work.
- `runs`: recent backend run records from `project.runs`.
- `results`: Result node status summaries.
- `scheduler`: chain-run scheduler state, including blocked or waiting status.

Each run or result may contain:

- `state`: raw state from the frontend/backend.
- `status_kind`: normalized interpretation for the Agent.
- `percent`: progress from 0 to 1 when available.
- `output_count`: number of generated assets.
- `message`: user-facing runtime message.
- `error`: error summary if one exists.
- `user_cancel_action`: `stop` or `skip` when the user manually interrupted.

## Raw State Meaning

- `queued`: submitted and waiting for AsyncTask.
- `waiting`: blocked on upstream refresh, model preparation, or scheduler wait.
- `task_ready`, `args_ready`, `dry_run_ready`: payload validation/preflight has
  succeeded but the backend generation is not final output yet.
- `running`: backend is processing.
- `cancelling`: user requested stop; backend has not returned final state yet.
- `skipping`: user requested skip; backend has not returned final state yet.
- `finished`: backend completed. Check `output_count` to know whether it
  produced usable assets.
- `failed`: backend or preflight failed.
- `canceled`: user stop completed. This is not a model failure.
- `skipped`: user skip completed, usually with no result. This is not a model
  failure.

## Normalized Status Kind

Use `status_kind` first when present:

- `pending`: queued, waiting, or preflight-ready but not executing final output.
- `running`: actively processing.
- `user_interrupt_pending`: stop/skip requested but final backend state not yet
  returned.
- `succeeded`: finished with one or more outputs.
- `finished_without_output`: finished normally but returned no assets. Treat as
  suspicious and ask the user to check backend console or parameters.
- `failed`: error state. Read `error`, `message`, and `last_event`.
- `user_stopped`: user requested stop and backend confirmed cancellation. Do not
  describe this as a model crash.
- `user_skipped`: user requested skip and backend confirmed skip. Do not describe
  this as a model crash.
- `unknown`: state is missing or not recognized.

## Text-To-Image Judgment Rules

For a text-to-image generation:

1. If `status_kind` is `running` or `pending`, say the task is still active or
   waiting. Do not claim failure.
2. If `status_kind` is `user_interrupt_pending`, say the user interruption has
   been requested and the system is waiting for backend confirmation.
3. If `status_kind` is `succeeded`, say it completed and mention `output_count`.
4. If `status_kind` is `finished_without_output`, say the backend ended without
   returning an image. This is different from user stop/skip.
5. If `status_kind` is `failed`, summarize `error` and `message`.
6. If `status_kind` is `user_stopped` or `user_skipped`, say the user manually
   interrupted it and no result should be expected unless a previous asset is
   still attached to the Result node.
7. If a Result node has `stale: true`, tell the user the visible asset may be an
   older output from a previous successful run.

## Agent Response Guidance

When asked "why no result?", check in this order:

1. Is the run still active?
2. Did the user stop or skip it?
3. Did it finish without output?
4. Did it fail with an error?
5. Is the Result node showing a stale previous asset?
6. Is the scheduler blocked by missing or refreshing upstream inputs?

If a status action would help, suggest:

```json
{
  "action": "inspect_tool_status",
  "target_node_id": "result_or_generator_node_id",
  "summary": "Explain whether the task is running, failed, user-stopped, skipped, or completed without output."
}
```

Do not suggest rerunning, deleting, or changing prompts unless the user asks for
that next step.
