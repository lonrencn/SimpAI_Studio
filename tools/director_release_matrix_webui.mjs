import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const URL = process.env.SIMPAI_DIRECTOR_MATRIX_URL || "http://127.0.0.1:8186/?__theme=dark";
const CHROME = process.env.SIMPAI_CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const REPORT_DIR = process.env.SIMPAI_DIRECTOR_MATRIX_REPORT_DIR || "reports/director-release-matrix";

const results = [];

function compactText(value) {
  return String(value || "").trim().replace(/\s+/g, " ");
}

function pass(id, name, details = {}) {
  results.push({ id, name, status: "PASS", details });
}

function fail(id, name, details = {}) {
  results.push({ id, name, status: "FAIL", details });
}

function assertCondition(condition, message, details = {}) {
  if (!condition) {
    const error = new Error(message);
    error.details = details;
    throw error;
  }
}

async function clickPreset(page, label) {
  await page.getByText(label, { exact: true }).first().click({ timeout: 25000 });
  await page.waitForTimeout(4500);
}

async function openDirector(page) {
  const button = page.locator("#scene_director_accordion button.label-wrap").first();
  await button.click({ timeout: 15000 });
  await page.waitForTimeout(1500);
  await page.evaluate(() => {
    if (window.sceneDirectorInitWorkspace) window.sceneDirectorInitWorkspace();
    if (window.refresh_scene_director_editor) window.refresh_scene_director_editor();
  });
  await page.waitForTimeout(600);
}

async function readDirector(page) {
  return page.evaluate(() => {
    const root = document.documentElement;
    const accordion = document.getElementById("scene_director_accordion");
    const advanced = document.getElementById("scene_advanced_parameters_accordion");
    const all = Array.from(document.querySelectorAll("body *"));
    const row0 = document.querySelector("#scene_director_editor .scene-director-shot");
    const enabled = document.querySelector("#scene_director_enabled input[type='checkbox']");
    const compose = document.querySelector("#scene_director_compose input[type='checkbox']");
    const end = row0 ? row0.querySelector("[data-scene-director-field='end']") : null;
    const videoSelect = row0 ? row0.querySelector("[data-scene-director-field='video_ref']") : null;
    const audioSelect = row0 ? row0.querySelector("[data-scene-director-field='audio_ref']") : null;
    const choices = Array.from(row0 ? row0.querySelectorAll("[data-scene-director-ref-choice]") : []).map((btn) => ({
      ref: btn.getAttribute("data-scene-director-ref-choice") || "",
      disabled: btn.disabled,
      active: btn.classList.contains("is-active"),
      limitDisabled: btn.classList.contains("is-limit-disabled"),
      text: btn.innerText.trim().replace(/\s+/g, " "),
    }));
    const rect = accordion ? accordion.getBoundingClientRect() : null;
    return {
      htmlClasses: root.className,
      visible: accordion ? getComputedStyle(accordion).display !== "none" && rect.width > 0 && rect.height > 0 : false,
      order: {
        advanced: all.indexOf(advanced),
        director: all.indexOf(accordion),
      },
      dataset: {
        imagePolicy: root.dataset.simpaiSceneDirectorImagePolicy || "",
        audioPolicy: root.dataset.simpaiSceneDirectorAudioPolicy || "",
        videoPolicy: root.dataset.simpaiSceneDirectorVideoPolicy || "",
        maxImages: root.dataset.simpaiSceneDirectorMaxImages || "",
        minImages: root.dataset.simpaiSceneDirectorMinImages || "",
        maxDuration: root.dataset.simpaiSceneDirectorMaxSegmentDuration || "",
        minDuration: root.dataset.simpaiSceneDirectorMinSegmentDuration || "",
        durationStrategy: root.dataset.simpaiSceneDirectorDurationStrategy || "",
        audioOutput: root.dataset.simpaiSceneDirectorAudioOutput || "",
        videoModes: root.dataset.simpaiSceneDirectorVideoModes || "",
        chainOutput: root.dataset.simpaiSceneDirectorChainOutput || "",
      },
      enabledChecked: enabled ? enabled.checked : null,
      composeChecked: compose ? compose.checked : null,
      endMax: end ? end.getAttribute("max") : null,
      endValue: end ? end.value : null,
      videoOptions: Array.from(videoSelect ? videoSelect.options : []).map((item) => item.value),
      audioOptions: Array.from(audioSelect ? audioSelect.options : []).map((item) => item.value),
      choices,
      row0Text: row0 ? row0.innerText.slice(0, 1200) : "",
      bodyText: document.body.innerText.slice(0, 2500),
    };
  });
}

function imageChoiceMap(state) {
  return Object.fromEntries(state.choices.filter((item) => item.ref).map((item) => [item.ref, item]));
}

async function testDefaultLayout(page) {
  const state = await readDirector(page);
  assertCondition(state.order.advanced >= 0 && state.order.director >= 0 && state.order.advanced < state.order.director, "Advanced accordion should be above director workspace", state.order);
  assertCondition(!state.visible, "Director workspace should be hidden for the initial non-video preset", state);
  pass("W-00", "non-video preset hides director and keeps advanced above director", state);
}

async function testWanI2V(page) {
  await clickPreset(page, "Wan图生视频");
  await openDirector(page);
  await page.locator("#scene_director_editor .scene-director-shot").first().locator("[data-scene-director-ref-choice='image_2']").click();
  await page.waitForTimeout(400);
  const state = await readDirector(page);
  const choices = imageChoiceMap(state);
  assertCondition(state.visible, "Wan I2V should show director workspace", state);
  assertCondition(state.dataset.imagePolicy === "required", "Wan I2V should require images", state.dataset);
  assertCondition(state.dataset.maxImages === "2", "Wan I2V should cap images at 2", state.dataset);
  assertCondition(state.dataset.maxDuration === "10", "Wan I2V should use 10s segment cap", state.dataset);
  assertCondition(state.composeChecked === false, "Compose timeline should default off", state);
  assertCondition(choices.image_1?.active && choices.image_2?.active, "First two images should be selected after click", state.choices);
  assertCondition(choices.image_3?.disabled && choices.image_4?.disabled && choices.image_5?.disabled, "Images 3-5 should disable after two image refs", state.choices);
  pass("W-03/W-04", "Wan I2V image cap and compose default", state);
}

async function testLtxT2V(page) {
  await clickPreset(page, "LTX2.3文生视频");
  await openDirector(page);
  const state = await readDirector(page);
  assertCondition(state.dataset.imagePolicy === "forbidden", "LTX T2V should forbid image refs", state.dataset);
  assertCondition(state.dataset.maxImages === "0", "LTX T2V should keep max_images=0", state.dataset);
  assertCondition(state.dataset.maxDuration === "60" && state.endMax === "60", "LTX T2V should expose 60s cap", state);
  assertCondition(state.choices.every((item) => !item.ref || item.disabled), "LTX T2V image buttons should be disabled", state.choices);
  pass("W-06/T-03", "LTX T2V media policy and 60s duration", state);
}

async function testLtxI2V(page) {
  await clickPreset(page, "LTX2.3图生视频");
  await openDirector(page);
  let state = await readDirector(page);
  let choices = imageChoiceMap(state);
  let activeChoices = Object.values(choices).filter((item) => item.active);
  if (activeChoices.length === 0) {
    const candidate = Object.values(choices).find((item) => item.ref && !item.disabled);
    assertCondition(candidate, "LTX I2V should expose one selectable image candidate", state.choices);
    await page.locator("#scene_director_editor .scene-director-shot").first().locator(`[data-scene-director-ref-choice='${candidate.ref}']`).click();
    await page.waitForTimeout(400);
    state = await readDirector(page);
    choices = imageChoiceMap(state);
    activeChoices = Object.values(choices).filter((item) => item.active);
  }
  const inactiveChoices = Object.values(choices).filter((item) => item.ref && !item.active);
  assertCondition(state.dataset.imagePolicy === "required", "LTX I2V should require one image", state.dataset);
  assertCondition(state.dataset.maxImages === "1", "LTX I2V should cap images at 1", state.dataset);
  assertCondition(state.dataset.maxDuration === "60", "LTX I2V should expose 60s cap", state.dataset);
  assertCondition(activeChoices.length === 1, "Only one image should be active for LTX I2V", state.choices);
  assertCondition(inactiveChoices.every((item) => item.disabled), "Other image choices should be disabled after one image ref", state.choices);
  pass("W-05", "LTX I2V single image cap", state);
}

async function testInfiniteTalk(page) {
  await clickPreset(page, "Wan无限对话");
  await openDirector(page);
  const state = await readDirector(page);
  assertCondition(state.dataset.imagePolicy === "required", "InfiniteTalk should require image", state.dataset);
  assertCondition(state.dataset.audioPolicy === "required", "InfiniteTalk should require audio", state.dataset);
  assertCondition(state.dataset.videoPolicy === "forbidden", "InfiniteTalk should forbid video", state.dataset);
  assertCondition(state.dataset.durationStrategy === "audio_min", "InfiniteTalk should use audio_min", state.dataset);
  assertCondition(state.dataset.maxDuration === "120", "InfiniteTalk should expose 120s cap", state.dataset);
  pass("W-09", "InfiniteTalk image/audio required and audio_min", state);
}

async function testVideoExtend(page) {
  await clickPreset(page, "Dasiwa视频延长");
  await openDirector(page);
  const state = await readDirector(page);
  assertCondition(state.dataset.imagePolicy === "forbidden", "Video extend should forbid image refs", state.dataset);
  assertCondition(state.dataset.videoPolicy === "required", "Video extend should require video", state.dataset);
  assertCondition(state.dataset.chainOutput === "last_result", "Video extend should use last_result", state.dataset);
  assertCondition(state.dataset.videoModes.includes("previous_segment"), "Video extend should allow previous_segment", state.dataset);
  assertCondition(state.videoOptions.includes("previous_segment"), "Video select should include previous_segment", state.videoOptions);
  pass("W-10/W-11/T-09", "Video extend policy and previous segment mode", state);
}

async function testVideoProcessing(page) {
  await clickPreset(page, "Nvidia超分辨率");
  await openDirector(page);
  const state = await readDirector(page);
  assertCondition(state.dataset.imagePolicy === "forbidden", "Nvidia VSR should forbid image refs", state.dataset);
  assertCondition(state.dataset.videoPolicy === "required", "Nvidia VSR should require video", state.dataset);
  assertCondition(state.dataset.durationStrategy === "video_min", "Nvidia VSR should use video_min", state.dataset);
  assertCondition(state.dataset.audioOutput === "source_audio", "Nvidia VSR should preserve source audio", state.dataset);
  assertCondition(state.dataset.maxDuration === "120", "Nvidia VSR should expose 120s cap", state.dataset);
  pass("W-14/T-05", "Video processing policy and source audio", state);
}

async function main() {
  await mkdir(REPORT_DIR, { recursive: true });
  const browser = await chromium.launch({ headless: true, executablePath: CHROME });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1200 } });
  page.setDefaultTimeout(30000);
  await page.goto(URL, { waitUntil: "domcontentloaded", timeout: 120000 });
  await page.waitForLoadState("networkidle", { timeout: 120000 }).catch(() => {});
  await page.waitForTimeout(5000);
  const tests = [
    testDefaultLayout,
    testWanI2V,
    testLtxT2V,
    testLtxI2V,
    testInfiniteTalk,
    testVideoExtend,
    testVideoProcessing,
  ];
  for (const test of tests) {
    try {
      await test(page);
    } catch (error) {
      fail(test.name, compactText(error.message), error.details || {});
    }
  }
  await browser.close();
  const failed = results.filter((item) => item.status !== "PASS");
  const report = {
    url: URL,
    chrome: CHROME,
    generated_at: new Date().toISOString(),
    summary: {
      total: results.length,
      pass: results.length - failed.length,
      fail: failed.length,
    },
    results,
  };
  const output = path.join(REPORT_DIR, `webui-${Date.now()}.json`);
  await writeFile(output, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify(report, null, 2));
  if (failed.length) process.exit(1);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
