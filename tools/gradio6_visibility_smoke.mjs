#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";

const DEFAULT_BASE_URL = "http://127.0.0.1:8190/?__theme=dark";

const SELECTORS = Object.freeze({
  finishedCatalog: "#finished_images_catalog",
  previewGenerating: "#preview_generating",
  finishedGallery: "#finished_gallery",
  videoPlayer: "#video_player",
  finalGallery: "#final_gallery",
  imageToolbox: "#image_toolbox",
  paramsNoteRegenButton: "#params_note_regen_button",
  paramsNoteBox: ".toolbox_note",
  galleryBrowserStatus: "#gallery_browser_status",
  galleryImagesButton: "#gallery_images_btn",
  galleryVideosButton: "#gallery_videos_btn",
  scenePanel: "#scene_panel",
  sceneAdditionalPrompt: "#scene_additional_prompt",
  sceneVideoDuration: "#scene_video_duration",
  sceneVarNumber: "#scene_var_number",
  sceneVarNumber2: "#scene_var_number2",
  sceneAdvancedParameters: "#scene_advanced_parameters_accordion",
  sam3VideoMaskAccordion: "#sam3_video_mask_accordion",
  sam3FramesBackdrop: "#sam3_frames_modal_backdrop",
  inputImageCheckbox: "#input_image_checkbox",
  qwenTtsCheckbox: "#qwen_tts_checkbox",
  advancedCheckbox: "#advanced_checkbox",
  imageInputPanel: "#image_input_panel",
  ttsPanel: "#tts_panel",
  advancedColumn: "#advanced_column",
  engineClass: "#engine_class",
  engineClassContainer: "#engine_class > .html-container",
  inpaintMode: "#inpaint_mode",
  inpaintAdditionalPrompt: "#inpaint_additional_prompt",
  outpaintSelections: "#outpaint_selections",
  exampleInpaintPrompts: "#example_inpaint_prompts",
  enhanceMaskModel1: "#enhance_mask_model_1",
  enhanceMaskClothCategory1: "#enhance_mask_cloth_category_1",
  enhanceMaskDinoPrompt1: "#enhance_mask_dino_prompt_text_1",
  enhanceMaskSamOptions1: "#enhance_mask_sam_options_1",
  exampleEnhanceMaskDinoPrompt1: "#example_enhance_mask_dino_prompt_text_1",
  statusMonitor: "#gradio-status-monitor",
  modelsPanel: "#models_js_panel",
  baseModelDropdown: '.simpai-models-js-panel [data-simpai-model-field="base_model"]',
  baseModelBrowserButton: '.simpai-models-js-panel [data-simpai-model-browser="base"]',
  modelPreviewTooltip: ".model-preview-tooltip",
  modelBrowserDialog: ".sai-model-browser-v2",
  barStoreButton: "#bar_store",
  presetStore: ".preset_store",
  presetStoreTools: "#preset_store_tools",
  presetStoreDraft: "#preset_store_nav_draft",
  presetStoreCandidatePool: "#preset_store_candidate_pool",
  presetStoreApply: "#preset_store_apply_draft",
  presetStoreClose: "#preset_store_close",
  identityDialog: "#identity_dialog",
});

const env = process.env;
const config = Object.freeze({
  baseUrl: env.SIMPAI_BASE_URL || DEFAULT_BASE_URL,
  basePresetSelector: env.SIMPAI_PRESET_BASE_SELECTOR || "#bar0",
  scenePresetSelector: env.SIMPAI_PRESET_SCENE_SELECTOR || "#bar2",
  scenePresetVarNumber: env.SIMPAI_PRESET_SCENE_VAR_NUMBER || "0",
  altPresetSelector: env.SIMPAI_PRESET_ALT_SELECTOR || "#bar1",
  ttpPresetSelector: env.SIMPAI_PRESET_TTP_SELECTOR || "",
  ttpPresetVarNumber: env.SIMPAI_PRESET_TTP_VAR_NUMBER || "8",
  ttpPresetVarNumberMax: env.SIMPAI_PRESET_TTP_VAR_NUMBER_MAX || "16",
  ttpPresetVarNumber2: env.SIMPAI_PRESET_TTP_VAR_NUMBER2 || "3072",
  paramPresetSelector: env.SIMPAI_PRESET_PARAM_SELECTOR || "#bar4",
  paramPresetGuidance: env.SIMPAI_PRESET_PARAM_GUIDANCE || "1",
  paramPresetOverwriteStep: env.SIMPAI_PRESET_PARAM_OVERWRITE_STEP || "8",
  panelPresetSelector: env.SIMPAI_PRESET_PANEL_SELECTOR || env.SIMPAI_PRESET_ALT_SELECTOR || "#bar1",
  enhancePresetSelector:
    env.SIMPAI_PRESET_ENHANCE_SELECTOR ||
    env.SIMPAI_PRESET_BASE_SELECTOR ||
    env.SIMPAI_PRESET_PANEL_SELECTOR ||
    env.SIMPAI_PRESET_ALT_SELECTOR ||
    "#bar0",
  headless: !/^(0|false|no)$/i.test(env.SIMPAI_HEADLESS || "1"),
  screenshotDir: env.SIMPAI_SMOKE_SCREENSHOT_DIR || "",
  slowMo: parseIntValue(env.SIMPAI_SLOWMO, 0),
  timeoutMs: parseIntValue(env.SIMPAI_TIMEOUT_MS, 30000),
  playwrightChannel: env.SIMPAI_PLAYWRIGHT_CHANNEL || "",
});

const results = [];

class SmokeSkip extends Error {
  constructor(message) {
    super(message);
    this.name = "SmokeSkip";
  }
}

function parseIntValue(value, fallback) {
  const parsed = Number.parseInt(value || "", 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function assertCondition(condition, message) {
  if (!condition) throw new Error(message);
}

function compactMeasure(measurement) {
  if (!measurement || !measurement.exists) return "absent";
  return [
    `visible=${measurement.visible}`,
    `display=${measurement.display}`,
    `hidden=${measurement.hidden}`,
    `w=${Math.round(measurement.width)}`,
    `h=${Math.round(measurement.height)}`,
    `media=${measurement.mediaCount}`,
    `text=${JSON.stringify(measurement.text)}`,
  ].join(" ");
}

function record(status, name, detail = "") {
  const row = { status, name, detail };
  results.push(row);
  const suffix = detail ? ` - ${detail}` : "";
  console.log(`[${status}] ${name}${suffix}`);
}

async function loadPlaywright() {
  try {
    return await import("playwright");
  } catch (error) {
    console.error("Playwright is required for this opt-in smoke test.");
    console.error("Install locally with: npm install --no-save playwright");
    console.error("If Chromium is missing, run: npx playwright install chromium");
    console.error(`Import error: ${error.message}`);
    process.exit(2);
  }
}

async function saveFailureScreenshot(page, stepName) {
  if (!config.screenshotDir || !page) return "";
  const safeName = stepName.toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^-|-$/g, "") || "failure";
  await fs.mkdir(config.screenshotDir, { recursive: true });
  const filePath = path.join(config.screenshotDir, `${Date.now()}-${safeName}.png`);
  await page.screenshot({ path: filePath, fullPage: true });
  return filePath;
}

async function runStep(page, name, fn) {
  try {
    const detail = await fn();
    record("pass", name, detail || "");
  } catch (error) {
    if (error instanceof SmokeSkip) {
      record("skip", name, error.message);
      return;
    }
    const screenshot = await saveFailureScreenshot(page, name).catch(() => "");
    record("fail", name, screenshot ? `${error.message}; screenshot=${screenshot}` : error.message);
    throw error;
  }
}

async function waitForUiSettle(page, delayMs = 900) {
  await page.waitForLoadState("domcontentloaded", { timeout: config.timeoutMs }).catch(() => {});
  await page.waitForTimeout(delayMs);
}

async function waitForPresetGallerySuppressionClear(page, timeoutMs = 7000) {
  const started = Date.now();
  let last = null;
  do {
    last = await page.evaluate(() => {
      const htmlClassName = document.documentElement.className || "";
      const suppressed = typeof window.isSimpleAIPresetGallerySuppressed === "function"
        ? window.isSimpleAIPresetGallerySuppressed()
        : htmlClassName.includes("simpai-preset-switch-gallery-suppressed");
      const presetActive = htmlClassName.includes("simpai-preset-nav-active");
      return { suppressed, presetActive, htmlClassName };
    });
    if (!last.suppressed && !last.presetActive) return last;
    await page.waitForTimeout(250);
  } while (Date.now() - started < timeoutMs);
  throw new Error(`preset gallery suppression did not clear; ${JSON.stringify(last)}`);
}

async function gotoWebUi(page) {
  await page.goto(config.baseUrl, { waitUntil: "domcontentloaded", timeout: config.timeoutMs });
  await page.locator(config.basePresetSelector).first().waitFor({ state: "attached", timeout: config.timeoutMs });
  await page.locator(SELECTORS.inputImageCheckbox).first().waitFor({ state: "attached", timeout: config.timeoutMs });
  await waitForUiSettle(page, 1600);
}

async function measure(page, selector) {
  return await page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) {
      return {
        selector: sel,
        exists: false,
        visible: false,
        width: 0,
        height: 0,
        mediaCount: 0,
        text: "",
      };
    }

    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle ? window.getComputedStyle(el) : null;
    let hiddenByAncestor = false;
    let node = el;
    while (node && node.nodeType === 1) {
      const nodeStyle = window.getComputedStyle ? window.getComputedStyle(node) : null;
      if (
        node.hidden ||
        node.hasAttribute("hidden") ||
        (nodeStyle && (nodeStyle.display === "none" || nodeStyle.visibility === "hidden"))
      ) {
        hiddenByAncestor = true;
        break;
      }
      node = node.parentElement;
    }

    return {
      selector: sel,
      exists: true,
      visible: !hiddenByAncestor && rect.width > 0 && rect.height > 0,
      hidden: !!el.hidden || el.hasAttribute("hidden"),
      display: style ? style.display : "",
      visibility: style ? style.visibility : "",
      width: rect.width,
      height: rect.height,
      top: rect.top,
      left: rect.left,
      mediaCount: el.querySelectorAll("img, video, canvas, .gallery-item").length,
      buttonCount: el.querySelectorAll("button, summary, [role='button']").length,
      open: !!el.open || el.hasAttribute("open"),
      className: typeof el.className === "string" ? el.className : "",
      text: (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 160),
      htmlClassName: document.documentElement.className || "",
    };
  }, selector);
}

async function measureMany(page, selectors) {
  return await page.evaluate((selectorList) => {
    const measureOne = (sel) => {
      const el = document.querySelector(sel);
      if (!el) {
        return {
          selector: sel,
          exists: false,
          visible: false,
          width: 0,
          height: 0,
          mediaCount: 0,
          text: "",
          htmlClassName: document.documentElement.className || "",
        };
      }

      const rect = el.getBoundingClientRect();
      const style = window.getComputedStyle ? window.getComputedStyle(el) : null;
      let hiddenByAncestor = false;
      let node = el;
      while (node && node.nodeType === 1) {
        const nodeStyle = window.getComputedStyle ? window.getComputedStyle(node) : null;
        if (
          node.hidden ||
          node.hasAttribute("hidden") ||
          (nodeStyle && (nodeStyle.display === "none" || nodeStyle.visibility === "hidden"))
        ) {
          hiddenByAncestor = true;
          break;
        }
        node = node.parentElement;
      }

      return {
        selector: sel,
        exists: true,
        visible: !hiddenByAncestor && rect.width > 0 && rect.height > 0,
        hidden: !!el.hidden || el.hasAttribute("hidden"),
        display: style ? style.display : "",
        visibility: style ? style.visibility : "",
        width: rect.width,
        height: rect.height,
        top: rect.top,
        left: rect.left,
        mediaCount: el.querySelectorAll("img, video, canvas, .gallery-item").length,
        buttonCount: el.querySelectorAll("button, summary, [role='button']").length,
        open: !!el.open || el.hasAttribute("open"),
        className: typeof el.className === "string" ? el.className : "",
        text: (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 160),
        htmlClassName: document.documentElement.className || "",
      };
    };
    return Object.fromEntries(selectorList.map((sel) => [sel, measureOne(sel)]));
  }, selectors);
}

async function measureFinishedCatalogState(page) {
  return await page.evaluate((selector) => {
    const root = document.querySelector(selector);
    if (!root) {
      return {
        exists: false,
        visible: false,
        labelOpen: false,
        bodyVisible: false,
        rootHeight: 0,
        maxBodyHeight: 0,
        bodyCount: 0,
        htmlClassName: document.documentElement.className || "",
      };
    }
    const rootRect = root.getBoundingClientRect();
    const rootStyle = window.getComputedStyle ? window.getComputedStyle(root) : null;
    const label = root.querySelector(":scope > button.label-wrap") || root.querySelector("button.label-wrap");
    const labelRect = label ? label.getBoundingClientRect() : null;
    const labelOpen = !!label && (
      label.classList.contains("open") ||
      label.getAttribute("aria-expanded") === "true" ||
      label.hasAttribute("open")
    );
    const bodies = Array.from(root.children || []).filter((child) => {
      try {
        return !(child.matches && child.matches("button.label-wrap"));
      } catch (error) {
        return true;
      }
    });
    const bodyStates = bodies.map((body) => {
      const rect = body.getBoundingClientRect();
      const style = window.getComputedStyle ? window.getComputedStyle(body) : null;
      const hidden = !!body.hidden || body.hasAttribute("hidden") || body.getAttribute("aria-hidden") === "true";
      const displayNone = !!style && (style.display === "none" || style.visibility === "hidden");
      return {
        height: rect.height,
        width: rect.width,
        display: style ? style.display : "",
        hidden,
        visible: !hidden && !displayNone && rect.width > 0 && rect.height > 2,
      };
    });
    const maxBodyHeight = bodyStates.reduce((max, state) => Math.max(max, state.height || 0), 0);
    const bodyVisible = bodyStates.some((state) => state.visible);
    return {
      exists: true,
      visible: !!rootStyle && rootStyle.display !== "none" && rootStyle.visibility !== "hidden" && rootRect.width > 0 && rootRect.height > 0,
      labelOpen,
      labelExpanded: label ? label.getAttribute("aria-expanded") : "",
      labelHeight: labelRect ? labelRect.height : 0,
      bodyVisible,
      bodyCount: bodies.length,
      maxBodyHeight,
      rootHeight: rootRect.height,
      className: typeof root.className === "string" ? root.className : "",
      collapsedDataset: root.dataset?.simpleaiPresetSwitchCatalogCollapsed || "",
      suppressed: document.documentElement.classList.contains("simpai-preset-switch-gallery-suppressed"),
      htmlClassName: document.documentElement.className || "",
      text: (root.innerText || root.textContent || "").replace(/\s+/g, " ").trim().slice(0, 160),
    };
  }, SELECTORS.finishedCatalog);
}

function compactCatalogState(state) {
  if (!state || !state.exists) return "absent";
  return [
    `visible=${state.visible}`,
    `open=${state.labelOpen}`,
    `suppressed=${state.suppressed}`,
    `collapsed=${state.collapsedDataset}`,
    `rootH=${Math.round(state.rootHeight)}`,
    `bodyH=${Math.round(state.maxBodyHeight)}`,
    `bodyVisible=${state.bodyVisible}`,
  ].join(" ");
}

async function measureGalleryWelcomeSurface(page) {
  return await page.evaluate((selectors) => {
    const isVisible = (el) => {
      if (!el) return false;
      let node = el;
      while (node && node.nodeType === 1) {
        const style = window.getComputedStyle ? window.getComputedStyle(node) : null;
        if (
          node.hidden ||
          node.hasAttribute("hidden") ||
          (style && (style.display === "none" || style.visibility === "hidden" || Number.parseFloat(style.opacity || "1") <= 0.03))
        ) {
          return false;
        }
        node = node.parentElement;
      }
      const rect = el.getBoundingClientRect();
      return rect.width > 2 && rect.height > 2;
    };
    const rect = (el) => {
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return {
        left: Math.round(r.left),
        top: Math.round(r.top),
        width: Math.round(r.width),
        height: Math.round(r.height),
      };
    };
    const loadedImage = (root) => {
      const img = root ? root.querySelector("img") : null;
      return !!img && (img.naturalWidth || 0) > 0 && (img.naturalHeight || 0) > 0;
    };
    const preview = document.querySelector(selectors.previewGenerating);
    const placeholder = document.querySelector("#simpleai_gallery_welcome_guard_placeholder");
    const gallery = document.querySelector(selectors.finishedGallery);
    const video = document.querySelector(selectors.videoPlayer);
    return {
      previewVisible: isVisible(preview),
      previewLoaded: loadedImage(preview),
      previewRect: rect(preview),
      placeholderVisible: isVisible(placeholder),
      placeholderLoaded: loadedImage(placeholder),
      placeholderRect: rect(placeholder),
      galleryVisible: isVisible(gallery),
      galleryRect: rect(gallery),
      videoVisible: isVisible(video),
      videoRect: rect(video),
      overlayActive: document.documentElement.classList.contains("simpai-gallery-browser-overlay-active"),
      pending: document.documentElement.classList.contains("simpai-gallery-browser-welcome-pending"),
    };
  }, SELECTORS);
}

async function galleryBrowserStatusState(page) {
  return await page.evaluate((selectors) => {
    const text = (selector) => {
      const root = document.querySelector(selector);
      if (!root) return "";
      const target = root.querySelector ? (root.querySelector(".prose, .md, p") || root) : root;
      return (target.innerText || target.textContent || "").replace(/\s+/g, " ").trim();
    };
    const buttonState = (selector) => {
      const root = document.querySelector(selector);
      const button = root && root.matches && root.matches("button") ? root : root?.querySelector?.("button");
      return {
        exists: !!button,
        pressed: button ? button.getAttribute("aria-pressed") || "" : "",
        className: button ? String(button.className || "") : "",
        text: button ? (button.innerText || button.textContent || "").replace(/\s+/g, " ").trim() : "",
      };
    };
    return {
      status: text(selectors.galleryBrowserStatus),
      images: buttonState(selectors.galleryImagesButton),
      videos: buttonState(selectors.galleryVideosButton),
    };
  }, SELECTORS);
}

async function waitForGalleryStatusText(page, pattern, reason, options = {}) {
  const timeoutMs = options.timeoutMs ?? 8000;
  const intervalMs = options.intervalMs ?? 180;
  const started = Date.now();
  let last = null;
  do {
    last = await galleryBrowserStatusState(page);
    if (pattern.test(last.status || "")) return last;
    await page.waitForTimeout(intervalMs);
  } while (Date.now() - started < timeoutMs);
  throw new Error(`${SELECTORS.galleryBrowserStatus} did not show ${reason}; last=${JSON.stringify(last)}`);
}

async function clickGalleryMediaButton(page, selector, label) {
  const clicked = await page.evaluate((sel) => {
    const root = document.querySelector(sel);
    const button = root && root.matches && root.matches("button") ? root : root?.querySelector?.("button");
    if (!button || typeof button.click !== "function") return false;
    button.click();
    return true;
  }, selector);
  assertCondition(clicked, `${selector} ${label} button missing`);
}

async function presetStoreState(page) {
  return await page.evaluate((selectors) => {
    const normalize = (value) => {
      let text = String(value || "").trim();
      if (text.endsWith("\u2B07")) text = text.slice(0, -1).trim();
      return text;
    };
    const uniqueNames = (names) => {
      const seen = new Set();
      const result = [];
      names.forEach((name) => {
        const clean = normalize(name);
        if (!clean || seen.has(clean)) return;
        seen.add(clean);
        result.push(clean);
      });
      return result;
    };
    const navButtonOriginalText = (button) => {
      if (!button) return "";
      const own = button.getAttribute?.("data-original-text");
      if (own) return own;
      const original = button.querySelector?.("[data-original-text]")?.getAttribute?.("data-original-text");
      if (original) return original;
      return button.textContent || "";
    };
    const isVisible = (el) => {
      if (!el) return false;
      let node = el;
      while (node && node.nodeType === 1) {
        const style = window.getComputedStyle ? window.getComputedStyle(node) : null;
        if (
          node.hidden ||
          node.hasAttribute("hidden") ||
          (style && (style.display === "none" || style.visibility === "hidden"))
        ) {
          return false;
        }
        node = node.parentElement;
      }
      const rect = el.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    };
    const store =
      (typeof getPresetStoreElement === "function" ? getPresetStoreElement() : null) ||
      document.querySelector(selectors.presetStore);
    const tools = document.querySelector(selectors.presetStoreTools);
    const draft = document.querySelector(selectors.presetStoreDraft);
    const candidatePool = document.querySelector(selectors.presetStoreCandidatePool);
    const identity = document.querySelector(selectors.identityDialog);
    const draftChips = Array.from(draft?.querySelectorAll?.(".preset-store-draft-chip:not(.preset-store-draft-placeholder)") || []);
    const draftNamesRaw = draftChips.map((chip) => normalize(
      chip.dataset?.presetName ||
      chip.querySelector?.(".preset-store-draft-name")?.getAttribute?.("data-original-text") ||
      chip.querySelector?.(".preset-store-draft-name")?.textContent ||
      chip.textContent ||
      ""
    )).filter(Boolean);
    const navButtons = typeof getTopbarBarButtons === "function"
      ? getTopbarBarButtons()
      : Array.from(document.querySelectorAll("[id^='bar']")).filter((el) => /^bar\d+$/.test(String(el.id || "")));
    const navNamesRaw = navButtons.map(navButtonOriginalText).map(normalize).filter(Boolean);
    const draftNames = uniqueNames(draftNamesRaw);
    const navNames = navNamesRaw.slice(0, draftNames.length);
    const duplicateDraftNames = draftNamesRaw.filter((name, index) => draftNamesRaw.indexOf(name) !== index);
    const duplicateNavNames = navNames.filter((name, index) => navNames.indexOf(name) !== index);
    return {
      storeExists: !!store,
      storeVisible: isVisible(store),
      toolsExists: !!tools,
      toolsVisible: isVisible(tools),
      draftCount: draftChips.length,
      candidateCount: candidatePool ? candidatePool.querySelectorAll("button, [role='button'], .preset-store-candidate").length : 0,
      draftNames,
      navNames,
      duplicateDraftNames,
      duplicateNavNames,
      presetStoreSeq: Number(window.simpleaiTopbarSystemParams?.__preset_store_seq || 0),
      identityVisible: isVisible(identity),
      text: store ? (store.innerText || store.textContent || "").replace(/\s+/g, " ").trim().slice(0, 160) : "",
    };
  }, SELECTORS);
}

async function waitForPresetStoreOpen(page) {
  const started = Date.now();
  let last = null;
  do {
    last = await presetStoreState(page);
    if (last.storeVisible && last.toolsVisible && (last.draftCount > 0 || last.candidateCount > 0)) return last;
    await page.waitForTimeout(250);
  } while (Date.now() - started < 9000);
  if (last && last.identityVisible && !last.storeVisible) {
    throw new SmokeSkip(`preset store unavailable; identity dialog opened instead; ${JSON.stringify(last)}`);
  }
  throw new Error(`preset store did not open; last=${JSON.stringify(last)}`);
}

async function waitForPresetStoreClosed(page) {
  const started = Date.now();
  let last = null;
  do {
    last = await presetStoreState(page);
    if (last.storeExists && !last.storeVisible && !last.identityVisible) return last;
    await page.waitForTimeout(200);
  } while (Date.now() - started < 5000);
  throw new Error(`preset store did not close cleanly; last=${JSON.stringify(last)}`);
}

async function waitForPresetStoreApply(page, beforeSeq, expectedDraftNames) {
  const expected = Array.isArray(expectedDraftNames) ? expectedDraftNames.filter(Boolean) : [];
  const started = Date.now();
  let last = null;
  do {
    last = await presetStoreState(page);
    const seqAdvanced = Number(last.presetStoreSeq || 0) > Number(beforeSeq || 0);
    const navMatchesDraft = expected.length > 0
      && last.navNames.length >= expected.length
      && expected.every((name, index) => last.navNames[index] === name);
    if (seqAdvanced && navMatchesDraft && last.duplicateNavNames.length === 0) return last;
    await page.waitForTimeout(220);
  } while (Date.now() - started < 9000);
  throw new Error(`preset store apply did not update navbar; beforeSeq=${beforeSeq}; expected=${JSON.stringify(expected)}; last=${JSON.stringify(last)}`);
}

async function assertFinishedCatalogCollapsed(page, reason) {
  const state = await measureFinishedCatalogState(page);
  assertCondition(state.exists, `${SELECTORS.finishedCatalog} missing during ${reason}`);
  assertCondition(!state.labelOpen, `${SELECTORS.finishedCatalog} label is open during ${reason}; ${compactCatalogState(state)}`);
  assertCondition(
    !state.bodyVisible && state.maxBodyHeight <= 4,
    `${SELECTORS.finishedCatalog} body leaked during ${reason}; ${compactCatalogState(state)}`
  );
  if (state.visible) {
    assertCondition(
      state.rootHeight <= Math.max(72, state.labelHeight + 12),
      `${SELECTORS.finishedCatalog} reserves expanded height during ${reason}; ${compactCatalogState(state)}`
    );
  }
  return state;
}

function assertCatalogSamplesCollapsed(samples, reason) {
  let suppressionSeen = false;
  let firstLeak = null;
  for (const [index, sample] of samples.entries()) {
    const state = sample.catalog;
    if (!state || !state.exists) continue;
    suppressionSeen = suppressionSeen || !!state.suppressed || String(state.htmlClassName || "").includes("simpai-preset-switch-gallery-suppressed");
    if (!firstLeak && index > 1 && state.bodyVisible && state.maxBodyHeight > 4) {
      firstLeak = state;
    }
    if (!firstLeak && index > 1 && state.labelOpen && state.maxBodyHeight > 4) {
      firstLeak = state;
    }
  }
  assertCondition(!firstLeak, `${reason} reopened finished catalog during preset switch; ${compactCatalogState(firstLeak)}`);
  assertCondition(suppressionSeen, `${reason} did not observe finished catalog suppression`);
  return `samples=${samples.length}`;
}

async function mountedSelfState(page, selector) {
  return await page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) return { selector: sel, exists: false, selfHidden: true, className: "", display: "", text: "" };
    const style = window.getComputedStyle ? window.getComputedStyle(el) : null;
    const classList = el.classList ? Array.from(el.classList) : [];
    const selfHidden =
      !!el.hidden ||
      el.hasAttribute("hidden") ||
      el.dataset.simpleaiSceneHidden === "1" ||
      el.dataset.simpleaiAuxHidden === "1" ||
      classList.includes("simpai-mounted-hidden") ||
      classList.includes("simpai-force-hidden") ||
      classList.includes("hidden") ||
      classList.includes("hide") ||
      (style && style.display === "none");
    const rect = el.getBoundingClientRect();
    return {
      selector: sel,
      exists: true,
      selfHidden,
      className: typeof el.className === "string" ? el.className : "",
      display: style ? style.display : "",
      width: rect.width,
      height: rect.height,
      text: (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 160),
    };
  }, selector);
}

async function assertMountedSelfShown(page, selector) {
  const state = await mountedSelfState(page, selector);
  assertCondition(state.exists, `${selector} does not exist`);
  assertCondition(!state.selfHidden, `${selector} should be mounted-shown; ${JSON.stringify(state)}`);
  return state;
}

async function assertMountedSelfHidden(page, selector) {
  const state = await mountedSelfState(page, selector);
  assertCondition(state.exists, `${selector} does not exist`);
  assertCondition(state.selfHidden, `${selector} should be mounted-hidden; ${JSON.stringify(state)}`);
  return state;
}

async function measureScroll(page) {
  return await page.evaluate(() => {
    const root = document.scrollingElement || document.documentElement;
    const y = Math.round(window.scrollY || root.scrollTop || 0);
    const maxY = Math.round(Math.max(0, root.scrollHeight - window.innerHeight));
    return {
      y,
      maxY,
      height: Math.round(root.scrollHeight),
      viewport: Math.round(window.innerHeight),
      scrollRestoration: window.history ? window.history.scrollRestoration || "" : "",
      guardInstalled: !!window.__simpaiViewerScrollGuardInstalled,
    };
  });
}

async function assertScrollNearTop(page, reason, maxY = 8) {
  const scroll = await measureScroll(page);
  assertCondition(
    scroll.y <= maxY,
    `${reason} should stay near page top; y=${scroll.y} maxY=${scroll.maxY} restoration=${scroll.scrollRestoration} guard=${scroll.guardInstalled}`
  );
  return scroll;
}

async function assertVisible(page, selector, options = {}) {
  const minHeight = options.minHeight ?? 4;
  const minWidth = options.minWidth ?? 4;
  const measurement = await measure(page, selector);
  assertCondition(measurement.exists, `${selector} does not exist`);
  assertCondition(
    measurement.visible && measurement.height >= minHeight && measurement.width >= minWidth,
    `${selector} should be visible; ${compactMeasure(measurement)}`
  );
  return measurement;
}

async function waitForMeasuredVisible(page, selector, options = {}) {
  const timeoutMs = options.timeoutMs ?? config.timeoutMs;
  const intervalMs = options.intervalMs ?? 250;
  const minHeight = options.minHeight ?? 4;
  const minWidth = options.minWidth ?? 4;
  const started = Date.now();
  let last = null;
  do {
    last = await measure(page, selector);
    if (last.exists && last.visible && last.height >= minHeight && last.width >= minWidth) {
      return last;
    }
    await page.waitForTimeout(intervalMs);
  } while (Date.now() - started < timeoutMs);
  throw new Error(`${selector} did not become visible; ${compactMeasure(last)}`);
}

async function waitForMeasuredHiddenOrZero(page, selector, options = {}) {
  const timeoutMs = options.timeoutMs ?? config.timeoutMs;
  const intervalMs = options.intervalMs ?? 250;
  const maxHeight = options.maxHeight ?? 2;
  const started = Date.now();
  let last = null;
  do {
    last = await measure(page, selector);
    if (!last.exists || (!last.visible && last.height <= maxHeight)) {
      return last;
    }
    await page.waitForTimeout(intervalMs);
  } while (Date.now() - started < timeoutMs);
  throw new Error(`${selector} did not become hidden without layout gap; ${compactMeasure(last)}`);
}

async function assertHiddenOrZero(page, selector, options = {}) {
  const maxHeight = options.maxHeight ?? 2;
  const measurement = await measure(page, selector);
  if (!measurement.exists) return measurement;
  assertCondition(
    !measurement.visible && measurement.height <= maxHeight,
    `${selector} should be hidden without layout gap; ${compactMeasure(measurement)}`
  );
  return measurement;
}

async function assertNoExpandedGallery(page, reason) {
  for (const selector of [SELECTORS.finishedGallery, SELECTORS.finalGallery]) {
    const measurement = await measure(page, selector);
    if (!measurement.exists) continue;
    const looksExpanded = measurement.visible && measurement.height > 80 && measurement.mediaCount > 0;
    assertCondition(!looksExpanded, `${selector} is expanded during ${reason}; ${compactMeasure(measurement)}`);
  }
  return "no expanded result galleries";
}

async function switchPreset(page, selector, name) {
  await page.locator(selector).first().waitFor({ state: "attached", timeout: config.timeoutMs });
  await page.locator(selector).first().click({ timeout: config.timeoutMs });
  await waitForUiSettle(page, 1800);
  return name;
}

async function clickPresetAndSample(page, selector, options = {}) {
  const durationMs = options.durationMs ?? 2600;
  const intervalMs = options.intervalMs ?? 50;
  await page.locator(selector).first().waitFor({ state: "attached", timeout: config.timeoutMs });
  await page.locator(selector).first().click({ force: !!options.force, timeout: config.timeoutMs });
  const started = Date.now();
  const samples = [];
  do {
    samples.push(await measureMany(page, [
      SELECTORS.scenePanel,
      SELECTORS.sam3VideoMaskAccordion,
      SELECTORS.sceneAdditionalPrompt,
      SELECTORS.sam3FramesBackdrop,
    ]));
    await page.waitForTimeout(intervalMs);
  } while (Date.now() - started < durationMs);
  return samples;
}

async function clickPresetAndSampleCatalog(page, selector, options = {}) {
  const durationMs = options.durationMs ?? 3200;
  const intervalMs = options.intervalMs ?? 60;
  await page.locator(selector).first().waitFor({ state: "attached", timeout: config.timeoutMs });
  await page.locator(selector).first().click({ timeout: config.timeoutMs });
  const started = Date.now();
  const samples = [];
  do {
    samples.push({
      catalog: await measureFinishedCatalogState(page),
      finishedGallery: await measure(page, SELECTORS.finishedGallery),
      finalGallery: await measure(page, SELECTORS.finalGallery),
      sam3Backdrop: await measure(page, SELECTORS.sam3FramesBackdrop),
    });
    await page.waitForTimeout(intervalMs);
  } while (Date.now() - started < durationMs);
  return samples;
}

async function activateImageInputTab(page, tabName) {
  const tabConfig = {
    uov: { targetId: "uov_tab", overflowIndex: 0, labels: ["Upscale or Variation", "放大与变化"] },
    inpaint: { targetId: "inpaint_tab", overflowIndex: 1, labels: ["Inpaint or Outpaint", "内外重绘"] },
    enhance: { targetId: "enhance_tab", overflowIndex: 2, labels: ["Enhance+", "Enhance", "增强修图"] },
  }[tabName];
  assertCondition(tabConfig !== undefined, `unknown image input tab ${tabName}`);
  const result = await page.evaluate(async ({ targetId, labels, overflowIndex }) => {
    const root = document.getElementById("image_input_tabs");
    if (!root) return { ok: false, reason: "missing image_input_tabs" };

    const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim();
    const matchesLabel = (button) => labels.some((label) => normalize(button.textContent).startsWith(label));
    const usable = (button) => {
      if (!button) return false;
      const rect = button.getBoundingClientRect();
      const style = window.getComputedStyle ? window.getComputedStyle(button) : null;
      return rect.width > 0 && rect.height > 8 && (!style || (style.display !== "none" && style.visibility !== "hidden"));
    };
    const byId = targetId
      ? root.querySelector(`[data-tab-id="${targetId}"], [aria-controls="${targetId}"], #${targetId}-button`)
      : null;
    const textCandidates = Array.from(root.querySelectorAll('[role="tab"], button')).filter(matchesLabel);
    const byText =
      textCandidates.find((button) => button.getAttribute("role") === "tab" && usable(button)) ||
      textCandidates.find(usable) ||
      null;
    const direct = byId || byText;
    if (direct && typeof direct.click === "function") {
      direct.click();
      await new Promise((resolve) => setTimeout(resolve, 900));
      return { ok: true, via: "direct", text: normalize(direct.textContent) };
    }

    const menu = root.querySelector(".overflow-menu > button");
    if (!menu || typeof menu.click !== "function") {
      return { ok: false, reason: "missing overflow menu" };
    }
    menu.click();
    await new Promise((resolve) => setTimeout(resolve, 120));
    const buttons = Array.from(root.querySelectorAll(".overflow-dropdown button"));
    const button = buttons.find(matchesLabel) || buttons[overflowIndex];
    if (!button || typeof button.click !== "function") {
      return {
        ok: false,
        reason: `missing overflow item ${overflowIndex}`,
        count: buttons.length,
        overflowTexts: buttons.map((item) => normalize(item.textContent)).filter(Boolean),
      };
    }
    button.click();
    await new Promise((resolve) => setTimeout(resolve, 1100));
    return { ok: true, via: "overflow", count: buttons.length, text: normalize(button.textContent) };
  }, tabConfig);
  assertCondition(result.ok, `could not activate image input tab ${tabName}: ${JSON.stringify(result)}`);
  return result;
}

async function activateEnhanceRegionOne(page) {
  const result = await page.evaluate(async () => {
    const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim();
    const usable = (button) => {
      if (!button) return false;
      const rect = button.getBoundingClientRect();
      const style = window.getComputedStyle ? window.getComputedStyle(button) : null;
      return rect.width > 0 && rect.height > 8 && (!style || (style.display !== "none" && style.visibility !== "hidden"));
    };
    const tabs = Array.from(document.querySelectorAll('[role="tab"], button'));
    const candidates = tabs.filter((button) => ["Region#1", "区域#1"].includes(normalize(button.textContent)));
    const region =
      candidates.find((button) => button.getAttribute("role") === "tab" && usable(button)) ||
      candidates.find((button) => button.getAttribute("role") === "tab") ||
      candidates.find(usable) ||
      candidates[0];
    if (!region || typeof region.click !== "function") return { ok: false, reason: "missing Region#1/区域#1 tab" };
    region.click();
    await new Promise((resolve) => setTimeout(resolve, 900));
    return { ok: true, text: normalize(region.textContent) };
  });
  return result;
}

async function openEnhanceDetectionAccordion(page) {
  const result = await page.evaluate(async () => {
    const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim();
    const usable = (button) => {
      if (!button) return false;
      const rect = button.getBoundingClientRect();
      const style = window.getComputedStyle ? window.getComputedStyle(button) : null;
      return rect.width > 0 && rect.height > 8 && (!style || (style.display !== "none" && style.visibility !== "hidden"));
    };
    if (document.getElementById("enhance_mask_model_1")) {
      return { ok: true, alreadyOpen: true };
    }
    const buttons = Array.from(document.querySelectorAll("button"));
    const candidates = buttons.filter((candidate) => {
      const text = normalize(candidate.textContent);
      return text.includes("Detection") || text.includes("识别设置");
    });
    const button = candidates.find(usable) || candidates[0];
    if (!button || typeof button.click !== "function") {
      return { ok: false, reason: "missing Detection/识别设置 accordion" };
    }
    if (typeof button.scrollIntoView === "function") {
      button.scrollIntoView({ block: "center", inline: "nearest" });
      await new Promise((resolve) => setTimeout(resolve, 120));
    }
    button.click();
    await new Promise((resolve) => setTimeout(resolve, 1600));
    return {
      ok: !!document.getElementById("enhance_mask_model_1"),
      text: normalize(button.textContent),
      candidateCount: candidates.length,
    };
  });
  return result;
}

function assertSceneSamplesCollapsed(samples, reason) {
  const selectors = [
    SELECTORS.scenePanel,
    SELECTORS.sam3VideoMaskAccordion,
    SELECTORS.sceneAdditionalPrompt,
    SELECTORS.sam3FramesBackdrop,
  ];
  const maxBySelector = Object.fromEntries(selectors.map((selector) => [selector, 0]));
  let suppressionSeen = false;
  let firstLeak = null;

  for (const sample of samples) {
    for (const selector of selectors) {
      const measurement = sample[selector];
      if (!measurement || !measurement.exists) continue;
      maxBySelector[selector] = Math.max(maxBySelector[selector], Math.round(measurement.height || 0));
      suppressionSeen = suppressionSeen || String(measurement.htmlClassName || "").includes("simpai-preset-nav-active");
      if (!firstLeak && measurement.visible && measurement.height > 4) {
        firstLeak = { selector, measurement };
      }
    }
  }

  assertCondition(!firstLeak, `${reason} leaked scene UI; ${JSON.stringify(firstLeak)}`);
  assertCondition(suppressionSeen, `${reason} did not observe simpai-preset-nav-active suppression`);
  return maxBySelector;
}

async function clickAccordionRoot(page, selector) {
  const label = page.locator(`${selector} > button.label-wrap`).first();
  if (await label.count()) {
    await label.click({ force: true, timeout: config.timeoutMs });
    return true;
  }
  const target = page.locator(`${selector} summary, ${selector} button, ${selector} [role='button'], ${selector} label`).first();
  if (await target.count()) {
    await target.click({ force: true, timeout: config.timeoutMs });
    return true;
  }
  const root = page.locator(selector).first();
  if (await root.count()) {
    await root.click({ force: true, timeout: config.timeoutMs });
    return true;
  }
  return false;
}

async function checkboxState(page, id) {
  return await page.evaluate((checkboxId) => {
    const root = document.getElementById(checkboxId);
    const input = root ? root.querySelector('input[type="checkbox"]') : null;
    return {
      exists: !!input,
      checked: !!(input && input.checked),
      disabled: !!(input && input.disabled),
    };
  }, id);
}

async function setCheckbox(page, id, checked) {
  const before = await checkboxState(page, id);
  assertCondition(before.exists, `#${id} checkbox input does not exist`);
  assertCondition(!before.disabled, `#${id} checkbox input is disabled`);
  if (before.checked === checked) return `#${id} already ${checked ? "checked" : "unchecked"}`;

  await page.evaluate((checkboxId) => {
    const root = document.getElementById(checkboxId);
    const input = root ? root.querySelector('input[type="checkbox"]') : null;
    if (!input) return false;
    input.click();
    return true;
  }, id);
  await waitForUiSettle(page, 1000);

  const after = await checkboxState(page, id);
  assertCondition(after.checked === checked, `#${id} expected checked=${checked} but got ${after.checked}`);
  return `#${id} -> ${checked ? "checked" : "unchecked"}`;
}

async function activateTopLevelTab(page, labels) {
  const requestedLabels = Array.isArray(labels) ? labels : [labels];
  const result = await page.evaluate((tabLabels) => {
    const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim();
    const normalizedLabels = tabLabels.map(normalize).filter(Boolean);
    const isVisible = (el) => {
      if (!el || el.hidden) return false;
      const style = window.getComputedStyle ? window.getComputedStyle(el) : null;
      if (style && (style.display === "none" || style.visibility === "hidden")) return false;
      const rect = el.getBoundingClientRect();
      return rect.width > 0 && rect.height > 8;
    };
    const candidates = Array.from(document.querySelectorAll('[role="tab"], button'))
      .filter((el) => isVisible(el) && normalizedLabels.includes(normalize(el.innerText || el.textContent)))
      .sort((a, b) => {
        const roleDelta = (b.getAttribute("role") === "tab" ? 1 : 0) - (a.getAttribute("role") === "tab" ? 1 : 0);
        if (roleDelta) return roleDelta;
        return 0;
      });
    const target = candidates[0];
    if (!target) {
      return {
        ok: false,
        reason: "missing visible tab",
        labels: normalizedLabels,
        available: Array.from(document.querySelectorAll('[role="tab"], button'))
          .filter(isVisible)
          .map((el) => normalize(el.innerText || el.textContent))
          .filter(Boolean)
          .slice(0, 80),
      };
    }
    target.click();
    return {
      ok: true,
      label: normalize(target.innerText || target.textContent),
      labels: normalizedLabels,
      id: target.id || "",
      role: target.getAttribute("role") || "",
      className: typeof target.className === "string" ? target.className : "",
    };
  }, requestedLabels);
  assertCondition(result.ok, `could not activate top-level tab ${requestedLabels.join("/")}: ${JSON.stringify(result)}`);
  await waitForUiSettle(page, 700);
  return result;
}

async function readAdvancedPresetParameterState(page) {
  await activateTopLevelTab(page, ["Settings", "设置"]);
  await activateTopLevelTab(page, ["Advanced", "高级"]);
  await waitForUiSettle(page, 500);
  return await page.evaluate(() => {
    const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim();
    const readSliderBlock = (labelText) => {
      const blocks = Array.from(document.querySelectorAll(".block")).filter((node) => {
        const rect = node.getBoundingClientRect();
        const style = window.getComputedStyle ? window.getComputedStyle(node) : null;
        return rect.width > 0 && rect.height > 0 && (!style || (style.display !== "none" && style.visibility !== "hidden"));
      });
      const block = blocks.find((node) => normalize(node.innerText || node.textContent).startsWith(labelText));
      const number = block?.querySelector?.('input[type="number"]') || null;
      const range = block?.querySelector?.('input[type="range"]') || null;
      return {
        found: !!block,
        numberValue: number ? String(number.value) : "",
        rangeValue: range ? String(range.value) : "",
        text: normalize(block?.innerText || block?.textContent || "").slice(0, 120),
      };
    };
    return {
      guidance: readSliderBlock("Guidance Scale"),
      overwriteStep: readSliderBlock("Forced Overwrite of Sampling Step"),
    };
  });
}

async function presetAdvancedParamsRestoreStep(page) {
  await switchPreset(page, config.basePresetSelector, "base preset");
  await waitForPresetGallerySuppressionClear(page).catch(() => {});
  const baseState = await readAdvancedPresetParameterState(page);

  await switchPreset(page, config.paramPresetSelector, "parameter preset");
  await waitForPresetGallerySuppressionClear(page).catch(() => {});
  const paramState = await readAdvancedPresetParameterState(page);

  assertCondition(baseState.guidance.found && baseState.overwriteStep.found, `base advanced params missing; ${JSON.stringify(baseState)}`);
  assertCondition(paramState.guidance.found && paramState.overwriteStep.found, `parameter advanced params missing; ${JSON.stringify(paramState)}`);
  assertCondition(paramState.guidance.numberValue === config.paramPresetGuidance || paramState.guidance.rangeValue === config.paramPresetGuidance, `Guidance Scale did not restore for ${config.paramPresetSelector}; base=${JSON.stringify(baseState)} param=${JSON.stringify(paramState)}`);
  assertCondition(paramState.overwriteStep.numberValue === config.paramPresetOverwriteStep || paramState.overwriteStep.rangeValue === config.paramPresetOverwriteStep, `Forced Overwrite of Sampling Step did not restore for ${config.paramPresetSelector}; base=${JSON.stringify(baseState)} param=${JSON.stringify(paramState)}`);

  await activateTopLevelTab(page, ["Models", "模型"]);
  await page.locator(SELECTORS.baseModelDropdown).first().waitFor({ state: "visible", timeout: config.timeoutMs });
  const loraState = await readModelsPanelStabilityState(page);
  assertCondition(loraState.loraCheckboxCount > 0 && loraState.loraCheckedCount === loraState.loraCheckboxCount, `parameter preset lora checkboxes were not restored checked; ${JSON.stringify(loraState)}`);
  return `guidance=${paramState.guidance.numberValue || paramState.guidance.rangeValue} step=${paramState.overwriteStep.numberValue || paramState.overwriteStep.rangeValue} lora=${loraState.loraCheckedCount}/${loraState.loraCheckboxCount}`;
}

async function assertEngineClassMarker(page, expectedVisible) {
  const root = await measure(page, SELECTORS.engineClass);
  assertCondition(root.exists, `${SELECTORS.engineClass} does not exist`);

  const htmlHasVisibleClass = await page.evaluate(() => {
    return document.documentElement.classList.contains("simpai-engine-class-visible");
  });
  assertCondition(
    htmlHasVisibleClass === expectedVisible,
    `engine marker html class expected ${expectedVisible} but got ${htmlHasVisibleClass}; ${compactMeasure(root)}`
  );

  assertCondition(
    root.height <= 8,
    `${SELECTORS.engineClass} should not reserve a full row; ${compactMeasure(root)}`
  );

  const container = await measure(page, SELECTORS.engineClassContainer);
  if (container.exists) {
    assertCondition(
      container.height <= 8,
      `${SELECTORS.engineClassContainer} should not reserve a full row; ${compactMeasure(container)}`
    );
  }

  if (expectedVisible) {
    assertCondition(root.text.length > 0, `${SELECTORS.engineClass} should keep a non-empty engine label`);
  }
  return `engine marker visibleClass=${htmlHasVisibleClass} h=${Math.round(root.height)}`;
}

async function assertControlInputValue(page, selector, expected) {
  const state = await page.evaluate((sel) => {
    const root = document.querySelector(sel);
    const input = root ? root.querySelector('input[type="number"], input, textarea') : null;
    return {
      exists: !!input,
      value: input ? input.value : null,
    };
  }, selector);
  assertCondition(state.exists, `${selector} input does not exist`);
  assertCondition(String(state.value) === String(expected), `${selector} expected value=${expected} but got ${state.value}`);
  return state;
}

async function assertControlInputBounds(page, selector, expected) {
  const state = await page.evaluate((sel) => {
    const root = document.querySelector(sel);
    const input = root ? root.querySelector('input[type="number"], input[type="range"], input, textarea') : null;
    return {
      exists: !!input,
      value: input ? input.value : null,
      min: input ? input.getAttribute("min") : null,
      max: input ? input.getAttribute("max") : null,
      step: input ? input.getAttribute("step") : null,
    };
  }, selector);
  assertCondition(state.exists, `${selector} input does not exist`);
  if (Object.prototype.hasOwnProperty.call(expected, "value")) {
    assertCondition(String(state.value) === String(expected.value), `${selector} expected value=${expected.value} but got ${state.value}`);
  }
  if (Object.prototype.hasOwnProperty.call(expected, "min")) {
    assertCondition(String(state.min) === String(expected.min), `${selector} expected min=${expected.min} but got ${state.min}`);
  }
  if (Object.prototype.hasOwnProperty.call(expected, "max")) {
    assertCondition(String(state.max) === String(expected.max), `${selector} expected max=${expected.max} but got ${state.max}`);
  }
  return state;
}

async function clickSceneControlResetAndAssertValue(page, selector, expected) {
  const state = await page.evaluate(async ({ sel, expectedValue }) => {
    const root = document.querySelector(sel);
    const number = root ? root.querySelector('input[type="number"]') : null;
    const range = root ? root.querySelector('input[type="range"]') : null;
    const input = number || range;
    const resetButton = root ? root.querySelector('[data-testid="reset-button"], .reset-button') : null;
    const setInputValue = (target, value) => {
      if (!target) return false;
      const descriptor = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");
      if (descriptor && descriptor.set) {
        descriptor.set.call(target, value);
      } else {
        target.value = value;
      }
      target.dispatchEvent(new Event("input", { bubbles: true }));
      target.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    };
    if (!root || !input || !resetButton) {
      return {
        ok: false,
        reason: "missing reset target",
        hasRoot: !!root,
        hasInput: !!input,
        hasResetButton: !!resetButton,
      };
    }
    const min = Number.parseFloat(input.getAttribute("min") || "");
    const max = Number.parseFloat(input.getAttribute("max") || "");
    const expectedNumber = Number.parseFloat(expectedValue);
    let temporaryValue = Number.isFinite(min) && String(min) !== String(expectedValue) ? min : null;
    if (temporaryValue === null && Number.isFinite(max) && String(max) !== String(expectedValue)) {
      temporaryValue = max;
    }
    if (temporaryValue === null && Number.isFinite(expectedNumber)) {
      temporaryValue = expectedNumber + 1;
    }
    if (temporaryValue === null || String(temporaryValue) === String(expectedValue)) {
      temporaryValue = "";
    }
    setInputValue(input, String(temporaryValue));
    await new Promise((resolve) => setTimeout(resolve, 160));
    resetButton.click();
    await new Promise((resolve) => setTimeout(resolve, 260));
    return {
      ok: true,
      temporaryValue: String(temporaryValue),
      numberValue: number ? String(number.value) : "",
      rangeValue: range ? String(range.value) : "",
      storedDefault: root.dataset.simpleaiScenePresetDefaultValue || "",
    };
  }, { sel: selector, expectedValue: String(expected) });
  assertCondition(state.ok, `${selector} reset target unavailable; ${JSON.stringify(state)}`);
  assertCondition(
    state.numberValue === String(expected) || state.rangeValue === String(expected),
    `${selector} reset button expected value=${expected} but got ${JSON.stringify(state)}`
  );
  return state;
}

async function seedSam3FramesEditorOpenForGuardTest(page) {
  return await page.evaluate((selector) => {
    const backdrop = document.querySelector(selector);
    if (!backdrop) return false;
    document.body.classList.add("sam3-frames-editor-open");
    backdrop.removeAttribute("aria-hidden");
    backdrop.style.display = "flex";
    backdrop.style.pointerEvents = "none";
    return true;
  }, SELECTORS.sam3FramesBackdrop);
}

async function initialStateStep(page) {
  await assertNoExpandedGallery(page, "initial page load");
  for (const selector of [
    SELECTORS.scenePanel,
    SELECTORS.sam3VideoMaskAccordion,
    SELECTORS.engineClass,
    SELECTORS.imageInputPanel,
    SELECTORS.ttsPanel,
    SELECTORS.advancedColumn,
    SELECTORS.inputImageCheckbox,
    SELECTORS.qwenTtsCheckbox,
    SELECTORS.advancedCheckbox,
  ]) {
    const measurement = await measure(page, selector);
    assertCondition(measurement.exists, `${selector} does not exist after initial load`);
  }
  return "required visibility roots exist";
}

async function refreshScrollStep(page) {
  await assertScrollNearTop(page, "initial load");
  await page.evaluate(() => {
    const root = document.scrollingElement || document.documentElement;
    window.scrollTo({ top: root.scrollHeight, left: 0, behavior: "auto" });
  });
  await page.waitForTimeout(300);
  const beforeReload = await measureScroll(page);
  if (beforeReload.maxY > 16) {
    assertCondition(beforeReload.y > 8, `test could not scroll before reload; y=${beforeReload.y} maxY=${beforeReload.maxY}`);
  }

  await page.reload({ waitUntil: "domcontentloaded", timeout: config.timeoutMs });
  await page.locator(config.basePresetSelector).first().waitFor({ state: "attached", timeout: config.timeoutMs });
  await page.locator(SELECTORS.inputImageCheckbox).first().waitFor({ state: "attached", timeout: config.timeoutMs });

  const samples = [];
  for (const delayMs of [250, 500, 900, 1400, 2200]) {
    await page.waitForTimeout(delayMs);
    samples.push(await assertScrollNearTop(page, `reload sample ${delayMs}ms`));
  }
  const maxSampleY = Math.max(...samples.map((item) => item.y));
  return `beforeReload y=${beforeReload.y}/${beforeReload.maxY}; maxReloadY=${maxSampleY}`;
}

async function galleryPresetSwitchStep(page) {
  await switchPreset(page, config.basePresetSelector, "base preset");
  await waitForPresetGallerySuppressionClear(page);
  const catalog = await measure(page, SELECTORS.finishedCatalog);
  if (!catalog.exists || !catalog.visible) {
    throw new SmokeSkip(`${SELECTORS.finishedCatalog} unavailable; no result history to reopen`);
  }

  const clicked = await clickAccordionRoot(page, SELECTORS.finishedCatalog);
  assertCondition(clicked, `${SELECTORS.finishedCatalog} could not be clicked`);
  await waitForUiSettle(page, 1000);

  const openedCatalog = await measureFinishedCatalogState(page);
  if (!openedCatalog.bodyVisible || openedCatalog.maxBodyHeight <= 20) {
    throw new SmokeSkip(`finished catalog body did not open; ${compactCatalogState(openedCatalog)}`);
  }

  const altSamples = await clickPresetAndSampleCatalog(page, config.altPresetSelector, { durationMs: 2600, intervalMs: 60 });
  assertCatalogSamplesCollapsed(altSamples, "base to alternate preset");
  await waitForUiSettle(page, 800);
  await assertFinishedCatalogCollapsed(page, "base to alternate preset final state");
  await assertHiddenOrZero(page, SELECTORS.finishedGallery, { maxHeight: 4 });

  const baseSamples = await clickPresetAndSampleCatalog(page, config.basePresetSelector, { durationMs: 2600, intervalMs: 60 });
  assertCatalogSamplesCollapsed(baseSamples, "alternate preset back to base preset");
  await waitForUiSettle(page, 800);
  const catalogAfterBaseSwitch = await assertFinishedCatalogCollapsed(page, "alternate preset back to base final state");
  await assertHiddenOrZero(page, SELECTORS.finishedGallery, { maxHeight: 4 });

  await waitForPresetGallerySuppressionClear(page);
  await clickAccordionRoot(page, SELECTORS.finishedCatalog);
  await waitForUiSettle(page, 1000);
  const reopened = await measureFinishedCatalogState(page);
  assertCondition(
    reopened.bodyVisible && reopened.maxBodyHeight > 20 && reopened.labelOpen,
    `finished catalog should reopen after preset switch; ${compactCatalogState(reopened)}`
  );
  const visibleGallery = await waitForMeasuredVisible(page, SELECTORS.finishedGallery, {
    minHeight: 80,
    timeoutMs: 8000,
    intervalMs: 400,
  }).catch(() => null);
  if (visibleGallery) {
    await clickAccordionRoot(page, SELECTORS.finishedCatalog);
    await waitForUiSettle(page, 900);
    await assertFinishedCatalogCollapsed(page, "manual catalog close");
    await assertHiddenOrZero(page, SELECTORS.finishedGallery, { maxHeight: 4 });
  }

  const sceneSamples = await clickPresetAndSampleCatalog(page, config.scenePresetSelector, { durationMs: 3200, intervalMs: 60 });
  assertCatalogSamplesCollapsed(sceneSamples, "base to scene preset");
  await waitForUiSettle(page, 800);
  await assertFinishedCatalogCollapsed(page, "base to scene final state");
  await switchPreset(page, config.basePresetSelector, "base preset");
  await assertNoExpandedGallery(page, "gallery cleanup restore");
  return `catalog collapsed h=${Math.round(catalogAfterBaseSwitch.rootHeight)}, manualGalleryLinked=${!!visibleGallery}`;
}

async function galleryMediaSwitchStatusStep(page) {
  await switchPreset(page, config.basePresetSelector, "base preset");
  await waitForPresetGallerySuppressionClear(page);

  const catalog = await measure(page, SELECTORS.finishedCatalog);
  if (!catalog.exists || !catalog.visible) {
    throw new SmokeSkip(`${SELECTORS.finishedCatalog} unavailable; no result history for media switch status`);
  }

  let catalogState = await measureFinishedCatalogState(page);
  if (!catalogState.bodyVisible || !catalogState.labelOpen) {
    const clicked = await clickAccordionRoot(page, SELECTORS.finishedCatalog);
    assertCondition(clicked, `${SELECTORS.finishedCatalog} could not be opened for media switch status`);
    await waitForUiSettle(page, 1200);
    catalogState = await measureFinishedCatalogState(page);
  }
  if (!catalogState.bodyVisible || !catalogState.labelOpen) {
    throw new SmokeSkip(`finished catalog body did not open for media switch status; ${compactCatalogState(catalogState)}`);
  }

  const initial = await galleryBrowserStatusState(page);
  if (!initial.images.exists || !initial.videos.exists) {
    throw new SmokeSkip(`gallery media switch buttons unavailable; ${JSON.stringify(initial)}`);
  }

  await clickGalleryMediaButton(page, SELECTORS.galleryVideosButton, "videos");
  const videos = await waitForGalleryStatusText(page, /\bvideos\b/i, "videos after switching to Videos");
  assertCondition(videos.videos.pressed === "true", `Videos button should be pressed after switch; ${JSON.stringify(videos)}`);

  const closedAfterVideo = await clickAccordionRoot(page, SELECTORS.finishedCatalog);
  assertCondition(closedAfterVideo, `${SELECTORS.finishedCatalog} could not be closed after switching to Videos`);
  await waitForUiSettle(page, 900);
  const videoCloseSurface = await measureGalleryWelcomeSurface(page);
  assertCondition(
    (videoCloseSurface.previewVisible || videoCloseSurface.placeholderVisible)
      && (videoCloseSurface.previewLoaded || videoCloseSurface.placeholderLoaded),
    `video gallery close did not restore welcome preview; sample=${JSON.stringify(videoCloseSurface)}`
  );
  assertCondition(
    !videoCloseSurface.galleryVisible && !videoCloseSurface.videoVisible,
    `video gallery close left gallery/video visible; sample=${JSON.stringify(videoCloseSurface)}`
  );

  const reopenedAfterVideo = await clickAccordionRoot(page, SELECTORS.finishedCatalog);
  assertCondition(reopenedAfterVideo, `${SELECTORS.finishedCatalog} could not reopen after Videos close`);
  await waitForUiSettle(page, 1200);

  await clickGalleryMediaButton(page, SELECTORS.galleryImagesButton, "images");
  const images = await waitForGalleryStatusText(page, /\bitems\b/i, "items after switching to Images");
  assertCondition(images.images.pressed === "true", `Images button should be pressed after switch; ${JSON.stringify(images)}`);

  return `videos=${videos.status}; videoCloseWelcome=${videoCloseSurface.previewVisible || videoCloseSurface.placeholderVisible}; images=${images.status}`;
}

async function galleryFirstOpenTimingStep(page) {
  await gotoWebUi(page);
  await waitForPresetGallerySuppressionClear(page).catch(() => {});

  const catalog = await measure(page, SELECTORS.finishedCatalog);
  if (!catalog.exists || !catalog.visible) {
    throw new SmokeSkip(`${SELECTORS.finishedCatalog} unavailable; no result history for first-open timing`);
  }

  let catalogState = await measureFinishedCatalogState(page);
  if (catalogState.bodyVisible || catalogState.labelOpen) {
    const closed = await clickAccordionRoot(page, SELECTORS.finishedCatalog);
    assertCondition(closed, `${SELECTORS.finishedCatalog} could not be closed before first-open timing`);
    await waitForUiSettle(page, 800);
    catalogState = await measureFinishedCatalogState(page);
  }
  if (catalogState.bodyVisible || catalogState.labelOpen) {
    throw new SmokeSkip(`finished catalog did not start closed for first-open timing; ${compactCatalogState(catalogState)}`);
  }

  const previewBefore = await measure(page, SELECTORS.previewGenerating);
  if (!previewBefore.exists || !previewBefore.visible) {
    throw new SmokeSkip(`welcome preview unavailable before first-open timing; ${compactMeasure(previewBefore)}`);
  }

  const clicked = await clickAccordionRoot(page, SELECTORS.finishedCatalog);
  assertCondition(clicked, `${SELECTORS.finishedCatalog} could not be opened for first-open timing`);

  const samples = [];
  const started = Date.now();
  do {
    samples.push(await page.evaluate((selectors) => {
      const isLayoutVisible = (el) => {
        if (!el) return false;
        let node = el;
        while (node && node.nodeType === 1) {
          const style = window.getComputedStyle ? window.getComputedStyle(node) : null;
          if (
            node.hidden ||
            node.hasAttribute("hidden") ||
            (style && (style.display === "none" || style.visibility === "hidden"))
          ) {
            return false;
          }
          node = node.parentElement;
        }
        const rect = el.getBoundingClientRect();
        return rect.width > 2 && rect.height > 2;
      };
      const isVisible = (el) => {
        if (!isLayoutVisible(el)) return false;
        let node = el;
        while (node && node.nodeType === 1) {
          const style = window.getComputedStyle ? window.getComputedStyle(node) : null;
          if (style && Number.parseFloat(style.opacity || "1") <= 0.03) return false;
          node = node.parentElement;
        }
        return true;
      };
      const countVisibleMedia = (root) => {
        if (!root) return 0;
        return Array.from(root.querySelectorAll(".grid-wrap .gallery-item, .gallery-container > .preview img, .gallery-container > .preview video, img, video"))
          .filter(isLayoutVisible)
          .length;
      };
      const overlapRatio = (a, b) => {
        if (!a || !b || a.width <= 0 || a.height <= 0 || b.width <= 0 || b.height <= 0) return 0;
        const left = Math.max(a.left, b.left);
        const right = Math.min(a.right, b.right);
        const top = Math.max(a.top, b.top);
        const bottom = Math.min(a.bottom, b.bottom);
        const overlap = Math.max(0, right - left) * Math.max(0, bottom - top);
        const base = Math.min(a.width * a.height, b.width * b.height);
        return base > 0 ? overlap / base : 0;
      };
      const catalogRoot = document.querySelector(selectors.finishedCatalog);
      const label = catalogRoot ? catalogRoot.querySelector(":scope > button.label-wrap") || catalogRoot.querySelector("button.label-wrap") : null;
      const preview = document.querySelector(selectors.previewGenerating);
      const gallery = document.querySelector(selectors.finishedGallery);
      const placeholder = document.querySelector("#simpleai_gallery_welcome_guard_placeholder");
      const statusRoot = document.querySelector(selectors.galleryBrowserStatus);
      const statusTarget = statusRoot?.querySelector?.(".prose, .md, p") || statusRoot;
      const previewRect = preview ? preview.getBoundingClientRect() : null;
      const galleryRect = gallery ? gallery.getBoundingClientRect() : null;
      const placeholderRect = placeholder ? placeholder.getBoundingClientRect() : null;
      const baseRect = (preview && isVisible(preview)) ? previewRect : ((placeholder && isVisible(placeholder)) ? placeholderRect : previewRect || placeholderRect);
      const galleryMediaCount = countVisibleMedia(gallery);
      const galleryUserVisible = isVisible(gallery);
      const statusText = (statusTarget?.innerText || statusTarget?.textContent || "").replace(/\s+/g, " ").trim();
      const overlayAligned = !!(galleryRect && baseRect) && overlapRatio(galleryRect, baseRect) > 0.88
        && Math.abs(galleryRect.left - baseRect.left) < 8
        && Math.abs(galleryRect.top - baseRect.top) < 8;
      return {
        t: Math.round(performance.now()),
        catalogOpen: !!label && (label.classList.contains("open") || label.getAttribute("aria-expanded") === "true"),
        previewVisible: isVisible(preview),
        placeholderVisible: isVisible(placeholder),
        previewHeight: previewRect ? previewRect.height : 0,
        galleryVisible: galleryUserVisible,
        galleryLayoutVisible: isLayoutVisible(gallery),
        galleryHeight: galleryRect ? galleryRect.height : 0,
        galleryMediaCount,
        statusText,
        welcomeGuard: document.documentElement.classList.contains("simpai-gallery-browser-welcome-pending"),
        overlayActive: document.documentElement.classList.contains("simpai-gallery-browser-overlay-active"),
        surfaceOverlayAligned: overlayAligned,
        galleryHasMedia: isLayoutVisible(gallery) && galleryMediaCount > 0,
        galleryReady: galleryUserVisible && galleryMediaCount > 0,
      };
    }, SELECTORS));
    const readyIndex = samples.findIndex((sample) => sample.galleryReady);
    if (readyIndex >= 0 && samples.length - readyIndex >= 4) break;
    await page.waitForTimeout(60);
  } while (Date.now() - started < 4200);

  const firstReadyIndex = samples.findIndex((sample) => sample.galleryReady);
  if (firstReadyIndex < 0) {
    const loadedButBlank = samples.find((sample) => /\b[1-9]\d*\s+(items|videos)\b/i.test(sample.statusText || "") && !sample.previewVisible && !sample.placeholderVisible && !sample.galleryVisible);
    assertCondition(
      !loadedButBlank,
      `gallery first-open reported loaded media but rendered blank; sample=${JSON.stringify(loadedButBlank)}`
    );
    throw new SmokeSkip(`gallery first-open did not render media; samples=${JSON.stringify(samples.slice(-5))}`);
  }
  const firstBlank = samples
    .slice(0, firstReadyIndex)
    .find((sample, index) => index > 0 && sample.catalogOpen && !sample.previewVisible && !sample.placeholderVisible && !sample.galleryReady);
  assertCondition(
    !firstBlank,
    `gallery first-open blank preview gap before media render; sample=${JSON.stringify(firstBlank)}`
  );
  const firstSideBySide = samples
    .slice(0, firstReadyIndex + 1)
    .find((sample) => sample.catalogOpen && sample.galleryVisible && (sample.previewVisible || sample.placeholderVisible) && !sample.surfaceOverlayAligned);
  assertCondition(
    !firstSideBySide,
    `gallery first-open rendered welcome and gallery side-by-side instead of overlay; sample=${JSON.stringify(firstSideBySide)}`
  );
  return `samples=${samples.length}, readyIndex=${firstReadyIndex}, previewBefore=${Math.round(previewBefore.height)}`;
}

async function galleryRegenButtonStep(page) {
  await switchPreset(page, config.basePresetSelector, "base preset");
  await waitForPresetGallerySuppressionClear(page);

  const catalog = await measure(page, SELECTORS.finishedCatalog);
  if (!catalog.exists || !catalog.visible) {
    throw new SmokeSkip(`${SELECTORS.finishedCatalog} unavailable; no result history for gallery regen`);
  }

  let catalogState = await measureFinishedCatalogState(page);
  if (!catalogState.bodyVisible || !catalogState.labelOpen) {
    const clicked = await clickAccordionRoot(page, SELECTORS.finishedCatalog);
    assertCondition(clicked, `${SELECTORS.finishedCatalog} could not be opened for gallery regen`);
    await waitForUiSettle(page, 1200);
    catalogState = await measureFinishedCatalogState(page);
  }
  if (!catalogState.bodyVisible || !catalogState.labelOpen) {
    throw new SmokeSkip(`finished catalog body did not open for gallery regen; ${compactCatalogState(catalogState)}`);
  }

  await clickGalleryMediaButton(page, SELECTORS.galleryImagesButton, "images");
  await waitForGalleryStatusText(page, /\bitems\b/i, "items before gallery regen");
  const openedPreview = await page.evaluate((selectors) => {
    const isVisible = (el) => {
      if (!el) return false;
      let node = el;
      while (node && node.nodeType === 1) {
        const style = window.getComputedStyle(node);
        if (node.hidden || node.hasAttribute("hidden") || style.display === "none" || style.visibility === "hidden") return false;
        node = node.parentElement;
      }
      const rect = el.getBoundingClientRect();
      return rect.width > 2 && rect.height > 2;
    };
    const media = Array.from(document.querySelectorAll(`${selectors.finishedGallery} img, ${selectors.finalGallery} img`)).find(isVisible);
    if (!media) return { ok: false, reason: "no visible gallery media" };
    const target = media.closest("button, .gallery-item, [role='button'], .thumbnail-item") || media;
    target.click();
    return { ok: true, tag: target.tagName, text: (target.innerText || target.textContent || "").trim().slice(0, 80) };
  }, SELECTORS);
  if (!openedPreview.ok) {
    throw new SmokeSkip(`gallery regen has no image to select; ${JSON.stringify(openedPreview)}`);
  }
  await waitForUiSettle(page, 1200);

  const clickedRegen = await page.evaluate((selectors) => {
    const isVisible = (el) => {
      if (!el) return false;
      let node = el;
      while (node && node.nodeType === 1) {
        const style = window.getComputedStyle(node);
        if (node.hidden || node.hasAttribute("hidden") || style.display === "none" || style.visibility === "hidden") return false;
        node = node.parentElement;
      }
      const rect = el.getBoundingClientRect();
      return rect.width > 2 && rect.height > 2;
    };
    const toolbox = document.querySelector(selectors.imageToolbox);
    const buttons = Array.from(toolbox?.querySelectorAll?.("button") || []).filter(isVisible);
    const regen = buttons.find((button) => (button.innerText || button.textContent || "").includes("🔁"));
    if (!regen) return { ok: false, reason: "regen button missing", toolboxVisible: isVisible(toolbox), buttonTexts: buttons.map((button) => (button.innerText || button.textContent || "").trim()) };
    regen.click();
    return { ok: true, buttonTexts: buttons.map((button) => (button.innerText || button.textContent || "").trim()) };
  }, SELECTORS);
  if (!clickedRegen.ok) {
    throw new SmokeSkip(`gallery regen button unavailable; ${JSON.stringify(clickedRegen)}`);
  }
  await waitForUiSettle(page, 500);

  const regenErrors = [];
  const onConsole = (message) => {
    const text = message.text();
    if (/Uncaught|TypeError|Textbox|choices|i18n/i.test(text)) {
      regenErrors.push({ type: "console", level: message.type(), text: text.slice(0, 1200) });
    }
  };
  const onPageError = (error) => {
    regenErrors.push({ type: "pageerror", text: String(error?.stack || error).slice(0, 1600) });
  };
  const onResponse = async (response) => {
    const url = response.url();
    if (!/gradio_api\/(queue|run|call|predict|api)/i.test(url)) return;
    if (response.status() < 400) return;
    const text = await response.text().catch(() => "");
    regenErrors.push({ type: "response", status: response.status(), url, text: text.slice(0, 1600) });
  };
  page.on("console", onConsole);
  page.on("pageerror", onPageError);
  page.on("response", onResponse);
  try {
    const clickedConfirm = await page.evaluate((selectors) => {
      const root = document.querySelector(selectors.paramsNoteRegenButton);
      const button = root && root.matches && root.matches("button") ? root : root?.querySelector?.("button");
      if (!button || typeof button.click !== "function") return false;
      button.click();
      return true;
    }, SELECTORS);
    assertCondition(clickedConfirm, `${SELECTORS.paramsNoteRegenButton} confirm button missing`);
    await page.waitForTimeout(4500);
  } finally {
    page.off("console", onConsole);
    page.off("pageerror", onPageError);
    page.off("response", onResponse);
  }
  assertCondition(regenErrors.length === 0, `gallery regen emitted browser/backend errors; ${JSON.stringify(regenErrors)}`);

  const after = await page.evaluate((selectors) => {
    const modelBridge = (id) => document.getElementById(id)?.value || "";
    const note = document.querySelector(selectors.paramsNoteBox);
    const noteDisplay = note ? window.getComputedStyle(note).display : "";
    return {
      base: modelBridge("model_bridge_base"),
      refiner: modelBridge("model_bridge_refiner"),
      lora0: modelBridge("lora_bridge_0"),
      noteDisplay,
    };
  }, SELECTORS);
  assertCondition(!!after.base, `gallery regen left model bridge empty; ${JSON.stringify(after)}`);
  return `base=${after.base.slice(0, 80)} refiner=${after.refiner.slice(0, 80)} lora0=${after.lora0.slice(0, 80)}`;
}

async function presetStoreToggleStep(page) {
  await page.evaluate(() => {
    try {
      if (typeof clearSimpleAIPresetSwitchGalleryHidden === "function") {
        clearSimpleAIPresetSwitchGalleryHidden("preset_store_smoke");
      }
    } catch (error) {
      console.warn("[UI-TRACE] preset_store_smoke.gallery_clear_failed", error);
    }
  });
  await waitForUiSettle(page, 500);
  await assertHiddenOrZero(page, SELECTORS.identityDialog, { maxHeight: 4 });

  const clicked = await page.evaluate((selector) => {
    const root = document.querySelector(selector);
    const button = root && root.matches && root.matches("button") ? root : root?.querySelector?.("button");
    if (!button || typeof button.click !== "function") return false;
    button.click();
    return true;
  }, SELECTORS.barStoreButton);
  assertCondition(clicked, `${SELECTORS.barStoreButton} could not be clicked`);

  const opened = await waitForPresetStoreOpen(page);
  assertCondition(!opened.identityVisible, `identity dialog opened while preset store opened; ${JSON.stringify(opened)}`);
  assertCondition(opened.draftNames.length > 0, `preset store draft did not render names; ${JSON.stringify(opened)}`);
  assertCondition(opened.duplicateDraftNames.length === 0, `preset store draft contains duplicate names; ${JSON.stringify(opened)}`);

  const applyClicked = await page.evaluate((selector) => {
    const root = document.querySelector(selector);
    const button = root && root.matches && root.matches("button") ? root : root?.querySelector?.("button");
    if (!button || typeof button.click !== "function") return false;
    button.click();
    return true;
  }, SELECTORS.presetStoreApply);
  assertCondition(applyClicked, `${SELECTORS.presetStoreApply} could not be clicked`);

  const applied = await waitForPresetStoreApply(page, opened.presetStoreSeq, opened.draftNames);

  const closeClicked = await page.evaluate((selector) => {
    const button = document.querySelector(selector);
    if (!button || typeof button.click !== "function") return false;
    button.click();
    return true;
  }, SELECTORS.presetStoreClose);
  assertCondition(closeClicked, `${SELECTORS.presetStoreClose} could not be clicked`);

  await waitForPresetStoreClosed(page);
  return `draft=${applied.draftCount}; pool=${opened.candidateCount}; seq=${opened.presetStoreSeq}->${applied.presetStoreSeq}`;
}

async function sceneSwitchStep(page) {
  await switchPreset(page, config.scenePresetSelector, "scene preset");
  await waitForMeasuredVisible(page, SELECTORS.scenePanel, { minHeight: 24 });
  await waitForMeasuredVisible(page, SELECTORS.sam3VideoMaskAccordion, { minHeight: 16 });
  await assertControlInputValue(page, SELECTORS.sceneVarNumber, config.scenePresetVarNumber);
  const seededSam3Editor = await seedSam3FramesEditorOpenForGuardTest(page);

  const samples = await clickPresetAndSample(page, config.basePresetSelector, { durationMs: 1800, intervalMs: 45, force: seededSam3Editor });
  assertSceneSamplesCollapsed(samples, seededSam3Editor ? "seeded SAM3 editor scene to base" : "scene to base");
  await waitForUiSettle(page, 900);
  await waitForMeasuredHiddenOrZero(page, SELECTORS.scenePanel, { maxHeight: 4 });
  await waitForMeasuredHiddenOrZero(page, SELECTORS.sam3VideoMaskAccordion, { maxHeight: 4 });
  await waitForMeasuredHiddenOrZero(page, SELECTORS.sceneAdditionalPrompt, { maxHeight: 4 });
  await assertHiddenOrZero(page, SELECTORS.sam3FramesBackdrop, { maxHeight: 4 });
  return `scene controls hide cleanly after leaving scene preset; seededSam3Editor=${seededSam3Editor}`;
}

async function continuousPresetSwitchStep(page) {
  const rounds = [];
  for (let index = 0; index < 2; index += 1) {
    await switchPreset(page, config.scenePresetSelector, `scene preset round ${index + 1}`);
    await waitForMeasuredVisible(page, SELECTORS.scenePanel, { minHeight: 24 });
    await assertControlInputValue(page, SELECTORS.sceneVarNumber, config.scenePresetVarNumber);

    const samples = await clickPresetAndSample(page, config.basePresetSelector, { durationMs: 2800, intervalMs: 45 });
    const maxBySelector = assertSceneSamplesCollapsed(samples, `scene to base round ${index + 1}`);
    await waitForUiSettle(page, 900);
    await waitForMeasuredHiddenOrZero(page, SELECTORS.scenePanel, { maxHeight: 4 });
    await waitForMeasuredHiddenOrZero(page, SELECTORS.sam3VideoMaskAccordion, { maxHeight: 4 });
    rounds.push(maxBySelector);
  }
  return `scene/base rounds=${rounds.length} max=${JSON.stringify(rounds)}`;
}

async function ttpScenePresetParameterStep(page) {
  if (!config.ttpPresetSelector) {
    throw new SmokeSkip("SIMPAI_PRESET_TTP_SELECTOR not configured");
  }
  await switchPreset(page, config.ttpPresetSelector, "TTP scene preset");
  await waitForMeasuredVisible(page, SELECTORS.scenePanel, { minHeight: 24 });
  const state = await assertControlInputBounds(page, SELECTORS.sceneVarNumber, {
    value: config.ttpPresetVarNumber,
    max: config.ttpPresetVarNumberMax,
  });
  await clickAccordionRoot(page, SELECTORS.sceneAdvancedParameters);
  await waitForUiSettle(page, 700);
  const resetState = await clickSceneControlResetAndAssertValue(
    page,
    SELECTORS.sceneVarNumber2,
    config.ttpPresetVarNumber2
  );
  return `${config.ttpPresetSelector} scene_var_number=${state.value} max=${state.max}; scene_var_number2 reset=${resetState.numberValue || resetState.rangeValue}`;
}

async function togglePanelsStep(page) {
  await switchPreset(page, config.panelPresetSelector, "panel preset");
  const originalImage = await checkboxState(page, "input_image_checkbox");
  const originalTts = await checkboxState(page, "qwen_tts_checkbox");
  const originalAdvanced = await checkboxState(page, "advanced_checkbox");

  try {
    await setCheckbox(page, "input_image_checkbox", true);
    await assertVisible(page, SELECTORS.imageInputPanel, { minHeight: 24 });
    await assertEngineClassMarker(page, true);

    await setCheckbox(page, "qwen_tts_checkbox", true);
    await assertVisible(page, SELECTORS.ttsPanel, { minHeight: 24 });
    await assertEngineClassMarker(page, true);

    await setCheckbox(page, "qwen_tts_checkbox", false);
    await assertHiddenOrZero(page, SELECTORS.ttsPanel, { maxHeight: 4 });
    await assertEngineClassMarker(page, true);

    await setCheckbox(page, "input_image_checkbox", false);
    await assertHiddenOrZero(page, SELECTORS.imageInputPanel, { maxHeight: 4 });
    await assertEngineClassMarker(page, false);

    await setCheckbox(page, "advanced_checkbox", true);
    await assertVisible(page, SELECTORS.advancedColumn, { minHeight: 24 });

    await setCheckbox(page, "advanced_checkbox", false);
    await assertHiddenOrZero(page, SELECTORS.advancedColumn, { maxHeight: 4 });
  } finally {
    if (originalAdvanced.exists) await setCheckbox(page, "advanced_checkbox", originalAdvanced.checked).catch(() => {});
    if (originalTts.exists) await setCheckbox(page, "qwen_tts_checkbox", originalTts.checked).catch(() => {});
    if (originalImage.exists) await setCheckbox(page, "input_image_checkbox", originalImage.checked).catch(() => {});
  }

  return "image/TTS/advanced panels toggle without reserved blank rows";
}

async function inpaintModeFirstSwitchStep(page) {
  await switchPreset(page, config.panelPresetSelector, "panel preset");
  const originalImage = await checkboxState(page, "input_image_checkbox");
  try {
    await setCheckbox(page, "input_image_checkbox", true);
    await activateImageInputTab(page, "inpaint");
    await page.locator(SELECTORS.inpaintMode).first().waitFor({ state: "attached", timeout: config.timeoutMs });

    for (const selector of [
      SELECTORS.inpaintMode,
      SELECTORS.inpaintAdditionalPrompt,
      SELECTORS.outpaintSelections,
      SELECTORS.exampleInpaintPrompts,
    ]) {
      const state = await mountedSelfState(page, selector);
      assertCondition(state.exists, `${selector} does not exist`);
    }

    await page.evaluate(() => {
      window.syncInpaintModePromptVisibility?.("Inpaint or Outpaint (default)");
    });
    await waitForUiSettle(page, 450);
    await assertMountedSelfHidden(page, SELECTORS.inpaintAdditionalPrompt);
    await assertMountedSelfHidden(page, SELECTORS.exampleInpaintPrompts);
    await assertMountedSelfShown(page, SELECTORS.outpaintSelections);

    await page.evaluate(() => {
      window.syncInpaintModePromptVisibility?.("Improve Detail (face, hand, eyes, etc.)");
    });
    await waitForUiSettle(page, 450);
    await assertMountedSelfShown(page, SELECTORS.inpaintAdditionalPrompt);
    await assertMountedSelfShown(page, SELECTORS.exampleInpaintPrompts);
    await assertMountedSelfHidden(page, SELECTORS.outpaintSelections);

    await page.evaluate(() => {
      window.syncInpaintModePromptVisibility?.("Modify Content (add objects, change background, etc.)");
    });
    await waitForUiSettle(page, 450);
    await assertMountedSelfShown(page, SELECTORS.inpaintAdditionalPrompt);
    await assertMountedSelfHidden(page, SELECTORS.exampleInpaintPrompts);
    await assertMountedSelfHidden(page, SELECTORS.outpaintSelections);

    return "inpaint mode mounted controls sync on first explicit mode switch";
  } finally {
    if (originalImage.exists) await setCheckbox(page, "input_image_checkbox", originalImage.checked).catch(() => {});
  }
}

async function enhanceMaskFirstSyncStep(page) {
  await switchPreset(page, config.enhancePresetSelector, "enhance preset");
  const originalImage = await checkboxState(page, "input_image_checkbox");
  const originalAdvanced = await checkboxState(page, "advanced_checkbox");

  try {
    await setCheckbox(page, "input_image_checkbox", true);
    await setCheckbox(page, "advanced_checkbox", true);
    try {
      await activateImageInputTab(page, "enhance");
    } catch (error) {
      throw new SmokeSkip(`enhance tab unavailable in current preset: ${error.message}`);
    }
    const regionReady = await activateEnhanceRegionOne(page);
    if (!regionReady.ok) {
      throw new SmokeSkip("enhance region#1 unavailable in current preset");
    }
    const detectionReady = await openEnhanceDetectionAccordion(page);
    if (!detectionReady.ok) {
      throw new SmokeSkip(`enhance detection accordion unavailable in current preset: ${JSON.stringify(detectionReady)}`);
    }

    const root = await mountedSelfState(page, SELECTORS.enhanceMaskModel1);
    if (!root.exists) {
      throw new SmokeSkip(`${SELECTORS.enhanceMaskModel1} unavailable in current preset`);
    }

    const model = await page.evaluate(() => {
      const normalize = (value) => String(value || "").trim().toLowerCase();
      const explicit = window.SimpAIDefaultEnhanceMaskModel;
      if (explicit) return normalize(explicit);
      const root = document.getElementById("enhance_mask_model_1");
      const input = root ? root.querySelector("input, textarea") : null;
      return normalize(input ? input.value : root?.textContent || "");
    });

    await page.evaluate(() => {
      window.syncEnhanceMaskControlsVisibility?.();
    });
    await waitForUiSettle(page, 700);

    if (model === "sam") {
      await assertMountedSelfShown(page, SELECTORS.enhanceMaskDinoPrompt1);
      await assertMountedSelfShown(page, SELECTORS.enhanceMaskSamOptions1);
      await assertMountedSelfShown(page, SELECTORS.exampleEnhanceMaskDinoPrompt1);
      await assertMountedSelfHidden(page, SELECTORS.enhanceMaskClothCategory1);
    } else if (model === "u2net_cloth_seg") {
      await assertMountedSelfShown(page, SELECTORS.enhanceMaskClothCategory1);
      await assertMountedSelfHidden(page, SELECTORS.enhanceMaskDinoPrompt1);
      await assertMountedSelfHidden(page, SELECTORS.enhanceMaskSamOptions1);
      await assertMountedSelfHidden(page, SELECTORS.exampleEnhanceMaskDinoPrompt1);
    } else {
      await assertMountedSelfHidden(page, SELECTORS.enhanceMaskClothCategory1);
      await assertMountedSelfHidden(page, SELECTORS.enhanceMaskDinoPrompt1);
      await assertMountedSelfHidden(page, SELECTORS.enhanceMaskSamOptions1);
      await assertMountedSelfHidden(page, SELECTORS.exampleEnhanceMaskDinoPrompt1);
    }
    return `enhance mask region#1 sync model=${model || "unknown"}`;
  } finally {
    if (originalAdvanced.exists) await setCheckbox(page, "advanced_checkbox", originalAdvanced.checked).catch(() => {});
    if (originalImage.exists) await setCheckbox(page, "input_image_checkbox", originalImage.checked).catch(() => {});
  }
}

async function measureStatusMonitorModelBrowserObstruction(page) {
  return await page.evaluate((selectors) => {
    const monitor = document.querySelector(selectors.statusMonitor);
    const dropdown = document.querySelector(selectors.baseModelDropdown);
    const button = document.querySelector(selectors.baseModelBrowserButton);
    const rectData = (el) => {
      if (!el) return null;
      const rect = el.getBoundingClientRect();
      const style = window.getComputedStyle ? window.getComputedStyle(el) : null;
      return {
        left: rect.left,
        top: rect.top,
        right: rect.right,
        bottom: rect.bottom,
        width: rect.width,
        height: rect.height,
        visible: rect.width > 0 && rect.height > 0 && (!style || (style.display !== "none" && style.visibility !== "hidden")),
        pointerEvents: style ? style.pointerEvents : "",
        zIndex: style ? style.zIndex : "",
      };
    };

    const monitorRect = rectData(monitor);
    const dropdownRect = rectData(dropdown);
    const buttonRect = rectData(button);
    const overlap = (a, b) => {
      if (!a || !b) return { width: 0, height: 0, area: 0 };
      const width = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left));
      const height = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
      return { width, height, area: width * height };
    };

    let centerHit = null;
    let buttonReceivesPointer = false;
    let statusMonitorAtButtonCenter = false;
    if (buttonRect) {
      const x = buttonRect.left + buttonRect.width / 2;
      const y = buttonRect.top + buttonRect.height / 2;
      const stack = typeof document.elementsFromPoint === "function"
        ? document.elementsFromPoint(x, y)
        : [document.elementFromPoint(x, y)].filter(Boolean);
      const top = stack[0] || null;
      centerHit = top ? {
        tagName: top.tagName,
        id: top.id || "",
        className: typeof top.className === "string" ? top.className : "",
      } : null;
      buttonReceivesPointer = !!(button && top && button.contains(top));
      statusMonitorAtButtonCenter = stack.some((el) => !!(monitor && monitor.contains(el)));
    }

    return {
      monitorExists: !!monitor,
      dropdownExists: !!dropdown,
      buttonExists: !!button,
      monitorRect,
      dropdownRect,
      buttonRect,
      monitorButtonOverlap: overlap(monitorRect, buttonRect),
      monitorDropdownOverlap: overlap(monitorRect, dropdownRect),
      centerHit,
      buttonReceivesPointer,
      statusMonitorAtButtonCenter,
      htmlClassName: document.documentElement.className || "",
    };
  }, SELECTORS);
}

async function closeSharedModelBrowser(page) {
  await page.evaluate(() => {
    if (window.SimpAIModelBrowser && typeof window.SimpAIModelBrowser.close === "function") {
      window.SimpAIModelBrowser.close();
      return true;
    }
    const closeButton = document.querySelector(".sai-model-browser-v2 [data-smb-close]");
    if (closeButton) {
      closeButton.click();
      return true;
    }
    return false;
  });
  await page.locator(`${SELECTORS.modelBrowserDialog}.is-open`).first().waitFor({ state: "hidden", timeout: config.timeoutMs }).catch(() => {});
  await page.waitForTimeout(250);
}

async function measureSharedModelBrowserScrollContainment(page) {
  const headBox = await page.locator(`${SELECTORS.modelBrowserDialog}.is-open .sai-model-browser-head`).first().boundingBox().catch(() => null);
  const gridBox = await page.locator(`${SELECTORS.modelBrowserDialog}.is-open .sai-model-browser-grid`).first().boundingBox().catch(() => null);
  const initial = await page.evaluate(() => {
    const scroller = document.scrollingElement || document.documentElement;
    const maxY = Math.max(0, scroller.scrollHeight - window.innerHeight);
    window.scrollTo(0, Math.min(180, maxY));
    return { scrollY: window.scrollY, maxY };
  });
  await page.waitForTimeout(80);
  const beforeY = await page.evaluate(() => window.scrollY);

  if (headBox) {
    await page.mouse.move(headBox.left + Math.min(80, Math.max(1, headBox.width / 2)), headBox.top + Math.max(1, headBox.height / 2));
    await page.mouse.wheel(0, 700);
    await page.waitForTimeout(120);
  }
  const afterHeadY = await page.evaluate(() => window.scrollY);
  const gridBefore = await page.evaluate((selector) => {
    const grid = document.querySelector(`${selector}.is-open .sai-model-browser-grid`);
    return {
      exists: !!grid,
      scrollTop: grid?.scrollTop || 0,
      scrollHeight: grid?.scrollHeight || 0,
      clientHeight: grid?.clientHeight || 0,
    };
  }, SELECTORS.modelBrowserDialog);

  if (gridBox) {
    await page.mouse.move(gridBox.left + Math.max(1, gridBox.width / 2), gridBox.top + Math.max(1, gridBox.height / 2));
    await page.mouse.wheel(0, 700);
    await page.waitForTimeout(120);
  }
  const afterGridY = await page.evaluate(() => window.scrollY);
  const gridAfter = await page.evaluate((selector) => {
    const grid = document.querySelector(`${selector}.is-open .sai-model-browser-grid`);
    return {
      exists: !!grid,
      scrollTop: grid?.scrollTop || 0,
      scrollHeight: grid?.scrollHeight || 0,
      clientHeight: grid?.clientHeight || 0,
    };
  }, SELECTORS.modelBrowserDialog);
  return {
    initialY: initial.scrollY,
    beforeY,
    maxY: initial.maxY,
    afterHeadY,
    afterGridY,
    headerDelta: afterHeadY - beforeY,
    gridDelta: afterGridY - afterHeadY,
    gridScrollable: gridBefore.scrollHeight > gridBefore.clientHeight + 2,
    gridBefore,
    gridAfter,
  };
}

async function statusMonitorModelBrowserStep(page) {
  await switchPreset(page, config.basePresetSelector, "base preset");
  await waitForPresetGallerySuppressionClear(page).catch(() => {});
  await activateTopLevelTab(page, ["Models", "模型"]);
  await page.locator(SELECTORS.statusMonitor).first().waitFor({ state: "attached", timeout: config.timeoutMs });
  await page.locator(SELECTORS.baseModelBrowserButton).first().waitFor({ state: "visible", timeout: config.timeoutMs });
  await waitForUiSettle(page, 500);

  const obstruction = await measureStatusMonitorModelBrowserObstruction(page);
  assertCondition(obstruction.monitorExists, `${SELECTORS.statusMonitor} does not exist`);
  assertCondition(obstruction.dropdownExists, `${SELECTORS.baseModelDropdown} does not exist`);
  assertCondition(obstruction.buttonExists, `${SELECTORS.baseModelBrowserButton} does not exist`);
  assertCondition(obstruction.monitorRect?.visible, `${SELECTORS.statusMonitor} should be visible on desktop smoke viewport`);
  assertCondition(obstruction.buttonRect?.visible, `${SELECTORS.baseModelBrowserButton} should be visible`);
  assertCondition(
    obstruction.monitorButtonOverlap.area === 0,
    `status monitor overlaps model browser button; ${JSON.stringify(obstruction)}`,
  );
  assertCondition(
    obstruction.buttonReceivesPointer && !obstruction.statusMonitorAtButtonCenter,
    `model browser button center is obstructed; ${JSON.stringify(obstruction)}`,
  );

  await page.locator(SELECTORS.baseModelBrowserButton).first().click({ timeout: config.timeoutMs });
  await page.locator(`${SELECTORS.modelBrowserDialog}.is-open`).first().waitFor({ state: "visible", timeout: config.timeoutMs });
  const scrollContainment = await measureSharedModelBrowserScrollContainment(page);
  assertCondition(Math.abs(scrollContainment.headerDelta) <= 1, `model browser header wheel leaked to page scroll; ${JSON.stringify(scrollContainment)}`);
  assertCondition(Math.abs(scrollContainment.gridDelta) <= 1, `model browser grid wheel leaked to page scroll; ${JSON.stringify(scrollContainment)}`);
  if (scrollContainment.gridScrollable) {
    assertCondition(scrollContainment.gridAfter.scrollTop > scrollContainment.gridBefore.scrollTop, `model browser grid did not keep internal wheel scroll; ${JSON.stringify(scrollContainment)}`);
  }
  await closeSharedModelBrowser(page);

  return `monitor=${Math.round(obstruction.monitorRect.width)}x${Math.round(obstruction.monitorRect.height)} button=${Math.round(obstruction.buttonRect.width)}x${Math.round(obstruction.buttonRect.height)} scrollLeak=${scrollContainment.headerDelta}/${scrollContainment.gridDelta}`;
}

async function readModelsPanelCatalogState(page) {
  return await page.evaluate(async (selectors) => {
    const select = document.querySelector(selectors.baseModelDropdown);
    if (!select) return { selectExists: false };
    if (typeof window.simpleaiRefreshModelsJsPanelCatalog === "function") {
      await window.simpleaiRefreshModelsJsPanelCatalog();
    }
    if (typeof window.simpleaiPopulateModelsJsSelect === "function") {
      window.simpleaiPopulateModelsJsSelect(select);
    }
    const params = window.simpleaiTopbarSystemParams || {};
    const catalog = params.__canvas_model_catalog || {};
    const options = Array.from(select.options || []).map((option) => option.value);
    const catalogModels = Array.isArray(catalog.model_filenames) ? catalog.model_filenames : [];
    const currentValue = String(select.value || "");
    const unexpectedOptions = options.filter((value) => value !== currentValue && !catalogModels.includes(value));
    const previewCandidate = options.find((value) => catalogModels.includes(value) && value && value.toLowerCase() !== "none")
      || options.find((value) => value && value.toLowerCase() !== "none")
      || currentValue;
    if (previewCandidate) {
      select.value = previewCandidate;
      select.dispatchEvent(new Event("input", { bubbles: true }));
    }
    return {
      selectExists: true,
      preset: params.__preset || "",
      backend: String(params.__backend_engine || params.backend_engine || params.engine || params.task_class_name || ""),
      taskMethod: String(params.task_method || params.__scene_task_method || ""),
      catalogEngine: String(catalog.engine || catalog.backend_engine || catalog.__backend_engine || ""),
      catalogTaskMethod: String(catalog.task_method || catalog.__scene_task_method || ""),
      catalogSignature: String(catalog.__simpai_signature_key || ""),
      optionCount: options.length,
      catalogCount: catalogModels.length,
      unexpectedOptions,
      previewCandidate,
    };
  }, SELECTORS);
}

async function hoverModelsPanelSelectPreview(page) {
  return await page.evaluate(async (selectors) => {
    const select = document.querySelector(selectors.baseModelDropdown);
    if (!select) return { selectExists: false };
    if (typeof window.simpleaiRefreshModelsJsPanelCatalog === "function") {
      await window.simpleaiRefreshModelsJsPanelCatalog();
    }
    if (typeof window.simpleaiPopulateModelsJsSelect === "function") {
      window.simpleaiPopulateModelsJsSelect(select);
    }
    if (typeof window.simpleaiOpenModelsJsSelectMenu === "function") {
      window.simpleaiOpenModelsJsSelectMenu(select);
    } else {
      select.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, cancelable: true }));
    }
    await new Promise((resolve) => setTimeout(resolve, 80));
    const menu = document.querySelector(".simpai-models-js-select-menu");
    const catalog = window.simpleaiTopbarSystemParams?.__canvas_model_catalog || {};
    const catalogModels = Array.isArray(catalog.model_filenames) ? catalog.model_filenames : [];
    const options = Array.from(menu?.querySelectorAll(".simpai-models-js-select-option") || []);
    const option = options.find((node) => {
      const value = String(node.dataset.simpaiSelectOptionValue || node.textContent || "").trim();
      return catalogModels.includes(value) && value && value.toLowerCase() !== "none";
    }) || options.find((node) => String(node.dataset.simpaiSelectOptionValue || node.textContent || "").trim().toLowerCase() !== "none");
    if (option) {
      option.dispatchEvent(new PointerEvent("pointerover", { bubbles: true, clientX: 24, clientY: 24 }));
      option.dispatchEvent(new MouseEvent("mouseover", { bubbles: true, clientX: 24, clientY: 24 }));
    }
    const menuRect = menu?.getBoundingClientRect();
    const selectRect = select.getBoundingClientRect();
    const preview = document.querySelector(".model-preview-tooltip");
    return {
      selectExists: true,
      menuExists: !!menu,
      optionCount: options.length,
      hoverValue: String(option?.dataset.simpaiSelectOptionValue || option?.textContent || "").trim(),
      selectWidth: selectRect.width,
      menuWidth: menuRect?.width || 0,
      menuZIndex: menu ? Number.parseInt(window.getComputedStyle(menu).zIndex, 10) : 0,
      previewZIndex: preview ? Number.parseInt(window.getComputedStyle(preview).zIndex, 10) : 0,
    };
  }, SELECTORS);
}

async function readModelsPanelStabilityState(page) {
  return await page.evaluate(async () => {
    const root = document.querySelector("[data-simpai-models-js-root]");
    if (!root) return { panelExists: false };
    const activeLang = (() => {
      try {
        const search = new URLSearchParams(window.location.search || "");
        const candidates = [
          search.get("__lang"),
          search.get("lang"),
          search.get("language"),
          window.locale_lang,
          localStorage.getItem("ailang"),
          window.simpleaiTopbarSystemParams?.__lang,
        ];
        const raw = candidates.map((value) => String(value || "").trim().toLowerCase()).find(Boolean) || "cn";
        return raw.startsWith("en") ? "en" : "cn";
      } catch (err) {
        return "cn";
      }
    })();
    const expectedBaseLabel = activeLang === "en" ? "Base Model" : "基础模型";
    const labelTexts = () => Array.from(root.querySelectorAll("[data-simpai-i18n-en]")).slice(0, 8).map((node) => node.textContent.trim());
    window.__simpaiSmokeModelsPanelRoot = root;
    window.__simpaiSmokeModelsPanelRemoved = 0;
    window.__simpaiSmokeModelsPanelObserver?.disconnect?.();
    window.__simpaiSmokeModelsPanelObserver = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        for (const node of mutation.removedNodes || []) {
          if (node === window.__simpaiSmokeModelsPanelRoot || node.querySelector?.("[data-simpai-models-js-root]")) {
            window.__simpaiSmokeModelsPanelRemoved += 1;
          }
        }
      }
    });
    window.__simpaiSmokeModelsPanelObserver.observe(document.body, { childList: true, subtree: true });
    const beforeLabels = labelTexts();
    const refiner = root.querySelector('[data-simpai-model-card="refiner"]');
    const refinerSwitch = root.querySelector('[data-simpai-model-card="refiner_switch"]');
    const weight = root.querySelector("[data-simpai-lora-weight]");
    const range = weight ? root.querySelector(`[data-simpai-lora-weight-range="${weight.dataset.simpaiLoraWeight}"]`) : null;
    const loraCheckboxes = Array.from(root.querySelectorAll("[data-simpai-lora-enabled]"));
    const beforeRefinerOpacity = refiner ? getComputedStyle(refiner).opacity : "";
    const beforeSwitchOpacity = refinerSwitch ? getComputedStyle(refinerSwitch).opacity : "";
    const nextWeight = String(Math.round(((Number(weight?.value) || 1) + 0.05) * 100) / 100);
    if (weight) {
      weight.value = nextWeight;
      weight.dispatchEvent(new Event("input", { bubbles: true }));
      weight.dispatchEvent(new Event("change", { bubbles: true }));
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
    const currentRoot = document.querySelector("[data-simpai-models-js-root]");
    const afterLabels = labelTexts();
    const footer = document.querySelector(".models_panel_footer_row");
    const footerShell = footer?.closest(".models_panel_footer_shell, .gr-group");
    const footerStyler = footerShell?.querySelector?.(":scope > .styler");
    const rect = (node) => {
      if (!node) return null;
      const box = node.getBoundingClientRect();
      return { top: box.top, bottom: box.bottom, width: box.width, height: box.height };
    };
    const footerRect = rect(footer);
    const shellRect = rect(footerShell);
    const stylerRect = rect(footerStyler);
    const nonFooterRows = footerStyler
      ? Array.from(footerStyler.children).filter((node) => node.classList?.contains("row") && !node.classList.contains("models_panel_footer_row"))
      : [];
    return {
      panelExists: true,
      activeLang,
      expectedBaseLabel,
      beforeLabels,
      afterLabels,
      sameRoot: currentRoot === window.__simpaiSmokeModelsPanelRoot,
      removedCount: window.__simpaiSmokeModelsPanelRemoved || 0,
      nextWeight,
      weightValue: weight ? String(weight.value) : "",
      rangeValue: range ? String(range.value) : "",
      beforeRefinerOpacity,
      afterRefinerOpacity: refiner ? getComputedStyle(refiner).opacity : "",
      beforeSwitchOpacity,
      afterSwitchOpacity: refinerSwitch ? getComputedStyle(refinerSwitch).opacity : "",
      footerShellTopGap: footerRect && shellRect ? footerRect.top - shellRect.top : null,
      footerShellBottomGap: footerRect && shellRect ? shellRect.bottom - footerRect.bottom : null,
      footerStylerTopGap: footerRect && stylerRect ? footerRect.top - stylerRect.top : null,
      footerStylerBottomGap: footerRect && stylerRect ? stylerRect.bottom - footerRect.bottom : null,
      footerHeight: footerRect?.height || 0,
      visibleFooterBridgeRows: nonFooterRows.filter((node) => getComputedStyle(node).display !== "none").length,
      loraCheckboxCount: loraCheckboxes.length,
      loraCheckedCount: loraCheckboxes.filter((node) => node.checked).length,
    };
  });
}

async function modelsPanelCatalogAndPreviewStep(page) {
  await switchPreset(page, config.basePresetSelector, "base preset");
  await waitForPresetGallerySuppressionClear(page).catch(() => {});
  await activateTopLevelTab(page, ["Models", "模型"]);
  await page.locator(SELECTORS.baseModelDropdown).first().waitFor({ state: "visible", timeout: config.timeoutMs });
  const baseState = await readModelsPanelCatalogState(page);
  assertCondition(baseState.selectExists, `${SELECTORS.baseModelDropdown} does not exist`);
  assertCondition(baseState.catalogEngine === baseState.backend, `base catalog backend mismatch; ${JSON.stringify(baseState)}`);
  assertCondition(baseState.catalogTaskMethod === baseState.taskMethod, `base catalog task mismatch; ${JSON.stringify(baseState)}`);
  assertCondition(baseState.optionCount > 1, `base model select did not populate; ${JSON.stringify(baseState)}`);
  assertCondition(baseState.unexpectedOptions.length === 0, `base model select contains stale options; ${JSON.stringify(baseState)}`);

  await page.locator(`${SELECTORS.modelPreviewTooltip} img`).first().waitFor({ state: "visible", timeout: config.timeoutMs });
  const baseHoverPreview = await hoverModelsPanelSelectPreview(page);
  assertCondition(baseHoverPreview.menuExists && baseHoverPreview.optionCount > 1, `base model custom menu did not open; ${JSON.stringify(baseHoverPreview)}`);
  assertCondition(!!baseHoverPreview.hoverValue, `base model custom menu did not expose a hover value; ${JSON.stringify(baseHoverPreview)}`);
  assertCondition(baseHoverPreview.menuWidth >= baseHoverPreview.selectWidth && baseHoverPreview.menuWidth <= 560, `base model custom menu width is not compact; ${JSON.stringify(baseHoverPreview)}`);
  assertCondition(baseHoverPreview.previewZIndex > baseHoverPreview.menuZIndex, `base model preview tooltip is not above custom menu; ${JSON.stringify(baseHoverPreview)}`);
  await page.locator(`${SELECTORS.modelPreviewTooltip} img`).first().waitFor({ state: "visible", timeout: config.timeoutMs });

  await switchPreset(page, config.altPresetSelector, "alt preset");
  await waitForPresetGallerySuppressionClear(page).catch(() => {});
  await activateTopLevelTab(page, ["Models", "模型"]);
  await page.locator(SELECTORS.baseModelDropdown).first().waitFor({ state: "visible", timeout: config.timeoutMs });
  const altState = await readModelsPanelCatalogState(page);
  assertCondition(altState.catalogEngine === altState.backend, `alt catalog backend mismatch; ${JSON.stringify(altState)}`);
  assertCondition(altState.catalogTaskMethod === altState.taskMethod, `alt catalog task mismatch; ${JSON.stringify(altState)}`);
  assertCondition(altState.optionCount > 1, `alt model select did not populate; ${JSON.stringify(altState)}`);
  assertCondition(altState.unexpectedOptions.length === 0, `alt model select contains stale options; ${JSON.stringify(altState)}`);
  if (baseState.backend !== altState.backend || baseState.taskMethod !== altState.taskMethod) {
    assertCondition(baseState.catalogSignature !== altState.catalogSignature, `catalog signature did not change after backend switch; base=${JSON.stringify(baseState)} alt=${JSON.stringify(altState)}`);
  }

  await page.locator(`${SELECTORS.modelPreviewTooltip} img`).first().waitFor({ state: "visible", timeout: config.timeoutMs });
  const altHoverPreview = await hoverModelsPanelSelectPreview(page);
  assertCondition(altHoverPreview.menuExists && altHoverPreview.optionCount > 1, `alt model custom menu did not open; ${JSON.stringify(altHoverPreview)}`);
  assertCondition(!!altHoverPreview.hoverValue, `alt model custom menu did not expose a hover value; ${JSON.stringify(altHoverPreview)}`);
  assertCondition(altHoverPreview.menuWidth >= altHoverPreview.selectWidth && altHoverPreview.menuWidth <= 560, `alt model custom menu width is not compact; ${JSON.stringify(altHoverPreview)}`);
  assertCondition(altHoverPreview.previewZIndex > altHoverPreview.menuZIndex, `alt model preview tooltip is not above custom menu; ${JSON.stringify(altHoverPreview)}`);
  await page.locator(`${SELECTORS.modelPreviewTooltip} img`).first().waitFor({ state: "visible", timeout: config.timeoutMs });
  const stability = await readModelsPanelStabilityState(page);
  assertCondition(stability.panelExists, "models panel root does not exist for stability smoke");
  assertCondition(stability.beforeLabels[0] === stability.expectedBaseLabel, `models panel language mismatch before edit; ${JSON.stringify(stability)}`);
  assertCondition(stability.afterLabels[0] === stability.expectedBaseLabel, `models panel language mismatch after edit; ${JSON.stringify(stability)}`);
  assertCondition(stability.sameRoot && stability.removedCount === 0, `models panel was re-rendered by value edit; ${JSON.stringify(stability)}`);
  assertCondition(stability.weightValue === stability.nextWeight && stability.rangeValue === stability.nextWeight, `models panel weight input/range did not stay synced; ${JSON.stringify(stability)}`);
  assertCondition(stability.beforeRefinerOpacity === stability.afterRefinerOpacity && stability.beforeSwitchOpacity === stability.afterSwitchOpacity, `models panel disabled state flickered after edit; ${JSON.stringify(stability)}`);
  assertCondition(Math.abs(stability.footerShellTopGap) <= 1 && Math.abs(stability.footerShellBottomGap) <= 1 && Math.abs(stability.footerStylerTopGap) <= 1 && Math.abs(stability.footerStylerBottomGap) <= 1, `models panel footer shell has visible padding; ${JSON.stringify(stability)}`);
  assertCondition(stability.visibleFooterBridgeRows === 0, `models panel hidden bridge rows are still visible; ${JSON.stringify(stability)}`);
  assertCondition(stability.loraCheckboxCount > 0 && stability.loraCheckedCount === stability.loraCheckboxCount, `models panel lora checkboxes were not restored checked after preset switch; ${JSON.stringify(stability)}`);
  return `base=${baseState.backend}/${baseState.optionCount} alt=${altState.backend}/${altState.optionCount} hover=${altHoverPreview.hoverValue} lang=${stability.activeLang}`;
}

async function main() {
  const { chromium } = await loadPlaywright();
  const launchOptions = {
    headless: config.headless,
    slowMo: config.slowMo,
  };
  if (config.playwrightChannel) launchOptions.channel = config.playwrightChannel;

  let browser;
  let page;
  try {
    browser = await chromium.launch(launchOptions);
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    page = await context.newPage();
    page.setDefaultTimeout(config.timeoutMs);

    await runStep(page, "load WebUI", async () => {
      await gotoWebUi(page);
      return config.baseUrl;
    });
    await runStep(page, "initial visibility roots", () => initialStateStep(page));
    await runStep(page, "refresh keeps page at top", () => refreshScrollStep(page));
    await runStep(page, "finished catalog closes on preset switch", () => galleryPresetSwitchStep(page));
    await runStep(page, "first history gallery open keeps welcome until media renders", () => galleryFirstOpenTimingStep(page));
    await runStep(page, "gallery media switch status syncs without refresh", () => galleryMediaSwitchStatusStep(page));
    await runStep(page, "gallery regen restores parameters without errors", () => galleryRegenButtonStep(page));
    await runStep(page, "preset store toggles without identity dialog churn", () => presetStoreToggleStep(page));
    await runStep(page, "scene/SAM3 hides after preset switch", () => sceneSwitchStep(page));
    await runStep(page, "continuous preset switch suppresses scene flash", () => continuousPresetSwitchStep(page));
    await runStep(page, "TTP scene preset restores var number", () => ttpScenePresetParameterStep(page));
    await runStep(page, "preset switch restores advanced params and lora checks", () => presetAdvancedParamsRestoreStep(page));
    await runStep(page, "status monitor does not cover model browser button", () => statusMonitorModelBrowserStep(page));
    await runStep(page, "models panel catalog follows backend and preview works", () => modelsPanelCatalogAndPreviewStep(page));
    await runStep(page, "image/TTS/advanced toggles do not leave blank rows", () => togglePanelsStep(page));
    await runStep(page, "inpaint first mode switch shows mounted prompt controls", () => inpaintModeFirstSwitchStep(page));
    await runStep(page, "enhance mask controls sync without fallback delay", () => enhanceMaskFirstSyncStep(page));

    console.log(JSON.stringify({ ok: true, results }, null, 2));
  } catch (error) {
    if (error && /Executable doesn't exist|browserType.launch/i.test(error.message || "")) {
      console.error("Playwright could not launch Chromium.");
      console.error("Run: npx playwright install chromium");
      console.error("Or set SIMPAI_PLAYWRIGHT_CHANNEL=chrome to use an installed Chrome channel.");
    }
    console.log(JSON.stringify({ ok: false, results }, null, 2));
    process.exitCode = 1;
  } finally {
    if (browser) await browser.close().catch(() => {});
  }
}

await main();
