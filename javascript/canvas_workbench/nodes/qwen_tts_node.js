(function () {
    'use strict';

    const UTILS = window.SimpAICanvasWorkbenchUtils || {};
    const escapeHtml = UTILS.escapeHtml || ((value) => String(value ?? ''));
    const t = UTILS.t || ((en, cn) => cn || en);
    const uid = UTILS.uid || ((prefix) => `${prefix}_${Date.now().toString(36)}_${Math.random().toString(16).slice(2, 8)}`);

    const MODE_TYPES = {
        voice_design: 'qwen_tts_voice_design',
        voice_clone: 'qwen_tts_voice_clone',
        custom_voice: 'qwen_tts_custom_voice',
        dialogue: 'qwen_tts_dialogue'
    };

    const TYPE_MODES = Object.fromEntries(Object.entries(MODE_TYPES).map(([mode, type]) => [type, mode]));

    const MODE_SPECS = {
        voice_design: {
            type: MODE_TYPES.voice_design,
            title: 'Qwen TTS Voice Design',
            kind: 'Qwen TTS',
            icon: 'fa-microphone-lines',
            description: 'Generate speech from text and a voice/style instruction.'
        },
        voice_clone: {
            type: MODE_TYPES.voice_clone,
            title: 'Qwen TTS Voice Clone',
            kind: 'Qwen Clone',
            icon: 'fa-wave-square',
            description: 'Clone a reference voice and speak target text.'
        },
        custom_voice: {
            type: MODE_TYPES.custom_voice,
            title: 'Qwen TTS Custom Voice',
            kind: 'Qwen Custom',
            icon: 'fa-user',
            description: 'Use a built-in or custom speaker for text to speech.'
        },
        dialogue: {
            type: MODE_TYPES.dialogue,
            title: 'Qwen TTS Dialogue',
            kind: 'Qwen Dialogue',
            icon: 'fa-comments',
            description: 'Generate scripted dialogue with optional role reference voices.'
        }
    };

    const SPEAKER_CHOICES = [
        ['Ryan', 'Ryan'],
        ['Serena', 'Serena'],
        ['Uncle Fu', 'Uncle_fu'],
        ['Vivian', 'Vivian'],
        ['Aiden', 'Aiden'],
        ['Ono Anna', 'Ono_anna'],
        ['Sohee', 'Sohee'],
        ['Dylan', 'Dylan'],
        ['Eric', 'Eric']
    ];

    const VOICE_DESIGN_STYLE_PRESETS = [
        ['Catgirl (Neko)', "Cute catgirl voice: high-pitched, bright and sweet, youthful and playful. Add occasional short interjections like 'nya', 'meow', 'na', 'ne', 'ya' (not every sentence). Expressive with subtle emotional shifts: shy -> softer, breathy, slightly shaky; tsundere -> quick pitch rise and a small 'hmph'; teary -> light sob or choked tone. Optionally add close-mic ASMR details (soft breathing, whispery delivery) while keeping articulation clear."],
        ['Warm Female', 'Female, mid-20s, warm and friendly, medium pace, clear articulation, slight smile in voice, natural breath and gentle intonation.'],
        ['News Anchor', 'Male, 30s, calm professional news anchor, steady rhythm, neutral emotion, crisp consonants, confident delivery, minimal pitch fluctuation.'],
        ['Energetic Teen', 'Young energetic teen, bright tone, fast pace, playful rising intonation, light laughter between phrases, vivid emphasis on keywords.'],
        ['Elderly Hoarse', 'Elderly male, ~70, slightly hoarse and breathy, slow pace, reflective mood, soft volume, longer pauses, subtle trembling on sustained vowels.'],
        ['Audiobook Narrator', 'Audiobook narrator, 40s, cinematic and immersive, controlled dynamics, clear phrasing, dramatic pauses, rich low-mid register, smooth resonance.']
    ];

    function call(context, name, fallback, ...args) {
        return typeof context?.[name] === 'function' ? context[name](...args) : fallback;
    }

    function modeFromNode(node) {
        return node?.qwen_tts_mode || TYPE_MODES[node?.type] || 'voice_design';
    }

    function specForMode(mode) {
        return MODE_SPECS[mode] || MODE_SPECS.voice_design;
    }

    function commonParams() {
        return {
            model_choice: '1.7B',
            precision: 'bf16',
            device: 'auto',
            language: 'Auto',
            attention: 'auto',
            seed_random: true,
            seed: 0,
            max_new_tokens: 4096,
            split_max_chars: 200,
            split_hard_max_chars: 260,
            top_p: 0.8,
            top_k: 20,
            temperature: 1.0,
            repetition_penalty: 1.05,
            unload_model_after_generate: true,
            decode_batch_size: 2,
            batch_size: 4
        };
    }

    function modeDefaults(mode) {
        if (mode === 'voice_clone') {
            return {
                ref_text: '',
                target_text: '',
                x_vector_only: false,
                batch_size: 16
            };
        }
        if (mode === 'custom_voice') {
            return {
                text: '',
                speaker: 'Ryan',
                custom_speaker_name: '',
                instruct: '',
                batch_size: 16
            };
        }
        if (mode === 'dialogue') {
            return {
                script: '',
                role_1_name: '',
                role_1_ref_text: '',
                role_2_name: '',
                role_2_ref_text: '',
                role_3_name: '',
                role_3_ref_text: '',
                role_4_name: '',
                role_4_ref_text: '',
                pause_linebreak: 0.5,
                period_pause: 0.4,
                comma_pause: 0.2,
                question_pause: 0.6,
                hyphen_pause: 0.3,
                merge_outputs: true,
                batch_size: 4,
                max_new_tokens_per_line: 4096
            };
        }
        return {
            text: '',
            style_preset: '',
            instruct: '',
            lock_timbre_with_first_segment: true,
            clone_batch_size: 16
        };
    }

    function defaultParams(mode) {
        return Object.assign(commonParams(), modeDefaults(mode));
    }

    function normalizeStylePresetEntries(entries) {
        const rows = [];
        const seen = new Set();
        const add = (name, instruction, source) => {
            const key = String(name || '').trim();
            const text = String(instruction || '').trim();
            if (!key || !text || seen.has(key)) return;
            seen.add(key);
            rows.push({ name: key, instruction: text, source: source || 'builtin' });
        };
        if (Array.isArray(entries)) {
            entries.forEach((entry) => {
                if (Array.isArray(entry)) add(entry[0], entry[1], entry[2]);
                else if (entry && typeof entry === 'object') add(entry.name || entry.label || entry.key, entry.instruction || entry.value || entry.text, entry.source);
            });
        }
        return rows;
    }

    function stylePresetEntries(context) {
        const fallback = normalizeStylePresetEntries(VOICE_DESIGN_STYLE_PRESETS);
        const remote = normalizeStylePresetEntries(context?.qwenTtsStylePresets);
        if (!remote.length) return fallback;
        return remote;
    }

    function stylePresetChoices(context) {
        return [[t('Select...', 'Select...'), '']].concat(stylePresetEntries(context).map(item => {
            const suffix = item.source === 'user' ? ' *' : '';
            return [`${item.name}${suffix}`, item.name];
        }));
    }

    function stylePresetInstruction(name, context) {
        const key = String(name || '').trim();
        if (!key) return '';
        const found = stylePresetEntries(context).find(item => item.name === key);
        return found ? found.instruction : '';
    }

    function audioInputSlots(mode) {
        if (mode === 'voice_clone') {
            return [{ key: 'ref_audio', label: 'Reference Audio' }];
        }
        if (mode === 'dialogue') {
            return [1, 2, 3, 4].map(index => ({ key: `role_${index}_audio`, label: `Role ${index} Audio` }));
        }
        return [];
    }

    function isNode(node) {
        return !!(node && TYPE_MODES[node.type]);
    }

    function isRunning(node) {
        return ['queued', 'running', 'waiting', 'cancelling'].includes(String(node?.status?.state || node?.status || '').toLowerCase());
    }

    function inputLabel(context, node, slot) {
        return call(context, 'getQwenTtsAudioInputLabel', t('Not connected', 'Not connected'), node, slot);
    }

    function renderAudioInputRow(node, slot, context) {
        return `
<div class="sai-text-input-row" data-qwen-tts-audio-row="${escapeHtml(slot.key)}">
  <button type="button" class="sai-node-handle sai-node-handle-in" data-qwen-tts-audio-in="${escapeHtml(slot.key)}" title="${escapeHtml(slot.label)}"></button>
  <i class="fa-solid fa-wave-square"></i><span>${escapeHtml(slot.label)}</span><b>${escapeHtml(inputLabel(context, node, slot.key))}</b><small>${escapeHtml(t('Drag audio here', 'Drag audio here'))}</small>
</div>`;
    }

    function optionHtml(options, value) {
        return options.map(item => {
            const val = Array.isArray(item) ? item[1] : item;
            const label = Array.isArray(item) ? item[0] : item;
            return `<option value="${escapeHtml(val)}" ${String(val) === String(value) ? 'selected' : ''}>${escapeHtml(label)}</option>`;
        }).join('');
    }

    function field(key, label, value, attrs) {
        return `<label class="sai-node-field"><span>${escapeHtml(label)}</span><input data-node-param="${escapeHtml(key)}" value="${escapeHtml(value ?? '')}" ${attrs || ''}></label>`;
    }

    function textarea(key, label, value, rows, placeholder) {
        return `<label class="sai-node-field sai-text-node-field"><span>${escapeHtml(label)}</span><textarea data-node-param="${escapeHtml(key)}" rows="${Number(rows || 3)}" placeholder="${escapeHtml(placeholder || '')}">${escapeHtml(value || '')}</textarea></label>`;
    }

    function check(key, label, checked) {
        return `<label class="sai-node-check"><input data-node-param="${escapeHtml(key)}" type="checkbox" ${checked ? 'checked' : ''}><span>${escapeHtml(label)}</span></label>`;
    }

    function numberField(key, label, value, min, max, step) {
        const bits = [
            `type="number"`,
            min !== undefined ? `min="${escapeHtml(min)}"` : '',
            max !== undefined ? `max="${escapeHtml(max)}"` : '',
            step !== undefined ? `step="${escapeHtml(step)}"` : ''
        ].filter(Boolean).join(' ');
        return field(key, label, value, bits);
    }

    function selectField(key, label, choices, value) {
        return `<label class="sai-node-field"><span>${escapeHtml(label)}</span><select data-node-param="${escapeHtml(key)}">${optionHtml(choices, value)}</select></label>`;
    }

    function commonControls(params, compact) {
        const advanced = compact ? '' : `
<div class="sai-node-field-row">
  ${numberField('split_max_chars', 'Split Max', params.split_max_chars ?? 200, 20, 600, 10)}
  ${numberField('split_hard_max_chars', 'Split Hard', params.split_hard_max_chars ?? 260, 20, 800, 10)}
</div>
<div class="sai-node-field-row">
  ${numberField('top_p', 'Top P', params.top_p ?? 0.8, 0, 1, 0.05)}
  ${numberField('top_k', 'Top K', params.top_k ?? 20, 0, 100, 1)}
</div>
<div class="sai-node-field-row">
  ${numberField('temperature', 'Temp', params.temperature ?? 1.0, 0.1, 2, 0.1)}
  ${numberField('repetition_penalty', 'Repeat', params.repetition_penalty ?? 1.05, 1, 2, 0.05)}
</div>`;
        return `
<div class="sai-node-field-row">
  ${selectField('model_choice', 'Model', ['0.6B', '1.7B'], params.model_choice || '1.7B')}
  ${selectField('language', 'Language', ['Auto', 'Chinese', 'English', 'Japanese', 'Korean'], params.language || 'Auto')}
</div>
<div class="sai-node-field-row">
  ${selectField('precision', 'Precision', ['bf16', 'fp32'], params.precision || 'bf16')}
  ${selectField('device', 'Device', ['auto', 'cuda', 'mps', 'cpu'], params.device || 'auto')}
</div>
<div class="sai-node-field-row">
  ${check('seed_random', 'Random Seed', params.seed_random !== false)}
  ${params.seed_random === false ? numberField('seed', 'Seed', params.seed ?? 0, 0, 2147483647, 1) : ''}
</div>
<div class="sai-node-field-row">
  ${numberField('max_new_tokens', 'Max Tokens', params.max_new_tokens ?? 4096, 512, 16384, 256)}
  ${numberField('decode_batch_size', 'Decode BS', params.decode_batch_size ?? 2, 1, 16, 1)}
</div>
${advanced}
${check('unload_model_after_generate', 'Unload After Run', params.unload_model_after_generate !== false)}`;
    }

    function modeControls(mode, params, context) {
        if (mode === 'voice_clone') {
            return `
${textarea('ref_text', 'Reference Text', params.ref_text || '', 2, 'Optional transcript of the reference audio')}
${textarea('target_text', 'Target Text', params.target_text || '', 4, 'Text to speak with the cloned voice')}
<div class="sai-node-field-row">
  ${numberField('batch_size', 'Batch Size', params.batch_size ?? 4, 1, 16, 1)}
  ${check('x_vector_only', 'XVector Only', !!params.x_vector_only)}
</div>`;
        }
        if (mode === 'custom_voice') {
            return `
${textarea('text', 'Text to Speech', params.text || '', 4, 'Text to speak')}
<div class="sai-node-field-row">
  ${selectField('speaker', 'Speaker', SPEAKER_CHOICES, params.speaker || 'Ryan')}
  ${field('custom_speaker_name', 'Custom Speaker', params.custom_speaker_name || '')}
</div>
${textarea('instruct', 'Style Instruction', params.instruct || '', 3, 'Optional style / character instruction')}
${numberField('batch_size', 'Batch Size', params.batch_size ?? 4, 1, 16, 1)}`;
        }
        if (mode === 'dialogue') {
            const roleFields = [1, 2, 3, 4].map(index => `
<div class="sai-node-field-row">
  ${field(`role_${index}_name`, `Role ${index}`, params[`role_${index}_name`] || '')}
  ${field(`role_${index}_ref_text`, `Role ${index} Ref`, params[`role_${index}_ref_text`] || '')}
</div>`).join('');
            return `
${textarea('script', 'Script', params.script || '', 6, 'Role: line of dialogue')}
${roleFields}
<div class="sai-node-field-row">
  ${numberField('pause_linebreak', 'Line Gap', params.pause_linebreak ?? 0.5, 0, 5, 0.1)}
  ${numberField('period_pause', 'Period Gap', params.period_pause ?? 0.4, 0, 5, 0.1)}
</div>
<div class="sai-node-field-row">
  ${numberField('comma_pause', 'Comma Gap', params.comma_pause ?? 0.2, 0, 5, 0.1)}
  ${numberField('question_pause', 'Question Gap', params.question_pause ?? 0.6, 0, 5, 0.1)}
</div>
<div class="sai-node-field-row">
  ${numberField('batch_size', 'Batch Size', params.batch_size ?? 4, 1, 16, 1)}
  ${numberField('max_new_tokens_per_line', 'Tokens/Line', params.max_new_tokens_per_line ?? 4096, 512, 16384, 256)}
</div>
${check('merge_outputs', 'Merge Outputs', params.merge_outputs !== false)}`;
        }
        return `
${textarea('text', 'Text to Speech', params.text || '', 4, 'Text to speak')}
${selectField('style_preset', 'Character Preset', stylePresetChoices(context), params.style_preset || '')}
${textarea('instruct', 'Voice / Style Instruction', params.instruct || '', 3, 'Voice, timbre, emotion, accent...')}
<div class="sai-node-field-row">
  ${numberField('clone_batch_size', 'Batch Size', params.clone_batch_size ?? 16, 1, 16, 1)}
  ${check('lock_timbre_with_first_segment', 'Lock Timbre', !!params.lock_timbre_with_first_segment)}
</div>`;
    }

    function renderNodeHtml(node, context) {
        const mode = modeFromNode(node);
        const spec = specForMode(mode);
        const params = Object.assign(defaultParams(mode), node.params || {});
        const running = isRunning(node);
        const status = typeof node.status === 'string' ? node.status : (node.status?.message || '');
        const inputs = audioInputSlots(mode).map(slot => renderAudioInputRow(node, slot, context)).join('');
        return `
<div class="sai-node-head">
  <span class="sai-node-kind">${escapeHtml(spec.kind)}</span>
  <span class="sai-node-title">${escapeHtml(node.title || spec.title)}</span>
  ${call(context, 'renderNodeStateBadges', '', node)}
  <button type="button" data-node-action="run-qwen-tts" title="${escapeHtml(t('Run Qwen TTS', 'Run Qwen TTS'))}" ${running ? 'disabled' : ''}><i class="fa-solid fa-play"></i></button>
  <button type="button" data-node-action="delete" title="${escapeHtml(t('Delete', 'Delete'))}"><i class="fa-solid fa-xmark"></i></button>
</div>
${inputs}
${modeControls(mode, params, context)}
${commonControls(params, true)}
${status ? `<div class="sai-node-foot">${escapeHtml(status)}</div>` : ''}
<button type="button" class="sai-node-primary" data-node-action="run-qwen-tts" ${running ? 'disabled' : ''}><i class="fa-solid fa-play"></i><span>${escapeHtml(t('Generate Audio', 'Generate Audio'))}</span></button>
<button type="button" class="sai-node-handle sai-node-handle-out" data-handle-out="audio" title="${escapeHtml(t('Audio output', 'Audio output'))}"></button>`;
    }

    function renderInspector(node, context) {
        const mode = modeFromNode(node);
        const spec = specForMode(mode);
        const params = Object.assign(defaultParams(mode), node.params || {});
        const inputs = audioInputSlots(mode).map(slot => {
            return `<div class="sai-inspector-kv"><span>${escapeHtml(slot.label)}</span><b>${escapeHtml(inputLabel(context, node, slot.key))}</b></div>`;
        }).join('');
        return `
<div class="sai-inspector-section">
  <h3>${escapeHtml(spec.title)}</h3>
  <label>Title<input data-inspector-node-field="title" value="${escapeHtml(node.title || '')}"></label>
  <div class="sai-inspector-kv"><span>Mode</span><b>${escapeHtml(mode)}</b></div>
  ${inputs}
  <p>${escapeHtml(spec.description)}</p>
</div>
<div class="sai-inspector-section">
  <h3>Mode</h3>
  ${modeControls(mode, params, context).replaceAll('data-node-param=', 'data-inspector-param=')}
</div>
<div class="sai-inspector-section">
  <h3>Generation</h3>
  ${commonControls(params, false).replaceAll('data-node-param=', 'data-inspector-param=')}
</div>
<div class="sai-inspector-actions">
  <button type="button" data-inspector-action="run-qwen-tts"><i class="fa-solid fa-play"></i><span>Run</span></button>
  ${isRunning(node) ? '<button type="button" data-inspector-action="stop-qwen-tts" class="danger"><i class="fa-solid fa-stop"></i><span>Stop</span></button>' : ''}
  <button type="button" data-inspector-action="duplicate"><i class="fa-solid fa-copy"></i><span>Duplicate</span></button>
  <button type="button" data-inspector-action="delete" class="danger"><i class="fa-solid fa-trash"></i><span>Delete</span></button>
</div>`;
    }

    function createNode(mode, world, options, context) {
        const normalizedMode = MODE_SPECS[mode] ? mode : 'voice_design';
        const spec = specForMode(normalizedMode);
        const opts = options || {};
        if (opts.history !== false) call(context, 'pushHistory', null, `Add ${spec.title} node`);
        const size = call(context, 'defaultNodeSize', { w: 360, h: normalizedMode === 'dialogue' ? 660 : 560 }, spec.type);
        const node = {
            id: uid('qwentts'),
            type: spec.type,
            qwen_tts_mode: normalizedMode,
            x: world.x,
            y: world.y,
            w: size.w,
            h: size.h,
            title: opts.title || spec.title,
            params: Object.assign(defaultParams(normalizedMode), opts.params || {}),
            audio_inputs: {},
            source: { kind: 'qwen_tts', mode: normalizedMode, module: 'enhanced.webui_qwen_tts' },
            status: {
                state: 'idle',
                message: spec.description
            }
        };
        call(context, 'placeNodeAvoidingOverlap', null, node, world);
        const project = context?.project && typeof context.project === 'object' ? context.project : { nodes: [] };
        if (!Array.isArray(project.nodes)) project.nodes = [];
        project.nodes.push(node);
        call(context, 'setSelectedNode', null, node.id);
        if (opts.render !== false) call(context, 'mutate', null);
        if (opts.toast !== false) call(context, 'showToast', null, `${spec.title} node added`);
        return node;
    }

    window.SimpAICanvasWorkbenchQwenTtsNode = {
        MODE_SPECS,
        MODE_TYPES,
        TYPE_MODES,
        audioInputSlots,
        createNode,
        defaultParams,
        isNode,
        modeFromNode,
        stylePresetInstruction,
        renderInspector,
        renderNodeHtml
    };
})();
