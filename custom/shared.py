import os
import sys
import logging
from shared import *
import modules.config as config
from enhanced.logger import format_name

logger = logging.getLogger(format_name(__name__))

paths_checkpoints = config.paths_checkpoints
paths_loras = config.paths_loras
path_embeddings = config.paths_embeddings
path_vae_approx = config.paths_vae_approx
path_upscale_models = config.paths_upscale_models
paths_inpaint = config.paths_inpaint
paths_controlnet = config.paths_controlnet
path_clip_vision = config.paths_clip_vision
path_fooocus_expansion = config.path_fooocus_expansion
paths_llms = config.paths_llms
path_outputs = config.path_outputs

path_root = root

def init_module(file_path):
    module_root = os.path.dirname(file_path)
    sys.path.append(module_root)
    module_name = os.path.relpath(module_root, os.path.dirname(os.path.abspath(__file__)))
    logger.debug(f'[{module_name}] The customized module:{module_name} is initializing ...')
    return module_name, module_root


