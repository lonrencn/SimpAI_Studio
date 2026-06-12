function appRoot() {
    if (typeof gradioApp === "function") {
        return gradioApp();
    }
    return document;
}

function emitInput(target) {
    if (!target) return;
    if (typeof updateInput === "function") {
        updateInput(target);
        return;
    }
    target.dispatchEvent(new Event("input", { bubbles: true }));
    target.dispatchEvent(new Event("change", { bubbles: true }));
}

function labelTextTarget(labelWrap) {
    return labelWrap.querySelector("span") || labelWrap;
}

function inputAccordionChecked(id, checked) {
    const root = appRoot();
    const accordion = root.getElementById(id);
    if (!accordion || !accordion.visibleCheckbox) return;
    accordion.visibleCheckbox.checked = checked;
    accordion.onVisibleCheckboxChange();
}

function setupAccordion(accordion) {
    if (!accordion || accordion.dataset.forgeNeoAccordionReady === "1") return;

    const root = appRoot();
    const labelWrap = accordion.querySelector(".label-wrap");
    const gradioCheckbox = root.querySelector("#" + accordion.id + "-checkbox input");
    if (!labelWrap || !gradioCheckbox) return;

    accordion.dataset.forgeNeoAccordionReady = "1";
    const extra = root.querySelector("#" + accordion.id + "-extra");
    const target = labelTextTarget(labelWrap);
    let linked = true;

    const isOpen = function () {
        return labelWrap.classList.contains("open");
    };

    const observerAccordionOpen = new MutationObserver(function () {
        accordion.classList.toggle("input-accordion-open", isOpen());
        if (linked) {
            accordion.visibleCheckbox.checked = isOpen();
            accordion.onVisibleCheckboxChange();
        }
    });
    observerAccordionOpen.observe(labelWrap, {
        attributes: true,
        attributeFilter: ["class"],
    });

    if (extra && extra.parentElement !== labelWrap) {
        labelWrap.insertBefore(extra, labelWrap.lastElementChild);
    }

    accordion.onChecked = function (checked) {
        if (isOpen() !== checked) {
            labelWrap.click();
        }
    };

    const visibleCheckbox = document.createElement("INPUT");
    visibleCheckbox.type = "checkbox";
    visibleCheckbox.checked = isOpen();
    visibleCheckbox.id = accordion.id + "-visible-checkbox";
    visibleCheckbox.className = gradioCheckbox.className + " input-accordion-checkbox";
    target.insertBefore(visibleCheckbox, target.firstChild);

    accordion.visibleCheckbox = visibleCheckbox;
    accordion.onVisibleCheckboxChange = function () {
        if (linked && isOpen() !== visibleCheckbox.checked) {
            labelWrap.click();
        }
        gradioCheckbox.checked = visibleCheckbox.checked;
        emitInput(gradioCheckbox);
    };

    visibleCheckbox.addEventListener("click", function (event) {
        linked = false;
        event.stopPropagation();
    });
    visibleCheckbox.addEventListener("input", accordion.onVisibleCheckboxChange);
}

function scheduleSetup() {
    const root = appRoot();
    for (const accordion of root.querySelectorAll(".input-accordion")) {
        setupAccordion(accordion);
    }
}

window.inputAccordionChecked = inputAccordionChecked;

new MutationObserver(scheduleSetup).observe(document.documentElement, {
    childList: true,
    subtree: true,
});

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scheduleSetup, { once: true });
} else {
    scheduleSetup();
}
