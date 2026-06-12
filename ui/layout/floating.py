from __future__ import annotations

from collections.abc import Iterable

import gradio as gr


def _classes(*groups: str | Iterable[str] | None) -> list[str]:
    result: list[str] = []
    for group in groups:
        if not group:
            continue
        if isinstance(group, str):
            items = [group]
        else:
            items = [item for item in group if item]
        for item in items:
            if item not in result:
                result.append(item)
    return result


def floating_shell(
    *,
    visible: bool = False,
    elem_id: str | None = None,
    elem_classes: str | Iterable[str] | None = None,
    modal: bool = True,
):
    """Create a SimpAI floating shell controlled by project CSS."""
    base = ["sai-floating-shell"]
    if modal:
        base.append("modal")
    return gr.Group(
        visible=visible,
        elem_id=elem_id,
        elem_classes=_classes(base, elem_classes),
    )


def floating_card(
    *,
    elem_id: str | None = None,
    elem_classes: str | Iterable[str] | None = None,
    scale: int | None = None,
    min_width: int | None = None,
):
    kwargs = {
        "elem_id": elem_id,
        "elem_classes": _classes(["sai-floating-card", "modal-content"], elem_classes),
    }
    if scale is not None:
        kwargs["scale"] = scale
    if min_width is not None:
        kwargs["min_width"] = min_width
    return gr.Column(
        **kwargs,
    )


def floating_panel(
    *,
    visible: bool = False,
    elem_id: str | None = None,
    elem_classes: str | Iterable[str] | None = None,
):
    """Create a compact floating panel for lightweight confirmation popups."""
    return gr.Group(
        visible=visible,
        elem_id=elem_id,
        elem_classes=_classes(["sai-floating-panel"], elem_classes),
    )
