from __future__ import annotations

from functools import wraps

import gradio as gr

from gradio.events import Dependency

class InputAccordionImpl(gr.Checkbox):
    webui_do_not_create_gradio_pyi_thank_you = True

    global_index = 0

    @wraps(gr.Checkbox.__init__)
    def __init__(self, value=None, setup: bool = False, **kwargs):
        if not setup:
            super().__init__(value=value, **kwargs)
            return

        self.accordion_id = kwargs.get("elem_id")
        if self.accordion_id is None:
            self.accordion_id = f"forge-neo-input-accordion-{InputAccordionImpl.global_index}"
            InputAccordionImpl.global_index += 1

        elem_classes = kwargs.get("elem_classes") or []
        if isinstance(elem_classes, str):
            elem_classes = [elem_classes]

        checkbox_kwargs = {
            **kwargs,
            "elem_id": f"{self.accordion_id}-checkbox",
            "visible": True,
            "elem_classes": ["forge-neo-input-accordion-hidden-checkbox", *elem_classes],
        }
        super().__init__(value=value, **checkbox_kwargs)
        self.change(fn=None, js=f'function(checked){{ inputAccordionChecked("{self.accordion_id}", checked); }}', inputs=[self])

        accordion_classes = ["input-accordion", *[item for item in elem_classes if item != "input-accordion"]]
        self.accordion = gr.Accordion(
            **{
                **kwargs,
                "elem_id": self.accordion_id,
                "label": kwargs.get("label", "Accordion"),
                "elem_classes": accordion_classes,
                "open": value,
            }
        )

    def extra(self):
        return gr.Column(elem_id=f"{self.accordion_id}-extra", elem_classes="input-accordion-extra", min_width=0)

    def __enter__(self):
        self.accordion.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.accordion.__exit__(exc_type, exc_val, exc_tb)

    def get_block_name(self):
        return "checkbox"
    from typing import Callable, Literal, Sequence, Any, TYPE_CHECKING
    from gradio.blocks import Block
    if TYPE_CHECKING:
        from gradio.components import Timer
        from gradio.components.base import Component


def InputAccordion(value=None, **kwargs):
    return InputAccordionImpl(value=value, setup=True, **kwargs)