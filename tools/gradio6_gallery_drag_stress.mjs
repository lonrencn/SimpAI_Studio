#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";

const DEFAULT_URL = "http://127.0.0.1:8190/?__theme=dark";
const DEFAULT_SELECTOR = [
  "#finished_gallery img",
  "#final_gallery img",
  "#preview_generating img",
  "#simpleai_gallery_welcome_guard_placeholder img",
].join(", ");
const CUSTOM_ORIGINAL_URL_TYPE = "application/x-simpleai-gallery-original-url";

function parseArgs(argv) {
  const config = {
    url: process.env.SIMPAI_GALLERY_DRAG_STRESS_URL || DEFAULT_URL,
    selector: process.env.SIMPAI_GALLERY_DRAG_STRESS_SELECTOR || DEFAULT_SELECTOR,
    iterations: Number(process.env.SIMPAI_GALLERY_DRAG_STRESS_ITERATIONS || 20),
    waitMs: Number(process.env.SIMPAI_GALLERY_DRAG_STRESS_WAIT_MS || 2500),
    caseTimeoutMs: Number(process.env.SIMPAI_GALLERY_DRAG_STRESS_CASE_TIMEOUT_MS || 3500),
    live: process.env.SIMPAI_GALLERY_DRAG_STRESS_LIVE === "1",
    headful: process.env.SIMPAI_GALLERY_DRAG_STRESS_HEADFUL === "1",
    playwrightChannel: process.env.SIMPAI_PLAYWRIGHT_CHANNEL || "",
    out: process.env.SIMPAI_GALLERY_DRAG_STRESS_OUT || "",
    selfTest: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = () => argv[++i];
    if (arg === "--url") config.url = next();
    else if (arg === "--selector") config.selector = next();
    else if (arg === "--iterations") config.iterations = Number(next());
    else if (arg === "--wait-ms") config.waitMs = Number(next());
    else if (arg === "--case-timeout-ms") config.caseTimeoutMs = Number(next());
    else if (arg === "--out") config.out = next();
    else if (arg === "--live") config.live = true;
    else if (arg === "--headful") config.headful = true;
    else if (arg === "--channel") config.playwrightChannel = next();
    else if (arg === "--self-test") config.selfTest = true;
    else if (arg === "--help" || arg === "-h") {
      printHelp();
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  if (!Number.isFinite(config.iterations) || config.iterations < 1) config.iterations = 1;
  if (!Number.isFinite(config.waitMs) || config.waitMs < 0) config.waitMs = 0;
  if (!Number.isFinite(config.caseTimeoutMs) || config.caseTimeoutMs < 500) config.caseTimeoutMs = 500;
  return config;
}

function printHelp() {
  console.log(`Usage:
  node tools/gradio6_gallery_drag_stress.mjs --url http://127.0.0.1:8190/?__theme=dark

Options:
  --url <url>                Target SimpAI page. Default: ${DEFAULT_URL}
  --iterations <n>           Synthetic drag rounds per image. Default: 20
  --live                     Also perform real mouse drag smoke in an isolated Chromium
  --headful                  Show the isolated Chromium window
  --wait-ms <n>              Wait after page load before collecting images. Default: 2500
  --case-timeout-ms <n>      Timeout for each live drag responsiveness check. Default: 3500
  --selector <css>           Image selector to stress
  --out <path>               Write JSON report
  --channel <name>           Playwright channel, e.g. chrome
  --self-test                Validate script contracts without launching browser
`);
}

async function loadPlaywright() {
  try {
    return await import("playwright");
  } catch (err) {
    throw new Error([
      "Playwright is required for gallery drag stress.",
      "Install locally with: npm install --no-save playwright",
      "If Chromium is missing, run: npx playwright install chromium",
      err?.message || String(err),
    ].join("\n"));
  }
}

function makeReport(config) {
  return {
    ok: true,
    tool: "gradio6_gallery_drag_stress",
    startedAt: new Date().toISOString(),
    config,
    summary: {
      candidates: 0,
      syntheticRuns: 0,
      liveRuns: 0,
      failures: 0,
      warnings: 0,
    },
    candidates: [],
    synthetic: [],
    live: [],
    failures: [],
    warnings: [],
    consoleErrors: [],
  };
}

function pushFailure(report, code, message, detail = {}) {
  report.ok = false;
  report.summary.failures += 1;
  report.failures.push({ code, message, detail });
}

function pushWarning(report, code, message, detail = {}) {
  report.summary.warnings += 1;
  report.warnings.push({ code, message, detail });
}

async function withTimeout(promise, timeoutMs, label) {
  let timer = null;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`${label} timed out after ${timeoutMs}ms`)), timeoutMs);
  });
  try {
    return await Promise.race([promise, timeout]);
  } finally {
    clearTimeout(timer);
  }
}

async function collectCandidates(page, selector) {
  return await page.evaluate((sel) => {
    function mediaSrc(elem) {
      return elem?.currentSrc || elem?.src || elem?.getAttribute?.("src") || "";
    }
    function displayPreviewOriginalSrc(src) {
      const value = String(src || "");
      if (!value) return "";
      try {
        const url = new URL(value, document.baseURI || location.href);
        const fileName = decodeURIComponent(url.pathname.split("/").filter(Boolean).pop() || "");
        const match = fileName.match(/^simpai_gprev__([A-Za-z0-9_-]+)__[0-9a-f]{16}\.jpg$/);
        if (!match) return "";
        return match[1] || "";
      } catch {
        return "";
      }
    }
    function expectedManaged(img) {
      const naturalWidth = Number(img?.naturalWidth || 0);
      const naturalHeight = Number(img?.naturalHeight || 0);
      const large = !!naturalWidth && !!naturalHeight && (
        naturalWidth * naturalHeight >= 2000000 || Math.max(naturalWidth, naturalHeight) >= 2048
      );
      return !!displayPreviewOriginalSrc(mediaSrc(img)) || !!img.closest?.("#preview_generating") || large;
    }
    return Array.from(document.querySelectorAll(sel)).map((img, index) => {
      const rect = img.getBoundingClientRect();
      const source = img.closest?.(".thumbnail-item, .gallery-item, .image-container, .image-frame, .preview, button") || img.parentElement;
      return {
        index,
        src: mediaSrc(img),
        naturalWidth: img.naturalWidth || 0,
        naturalHeight: img.naturalHeight || 0,
        rect: {
          x: Math.round(rect.x),
          y: Math.round(rect.y),
          width: Math.round(rect.width),
          height: Math.round(rect.height),
        },
        visible: rect.width > 0 && rect.height > 0,
        imgDraggable: !!img.draggable,
        sourceTag: source?.tagName || "",
        sourceClass: source?.className || "",
        sourceDraggable: !!source?.draggable,
        sourceMarked: source?.dataset?.simpleaiManagedNativeImageDragSource === "1",
        inPreview: !!img.closest?.("#preview_generating"),
        inGallery: !!img.closest?.("#finished_gallery, #final_gallery"),
        expectedManaged: expectedManaged(img),
      };
    });
  }, selector);
}

async function runSyntheticStress(page, config, report) {
  const result = await page.evaluate(({ selector, iterations, customType }) => {
    function mediaSrc(elem) {
      return elem?.currentSrc || elem?.src || elem?.getAttribute?.("src") || "";
    }
    function sourceFromImage(img) {
      return img?.closest?.(".thumbnail-item, .gallery-item, .image-container, .image-frame, .preview, button") || img?.parentElement || null;
    }
    function displayPreviewOriginalSrc(src) {
      const value = String(src || "");
      if (!value) return "";
      try {
        const url = new URL(value, document.baseURI || location.href);
        const fileName = decodeURIComponent(url.pathname.split("/").filter(Boolean).pop() || "");
        const match = fileName.match(/^simpai_gprev__([A-Za-z0-9_-]+)__[0-9a-f]{16}\.jpg$/);
        if (!match) return "";
        return match[1] || "";
      } catch {
        return "";
      }
    }
    function expectedManaged(img) {
      const naturalWidth = Number(img?.naturalWidth || 0);
      const naturalHeight = Number(img?.naturalHeight || 0);
      const large = !!naturalWidth && !!naturalHeight && (
        naturalWidth * naturalHeight >= 2000000 || Math.max(naturalWidth, naturalHeight) >= 2048
      );
      return !!displayPreviewOriginalSrc(mediaSrc(img)) || !!img.closest?.("#preview_generating") || large;
    }
    function dispatchMouse(type, target) {
      const event = new MouseEvent(type, { bubbles: true, cancelable: true, button: 0, buttons: type === "mouseup" ? 0 : 1 });
      target.dispatchEvent(event);
      return event;
    }
    function dispatchDrag(type, target, dataTransfer) {
      const event = new DragEvent(type, { bubbles: true, cancelable: true, dataTransfer });
      target.dispatchEvent(event);
      return event;
    }
    const failures = [];
    const warnings = [];
    const runs = [];
    const images = Array.from(document.querySelectorAll(selector));
    for (let round = 0; round < iterations; round += 1) {
      for (let index = 0; index < images.length; index += 1) {
        const img = images[index];
        const source = sourceFromImage(img);
        if (!img?.isConnected || !source?.isConnected) continue;
        const managed = expectedManaged(img);
        dispatchMouse("pointerover", img);
        dispatchMouse("mousedown", img);
        const dragTarget = source?.dataset?.simpleaiManagedNativeImageDragSource === "1" ? source : img;
        const dataTransfer = new DataTransfer();
        const startEvent = dispatchDrag("dragstart", dragTarget, dataTransfer);
        const types = Array.from(dataTransfer.types || []);
        const customUrl = dataTransfer.getData(customType);
        const uri = dataTransfer.getData("text/uri-list");
        const plain = dataTransfer.getData("text/plain");
        const downloadUrl = dataTransfer.getData("DownloadURL");
        const after = {
          imgDraggable: !!img.draggable,
          imgMarked: img.dataset?.simpleaiManagedNativeImageDragImage === "1",
          sourceDraggable: !!source.draggable,
          sourceMarked: source.dataset?.simpleaiManagedNativeImageDragSource === "1",
        };
        if (managed) {
          if (!after.imgMarked || after.imgDraggable) {
            failures.push({ code: "managed_image_still_native_draggable", round, index, after });
          }
          if (!after.sourceMarked || !after.sourceDraggable) {
            failures.push({ code: "managed_source_not_draggable", round, index, after });
          }
          if (!customUrl || !uri || !plain) {
            failures.push({ code: "managed_drag_missing_url_payload", round, index, types, customUrl, uri, plain });
          }
          if (!downloadUrl) {
            warnings.push({ code: "managed_drag_missing_downloadurl", round, index, types });
          }
        } else if (after.sourceMarked || after.imgMarked) {
          failures.push({ code: "unmanaged_drag_left_managed_marks", round, index, after });
        }
        dispatchDrag("dragend", dragTarget, dataTransfer);
        dispatchMouse("mouseup", img);
        runs.push({
          round,
          index,
          managed,
          defaultPrevented: !!startEvent.defaultPrevented,
          types,
          hasCustomUrl: !!customUrl,
          hasUri: !!uri,
          hasPlain: !!plain,
          hasDownloadUrl: !!downloadUrl,
          after,
        });
      }
    }
    return { runs, failures, warnings };
  }, { selector: config.selector, iterations: config.iterations, customType: CUSTOM_ORIGINAL_URL_TYPE });
  report.synthetic = result.runs;
  report.summary.syntheticRuns = result.runs.length;
  for (const failure of result.failures) {
    pushFailure(report, failure.code, "Synthetic drag data/state contract failed.", failure);
  }
  for (const warning of result.warnings) {
    pushWarning(report, warning.code, "Synthetic drag data/state warning.", warning);
  }
}

async function runLiveSmoke(page, config, report) {
  const candidates = report.candidates.filter((item) => item.visible && item.rect.width >= 8 && item.rect.height >= 8);
  for (let round = 0; round < config.iterations; round += 1) {
    for (const item of candidates) {
      const x = item.rect.x + Math.min(Math.max(4, Math.floor(item.rect.width / 2)), Math.max(4, item.rect.width - 4));
      const y = item.rect.y + Math.min(Math.max(4, Math.floor(item.rect.height / 2)), Math.max(4, item.rect.height - 4));
      const detail = { round, index: item.index, x, y };
      try {
        await withTimeout((async () => {
          await page.mouse.move(x, y);
          await page.mouse.down();
          await page.mouse.move(x + 18, y + 8, { steps: 3 });
          await page.mouse.move(x + 3, y + 2, { steps: 2 });
          await page.mouse.up();
          await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => resolve(true))));
        })(), config.caseTimeoutMs, `live drag round=${round} index=${item.index}`);
        report.live.push({ ...detail, ok: true });
      } catch (err) {
        report.live.push({ ...detail, ok: false, error: err?.message || String(err) });
        pushFailure(report, "live_drag_responsiveness_timeout", "Live drag smoke did not return in time.", { ...detail, error: err?.message || String(err) });
        return;
      } finally {
        report.summary.liveRuns = report.live.length;
      }
    }
  }
}

async function writeReport(report, outPath) {
  if (!outPath) return;
  const resolved = path.resolve(outPath);
  await fs.mkdir(path.dirname(resolved), { recursive: true });
  await fs.writeFile(resolved, JSON.stringify(report, null, 2), "utf-8");
}

function runSelfTest(config) {
  const report = makeReport(config);
  const source = [
    CUSTOM_ORIGINAL_URL_TYPE,
    DEFAULT_SELECTOR,
    String(runSyntheticStress),
    String(runLiveSmoke),
  ].join("\n");
  for (const needle of [
    CUSTOM_ORIGINAL_URL_TYPE,
    "#finished_gallery img",
    "#preview_generating img",
    "managed_drag_missing_url_payload",
    "managed_source_not_draggable",
    "managed_image_still_native_draggable",
    "live_drag_responsiveness_timeout",
  ]) {
    if (!source.includes(needle)) {
      pushFailure(report, "self_test_missing_contract", `Missing contract needle: ${needle}`, { needle });
    }
  }
  return report;
}

async function main() {
  const config = parseArgs(process.argv.slice(2));
  const report = makeReport(config);
  if (config.selfTest) {
    const selfReport = runSelfTest(config);
    await writeReport(selfReport, config.out);
    console.log(JSON.stringify(selfReport.summary));
    process.exit(selfReport.ok ? 0 : 1);
  }

  const { chromium } = await loadPlaywright();
  const launchOptions = { headless: !config.headful };
  if (config.playwrightChannel) launchOptions.channel = config.playwrightChannel;
  let browser = null;
  try {
    browser = await chromium.launch(launchOptions);
    const context = await browser.newContext({ acceptDownloads: true, viewport: { width: 1440, height: 1000 } });
    const page = await context.newPage();
    page.on("console", (msg) => {
      if (msg.type() === "error") report.consoleErrors.push({ type: msg.type(), text: msg.text() });
    });
    page.on("pageerror", (err) => {
      report.consoleErrors.push({ type: "pageerror", text: err?.message || String(err) });
    });
    await page.goto(config.url, { waitUntil: "domcontentloaded", timeout: 45000 });
    if (config.waitMs) await page.waitForTimeout(config.waitMs);
    report.candidates = await collectCandidates(page, config.selector);
    report.summary.candidates = report.candidates.length;
    if (!report.candidates.length) {
      pushFailure(report, "no_drag_candidates", "No gallery/preview images matched the stress selector.", { selector: config.selector });
    } else {
      await runSyntheticStress(page, config, report);
      if (config.live && report.ok) await runLiveSmoke(page, config, report);
    }
  } catch (err) {
    pushFailure(report, "gallery_drag_stress_runtime_error", "Gallery drag stress failed to run.", { error: err?.stack || err?.message || String(err) });
  } finally {
    report.finishedAt = new Date().toISOString();
    await writeReport(report, config.out);
    if (browser) await browser.close().catch(() => {});
  }

  console.log(JSON.stringify(report.summary, null, 2));
  if (!report.ok) {
    console.error(JSON.stringify(report.failures.slice(0, 10), null, 2));
    process.exit(1);
  }
}

main().catch((err) => {
  console.error(err?.stack || err?.message || String(err));
  process.exit(1);
});
