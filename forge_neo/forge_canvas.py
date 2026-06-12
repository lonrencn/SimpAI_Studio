from __future__ import annotations

import base64
import html
import uuid
from functools import wraps
from io import BytesIO
from pathlib import Path

import gradio as gr
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
CANVAS_HTML = (ROOT / "html" / "forge_neo" / "canvas.html").read_text(encoding="utf-8")


def image_to_base64(image: Image.Image) -> str:
    buffered = BytesIO()
    image.convert("RGBA").save(buffered, format="PNG")
    encoded = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def base64_to_image(data_url: str) -> Image.Image | None:
    if not isinstance(data_url, str):
        return None
    marker = "base64,"
    if not data_url.startswith("data:image/") or marker not in data_url:
        return None
    try:
        payload = data_url.split(marker, 1)[1]
        return Image.open(BytesIO(base64.b64decode(payload))).convert("RGBA")
    except Exception:
        return None


class LogicalImage(gr.Textbox):
    @wraps(gr.Textbox.__init__)
    def __init__(self, *args, **kwargs):
        self.infotext: dict[str, object] = {}
        value = kwargs.get("value")
        if isinstance(value, Image.Image):
            kwargs["value"] = image_to_base64(value)
        super().__init__(*args, **kwargs)

    def preprocess(self, payload):
        image = base64_to_image(payload)
        if image is not None:
            image.info = self.infotext
        return image

    def postprocess(self, value):
        if value is None:
            return None
        if isinstance(value, Image.Image):
            self.infotext = dict(getattr(value, "info", {}) or {})
            return image_to_base64(value)
        return value

    def get_block_name(self):
        return "textbox"


def _js_bool(value: bool) -> str:
    return "true" if bool(value) else "false"


class ForgeCanvas:
    def __init__(
        self,
        *,
        no_upload: bool = False,
        no_scribbles: bool = False,
        contrast_scribbles: bool = False,
        height: int = 512,
        scribble_color: str = "#000000",
        scribble_color_fixed: bool = False,
        scribble_width: int = 25,
        scribble_width_fixed: bool = False,
        scribble_width_consistent: bool = False,
        scribble_alpha: int = 100,
        scribble_alpha_fixed: bool = False,
        scribble_softness: int = 0,
        scribble_softness_fixed: bool = False,
        initial_image: Image.Image | None = None,
        elem_id: str | None = None,
        elem_classes: list[str] | None = None,
    ) -> None:
        self.uuid = "uuid_" + uuid.uuid4().hex
        canvas_html = CANVAS_HTML.replace("forge_mixin", self.uuid)
        data_attrs = " ".join(
            [
                'data-forge-neo-canvas="1"',
                f'data-forge-neo-canvas-uuid="{html.escape(self.uuid, quote=True)}"',
                f'data-no-upload="{_js_bool(no_upload)}"',
                f'data-no-scribbles="{_js_bool(no_scribbles)}"',
                f'data-contrast-scribbles="{_js_bool(contrast_scribbles)}"',
                f'data-height="{int(height or 512)}"',
                f'data-scribble-color="{html.escape(str(scribble_color or "#000000"), quote=True)}"',
                f'data-scribble-color-fixed="{_js_bool(scribble_color_fixed)}"',
                f'data-scribble-width="{int(scribble_width or 25)}"',
                f'data-scribble-width-fixed="{_js_bool(scribble_width_fixed)}"',
                f'data-scribble-width-consistent="{_js_bool(scribble_width_consistent)}"',
                f'data-scribble-alpha="{int(scribble_alpha or 100)}"',
                f'data-scribble-alpha-fixed="{_js_bool(scribble_alpha_fixed)}"',
                f'data-scribble-softness="{int(scribble_softness or 0)}"',
                f'data-scribble-softness-fixed="{_js_bool(scribble_softness_fixed)}"',
            ]
        )
        canvas_html = canvas_html.replace(
            f'id="container_{self.uuid}"',
            f'id="container_{self.uuid}" {data_attrs}',
            1,
        )
        classes = ["forge-neo-forge-canvas", *(elem_classes or [])]
        self.block = gr.HTML(canvas_html, elem_id=elem_id, elem_classes=classes)
        self.foreground = LogicalImage(
            visible=True,
            show_label=False,
            container=False,
            elem_id=self.uuid,
            elem_classes=["logical_image_foreground", "forge-neo-logical-image"],
        )
        self.background = LogicalImage(
            visible=True,
            show_label=False,
            container=False,
            value=initial_image,
            elem_id=self.uuid,
            elem_classes=["logical_image_background", "forge-neo-logical-image"],
        )
