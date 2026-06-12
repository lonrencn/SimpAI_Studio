from __future__ import annotations

import gradio as gr

_MISSING = object()


def gr_update(**kwargs):
    """Central wrapper for component updates during the Gradio 6 migration."""
    return gr.update(**kwargs)


def skip_update():
    """Return an explicit no-op output for unchanged Gradio event outputs."""
    skip = getattr(gr, "skip", None)
    if callable(skip):
        return skip()
    return gr.update()


def dataset_update(**kwargs):
    """Return a Dataset-specific update when Gradio exposes one."""
    dataset_cls = getattr(gr, "Dataset", None)
    update_method = getattr(dataset_cls, "update", None) if dataset_cls is not None else None
    if callable(update_method):
        return update_method(**kwargs)
    return gr.update(**kwargs)


def dropdown_choice_values(choices) -> list:
    if not choices:
        return []
    values = []
    for choice in choices:
        if isinstance(choice, (tuple, list)) and len(choice) >= 2:
            values.append(choice[1])
        else:
            values.append(choice)
    return values


def sanitize_dropdown_value(value, choices, *, allow_custom_value: bool = False, multiselect: bool = False, fallback=_MISSING):
    choice_values = dropdown_choice_values(choices)
    if multiselect:
        if value is None:
            return []
        if not isinstance(value, list):
            value = [value]
        if allow_custom_value:
            return value
        return [item for item in value if item in choice_values]

    if allow_custom_value:
        return value
    if value is None:
        return fallback if fallback is not _MISSING else None
    if value in choice_values:
        return value
    if fallback is not _MISSING:
        return fallback if fallback is None or fallback in choice_values else (choice_values[0] if choice_values else None)
    return choice_values[0] if choice_values else None


def dropdown_update(*, choices, value=None, allow_custom_value: bool = False, multiselect: bool = False, fallback=_MISSING, **kwargs):
    return gr_update(
        choices=choices,
        value=sanitize_dropdown_value(
            value,
            choices,
            allow_custom_value=allow_custom_value,
            multiselect=multiselect,
            fallback=fallback,
        ),
        **kwargs,
    )
