(function () {
  "use strict";

  const CONFIG_ROUTE = "/forge-neo/extensions/camera-angle-selector-config";
  const DEFAULT_CONFIG = {
    enabled: true,
    iframe_id: "forge_neo_camera_angle_iframe",
    txt2img_prompt_id: "forge_neo_prompt",
    img2img_prompt_id: "forge_neo_img2img_prompt",
    message_request_type: "GET_CURRENT_ANGLE",
    message_response_type: "ANGLE_SELECTED",
  };

  let config = DEFAULT_CONFIG;

  function mergeConfig(next) {
    config = Object.assign({}, DEFAULT_CONFIG, next || {});
    window.forgeNeoCameraAngleSelector = { config };
  }

  function promptRoot(target) {
    const id = target === "img2img" ? config.img2img_prompt_id : config.txt2img_prompt_id;
    return document.getElementById(id);
  }

  function promptInput(target) {
    const root = promptRoot(target);
    if (!root) return null;
    if (root.matches && root.matches("textarea, input")) return root;
    return root.querySelector("textarea, input");
  }

  function setNativeValue(input, value) {
    const proto = Object.getPrototypeOf(input);
    const descriptor = Object.getOwnPropertyDescriptor(proto, "value");
    if (descriptor && descriptor.set) {
      descriptor.set.call(input, value);
    } else {
      input.value = value;
    }
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function promptFromMessage(data) {
    return [data && data.azimuth, data && data.elevation, data && data.distance]
      .map((item) => String(item || "").trim())
      .filter(Boolean)
      .join(" ");
  }

  function statusElement() {
    return document.querySelector(".forge-neo-camera-angle-status");
  }

  function setStatus(text, kind) {
    const element = statusElement();
    if (!element) return;
    element.textContent = text || "";
    element.dataset.state = kind || "";
  }

  function appendPrompt(target, text) {
    const input = promptInput(target);
    if (!input || !text) return false;
    const current = String(input.value || "").trim();
    const next = current ? `${current}, ${text}` : text;
    setNativeValue(input, next);
    return true;
  }

  function requestCurrentAngle(target) {
    const iframe = document.getElementById(config.iframe_id);
    if (!iframe || !iframe.contentWindow) {
      setStatus("Camera view is not ready.", "error");
      return;
    }
    setStatus("Reading angle...", "pending");
    const timeoutId = window.setTimeout(() => {
      window.removeEventListener("message", onMessage);
      setStatus("Camera view did not respond.", "error");
    }, 3000);

    function onMessage(event) {
      if (!event || !event.data || event.data.type !== config.message_response_type) return;
      window.clearTimeout(timeoutId);
      window.removeEventListener("message", onMessage);
      const text = promptFromMessage(event.data);
      if (!text) {
        setStatus("No angle prompt returned.", "error");
        return;
      }
      if (appendPrompt(target, text)) {
        setStatus(text, "ok");
      } else {
        setStatus("Prompt input was not found.", "error");
      }
    }

    window.addEventListener("message", onMessage);
    iframe.contentWindow.postMessage({ type: config.message_request_type }, "*");
  }

  function bindButtons() {
    document.querySelectorAll("[data-forge-neo-camera-target]").forEach((button) => {
      if (button.dataset.forgeNeoCameraBound === "true") return;
      button.dataset.forgeNeoCameraBound = "true";
      button.addEventListener("click", () => requestCurrentAngle(button.dataset.forgeNeoCameraTarget || "txt2img"));
    });
  }

  async function loadConfig() {
    try {
      const response = await fetch(CONFIG_ROUTE, { cache: "no-store" });
      if (response.ok) mergeConfig(await response.json());
      else mergeConfig(DEFAULT_CONFIG);
    } catch (_error) {
      mergeConfig(DEFAULT_CONFIG);
    }
    bindButtons();
    const observer = new MutationObserver(bindButtons);
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadConfig, { once: true });
  } else {
    loadConfig();
  }
})();
