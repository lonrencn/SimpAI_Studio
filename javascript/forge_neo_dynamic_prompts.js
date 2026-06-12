(function () {
    "use strict";

    if (typeof window.gradioApp !== "function") {
        window.gradioApp = function () {
            return document;
        };
    }

    function isVisible(element) {
        if (!element) return false;
        const style = window.getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
    }

    function setTextValue(element, value) {
        if (!element) return;
        const prototype = Object.getPrototypeOf(element);
        const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
        if (descriptor && typeof descriptor.set === "function") {
            descriptor.set.call(element, value);
        } else {
            element.value = value;
        }
        element.dispatchEvent(new Event("input", { bubbles: true }));
        element.dispatchEvent(new Event("change", { bubbles: true }));
        window.updateInput?.(element);
    }

    const wildcardTexts = {
        managerTab: { en: "Wildcards Manager", cn: "通配符管理" },
        searchPlaceholder: { en: "Search in wildcard names...", cn: "使用通配符名称检索..." },
        help: { en: "Help", cn: "帮助" },
        collectionActions: { en: "Collection actions", cn: "合集操作" },
        selectCollection: { en: "Select a collection", cn: "选择集合" },
        copyCollection: { en: "Copy collection", cn: "复制集合" },
        overwriteExisting: { en: "Overwrite existing", cn: "覆写已有项" },
        refreshWildcards: { en: "Refresh wildcards", cn: "刷新通配符" },
        deleteAllWildcards: { en: "Delete all wildcards", cn: "删除所有通配符" },
        wildcardsFile: { en: "Wildcards file", cn: "通配符文件" },
        fileEditor: { en: "File editor", cn: "编辑文件" },
        saveWildcard: { en: "Save wildcard", cn: "保存通配符" }
    };

    function normalizeLang(value) {
        const raw = String(value || "").trim().toLowerCase();
        return raw.startsWith("en") ? "en" : "cn";
    }

    function currentLang() {
        try {
            if (window.SimpAII18n && typeof window.SimpAII18n.getUiLang === "function") {
                return normalizeLang(window.SimpAII18n.getUiLang(window.simpleaiTopbarSystemParams));
            }
        } catch (error) {}
        const runtime = document.querySelector(".forge-neo-hidden-runtime");
        if (runtime && runtime.dataset.lang) return normalizeLang(runtime.dataset.lang);
        if (typeof window.locale_lang === "string") return normalizeLang(window.locale_lang);
        try {
            const search = new URLSearchParams(window.location.search || "");
            const queryLang = search.get("__lang");
            if (queryLang) return normalizeLang(queryLang);
        } catch (error) {}
        try {
            return normalizeLang(localStorage.getItem("ailang"));
        } catch (error) {}
        return "cn";
    }

    function wildcardText(key) {
        const item = wildcardTexts[key];
        if (!item) return "";
        if (currentLang() === "en") return item.en;
        const localization = window.localization && typeof window.localization === "object" ? window.localization : {};
        return localization[item.en] || item.cn;
    }

    function setOriginalText(element, key) {
        const item = wildcardTexts[key];
        if (!element || !item) return;
        element.setAttribute("data-original-text", item.en);
    }

    function setElementText(element, key) {
        if (!element) return;
        const text = wildcardText(key);
        setOriginalText(element, key);
        if (element.textContent.trim() !== text) {
            element.textContent = text;
        }
    }

    function setSelectorText(selector, key) {
        gradioApp().querySelectorAll(selector).forEach(function (element) {
            setElementText(element, key);
        });
    }

    function setComponentLabel(componentId, key) {
        const root = gradioApp().querySelector("#" + componentId);
        if (!root) return;
        const label = root.querySelector("label span, .label-wrap span, [data-testid='block-info']");
        setElementText(label, key);
    }

    function setAccordionLabel(componentId, key) {
        const root = gradioApp().querySelector("#" + componentId);
        if (!root) return;
        const label = root.querySelector("button > span, button .label-wrap span, summary span, .label-wrap span");
        setElementText(label, key);
    }

    function setPlaceholder(selector, key) {
        const element = gradioApp().querySelector(selector);
        if (!element) return;
        const item = wildcardTexts[key];
        if (!item) return;
        element.setAttribute("data-original-placeholder", item.en);
        const text = wildcardText(key);
        if (element.placeholder !== text) element.placeholder = text;
    }

    function localizeWildcardManager() {
        setSelectorText("#tab_sddp-wildcard-manager-button, [aria-controls='tab_sddp-wildcard-manager']", "managerTab");
        setPlaceholder("#sddp-wildcard-search textarea, #sddp-wildcard-search input", "searchPlaceholder");
        setAccordionLabel("sddp-wildcard-help-accordion", "help");
        setAccordionLabel("sddp-wildcard-collection-actions", "collectionActions");
        setComponentLabel("sddp-wildcard-collection-dropdown", "selectCollection");
        setComponentLabel("sddp-wildcard-overwrite-checkbox", "overwriteExisting");
        setComponentLabel("sddp-wildcard-file-name", "wildcardsFile");
        setComponentLabel("sddp-wildcard-file-editor", "fileEditor");
        setSelectorText("#sddp-wildcard-copy-collection-button", "copyCollection");
        setSelectorText("#sddp-wildcard-refresh-visible-button", "refreshWildcards");
        setSelectorText("#sddp-wildcard-delete-tree-button", "deleteAllWildcards");
        setSelectorText("#sddp-wildcard-save-button", "saveWildcard");
    }

    function installWildcardManagerCompat() {
        const sddp = window.SDDP;
        if (!sddp || sddp.__forgeNeoWildcardCompatInstalled) return;
        sddp.__forgeNeoWildcardCompatInstalled = true;
        sddp.sendAction = function (payload) {
            const outbox = gradioApp().querySelector("#sddp-wildcard-c2s-message-textbox textarea");
            const actionButton = gradioApp().querySelector("#sddp-wildcard-c2s-action-button");
            if (!outbox || !actionButton) return;
            setTextValue(outbox, this.formatPayload(payload));
            actionButton.click();
        };
        sddp.loadFileIntoEditor = function (message) {
            const editor = gradioApp().querySelector("#sddp-wildcard-file-editor textarea");
            const name = gradioApp().querySelector("#sddp-wildcard-file-name textarea");
            const saveButton = gradioApp().querySelector("#sddp-wildcard-save-button");
            const { contents, wrapped_name: wrappedName, can_edit: canEdit } = message;
            setTextValue(editor, contents || "");
            setTextValue(name, wrappedName || "");
            if (editor) editor.readOnly = !canEdit;
            if (saveButton) saveButton.disabled = !canEdit;
        };
    }

    function activateWildcardManager() {
        localizeWildcardManager();
        const tab = document.querySelector("#tab_sddp-wildcard-manager");
        if (!isVisible(tab)) return;
        if (!window.SDDP || typeof window.SDDP.onWildcardManagerTabActivate !== "function") return;
        installWildcardManagerCompat();
        window.SDDP.onWildcardManagerTabActivate();
    }

    function scheduleActivate() {
        window.setTimeout(activateWildcardManager, 0);
        window.setTimeout(activateWildcardManager, 120);
    }

    const onUpdate = window.onAfterUiUpdate || window.onUiUpdate;
    if (typeof onUpdate === "function") {
        onUpdate(activateWildcardManager);
    }

    document.addEventListener("click", function (event) {
        const target = event.target;
        if (!(target instanceof Element)) return;
        if (target.closest("#tab_sddp-wildcard-manager-button, [aria-controls='tab_sddp-wildcard-manager']")) {
            scheduleActivate();
        }
    });

    window.setTimeout(scheduleActivate, 250);
    window.forgeNeoDynamicPromptsLocalizeWildcardManager = localizeWildcardManager;
    window.forgeNeoDynamicPromptsActivateWildcardManager = activateWildcardManager;
})();
