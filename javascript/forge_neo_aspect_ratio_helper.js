(function () {
  "use strict";

  const CONFIG_ROUTE = "/forge-neo/extensions/aspect-ratio-helper-config";
  const DEFAULT_CONFIG = {
    enabled: true,
    choices: ["Off", "Lock", "1:1", "3:2", "4:3", "5:4", "16:9", "9:16", "21:9"],
    default: "Off",
    min_dimension: 64,
    max_dimension: 2048,
    step: 8,
    txt2img: {
      width_id: "forge_neo_width",
      height_id: "forge_neo_height",
      switch_button_id: "forge_neo_res_switch_btn",
      select_id: "forge_neo_arh_txt2img_ratio",
    },
    img2img: {
      width_id: "forge_neo_img2img_width",
      height_id: "forge_neo_img2img_height",
      switch_button_id: "forge_neo_img2img_res_switch_btn",
      select_id: "forge_neo_arh_img2img_ratio",
    },
  };

  const state = {
    config: DEFAULT_CONFIG,
    controllers: {},
  };

  function mergeConfig(config) {
    return Object.assign({}, DEFAULT_CONFIG, config || {}, {
      txt2img: Object.assign({}, DEFAULT_CONFIG.txt2img, (config && config.txt2img) || {}),
      img2img: Object.assign({}, DEFAULT_CONFIG.img2img, (config && config.img2img) || {}),
    });
  }

  function root() {
    return document;
  }

  function byId(id) {
    return id ? root().getElementById(id) : null;
  }

  function inputsFor(component) {
    if (!component) return [];
    return Array.from(component.querySelectorAll("input[type='number'], input[type='range']"));
  }

  function numberInput(component) {
    return component && component.querySelector("input[type='number']");
  }

  function readValue(component) {
    const input = numberInput(component);
    const value = input ? Number(input.value) : NaN;
    return Number.isFinite(value) ? value : 0;
  }

  function clamp(value) {
    const min = Number(state.config.min_dimension || 64);
    const max = Number(state.config.max_dimension || 2048);
    const step = Number(state.config.step || 8);
    const bounded = Math.max(min, Math.min(max, Number(value) || min));
    return Math.round(bounded / step) * step;
  }

  function setNativeValue(input, value) {
    if (!input) return;
    const proto = Object.getPrototypeOf(input);
    const descriptor = Object.getOwnPropertyDescriptor(proto, "value");
    if (descriptor && descriptor.set) {
      descriptor.set.call(input, String(value));
    } else {
      input.value = String(value);
    }
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function setValue(component, value) {
    const next = clamp(value);
    inputsFor(component).forEach((input) => setNativeValue(input, next));
  }

  function parseRatio(value, controller) {
    if (value === "Off") return null;
    if (value === "Lock") {
      return controller.lockRatio || [readValue(controller.width), readValue(controller.height)];
    }
    const parts = String(value || "").split(":").map((item) => Number(item));
    if (parts.length !== 2 || !parts.every((item) => Number.isFinite(item) && item > 0)) return null;
    return parts;
  }

  function optionExists(value) {
    return (state.config.choices || []).includes(value);
  }

  function syncSelectLabel(select) {
    const label = select && select.parentElement && select.parentElement.querySelector(".forge-neo-arh-label");
    if (label) label.textContent = select.value || "";
  }

  function createSelect(target, controller) {
    const button = byId(target.switch_button_id);
    if (!button || !button.parentElement) return null;
    const toolsColumn = button.closest(".forge-neo-dimension-tools");
    if (toolsColumn) toolsColumn.classList.add("forge-neo-arh-dimension-tools");
    button.parentElement.classList.add("forge-neo-arh-tools");
    const existing = byId(target.select_id);
    if (existing) {
      syncSelectLabel(existing);
      return existing;
    }
    const wrapper = document.createElement("div");
    wrapper.className = "forge-neo-arh-control";
    const label = document.createElement("span");
    label.className = "forge-neo-arh-label";
    label.setAttribute("aria-hidden", "true");
    const select = document.createElement("select");
    select.id = target.select_id;
    select.className = "forge-neo-arh-select";
    (state.config.choices || DEFAULT_CONFIG.choices).forEach((choice) => {
      const option = document.createElement("option");
      option.value = choice;
      option.textContent = choice;
      select.appendChild(option);
    });
    select.value = state.config.default || "Off";
    label.textContent = select.value;
    wrapper.appendChild(label);
    wrapper.appendChild(select);
    button.parentElement.insertBefore(wrapper, button);
    select.addEventListener("change", () => {
      syncSelectLabel(select);
      if (select.value === "Lock") {
        controller.lockRatio = [readValue(controller.width), readValue(controller.height)];
      }
      applyRatio(controller, null);
    });
    button.addEventListener("click", () => {
      window.setTimeout(() => {
        if (select.value === "Lock") {
          controller.lockRatio = [readValue(controller.width), readValue(controller.height)];
        } else if (select.value.includes(":")) {
          const reversed = select.value.split(":").reverse().join(":");
          if (optionExists(reversed)) select.value = reversed;
        }
        syncSelectLabel(select);
        applyRatio(controller, null);
      }, 60);
    });
    return select;
  }

  function applyRatio(controller, changed) {
    if (controller.applying) return;
    const ratio = parseRatio(controller.select.value, controller);
    if (!ratio) return;
    const widthRatio = ratio[0];
    const heightRatio = ratio[1];
    const currentWidth = readValue(controller.width);
    const currentHeight = readValue(controller.height);
    let nextWidth = currentWidth;
    let nextHeight = currentHeight;
    if (!changed || changed === controller.width) {
      nextHeight = nextWidth * (heightRatio / widthRatio);
    } else {
      nextWidth = nextHeight * (widthRatio / heightRatio);
    }
    controller.applying = true;
    setValue(controller.width, nextWidth);
    setValue(controller.height, nextHeight);
    controller.applying = false;
  }

  function bindInputs(component, controller) {
    inputsFor(component).forEach((input) => {
      if (input.dataset.forgeNeoArhBound === "true") return;
      input.dataset.forgeNeoArhBound = "true";
      input.addEventListener("input", () => applyRatio(controller, component));
      input.addEventListener("change", () => applyRatio(controller, component));
    });
  }

  function setupTarget(name, target) {
    if (state.controllers[name]) return true;
    const width = byId(target.width_id);
    const height = byId(target.height_id);
    const button = byId(target.switch_button_id);
    if (!width || !height || !button || !inputsFor(width).length || !inputsFor(height).length) return false;
    const controller = { width, height, button, lockRatio: null, applying: false, select: null };
    controller.select = createSelect(target, controller);
    if (!controller.select) return false;
    bindInputs(width, controller);
    bindInputs(height, controller);
    state.controllers[name] = controller;
    return true;
  }

  function setup() {
    if (!state.config.enabled) return;
    setupTarget("txt2img", state.config.txt2img);
    setupTarget("img2img", state.config.img2img);
  }

  async function loadConfig() {
    try {
      const response = await fetch(CONFIG_ROUTE, { cache: "no-store" });
      if (response.ok) {
        state.config = mergeConfig(await response.json());
      }
    } catch (_error) {
      state.config = mergeConfig(DEFAULT_CONFIG);
    }
    window.forgeNeoAspectRatioHelper = state;
    setup();
    const observer = new MutationObserver(setup);
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadConfig, { once: true });
  } else {
    loadConfig();
  }
})();
