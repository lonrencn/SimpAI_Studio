import os
import sys

import folder_paths

# 获取当前目录的父目录的父目录
parent_dir = os.path.dirname(os.path.abspath(__file__))

# 添加父目录的父目录到系统路径
sys.path.insert(0, parent_dir)

models_dir_key = "birefnet"
models_dir_default = os.path.join(folder_paths.models_dir, "rembg")


def ensure_supported_model_key(folder_name):
    if folder_name in folder_paths.folder_names_and_paths:
        paths, _exts = folder_paths.folder_names_and_paths[folder_name]
        folder_paths.folder_names_and_paths[folder_name] = (
            paths, folder_paths.supported_pt_extensions)
    else:
        folder_paths.folder_names_and_paths[folder_name] = (
            [], folder_paths.supported_pt_extensions)


ensure_supported_model_key(models_dir_key)

if "rembg" in folder_paths.folder_names_and_paths:
    for model_path in folder_paths.get_folder_paths("rembg"):
        folder_paths.add_model_folder_path(models_dir_key, model_path)

os.makedirs(models_dir_default, exist_ok=True)
folder_paths.add_model_folder_path(models_dir_key, models_dir_default)

from . import birefnetNode

NODE_CLASS_MAPPINGS = {**birefnetNode.NODE_CLASS_MAPPINGS}
NODE_DISPLAY_NAME_MAPPINGS = {**birefnetNode.NODE_DISPLAY_NAME_MAPPINGS}
