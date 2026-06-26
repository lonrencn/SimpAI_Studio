"""ComfyUI-Sharp Prestartup Script."""

try:
    from comfy_env import setup_env, copy_files

    setup_env()

    from pathlib import Path
    SCRIPT_DIR = Path(__file__).resolve().parent
    COMFYUI_DIR = SCRIPT_DIR.parent.parent

    copy_files(SCRIPT_DIR / "assets", COMFYUI_DIR / "input")
except ImportError:
    pass
