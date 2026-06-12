(function () {
    'use strict';

    const UTILS = window.SimpAICanvasWorkbenchUtils || {};
    const ASSETS = window.SimpAICanvasWorkbenchAssetNodes || {};
    const escapeHtml = UTILS.escapeHtml || ((value) => String(value ?? ''));
    const t = UTILS.t || ((en, cn) => cn || en);
    const formatDuration = ASSETS.formatDuration || ((seconds) => `${Math.round(Number(seconds || 0) * 10) / 10}s`);

    function mediaRange(asset) {
        if (typeof ASSETS.mediaEditRange === 'function') return ASSETS.mediaEditRange(asset);
        const duration = Math.max(0, Number(asset?.duration || 0) || 0);
        const edit = asset?.edit && typeof asset.edit === 'object' ? asset.edit : {};
        const start = Math.max(0, Number(edit.trim_start || 0) || 0);
        const end = Math.max(start, Number(edit.trim_end || duration || 0) || duration || start);
        return { start, end, duration, clipped: duration > 0 && (start > 0.01 || end < duration - 0.01) };
    }

    function renderStoryboard(asset, range) {
        const frames = Array.isArray(asset?.preview_frames) ? asset.preview_frames.filter(Boolean).slice(0, 10) : [];
        const startPct = range.duration > 0 ? Math.max(0, Math.min(100, (range.start / range.duration) * 100)) : 0;
        const endPct = range.duration > 0 ? Math.max(startPct, Math.min(100, (range.end / range.duration) * 100)) : 100;
        const body = frames.length
            ? frames.map(frame => `<img src="${escapeHtml(frame.thumb || frame.data_url || '')}" alt="" draggable="false">`).join('')
            : '<div class="sai-media-storyboard-empty"><i class="fa-solid fa-film"></i></div>';
        return `<div class="sai-media-storyboard" style="--trim-start:${startPct}%;--trim-end:${endPct}%">${body}<i></i></div>`;
    }

    function renderTrimControls(node, range, disabled) {
        const duration = Math.max(0.1, Number(range.duration || 0) || 0.1);
        const step = duration > 60 ? 0.1 : 0.05;
        return `
<div class="sai-media-trim" data-media-trim-ui>
  <div class="sai-media-trim-time"><span>${escapeHtml(formatDuration(range.start))}</span><b>${escapeHtml(formatDuration(Math.max(0, range.end - range.start)))}</b><span>${escapeHtml(formatDuration(range.end || range.duration))}</span></div>
  <input class="sai-media-scrub" type="range" data-media-seek value="${range.start}" min="0" max="${duration}" step="${step}" ${disabled ? 'disabled' : ''}>
  <div class="sai-media-range-pair">
    <input type="range" data-media-trim-start value="${range.start}" min="0" max="${duration}" step="${step}" ${disabled ? 'disabled' : ''}>
    <input type="range" data-media-trim-end value="${range.end || duration}" min="0" max="${duration}" step="${step}" ${disabled ? 'disabled' : ''}>
  </div>
</div>`;
    }

    function renderDerivedInfo(asset, range) {
        const fps = Number(asset?.fps || 0) || 0;
        const totalFrames = Number(asset?.frame_count || 0) || (fps && range.duration ? Math.round(fps * range.duration) : 0);
        const clipDuration = Math.max(0, range.end - range.start);
        const clipFrames = fps && clipDuration ? Math.max(1, Math.round(fps * clipDuration)) : 0;
        const bits = [];
        if (fps) bits.push(`<span>FPS</span><b>${escapeHtml(String(Math.round(fps * 1000) / 1000))}</b>`);
        if (totalFrames) bits.push(`<span>${escapeHtml(t('Total Frames', '总帧数'))}</span><b>${escapeHtml(String(Math.round(totalFrames)))}</b>`);
        if (range.duration) bits.push(`<span>${escapeHtml(t('Clip Duration', '剪辑时长'))}</span><b>${escapeHtml(formatDuration(clipDuration))}</b>`);
        if (clipFrames) bits.push(`<span>${escapeHtml(t('Clip Frames', '剪辑帧数'))}</span><b>${escapeHtml(String(clipFrames))}</b>`);
        return `<div class="sai-media-derived-info" data-media-derived-info>${bits.length ? bits.join('') : `<span>${escapeHtml(t('Media', '媒体'))}</span><b>${escapeHtml(t('Metadata pending', '等待元数据'))}</b>`}</div>`;
    }

    function renderNodeHtml(node, context) {
        const ctx = context || {};
        const src = ASSETS.assetDisplaySrc ? ASSETS.assetDisplaySrc(node.asset) : (node.asset?.data_url || node.asset?.preview_url || '');
        const info = ASSETS.readAssetInfo ? ASSETS.readAssetInfo(node.asset || {}, false) : [];
        const stateBadges = typeof ctx.renderNodeStateBadges === 'function' ? ctx.renderNodeStateBadges(node) : '';
        const aspect = ASSETS.mediaAspectStyle ? ASSETS.mediaAspectStyle(node.asset) : '';
        const range = mediaRange(node.asset || {});
        const disabled = !!node.locked || !src || !range.duration;
        return `
<div class="sai-node-head">
  <span class="sai-node-kind">${escapeHtml(t('Video', '视频'))}</span>
  <span class="sai-node-title">${escapeHtml(node.title || t('Video', '视频'))}</span>
  ${stateBadges}
  <button type="button" data-node-action="media-reload" title="${escapeHtml(t('Re-upload video asset', '重新上传视频资产'))}"><i class="fa-solid fa-rotate"></i></button>
  <button type="button" data-node-action="view-media" title="${escapeHtml(t('View video', '查看视频'))}"><i class="fa-solid fa-magnifying-glass-plus"></i></button>
  <button type="button" data-node-action="media-play-toggle" title="${escapeHtml(t('Play selection', '播放选区'))}"><i class="fa-solid fa-play"></i></button>
  <button type="button" data-node-action="delete" title="${escapeHtml(t('Delete', '删除'))}"><i class="fa-solid fa-xmark"></i></button>
</div>
<div class="sai-node-media sai-node-video-media"${aspect}>${src ? `<video src="${escapeHtml(src)}" muted preload="metadata" data-media-player></video><img class="sai-video-drag-preview" data-video-drag-preview alt="" hidden draggable="false">` : `<div class="sai-node-empty">${escapeHtml(t('No video', '无视频'))}</div>`}</div>
${renderStoryboard(node.asset || {}, range)}
${renderTrimControls(node, range, disabled)}
${renderDerivedInfo(node.asset || {}, range)}
<div class="sai-node-info">${info.map(bit => `<span>${escapeHtml(bit)}</span>`).join('') || `<span>${escapeHtml(t('No metadata', '无元数据'))}</span>`}</div>
<button type="button" class="sai-node-handle sai-node-handle-out" data-handle-out="video" title="${escapeHtml(t('Output', '输出'))}"></button>`;
    }

    function renderInspector(node) {
        const info = ASSETS.readAssetInfo ? ASSETS.readAssetInfo(node.asset || {}, false) : [];
        const size = ASSETS.readAssetSize ? ASSETS.readAssetSize(node.asset) : '';
        return `
<div class="sai-inspector-section">
  <h3>${escapeHtml(t('Video Node', '视频节点'))}</h3>
  <label>${escapeHtml(t('Title', '标题'))}<input data-inspector-node-field="title" value="${escapeHtml(node.title || '')}"></label>
  <div class="sai-inspector-kv"><span>${escapeHtml(t('Type', '类型'))}</span><b>${escapeHtml(node.asset?.mime || 'video')}</b></div>
  <div class="sai-inspector-kv"><span>${escapeHtml(t('Size', '尺寸'))}</span><b>${escapeHtml(size)}</b></div>
  <div class="sai-inspector-kv"><span>${escapeHtml(t('Info', '信息'))}</span><b>${escapeHtml(info.join(' / ') || t('None', '无'))}</b></div>
  ${renderTrimControls(node, mediaRange(node.asset || {}), !!node.locked || !node.asset?.duration)}
  ${renderDerivedInfo(node.asset || {}, mediaRange(node.asset || {}))}
</div>
<div class="sai-inspector-actions">
  <button type="button" data-inspector-action="media-reload"><i class="fa-solid fa-rotate"></i><span>${escapeHtml(t('Re-upload', '重新上传'))}</span></button>
  <button type="button" data-inspector-action="view-media"><i class="fa-solid fa-magnifying-glass-plus"></i><span>${escapeHtml(t('View', '查看'))}</span></button>
  <button type="button" data-inspector-action="media-reset-trim"><i class="fa-solid fa-rotate-left"></i><span>${escapeHtml(t('Reset Trim', '重置裁剪'))}</span></button>
  <button type="button" data-inspector-action="duplicate"><i class="fa-solid fa-copy"></i><span>${escapeHtml(t('Duplicate', '复制'))}</span></button>
  <button type="button" data-inspector-action="delete" class="danger"><i class="fa-solid fa-trash"></i><span>${escapeHtml(t('Delete', '删除'))}</span></button>
</div>`;
    }

    window.SimpAICanvasWorkbenchVideoNode = {
        renderNodeHtml,
        renderInspector
    };
})();
