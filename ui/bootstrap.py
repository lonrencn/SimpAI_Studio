from __future__ import annotations

import gradio as gr

from ui.runtime_patches import apply_gradio6_runtime_patches


def _reload_javascript() -> None:
    from modules.ui_gradio_extensions import reload_javascript

    reload_javascript()


def apply_webui_assets() -> None:
    """Inject the WebUI JS/CSS bundle."""
    _reload_javascript()


def queue_blocks(blocks: gr.Blocks, concurrency_count: int = 5) -> gr.Blocks:
    """Queue a Blocks app through the Gradio 6 API."""
    return blocks.queue(default_concurrency_limit=concurrency_count)


def _create_default_theme():
    return gr.themes.Default(
        font=("ui-sans-serif", "system-ui", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "sans-serif"),
        font_mono=("ui-monospace", "Consolas", "Liberation Mono", "monospace"),
    )


def create_root_blocks(*, title: str, concurrency_count: int = 5) -> gr.Blocks:
    """Create the root Blocks instance for SimpAI WebUI."""
    apply_gradio6_runtime_patches()
    blocks = gr.Blocks(title=title)
    setattr(blocks, "_simpai_launch_theme", _create_default_theme())
    return queue_blocks(blocks, concurrency_count=concurrency_count)


def launch_root_app(blocks: gr.Blocks, **kwargs):
    """Single entry point for launching the root app."""
    launch_theme = getattr(blocks, "__dict__", {}).get("_simpai_launch_theme")
    if launch_theme is not None and "theme" not in kwargs:
        kwargs["theme"] = launch_theme
    return blocks.launch(**kwargs)
