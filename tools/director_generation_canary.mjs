#!/usr/bin/env node

import { readFile, mkdir, writeFile } from "node:fs/promises";
import { existsSync, statSync } from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

const URL = process.env.SIMPAI_DIRECTOR_GENERATION_URL || "http://127.0.0.1:8186/?__theme=dark";
const CHROME = process.env.SIMPAI_CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const REPORT_DIR = process.env.SIMPAI_DIRECTOR_GENERATION_REPORT_DIR || "reports/director-generation-canary";
const ALLOW_GENERATE = /^(1|true|yes|on)$/i.test(process.env.SIMPAI_DIRECTOR_GENERATION_ALLOW_GENERATE || "");
const CASE_FILTER_ENV = String(process.env.SIMPAI_DIRECTOR_GENERATION_CASES || "").trim();
const MAX_RUN_MS = Number.parseInt(process.env.SIMPAI_DIRECTOR_GENERATION_MAX_RUN_MS || "900000", 10);

const CASES = {
  "wan-i2v": {
    id: "G-02",
    preset: "Wan图生视频",
    prompt: "A slow camera move across a neon street.",
    rows: [[0, 1, "A slow camera move across a neon street.", "image_1", "", "", "", "", "", ""]],
    media: {
      images: {
        image_1: "comfy/input/0.png",
      },
    },
    expect: { media: "video", prompt: "@image1" },
  },
  "wan-i2v-first-last": {
    id: "G-03",
    preset: "Wan图生视频",
    prompt: "A short first-last frame transition test.",
    rows: [[0, 1, "A short first-last frame transition test.", "image_1", "image_2", "", "", "", "", ""]],
    media: {
      images: {
        image_1: "comfy/input/0.png",
        image_2: "comfy/input/1.png",
      },
    },
    expect: { media: "video", prompt: "@image1" },
  },
  "ltx-t2v": {
    id: "G-04",
    preset: "LTX2.3文生视频",
    theme: "Text-to-Video",
    prompt: "A tiny cinematic test shot, soft studio light.",
    rows: [[0, 2, "A tiny cinematic test shot, soft studio light.", "", "", "", "", "", "", ""]],
    media: {},
    expect: { media: "video", prompt: "tiny cinematic" },
  },
  "ltx-ta2v": {
    id: "G-05",
    preset: "LTX2.3文生视频",
    theme: "Text+Audio to Video",
    prompt: "A tiny cinematic test shot following the reference audio.",
    rows: [[0, 2, "A tiny cinematic test shot following the reference audio.", "", "", "", "", "", "audio_1", ""]],
    media: {
      audio: {
        audio_1: "comfy/input/audio_example.MP3",
      },
    },
    expect: { media: "video", prompt: "@audio1" },
  },
  "infinitetalk": {
    id: "G-07",
    preset: "Wan无限对话",
    prompt: "A talking portrait follows the reference audio.",
    rows: [[0, 0, "A talking portrait follows the reference audio.", "image_1", "", "", "", "", "audio_1", ""]],
    media: {
      images: {
        image_1: "comfy/input/ttm_example.jpeg",
      },
      audio: {
        audio_1: "comfy/input/audio_example.MP3",
      },
    },
    expect: { media: "video", prompt: "@image1" },
  },
  "wan-extend-previous": {
    id: "G-08",
    preset: "Dasiwa视频延长",
    prompt: "Continue the source video motion.",
    rows: [
      [0, 1, "Continue the source video motion.", "", "", "", "", "", "", "video_1"],
      [1, 2, "Continue the previous shot result.", "", "", "", "", "", "", "previous_segment"],
    ],
    media: {
      video: {
        video_1: "comfy/input/example.mp4",
      },
    },
    expect: { media: "video", prompt: "@video1" },
  },
  "ltx-outpaint": {
    id: "G-09",
    preset: "LTX视频外扩",
    prompt: "Outpaint the source video while preserving motion.",
    rows: [[0, 0, "Outpaint the source video while preserving motion.", "", "", "", "", "", "", "video_1"]],
    media: {
      video: {
        video_1: "comfy/input/example.mp4",
      },
    },
    expect: { media: "video", prompt: "@video1" },
  },
  "hunyuan-foley": {
    id: "G-10",
    preset: "Foley音效生成",
    prompt: "Footsteps, cloth movement, and subtle room ambience.",
    rows: [[0, 0, "Footsteps, cloth movement, and subtle room ambience.", "", "", "", "", "", "", "video_1"]],
    media: {
      video: {
        video_1: "comfy/input/example.mp4",
      },
    },
    expect: { media: "video", prompt: "@video1" },
  },
  "nvidia-vsr": {
    id: "G-11",
    preset: "Nvidia超分辨率",
    prompt: "Upscale the source video.",
    rows: [[0, 0, "Upscale the source video.", "", "", "", "", "", "", "video_1"]],
    media: {
      video: {
        video_1: "comfy/input/example.mp4",
      },
    },
    expect: { media: "video", prompt: "@video1" },
  },
};

const CASE_FILTER = String(CASE_FILTER_ENV || Object.keys(CASES).join(",")).split(",").map((item) => item.trim()).filter(Boolean);

function compactText(value) {
  return String(value || "").trim().replace(/\s+/g, " ");
}

function assertCondition(condition, message, details = {}) {
  if (!condition) {
    const error = new Error(message);
    error.details = details;
    throw error;
  }
}

function mimeFor(filePath, kind) {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === ".jpg" || ext === ".jpeg") return "image/jpeg";
  if (ext === ".png") return "image/png";
  if (ext === ".webp") return "image/webp";
  if (ext === ".mp3") return "audio/mpeg";
  if (ext === ".wav") return "audio/wav";
  if (ext === ".m4a") return "audio/mp4";
  if (ext === ".mp4") return "video/mp4";
  if (ext === ".mov") return "video/quicktime";
  if (ext === ".webm") return "video/webm";
  if (kind === "audio") return "audio/mpeg";
  if (kind === "video") return "video/mp4";
  return "application/octet-stream";
}

function resolveFixture(filePath) {
  const resolved = path.resolve(filePath);
  assertCondition(existsSync(resolved), `fixture is missing: ${filePath}`, { filePath, resolved });
  return resolved;
}

async function imageRecord(ref, filePath) {
  const resolved = resolveFixture(filePath);
  const bytes = await readFile(resolved);
  const mime = mimeFor(resolved, "image");
  const dataUrl = `data:${mime};base64,${bytes.toString("base64")}`;
  return {
    type: "image",
    name: path.basename(resolved),
    title: path.basename(resolved),
    mime,
    size: bytes.length,
    data_url: dataUrl,
    thumb: dataUrl,
    path: resolved,
    ref,
  };
}

function fileRecord(ref, filePath, kind) {
  const resolved = resolveFixture(filePath);
  const stat = statSync(resolved);
  return {
    type: kind,
    name: path.basename(resolved),
    title: path.basename(resolved),
    mime: mimeFor(resolved, kind),
    size: stat.size,
    path: resolved,
    ref,
  };
}

async function buildMediaState(caseDef) {
  const images = {};
  const audio = {};
  const video = {};
  for (const [ref, filePath] of Object.entries(caseDef.media?.images || {})) {
    images[ref] = await imageRecord(ref, filePath);
  }
  for (const [ref, filePath] of Object.entries(caseDef.media?.audio || {})) {
    audio[ref] = fileRecord(ref, filePath, "audio");
  }
  for (const [ref, filePath] of Object.entries(caseDef.media?.video || {})) {
    video[ref] = fileRecord(ref, filePath, "video");
  }
  return { images, audio, video };
}

function installWatchers(page, events) {
  page.on("console", (message) => {
    const text = message.text();
    if (/Director|SceneDirector|Traceback|Error|error|not in the list of choices|queue|progress/i.test(text)) {
      events.push({ type: "console", level: message.type(), text: text.slice(0, 3000) });
    }
  });
  page.on("pageerror", (error) => {
    events.push({ type: "pageerror", text: String(error?.stack || error).slice(0, 5000) });
  });
  page.on("response", async (response) => {
    const url = response.url();
    if (!/gradio_api\/(queue|run|call|predict|api)/i.test(url)) return;
    const status = response.status();
    const text = status >= 400 ? await response.text().catch(() => "") : "";
    if (status >= 400 || /Traceback|Error|not in the list of choices/i.test(text)) {
      events.push({ type: "response", status, url, text: text.slice(0, 5000) });
    }
  });
}

async function waitForPresetIdle(page, delayMs = 2200) {
  await page.waitForLoadState("domcontentloaded", { timeout: 120000 }).catch(() => {});
  await page.waitForFunction(
    () => {
      const className = document.documentElement.className || "";
      const suppressed = typeof window.isSimpleAIPresetGallerySuppressed === "function"
        ? window.isSimpleAIPresetGallerySuppressed()
        : className.includes("simpai-preset-switch-gallery-suppressed");
      return !className.includes("simpai-preset-nav-active") && !suppressed;
    },
    { timeout: 90000 }
  ).catch(() => {});
  await page.waitForTimeout(delayMs);
}

async function clickPreset(page, label) {
  await page.getByText(label, { exact: true }).first().click({ timeout: 45000 });
  await waitForPresetIdle(page, 4500);
}

async function openDirector(page) {
  const button = page.locator("#scene_director_accordion button.label-wrap").first();
  await button.click({ timeout: 20000 });
  await page.waitForTimeout(1200);
  await page.evaluate(() => {
    if (window.sceneDirectorInitWorkspace) window.sceneDirectorInitWorkspace();
    if (window.refresh_scene_director_editor) window.refresh_scene_director_editor();
  });
  await page.waitForTimeout(800);
}

async function setPrompt(page, value) {
  const ok = await page.evaluate((text) => {
    const root = document.querySelector("#positive_prompt") || document.querySelector("#prompt");
    const input = root?.querySelector?.("textarea:not([disabled]), input:not([disabled])") || document.querySelector("textarea");
    if (!input) return false;
    input.focus();
    input.value = text;
    input.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }, value);
  assertCondition(ok, "prompt input was not found");
}

async function setSceneTheme(page, theme) {
  if (!theme) return { changed: false, skipped: true };
  const result = await page.evaluate((value) => {
    const root = document.querySelector("#scene_theme");
    if (!root) return { changed: false, reason: "missing" };
    const candidates = Array.from(root.querySelectorAll("input[type='radio'], input, textarea, select"));
    const select = candidates.find((item) => item.tagName === "SELECT");
    if (select) {
      select.value = value;
      select.dispatchEvent(new Event("input", { bubbles: true }));
      select.dispatchEvent(new Event("change", { bubbles: true }));
      return { changed: true, mode: "select", value: select.value };
    }
    const radio = candidates.find((item) => item.type === "radio" && String(item.value || "") === value);
    if (radio) {
      radio.checked = true;
      radio.dispatchEvent(new Event("input", { bubbles: true }));
      radio.dispatchEvent(new Event("change", { bubbles: true }));
      const label = radio.closest("label");
      if (label) {
        try { label.click(); } catch (error) {}
      }
      return { changed: true, mode: "radio", value: radio.value };
    }
    const input = candidates.find((item) => item.type !== "radio" && item.type !== "checkbox");
    if (input) {
      input.value = value;
      input.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: value }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      return { changed: true, mode: "input", value: input.value };
    }
    return { changed: false, reason: "no-value-control", text: (root.innerText || root.textContent || "").slice(0, 300) };
  }, theme);
  assertCondition(result.changed, "scene theme was not updated", { theme, result });
  await page.evaluate((value) => {
    try {
      window.simpleaiTopbarSystemParams = window.simpleaiTopbarSystemParams || {};
      window.simpleaiTopbarSystemParams.__scene_theme = value;
      window.simpleaiTopbarSystemParams.scene_theme = value;
      window.simpleaiTopbarSystemParams.switch_scene_theme = true;
      if (typeof window.sceneDirectorInitWorkspace === "function") window.sceneDirectorInitWorkspace();
      if (typeof window.refresh_scene_director_editor === "function") window.refresh_scene_director_editor();
    } catch (error) {}
  }, theme);
  await page.waitForTimeout(2500);
  return result;
}

async function configureDirector(page, caseDef, mediaState) {
  const result = await page.evaluate(({ rows, media, prompt, compose }) => {
    const setField = (selector, value) => {
      const root = document.querySelector(selector);
      const input = root?.querySelector?.("textarea, input") || (root?.matches?.("textarea,input") ? root : null);
      if (!input) return false;
      input.value = value;
      input.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: value }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    };
    const setCheckbox = (selector, checked) => {
      const root = document.querySelector(selector);
      const input = root?.querySelector?.("input[type='checkbox']");
      if (!input) return false;
      input.checked = !!checked;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    };
    const rowsText = JSON.stringify(rows);
    const mediaText = JSON.stringify(media);
    const changed = {
      editor: setField("#scene_director_editor_state", rowsText),
      media: setField("#scene_director_media_state", mediaText),
      enabled: setCheckbox("#scene_director_enabled", true),
      compose: setCheckbox("#scene_director_compose", !!compose),
    };
    if (window.sceneDirectorRenderMediaPreview) window.sceneDirectorRenderMediaPreview();
    if (window.refresh_scene_director_editor) window.refresh_scene_director_editor();
    if (window.sceneDirectorWriteRows) window.sceneDirectorWriteRows(rows);
    return {
      changed,
      mediaTextLength: mediaText.length,
      rowsText,
      prompt,
    };
  }, { rows: caseDef.rows, media: mediaState, prompt: caseDef.prompt, compose: !!caseDef.compose });
  assertCondition(result.changed.editor && result.changed.media && result.changed.enabled, "director DOM fields were not updated", result);
  await page.waitForTimeout(3500);
  const preview = await readDirectorPreview(page);
  const expectedPrompt = caseDef.expect?.prompt || "";
  assertCondition(!expectedPrompt || preview.promptPreview.includes(expectedPrompt), "director prompt preview did not update", { preview, expectedPrompt, result });
  return { preview, result };
}

async function readDirectorPreview(page) {
  return page.evaluate(() => {
    const valueOf = (selector) => {
      const root = document.querySelector(selector);
      const input = root?.querySelector?.("textarea, input");
      if (input) return input.value || "";
      return root ? (root.innerText || root.textContent || "") : "";
    };
    const enabled = document.querySelector("#scene_director_enabled input[type='checkbox']");
    const compose = document.querySelector("#scene_director_compose input[type='checkbox']");
    const root = document.documentElement;
    return {
      promptPreview: valueOf("#scene_director_prompt_preview"),
      editorState: valueOf("#scene_director_editor_state"),
      mediaStateLength: valueOf("#scene_director_media_state").length,
      enabled: !!enabled?.checked,
      compose: !!compose?.checked,
      dataset: {
        imagePolicy: root.dataset.simpaiSceneDirectorImagePolicy || "",
        audioPolicy: root.dataset.simpaiSceneDirectorAudioPolicy || "",
        videoPolicy: root.dataset.simpaiSceneDirectorVideoPolicy || "",
        maxImages: root.dataset.simpaiSceneDirectorMaxImages || "",
        durationStrategy: root.dataset.simpaiSceneDirectorDurationStrategy || "",
        chainOutput: root.dataset.simpaiSceneDirectorChainOutput || "",
      },
    };
  });
}

function mediaCount(snapshot) {
  return Number(snapshot.finishedGallery?.imgs || 0) +
    Number(snapshot.finishedGallery?.videos || 0) +
    Number(snapshot.finalGallery?.imgs || 0) +
    Number(snapshot.finalGallery?.videos || 0) +
    Number(snapshot.progressVideo?.videos || 0);
}

async function readGenerationSnapshot(page, reason) {
  return page.evaluate((why) => {
    const hiddenByAncestor = (element) => {
      let node = element;
      while (node && node.nodeType === 1) {
        const style = window.getComputedStyle(node);
        if (node.hidden || node.hasAttribute("hidden") || style.display === "none" || style.visibility === "hidden") return true;
        node = node.parentElement;
      }
      return false;
    };
    const state = (selector) => {
      const root = document.querySelector(selector);
      if (!root) return { exists: false, visible: false, imgs: 0, videos: 0, text: "", srcs: [] };
      const rect = root.getBoundingClientRect();
      return {
        exists: true,
        visible: !hiddenByAncestor(root) && rect.width > 0 && rect.height > 0,
        imgs: root.querySelectorAll("img").length,
        videos: root.querySelectorAll("video").length,
        text: (root.innerText || root.textContent || "").replace(/\s+/g, " ").trim().slice(0, 260),
        srcs: Array.from(root.querySelectorAll("video[src], img[src], a[href]")).map((item) => item.getAttribute("src") || item.getAttribute("href") || "").filter(Boolean).slice(0, 12),
      };
    };
    const button = (selector) => {
      const root = document.querySelector(selector);
      const item = root?.matches?.("button") ? root : root?.querySelector?.("button");
      if (!item) return { exists: false, visible: false, disabled: false, text: "" };
      const rect = item.getBoundingClientRect();
      const style = window.getComputedStyle(item);
      return {
        exists: true,
        visible: style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0,
        disabled: !!item.disabled || item.getAttribute("aria-disabled") === "true",
        text: (item.innerText || item.textContent || "").replace(/\s+/g, " ").trim(),
      };
    };
    const visibleText = (element) => {
      if (!element || hiddenByAncestor(element)) return "";
      return (element.innerText || element.textContent || "").replace(/\s+/g, " ").trim();
    };
    const errors = Array.from(document.querySelectorAll(".toast-wrap, .toast, .toast-body, .error, .error-text, [role='alert'], [aria-live='assertive']"))
      .map(visibleText)
      .filter((text) => text && /error|traceback|exception|失败|错误|请先上传|requires|missing/i.test(text))
      .filter((text, index, list) => list.indexOf(text) === index)
      .slice(0, 8);
    return {
      reason: why,
      progress: state("#progress-bar"),
      preview: state("#preview_generating"),
      progressVideo: state("#progress_video"),
      finishedGallery: state("#finished_gallery"),
      finalGallery: state("#final_gallery"),
      generate: button("#generate_button"),
      stop: button("#stop_button"),
      skip: button("#skip_button"),
      errors,
      promptPreview: (() => {
        const root = document.querySelector("#scene_director_prompt_preview");
        const input = root?.querySelector?.("textarea, input");
        return (input ? input.value : (root?.innerText || "")).slice(0, 800);
      })(),
    };
  }, reason);
}

async function clickGenerate(page) {
  const result = await page.evaluate(() => {
    const root = document.querySelector("#generate_button");
    const button = root?.matches?.("button") ? root : root?.querySelector?.("button");
    if (!button) return { clicked: false, reason: "missing" };
    if (button.disabled || button.getAttribute("aria-disabled") === "true") {
      return { clicked: false, reason: "disabled", text: (button.innerText || button.textContent || "").trim() };
    }
    button.click();
    return { clicked: true, text: (button.innerText || button.textContent || "").trim() };
  });
  assertCondition(result.clicked, "generate button could not be clicked", result);
  return result;
}

async function waitForGeneration(page) {
  const samples = [];
  const start = Date.now();
  let sawActive = false;
  while (Date.now() - start < MAX_RUN_MS) {
    await page.waitForTimeout(1500);
    const elapsed = Date.now() - start;
    const snapshot = await readGenerationSnapshot(page, `running ${Math.round(elapsed / 1000)}s`);
    const active = snapshot.stop.exists && snapshot.stop.visible && !snapshot.stop.disabled;
    const hasMedia = mediaCount(snapshot) > 0;
    sawActive = sawActive || active;
    if (samples.length === 0 || hasMedia || elapsed % 15000 < 1800) samples.push(snapshot);
    if (snapshot.errors?.length && !active && snapshot.generate.exists && snapshot.generate.visible && !snapshot.generate.disabled) {
      return { ok: false, sawActive, samples, finalSnapshot: snapshot, error: snapshot.errors[0] };
    }
    if (hasMedia && sawActive && !active && snapshot.generate.exists && snapshot.generate.visible && !snapshot.generate.disabled) {
      await page.waitForTimeout(2000);
      const finalSnapshot = await readGenerationSnapshot(page, "generation complete");
      samples.push(finalSnapshot);
      return { ok: mediaCount(finalSnapshot) > 0, sawActive, samples, finalSnapshot };
    }
    if (hasMedia && !active && snapshot.generate.exists && snapshot.generate.visible && !snapshot.generate.disabled) {
      return { ok: true, sawActive, samples, finalSnapshot: snapshot };
    }
  }
  const finalSnapshot = await readGenerationSnapshot(page, "generation timeout");
  samples.push(finalSnapshot);
  return { ok: false, sawActive, timeout: true, samples, finalSnapshot };
}

async function runCase(page, key, caseDef) {
  const mediaState = await buildMediaState(caseDef);
  await clickPreset(page, caseDef.preset);
  const themeResult = await setSceneTheme(page, caseDef.theme || "");
  await openDirector(page);
  await setPrompt(page, caseDef.prompt);
  const configured = await configureDirector(page, caseDef, mediaState);
  const before = await readGenerationSnapshot(page, "before generate");
  if (!ALLOW_GENERATE) {
    return {
      key,
      id: caseDef.id,
      preset: caseDef.preset,
      status: "SKIPPED",
      reason: "set SIMPAI_DIRECTOR_GENERATION_ALLOW_GENERATE=1 to run real generation",
      themeResult,
      configured,
      before,
    };
  }
  await clickGenerate(page);
  const afterClick = await readGenerationSnapshot(page, "after generate click");
  const generation = await waitForGeneration(page);
  assertCondition(generation.ok, "director generation did not produce visible media", generation.finalSnapshot);
  return {
    key,
    id: caseDef.id,
    preset: caseDef.preset,
    status: "PASS",
    themeResult,
    configured,
    before,
    afterClick,
    generation,
  };
}

async function main() {
  await mkdir(REPORT_DIR, { recursive: true });
  const browser = await chromium.launch({ headless: true, executablePath: CHROME });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1200 } });
  page.setDefaultTimeout(90000);
  const events = [];
  installWatchers(page, events);
  const results = [];
  try {
    await page.goto(URL, { waitUntil: "domcontentloaded", timeout: 120000 });
    await waitForPresetIdle(page, 5000);
    for (const key of CASE_FILTER) {
      const caseDef = CASES[key];
      if (!caseDef) {
        results.push({ key, status: "FAIL", error: `unknown case: ${key}` });
        continue;
      }
      try {
        results.push(await runCase(page, key, caseDef));
      } catch (error) {
        results.push({
          key,
          id: caseDef.id,
          preset: caseDef.preset,
          status: "FAIL",
          error: compactText(error?.message || error),
          details: error?.details || {},
          snapshot: await readGenerationSnapshot(page, "failure snapshot").catch(() => null),
        });
      }
    }
  } finally {
    await browser.close();
  }
  const failed = results.filter((item) => item.status === "FAIL");
  const report = {
    url: URL,
    chrome: CHROME,
    generated_at: new Date().toISOString(),
    allow_generate: ALLOW_GENERATE,
    cases: CASE_FILTER,
    summary: {
      total: results.length,
      pass: results.filter((item) => item.status === "PASS").length,
      skipped: results.filter((item) => item.status === "SKIPPED").length,
      fail: failed.length,
    },
    results,
    events,
  };
  const output = path.join(REPORT_DIR, `canary-${Date.now()}.json`);
  await writeFile(output, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify({
    output,
    summary: report.summary,
    statuses: results.map((item) => ({ key: item.key, id: item.id, preset: item.preset, status: item.status, error: item.error || "" })),
    runtimeEventCount: events.length,
  }, null, 2));
  if (failed.length) process.exit(1);
}

main().catch((error) => {
  console.error(error?.stack || error);
  process.exit(1);
});
