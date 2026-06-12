(function () {
    'use strict';

    const UTILS = window.SimpAICanvasWorkbenchUtils || {};
    const escapeHtml = UTILS.escapeHtml || ((value) => String(value ?? ''));
    const t = UTILS.t || ((en, cn) => cn || en);

    function call(context, name, fallback, ...args) {
        return typeof context?.[name] === 'function' ? context[name](...args) : fallback;
    }

    function openPanel(context) {
        const existing = document.querySelector('.sai-group-list-modal');
        if (existing) existing.remove();
        const groups = call(context, 'getGroups', [], {}) || [];
        const modal = document.createElement('div');
        modal.className = 'sai-canvas-modal sai-group-list-modal';
        modal.classList.toggle('theme-dark', call(context, 'detectWorkbenchTheme', 'dark') === 'dark');
        modal.innerHTML = `
<div class="sai-canvas-modal-panel sai-group-list-panel">
  <div class="sai-canvas-modal-head">
    <h3>${escapeHtml(t('Area Groups', '区域分组'))}</h3>
    <button type="button" data-modal-close><i class="fa-solid fa-xmark"></i></button>
  </div>
  <div class="sai-group-list-body">
    ${groups.length ? groups.map(group => {
            const shortcut = call(context, 'groupShortcutLabel', '', group);
            const count = call(context, 'getNodesInsideGroup', [], group).length;
            const color = call(context, 'normalizeCanvasColor', '#14b8a6', group.color, '#14b8a6');
            return `<button type="button" data-group-jump="${escapeHtml(group.id)}">
      <i class="fa-solid fa-object-group" style="color:${escapeHtml(color)}"></i>
      <span>${escapeHtml(group.title || t('Group', '分组'))}</span>
      <b>${escapeHtml(shortcut || `${count} ${t('nodes', '节点')}`)}</b>
    </button>`;
        }).join('') : `<div class="sai-canvas-empty">${escapeHtml(t('No groups yet. Add one around a selected work area.', '还没有分组。可以围绕选中的工作区域添加一个。'))}</div>`}
  </div>
  <div class="sai-canvas-modal-foot">
    <button type="button" data-group-add><i class="fa-solid fa-plus"></i><span>${escapeHtml(t('Add group', '添加分组'))}</span></button>
  </div>
</div>`;
        document.body.appendChild(modal);
        call(context, 'ensureWorkbenchFormFieldNames', null, modal, 'group_list');
        modal.addEventListener('click', (evt) => {
            if (evt.target === modal || evt.target.closest('[data-modal-close]')) {
                modal.remove();
                return;
            }
            const jump = evt.target.closest('[data-group-jump]');
            if (jump) {
                const group = call(context, 'getGroup', null, jump.getAttribute('data-group-jump'));
                modal.remove();
                call(context, 'focusGroup', null, group);
                return;
            }
            if (evt.target.closest('[data-group-add]')) {
                modal.remove();
                call(context, 'addAreaGroup', null, call(context, 'viewportCenterWorld', { x: 0, y: 0 }));
            }
        });
    }

    window.SimpAICanvasWorkbenchGroupList = {
        openPanel
    };
})();
