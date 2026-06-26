"""Build and package the first-party Danbooru tag lookup runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build rust/danbooru-tags and copy it into vendor/danbooru-tags.")
    parser.add_argument("--profile", default="release", choices=["debug", "release"])
    parser.add_argument("--target", default="vendor/danbooru-tags")
    parser.add_argument("--anima-csv", default="", help="Optional Anima official anima-1.0.csv to merge into the lookup index.")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    manifest = root / "rust" / "danbooru-tags" / "Cargo.toml"
    cargo_args = ["cargo", "build", "--manifest-path", str(manifest)]
    if args.profile == "release":
        cargo_args.insert(2, "--release")
    subprocess.run(cargo_args, cwd=root, check=True)

    exe_name = "danbooru-tags.exe" if os.name == "nt" else "danbooru-tags"
    source_exe = root / "rust" / "danbooru-tags" / "target" / args.profile / exe_name
    target_root = root / args.target
    target_bin = target_root / "bin"
    target_bin.mkdir(parents=True, exist_ok=True)
    target_exe = target_bin / exe_name
    shutil.copy2(source_exe, target_exe)
    if os.name != "nt":
        target_exe.chmod(target_exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    lookup_path = target_root / "tags_lookup.bin"
    lookup_values_path = target_root / "tags_lookup_values.bin"
    lookup_records_path = target_root / "tags_lookup_records.bin"
    lookup_command = [str(target_exe), "--build-lookup", str(lookup_path)]
    if args.anima_csv:
        lookup_command.extend(["--anima-csv", str(Path(args.anima_csv).resolve())])
    subprocess.run(lookup_command, cwd=root, check=True)

    files = []
    for runtime_name, platform_name in (("danbooru-tags.exe", "windows"), ("danbooru-tags", "linux")):
        runtime_path = target_bin / runtime_name
        if runtime_path.is_file():
            files.append({
                "path": f"bin/{runtime_name}",
                "platform": platform_name,
                "bytes": runtime_path.stat().st_size,
                "sha256": sha256_file(runtime_path),
            })
    for relative, path in (
        ("tags_lookup.bin", lookup_path),
        ("tags_lookup_values.bin", lookup_values_path),
        ("tags_lookup_records.bin", lookup_records_path),
    ):
        files.append({
            "path": relative,
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    runtime_manifest = {
        "runtime": "simpai-danbooru-tags",
        "source_crate": "rust/danbooru-tags",
        "build_command": "cargo build --release --manifest-path rust/danbooru-tags/Cargo.toml",
        "linux_auto_build": "When vendor/danbooru-tags/bin/danbooru-tags is missing, source checkouts can build it from rust/danbooru-tags if Cargo is available.",
        "data_source": "repo tags/*.csv via SIMPAI_TAGS_ROOT" + (" plus Anima CSV supplement" if args.anima_csv else ""),
        "anima_csv_source": Path(args.anima_csv).name if args.anima_csv else "",
        "files": files,
        "license": "Apache-2.0 first-party code",
    }
    (target_root / "runtime_manifest.json").write_text(
        json.dumps(runtime_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Packaged {target_exe.relative_to(root)} ({target_exe.stat().st_size} bytes, sha256={sha256_file(target_exe)})")
    print(f"Wrote {lookup_path.relative_to(root)} ({lookup_path.stat().st_size} bytes, sha256={sha256_file(lookup_path)})")
    print(f"Wrote {lookup_values_path.relative_to(root)} ({lookup_values_path.stat().st_size} bytes, sha256={sha256_file(lookup_values_path)})")
    print(f"Wrote {lookup_records_path.relative_to(root)} ({lookup_records_path.stat().st_size} bytes, sha256={sha256_file(lookup_records_path)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
