# 导演工作台 README

本文说明主界面 `导演工作台` 和无限画布 `Director Timeline` 的当前实现、可见行为和上线前验证点。

相关文件：

- WebUI 入口：`webui.py`
- WebUI 后端逻辑：`modules/scene_director_webui.py`
- WebUI 前端交互：`javascript/scene_director.js`
- WebUI 样式：`css/style.css`
- Infinite Canvas 导演节点：`javascript/canvas_workbench/nodes/director_timeline_node.js`
- Preset 能力验证：`tests/test_scene_director_webui_contract.py`
- 上线矩阵：`docs/director-workspace/release-matrix-test-plan.md`

## 当前定位

`导演工作台` 是视频 preset 的分镜编排面板。它不属于右侧窄参数区，也不属于某个 preset 的普通参数组，而是和 `高级参数` 同级显示。

它负责：

- 编辑多个分镜的开始、结束、提示词、图片引用、音频引用和视频引用。
- 把分镜转换成 `prompt_override` 和 `director_timeline`。
- 按当前 preset 的 `director_capability` 限制图片、音频、视频、时长和串联方式。
- 逐分镜调用当前视频 preset。
- 在用户开启 `Compose timeline` 时，把多个分镜结果合成为最终视频。

它不负责：

- 替代 preset 自己的模型参数。
- 替代 SAM3 蒙版、局部重绘、视频擦除这类额外交互。
- 强制所有视频 preset 都支持导演模式。

## WebUI 可见结构

展开 `导演工作台` 后，界面分为四块：

| 区域 | 内容 |
| --- | --- |
| 顶部控制 | `Director mode`、`Compose timeline` |
| 素材区 | 图片 1-5、音频 1-5、视频 1-5 |
| 右侧栏 | 合成宽度、高度、FPS、时间轴范围、素材规则说明、README 链接 |
| 分镜区 | 分镜编辑器、图片引用按钮、音频/视频下拉、prompt 预览 |

宽屏布局：

- 左侧是素材区。
- 右侧是一个整体侧栏，合成参数和规则说明紧密排列。
- 分镜编辑器在素材区下方横向展开。

窄屏布局：

- 顺序变为顶部控制、素材区、右侧栏、分镜区、prompt 预览。
- 不依赖浏览器 viewport 宽度，按导演台内容容器宽度响应。

## 上传区语言

上传区固定文案由 `javascript/scene_director.js` 按当前语言刷新：

- `Images` / `图片`
- `Audio` / `音频`
- `Video` / `视频`
- `Click or drop` / `点击或拖入`
- `Clear` / `清除`
- 右侧素材规则说明
- `Director README` / `导演台说明`

语言来源：

- 优先使用 `window.SimpAII18n.isEnglishUi(window.simpleaiTopbarSystemParams)`。
- 其次读取 `window.simpleaiTopbarSystemParams.__lang`。
- 再其次读取 `locale_lang`。

注意：Gradio 上传音频或视频后会重新替换素材区 HTML，所以固定文案不能只在页面初始化时翻译。`sceneDirectorRenderMediaPreview()` 和 `sceneDirectorRenderRules()` 必须在每次刷新时重新写入当前语言。

Python 生成的固定 HTML 文案要保留 `data-original-text` 或 `data-scene-director-*` 标记，方便前端识别原始英文 key。

## 素材池

WebUI 导演台当前有 15 个素材位：

| 类型 | 引用名 | 说明 |
| --- | --- | --- |
| 图片 | `image_1` 到 `image_5` | 自绘拖入区，写入导演台自己的素材状态 |
| 音频 | `audio_1` 到 `audio_5` | 通过隐藏 Gradio File 组件上传，再显示为导演台卡片 |
| 视频 | `video_1` 到 `video_5` | 通过隐藏 Gradio File 组件上传，视频卡片显示缩略图 |

素材区和页面上方普通 `scene_canvas_image`、`scene_input_image*`、`scene_audio`、`scene_video` 输入是分开的。导演模式生成时，当前分镜选中的素材会被映射到后端实际输入。

当前策略：

- 当前 preset 不支持某类素材时，该素材区域仍显示。
- 当前 preset 不支持的类型，素材卡片上传和拖拽入口禁用。
- 当前 preset 不支持的类型，分镜里的引用选择也禁用。
- 导演台草稿按 preset 分开保存；切换 preset 会加载对应 preset 的草稿，不保证复用当前素材池。
- 已经存在但当前 preset 不允许的分镜引用会在前端和后端参数构建时清理。

## 分镜规则

图片数量决定分镜形态：

| 图片数量 | 形态 | 输出 |
| --- | --- | --- |
| 0 | Text-to-Video | 不写 `@image` |
| 1 | Image-to-Video / first frame | 写入 1 个图片引用 |
| 2 | First/last frame | 写入首帧和尾帧 |
| 3-5 | Reference set | 写入参考图组 |

音频和视频规则：

- 每个分镜最多选择一个音频引用。
- 每个分镜最多选择一个视频引用。
- 支持串联的 preset 可以选择 `previous_segment`，表示上一段结果。
- 是否允许音频、视频、上一段结果由 `director_capability` 决定。

分镜时长：

- 分镜生成时长来自 `结束 - 开始`。
- 默认写入 `scene_video_duration`。
- preset 可以通过 `director_capability.segment_duration_param` 改写目标参数名。
- `video_duration_min/max` 优先于旧的 `var_number_min/max`。

## Preset 能力字段

当前使用的主要字段：

| 字段 | 常见值 | 说明 |
| --- | --- | --- |
| `director_supported` | `true` / `false` | 是否允许导演台生成 |
| `image_policy` | `optional` / `required` / `forbidden` | 图片引用策略 |
| `audio_policy` | `optional` / `required` / `forbidden` | 音频引用策略 |
| `video_policy` | `optional` / `required` / `forbidden` | 视频引用策略 |
| `min_images` / `max_images` | `0` 到 `5` | 单分镜可选图片数量 |
| `image_modes` | `none`、`first_frame`、`first_last`、`reference_set` | 图片形态 |
| `video_modes` | `none`、`explicit`、`previous_segment` | 视频引用形态 |
| `timeline_format` | `Wan`、`LTXV` 等 | prompt/timeline 格式 |
| `chain_output` | `timeline` / `last_result` | 最终输出策略 |
| `requires_sequential` | `true` / `false` | 是否必须按顺序生成 |
| `duration_strategy` | `shot` / `audio_min` / `video_min` | 单分镜时长策略 |
| `audio_output` | `silent` / `generated` / `input_audio` / `source_audio` | 最终音频来源 |
| `segment_duration_param` | `scene_video_duration` 等 | 分镜时长写入参数 |
| `min_segment_duration` / `max_segment_duration` | 秒 | 单分镜时长范围 |

旧字段 `segment_duration_mode` / `duration_mode` 不再作为当前实现字段维护。

## 代表性 preset

| Preset | 能力概述 |
| --- | --- |
| `Wan(T2V)` | 不使用图片、音频、视频引用，适合纯文本分镜 |
| `Wan(I2V)` | 图片必需，最多 2 张，1 张为首帧，2 张为首尾帧 |
| `Wan-Extent` | 视频必需，允许 `previous_segment` |
| `LTX2.3(T2V)` | 纯文本到视频，不接受素材引用 |
| `LTX2.3(TA2V)` | 文本+音频到视频，音频必需 |
| `LTX2.3(I2V)` | 图片到视频，图片必需，支持首帧/首尾帧 |
| `LTX2.3(IA2V)` | 图片+音频到视频，图片和音频必需 |
| `InfiniteTalk` | 音频必需，导演模式下由导演台校验音频素材 |
| `Wan-Animate` / `Wan-Remover` | 当前不开放导演台生成 |

具体矩阵看 `docs/director-workspace/release-matrix-test-plan.md`。

## 生成行为

`Director mode` 关闭：

- 不写 `director_timeline`。
- 不写 `prompt_override`。
- 当前 preset 按普通模式生成。

`Director mode` 开启：

- 前端把分镜写入隐藏 `scene_director_editor_state`。
- Python 侧构建 runtime。
- 校验素材、图片数量、音频/视频必需项、时长范围。
- 逐分镜构建后端参数。
- 把当前分镜的媒体引用映射到后端输入。
- 把分镜文本写入 `prompt_override` 和 `director_prompt_override`。

`Compose timeline` 开启：

- 分镜生成完成后，使用生成结果、音频策略和合成宽高/FPS 渲染最终时间线视频。
- `Compose width`、`Compose height`、`Compose FPS` 只影响最终合成，不改变单个分镜模型的分辨率和采样参数。
- `Timeline range` 只影响预览轴和编排范围。

## Infinite Canvas

无限画布的 `Director Timeline` 节点和 WebUI 导演台共用同一类能力声明，但交互方式不同：

- WebUI 适合主界面快速分镜生成。
- Infinite Canvas 适合模板化、多节点编排、Result 节点串联和最终合成测试。
- 模板库里保留了 Wan、LTX、InfiniteTalk、Foley、Timeline 合成等导演相关模板。

维护时需要同时确认 WebUI 和 Infinite Canvas 没有偏离同一套 `director_capability` 语义。

## 上线前验证

常用命令：

```powershell
node --check javascript\scene_director.js
node --check javascript\topbar.js
..\python_embeded\python.exe -m py_compile webui.py modules\scene_director_webui.py
..\python_embeded\python.exe -m pytest tests\test_scene_director_webui_contract.py -q --basetemp=.pytest_tmp_scene_director
```

手动检查：

- 中文界面下上传区不出现 `Images`、`Audio`、`Video`、`Click or drop`。
- 英文界面下上传区显示英文。
- 上传音频或视频后，上传区标题和提示不会回到另一种语言。
- 右侧规则说明跟随语言切换。
- 右侧规则说明旁边有 `Director README` / `导演台说明` 链接。
- 当前 preset 不支持音频或视频时，对应素材区域仍显示，但上传、拖拽和分镜引用选择都不可用。
- `Wan(T2V)` 不允许选择图片、音频、视频引用。
- `Wan(I2V)` 最多选择 2 张图片。
- `LTX2.3` 的单分镜时长范围来自当前 preset 声明。
- `previous_segment` 只在支持的 preset 中可选。

浏览器矩阵测试：

```powershell
node tools\director_release_matrix_webui.mjs
```

真实生成 canary：

```powershell
node tools\director_generation_canary.mjs
```

真实生成失败时，先区分以下类别：

- 模型缺失。
- Comfy workflow 节点报错。
- preset 能力声明不准确。
- WebUI 分镜参数构建错误。
- 时间线合成阶段错误。

## 维护注意

- 固定文案统一放在 `javascript/scene_director.js` 的 `SCENE_DIRECTOR_TEXT`。
- Python 输出的 HTML 如果包含固定文案，要加可识别标记。
- WebUI 右侧栏由 `#scene_director_side_panel` 承载，不要把规则说明重新放回独立 grid 行。
- 媒体区域禁止交互时保持可见，避免用户误以为上传区消失。
- capability 字段变更后，同步检查 preset JSON、WebUI、Infinite Canvas、release matrix 和 contract 测试。
