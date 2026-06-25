---
name: create-preset-workflow
description: Use when creating a new SimpAI_Studio preset tab, importing a ComfyUI workflow, or debugging "prompt_no_outputs" / workflow conversion errors. Covers the preset-to-workflow mapping, scene vs non-scene architecture, GeneralInput/SceneInput node conventions, and common pitfalls.
---

# Create Preset & Import Workflow

## Architecture: 3-Layer Mapping

```
presets/{Name}.json  →  task_method  →  workflows/{task_method}_api.json
       (UI config)         (string key)       (ComfyUI API workflow JSON)
```

- **Preset JSON** (`presets/*.json`): defines UI visibility, default models, aspect ratios, and the `task_method` key.
- **Workflow JSON** (`workflows/{task_method}_api.json`): ComfyUI API-format workflow template with parameter placeholders.
- **Rust `convert2comfy(flow_name)`** (`simpleai_base` `.so`): at generation time, reads the workflow template, substitutes UI parameters into it, returns the final prompt dict sent to ComfyUI.

## Scene vs Non-Scene

| Feature | Non-scene (`_aio`) | Scene (`scene_`) |
|---|---|---|
| Preset key | `backend_params.task_method` | `scene_frontend` block |
| Input node | `GeneralInput` (14 outputs) | `SceneInput` (33 outputs) |
| UI | Clean T2I only (no panels) | Full scene panel (themes, canvas, inputs) |
| Example | Z-imageT, Flux, Playground | Wan(T2V), QwenEdit+ |

**Use non-scene** for simple text-to-image presets. **Use scene** when you need canvas, input images, video/audio, or themed multi-mode UI.

## Creating a Non-Scene Preset

### 1. Preset JSON (`presets/MyPreset.json`)

Model after `presets/Z-imageT.json`:

```json
{
    "default_engine": {
        "backend_engine": "Comfy",
        "disvisible": ["input_image_checkbox", "prompt_panel_checkbox", "performance_selection", "refiner_model", "backend_selection"],
        "disinteractive": ["input_image_checkbox", "prompt_panel_checkbox", "performance_selection", "refiner_model"],
        "available_aspect_ratios_selection": "Custom",
        "custom_aspect_ratios": ["1024*1024", "1152*896", "896*1152"],
        "backend_params": {
            "task_method": "my_preset_aio"
        },
        "resolution_control": {
            "mode": "standard", "source": "none",
            "base_width": 1024, "base_height": 1024, "quantize": 16,
            "interactive": true, "frontend_preprocess": false,
            "preprocess_target": "none", "preprocess_fit": "scale"
        }
    },
    "default_model": "model-file.safetensors",
    "default_refiner": "None",
    "default_refiner_switch": 0.5,
    "default_cfg_scale": 4,
    "default_sample_sharpness": 2,
    "default_sampler": "euler",
    "default_scheduler": "simple",
    "default_performance": "Speed",
    "default_styles": [],
    "default_aspect_ratio": "1024*1024",
    "default_overwrite_step": 20,
    "checkpoint_downloads": {},
    "embeddings_downloads": {},
    "lora_downloads": {},
    "model_list": [
        "checkpoints,model-file.safetensors,13875718056,0,"
    ]
}
```

Key points:
- `backend_engine`: `"Comfy"` for standard ComfyUI, `"Z-image"` / `"Wan"` / `"Qwen"` for special engines.
- `backend_params.task_method` must match the workflow filename (without `_api.json`).
- `topbar.py` auto-scans `presets/*.json` to generate nav buttons. No manual registration needed.

### 2. Workflow JSON (`workflows/my_preset_aio_api.json`)

#### GeneralInput Node (required)

Every non-scene workflow MUST have a `GeneralInput` node. Its outputs feed parameters to other nodes:

| Output idx | Name | Type |
|---|---|---|
| 0 | prompt | STRING |
| 1 | negative_prompt | STRING |
| 2 | width | INT |
| 3 | height | INT |
| 4 | cfg | FLOAT |
| 5 | steps | INT |
| 6 | refiner_step | INT |
| 7 | sampler | STRING |
| 8 | scheduler | STRING |
| 9 | denoise | FLOAT |
| 10 | clip_skip | INT |
| 11 | inpaint_disable_initial_latent | BOOLEAN |
| 12 | wavespeed_strength | FLOAT |
| 13 | save_final_enhanced_image_only | BOOLEAN |

GeneralInput node definition: `comfy/custom_nodes/params_input.py:13-31`.

#### SeedInput Node (required)

```json
"417": {
    "inputs": { "seed": 0 },
    "class_type": "SeedInput",
    "_meta": { "title": "SeedInput" }
}
```

Node IDs are NOT fixed across workflows. The Rust `convert2comfy()` finds nodes by `class_type`, not by ID. However, using conventional IDs (728 for GeneralInput, 417 for SeedInput) is recommended for consistency with other `_aio` workflows.

#### CRITICAL: Output Node Requirement

ComfyUI rejects prompts without at least one `OUTPUT_NODE = True` node. This is the most common pitfall.

| Node type | OUTPUT_NODE | Notes |
|---|---|---|
| `PreviewImage` | **True** | Always include at least one |
| `SaveImage` | **True** | Standard save |
| `SaveImageWebsocketLazy` | **False** | Pass-through, sends via websocket |
| `SaveImageWebsocket` | **True** | Terminal, but less common in `_aio` |

**Rule:** Every workflow must have at least one `PreviewImage` (or other `OUTPUT_NODE=True` node). `SaveImageWebsocketLazy` alone will cause `prompt_no_outputs` error.

Typical pattern (from working workflows):
```json
"381": {
    "inputs": {
        "images": ["8", 0],
        "format": "JPEG"
    },
    "class_type": "SaveImageWebsocketLazy",
    "_meta": { "title": "SaveImageWebsocketLazy" }
},
"348": {
    "inputs": {
        "images": ["381", 0]
    },
    "class_type": "PreviewImage",
    "_meta": { "title": "PreviewImage" }
}
```

Note: `SaveImageWebsocketLazy` requires `format` input (`"PNG"`, `"JPEG"`, or `"WEBP"`).

#### Model Loading

- **Checkpoint models** (SD1.5, SDXL, Playground): use `CheckpointLoaderSimple` (provides MODEL, CLIP, VAE).
- **Diffusion models** (Flux, Z-imageT): use `UNETLoader` + separate `DualCLIPLoader` + `VAELoader`.

The Rust code substitutes the `base_model` parameter into the loader node's `ckpt_name` or `unet_name` field.

#### Minimal Working T2I Workflow Example

```json
{
    "4": {
        "inputs": { "ckpt_name": "model.safetensors" },
        "class_type": "CheckpointLoaderSimple"
    },
    "417": {
        "inputs": { "seed": 0 },
        "class_type": "SeedInput"
    },
    "728": {
        "inputs": {
            "prompt": "", "negative_prompt": "",
            "width": 1024, "height": 1024,
            "cfg": 4.0, "steps": 20, "refiner_step": 999,
            "sampler": "euler", "scheduler": "simple", "denoise": 1.0,
            "clip_skip": -1, "inpaint_disable_initial_latent": false,
            "wavespeed_strength": 0, "save_final_enhanced_image_only": false
        },
        "class_type": "GeneralInput"
    },
    "6": {
        "inputs": { "text": ["728", 0], "clip": ["4", 1] },
        "class_type": "CLIPTextEncode"
    },
    "7": {
        "inputs": { "text": ["728", 1], "clip": ["4", 1] },
        "class_type": "CLIPTextEncode"
    },
    "5": {
        "inputs": { "width": ["728", 2], "height": ["728", 3], "batch_size": 1 },
        "class_type": "EmptyLatentImage"
    },
    "3": {
        "inputs": {
            "seed": ["417", 0], "steps": ["728", 5], "cfg": ["728", 4],
            "sampler_name": ["728", 7], "scheduler": ["728", 8],
            "denoise": 1.0, "model": ["MODEL_NODE", 0],
            "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]
        },
        "class_type": "KSampler"
    },
    "8": {
        "inputs": { "samples": ["3", 0], "vae": ["4", 2] },
        "class_type": "VAEDecode"
    },
    "381": {
        "inputs": { "images": ["8", 0], "format": "JPEG" },
        "class_type": "SaveImageWebsocketLazy"
    },
    "348": {
        "inputs": { "images": ["381", 0] },
        "class_type": "PreviewImage"
    }
}
```

### 3. Verify Node Types

Before testing, verify all node `class_type` values exist in the running ComfyUI backend:

```bash
curl -s http://localhost:9187/object_info | python3 -c "
import sys, json
d = json.load(sys.stdin)
for n in ['GeneralInput', 'SeedInput', 'PreviewImage', ...]:
    print(f'  {n}: {\"OK\" if n in d else \"MISSING\"}')"
```

Also check `output_node` flag for output nodes:

```bash
curl -s http://localhost:9187/object_info/SaveImageWebsocketLazy | python3 -c "
import sys, json; d=json.load(sys.stdin)
print('output_node:', d['SaveImageWebsocketLazy']['output_node'])"
```

### 4. Test convert2comfy

The Rust `convert2comfy()` uses `sys.argv[0]`'s directory as root. Must run from a `.py` file inside SimpAI_Studio (NOT `python -c`):

```python
# save as /home/dcy-server/SimpAI_Studio/test_wf.py
import os, sys, json, httpx
os.chdir('/home/dcy-server/SimpAI_Studio')
sys.path.insert(0, '/home/dcy-server/SimpAI_Studio')
from simpleai_base import simpleai_base
simpleai_base.init_local()
from simpleai_base.params_mapper import ComfyTaskParams

params = {
    'base_model': 'model.safetensors', 'prompt': 'test',
    'negative_prompt': '', 'width': 1024, 'height': 1024,
    'cfg_scale': 4, 'steps': 20, 'sampler': 'euler',
    'scheduler': 'simple', 'denoise': 1.0, 'seed': 1,
}
ctp = ComfyTaskParams(params)
prompt = ctp.convert2comfy('my_preset_aio')
print(f'Nodes: {len(prompt)}')
# Submit to ComfyUI backend
r = httpx.post('http://127.0.0.1:9187/prompt',
    json={'prompt': prompt, 'client_id': 'test'}, timeout=10)
print(f'Status: {r.status_code} {r.text[:300]}')
```

Run: `/home/dcy-server/.conda/envs/simpai/bin/python test_wf.py`

### 5. Restart & Test

```bash
setsid bash /home/dcy-server/SimpAI_Studio/start.sh 1 > /tmp/simpai_launch.log 2>&1 &
```

Hard refresh browser (Ctrl+Shift+R), switch to the new preset, generate.

## Creating a Scene Preset

For scene presets (canvas, input images, video/audio), model after `presets/Wan(T2V).json` or `presets/QwenEdit+.json`. Key differences:

1. Use `scene_frontend` block instead of `backend_params`
2. `task_method` inside `scene_frontend` maps theme names to workflow names
3. Workflow uses `SceneInput` node (33 outputs) instead of `GeneralInput`
4. Workflow filename starts with `scene_` prefix

SceneInput output mapping: 0=prompt, 1=additional_prompt, 6=width, 7=height, 8=cfg, 9=steps, 29=negative_prompt, 30=sampler, 31=scheduler.

SceneInput node definition: `comfy/custom_nodes/params_input.py:45-94`.

## Common Pitfalls

### 1. `prompt_no_outputs`
**Cause:** No `OUTPUT_NODE=True` node in workflow. `SaveImageWebsocketLazy` has `OUTPUT_NODE=False`.
**Fix:** Add a `PreviewImage` node.

### 2. Rust `convert2comfy` returns empty `{}`
**Cause:** Root directory not found. Rust uses `sys.argv[0]`'s dirname as root.
**Fix:** Run test from a `.py` file inside SimpAI_Studio, not `python -c`.

### 3. Missing `format` input on `SaveImageWebsocketLazy`
**Cause:** Node requires `format` field (`"PNG"`, `"JPEG"`, `"WEBP"`).
**Fix:** Add `"format": "JPEG"` to node inputs.

### 4. `topbar.py` KeyError after adding preset
**Cause:** Preset JSON missing required fields or has unexpected structure.
**Fix:** Ensure all fields match the Z-imageT template structure.

### 5. Model not found
**Cause:** `model_list` entry has wrong path or size.
**Format:** `"category,filename,size_bytes,0,download_url"` (download_url can be empty).

## Reference Files

| File | Purpose |
|---|---|
| `presets/Z-imageT.json` | Non-scene T2I preset template |
| `presets/Wan(T2V).json` | Scene video preset template |
| `presets/Playground.json` | Non-scene T2I preset (simplest) |
| `comfy/custom_nodes/params_input.py:13-31` | GeneralInput definition |
| `comfy/custom_nodes/params_input.py:45-94` | SceneInput definition |
| `comfy/custom_nodes/websocket_save.py:45-73` | SaveImageWebsocketLazy (OUTPUT_NODE=False) |
| `enhanced/comfy_task.py` | Task routing, mapping rules |
| `enhanced/topbar.py` | Preset scanning, scene schema builder |
| `modules/async_worker.py:2341-2375` | Parameter assembly for Comfy tasks |
| `~/.conda/envs/simpai/lib/.../simpleai_base/comfyclient_pipeline.py` | process_flow, queue_prompt, get_images |
| `~/.conda/envs/simpai/lib/.../simpleai_base/params_mapper.py` | ComfyTaskParams Python wrapper |
