use clap::Parser;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::cmp::Ordering;
use std::collections::{BTreeMap, HashSet};
use std::env;
use std::fs::{self, File};
use std::io::{BufRead, BufReader, BufWriter, Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};
use std::thread;

#[derive(Parser, Debug)]
#[command(
    name = "danbooru-tags",
    about = "SimpAI first-party Danbooru tag lookup"
)]
struct Args {
    #[arg(short = 'k', long, default_value = "")]
    keyword: String,
    #[arg(short = 'p', long, default_value = "")]
    prefix: String,
    #[arg(short = 'c', long, default_value = "")]
    category: String,
    #[arg(short = 'g', long, default_value = "")]
    group: String,
    #[arg(short = 'm', long, default_value_t = 0)]
    min_count: u64,
    #[arg(short = 'l', long, default_value_t = 20)]
    limit: usize,
    #[arg(short = 'j', long)]
    json: bool,
    #[arg(long)]
    for_prompt: bool,
    #[arg(long)]
    compact: bool,
    #[arg(short = 'r', long, default_value_t = 0)]
    random: usize,
    #[arg(short = 'e', long)]
    extended: bool,
    #[arg(short = 'v', long)]
    verbose: bool,
    #[arg(long, default_value = "")]
    batch_json: String,
    #[arg(long, default_value = "")]
    batch_file: String,
    #[arg(long, default_value_t = 4)]
    batch_workers: usize,
    #[arg(long, default_value = "")]
    build_cache: String,
    #[arg(long, default_value = "")]
    build_lookup: String,
    #[arg(long, default_value = "")]
    anima_csv: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct TagEntry {
    tag: String,
    category: String,
    source_category: String,
    count: u64,
    alias_space: Vec<String>,
    alias_under: Vec<String>,
    translation_space: String,
    translation_under: String,
    translation_parts: Vec<String>,
    group: String,
    source: String,
    priority: f64,
    tag_space: String,
    tag_under: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct CacheFile {
    version: u32,
    entries: Vec<TagEntry>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct LookupEntry {
    key: String,
    offset: u64,
    len: u32,
}

#[derive(Debug, Serialize, Deserialize)]
struct LookupIndexFile {
    version: u32,
    entries: Vec<LookupEntry>,
}

#[derive(Debug)]
struct LookupRuntime {
    entries: Vec<LookupEntry>,
    values_path: PathBuf,
    records: Vec<TagResult>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct TagResult {
    tag: String,
    prompt_tag: String,
    category: String,
    source_category: String,
    count: u64,
    match_score: f64,
}

#[derive(Debug, Deserialize)]
struct BatchPayload {
    queries: Vec<BatchQuery>,
}

#[derive(Debug, Deserialize)]
struct BatchQuery {
    id: String,
    #[serde(default)]
    keyword: String,
    #[serde(default)]
    prefix: String,
    #[serde(default)]
    category: String,
    #[serde(default)]
    group: String,
    #[serde(default)]
    limit: Option<usize>,
    #[serde(default)]
    min_count: Option<u64>,
}

#[derive(Debug, Clone)]
struct QuerySpec {
    keyword: String,
    prefix: String,
    group: String,
    min_count: u64,
    limit: usize,
}

fn normalize_text(value: &str) -> String {
    let mut out = String::with_capacity(value.len());
    let mut last_space = false;
    for ch in value
        .replace("\\(", "(")
        .replace("\\)", ")")
        .trim_matches(|c: char| c == '"' || c == '\'' || c == '`')
        .trim_start_matches('@')
        .chars()
    {
        let mapped = match ch {
            '_' | '-' | '(' | ')' | '[' | ']' | '{' | '}' | '\t' | '\r' | '\n' => ' ',
            _ => ch.to_ascii_lowercase(),
        };
        if mapped.is_whitespace() {
            if !last_space {
                out.push(' ');
                last_space = true;
            }
        } else {
            out.push(mapped);
            last_space = false;
        }
    }
    out.trim().to_string()
}

fn normalize_under(value: &str) -> String {
    normalize_text(value).replace(' ', "_")
}

fn category_name(raw: &str) -> String {
    match raw.trim().to_ascii_lowercase().as_str() {
        "0" | "general" => "general".to_string(),
        "1" | "artist" | "artists" => "artist".to_string(),
        "3" | "series" | "copyright" | "copyrights" => "copyright".to_string(),
        "4" | "character" | "characters" => "character".to_string(),
        "5" | "meta" | "metadata" => "meta".to_string(),
        other if !other.is_empty() => other.to_string(),
        _ => "general".to_string(),
    }
}

fn anima_category_name(raw: &str) -> String {
    match raw.trim().to_ascii_lowercase().as_str() {
        "0" | "6" | "general" => "general".to_string(),
        "1" | "artist" | "artists" => "artist".to_string(),
        "3" | "series" | "copyright" | "copyrights" => "copyright".to_string(),
        "4" | "character" | "characters" => "character".to_string(),
        "5" | "-1" | "meta" | "metadata" => "meta".to_string(),
        other if !other.is_empty() => other.to_string(),
        _ => "general".to_string(),
    }
}

fn prompt_tag(tag: &str, category: &str, for_prompt: bool) -> String {
    let clean = tag.trim().to_ascii_lowercase();
    if for_prompt && category == "artist" && !clean.starts_with('@') {
        format!("@{}", clean)
    } else {
        clean
    }
}

fn split_aliases(value: &str) -> Vec<String> {
    value
        .split(|c| c == ',' || c == '|' || c == ';')
        .map(str::trim)
        .filter(|item| !item.is_empty())
        .map(ToOwned::to_owned)
        .collect()
}

fn should_skip_source_tag(tag: &str, category: &str) -> bool {
    let clean = tag.trim().trim_start_matches('@').to_ascii_lowercase();
    if clean.is_empty() {
        return true;
    }
    if clean.starts_with('_') || clean.ends_with('_') {
        return true;
    }
    if matches!(
        clean.as_str(),
        "bad_tag"
            | "tagme"
            | "commentary"
            | "commentary_request"
            | "missing_commentary"
            | "check_commentary"
            | "delete_request"
            | "model_request"
            | "watermark"
            | "sample_watermark"
            | "weibo_watermark"
            | "miyoushe_watermark"
            | "commission_watermark"
            | "too_many_watermarks"
            | "character_watermark"
            | "artist_name"
            | "signature"
            | "logo"
            | "text"
    ) {
        return true;
    }
    if clean.ends_with("_commentary")
        || clean.ends_with("-only_commentary")
        || clean.contains("watermark")
    {
        return true;
    }
    category == "meta" && (clean.contains("request") || clean.contains("commentary"))
}

fn normalized_aliases(aliases: &[String]) -> (Vec<String>, Vec<String>) {
    let mut spaces = Vec::new();
    let mut unders = Vec::new();
    for alias in aliases {
        let space = normalize_text(alias);
        if space.is_empty() {
            continue;
        }
        let under = space.replace(' ', "_");
        spaces.push(space);
        unders.push(under);
    }
    (spaces, unders)
}

fn normalized_translation_parts(value: &str) -> Vec<String> {
    value
        .split('|')
        .map(normalize_text)
        .filter(|item| !item.is_empty())
        .collect()
}

fn repo_root_candidates() -> Vec<PathBuf> {
    let mut roots = Vec::new();
    if let Ok(value) = env::var("SIMPAI_TAGS_ROOT") {
        roots.push(PathBuf::from(value));
    }
    if let Ok(value) = env::var("SIMPAI_DANBOORU_TAGS_DATA") {
        roots.push(PathBuf::from(value));
    }
    if let Ok(cwd) = env::current_dir() {
        let mut current = Some(cwd.as_path());
        while let Some(path) = current {
            roots.push(path.to_path_buf());
            current = path.parent();
        }
    }
    if let Ok(exe) = env::current_exe() {
        if let Some(parent) = exe.parent() {
            let mut current = Some(parent);
            while let Some(path) = current {
                roots.push(path.to_path_buf());
                current = path.parent();
            }
        }
    }
    roots
}

fn find_tags_root() -> Option<PathBuf> {
    let mut seen = HashSet::new();
    for root in repo_root_candidates() {
        let canonical = fs::canonicalize(&root).unwrap_or(root.clone());
        if !seen.insert(canonical.clone()) {
            continue;
        }
        if canonical.join("tags").join("danbooru_all.csv").is_file() {
            return Some(canonical);
        }
        if canonical.join("danbooru_all.csv").is_file() {
            return Some(canonical);
        }
    }
    None
}

fn tag_file(root: &Path, name: &str) -> PathBuf {
    let nested = root.join("tags").join(name);
    if nested.is_file() {
        nested
    } else {
        root.join(name)
    }
}

fn source_data_files(root: &Path) -> Vec<PathBuf> {
    [
        "danbooru_all.csv",
        "weilin_tagcart.csv",
        "custom_tags.csv",
        "character_glossary.csv",
        "anima-1.0.csv",
    ]
    .iter()
    .map(|name| tag_file(root, name))
    .filter(|path| path.is_file())
    .collect()
}

fn anima_csv_candidates(extra_path: &str) -> Vec<PathBuf> {
    let mut output = Vec::new();
    if !extra_path.trim().is_empty() {
        output.push(PathBuf::from(extra_path.trim()));
    }
    if let Ok(value) = env::var("SIMPAI_ANIMA_TAGS_CSV") {
        output.push(PathBuf::from(value));
    }
    for root in repo_root_candidates() {
        output.push(tag_file(&root, "anima-1.0.csv"));
        output.push(
            root.join("vendor")
                .join("danbooru-tags")
                .join("anima-1.0.csv"),
        );
    }
    output
}

fn find_anima_csv(extra_path: &str) -> Option<PathBuf> {
    let mut seen = HashSet::new();
    for path in anima_csv_candidates(extra_path) {
        let canonical = fs::canonicalize(&path).unwrap_or(path.clone());
        if seen.insert(canonical.clone()) && canonical.is_file() {
            return Some(canonical);
        }
    }
    None
}

fn cache_file_candidates() -> Vec<PathBuf> {
    let mut output = Vec::new();
    if let Ok(value) = env::var("SIMPAI_DANBOORU_TAGS_CACHE") {
        output.push(PathBuf::from(value));
    }
    for root in repo_root_candidates() {
        output.push(root.join("tags_cache.bin"));
        output.push(root.join("tags_cache.tsv"));
        output.push(root.join("danbooru_tags.cache.bin"));
        output.push(root.join("danbooru_tags.cache.tsv"));
    }
    output
}

fn find_cache_file() -> Option<PathBuf> {
    let mut seen = HashSet::new();
    for path in cache_file_candidates() {
        let canonical = fs::canonicalize(&path).unwrap_or(path.clone());
        if seen.insert(canonical.clone()) && canonical.is_file() {
            return Some(canonical);
        }
    }
    None
}

fn cache_is_fresh(cache_path: &Path, tags_root: Option<&Path>) -> bool {
    let Ok(cache_meta) = fs::metadata(cache_path) else {
        return false;
    };
    let Ok(cache_modified) = cache_meta.modified() else {
        return false;
    };
    let Some(root) = tags_root else {
        return true;
    };
    for data_file in source_data_files(root) {
        if let Ok(modified) = fs::metadata(data_file).and_then(|meta| meta.modified()) {
            if modified > cache_modified {
                return false;
            }
        }
    }
    true
}

fn escape_cache_field(value: &str) -> String {
    let mut output = String::with_capacity(value.len());
    for ch in value.chars() {
        match ch {
            '\\' => output.push_str("\\\\"),
            '\t' => output.push_str("\\t"),
            '\n' => output.push_str("\\n"),
            '\r' => output.push_str("\\r"),
            '\u{1f}' => output.push_str("\\x1f"),
            _ => output.push(ch),
        }
    }
    output
}

fn unescape_cache_field(value: &str) -> String {
    let mut output = String::with_capacity(value.len());
    let mut chars = value.chars();
    while let Some(ch) = chars.next() {
        if ch != '\\' {
            output.push(ch);
            continue;
        }
        match chars.next() {
            Some('\\') => output.push('\\'),
            Some('t') => output.push('\t'),
            Some('n') => output.push('\n'),
            Some('r') => output.push('\r'),
            Some('x') => {
                let first = chars.next();
                let second = chars.next();
                if first == Some('1') && second == Some('f') {
                    output.push('\u{1f}');
                } else {
                    output.push('\\');
                    output.push('x');
                    if let Some(item) = first {
                        output.push(item);
                    }
                    if let Some(item) = second {
                        output.push(item);
                    }
                }
            }
            Some(other) => output.push(other),
            None => output.push('\\'),
        }
    }
    output
}

fn cache_join(items: &[String]) -> String {
    items
        .iter()
        .map(|item| escape_cache_field(item))
        .collect::<Vec<_>>()
        .join("\u{1f}")
}

fn cache_split(value: &str) -> Vec<String> {
    if value.is_empty() {
        return Vec::new();
    }
    value.split('\u{1f}').map(unescape_cache_field).collect()
}

fn cache_is_tsv(path: &Path) -> bool {
    path.extension()
        .and_then(|value| value.to_str())
        .map(|value| value.eq_ignore_ascii_case("tsv"))
        .unwrap_or(false)
}

fn write_binary_cache_entries(path: &Path, entries: &[TagEntry]) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|exc| format!("Failed to create cache directory: {exc}"))?;
    }
    let file = File::create(path).map_err(|exc| format!("Failed to create cache file: {exc}"))?;
    let mut writer = BufWriter::new(file);
    let cache = CacheFile {
        version: 1,
        entries: entries.to_vec(),
    };
    bincode::serialize_into(&mut writer, &cache)
        .map_err(|exc| format!("Failed to write binary cache: {exc}"))?;
    writer
        .flush()
        .map_err(|exc| format!("Failed to flush cache file: {exc}"))?;
    Ok(())
}

fn load_binary_cache_entries(path: &Path) -> Result<Vec<TagEntry>, String> {
    let file = File::open(path).map_err(|exc| format!("Failed to open cache file: {exc}"))?;
    let mut reader = BufReader::new(file);
    let cache: CacheFile = bincode::deserialize_from(&mut reader)
        .map_err(|exc| format!("Failed to read binary cache: {exc}"))?;
    if cache.version != 1 {
        return Err(format!("Unsupported cache version: {}", cache.version));
    }
    Ok(cache.entries)
}

fn write_cache_entries(path: &Path, entries: &[TagEntry]) -> Result<(), String> {
    if !cache_is_tsv(path) {
        return write_binary_cache_entries(path, entries);
    }
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|exc| format!("Failed to create cache directory: {exc}"))?;
    }
    let file = File::create(path).map_err(|exc| format!("Failed to create cache file: {exc}"))?;
    let mut writer = BufWriter::new(file);
    writeln!(writer, "# simpai-danbooru-tags-cache-v1")
        .map_err(|exc| format!("Failed to write cache header: {exc}"))?;
    for entry in entries {
        let fields = [
            escape_cache_field(&entry.tag),
            escape_cache_field(&entry.category),
            escape_cache_field(&entry.source_category),
            entry.count.to_string(),
            cache_join(&entry.alias_space),
            cache_join(&entry.alias_under),
            escape_cache_field(&entry.translation_space),
            escape_cache_field(&entry.translation_under),
            cache_join(&entry.translation_parts),
            escape_cache_field(&entry.group),
            escape_cache_field(&entry.source),
            entry.priority.to_string(),
            escape_cache_field(&entry.tag_space),
            escape_cache_field(&entry.tag_under),
        ];
        writeln!(writer, "{}", fields.join("\t"))
            .map_err(|exc| format!("Failed to write cache row: {exc}"))?;
    }
    writer
        .flush()
        .map_err(|exc| format!("Failed to flush cache file: {exc}"))?;
    Ok(())
}

fn load_cache_entries(path: &Path) -> Result<Vec<TagEntry>, String> {
    if !cache_is_tsv(path) {
        return load_binary_cache_entries(path);
    }
    let file = File::open(path).map_err(|exc| format!("Failed to open cache file: {exc}"))?;
    let reader = BufReader::new(file);
    let mut entries = Vec::new();
    for (index, line) in reader.lines().enumerate() {
        let line = line.map_err(|exc| format!("Failed to read cache row: {exc}"))?;
        if index == 0 && line.starts_with("# simpai-danbooru-tags-cache-v1") {
            continue;
        }
        if line.trim().is_empty() || line.starts_with('#') {
            continue;
        }
        let fields: Vec<&str> = line.split('\t').collect();
        if fields.len() < 14 {
            continue;
        }
        entries.push(TagEntry {
            tag: unescape_cache_field(fields[0]),
            category: unescape_cache_field(fields[1]),
            source_category: unescape_cache_field(fields[2]),
            count: fields[3].parse::<u64>().unwrap_or(0),
            alias_space: cache_split(fields[4]),
            alias_under: cache_split(fields[5]),
            translation_space: unescape_cache_field(fields[6]),
            translation_under: unescape_cache_field(fields[7]),
            translation_parts: cache_split(fields[8]),
            group: unescape_cache_field(fields[9]),
            source: unescape_cache_field(fields[10]),
            priority: fields[11].parse::<f64>().unwrap_or(0.0),
            tag_space: unescape_cache_field(fields[12]),
            tag_under: unescape_cache_field(fields[13]),
        });
    }
    Ok(entries)
}

fn lookup_values_path(index_path: &Path) -> PathBuf {
    index_path.with_file_name("tags_lookup_values.bin")
}

fn lookup_records_path(index_path: &Path) -> PathBuf {
    index_path.with_file_name("tags_lookup_records.bin")
}

fn lookup_file_candidates() -> Vec<PathBuf> {
    let mut output = Vec::new();
    if let Ok(value) = env::var("SIMPAI_DANBOORU_TAGS_LOOKUP") {
        output.push(PathBuf::from(value));
    }
    for root in repo_root_candidates() {
        output.push(root.join("tags_lookup.bin"));
        output.push(root.join("danbooru_tags.lookup.bin"));
    }
    output
}

fn find_lookup_file() -> Option<PathBuf> {
    let mut seen = HashSet::new();
    for path in lookup_file_candidates() {
        let canonical = fs::canonicalize(&path).unwrap_or(path.clone());
        if seen.insert(canonical.clone())
            && canonical.is_file()
            && lookup_values_path(&canonical).is_file()
            && lookup_records_path(&canonical).is_file()
        {
            return Some(canonical);
        }
    }
    None
}

fn lookup_is_fresh(index_path: &Path, tags_root: Option<&Path>) -> bool {
    let Ok(index_modified) = fs::metadata(index_path).and_then(|meta| meta.modified()) else {
        return false;
    };
    let values_path = lookup_values_path(index_path);
    let records_path = lookup_records_path(index_path);
    let Ok(values_modified) = fs::metadata(values_path).and_then(|meta| meta.modified()) else {
        return false;
    };
    let Ok(records_modified) = fs::metadata(records_path).and_then(|meta| meta.modified()) else {
        return false;
    };
    let cache_modified = index_modified.min(values_modified).min(records_modified);
    let Some(root) = tags_root else {
        return true;
    };
    for data_file in source_data_files(root) {
        if let Ok(modified) = fs::metadata(data_file).and_then(|meta| meta.modified()) {
            if modified > cache_modified {
                return false;
            }
        }
    }
    true
}

fn load_lookup_runtime(path: &Path) -> Result<LookupRuntime, String> {
    let file = File::open(path).map_err(|exc| format!("Failed to open lookup index: {exc}"))?;
    let mut reader = BufReader::new(file);
    let index: LookupIndexFile = bincode::deserialize_from(&mut reader)
        .map_err(|exc| format!("Failed to read lookup index: {exc}"))?;
    if index.version != 1 {
        return Err(format!(
            "Unsupported lookup index version: {}",
            index.version
        ));
    }
    let records_file = File::open(lookup_records_path(path))
        .map_err(|exc| format!("Failed to open lookup records: {exc}"))?;
    let mut records_reader = BufReader::new(records_file);
    let records: Vec<TagResult> = bincode::deserialize_from(&mut records_reader)
        .map_err(|exc| format!("Failed to read lookup records: {exc}"))?;
    Ok(LookupRuntime {
        entries: index.entries,
        values_path: lookup_values_path(path),
        records,
    })
}

fn find_lookup_runtime(tags_root: Option<&Path>) -> Option<LookupRuntime> {
    let path = find_lookup_file()?;
    if !lookup_is_fresh(&path, tags_root) {
        return None;
    }
    load_lookup_runtime(&path).ok()
}

fn add_lookup_key(map: &mut BTreeMap<String, Vec<u32>>, key: &str, item_id: u32) {
    let clean = normalize_text(key);
    if clean.is_empty() {
        return;
    }
    map.entry(clean.clone()).or_default().push(item_id);
    let under = clean.replace(' ', "_");
    if under != clean {
        map.entry(under).or_default().push(item_id);
    }
}

fn write_lookup_entries(path: &Path, entries: &[TagEntry]) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|exc| format!("Failed to create lookup directory: {exc}"))?;
    }
    let values_path = lookup_values_path(path);
    let records_path = lookup_records_path(path);
    let records: Vec<TagResult> = entries
        .iter()
        .map(|entry| {
            result_from_entry(
                entry,
                1000.0
                    + if entry.count > 0 {
                        (entry.count as f64).log10().min(8.0)
                    } else {
                        0.0
                    }
                    + entry.priority,
                true,
            )
        })
        .collect();
    let mut lookup: BTreeMap<String, Vec<u32>> = BTreeMap::new();
    for (item_id, entry) in entries.iter().enumerate() {
        let item_id = item_id as u32;
        add_lookup_key(&mut lookup, &entry.tag_space, item_id);
        add_lookup_key(&mut lookup, &entry.tag_under, item_id);
        for alias in &entry.alias_space {
            add_lookup_key(&mut lookup, alias, item_id);
        }
        for alias in &entry.alias_under {
            add_lookup_key(&mut lookup, alias, item_id);
        }
        add_lookup_key(&mut lookup, &entry.translation_space, item_id);
        add_lookup_key(&mut lookup, &entry.translation_under, item_id);
        for part in &entry.translation_parts {
            add_lookup_key(&mut lookup, part, item_id);
        }
    }

    let mut records_writer = BufWriter::new(
        File::create(&records_path)
            .map_err(|exc| format!("Failed to create lookup records: {exc}"))?,
    );
    bincode::serialize_into(&mut records_writer, &records)
        .map_err(|exc| format!("Failed to write lookup records: {exc}"))?;
    records_writer
        .flush()
        .map_err(|exc| format!("Failed to flush lookup records: {exc}"))?;

    let mut values_writer = BufWriter::new(
        File::create(&values_path)
            .map_err(|exc| format!("Failed to create lookup values: {exc}"))?,
    );
    let mut index_entries = Vec::with_capacity(lookup.len());
    for (key, mut values) in lookup {
        values.sort_by(|left, right| {
            let left_item = &records[*left as usize];
            let right_item = &records[*right as usize];
            right_item
                .match_score
                .partial_cmp(&left_item.match_score)
                .unwrap_or(Ordering::Equal)
                .then_with(|| right_item.count.cmp(&left_item.count))
                .then_with(|| left_item.tag.cmp(&right_item.tag))
        });
        let mut seen = HashSet::new();
        values.retain(|item_id| seen.insert(records[*item_id as usize].tag.clone()));
        values.truncate(8);
        let encoded = bincode::serialize(&values)
            .map_err(|exc| format!("Failed to encode lookup values: {exc}"))?;
        let offset = values_writer
            .stream_position()
            .map_err(|exc| format!("Failed to seek lookup values: {exc}"))?;
        values_writer
            .write_all(&encoded)
            .map_err(|exc| format!("Failed to write lookup values: {exc}"))?;
        index_entries.push(LookupEntry {
            key,
            offset,
            len: encoded.len() as u32,
        });
    }
    values_writer
        .flush()
        .map_err(|exc| format!("Failed to flush lookup values: {exc}"))?;

    let index = LookupIndexFile {
        version: 1,
        entries: index_entries,
    };
    let mut index_writer = BufWriter::new(
        File::create(path).map_err(|exc| format!("Failed to create lookup index: {exc}"))?,
    );
    bincode::serialize_into(&mut index_writer, &index)
        .map_err(|exc| format!("Failed to write lookup index: {exc}"))?;
    index_writer
        .flush()
        .map_err(|exc| format!("Failed to flush lookup index: {exc}"))?;
    Ok(())
}

fn lower_bound_lookup(entries: &[LookupEntry], key: &str) -> usize {
    entries.partition_point(|entry| entry.key.as_str() < key)
}

fn read_lookup_values(file: &mut File, entry: &LookupEntry) -> Result<Vec<u32>, String> {
    file.seek(SeekFrom::Start(entry.offset))
        .map_err(|exc| format!("Failed to seek lookup values: {exc}"))?;
    let mut buffer = vec![0_u8; entry.len as usize];
    file.read_exact(&mut buffer)
        .map_err(|exc| format!("Failed to read lookup values: {exc}"))?;
    bincode::deserialize(&buffer).map_err(|exc| format!("Failed to decode lookup values: {exc}"))
}

fn lookup_category_matches(item: &TagResult, group: &str) -> bool {
    let clean = category_name(group);
    if group.trim().is_empty() {
        return true;
    }
    clean == item.category || (clean == "copyright" && item.category == "copyright")
}

fn push_lookup_values(
    rows: &mut Vec<(f64, bool, TagResult)>,
    runtime: &LookupRuntime,
    values_file: &mut File,
    key: &str,
    spec: &QuerySpec,
    exact: bool,
    seen_keys: &mut HashSet<String>,
) {
    let clean = normalize_text(key);
    if clean.is_empty() || !seen_keys.insert(format!("{}:{}", exact, clean)) {
        return;
    }
    let start = lower_bound_lookup(&runtime.entries, &clean);
    let mut visited = 0_usize;
    for entry in runtime.entries.iter().skip(start) {
        if exact {
            if entry.key != clean {
                break;
            }
        } else if !entry.key.starts_with(&clean) {
            break;
        }
        if let Ok(values) = read_lookup_values(values_file, entry) {
            for item_id in values {
                let Some(mut item) = runtime.records.get(item_id as usize).cloned() else {
                    continue;
                };
                if item.count < spec.min_count || !lookup_category_matches(&item, &spec.group) {
                    continue;
                }
                let mut score = item.match_score;
                if !exact {
                    let boost = if item.count > 0 {
                        (item.count as f64).log10().min(8.0)
                    } else {
                        0.0
                    };
                    score = (780.0 + boost).min(score);
                    item.match_score = (score * 1000.0).round() / 1000.0;
                }
                rows.push((score, exact && score >= 850.0, item));
            }
        }
        visited += 1;
        if visited >= 64 || rows.len() >= spec.limit.saturating_mul(12).max(48) {
            break;
        }
    }
}

fn query_lookup(
    runtime: &LookupRuntime,
    spec: &QuerySpec,
) -> Option<(Vec<TagResult>, Vec<TagResult>)> {
    let query = if !spec.prefix.trim().is_empty() {
        spec.prefix.trim()
    } else {
        spec.keyword.trim()
    };
    let q_space = normalize_text(query);
    if q_space.is_empty() {
        return Some((Vec::new(), Vec::new()));
    }
    let q_under = q_space.replace(' ', "_");
    let prefix = !spec.prefix.trim().is_empty();
    let mut values_file = File::open(&runtime.values_path).ok()?;
    let mut rows = Vec::new();
    let mut seen_keys = HashSet::new();
    if !prefix {
        push_lookup_values(
            &mut rows,
            runtime,
            &mut values_file,
            &q_space,
            spec,
            true,
            &mut seen_keys,
        );
        if q_under != q_space {
            push_lookup_values(
                &mut rows,
                runtime,
                &mut values_file,
                &q_under,
                spec,
                true,
                &mut seen_keys,
            );
        }
    }
    push_lookup_values(
        &mut rows,
        runtime,
        &mut values_file,
        &q_space,
        spec,
        false,
        &mut seen_keys,
    );
    if q_under != q_space {
        push_lookup_values(
            &mut rows,
            runtime,
            &mut values_file,
            &q_under,
            spec,
            false,
            &mut seen_keys,
        );
    }
    rows.sort_by(|left, right| {
        right
            .0
            .partial_cmp(&left.0)
            .unwrap_or(Ordering::Equal)
            .then_with(|| right.2.count.cmp(&left.2.count))
            .then_with(|| left.2.tag.cmp(&right.2.tag))
    });
    let mut seen_tags = HashSet::new();
    let mut confirmed = Vec::new();
    let mut candidates = Vec::new();
    for (_, confirmed_row, item) in rows {
        if !seen_tags.insert(item.tag.clone()) {
            continue;
        }
        if confirmed_row {
            confirmed.push(item);
        } else {
            candidates.push(item);
        }
        if confirmed.len() + candidates.len() >= spec.limit.saturating_mul(2).max(spec.limit) {
            break;
        }
    }
    confirmed.truncate(spec.limit);
    candidates.truncate(spec.limit);
    Some((confirmed, candidates))
}

fn load_csv_entries_with_category_mapper(
    path: &Path,
    source: &str,
    priority: f64,
    entries: &mut Vec<TagEntry>,
    category_mapper: fn(&str) -> String,
) -> csv::Result<()> {
    if !path.is_file() {
        return Ok(());
    }
    let mut reader = csv::ReaderBuilder::new()
        .has_headers(false)
        .flexible(true)
        .from_path(path)?;
    for record in reader.records() {
        let record = record?;
        let tag = record.get(0).unwrap_or("").trim().to_ascii_lowercase();
        if tag.is_empty() || tag == "tag" || tag == "source_term" {
            continue;
        }
        let category = category_mapper(record.get(1).unwrap_or(""));
        if should_skip_source_tag(&tag, &category) {
            continue;
        }
        let count = record
            .get(2)
            .unwrap_or("0")
            .trim()
            .parse::<u64>()
            .unwrap_or(0);
        let aliases = split_aliases(record.get(3).unwrap_or(""));
        let translation = record.get(4).unwrap_or("").trim().to_string();
        let group = record.get(5).unwrap_or("").trim().to_string();
        let source_category = category.clone();
        let (alias_space, alias_under) = normalized_aliases(&aliases);
        let translation_space = normalize_text(&translation);
        let translation_under = translation_space.replace(' ', "_");
        let translation_parts = normalized_translation_parts(&translation);
        entries.push(TagEntry {
            tag_space: normalize_text(&tag),
            tag_under: normalize_under(&tag),
            tag,
            category,
            source_category,
            count,
            alias_space,
            alias_under,
            translation_space,
            translation_under,
            translation_parts,
            group,
            source: source.to_string(),
            priority,
        });
    }
    Ok(())
}

fn load_csv_entries(
    path: &Path,
    source: &str,
    priority: f64,
    entries: &mut Vec<TagEntry>,
) -> csv::Result<()> {
    load_csv_entries_with_category_mapper(path, source, priority, entries, category_name)
}

fn load_anima_csv_entries(path: &Path, entries: &mut Vec<TagEntry>) -> csv::Result<()> {
    load_csv_entries_with_category_mapper(
        path,
        "anima-1.0.csv",
        120.0,
        entries,
        anima_category_name,
    )
}

fn load_glossary_entries(path: &Path, entries: &mut Vec<TagEntry>) -> csv::Result<()> {
    if !path.is_file() {
        return Ok(());
    }
    let mut reader = csv::ReaderBuilder::new().flexible(true).from_path(path)?;
    for row in reader.deserialize::<BTreeMap<String, String>>() {
        let row = row?;
        let character = row
            .get("character_tag")
            .map(String::as_str)
            .unwrap_or("")
            .trim()
            .to_ascii_lowercase();
        let copyright = row
            .get("copyright_tag")
            .map(String::as_str)
            .unwrap_or("")
            .trim()
            .to_ascii_lowercase();
        let aliases = split_aliases(row.get("aliases").map(String::as_str).unwrap_or(""));
        let translation = row.get("translation").cloned().unwrap_or_default();
        let source_term = row.get("source_term").cloned().unwrap_or_default();
        if !character.is_empty() {
            let mut merged_aliases = aliases.clone();
            if !source_term.trim().is_empty() {
                merged_aliases.push(source_term.clone());
            }
            let (alias_space, alias_under) = normalized_aliases(&merged_aliases);
            let translation_space = normalize_text(&translation);
            let translation_under = translation_space.replace(' ', "_");
            let translation_parts = normalized_translation_parts(&translation);
            entries.push(TagEntry {
                tag_space: normalize_text(&character),
                tag_under: normalize_under(&character),
                tag: character,
                category: "character".to_string(),
                source_category: "character".to_string(),
                count: 0,
                alias_space,
                alias_under,
                translation_space,
                translation_under,
                translation_parts,
                group: "character_glossary".to_string(),
                source: "character_glossary.csv".to_string(),
                priority: 450.0,
            });
        }
        if !copyright.is_empty() {
            let translation_space = normalize_text(&source_term);
            let translation_under = translation_space.replace(' ', "_");
            let translation_parts = normalized_translation_parts(&source_term);
            entries.push(TagEntry {
                tag_space: normalize_text(&copyright),
                tag_under: normalize_under(&copyright),
                tag: copyright,
                category: "copyright".to_string(),
                source_category: "copyright".to_string(),
                count: 0,
                alias_space: Vec::new(),
                alias_under: Vec::new(),
                translation_space,
                translation_under,
                translation_parts,
                group: "character_glossary".to_string(),
                source: "character_glossary.csv".to_string(),
                priority: 250.0,
            });
        }
    }
    Ok(())
}

fn load_entries_from_csv(anima_csv: &str) -> Result<Vec<TagEntry>, String> {
    let root =
        find_tags_root().ok_or_else(|| "Could not find tags/danbooru_all.csv".to_string())?;
    let mut entries = Vec::new();
    load_csv_entries(
        &tag_file(&root, "danbooru_all.csv"),
        "danbooru_all.csv",
        0.0,
        &mut entries,
    )
    .map_err(|exc| format!("Failed to read danbooru_all.csv: {exc}"))?;
    load_csv_entries(
        &tag_file(&root, "weilin_tagcart.csv"),
        "weilin_tagcart.csv",
        35.0,
        &mut entries,
    )
    .map_err(|exc| format!("Failed to read weilin_tagcart.csv: {exc}"))?;
    load_csv_entries(
        &tag_file(&root, "custom_tags.csv"),
        "custom_tags.csv",
        80.0,
        &mut entries,
    )
    .map_err(|exc| format!("Failed to read custom_tags.csv: {exc}"))?;
    if let Some(path) = find_anima_csv(anima_csv) {
        load_anima_csv_entries(&path, &mut entries)
            .map_err(|exc| format!("Failed to read anima-1.0.csv: {exc}"))?;
    }
    load_glossary_entries(&tag_file(&root, "character_glossary.csv"), &mut entries)
        .map_err(|exc| format!("Failed to read character_glossary.csv: {exc}"))?;
    Ok(entries)
}

fn load_entries() -> Result<Vec<TagEntry>, String> {
    let tags_root = find_tags_root();
    if let Some(cache_path) = find_cache_file() {
        if cache_is_fresh(&cache_path, tags_root.as_deref()) {
            if let Ok(entries) = load_cache_entries(&cache_path) {
                if !entries.is_empty() {
                    return Ok(entries);
                }
            }
        }
    }
    load_entries_from_csv("")
}

fn category_matches(entry: &TagEntry, group: &str) -> bool {
    let clean = category_name(group);
    if group.trim().is_empty() {
        return true;
    }
    if clean == entry.category {
        return true;
    }
    clean == "copyright" && entry.category == "copyright"
}

fn score_entry(entry: &TagEntry, query: &str, prefix: bool) -> Option<f64> {
    let q_space = normalize_text(query);
    let q_under = normalize_under(query);
    if q_space.is_empty() {
        return None;
    }
    let mut score: f64 = 0.0;
    if prefix {
        if entry.tag_space.starts_with(&q_space) || entry.tag_under.starts_with(&q_under) {
            score = 780.0;
        }
    } else if entry.tag_space == q_space || entry.tag_under == q_under {
        score = 1000.0;
    } else if entry.tag_space.starts_with(&q_space) || entry.tag_under.starts_with(&q_under) {
        score = 780.0;
    } else if entry.tag_space.contains(&q_space) || entry.tag_under.contains(&q_under) {
        score = 430.0;
    }
    for (a_space, a_under) in entry.alias_space.iter().zip(entry.alias_under.iter()) {
        if prefix {
            if a_space.starts_with(&q_space) || a_under.starts_with(&q_under) {
                score = score.max(740.0);
            }
        } else if a_space == &q_space || a_under == &q_under {
            score = score.max(920.0);
        } else if a_space.starts_with(&q_space) || a_under.starts_with(&q_under) {
            score = score.max(700.0);
        }
    }
    if !entry.translation_space.is_empty() && !prefix {
        if entry.translation_space == q_space
            || entry.translation_parts.iter().any(|part| part == &q_space)
        {
            score = score.max(900.0);
        } else if entry.translation_space.contains(&q_space)
            || (!q_under.is_empty() && entry.translation_under.contains(&q_under))
        {
            score = score.max(660.0);
        }
    }
    if score <= 0.0 {
        return None;
    }
    let count_boost = if entry.count > 0 {
        (entry.count as f64).log10().min(8.0)
    } else {
        0.0
    };
    Some(score + count_boost + entry.priority)
}

fn result_from_entry(entry: &TagEntry, score: f64, for_prompt: bool) -> TagResult {
    let tag = prompt_tag(&entry.tag, &entry.category, for_prompt);
    TagResult {
        prompt_tag: tag.clone(),
        tag,
        category: entry.category.clone(),
        source_category: entry.source_category.clone(),
        count: entry.count,
        match_score: (score * 1000.0).round() / 1000.0,
    }
}

fn query_entries(
    entries: &[TagEntry],
    spec: &QuerySpec,
    for_prompt: bool,
) -> (Vec<TagResult>, Vec<TagResult>) {
    let query = if !spec.prefix.trim().is_empty() {
        spec.prefix.trim()
    } else {
        spec.keyword.trim()
    };
    let prefix = !spec.prefix.trim().is_empty();
    let mut scored: Vec<(f64, TagResult)> = entries
        .iter()
        .filter(|entry| entry.count >= spec.min_count)
        .filter(|entry| category_matches(entry, &spec.group))
        .filter_map(|entry| {
            score_entry(entry, query, prefix)
                .map(|score| (score, result_from_entry(entry, score, for_prompt)))
        })
        .collect();
    scored.sort_by(|left, right| {
        right
            .0
            .partial_cmp(&left.0)
            .unwrap_or(Ordering::Equal)
            .then_with(|| right.1.count.cmp(&left.1.count))
            .then_with(|| left.1.tag.cmp(&right.1.tag))
    });

    let mut seen = HashSet::new();
    let mut confirmed = Vec::new();
    let mut candidates = Vec::new();
    for (score, item) in scored {
        if !seen.insert(item.tag.clone()) {
            continue;
        }
        if score >= 850.0 {
            confirmed.push(item);
        } else {
            candidates.push(item);
        }
        if confirmed.len() + candidates.len() >= spec.limit.saturating_mul(3).max(spec.limit) {
            break;
        }
    }
    confirmed.truncate(spec.limit);
    candidates.truncate(spec.limit);
    (confirmed, candidates)
}

fn grouped(items: Vec<TagResult>) -> BTreeMap<String, Vec<TagResult>> {
    let mut output: BTreeMap<String, Vec<TagResult>> = BTreeMap::new();
    for item in items {
        output.entry(item.category.clone()).or_default().push(item);
    }
    output
}

fn response_for(confirmed: Vec<TagResult>, candidates: Vec<TagResult>) -> Value {
    let found = !confirmed.is_empty() || !candidates.is_empty();
    json!({
        "found": found,
        "confirmed_tags": grouped(confirmed),
        "candidate_tags": grouped(candidates),
    })
}

fn random_response(entries: &[TagEntry], spec: &QuerySpec, for_prompt: bool) -> Value {
    let group = spec.group.trim();
    let mut rows: Vec<&TagEntry> = entries
        .iter()
        .filter(|entry| entry.count >= spec.min_count)
        .filter(|entry| category_matches(entry, group))
        .collect();
    rows.sort_by(|left, right| {
        right
            .count
            .cmp(&left.count)
            .then_with(|| left.tag.cmp(&right.tag))
    });
    let limit = spec.limit.max(1);
    let items: Vec<TagResult> = rows
        .into_iter()
        .take(limit)
        .map(|entry| {
            result_from_entry(
                entry,
                500.0 + (entry.count as f64).log10().min(8.0),
                for_prompt,
            )
        })
        .collect();
    if for_prompt {
        json!({"random_artists_for_prompt": items.into_iter().take(1).collect::<Vec<_>>()})
    } else if category_name(group) == "artist" || group.trim().is_empty() {
        json!({"random_artists": items})
    } else {
        json!({"random_tags": items})
    }
}

fn run_batch_queries(
    entries: &[TagEntry],
    tasks: Vec<(String, QuerySpec)>,
    for_prompt: bool,
    workers: usize,
) -> serde_json::Map<String, Value> {
    if tasks.is_empty() {
        return serde_json::Map::new();
    }
    let worker_count = workers.max(1).min(tasks.len());
    if worker_count <= 1 {
        let mut results = serde_json::Map::new();
        for (id, spec) in tasks {
            let (confirmed, candidates) = query_entries(entries, &spec, for_prompt);
            results.insert(id, response_for(confirmed, candidates));
        }
        return results;
    }

    let chunk_size = (tasks.len() + worker_count - 1) / worker_count;
    let mut rows: Vec<(String, Value)> = Vec::with_capacity(tasks.len());
    thread::scope(|scope| {
        let mut handles = Vec::new();
        for chunk in tasks.chunks(chunk_size) {
            let local_tasks = chunk.to_vec();
            handles.push(scope.spawn(move || {
                let mut local_rows = Vec::with_capacity(local_tasks.len());
                for (id, spec) in local_tasks {
                    let (confirmed, candidates) = query_entries(entries, &spec, for_prompt);
                    local_rows.push((id, response_for(confirmed, candidates)));
                }
                local_rows
            }));
        }
        for handle in handles {
            if let Ok(mut local_rows) = handle.join() {
                rows.append(&mut local_rows);
            }
        }
    });

    let mut results = serde_json::Map::new();
    for (id, value) in rows {
        results.insert(id, value);
    }
    results
}

fn run_lookup_batch_queries(
    runtime: &LookupRuntime,
    tasks: Vec<(String, QuerySpec)>,
) -> serde_json::Map<String, Value> {
    let mut results = serde_json::Map::new();
    for (id, spec) in tasks {
        let (confirmed, candidates) =
            query_lookup(runtime, &spec).unwrap_or_else(|| (Vec::new(), Vec::new()));
        results.insert(id, response_for(confirmed, candidates));
    }
    results
}

fn spec_from_args(args: &Args) -> QuerySpec {
    let group = if !args.group.trim().is_empty() {
        args.group.clone()
    } else {
        args.category.clone()
    };
    QuerySpec {
        keyword: args.keyword.clone(),
        prefix: args.prefix.clone(),
        group,
        min_count: args.min_count,
        limit: args.limit.max(1).min(200),
    }
}

fn spec_from_batch(query: &BatchQuery, default_limit: usize) -> QuerySpec {
    let group = if !query.group.trim().is_empty() {
        query.group.clone()
    } else {
        query.category.clone()
    };
    QuerySpec {
        keyword: query.keyword.clone(),
        prefix: query.prefix.clone(),
        group,
        min_count: query.min_count.unwrap_or(0),
        limit: query.limit.unwrap_or(default_limit).max(1).min(200),
    }
}

fn print_json(value: &Value, compact: bool) -> Result<(), String> {
    let text = if compact {
        serde_json::to_string(value)
    } else {
        serde_json::to_string_pretty(value)
    }
    .map_err(|exc| format!("JSON encode failed: {exc}"))?;
    println!("{text}");
    Ok(())
}

fn run() -> Result<(), String> {
    let args = Args::parse();
    let tags_root = find_tags_root();
    if !args.build_cache.trim().is_empty() || !args.build_lookup.trim().is_empty() {
        let entries = load_entries_from_csv(&args.anima_csv)?;
        if !args.build_cache.trim().is_empty() {
            write_cache_entries(Path::new(args.build_cache.trim()), &entries)?;
        }
        if !args.build_lookup.trim().is_empty() {
            write_lookup_entries(Path::new(args.build_lookup.trim()), &entries)?;
        }
        return Ok(());
    }
    if !args.batch_file.trim().is_empty() || !args.batch_json.trim().is_empty() {
        let batch_text = if !args.batch_file.trim().is_empty() {
            fs::read_to_string(&args.batch_file)
                .map_err(|exc| format!("Failed to read batch file: {exc}"))?
        } else {
            args.batch_json.clone()
        };
        let batch_text = batch_text.trim_start_matches('\u{feff}');
        let batch: BatchPayload = serde_json::from_str(&batch_text)
            .map_err(|exc| format!("Invalid batch JSON: {exc}"))?;
        let tasks = batch
            .queries
            .into_iter()
            .map(|query| {
                let spec = spec_from_batch(&query, args.limit);
                (query.id, spec)
            })
            .collect();
        let results = if let Some(runtime) = find_lookup_runtime(tags_root.as_deref()) {
            run_lookup_batch_queries(&runtime, tasks)
        } else {
            let entries = load_entries()?;
            run_batch_queries(&entries, tasks, args.for_prompt, args.batch_workers)
        };
        return print_json(&json!({"results": results}), args.compact);
    }

    let spec = spec_from_args(&args);
    let value = if args.random > 0 {
        let entries = load_entries()?;
        let spec = QuerySpec {
            limit: args.random,
            ..spec
        };
        random_response(&entries, &spec, args.for_prompt)
    } else if let Some(runtime) = find_lookup_runtime(tags_root.as_deref()) {
        let (confirmed, candidates) =
            query_lookup(&runtime, &spec).unwrap_or_else(|| (Vec::new(), Vec::new()));
        response_for(confirmed, candidates)
    } else {
        let entries = load_entries()?;
        let (confirmed, candidates) = query_entries(&entries, &spec, args.for_prompt);
        response_for(confirmed, candidates)
    };
    print_json(&value, args.compact)
}

fn main() {
    if let Err(exc) = run() {
        eprintln!("{exc}");
        std::process::exit(1);
    }
}
