from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sys
import types
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import gradio as gr


ROOT = Path(__file__).resolve().parents[1]
SOURCE_WEBUI_ROOT = ROOT / "forge_neo" / "webui"
SOURCE_EXTENSIONS_ROOT = SOURCE_WEBUI_ROOT / "extensions"
_GRADIO6_PATCH_SENTINEL = "_forge_neo_source_ui_gradio6_patch"
_EVENT_NAMES = ("click", "change", "submit", "upload", "select", "clear", "release", "input")
_IGNORED_COMPONENT_KWARGS = {
    "Audio": {"show_download_button"},
    "Button": {"info"},
    "Textbox": {"show_copy_button"},
}


def source_extension_ui_tabs_enabled() -> bool:
    value = str(os.environ.get("FORGE_NEO_SOURCE_EXTENSION_UI_TABS", "") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


class _SafeTextWriter(io.TextIOBase):
    def __init__(self, wrapped: Any):
        self._wrapped = wrapped

    @property
    def encoding(self) -> str:
        return getattr(self._wrapped, "encoding", None) or "utf-8"

    def write(self, text: str) -> int:
        value = str(text)
        try:
            return self._wrapped.write(value)
        except UnicodeEncodeError:
            return self._wrapped.write(value.encode(self.encoding, errors="replace").decode(self.encoding, errors="replace"))

    def flush(self) -> None:
        flush = getattr(self._wrapped, "flush", None)
        if callable(flush):
            with contextlib.suppress(ValueError):
                flush()


@contextlib.contextmanager
def _safe_console() -> Iterator[None]:
    previous_stdout = sys.stdout
    previous_stderr = sys.stderr
    sys.stdout = _SafeTextWriter(previous_stdout)
    sys.stderr = _SafeTextWriter(previous_stderr)
    try:
        yield
    finally:
        sys.stdout = previous_stdout
        sys.stderr = previous_stderr


def _patch_component_init(component_cls: type[Any], ignored_kwargs: set[str]) -> None:
    sentinel = f"{_GRADIO6_PATCH_SENTINEL}_init"
    if getattr(component_cls, sentinel, False):
        return
    original_init = component_cls.__init__

    def patched_init(self, *args: Any, **kwargs: Any):
        for key in ignored_kwargs:
            kwargs.pop(key, None)
        return original_init(self, *args, **kwargs)

    component_cls.__init__ = patched_init
    setattr(component_cls, sentinel, True)


def _patch_event_method(component_cls: type[Any], event_name: str) -> None:
    event = getattr(component_cls, event_name, None)
    if not callable(event):
        return
    sentinel = f"{_GRADIO6_PATCH_SENTINEL}_{event_name}"
    if getattr(event, sentinel, False):
        return

    def patched_event(self, *args: Any, **kwargs: Any):
        if "_js" in kwargs and "js" not in kwargs:
            kwargs["js"] = kwargs.pop("_js")
        else:
            kwargs.pop("_js", None)
        return event(self, *args, **kwargs)

    setattr(patched_event, sentinel, True)
    setattr(component_cls, event_name, patched_event)


def ensure_source_gradio6_ui_compat() -> None:
    if not hasattr(gr, "Box"):
        gr.Box = gr.Group

    for component_name, ignored_kwargs in _IGNORED_COMPONENT_KWARGS.items():
        component_cls = getattr(gr, component_name, None)
        if isinstance(component_cls, type):
            _patch_component_init(component_cls, ignored_kwargs)

    for component_cls in {value for value in vars(gr).values() if isinstance(value, type)}:
        for event_name in _EVENT_NAMES:
            _patch_event_method(component_cls, event_name)


def _source_shared_opts() -> types.SimpleNamespace:
    output_dir = ROOT / "outputs"
    return types.SimpleNamespace(
        forge_canvas_plain=False,
        forge_canvas_plain_color="#808080",
        forge_canvas_toolbar_always=False,
        forge_canvas_height=512,
        forge_canvas_consistent_brush=False,
        outdir_samples=str(output_dir),
        outdir_txt2img_samples=str(output_dir / "txt2img-images"),
        outdir_img2img_samples=str(output_dir / "img2img-images"),
        outdir_extras_samples=str(output_dir / "extras-images"),
    )


def _ensure_root_module(name: str) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = [str(SOURCE_WEBUI_ROOT / name.replace(".", os.sep))]
        sys.modules[name] = module
    return module


def _install_module(name: str, module: types.ModuleType) -> None:
    sys.modules[name] = module
    if "." in name:
        parent_name, child_name = name.rsplit(".", 1)
        parent = _ensure_root_module(parent_name)
        setattr(parent, child_name, module)


class _ScriptCallbacksModule(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("modules.script_callbacks")
        self.on_ui_tabs = self._noop
        self.on_app_started = self._noop

    @staticmethod
    def _noop(callback: Callable[..., Any] | None = None, **kwargs: Any) -> None:
        return None

    def __getattr__(self, name: str) -> Callable[..., None]:
        if name.startswith("on_"):
            return self._noop
        raise AttributeError(name)


def _install_source_module_stubs() -> None:
    models_path = str(ROOT / "models")
    output_dir = str(ROOT / "outputs")

    modules_root = _ensure_root_module("modules")
    modules_root.__path__ = list(dict.fromkeys([*getattr(modules_root, "__path__", []), str(SOURCE_WEBUI_ROOT / "modules")]))

    script_callbacks = _ScriptCallbacksModule()
    _install_module("modules.script_callbacks", script_callbacks)

    shared = types.ModuleType("modules.shared")
    shared.opts = _source_shared_opts()
    shared.models_path = models_path
    shared.cmd_opts = types.SimpleNamespace()
    _install_module("modules.shared", shared)

    paths = types.ModuleType("modules.paths")
    paths.models_path = models_path
    paths.script_path = str(SOURCE_WEBUI_ROOT)
    paths.data_path = str(ROOT)
    paths.extensions_dir = str(SOURCE_EXTENSIONS_ROOT)
    paths.extensions_builtin_dir = str(SOURCE_WEBUI_ROOT / "extensions-builtin")
    paths.cwd = str(ROOT)
    _install_module("modules.paths", paths)

    paths_internal = types.ModuleType("modules.paths_internal")
    paths_internal.models_path = models_path
    paths_internal.script_path = str(SOURCE_WEBUI_ROOT)
    paths_internal.data_path = str(ROOT)
    paths_internal.default_output_dir = output_dir
    paths_internal.extensions_dir = str(SOURCE_EXTENSIONS_ROOT)
    paths_internal.extensions_builtin_dir = str(SOURCE_WEBUI_ROOT / "extensions-builtin")
    paths_internal.cwd = str(ROOT)
    paths_internal.normalized_filepath = lambda value: value
    paths_internal.parser = _SilentParser()
    _install_module("modules.paths_internal", paths_internal)

    devices = types.ModuleType("modules.devices")
    devices.device = "cpu"
    devices.dtype = None
    _install_module("modules.devices", devices)

    scripts = types.ModuleType("modules.scripts")
    scripts.Script = _SourceScript
    scripts.basedir = lambda: str(SOURCE_WEBUI_ROOT)
    _install_module("modules.scripts", scripts)


class _SourceScript:
    def title(self) -> str:
        return self.__class__.__name__

    def show(self, is_img2img: bool) -> None:
        return None

    def ui(self, is_img2img: bool) -> list[Any]:
        return []


class _SilentParser:
    def add_argument(self, *args: Any, **kwargs: Any) -> None:
        return None

    def parse_known_args(self, *args: Any, **kwargs: Any) -> tuple[types.SimpleNamespace, list[str]]:
        return types.SimpleNamespace(), []


@contextlib.contextmanager
def _source_paths(script_path: Path) -> Iterator[None]:
    paths = [SOURCE_WEBUI_ROOT, script_path.parent, script_path.parent.parent]
    inserted: list[str] = []
    for path in paths:
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)
            inserted.append(value)
    try:
        yield
    finally:
        for value in inserted:
            with contextlib.suppress(ValueError):
                sys.path.remove(value)


def _clear_script_local_modules(script_path: Path) -> None:
    for path in script_path.parent.glob("*.py"):
        if path.stem != "__init__":
            sys.modules.pop(path.stem, None)


def _load_source_module(script_path: Path) -> types.ModuleType:
    module_name = f"_forge_neo_source_ui_{script_path.parent.parent.name}_{script_path.stem}"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load source UI script: {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def build_source_extension_ui(extension_dirname: str, script_relative_path: str, callback_name: str) -> tuple[Any, str, str]:
    ensure_source_gradio6_ui_compat()
    _install_source_module_stubs()

    script_path = SOURCE_EXTENSIONS_ROOT / extension_dirname / script_relative_path
    if not script_path.is_file():
        raise FileNotFoundError(script_path)

    with _safe_console(), _source_paths(script_path):
        _clear_script_local_modules(script_path)
        module = _load_source_module(script_path)
        callback = getattr(module, callback_name, None)
        if not callable(callback):
            raise AttributeError(f"{extension_dirname} has no callable {callback_name}")
        result = callback()

    if not isinstance(result, Sequence) or not result:
        raise ValueError(f"{extension_dirname} returned no UI tabs")
    interface, label, ifid = result[0]
    return interface, str(label), str(ifid)


def render_source_extension_tab(
    extension_dirname: str,
    script_relative_path: str,
    callback_name: str,
    *,
    visible: bool,
    on_error: Callable[[Exception], None] | None = None,
) -> bool:
    if not visible or not source_extension_ui_tabs_enabled():
        return False
    try:
        interface, label, ifid = build_source_extension_ui(extension_dirname, script_relative_path, callback_name)
    except Exception as exc:
        if on_error is not None:
            on_error(exc)
        else:
            print(f"Forge Neo source UI failed for {extension_dirname}: {type(exc).__name__}: {exc}", flush=True)
        return False

    with gr.Tab(label, id=ifid, elem_id=f"tab_{ifid}", visible=visible):
        interface.render()
    return True
