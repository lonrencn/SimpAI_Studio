from __future__ import annotations

import importlib.util
import os
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXTENSION_DIR = ROOT / "forge_neo" / "webui" / "extensions" / "sd-webui-multimodal-media"
SCRIPTS_DIR = EXTENSION_DIR / "scripts"
SOURCE_WEBUI_ROOT = ROOT / "forge_neo" / "webui"
VIDEO_FRAME_OUTPUT_DIR = SOURCE_WEBUI_ROOT / "outputs" / "video-frames"
QWEN3_TTS_OUTPUT_DIR = SOURCE_WEBUI_ROOT / "outputs" / "qwen3-tts"
QWEN_VIDEO_OUTPUT_DIR = SOURCE_WEBUI_ROOT / "outputs" / "qwen-video"
LATENT_SYNC_OUTPUT_DIR = SOURCE_WEBUI_ROOT / "outputs" / "latent-sync"
ACE_STEP_OUTPUT_DIR = SOURCE_WEBUI_ROOT / "outputs" / "ace-step"
INDEX_TTS_OUTPUT_DIR = SOURCE_WEBUI_ROOT / "outputs" / "indextts-2"
QWEN3_TTS_CONFIG_DIR = EXTENSION_DIR / "config" / "qwen3_tts"
LATENT_SYNC_DIR = EXTENSION_DIR / "LatentSync"
ACE_STEP_DIR = EXTENSION_DIR / "ACE-Step-1.5"
INDEX_TTS_DIR = EXTENSION_DIR / "index-tts"
INDEX_TTS_MODEL_DIR = SOURCE_WEBUI_ROOT / "models" / "indextts-2"
QWEN3_TTS_MODELS = (
    ("Base - voice clone", "Base"),
    ("CustomVoice - preset speakers", "CustomVoice"),
    ("VoiceDesign - designed voice", "VoiceDesign"),
)
QWEN3_TTS_LANGUAGES = (
    ("Chinese", "Chinese"),
    ("English", "English"),
    ("Japanese", "Japanese"),
    ("Korean", "Korean"),
    ("German", "German"),
    ("French", "French"),
    ("Russian", "Russian"),
    ("Portuguese", "Portuguese"),
    ("Spanish", "Spanish"),
    ("Italian", "Italian"),
)
QWEN3_TTS_SPEAKERS = (
    ("Vivian", "Vivian"),
    ("Serena", "Serena"),
    ("Uncle_Fu", "Uncle_Fu"),
    ("Dylan", "Dylan"),
    ("Eric", "Eric"),
    ("Ryan", "Ryan"),
    ("Aiden", "Aiden"),
    ("Ono_Anna", "Ono_Anna"),
    ("Sohee", "Sohee"),
)
QWEN_VIDEO_MODES = (
    ("Image to video wan2.6", "wan26_i2v"),
    ("Image to video wan2.5", "wan25_i2v"),
    ("Keyframes to video wan2.2", "wan22_kf2v"),
    ("Text to video wan2.5", "wan25_t2v"),
)
QWEN_VIDEO_RESOLUTIONS = ("720P", "1080P")
QWEN_VIDEO_T2V_RESOLUTIONS = ("832*480", "720P", "1080P")
QWEN_VIDEO_SHOT_TYPES = (("Single", "single"), ("Multi", "multi"))
LATENT_SYNC_MODEL_CONFIGS = {
    "LatentSync": {
        "config_path": LATENT_SYNC_DIR / "configs" / "unet" / "stage2.yaml",
        "checkpoint_path": SOURCE_WEBUI_ROOT / "models" / "LatentSync" / "checkpoints" / "latentsync_unet.pt",
        "vae_path": SOURCE_WEBUI_ROOT / "models" / "LatentSync" / "checkpoints" / "sd-vae-ft-mse",
    }
}
ACE_STEP_MODEL_VERSIONS = ("ACE-Step-v15-xl-turbo",)
ACE_STEP_KEY_SCALES = (
    "C major", "C minor", "C# major", "C# minor",
    "D major", "D minor", "D# major", "D# minor",
    "E major", "E minor",
    "F major", "F minor", "F# major", "F# minor",
    "G major", "G minor", "G# major", "G# minor",
    "A major", "A minor", "A# major", "A# minor",
    "B major", "B minor",
)
ACE_STEP_TIME_SIGNATURES = ("2/4", "3/4", "4/4", "6/8")
ACE_STEP_LANGUAGES = ("en", "zh", "ja", "ko", "fr", "de", "es", "it", "ru", "unknown")
INDEX_TTS_LANGUAGES = (("Chinese", "zh_CN"), ("English", "en_US"))
INDEX_TTS_EMOTION_MODES = (
    "与音色参考音频相同",
    "使用情感参考音频",
    "使用情感向量控制",
    "使用情感描述文本控制",
)
INDEX_TTS_REQUIRED_MODEL_FILES = (
    "bpe.model",
    "gpt.pth",
    "config.yaml",
    "s2mel.pth",
    "wav2vec2bert_stats.pt",
)


def _dependency_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def multimodal_media_defaults() -> dict[str, Any]:
    return {
        "frame_quality": 85,
        "frame_mode": "uniform",
    }


def _qwen3_tts_presets() -> list[str]:
    if not QWEN3_TTS_CONFIG_DIR.is_dir():
        return []
    return sorted(path.stem for path in QWEN3_TTS_CONFIG_DIR.glob("*.json"))


def qwen3_tts_defaults() -> dict[str, Any]:
    return {
        "models": [{"label": label, "value": value} for label, value in QWEN3_TTS_MODELS],
        "languages": [{"label": label, "value": value} for label, value in QWEN3_TTS_LANGUAGES],
        "speakers": [{"label": label, "value": value} for label, value in QWEN3_TTS_SPEAKERS],
        "default_model": "CustomVoice",
        "default_language": "Chinese",
        "default_speaker": "Vivian",
        "default_voice_design": "A warm young female voice with clear pronunciation.",
        "output_dir": str(QWEN3_TTS_OUTPUT_DIR),
        "presets": _qwen3_tts_presets(),
    }


def qwen_video_defaults() -> dict[str, Any]:
    return {
        "modes": [{"label": label, "value": value} for label, value in QWEN_VIDEO_MODES],
        "resolutions": list(QWEN_VIDEO_RESOLUTIONS),
        "t2v_resolutions": list(QWEN_VIDEO_T2V_RESOLUTIONS),
        "shot_types": [{"label": label, "value": value} for label, value in QWEN_VIDEO_SHOT_TYPES],
        "default_mode": "wan26_i2v",
        "default_resolution": "720P",
        "default_t2v_resolution": "832*480",
        "default_duration": 10,
        "default_audio_enabled": True,
        "default_shot_type": "multi",
        "output_dir": str(QWEN_VIDEO_OUTPUT_DIR),
        "endpoint": "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis",
    }


def latent_sync_defaults() -> dict[str, Any]:
    return {
        "models": list(LATENT_SYNC_MODEL_CONFIGS.keys()),
        "default_model": "LatentSync",
        "default_guidance_scale": 1.5,
        "default_inference_steps": 20,
        "default_seed": 1247,
        "output_dir": str(LATENT_SYNC_OUTPUT_DIR),
        "model_files": {
            name: {
                "config_path": str(paths["config_path"]),
                "config_exists": paths["config_path"].is_file(),
                "checkpoint_path": str(paths["checkpoint_path"]),
                "checkpoint_exists": paths["checkpoint_path"].is_file(),
                "vae_path": str(paths["vae_path"]),
                "vae_exists": paths["vae_path"].exists(),
            }
            for name, paths in LATENT_SYNC_MODEL_CONFIGS.items()
        },
    }


def ace_step_defaults() -> dict[str, Any]:
    return {
        "models": list(ACE_STEP_MODEL_VERSIONS),
        "default_model": "ACE-Step-v15-xl-turbo",
        "default_duration": 30,
        "default_infer_steps": 8,
        "default_guidance_scale": 1.0,
        "default_bpm": 120,
        "key_scales": list(ACE_STEP_KEY_SCALES),
        "default_key_scale": "E minor",
        "time_signatures": list(ACE_STEP_TIME_SIGNATURES),
        "default_time_signature": "4/4",
        "languages": list(ACE_STEP_LANGUAGES),
        "default_language": "zh",
        "source_dir": str(ACE_STEP_DIR),
        "model_dir": str(SOURCE_WEBUI_ROOT / "models" / "ace-step"),
        "output_dir": str(ACE_STEP_OUTPUT_DIR),
    }


def index_tts_defaults() -> dict[str, Any]:
    return {
        "languages": [{"label": label, "value": value} for label, value in INDEX_TTS_LANGUAGES],
        "emotion_modes": list(INDEX_TTS_EMOTION_MODES),
        "default_language": "zh_CN",
        "default_emotion_mode": "与音色参考音频相同",
        "default_emotion_weight": 1.0,
        "default_top_p": 0.8,
        "default_top_k": 50,
        "default_temperature": 0.8,
        "default_length_penalty": 1.0,
        "default_num_beams": 1,
        "default_repetition_penalty": 1.2,
        "default_max_mel_tokens": 500,
        "default_max_text_tokens_per_segment": 120,
        "model_dir": str(INDEX_TTS_MODEL_DIR),
        "model_files": {name: (INDEX_TTS_MODEL_DIR / name).is_file() for name in INDEX_TTS_REQUIRED_MODEL_FILES},
        "output_dir": str(INDEX_TTS_OUTPUT_DIR),
        "source_dir": str(INDEX_TTS_DIR),
    }


def multimodal_media_status() -> dict[str, Any]:
    dependencies = {
        "cv2": _dependency_available("cv2"),
        "numpy": _dependency_available("numpy"),
        "ffmpeg": _dependency_available("ffmpeg"),
        "dashscope": _dependency_available("dashscope"),
        "qwen_tts": _dependency_available("qwen_tts"),
        "torchaudio": _dependency_available("torchaudio"),
        "soundfile": _dependency_available("soundfile"),
        "resampy": _dependency_available("resampy"),
        "librosa": _dependency_available("librosa"),
        "insightface": _dependency_available("insightface"),
        "onnxruntime": _dependency_available("onnxruntime"),
    }
    return {
        "extension_dir": str(EXTENSION_DIR),
        "scripts_dir": str(SCRIPTS_DIR),
        "source_available": EXTENSION_DIR.is_dir(),
        "dependencies": dependencies,
        "output_dirs": {
            "video_frames": str(VIDEO_FRAME_OUTPUT_DIR),
            "qwen3_tts": str(QWEN3_TTS_OUTPUT_DIR),
            "qwen_video": str(QWEN_VIDEO_OUTPUT_DIR),
            "latent_sync": str(LATENT_SYNC_OUTPUT_DIR),
            "ace_step": str(ACE_STEP_OUTPUT_DIR),
            "index_tts": str(INDEX_TTS_OUTPUT_DIR),
        },
        "submodules": {
            "video_frame_extractor": (SCRIPTS_DIR / "video_frame_extractor.py").is_file(),
            "qwen3_tts": (SCRIPTS_DIR / "qwen3_tts_ui.py").is_file(),
            "qwen_video": (SCRIPTS_DIR / "qwen_video" / "main_ui.py").is_file(),
            "ace_step": (SCRIPTS_DIR / "ace_step_ui.py").is_file(),
            "latent_sync": LATENT_SYNC_DIR.is_dir(),
            "index_tts": INDEX_TTS_DIR.is_dir(),
        },
        "capabilities": {
            "video_frames": (SCRIPTS_DIR / "video_frame_extractor.py").is_file(),
            "qwen3_tts": (SCRIPTS_DIR / "qwen3_tts_ui.py").is_file(),
            "qwen_video": (SCRIPTS_DIR / "qwen_video" / "main_ui.py").is_file(),
            "latent_sync": (SCRIPTS_DIR / "latent_sync_ui.py").is_file() and LATENT_SYNC_DIR.is_dir(),
            "ace_step": (SCRIPTS_DIR / "ace_step_ui.py").is_file() and ACE_STEP_DIR.is_dir(),
            "index_tts": (SCRIPTS_DIR / "indextts_ui.py").is_file() and INDEX_TTS_DIR.is_dir(),
        },
        "qwen3_tts_presets": _qwen3_tts_presets(),
        "qwen3_tts": qwen3_tts_defaults(),
        "qwen_video": qwen_video_defaults(),
        "latent_sync": latent_sync_defaults(),
        "ace_step": ace_step_defaults(),
        "index_tts": index_tts_defaults(),
        "defaults": multimodal_media_defaults(),
    }


def _source_module(module_name: str):
    if not SCRIPTS_DIR.is_dir():
        raise FileNotFoundError(f"Multimodal Media scripts directory is missing: {SCRIPTS_DIR}")
    module_path = SCRIPTS_DIR / f"{module_name}.py"
    if not module_path.is_file():
        raise FileNotFoundError(f"Multimodal Media source module is missing: {module_path}")
    cache_key = f"forge_neo_multimodal_media_source_{module_name}"
    if cache_key in sys.modules:
        return sys.modules[cache_key]
    spec = importlib.util.spec_from_file_location(cache_key, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load Multimodal Media source module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    added_paths: list[str] = []
    for path in (str(EXTENSION_DIR), str(SCRIPTS_DIR)):
        if path not in sys.path:
            sys.path.insert(0, path)
            added_paths.append(path)
    try:
        sys.modules[cache_key] = module
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(cache_key, None)
        raise
    finally:
        for path in added_paths:
            try:
                sys.path.remove(path)
            except ValueError:
                pass
    return module


def _qwen_video_module(module_name: str):
    package_dir = SCRIPTS_DIR / "qwen_video"
    module_path = package_dir / f"{module_name}.py"
    if not module_path.is_file():
        raise FileNotFoundError(f"Qwen Video source module is missing: {module_path}")
    added_paths: list[str] = []
    for path in (str(EXTENSION_DIR), str(SCRIPTS_DIR)):
        if path not in sys.path:
            sys.path.insert(0, path)
            added_paths.append(path)
    try:
        import importlib

        return importlib.import_module(f"qwen_video.{module_name}")
    finally:
        for path in added_paths:
            try:
                sys.path.remove(path)
            except ValueError:
                pass


def _file_path_from_value(value: object) -> str:
    if isinstance(value, str) and Path(value).is_file():
        return value
    if isinstance(value, dict):
        for key in ("name", "path", "file"):
            candidate = value.get(key)
            if isinstance(candidate, str) and Path(candidate).is_file():
                return candidate
    if hasattr(value, "name") and isinstance(value.name, str) and Path(value.name).is_file():
        return value.name
    return ""


def _qwen_video_result_html(text: str) -> str:
    video_url = ""
    for line in str(text or "").splitlines():
        if line.startswith("视频URL:"):
            video_url = line.replace("视频URL:", "", 1).strip()
            break
    if not video_url:
        return ""
    escaped = video_url.replace('"', "%22")
    return (
        '<div class="forge-neo-qwen-video-player">'
        f'<video src="{escaped}" controls preload="metadata"></video>'
        f'<a href="{escaped}" target="_blank" rel="noopener noreferrer">Open video</a>'
        "</div>"
    )


def qwen_video_set_api_key(api_key: object) -> dict[str, Any]:
    key = str(api_key or "").strip()
    if not key:
        has_key = bool(os.getenv("DASHSCOPE_API_KEY"))
        message = "DASHSCOPE_API_KEY is already set in environment." if has_key else "API key is empty."
        return {"ok": has_key, "message": message, "has_key": has_key}
    try:
        module = _qwen_video_module("api_handler")
        message = module.set_api_key(key)
    except Exception as exc:
        return {"ok": False, "message": f"Qwen Video API key setup failed: {exc}", "has_key": False}
    return {"ok": True, "message": str(message or "API key set."), "has_key": True}


def qwen_video_generate(
    *,
    mode: object,
    prompt: object,
    image: object = None,
    first_frame: object = None,
    last_frame: object = None,
    audio: object = None,
    resolution: object = "720P",
    duration: object = 10,
    audio_enabled: object = True,
    shot_type: object = "multi",
) -> dict[str, Any]:
    actual_mode = str(mode or "wan26_i2v")
    actual_prompt = str(prompt or "").strip()
    if not actual_prompt:
        return {"ok": False, "message": "Prompt is required.", "video_html": "", "output_dir": str(QWEN_VIDEO_OUTPUT_DIR)}
    try:
        duration_value = max(1, min(int(float(str(duration or 10))), 30))
    except Exception:
        duration_value = 10
    try:
        module = _qwen_video_module("video_models")
    except Exception as exc:
        return {"ok": False, "message": f"Qwen Video is not available: {exc}", "video_html": "", "output_dir": str(QWEN_VIDEO_OUTPUT_DIR)}
    image_path = _file_path_from_value(image)
    first_frame_path = _file_path_from_value(first_frame)
    last_frame_path = _file_path_from_value(last_frame)
    audio_path = _file_path_from_value(audio)
    actual_resolution = str(resolution or "720P")
    try:
        if actual_mode == "wan25_i2v":
            if not image_path:
                return {"ok": False, "message": "Image is required for wan2.5 image-to-video.", "video_html": "", "output_dir": str(QWEN_VIDEO_OUTPUT_DIR)}
            result_text = module.generate_video_with_wan25_i2v(actual_prompt, image_path, audio_path or None, actual_resolution, duration_value, bool(audio_enabled))
        elif actual_mode == "wan22_kf2v":
            if not first_frame_path or not last_frame_path:
                return {"ok": False, "message": "First and last frame images are required.", "video_html": "", "output_dir": str(QWEN_VIDEO_OUTPUT_DIR)}
            result_text = module.generate_video_with_wan22_kf2v(actual_prompt, first_frame_path, last_frame_path, actual_resolution)
        elif actual_mode == "wan25_t2v":
            result_text = module.generate_video_with_wan25_t2v(actual_prompt, audio_path or None, actual_resolution, duration_value, bool(audio_enabled))
        else:
            if not image_path:
                return {"ok": False, "message": "Image is required for wan2.6 image-to-video.", "video_html": "", "output_dir": str(QWEN_VIDEO_OUTPUT_DIR)}
            actual_shot = str(shot_type or "multi")
            if actual_shot not in {"single", "multi"}:
                actual_shot = "multi"
            result_text = module.generate_video_with_wan26(actual_prompt, image_path, audio_path or None, actual_resolution, duration_value, bool(audio_enabled), actual_shot)
    except Exception as exc:
        return {"ok": False, "message": f"Qwen Video generation failed: {exc}", "video_html": "", "output_dir": str(QWEN_VIDEO_OUTPUT_DIR)}
    text = str(result_text or "")
    failed = text.startswith("❌") or text.startswith("⚠")
    return {
        "ok": bool(text and not failed),
        "message": text,
        "video_html": _qwen_video_result_html(text),
        "output_dir": str(QWEN_VIDEO_OUTPUT_DIR),
    }


def qwen_video_query(task_id: object) -> dict[str, Any]:
    actual_task_id = str(task_id or "").strip()
    if not actual_task_id:
        return {"ok": False, "message": "Task ID is required.", "output_dir": str(QWEN_VIDEO_OUTPUT_DIR)}
    try:
        module = _qwen_video_module("task_query")
        result_text = module.query_video_task(actual_task_id)
    except Exception as exc:
        return {"ok": False, "message": f"Qwen Video task query failed: {exc}", "output_dir": str(QWEN_VIDEO_OUTPUT_DIR)}
    text = str(result_text or "")
    return {"ok": bool(text and not text.startswith("❌") and not text.startswith("⚠")), "message": text, "output_dir": str(QWEN_VIDEO_OUTPUT_DIR)}


def qwen_video_recent_tasks() -> list[list[str]]:
    try:
        module = _qwen_video_module("task_query")
        tasks = module.get_recent_tasks()
    except Exception:
        return []
    rows: list[list[str]] = []
    for task in tasks or []:
        rows.append([
            str(task.get("task_id", "")),
            str(task.get("status", "")),
            str(task.get("submit_time", "")),
            str(task.get("model", "")),
        ])
    return rows


def latent_sync_generate(
    *,
    video: object,
    audio: object,
    guidance_scale: object,
    inference_steps: object,
    seed: object,
    model_name: object,
) -> dict[str, Any]:
    video_path = _file_path_from_value(video)
    audio_path = _file_path_from_value(audio)
    if not video_path:
        return {"ok": False, "message": "Video is required.", "video": None, "output_dir": str(LATENT_SYNC_OUTPUT_DIR)}
    if not audio_path:
        return {"ok": False, "message": "Audio is required.", "video": None, "output_dir": str(LATENT_SYNC_OUTPUT_DIR)}
    actual_model = str(model_name or "LatentSync")
    if actual_model not in LATENT_SYNC_MODEL_CONFIGS:
        actual_model = "LatentSync"
    try:
        guidance_value = max(1.0, min(float(str(guidance_scale or 1.5)), 3.0))
    except Exception:
        guidance_value = 1.5
    try:
        step_value = max(10, min(int(float(str(inference_steps or 20))), 50))
    except Exception:
        step_value = 20
    try:
        seed_value = int(float(str(seed or 1247)))
    except Exception:
        seed_value = 1247
    try:
        module = _source_module("latent_sync_ui")
        output_path = module.process_video(video_path, audio_path, guidance_value, step_value, seed_value, actual_model)
    except Exception as exc:
        return {"ok": False, "message": f"LatentSync generation failed: {exc}", "video": None, "output_dir": str(LATENT_SYNC_OUTPUT_DIR)}
    return {
        "ok": bool(output_path and Path(str(output_path)).is_file()),
        "message": f"LatentSync generation finished: {output_path}",
        "video": str(output_path) if output_path else None,
        "output_dir": str(LATENT_SYNC_OUTPUT_DIR),
    }


def ace_step_generate(
    *,
    prompt: object,
    lyrics: object,
    duration: object,
    infer_steps: object,
    guidance_scale: object,
    model_version: object,
    bpm: object,
    key_scale: object,
    time_signature: object,
    vocal_language: object,
) -> dict[str, Any]:
    actual_prompt = str(prompt or "").strip()
    if not actual_prompt:
        return {"ok": False, "message": "Style prompt is required.", "audio": None, "output_dir": str(ACE_STEP_OUTPUT_DIR)}
    actual_model = str(model_version or "ACE-Step-v15-xl-turbo")
    if actual_model not in ACE_STEP_MODEL_VERSIONS:
        actual_model = "ACE-Step-v15-xl-turbo"
    try:
        duration_value = max(5, min(int(float(str(duration or 30))), 300))
    except Exception:
        duration_value = 30
    try:
        steps_value = max(4, min(int(float(str(infer_steps or 8))), 50))
    except Exception:
        steps_value = 8
    try:
        guidance_value = max(1.0, min(float(str(guidance_scale or 1.0)), 20.0))
    except Exception:
        guidance_value = 1.0
    try:
        bpm_value = int(float(str(bpm or 120)))
    except Exception:
        bpm_value = 120
    try:
        module = _source_module("ace_step_ui")
        audio_path, error = module.generate_music(
            actual_prompt,
            str(lyrics or ""),
            duration_value,
            steps_value,
            guidance_value,
            actual_model,
            bpm_value,
            str(key_scale or "E minor"),
            str(time_signature or "4/4"),
            str(vocal_language or "zh"),
        )
    except Exception as exc:
        return {"ok": False, "message": f"ACE-Step generation failed: {exc}", "audio": None, "output_dir": str(ACE_STEP_OUTPUT_DIR)}
    message = str(error or f"ACE-Step generation finished: {audio_path}")
    return {
        "ok": bool(audio_path and Path(str(audio_path)).is_file() and not error),
        "message": message,
        "audio": str(audio_path) if audio_path else None,
        "output_dir": str(ACE_STEP_OUTPUT_DIR),
    }


def ace_step_analyze(audio: object, model_version: object) -> dict[str, Any]:
    audio_path = _file_path_from_value(audio)
    if not audio_path:
        return {"ok": False, "message": "Reference audio is required.", "values": {}, "output_dir": str(ACE_STEP_OUTPUT_DIR)}
    actual_model = str(model_version or "ACE-Step-v15-xl-turbo")
    if actual_model not in ACE_STEP_MODEL_VERSIONS:
        actual_model = "ACE-Step-v15-xl-turbo"
    try:
        module = _source_module("ace_step_ui")
        status, prompt, lyrics, bpm, duration, key_scale, language, time_signature = module.analyze_src_audio_wrapper(audio_path, actual_model)
    except Exception as exc:
        return {"ok": False, "message": f"ACE-Step audio analysis failed: {exc}", "values": {}, "output_dir": str(ACE_STEP_OUTPUT_DIR)}
    return {
        "ok": str(status or "").startswith("✅"),
        "message": str(status or ""),
        "values": {
            "prompt": prompt or "",
            "lyrics": lyrics or "",
            "bpm": bpm or ace_step_defaults()["default_bpm"],
            "duration": duration or ace_step_defaults()["default_duration"],
            "key_scale": key_scale or ace_step_defaults()["default_key_scale"],
            "language": language or ace_step_defaults()["default_language"],
            "time_signature": time_signature or ace_step_defaults()["default_time_signature"],
        },
        "output_dir": str(ACE_STEP_OUTPUT_DIR),
    }


def index_tts_generate(
    *,
    text: object,
    language: object,
    prompt_audio: object,
    emotion_mode: object,
    emotion_reference_audio: object = None,
    emotion_weight: object = 1.0,
    emotion_text: object = "",
    vectors: object = None,
    do_sample: object = True,
    top_p: object = 0.8,
    top_k: object = 50,
    temperature: object = 0.8,
    length_penalty: object = 1.0,
    num_beams: object = 1,
    repetition_penalty: object = 1.2,
    max_mel_tokens: object = 500,
    max_text_tokens_per_segment: object = 120,
) -> dict[str, Any]:
    actual_text = str(text or "").strip()
    if not actual_text:
        return {"ok": False, "message": "Text is required.", "audio": None, "output_dir": str(INDEX_TTS_OUTPUT_DIR)}
    prompt_audio_path = _file_path_from_value(prompt_audio)
    if not prompt_audio_path:
        return {"ok": False, "message": "Reference audio is required.", "audio": None, "output_dir": str(INDEX_TTS_OUTPUT_DIR)}
    actual_language = str(language or "zh_CN")
    if actual_language not in {value for _, value in INDEX_TTS_LANGUAGES}:
        actual_language = "zh_CN"
    actual_mode = str(emotion_mode or INDEX_TTS_EMOTION_MODES[0])
    if actual_mode not in INDEX_TTS_EMOTION_MODES:
        actual_mode = INDEX_TTS_EMOTION_MODES[0]
    vector_values = list(vectors or [])
    while len(vector_values) < 8:
        vector_values.append(0)
    try:
        module = _source_module("indextts_ui")
        audio_path, message = module.generate_speech(
            actual_text,
            actual_language,
            prompt_audio_path,
            actual_mode,
            _file_path_from_value(emotion_reference_audio) or None,
            float(emotion_weight or 1.0),
            str(emotion_text or ""),
            *[float(value or 0) for value in vector_values[:8]],
            bool(do_sample),
            float(top_p or 0.8),
            int(float(str(top_k or 50))),
            float(temperature or 0.8),
            float(length_penalty or 1.0),
            int(float(str(num_beams or 1))),
            float(repetition_penalty or 1.2),
            int(float(str(max_mel_tokens or 500))),
            int(float(str(max_text_tokens_per_segment or 120))),
        )
    except Exception as exc:
        return {"ok": False, "message": f"IndexTTS generation failed: {exc}", "audio": None, "output_dir": str(INDEX_TTS_OUTPUT_DIR)}
    return {
        "ok": bool(audio_path and Path(str(audio_path)).is_file()),
        "message": str(message or ""),
        "audio": str(audio_path) if audio_path else None,
        "output_dir": str(INDEX_TTS_OUTPUT_DIR),
    }


def _frame_positions(total_frames: int, fps: float, mode: str) -> list[int]:
    if total_frames <= 0:
        return []
    duration = total_frames / fps if fps > 0 else 0
    target_count = max(1, min(60, int(duration / 2) if duration > 0 else 10, total_frames))
    if mode not in {"uniform", "interval", "change_detection"}:
        mode = "uniform"
    if mode == "interval":
        interval = max(1, int(total_frames / target_count))
        return [min(total_frames - 1, index * interval) for index in range(target_count)]
    return [min(total_frames - 1, int(index * total_frames / target_count)) for index in range(target_count)]


def extract_video_frames(video: object, quality: object = 85, mode: object = "uniform") -> dict[str, Any]:
    video_path = _file_path_from_value(video)
    if not video_path:
        return {"ok": False, "message": "Video is required.", "frames": [], "output_dir": str(VIDEO_FRAME_OUTPUT_DIR)}
    try:
        import cv2
        import numpy as np
    except Exception as exc:
        return {"ok": False, "message": f"OpenCV frame extraction is not available: {exc}", "frames": [], "output_dir": str(VIDEO_FRAME_OUTPUT_DIR)}
    try:
        quality_value = max(1, min(int(float(str(quality or 85))), 100))
    except Exception:
        quality_value = 85
    actual_mode = str(mode or "uniform")
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"ok": False, "message": f"Cannot open video: {video_path}", "frames": [], "output_dir": str(VIDEO_FRAME_OUTPUT_DIR)}
    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
        positions = _frame_positions(total_frames, fps, actual_mode)
        if actual_mode == "change_detection":
            positions = _change_detection_positions(cap, total_frames, fps, cv2, np) or positions
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_dir = VIDEO_FRAME_OUTPUT_DIR / f"video_{timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)
        saved: list[str] = []
        for frame_index, frame_position in enumerate(positions):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_position)
            ok, frame = cap.read()
            if not ok:
                continue
            path = output_dir / f"frame_{frame_index:04d}.jpg"
            cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, quality_value])
            saved.append(str(path))
    except Exception as exc:
        return {"ok": False, "message": f"Video frame extraction failed: {exc}", "frames": [], "output_dir": str(VIDEO_FRAME_OUTPUT_DIR)}
    finally:
        cap.release()
    return {
        "ok": bool(saved),
        "message": f"Video frame extraction finished. {len(saved)} frame(s) saved.",
        "frames": saved,
        "output_dir": str(output_dir if saved else VIDEO_FRAME_OUTPUT_DIR),
    }


def qwen3_tts_generate(
    *,
    text: object,
    language: object,
    model_choice: object,
    ref_audio: object = None,
    ref_text: object = "",
    auto_transcribe: object = False,
    speaker: object = "Vivian",
    custom_instruct: object = "",
    design_instruct: object = "",
    output_dir: object = "",
    use_batch_mode: object = False,
) -> dict[str, Any]:
    actual_text = str(text or "").strip()
    if not actual_text:
        return {"ok": False, "message": "Text is required.", "audio": None, "output_dir": str(QWEN3_TTS_OUTPUT_DIR)}
    actual_model = str(model_choice or "CustomVoice")
    actual_language = str(language or "Chinese")
    actual_output_dir = Path(str(output_dir or QWEN3_TTS_OUTPUT_DIR)).expanduser()
    if not actual_output_dir.is_absolute():
        actual_output_dir = QWEN3_TTS_OUTPUT_DIR
    actual_output_dir.mkdir(parents=True, exist_ok=True)
    try:
        module = _source_module("qwen3_tts_ui")
    except Exception as exc:
        return {"ok": False, "message": f"Qwen3-TTS is not available: {exc}", "audio": None, "output_dir": str(actual_output_dir)}
    try:
        if actual_model == "Base":
            audio_path = _file_path_from_value(ref_audio)
            if not audio_path:
                return {"ok": False, "message": "Reference audio is required for Base mode.", "audio": None, "output_dir": str(actual_output_dir)}
            result_audio, message = module.generate_speech_base(
                actual_text,
                actual_language,
                audio_path,
                str(ref_text or ""),
                str(actual_output_dir),
                bool(use_batch_mode),
                bool(auto_transcribe),
            )
        elif actual_model == "VoiceDesign":
            result_audio, message = module.generate_speech_voicedesign(
                actual_text,
                actual_language,
                str(design_instruct or qwen3_tts_defaults()["default_voice_design"]),
                str(actual_output_dir),
                bool(use_batch_mode),
            )
        else:
            actual_speaker = str(speaker or "Vivian")
            if actual_speaker not in {value for _, value in QWEN3_TTS_SPEAKERS}:
                actual_speaker = "Vivian"
            result_audio, message = module.generate_speech_customvoice(
                actual_text,
                actual_language,
                actual_speaker,
                str(custom_instruct or ""),
                str(actual_output_dir),
                bool(use_batch_mode),
            )
    except Exception as exc:
        return {"ok": False, "message": f"Qwen3-TTS generation failed: {exc}", "audio": None, "output_dir": str(actual_output_dir)}
    audio_path = str(result_audio) if result_audio else ""
    return {
        "ok": bool(audio_path and Path(audio_path).is_file()),
        "message": str(message or ""),
        "audio": audio_path if audio_path else None,
        "output_dir": str(actual_output_dir),
    }


def _change_detection_positions(cap, total_frames: int, fps: float, cv2, np) -> list[int]:
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    target_count = len(_frame_positions(total_frames, fps, "uniform"))
    previous = None
    positions: list[int] = []
    frame_index = 0
    while frame_index < total_frames:
        ok, frame = cap.read()
        if not ok:
            break
        if previous is not None:
            diff = cv2.absdiff(previous, frame)
            if int(np.count_nonzero(diff)) > 1000:
                positions.append(frame_index)
                if len(positions) >= target_count:
                    break
        previous = frame.copy()
        frame_index += 1
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    return positions
