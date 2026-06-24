(function () {
    'use strict';

    const UTILS = window.SimpAICanvasWorkbenchUtils || {};
    const escapeHtml = UTILS.escapeHtml || ((value) => String(value ?? ''));
    const t = UTILS.t || ((en, cn) => cn || en);

    function assetsApi() {
        return window.SimpAICanvasWorkbenchAssetNodes || {};
    }

    function assetDisplaySrc(asset, context) {
        if (typeof context?.assetDisplaySrc === 'function') return context.assetDisplaySrc(asset || {});
        const api = assetsApi();
        if (typeof api.assetDisplaySrc === 'function') return api.assetDisplaySrc(asset || {});
        return asset?.data_url || asset?.preview_url || asset?.thumb || '';
    }

    function nodeImageSrc(node, context) {
        if (typeof context?.getNodeImageSrc === 'function') {
            const src = context.getNodeImageSrc(node || {});
            if (src) return src;
        }
        return assetDisplaySrc(node?.asset, context);
    }

    function readImageInfo(node, context) {
        if (typeof context?.readImageInfo === 'function') return context.readImageInfo(node || {});
        const api = assetsApi();
        return typeof api.readImageInfo === 'function' ? api.readImageInfo(node || {}) : [];
    }

    function mediaAspectStyle(asset, context) {
        if (typeof context?.mediaAspectStyle === 'function') return context.mediaAspectStyle(asset || {});
        const api = assetsApi();
        return typeof api.mediaAspectStyle === 'function' ? api.mediaAspectStyle(asset || {}) : '';
    }

    function readAssetSize(asset, context) {
        if (typeof context?.readAssetSize === 'function') return context.readAssetSize(asset || {});
        const api = assetsApi();
        return typeof api.readAssetSize === 'function' ? api.readAssetSize(asset || {}) : '';
    }

    function renderNodeHtml(node, context) {
        const ctx = context || {};
        const image = nodeImageSrc(node, ctx);
        const mask = node.mask && (node.mask.thumb || node.mask.data_url);
        const info = readImageInfo(node, ctx);
        const stateBadges = typeof ctx.renderNodeStateBadges === 'function' ? ctx.renderNodeStateBadges(node) : '';
        const aspect = mediaAspectStyle(node.asset, ctx);
        const displayMode = String(node.display_mode || node.image_display_mode || '').toLowerCase();
        const frameless = displayMode !== 'card';
        const emptyUpload = `<button type="button" class="sai-node-empty sai-image-empty-upload" data-node-action="replace-image">${escapeHtml(t('No image', '无图像'))}</button>`;
        return `
<div class="sai-node-head">
  <span class="sai-node-kind">${escapeHtml(t('Image', '图像'))}</span>
  <span class="sai-node-title">${escapeHtml(node.title || t('Image', '图像'))}</span>
  ${stateBadges}
  <button type="button" data-node-action="view-image" title="${escapeHtml(t('View image', '查看图像'))}"><i class="fa-solid fa-magnifying-glass-plus"></i></button>
  <button type="button" data-node-action="sketch-edit" title="${escapeHtml(t('Edit in Sketch', '在 Sketch 中编辑'))}"><i class="fa-solid fa-pen-ruler"></i></button>
  <button type="button" data-node-action="layerforge-edit" title="${escapeHtml(t('Edit in LayerForge', '在 LayerForge 中编辑'))}"><i class="fa-solid fa-layer-group"></i></button>
  <button type="button" data-node-action="edit-mask" title="${escapeHtml(t('Edit Mask', '编辑遮罩'))}"><i class="fa-solid fa-paintbrush"></i></button>
  <button type="button" class="${frameless ? 'is-active' : ''}" data-node-action="toggle-image-frameless" title="${escapeHtml(frameless ? t('Show image frame', '显示图像边框') : t('Hide image frame', '隐藏图像边框'))}"><i class="fa-solid fa-border-none"></i></button>
  <button type="button" data-node-action="replace-image" title="${escapeHtml(t('Replace image', '替换图像'))}"><i class="fa-solid fa-arrows-rotate"></i></button>
  <button type="button" class="sai-node-close" data-node-action="delete" title="${escapeHtml(t('Delete', '删除'))}"><i class="fa-solid fa-xmark"></i></button>
</div>
<div class="sai-node-media sai-image-node-media sai-collapsed-keep${frameless ? ' is-frameless' : ''}${image ? '' : ' is-empty-upload'}" data-image-drop-zone${aspect}>${image ? `<img src="${escapeHtml(image)}" alt="" draggable="false">${mask ? `<img class="sai-mask-overlay" src="${escapeHtml(mask)}" alt="" draggable="false">` : ''}` : emptyUpload}</div>
<div class="sai-node-info">${info.map(bit => `<span>${escapeHtml(bit)}</span>`).join('') || `<span>${escapeHtml(t('No metadata', '无元数据'))}</span>`}</div>
<button type="button" class="sai-node-handle sai-node-handle-out" data-handle-out="image" title="${escapeHtml(t('Output', '输出'))}"></button>`;
    }

    function renderInspector(node) {
        const info = readImageInfo(node);
        const size = readAssetSize(node.asset);
        return `
<div class="sai-inspector-section">
  <h3>${escapeHtml(t('Image Node', '图像节点'))}</h3>
  <label>${escapeHtml(t('Title', '标题'))}<input data-inspector-node-field="title" value="${escapeHtml(node.title || '')}"></label>
  <div class="sai-inspector-kv"><span>${escapeHtml(t('Type', '类型'))}</span><b>${escapeHtml(node.asset?.mime || 'image')}</b></div>
  <div class="sai-inspector-kv"><span>${escapeHtml(t('Size', '尺寸'))}</span><b>${escapeHtml(size)}</b></div>
  <div class="sai-inspector-kv"><span>${escapeHtml(t('Info', '信息'))}</span><b>${escapeHtml(info.join(' / ') || t('None', '无'))}</b></div>
</div>
<div class="sai-inspector-actions">
  <button type="button" data-inspector-action="view-image"><i class="fa-solid fa-magnifying-glass-plus"></i><span>${escapeHtml(t('View', '查看'))}</span></button>
  <button type="button" data-inspector-action="sketch-edit"><i class="fa-solid fa-pen-ruler"></i><span>Sketch</span></button>
  <button type="button" data-inspector-action="layerforge-edit"><i class="fa-solid fa-layer-group"></i><span>LayerForge</span></button>
  <button type="button" data-inspector-action="replace-image"><i class="fa-solid fa-arrows-rotate"></i><span>${escapeHtml(t('Replace', '替换'))}</span></button>
  <button type="button" data-inspector-action="edit-mask"><i class="fa-solid fa-paintbrush"></i><span>${escapeHtml(t('Mask', '遮罩'))}</span></button>
  <button type="button" data-inspector-action="duplicate"><i class="fa-solid fa-copy"></i><span>${escapeHtml(t('Duplicate', '复制'))}</span></button>
  <button type="button" data-inspector-action="delete" class="danger"><i class="fa-solid fa-trash"></i><span>${escapeHtml(t('Delete', '删除'))}</span></button>
</div>`;
    }

    window.SimpAICanvasWorkbenchImageNode = {
        renderNodeHtml,
        renderInspector
    };
})();
