from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

import spandrel
import spandrel_extra_arches
import torch

from backend.utils import load_torch_file
from modules import shared
from modules.upscaler import Upscaler, UpscalerLanczos, UpscalerNearest, UpscalerNone  # noqa
from modules.util import load_file_from_url  # noqa

spandrel_extra_arches.install()

logger = logging.getLogger(__name__)


def _env_upscaler_model_roots() -> list[str]:
    value = str(os.environ.get("FORGE_NEO_SOURCE_BACKEND_UPSCALE_MODEL_DIRS", "") or "").strip()
    if not value:
        return []
    roots: list[str] = []
    for item in value.split(os.pathsep):
        text = str(item or "").strip()
        if text and os.path.isdir(text):
            roots.append(text)
    return roots


def _source_upscaler_model_roots(command_path: str | None, model_path: str | None) -> list[str]:
    roots: list[str] = []
    seen: set[str] = set()

    def add(value: object, *, require_existing_dir: bool) -> None:
        text = str(value or "").strip()
        if not text:
            return
        if require_existing_dir and not os.path.isdir(text):
            return
        key = os.path.normcase(os.path.abspath(text))
        if key in seen:
            return
        seen.add(key)
        roots.append(text)

    env_roots = _env_upscaler_model_roots()
    if env_roots:
        for root in env_roots:
            add(root, require_existing_dir=True)
    else:
        try:
            from forge_neo.models import model_roots_for_catalog

            for root in model_roots_for_catalog("upscale_models"):
                add(root, require_existing_dir=True)
        except Exception:
            pass

    add(command_path, require_existing_dir=False)
    add(model_path, require_existing_dir=False)
    return roots


def _unique_upscaler_scalers(scalers: list) -> list:
    out = []
    seen: set[str] = set()
    for scaler in scalers:
        name = str(getattr(scaler, "name", "") or "").strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(scaler)
    return out


def _source_esrgan_scalers(commandline_model_path: str | None):
    from modules.esrgan_model import UpscalerESRGAN

    local_scalers = []
    fallback_scalers = []
    roots = _source_upscaler_model_roots(commandline_model_path, commandline_model_path)
    for root in roots or [commandline_model_path]:
        upscaler = UpscalerESRGAN(root)
        upscaler.user_path = root
        upscaler.model_download_path = root or upscaler.model_path
        for scaler in upscaler.scalers:
            data_path = str(getattr(scaler, "data_path", "") or "")
            if data_path.startswith("http"):
                fallback_scalers.append(scaler)
            else:
                local_scalers.append(scaler)
    scalers = local_scalers or fallback_scalers
    return sorted(_unique_upscaler_scalers(scalers), key=lambda s: str(getattr(s, "name", "") or "").lower())


def load_models(model_path: str, model_url: str = None, command_path: str = None, ext_filter=None, download_name=None, ext_blacklist=None, hash_prefix=None) -> list:
    """
    A one-and done loader to try finding the desired models in specified directories.

    @param download_name: Specify to download from model_url immediately.
    @param model_url: If no other models are found, this will be downloaded on upscale.
    @param model_path: The location to store/find models in.
    @param command_path: A command-line argument to search for models in first.
    @param ext_filter: An optional list of filename extensions to filter by
    @param hash_prefix: the expected sha256 of the model_url
    @return: A list of paths containing the desired model(s)
    """
    output = []

    try:
        places = []

        if command_path is not None and command_path != model_path:
            pretrained_path = os.path.join(command_path, "experiments/pretrained_models")
            if os.path.exists(pretrained_path):
                print(f"Appending path: {pretrained_path}")
                places.append(pretrained_path)
            elif os.path.exists(command_path):
                places.append(command_path)

        places.append(model_path)

        for place in places:
            for full_path in shared.walk_files(place, allowed_extensions=ext_filter):
                if os.path.islink(full_path) and not os.path.exists(full_path):
                    print(f"Skipping broken symlink: {full_path}")
                    continue
                if ext_blacklist is not None and any(full_path.endswith(x) for x in ext_blacklist):
                    continue
                if full_path not in output:
                    output.append(full_path)

        if model_url is not None and len(output) == 0:
            if download_name is not None:
                output.append(load_file_from_url(model_url, model_dir=places[0], file_name=download_name, hash_prefix=hash_prefix))
            else:
                output.append(model_url)

    except Exception:
        pass

    return output


def friendly_name(file: str):
    if file.startswith("http"):
        file = urlparse(file).path

    file = os.path.basename(file)
    model_name, _ = os.path.splitext(file)
    return model_name


def load_upscalers():
    del shared.sd_upscalers

    commandline_model_path = shared.cmd_opts.esrgan_models_path

    shared.sd_upscalers = [
        *UpscalerNone().scalers,
        *UpscalerLanczos().scalers,
        *UpscalerNearest().scalers,
        *_source_esrgan_scalers(commandline_model_path),
    ]


def load_spandrel_model(path: os.PathLike, device: torch.device | None, prefer_half: bool = False, *args, **kwargs) -> spandrel.ImageModelDescriptor:
    sd = load_torch_file(path, safe_load=True, device=device)
    model_descriptor = spandrel.ModelLoader(device=device).load_from_state_dict(sd)

    arch = model_descriptor.architecture
    logger.info(f'Loaded {arch.name} Model: "{os.path.basename(path)}"')

    if prefer_half:
        if model_descriptor.supports_half:
            model_descriptor.half()
        elif model_descriptor.supports_bfloat16:
            model_descriptor.bfloat16()
        else:
            logger.warning(f"Model {path} does not support half precision...")

    model_descriptor.eval()
    return model_descriptor
