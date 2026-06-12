# Skill Ownership And Edit Boundaries

本文档用来区分两类知识：一类必须由项目作者亲自说明或审核，另一类可以由
Codex 根据代码、运行时画布和接口结构自动生成。

## 中文速查

需要你手动改的地方：

- `docs/vlm_skills/skill_ownership.md`：维护边界本身，也就是“哪些必须你解释”。
- `docs/vlm_skills/safe_actions.md`：Agent 可以建议哪些 action，哪些绝对不能碰。
- `docs/vlm_skills/canvas_operations.md`：画布功能的真实用途、推荐流程、中文命名和隐藏约定。
- `docs/vlm_skills/image_prompting.md` 里与产品协议直接相关的部分：例如
  图像 action 是否必须带 `subject_counts`，以及 `girls / boys / others / total`
  各字段的语义边界。
- 未来新增的专题文档，例如 `workflow_recipes.md`、`node_reference.md`、`troubleshooting.md`、`asset_management.md`、`timeline_editing.md`、`model_selection.md`。

通常不用你改的地方：

- `webui.py` 里的 `_canvas_build_vlm_agent_system_prompt()`：只是把已批准文档和画布快照塞给模型。
- `webui.py` 里的 `_canvas_read_vlm_skill_docs()`：只是读取 `docs/vlm_skills/`。
- `javascript/infinite_canvas_workbench.js` 里的 `buildVlmAgentContext()`：只是自动收集当前画布节点、连线、选中状态。
- Chat 气泡下的 action 预览 UI：只展示解析结果，不执行操作。

需要改代码的情况：

- 你要给 Agent 新增一种上下文字段，例如“当前画布缩放比例”“当前打开的资产面板状态”。
- 你要新增一个 action 类型，例如让 Agent 创建节点、连接边、提交生成任务。
- 你要让 action 从“只读建议”变成“用户确认后执行”。

不需要改代码的情况：

- 只是补充某个功能怎么用。
- 只是改推荐工作流、中文措辞、注意事项。
- 只是把某个 action 从“建议使用”改成“暂不开放”。
- 只是添加一篇新的技能说明文档，并在 `skill_index.json` 登记。

---

This document separates SimpAI knowledge that must be written or reviewed by the
project owner from knowledge that Codex can generate from the codebase.

## You Should Manually Add Or Review

Edit these files when the meaning depends on your product intent:

- `docs/vlm_skills/skill_ownership.md`: ownership rules and what must remain
  human-authored.
- `docs/vlm_skills/safe_actions.md`: action whitelist, risk rules, and anything
  that may later mutate the canvas.
- `docs/vlm_skills/canvas_operations.md`: workflow intent, user-facing names,
  preferred operating procedures, and hidden assumptions that are not obvious
  from code.
- Future topic files such as `node_reference.md`, `workflow_recipes.md`,
  `troubleshooting.md`, `asset_management.md`, `timeline_editing.md`, and
  `model_selection.md`.

Manual knowledge is needed for:

- Why a feature exists and when a user should choose it.
- Domain-specific workflow names and Chinese/English wording.
- Safety policy for operations that create, delete, overwrite, run generation,
  call online APIs, or spend user credits.
- Product promises that should not be inferred from implementation details.
- Exceptions, preferred defaults, and project-specific conventions.
- Structured generation contracts that the UI, validator, and model must all
  agree on, for example whether image actions use `subject_counts` as
  `{girls,boys,others,total}` and how unnamed visible extra subjects should be
  represented.

## Codex Can Generate Or Refresh

These areas can be generated from the current repository and runtime canvas:

- Node type summaries from render and serializer code.
- Edge type compatibility from connection rules.
- API endpoint summaries from `webui.py` and `javascript/canvas_workbench/api.js`.
- Runtime canvas snapshots sent by `buildVlmAgentContext()`.
- Low-risk action parsing and preview UI, as long as the whitelist is unchanged.
- Draft documentation that you later review and promote to official knowledge.
- Examples, acceptance notes, and consistency updates derived from an already
  approved `subject_counts` contract.

Codex may update these files directly when asked to refresh generated knowledge:

- `docs/vlm_skills/canvas_operations.md`
- future generated reference docs under `docs/vlm_skills/generated/`
- development logs under `docs/`

## Usually Do Not Edit By Hand

Do not manually edit generated runtime state inside saved canvas project JSON
just to teach the Agent. Put stable knowledge in `docs/vlm_skills/` instead.

Do not manually edit the prompt injection code for normal knowledge updates:

- `webui.py` `_canvas_build_vlm_agent_system_prompt()`
- `webui.py` `_canvas_read_vlm_skill_docs()`
- `javascript/infinite_canvas_workbench.js` `buildVlmAgentContext()`

Only change those code paths when adding a new context field, a new retrieval
rule, or a new Agent UI behavior.

## When Adding A New Function Area

1. Add a Markdown file under `docs/vlm_skills/`.
2. Add an entry in `docs/vlm_skills/skill_index.json`.
3. Mark `manual_required` as `true` if the feature has product meaning or safety
   consequences.
4. Mark `auto_generated` as `true` only when the content can be recreated from
   code or runtime state.
5. If the new area needs a new action, add it to `safe_actions.md` first, then
   add parser/UI support in code.
