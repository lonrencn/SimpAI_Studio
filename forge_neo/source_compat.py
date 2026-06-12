from __future__ import annotations

import hashlib
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from urllib.parse import urlparse


def make_source_util_module(source_root: Path) -> ModuleType:
    root = Path(source_root)
    module = ModuleType("modules.util")
    module.__file__ = str(root / "modules" / "util.py")

    def natural_sort_key(s, regex=re.compile(r"([0-9]+)")):
        return [int(text) if text.isdigit() else text.lower() for text in regex.split(str(s))]

    def listfiles(dirname):
        filenames = [os.path.join(dirname, x) for x in sorted(os.listdir(dirname), key=natural_sort_key) if not x.startswith(".")]
        return [file for file in filenames if os.path.isfile(file)]

    def html_path(filename):
        return os.path.join(str(root), "html", filename)

    def html(filename):
        path = html_path(filename)
        try:
            with open(path, encoding="utf8") as file:
                return file.read()
        except OSError:
            return ""

    def walk_files(path, allowed_extensions=None):
        if not os.path.exists(path):
            return
        if allowed_extensions is not None:
            allowed_extensions = set(allowed_extensions)
        try:
            from modules import shared

            list_hidden_files = bool(getattr(getattr(shared, "opts", object()), "list_hidden_files", True))
        except Exception:
            list_hidden_files = True
        items = sorted(list(os.walk(path, followlinks=True)), key=lambda x: natural_sort_key(x[0]))
        for walk_root, _, files in items:
            for filename in sorted(files, key=natural_sort_key):
                if allowed_extensions is not None:
                    _, ext = os.path.splitext(filename)
                    if ext.lower() not in allowed_extensions:
                        continue
                if not list_hidden_files and ("/." in walk_root or "\\." in walk_root):
                    continue
                yield os.path.join(walk_root, filename)

    def truncate_path(target_path, base_path=None):
        base_path = str(root) if base_path is None else base_path
        abs_target, abs_base = os.path.abspath(target_path), os.path.abspath(base_path)
        try:
            if os.path.commonpath([abs_target, abs_base]) == abs_base:
                return os.path.relpath(abs_target, abs_base)
        except ValueError:
            pass
        return abs_target

    class MassFileListerCachedDir:
        def __init__(self, dirname):
            self.files = None
            self.files_cased = None
            self.dirname = dirname
            stats = ((x.name, x.stat(follow_symlinks=False)) for x in os.scandir(self.dirname))
            files = [(n, s.st_mtime, s.st_ctime) for n, s in stats]
            self.files = {x[0].lower(): x for x in files}
            self.files_cased = {x[0]: x for x in files}

        def update_entry(self, filename):
            file_path = os.path.join(self.dirname, filename)
            try:
                stat = os.stat(file_path)
                entry = (filename, stat.st_mtime, stat.st_ctime)
                self.files[filename.lower()] = entry
                self.files_cased[filename] = entry
            except FileNotFoundError as e:
                print(f'MassFileListerCachedDir.add_entry: "{file_path}" {e}')

    class MassFileLister:
        def __init__(self):
            self.cached_dirs = {}

        def find(self, path):
            dirname, filename = os.path.split(path)
            cached_dir = self.cached_dirs.get(dirname)
            if cached_dir is None:
                cached_dir = MassFileListerCachedDir(dirname)
                self.cached_dirs[dirname] = cached_dir
            stats = cached_dir.files_cased.get(filename)
            if stats is not None:
                return stats
            stats = cached_dir.files.get(filename.lower())
            if stats is None:
                return None
            try:
                os_stats = os.stat(path, follow_symlinks=False)
                return filename, os_stats.st_mtime, os_stats.st_ctime
            except Exception:
                return None

        def exists(self, path):
            return self.find(path) is not None

        def mctime(self, path):
            stats = self.find(path)
            return (0, 0) if stats is None else stats[1:3]

        def reset(self):
            self.cached_dirs.clear()

        def update_file_entry(self, path):
            dirname, filename = os.path.split(path)
            if cached_dir := self.cached_dirs.get(dirname):
                cached_dir.update_entry(filename)

    def topological_sort(dependencies):
        visited = {}
        result = []

        def inner(name):
            visited[name] = True
            for dep in dependencies.get(name, []):
                if dep in dependencies and dep not in visited:
                    inner(dep)
            result.append(name)

        for depname in dependencies:
            if depname not in visited:
                inner(depname)
        return result

    def open_folder(path):
        if not os.path.exists(path):
            print(f'Folder "{path}" does not exist. after you save an image, the folder will be created.')
            return
        if not os.path.isdir(path):
            print(f'WARNING: open_folder requested a non-folder path: {path}', file=sys.stderr)
            return
        normalized = os.path.normpath(path)
        if platform.system() == "Windows":
            os.startfile(normalized)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", normalized])
        elif "microsoft-standard-WSL2" in platform.uname().release:
            subprocess.Popen(["explorer.exe", subprocess.check_output(["wslpath", "-w", normalized])])
        else:
            subprocess.Popen(["xdg-open", normalized])

    def compare_sha256(file_path: str, hash_prefix: str) -> bool:
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest().startswith(hash_prefix.strip().lower())

    def load_file_from_url(
        url: str,
        *,
        model_dir: str,
        progress: bool = True,
        file_name: str | None = None,
        hash_prefix: str | None = None,
        re_download: bool = False,
    ) -> str:
        import requests
        from tqdm import tqdm

        if not file_name:
            parts = urlparse(url)
            file_name = os.path.basename(parts.path)
        cached_file = os.path.abspath(os.path.join(model_dir, file_name))
        if re_download or not os.path.exists(cached_file):
            os.makedirs(model_dir, exist_ok=True)
            temp_file = os.path.join(model_dir, f"{file_name}.tmp")
            print(f'\nDownloading: "{url}" to {cached_file}')
            response = requests.get(url, stream=True)
            response.raise_for_status()
            total_size = int(response.headers.get("content-length", 0))
            with tqdm(total=total_size, unit="B", unit_scale=True, desc=file_name, disable=not progress) as progress_bar:
                with open(temp_file, "wb") as file:
                    for chunk in response.iter_content(chunk_size=1024):
                        if chunk:
                            file.write(chunk)
                            progress_bar.update(len(chunk))
            if hash_prefix and not compare_sha256(temp_file, hash_prefix):
                print(f"Hash mismatch for {temp_file}. Deleting the temporary file.")
                os.remove(temp_file)
                raise ValueError(f"File hash does not match the expected hash prefix {hash_prefix}!")
            os.rename(temp_file, cached_file)
        return cached_file

    for name, value in {
        "natural_sort_key": natural_sort_key,
        "listfiles": listfiles,
        "html_path": html_path,
        "html": html,
        "walk_files": walk_files,
        "truncate_path": truncate_path,
        "MassFileListerCachedDir": MassFileListerCachedDir,
        "MassFileLister": MassFileLister,
        "topological_sort": topological_sort,
        "open_folder": open_folder,
        "load_file_from_url": load_file_from_url,
        "compare_sha256": compare_sha256,
    }.items():
        setattr(module, name, value)

    return module


def bind_source_shared_util(source_shared, source_util: ModuleType) -> None:
    source_shared.util = source_util
    for name in ("natural_sort_key", "listfiles", "html_path", "html", "walk_files"):
        setattr(source_shared, name, getattr(source_util, name))
