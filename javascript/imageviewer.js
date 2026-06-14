// From A1111

function closeModal() {
    const modal = gradioApp().getElementById("lightboxModal");
    if (!modal) return;
    modal.style.setProperty("display", "none", "important");
    modal.style.setProperty("visibility", "hidden", "important");
    modal.setAttribute("aria-hidden", "true");
}

function showModal(event) {
    const source = event.target || event.srcElement;
    const modalImage = gradioApp().getElementById("modalImage");
    const lb = gradioApp().getElementById("lightboxModal");
    const src = simpleaiMediaSrc(source);
    if (!src) return;
    modalImage.src = src;
    if (modalImage.style.display === 'none') {
        lb.style.setProperty('background-image', 'url(' + src + ')');
    }
    lb.style.setProperty("display", "flex", "important");
    lb.style.setProperty("visibility", "visible", "important");
    lb.removeAttribute("aria-hidden");
    lb.focus();

    event.stopPropagation();
    event.stopImmediatePropagation();
}

function negmod(n, m) {
    return ((n % m) + m) % m;
}

function updateOnBackgroundChange() {
    const modalImage = gradioApp().getElementById("modalImage");
    if (modalImage && modalImage.offsetParent) {
        let currentButton = selected_gallery_button();
        const media = simpleaiGalleryButtonMedia(currentButton);
        const src = simpleaiMediaSrc(media);

        if (src && modalImage.src != src) {
            modalImage.src = src;
            if (modalImage.style.display === 'none') {
                const modal = gradioApp().getElementById("lightboxModal");
                modal.style.setProperty('background-image', `url(${modalImage.src})`);
            }
        }
    }
}

function all_gallery_buttons() {
    var allGalleryButtons = gradioApp().querySelectorAll('.image_gallery .thumbnails > .thumbnail-item.thumbnail-small');
    var visibleGalleryButtons = [];
    allGalleryButtons.forEach(function(elem) {
        if (elem.parentElement.offsetParent) {
            visibleGalleryButtons.push(elem);
        }
    });
    return visibleGalleryButtons;
}

function selected_gallery_button() {
    return all_gallery_buttons().find(elem => elem.classList.contains('selected')) ?? null;
}

function selected_gallery_index() {
    return all_gallery_buttons().findIndex(elem => elem.classList.contains('selected'));
}

function simpleaiGalleryButtonMedia(button) {
    return button?.querySelector?.('img, video') || null;
}

function simpleaiMediaSrc(elem) {
    if (!elem) return '';
    return elem.currentSrc || elem.src || elem.getAttribute?.('src') || '';
}

const SIMPLEAI_NATIVE_IMAGE_DRAG_PREVIEW_SELECTOR = [
    '#finished_gallery .gallery-container img',
    '#final_gallery .gallery-container img',
    '#scene_input_images img',
    '#scene_input_image1 img',
    '#scene_input_image2 img',
    '#scene_input_image3 img',
    '#scene_input_image4 img',
    '#describe_input_image img',
    '#image_input_panel img',
    '#input_image img',
    '#uov_input_image img',
    '#inpaint_input_image img',
    '#ip_image_grid img',
    '#ip_image_1 img',
    '#ip_image_2 img',
    '#ip_image_3 img',
    '#ip_image_4 img'
].join(', ');

function simpleaiNativeImageDragPreviewImageFromEvent(event) {
    const target = event?.target;
    if (!target || !target.closest) return null;
    const img = target.closest(SIMPLEAI_NATIVE_IMAGE_DRAG_PREVIEW_SELECTOR);
    if (!img || img.tagName !== 'IMG') return null;
    const src = simpleaiMediaSrc(img);
    if (!src || src.startsWith('data:image/svg+xml')) return null;
    const naturalWidth = Number(img.naturalWidth || 0);
    const naturalHeight = Number(img.naturalHeight || 0);
    if (naturalWidth && naturalHeight && (naturalWidth < 48 || naturalHeight < 48)) return null;
    return img;
}

function simpleaiRemoveNativeImageDragPreview() {
    document.getElementById('simpleai-native-image-drag-preview')?.remove();
}

function simpleaiCreateNativeImageDragPreview(img) {
    simpleaiRemoveNativeImageDragPreview();
    const src = simpleaiMediaSrc(img);
    if (!src) return null;
    const preview = document.createElement('div');
    preview.id = 'simpleai-native-image-drag-preview';
    const width = 120;
    const naturalWidth = Number(img?.naturalWidth || 0);
    const naturalHeight = Number(img?.naturalHeight || 0);
    const ratio = naturalWidth > 0 && naturalHeight > 0 ? naturalHeight / naturalWidth : 1;
    const height = Math.max(48, Math.min(160, Math.round(width * ratio)));
    preview.style.position = 'fixed';
    preview.style.left = '-10000px';
    preview.style.top = '-10000px';
    preview.style.width = `${width}px`;
    preview.style.height = `${height}px`;
    preview.style.pointerEvents = 'none';
    preview.style.opacity = '0.95';
    preview.style.borderRadius = '8px';
    preview.style.backgroundColor = '#111827';
    preview.style.backgroundImage = `url("${String(src).replace(/\\/g, "\\\\").replace(/"/g, '\\"')}")`;
    preview.style.backgroundPosition = 'center';
    preview.style.backgroundRepeat = 'no-repeat';
    preview.style.backgroundSize = 'cover';
    preview.style.boxShadow = '0 10px 28px rgba(0, 0, 0, 0.35)';
    preview.style.zIndex = '2147483647';
    document.body.appendChild(preview);
    return preview;
}

function simpleaiHandleNativeImageDragStart(event) {
    const img = simpleaiNativeImageDragPreviewImageFromEvent(event);
    const transfer = event?.dataTransfer;
    if (!img || !transfer) return;
    const preview = simpleaiCreateNativeImageDragPreview(img);
    if (!preview) return;
    try {
        transfer.setDragImage(preview, Math.round(preview.offsetWidth / 2), Math.round(preview.offsetHeight / 2));
    } catch (e) {}
    setTimeout(simpleaiRemoveNativeImageDragPreview, 0);
}

function modalImageSwitch(offset) {
    var galleryButtons = all_gallery_buttons();

    if (galleryButtons.length > 1) {
        var currentButton = selected_gallery_button();

        var result = -1;
        galleryButtons.forEach(function(v, i) {
            if (v == currentButton) {
                result = i;
            }
        });

        if (result != -1) {
            var nextButton = galleryButtons[negmod((result + offset), galleryButtons.length)];
            nextButton.click();
            const nextMedia = simpleaiGalleryButtonMedia(nextButton);
            const nextSrc = simpleaiMediaSrc(nextMedia);
            const modalImage = gradioApp().getElementById("modalImage");
            const modal = gradioApp().getElementById("lightboxModal");
            if (nextSrc) {
                modalImage.src = nextSrc;
                if (modalImage.style.display === 'none') {
                    modal.style.setProperty('background-image', `url(${modalImage.src})`);
                }
            }
            setTimeout(function() {
                modal.focus();
            }, 10);
        }
    }
}

function saveImage() {

}

function modalSaveImage(event) {
    event.stopPropagation();
}

function modalNextImage(event) {
    modalImageSwitch(1);
    event.stopPropagation();
}

function modalPrevImage(event) {
    modalImageSwitch(-1);
    event.stopPropagation();
}

function modalKeyHandler(event) {
    switch (event.key) {
    case "s":
        saveImage();
        break;
    case "ArrowLeft":
        modalPrevImage(event);
        break;
    case "ArrowRight":
        modalNextImage(event);
        break;
    case "Escape":
        closeModal();
        break;
    }
}

function setupImageForLightbox(e) {
    if (!simpleaiShouldUseLightboxImage(e)) {
        return;
    }
    if (e.dataset.modded) {
        return;
    }

    e.dataset.modded = true;
    e.style.cursor = 'pointer';
    e.style.userSelect = 'none';

    var isFirefox = navigator.userAgent.toLowerCase().indexOf('firefox') > -1;

    // For Firefox, listening on click first switched to next image then shows the lightbox.
    // If you know how to fix this without switching to mousedown event, please.
    // For other browsers the event is click to make it possiblr to drag picture.
    var event = isFirefox ? 'mousedown' : 'click';

    e.addEventListener(event, function(evt) {
        if (evt.button == 1) {
            open(evt.target.src);
            evt.preventDefault();
            return;
        }
        if (evt.button != 0) return;

        modalZoomSet(gradioApp().getElementById('modalImage'), true);
        evt.preventDefault();
        showModal(evt);
    }, true);

}

function simpleaiIsManagedGalleryGridMedia(elem) {
    if (!elem || !elem.closest) return false;
    return !!elem.closest('#finished_gallery .grid-wrap .gallery-item, #final_gallery .grid-wrap .gallery-item');
}

function simpleaiShouldUseLightboxImage(elem) {
    if (!elem || !elem.closest) return false;
    // Let Gradio 6 keep owning multi-gallery grid clicks so a tile opens the
    // native single-preview/toolbox mode instead of the custom fullscreen viewer.
    if (simpleaiIsManagedGalleryGridMedia(elem)) return false;
    return true;
}

function simpleaiLightboxImages() {
    const selector = [
        '.image_gallery > div > img',
        '#finished_gallery .gallery-container > .preview .media-button img',
        '#final_gallery .gallery-container > .preview .media-button img'
    ].join(', ');
    return Array.from(gradioApp().querySelectorAll(selector)).filter(simpleaiShouldUseLightboxImage);
}

function simpleaiBindGalleryLightbox() {
    simpleaiLightboxImages().forEach(setupImageForLightbox);
}

function simpleaiManagedGalleryRoot(elem) {
    if (!elem || !elem.closest) return null;
    return elem.closest('#finished_gallery, #final_gallery');
}

function simpleaiGalleryPreview(root) {
    return root && root.querySelector ? root.querySelector('.gallery-container > .preview') : null;
}

function simpleaiIsGalleryFullscreenButton(button) {
    if (!button) return false;
    if (button.querySelector('svg.feather-maximize, svg.feather-maximize-2, svg.feather-minimize, svg.feather-minimize-2')) return true;
    const icon = button.querySelector('svg');
    const iconLabel = icon ? [
        icon.getAttribute('class') || '',
        icon.getAttribute('data-testid') || '',
        icon.getAttribute('data-lucide') || '',
        icon.getAttribute('aria-label') || ''
    ].join(' ').toLowerCase() : '';
    if (iconLabel.includes('fullscreen') || iconLabel.includes('maximize') || iconLabel.includes('minimize')) return true;
    const label = [
        button.getAttribute('aria-label') || '',
        button.getAttribute('title') || '',
        button.textContent || ''
    ].join(' ').toLowerCase();
    return label.includes('fullscreen') || label.includes('full screen') || label.includes('maximize') || label.includes('minimize') || label.includes('全屏');
}

function simpleaiHandleGalleryFullscreenClick(event, button, root) {
    if (!event || !root || !button || !button.closest('.preview') || !simpleaiIsGalleryFullscreenButton(button)) return false;

    event.preventDefault();
    event.stopImmediatePropagation();

    const exiting = root.classList.contains('simpleai-gallery-fullscreen') || !!button.querySelector('svg.feather-minimize, svg.feather-minimize-2');
    if (exiting) {
        simpleaiExitGalleryFullscreen(true);
    } else {
        simpleaiEnterGalleryFullscreen(root);
    }
    setTimeout(simpleaiSyncGalleryStateSoon, 0);
    return true;
}

function simpleaiEnterGalleryFullscreen(root) {
    if (!root) return;
    root.classList.add('simpleai-gallery-fullscreen');
    document.documentElement.classList.add('simpleai-gallery-fullscreen-open');
    document.body.classList.add('simpleai-gallery-fullscreen-open');

    try {
        if (root.requestFullscreen && document.fullscreenElement !== root) {
            const fullscreenPromise = root.requestFullscreen();
            if (fullscreenPromise && fullscreenPromise.catch) fullscreenPromise.catch(() => {});
        }
    } catch (e) {
        // The fixed overlay CSS is still used when browser fullscreen is blocked.
    }
}

function simpleaiExitGalleryFullscreen(exitBrowserFullscreen) {
    const roots = document.querySelectorAll('#finished_gallery.simpleai-gallery-fullscreen, #final_gallery.simpleai-gallery-fullscreen');
    roots.forEach((root) => root.classList.remove('simpleai-gallery-fullscreen'));
    document.documentElement.classList.remove('simpleai-gallery-fullscreen-open');
    document.body.classList.remove('simpleai-gallery-fullscreen-open');

    if (exitBrowserFullscreen && document.fullscreenElement) {
        let fullscreenRoot = simpleaiManagedGalleryRoot(document.fullscreenElement);
        if (!fullscreenRoot && document.fullscreenElement.matches && document.fullscreenElement.matches('#finished_gallery, #final_gallery')) {
            fullscreenRoot = document.fullscreenElement;
        }
        if (fullscreenRoot) {
            try {
                const exitPromise = document.exitFullscreen?.();
                if (exitPromise && exitPromise.catch) exitPromise.catch(() => {});
            } catch (e) {
                // Ignore browser fullscreen exit failures.
            }
        }
    }
}

function simpleaiSyncGalleryFullscreenState() {
    document.querySelectorAll('#finished_gallery.simpleai-gallery-fullscreen, #final_gallery.simpleai-gallery-fullscreen').forEach((root) => {
        if (!simpleaiGalleryPreview(root)) {
            simpleaiExitGalleryFullscreen(false);
        }
    });
}

function simpleaiAnyManagedGalleryPreviewOpen() {
    if (document.querySelector('#finished_gallery .gallery-container > .preview, #final_gallery .gallery-container > .preview')) {
        return true;
    }
    if (document.documentElement.classList.contains('simpai-comparison-preview')) {
        const comparison = document.querySelector('#comparison_box');
        if (comparison) {
            const style = window.getComputedStyle ? window.getComputedStyle(comparison) : null;
            if (!style || (style.display !== 'none' && style.visibility !== 'hidden')) return true;
        }
    }
    const video = document.querySelector('#video_player');
    if (video) {
        const style = window.getComputedStyle ? window.getComputedStyle(video) : null;
        if (!style || (style.display !== 'none' && style.visibility !== 'hidden')) {
            if (video.querySelector('video') || video.tagName === 'VIDEO') return true;
        }
    }
    return false;
}

function simpleaiRevealGalleryToolbox(toolbox) {
    if (!toolbox) return;
    try {
        toolbox.classList.remove('simpleai-gallery-toolbox-hidden');
        toolbox.classList.remove('hidden');
        toolbox.classList.remove('hide');
    } catch (e) {}
    try { toolbox.removeAttribute('hidden'); } catch (e) {}
    try { toolbox.removeAttribute('aria-hidden'); } catch (e) {}
    try { toolbox.hidden = false; } catch (e) {}
    try { toolbox.style.removeProperty('display'); } catch (e) {}
    try { toolbox.style.removeProperty('visibility'); } catch (e) {}
    try { toolbox.style.removeProperty('pointer-events'); } catch (e) {}
    try {
        toolbox.querySelectorAll?.('button.toolbox_icon_btn, #compare_btn').forEach((button) => {
            button.classList.remove('simpleai-gallery-toolbox-hidden');
            button.classList.remove('hidden');
            button.removeAttribute('hidden');
            button.removeAttribute('aria-hidden');
            button.hidden = false;
            button.style.removeProperty('display');
            button.style.removeProperty('visibility');
            button.style.removeProperty('pointer-events');
        });
    } catch (e) {}
}

function simpleaiSyncGalleryToolboxState() {
    const imageToolsDisabled = document.documentElement.classList.contains('simpleai-image-tools-disabled');
    const hidden = imageToolsDisabled || !simpleaiAnyManagedGalleryPreviewOpen();
    const toolboxes = document.querySelectorAll(
        '#image_toolbox, .toolbox, .gr-group:has(> .styler > button.toolbox_icon_btn)'
    );
    toolboxes.forEach((toolbox) => {
        if (hidden) {
            toolbox.classList.add('simpleai-gallery-toolbox-hidden');
        } else {
            simpleaiRevealGalleryToolbox(toolbox);
        }
    });
}

function simpleaiSyncGalleryStateSoon() {
    simpleaiSyncGalleryFullscreenState();
    simpleaiSyncGalleryToolboxState();
    setTimeout(() => {
        simpleaiSyncGalleryFullscreenState();
        simpleaiSyncGalleryToolboxState();
    }, 60);
    setTimeout(() => {
        simpleaiSyncGalleryFullscreenState();
        simpleaiSyncGalleryToolboxState();
    }, 180);
}

const simpleaiComparisonSliderStates = new WeakMap();
let simpleaiActiveComparisonPan = null;

function simpleaiComparisonSliderScope() {
    try {
        if (typeof gradioApp === "function") return gradioApp();
    } catch (e) {}
    return document;
}

function simpleaiClampNumber(value, min, max) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return min;
    return Math.min(Math.max(numeric, min), max);
}

function simpleaiParseTransformState(transformText) {
    const fallback = { x: 0, y: 0, scale: 1 };
    if (!transformText || transformText === "none") return fallback;

    const matrix = transformText.match(/^matrix\(([^)]+)\)$/);
    if (matrix) {
        const parts = matrix[1].split(",").map((part) => Number(part.trim()));
        if (parts.length >= 6 && parts.every(Number.isFinite)) {
            return { x: parts[4], y: parts[5], scale: parts[0] || 1 };
        }
    }

    const translate = transformText.match(/translate(?:3d)?\(\s*([-.\d]+)px\s*,\s*([-.\d]+)px/i);
    const scale = transformText.match(/scale\(\s*([-.\d]+)/i);
    return {
        x: translate ? Number(translate[1]) || 0 : 0,
        y: translate ? Number(translate[2]) || 0 : 0,
        scale: scale ? Number(scale[1]) || 1 : 1
    };
}

function simpleaiComparisonElements(root) {
    if (!root || !root.querySelector) return null;
    const content = root.querySelector(".slider-wrap .wrap .content") || root.querySelector(".content");
    const wrap = root.querySelector(".slider-wrap .wrap") || root.querySelector(".wrap");
    const handle = root.querySelector(".slider-wrap .wrap .outer") || root.querySelector(".outer");
    const images = Array.from(root.querySelectorAll(".slider-wrap .content img.preview, .content img.preview, .slider-wrap .content img, .content img"))
        .filter((img, index, list) => list.indexOf(img) === index);
    if (!content || !wrap || images.length < 2) return null;
    return { content, wrap, handle, images, primary: images[0], overlay: images[1] };
}

function simpleaiComparisonVisible(root) {
    if (!root || !root.isConnected) return false;
    const style = window.getComputedStyle ? window.getComputedStyle(root) : null;
    if (style && (style.display === "none" || style.visibility === "hidden")) return false;
    const rect = root.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
}

function simpleaiComparisonGetState(root, els) {
    let state = simpleaiComparisonSliderStates.get(root);
    const signature = els.images.map((img) => img.currentSrc || img.src || "").join("|");
    if (!state || state.signature !== signature) {
        const parsed = simpleaiParseTransformState(els.primary.style.transform || window.getComputedStyle(els.primary).transform);
        state = {
            x: parsed.x,
            y: parsed.y,
            scale: simpleaiClampNumber(parsed.scale, 1, 15),
            position: 0.5,
            signature,
            scheduled: false,
            observer: state && state.observer,
            resizeObserver: state && state.resizeObserver
        };
        simpleaiComparisonSliderStates.set(root, state);
    }
    return state;
}

function simpleaiComparisonImageBase(els, state) {
    const contentRect = els.content.getBoundingClientRect();
    if (contentRect.width <= 0 || contentRect.height <= 0) return null;

    const naturalWidth = els.primary.naturalWidth || els.overlay.naturalWidth || 0;
    const naturalHeight = els.primary.naturalHeight || els.overlay.naturalHeight || 0;
    if (naturalWidth > 0 && naturalHeight > 0) {
        const naturalAspect = naturalWidth / naturalHeight;
        const containerAspect = contentRect.width / contentRect.height;
        const width = naturalAspect > containerAspect ? contentRect.width : contentRect.height * naturalAspect;
        const height = naturalAspect > containerAspect ? contentRect.width / naturalAspect : contentRect.height;
        return {
            left: (contentRect.width - width) / 2,
            top: (contentRect.height - height) / 2,
            width,
            height,
            originX: 0,
            originY: 0,
            clipBoxLeft: (contentRect.width - width) / 2,
            clipBoxTop: (contentRect.height - height) / 2,
            clipBoxWidth: width,
            clipBoxHeight: height,
            clipOriginX: 0,
            clipOriginY: 0,
            viewportWidth: contentRect.width,
            viewportHeight: contentRect.height,
            contentRect
        };
    }

    const scale = simpleaiClampNumber(state.scale, 1, 15) || 1;
    const imageRect = els.primary.getBoundingClientRect();
    if (imageRect.width <= 0 || imageRect.height <= 0) return null;
    return {
        left: imageRect.left - contentRect.left - state.x,
        top: imageRect.top - contentRect.top - state.y,
        width: imageRect.width / scale,
        height: imageRect.height / scale,
        originX: 0,
        originY: 0,
        clipBoxLeft: imageRect.left - contentRect.left - state.x,
        clipBoxTop: imageRect.top - contentRect.top - state.y,
        clipBoxWidth: imageRect.width / scale,
        clipBoxHeight: imageRect.height / scale,
        clipOriginX: 0,
        clipOriginY: 0,
        viewportWidth: contentRect.width,
        viewportHeight: contentRect.height,
        contentRect
    };
}

function simpleaiComparisonReadHandlePosition(els, base) {
    if (!els.handle || !base || base.width <= 0) return null;
    const transformText = els.handle.style.transform || window.getComputedStyle(els.handle).transform;
    let px = null;
    const matrix = transformText && transformText.match(/^matrix\(([^)]+)\)$/);
    if (matrix) {
        const parts = matrix[1].split(",").map((part) => Number(part.trim()));
        if (parts.length >= 6 && Number.isFinite(parts[4])) px = parts[4];
    }
    if (px === null) {
        const translated = transformText && transformText.match(/translateX\(\s*([-.\d]+)px/i);
        if (translated) px = Number(translated[1]);
    }
    if (px === null) {
        const handleRect = els.handle.getBoundingClientRect();
        const wrapRect = els.wrap.getBoundingClientRect();
        if (handleRect.width > 0 && wrapRect.width > 0) {
            px = handleRect.left - wrapRect.left + (handleRect.width / 2);
        }
    }
    if (px === null || !Number.isFinite(px)) return null;
    return simpleaiClampNumber((px - base.left) / base.width, 0, 1);
}

function simpleaiComparisonConstrain(state, base) {
    if (!state || !base) return;
    state.scale = simpleaiClampNumber(state.scale, 1, 15);
    if (state.scale <= 1.0001) {
        state.scale = 1;
        state.x = 0;
        state.y = 0;
        return;
    }

    const minX = base.width * (1 - state.scale);
    const minY = base.height * (1 - state.scale);
    state.x = simpleaiClampNumber(state.x, minX, 0);
    state.y = simpleaiClampNumber(state.y, minY, 0);
}

function simpleaiSetStyleProperty(el, prop, value) {
    if (!el || !el.style) return;
    if (el.style[prop] !== value) el.style[prop] = value;
}

function simpleaiSetImportantCssProperty(el, prop, value) {
    if (!el || !el.style) return;
    if (el.style.getPropertyValue(prop) !== value || el.style.getPropertyPriority(prop) !== "important") {
        el.style.setProperty(prop, value, "important");
    }
}

function simpleaiApplyComparisonImageGeometry(els, base) {
    if (!els || !base) return;
    simpleaiSetImportantCssProperty(els.content, "position", "relative");
    simpleaiSetImportantCssProperty(els.content, "overflow", "hidden");
    const left = `${base.left}px`;
    const top = `${base.top}px`;
    const width = `${base.width}px`;
    const height = `${base.height}px`;
    els.images.forEach((img) => {
        simpleaiSetImportantCssProperty(img, "position", "absolute");
        simpleaiSetImportantCssProperty(img, "left", left);
        simpleaiSetImportantCssProperty(img, "top", top);
        simpleaiSetImportantCssProperty(img, "right", "auto");
        simpleaiSetImportantCssProperty(img, "bottom", "auto");
        simpleaiSetImportantCssProperty(img, "width", width);
        simpleaiSetImportantCssProperty(img, "height", height);
        simpleaiSetImportantCssProperty(img, "min-width", "0px");
        simpleaiSetImportantCssProperty(img, "min-height", "0px");
        simpleaiSetImportantCssProperty(img, "max-width", "none");
        simpleaiSetImportantCssProperty(img, "max-height", "none");
        simpleaiSetImportantCssProperty(img, "object-fit", "fill");
    });
}

function simpleaiApplyComparisonSliderState(root, reason) {
    if (!simpleaiComparisonVisible(root)) return;
    const els = simpleaiComparisonElements(root);
    if (!els) return;
    const state = simpleaiComparisonGetState(root, els);
    const base = simpleaiComparisonImageBase(els, state);
    if (!base || base.width <= 0 || base.height <= 0) return;

    simpleaiApplyComparisonImageGeometry(els, base);
    const handlePosition = simpleaiComparisonReadHandlePosition(els, base);
    if (handlePosition !== null && reason !== "wheel" && reason !== "pan") {
        state.position = handlePosition;
    }
    state.position = simpleaiClampNumber(state.position, 0, 1);
    simpleaiComparisonConstrain(state, base);

    const transform = `translate(${state.x}px, ${state.y}px) scale(${state.scale})`;
    els.images.forEach((img) => {
        const originX = img === els.overlay ? base.clipOriginX : base.originX;
        const originY = img === els.overlay ? base.clipOriginY : base.originY;
        simpleaiSetImportantCssProperty(img, "transform-origin", `${originX}px ${originY}px`);
        simpleaiSetStyleProperty(img, "transform", transform);
        simpleaiSetStyleProperty(img, "cursor", state.scale > 1 ? "grab" : "zoom-in");
    });

    const handlePx = simpleaiClampNumber(base.left + base.width * state.position, 0, base.viewportWidth);
    const splitPx = base.left + base.width * state.position;
    const clipLocalPx = base.clipOriginX + ((splitPx - base.clipBoxLeft - base.clipOriginX - state.x) / state.scale);
    const clipPosition = simpleaiClampNumber(clipLocalPx / (base.clipBoxWidth || base.width), 0, 1);
    const clipPath = `inset(0 0 0 ${clipPosition * 100}%)`;
    simpleaiSetStyleProperty(els.overlay, "clipPath", clipPath);
    simpleaiSetStyleProperty(els.overlay, "webkitClipPath", clipPath);
    if (els.handle) {
        simpleaiSetStyleProperty(els.handle, "transform", `translateX(${handlePx}px)`);
    }
}

function simpleaiScheduleComparisonSliderSync(root, reason) {
    if (!root) return;
    const state = simpleaiComparisonSliderStates.get(root) || {};
    if (state.scheduled) return;
    state.scheduled = true;
    simpleaiComparisonSliderStates.set(root, state);
    requestAnimationFrame(() => {
        state.scheduled = false;
        simpleaiApplyComparisonSliderState(root, reason || "scheduled");
    });
}

function simpleaiComparisonPointInImage(event, base, state) {
    const x = event.clientX - base.contentRect.left;
    const y = event.clientY - base.contentRect.top;
    const left = base.left + state.x;
    const top = base.top + state.y;
    return x >= left && x <= left + base.width * state.scale && y >= top && y <= top + base.height * state.scale;
}

function simpleaiComparisonWheel(event, root) {
    const els = simpleaiComparisonElements(root);
    if (!els) return;
    const state = simpleaiComparisonGetState(root, els);
    const base = simpleaiComparisonImageBase(els, state);
    if (!base || !simpleaiComparisonPointInImage(event, base, state)) return;

    event.preventDefault();
    event.stopImmediatePropagation();

    const oldScale = state.scale || 1;
    const zoomFactor = event.deltaY < 0 ? 1.08 : 1 / 1.08;
    const newScale = simpleaiClampNumber(oldScale * zoomFactor, 1, 15);
    if (Math.abs(newScale - oldScale) < 0.0001) return;

    const cursorX = event.clientX - base.contentRect.left - base.left;
    const cursorY = event.clientY - base.contentRect.top - base.top;
    state.scale = newScale;
    state.x = cursorX - (newScale / oldScale) * (cursorX - state.x);
    state.y = cursorY - (newScale / oldScale) * (cursorY - state.y);
    simpleaiComparisonConstrain(state, base);
    simpleaiApplyComparisonSliderState(root, "wheel");
}

function simpleaiComparisonMouseDown(event, root) {
    if (event.button !== 0 || event.target.closest?.(".outer, .icon-wrap, button, a")) return;
    const els = simpleaiComparisonElements(root);
    if (!els) return;
    const state = simpleaiComparisonGetState(root, els);
    const base = simpleaiComparisonImageBase(els, state);
    if (!base || state.scale <= 1 || !simpleaiComparisonPointInImage(event, base, state)) return;

    event.preventDefault();
    event.stopImmediatePropagation();
    simpleaiActiveComparisonPan = { root, lastX: event.clientX, lastY: event.clientY };
    els.images.forEach((img) => simpleaiSetStyleProperty(img, "cursor", "grabbing"));
}

function simpleaiComparisonDocumentMouseMove(event) {
    if (!simpleaiActiveComparisonPan) return;
    const root = simpleaiActiveComparisonPan.root;
    const els = simpleaiComparisonElements(root);
    if (!els) return;
    const state = simpleaiComparisonGetState(root, els);
    const base = simpleaiComparisonImageBase(els, state);
    if (!base) return;

    state.x += event.clientX - simpleaiActiveComparisonPan.lastX;
    state.y += event.clientY - simpleaiActiveComparisonPan.lastY;
    simpleaiActiveComparisonPan.lastX = event.clientX;
    simpleaiActiveComparisonPan.lastY = event.clientY;
    simpleaiComparisonConstrain(state, base);
    simpleaiApplyComparisonSliderState(root, "pan");
}

function simpleaiComparisonDocumentMouseUp() {
    if (!simpleaiActiveComparisonPan) return;
    const root = simpleaiActiveComparisonPan.root;
    simpleaiActiveComparisonPan = null;
    simpleaiScheduleComparisonSliderSync(root, "pan_end");
}

function simpleaiInstallComparisonSliderPatch(root) {
    if (!root) return;
    const els = simpleaiComparisonElements(root);
    if (!els) return;

    const state = simpleaiComparisonGetState(root, els);

    if (els.content.dataset.simpleaiComparisonSliderContentPatched !== "1") {
        els.content.dataset.simpleaiComparisonSliderContentPatched = "1";
        const wheelHandler = (event) => simpleaiComparisonWheel(event, root);
        const mouseDownHandler = (event) => simpleaiComparisonMouseDown(event, root);
        els.content.addEventListener("wheel", wheelHandler, { capture: true, passive: false });
        els.content.addEventListener("mousedown", mouseDownHandler, { capture: true });
    }

    if (root.dataset.simpleaiComparisonSliderPatched !== "1") {
        root.dataset.simpleaiComparisonSliderPatched = "1";
        const observer = new MutationObserver(() => simpleaiScheduleComparisonSliderSync(root, "mutation"));
        observer.observe(root, { subtree: true, childList: true, attributes: true, attributeFilter: ["style", "class", "src"] });
        state.observer = observer;

        const resizeObserver = new ResizeObserver(() => simpleaiScheduleComparisonSliderSync(root, "resize"));
        resizeObserver.observe(root);
        state.resizeObserver = resizeObserver;
    }

    if (state.resizeObserver) {
        state.resizeObserver.observe(els.content);
        els.images.forEach((img) => {
            if (img.dataset.simpleaiComparisonResizeObserved !== "1") {
                img.dataset.simpleaiComparisonResizeObserved = "1";
                state.resizeObserver.observe(img);
                img.addEventListener("load", () => simpleaiScheduleComparisonSliderSync(root, "image_load"));
            }
        });
    }

    simpleaiScheduleComparisonSliderSync(root, "install");
}

function simpleaiSyncComparisonSliders() {
    const scope = simpleaiComparisonSliderScope();
    scope.querySelectorAll?.("#comparison_box").forEach(simpleaiInstallComparisonSliderPatch);
}

document.addEventListener("mousemove", simpleaiComparisonDocumentMouseMove, true);
document.addEventListener("mouseup", simpleaiComparisonDocumentMouseUp, true);
document.addEventListener('dragstart', simpleaiHandleNativeImageDragStart, true);
document.addEventListener('dragend', simpleaiRemoveNativeImageDragPreview, true);
window.addEventListener("resize", () => {
    const scope = simpleaiComparisonSliderScope();
    scope.querySelectorAll?.("#comparison_box").forEach((root) => simpleaiScheduleComparisonSliderSync(root, "window_resize"));
});

if (typeof onUiLoaded === "function") {
    onUiLoaded(async () => {
        simpleaiSyncComparisonSliders();
        setTimeout(simpleaiSyncComparisonSliders, 100);
        setTimeout(simpleaiSyncComparisonSliders, 600);
    });
}
setInterval(simpleaiSyncComparisonSliders, 1500);
window.simpleaiSyncComparisonSliders = simpleaiSyncComparisonSliders;

document.addEventListener('click', function(event) {
    const target = event.target;
    if (!target || !target.closest) return;
    if (simpleaiManagedGalleryRoot(target)) {
        setTimeout(simpleaiSyncGalleryStateSoon, 0);
    }

    const outputDeleteButton = target.closest('#finished_gallery .delete-button, #final_gallery .delete-button');
    if (outputDeleteButton) {
        event.preventDefault();
        event.stopImmediatePropagation();
        return;
    }

    const button = target.closest('button');
    const root = simpleaiManagedGalleryRoot(button);
    if (simpleaiHandleGalleryFullscreenClick(event, button, root)) return;
}, true);

document.addEventListener('click', function(event) {
    const target = event.target;
    if (target && target.closest && target.closest('#finished_gallery, #final_gallery')) {
        setTimeout(simpleaiSyncGalleryStateSoon, 0);
    }
}, false);

document.addEventListener('fullscreenchange', function() {
    if (!document.fullscreenElement) {
        simpleaiExitGalleryFullscreen(false);
    }
});

document.addEventListener('keydown', function(event) {
    if (event && event.key === 'Escape') {
        setTimeout(simpleaiSyncGalleryStateSoon, 0);
    }
}, true);

function modalZoomSet(modalImage, enable) {
    if (modalImage) modalImage.classList.toggle('modalImageFullscreen', !!enable);
}

function modalZoomToggle(event) {
    var modalImage = gradioApp().getElementById("modalImage");
    modalZoomSet(modalImage, !modalImage.classList.contains('modalImageFullscreen'));
    event.stopPropagation();
}

function modalTileImageToggle(event) {
    const modalImage = gradioApp().getElementById("modalImage");
    const modal = gradioApp().getElementById("lightboxModal");
    const isTiling = modalImage.style.display === 'none';
    if (isTiling) {
        modalImage.style.display = 'block';
        modal.style.setProperty('background-image', 'none');
    } else {
        modalImage.style.display = 'none';
        modal.style.setProperty('background-image', `url(${modalImage.src})`);
    }

    event.stopPropagation();
}

onAfterUiUpdate(function() {
    simpleaiBindGalleryLightbox();
    simpleaiSyncGalleryFullscreenState();
    simpleaiSyncGalleryToolboxState();
    updateOnBackgroundChange();
});

document.addEventListener("DOMContentLoaded", function() {
    //const modalFragment = document.createDocumentFragment();
    const modal = document.createElement('div');
    modal.onclick = closeModal;
    modal.id = "lightboxModal";
    modal.tabIndex = 0;
    modal.addEventListener('keydown', modalKeyHandler, true);

    const modalControls = document.createElement('div');
    modalControls.className = 'modalControls gradio-container';
    modal.append(modalControls);

    const modalZoom = document.createElement('span');
    modalZoom.className = 'modalZoom cursor';
    modalZoom.innerHTML = '&#10529;';
    modalZoom.addEventListener('click', modalZoomToggle, true);
    modalZoom.title = "Toggle zoomed view";
    modalControls.appendChild(modalZoom);

    // const modalTileImage = document.createElement('span');
    // modalTileImage.className = 'modalTileImage cursor';
    // modalTileImage.innerHTML = '&#8862;';
    // modalTileImage.addEventListener('click', modalTileImageToggle, true);
    // modalTileImage.title = "Preview tiling";
    // modalControls.appendChild(modalTileImage);
    //
    // const modalSave = document.createElement("span");
    // modalSave.className = "modalSave cursor";
    // modalSave.id = "modal_save";
    // modalSave.innerHTML = "&#x1F5AB;";
    // modalSave.addEventListener("click", modalSaveImage, true);
    // modalSave.title = "Save Image(s)";
    // modalControls.appendChild(modalSave);

    const modalClose = document.createElement('span');
    modalClose.className = 'modalClose cursor';
    modalClose.innerHTML = '&times;';
    modalClose.onclick = closeModal;
    modalClose.title = "Close image viewer";
    modalControls.appendChild(modalClose);

    const modalImage = document.createElement('img');
    modalImage.id = 'modalImage';
    modalImage.onclick = closeModal;
    modalImage.tabIndex = 0;
    modalImage.addEventListener('keydown', modalKeyHandler, true);
    modal.appendChild(modalImage);

    const modalPrev = document.createElement('a');
    modalPrev.className = 'modalPrev';
    modalPrev.innerHTML = '&#10094;';
    modalPrev.tabIndex = 0;
    modalPrev.addEventListener('click', modalPrevImage, true);
    modalPrev.addEventListener('keydown', modalKeyHandler, true);
    modal.appendChild(modalPrev);

    const modalNext = document.createElement('a');
    modalNext.className = 'modalNext';
    modalNext.innerHTML = '&#10095;';
    modalNext.tabIndex = 0;
    modalNext.addEventListener('click', modalNextImage, true);
    modalNext.addEventListener('keydown', modalKeyHandler, true);

    modal.appendChild(modalNext);

    try {
        gradioApp().appendChild(modal);
    } catch (e) {
        gradioApp().body.appendChild(modal);
    }

    document.body.appendChild(modal);

});
