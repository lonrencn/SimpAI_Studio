# danbooru-tags Runtime

This directory contains the packaged first-party Danbooru lookup runtime used
by SimpAI. The source lives in `rust/danbooru-tags`.

Runtime discovery prefers this directory before developer-only external paths.
Runtime files:

- `bin/danbooru-tags.exe`
- `bin/danbooru-tags`

Windows uses `bin/danbooru-tags.exe`. Linux uses `bin/danbooru-tags`.
When a Linux source checkout is missing `bin/danbooru-tags`, SimpAI tries to
build it from `rust/danbooru-tags` if `cargo` is available. If Cargo is missing
or the build fails, the UI/API reports the runtime status and continues with the
Python/CSV lookup fallback.

Generated lookup index files:

- `tags_lookup.bin`
- `tags_lookup_values.bin`
- `tags_lookup_records.bin`

The executable reads the tracked repo tag data from `tags/`:

- `tags/danbooru_all.csv`
- `tags/weilin_tagcart.csv`
- `tags/custom_tags.csv`
- `tags/character_glossary.csv`

Build and refresh the packaged executable with:

```powershell
python -B tools\build_danbooru_tags_runtime.py
```

On Linux, run the same command from a shell:

```bash
python -B tools/build_danbooru_tags_runtime.py
```

If a full Anima official tag CSV is available, merge it into the generated
lookup index to cover tags missing from the filtered repo CSV:

```powershell
python -B tools\build_danbooru_tags_runtime.py --anima-csv <path-to-anima-1.0.csv>
```

The crate is first-party code licensed as Apache-2.0. No upstream GPL binary or
SQLite index is required by this packaged runtime.
