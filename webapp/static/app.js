'use strict';

/*
 * Local workbench front end: plain DOM + fetch, no build step and no CDN.
 * All option lists come from GET /api/schema (shared/ modules), and every
 * value the server builds (spec, runner config, candidates, exports) is
 * computed by the same shared code the desktop workbench uses.
 */

const SIDES = ['target', 'left', 'right'];
const DONE_STATUSES = ['succeeded', 'failed', 'cancelled', 'interrupted'];
/* Formats that still make sense for the run's full output table; the others
   (fasta/bed/unique_guides/library) only reinterpret candidate rows. */
const TABULAR_EXPORT_FORMATS = ['csv', 'tsv', 'xlsx'];

const state = {
  schema: null,
  values: {},
  mode: 'single_motif_flank',
  input_mode: 'sequence',
  nuclease: 'cas9',
  tnpb_subtype: 'unknown',
  require_pam: true,
  active_side: 'target',
  side_presets: {target: 'cas9', left: 'cas9', right: 'cas9'},
  side_on_target_models: {target: '', left: '', right: ''},
  side_off_target_models: {target: '', left: '', right: ''},
  side_model_options: {},
  preset_models: {},
  confirm_policy: 'yes',
  jobId: null,
  pollTimer: null,
  logOffset: 0,
  dpJobId: null,
  dpPollTimer: null,
  dpLogOffset: 0,
  detailJobId: null,
  detailTimer: null,
  detailLogOffset: 0,
  previewTimer: null,
  pattern_name: '',
  results: null,
  resultsViewPinned: false,
  drawerOpen: false,
  loadedHint: null,
  recentJob: null,
};

function $(id) {
  return document.getElementById(id);
}

function el(tag, attrs, children) {
  const node = document.createElement(tag);
  if (attrs) {
    Object.keys(attrs).forEach(function (key) {
      if (key === 'text') {
        node.textContent = attrs[key];
      } else if (key === 'class') {
        node.className = attrs[key];
      } else {
        node.setAttribute(key, attrs[key]);
      }
    });
  }
  (children || []).forEach(function (child) {
    node.appendChild(child);
  });
  return node;
}

function showBanner(message, isError) {
  const banner = $('global-banner');
  if (!banner) {
    return;
  }
  banner.textContent = message;
  banner.className = 'banner ' + (isError ? 'error' : 'info');
}

function hideBanner() {
  const banner = $('global-banner');
  if (banner) {
    banner.className = 'banner hidden';
  }
}

async function api(path, options) {
  const opts = Object.assign({method: 'GET', headers: {}}, options || {});
  if (opts.body !== undefined && opts.body !== null) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(opts.body);
  }
  const response = await fetch(path, opts);
  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch (err) {
      data = null;
    }
  }
  if (!response.ok) {
    throw new Error((data && data.error) || ('HTTP ' + response.status));
  }
  return data;
}

function currentValue(key, fallback) {
  const value = state.values[key];
  if (value === undefined || value === null) {
    return fallback === undefined || fallback === null ? '' : String(fallback);
  }
  if (typeof value === 'boolean') {
    return value ? '1' : '';
  }
  return String(value);
}

function boolValue(key, fallback) {
  const raw = state.values[key];
  if (raw === undefined || raw === null) {
    return !!fallback;
  }
  if (typeof raw === 'boolean') {
    return raw;
  }
  const text = String(raw).trim().toLowerCase();
  if (['1', 'true', 'yes', 'on'].indexOf(text) >= 0) { return true; }
  if (['', '0', 'false', 'no', 'off'].indexOf(text) >= 0) { return false; }
  return !!text;
}

function setValue(key, value) {
  state.values[key] = value;
  schedulePreview();
}

/* ------------------------------------------------------------ page layout */

function setDrawer(open) {
  const drawer = $('drawer');
  const workspace = $('workspace');
  const toggle = $('drawer-toggle');
  if (!drawer || !workspace || !toggle) {
    return;
  }
  state.drawerOpen = !!open;
  drawer.classList.toggle('open', state.drawerOpen);
  drawer.setAttribute('aria-hidden', state.drawerOpen ? 'false' : 'true');
  workspace.classList.toggle('drawer-open', state.drawerOpen);
  const scrim = $('drawer-scrim');
  if (scrim) {
    scrim.classList.toggle('hidden', !state.drawerOpen);
  }
  toggle.setAttribute('aria-expanded', state.drawerOpen ? 'true' : 'false');
  writeStorage(DRAWER_OPEN_KEY, state.drawerOpen ? '1' : '0');
  if (state.drawerOpen && $('models-groups')) {
    loadModels();
  }
}

/* ------------------------------------------------------- drawer geometry */

const DRAWER_WIDTH_KEY = 'crispr.drawerWidth';
const DRAWER_OPEN_KEY = 'crispr.drawerOpen';
const DRAWER_MIN_WIDTH = 380;
const DRAWER_VIEWPORT_GAP = 48;

function readStorage(key) {
  try {
    return window.localStorage.getItem(key);
  } catch (error) {
    return null;
  }
}

function writeStorage(key, value) {
  try {
    window.localStorage.setItem(key, String(value));
  } catch (error) {
    /* storage disabled: keep working, just without persistence */
  }
}

/* Nearly the whole viewport: the 48px slit on the right stays clickable as
   the way back to the Designer. */
function drawerDefaultWidth() {
  return Math.min(1800, window.innerWidth - DRAWER_VIEWPORT_GAP);
}

function drawerMaxWidth() {
  return Math.max(DRAWER_MIN_WIDTH, window.innerWidth - DRAWER_VIEWPORT_GAP);
}

function applyDrawerWidth(width) {
  const clamped = Math.min(Math.max(Math.round(width), DRAWER_MIN_WIDTH),
    drawerMaxWidth());
  document.documentElement.style.setProperty('--drawer-width', clamped + 'px');
  return clamped;
}

function drawerWidth() {
  return $('drawer').getBoundingClientRect().width;
}

/* Drag (or arrow-key) resizing of the Data prep drawer; the width is kept in
   localStorage and double-clicking the handle restores the default. */
function initDrawerGeometry() {
  const handle = $('drawer-resizer');
  if (!handle) {
    return;
  }
  const saved = parseInt(readStorage(DRAWER_WIDTH_KEY), 10);
  applyDrawerWidth(isNaN(saved) ? drawerDefaultWidth() : saved);
  let dragging = false;
  let startX = 0;
  let startWidth = 0;
  handle.addEventListener('pointerdown', function (event) {
    dragging = true;
    startX = event.clientX;
    startWidth = drawerWidth();
    try {
      if (handle.setPointerCapture) {
        handle.setPointerCapture(event.pointerId);
      }
    } catch (error) {
      /* synthetic / already-released pointer: dragging still works */
    }
    document.body.classList.add('resizing');
    event.preventDefault();
  });
  handle.addEventListener('pointermove', function (event) {
    if (dragging) {
      applyDrawerWidth(startWidth + (event.clientX - startX));
    }
  });
  const finish = function (event) {
    if (!dragging) {
      return;
    }
    dragging = false;
    try {
      if (handle.releasePointerCapture) {
        handle.releasePointerCapture(event.pointerId);
      }
    } catch (error) {
      /* pointer already released */
    }
    document.body.classList.remove('resizing');
    writeStorage(DRAWER_WIDTH_KEY, Math.round(drawerWidth()));
  };
  handle.addEventListener('pointerup', finish);
  handle.addEventListener('pointercancel', finish);
  handle.addEventListener('dblclick', function () {
    try {
      window.localStorage.removeItem(DRAWER_WIDTH_KEY);
    } catch (error) {
      /* ignore */
    }
    applyDrawerWidth(drawerDefaultWidth());
  });
  handle.addEventListener('keydown', function (event) {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') {
      return;
    }
    const step = event.shiftKey ? 48 : 16;
    const next = applyDrawerWidth(
      drawerWidth() + (event.key === 'ArrowRight' ? step : -step));
    writeStorage(DRAWER_WIDTH_KEY, next);
    event.preventDefault();
  });
  window.addEventListener('resize', function () {
    applyDrawerWidth(drawerWidth());
  });
}

/* ``dataprep.find`` -> ``find``; keeps the recent-job line readable. */
function shortKind(kind) {
  const text = String(kind || 'job');
  const parts = text.split('.');
  return parts.length > 1 ? parts[parts.length - 1] : text;
}

function formatDuration(started, finished) {
  if (!started || !finished) {
    return '';
  }
  const from = Date.parse(started);
  const to = Date.parse(finished);
  if (isNaN(from) || isNaN(to) || to < from) {
    return '';
  }
  const seconds = (to - from) / 1000;
  if (seconds < 60) {
    return seconds.toFixed(1) + 's';
  }
  const minutes = Math.floor(seconds / 60);
  return minutes + 'm ' + Math.round(seconds - minutes * 60) + 's';
}

/* One-line ``<kind> · <status> · <duration>`` summary of the last job. */
function renderRecentJob() {
  const node = $('designer-recent');
  if (!node) {
    return;
  }
  const job = state.recentJob;
  if (!job) {
    node.textContent = '';
    node.title = '';
    node.classList.add('hidden');
    return;
  }
  const parts = [shortKind(job.kind), job.status];
  const duration = formatDuration(job.started, job.finished);
  if (duration) {
    parts.push(duration);
  }
  node.textContent = parts.join(' · ');
  node.title = (job.title || shortKind(job.kind)) + ' ' + job.job_id
    + (job.message ? ('\n' + job.message) : '');
  node.classList.remove('hidden');
}

function setRecentJob(job) {
  if (!job || !job.job_id) {
    return;
  }
  state.recentJob = {
    job_id: job.job_id,
    kind: job.kind || '',
    title: job.title || '',
    status: job.status || '',
    message: job.message || '',
    started: job.started || null,
    finished: job.finished || null,
  };
  renderRecentJob();
}

/* Start a fresh summary line when a new job is submitted. */
function resetRecentJob(jobId, kind, title) {
  setRecentJob({
    job_id: jobId, kind: kind, title: title, status: 'queued',
    started: new Date().toISOString(), finished: null,
  });
}

function scrollToRunLog() {
  const wrap = $('designer-log-wrap');
  if (!wrap) {
    return;
  }
  wrap.open = true;
  if (wrap.scrollIntoView) {
    wrap.scrollIntoView({behavior: 'smooth', block: 'start'});
  }
}

function initLayout() {
  initDrawerGeometry();
  setDrawer(readStorage(DRAWER_OPEN_KEY) === '1');
  $('drawer-toggle').addEventListener('click', function () {
    setDrawer(!state.drawerOpen);
  });
  $('drawer-close').addEventListener('click', function () {
    setDrawer(false);
  });
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && state.drawerOpen && !isPickerOpen()) {
      setDrawer(false);
    }
  });
  const scrim = $('drawer-scrim');
  if (scrim) {
    scrim.addEventListener('click', function () {
      setDrawer(false);
    });
  }
  const recent = $('designer-recent');
  if (recent) {
    recent.addEventListener('click', scrollToRunLog);
  }
  const resultsWrap = $('results-wrap');
  if (resultsWrap) {
    resultsWrap.addEventListener('toggle', function () {
      if (resultsWrap.open) {
        loadJobs();
      }
    });
  }
  initDataPrep();
  initModels();
  initDesigner();
  initResults();
  initBatch();
  loadJobs();
}
/* --------------------------------------------------------------- back-fill */

/* ``outputs`` key -> Designer field of the main area (task 1.3 table). */
const OUTPUT_FIELD_MAP = {
  genome_fasta: 'genome_fasta',
  target_fasta: 'search_fasta',
  mask_fasta: 'mask_fasta',
  blastdb: 'blastdb',
  annotation: 'annotation',
  index_path: 'index_path',
  search_fasta: 'search_fasta',
  bed_regions: 'bed_regions',
};

/* ``outputs`` keys that only have a drawer input. */
const DRAWER_FIELD_MAP = {
  genome_fasta: 'dp-genome',
  annotation: 'dp-annotation',
  output_dir: 'dp-output',
  blastdb: 'dp-blastdb',
  index_path: 'dp-index-prefix',
};

function cleanText(value) {
  return value === null || value === undefined ? '' : String(value).trim();
}

/* Pure rule: which ``outputs`` may be written, given what the user already has.

 * Only empty fields are filled; ``skipMask`` keeps ``mask_fasta`` untouched.
 */
function backfillPlan(outputs, values, drawerValues, options) {
  const opts = options || {};
  const plan = {updates: {}, drawerUpdates: {}, skipped: [], ignored: []};
  Object.keys(outputs || {}).forEach(function (key) {
    const value = cleanText(outputs[key]);
    if (!value) {
      return;
    }
    if (key === 'mask_fasta' && opts.skipMask) {
      return;
    }
    const field = OUTPUT_FIELD_MAP[key];
    if (field) {
      const drawerId = DRAWER_FIELD_MAP[key];
      if (cleanText((values || {})[field])
          || (drawerId && cleanText((drawerValues || {})[drawerId]))) {
        plan.skipped.push(key);
        return;
      }
      plan.updates[field] = value;
      return;
    }
    const drawerId = DRAWER_FIELD_MAP[key];
    if (drawerId) {
      if (cleanText((drawerValues || {})[drawerId])) {
        plan.skipped.push(key);
        return;
      }
      plan.drawerUpdates[drawerId] = value;
      return;
    }
    plan.ignored.push(key);
  });
  return plan;
}

/* The back-fill hint exists twice: in the Designer column and inside the Data
   prep panel (the panel covers the main area when it is open). Both must show
   the same text and the same tooltip, so the copy lives here once. */
const LOADED_HINT_IDS = ['designer-loaded-hint', 'dp-loaded-hint'];

function loadedHintText(info) {
  if (!info) {
    return '';
  }
  const fields = Object.keys(info.updates || {});
  const drawerFields = Object.keys(info.drawerUpdates || {}).map(function (id) {
    return id.replace(/^dp-/, '');
  });
  let text = 'Loaded: ' + fields.join(', ');
  if (drawerFields.length) {
    text += ' (drawer: ' + drawerFields.join(', ') + ')';
  }
  if ((info.skipped || []).length) {
    text += ' · kept your values: ' + info.skipped.join(', ');
  }
  return text;
}

function renderLoadedHint() {
  const info = state.loadedHint;
  const text = loadedHintText(info);
  LOADED_HINT_IDS.forEach(function (id) {
    const hint = $(id);
    if (!hint) {
      return;
    }
    if (!info) {
      hint.textContent = '';
      hint.title = '';
      hint.className = 'loaded-hint hidden';
      return;
    }
    hint.textContent = text;
    hint.title = info.tooltip || '';
    hint.className = 'loaded-hint';
  });
}

/* Write a finished Data prep / Models job's ``outputs`` into empty fields. */
function applyJobOutputs(job) {
  const outputs = (job && job.outputs) || {};
  if (!Object.keys(outputs).length) {
    return;
  }
  const drawerValues = {};
  Object.keys(DRAWER_FIELD_MAP).forEach(function (key) {
    const input = $(DRAWER_FIELD_MAP[key]);
    drawerValues[DRAWER_FIELD_MAP[key]] = input ? input.value : '';
  });
  const plan = backfillPlan(outputs, state.values, drawerValues, {
    skipMask: !!($('dp-skip-mask') && $('dp-skip-mask').checked),
  });
  const lines = [];
  Object.keys(plan.updates).forEach(function (field) {
    state.values[field] = plan.updates[field];
    lines.push(field + ' = ' + plan.updates[field]);
  });
  Object.keys(plan.drawerUpdates).forEach(function (drawerId) {
    const input = $(drawerId);
    if (!input) {
      return;
    }
    input.value = plan.drawerUpdates[drawerId];
    lines.push(drawerId + ' = ' + plan.drawerUpdates[drawerId]);
  });
  if ($('dp-download-output') && !cleanText($('dp-download-output').value)
      && outputs.output_dir) {
    $('dp-download-output').value = outputs.output_dir;
  }
  if (outputs.target_fasta && $('dp-target-num')) {
    $('dp-target-num').title = outputs.target_fasta;
  }
  if (!Object.keys(plan.updates).length && !Object.keys(plan.drawerUpdates).length) {
    state.loadedHint = plan.skipped.length ? {
      updates: {}, drawerUpdates: {}, skipped: plan.skipped,
      tooltip: 'Job ' + (job.job_id || '') + ' produced values but your '
        + 'fields were already filled.',
    } : null;
    renderLoadedHint();
    return;
  }
  state.loadedHint = {
    updates: plan.updates,
    drawerUpdates: plan.drawerUpdates,
    skipped: plan.skipped,
    tooltip: 'From job ' + (job.job_id || '') + ' (' + (job.title || job.kind || '')
      + '):\n' + lines.join('\n'),
  };
  renderLoadedHint();
  /* Redraw the inputs so the new values are visible, not just stored. */
  renderDesigner();
  schedulePreview();
}

/* ---------------------------------------------------------------- schema */

async function loadSchema() {
  try {
    const schema = await api('/api/schema');
    state.schema = schema;
    initStateFromSchema(schema);
    fillDataPrepOptions(schema);
    fillExportFormats(schema);
    renderDesigner();
    previewNow();
    hideBanner();
  } catch (err) {
    const message = 'Could not load /api/schema: ' + err.message
      + ' - the server is reachable but the forms cannot be populated.';
    showBanner(message, true);
    const box = $('designer-schema-error');
    if (box) {
      box.textContent = message;
      box.className = 'banner error';
    }
    $('designer-ready').textContent = 'Schema unavailable';
    $('designer-ready').className = 'ready-badge missing';
  }
}

function initStateFromSchema(schema) {
  const designer = schema.designer || {};
  state.values = Object.assign({}, designer.defaults || {});
  state.mode = (schema.modes && schema.modes[0]) ? schema.modes[0].value : 'single_motif_flank';
  state.input_mode = 'sequence';
  state.active_side = 'target';
  state.nuclease = 'cas9';
  state.tnpb_subtype = 'unknown';
  state.require_pam = designer.default_require_pam !== false;
  state.side_presets = Object.assign({target: 'cas9', left: 'cas9', right: 'cas9'}, designer.default_side_presets || {});
  state.side_on_target_models = Object.assign({target: '', left: '', right: ''}, designer.default_side_on_target_models || {});
  state.side_off_target_models = Object.assign({target: '', left: '', right: ''}, designer.default_side_off_target_models || {});
  state.preset_models = schema.preset_models || {};
  SIDES.forEach(function (side) {
    state.side_model_options[side] = state.preset_models[state.side_presets[side]] || {on_target: [], off_target: []};
  });
  const modeSelect = $('designer-mode');
  modeSelect.innerHTML = '';
  (schema.modes || []).forEach(function (mode) {
    modeSelect.appendChild(el('option', {value: mode.value, text: mode.label}));
  });
  modeSelect.value = state.mode;
}

/* ------------------------------------------------------- designer render */

function renderField(field) {
  const wrap = el('div', {class: 'field'});
  if (field.type === 'check') {
    const line = el('label', {class: 'inline'});
    const input = el('input', {type: 'checkbox'});
    input.checked = boolValue(field.key, field.default);
    input.addEventListener('change', function () {
      setValue(field.key, input.checked ? '1' : '');
    });
    line.appendChild(input);
    line.appendChild(document.createTextNode(' ' + (field.hint || field.label)));
    wrap.appendChild(line);
    return wrap;
  }
  wrap.appendChild(el('label', {text: field.label}));
  let input;
  if (field.type === 'combo') {
    input = el('select');
    (field.options || []).forEach(function (option) {
      input.appendChild(el('option', {value: option, text: option === '' ? '(none)' : option}));
    });
    input.value = currentValue(field.key, field.default);
    input.addEventListener('change', function () { setValue(field.key, input.value); });
  } else {
    input = el('input', {type: 'text'});
    input.id = 'field-' + field.key;
    input.value = currentValue(field.key, field.default);
    input.addEventListener('input', function () { setValue(field.key, input.value); });
  }
  if (field.type === 'file' || field.type === 'dir') {
    /* Path fields also get a Browse... button; the .path-row keeps the text box
       and the button on one line without squashing the path (see styles.css:
       it also has to grow inside the Results pane's flex .actions). */
    const line = el('div', {class: 'row path-row'});
    line.appendChild(input);
    line.appendChild(browseButton(input, field.kind));
    wrap.appendChild(line);
  } else {
    wrap.appendChild(input);
  }
  if (field.hint) {
    wrap.appendChild(el('div', {class: 'hint', text: field.hint}));
  }
  return wrap;
}

function renderSidePreset(side) {
  const wrap = el('div', {class: 'field'});
  wrap.appendChild(el('label', {text: 'System Preset'}));
  const row = el('div', {class: 'row'});
  const select = el('select');
  (state.schema.presets || []).forEach(function (preset) {
    select.appendChild(el('option', {value: preset.value, text: preset.label}));
  });
  select.value = state.side_presets[side];
  select.addEventListener('change', function () {
    state.side_presets[side] = select.value;
    state.side_model_options[side] = state.preset_models[select.value] || state.side_model_options[side];
    renderPattern();
    /* Selecting a preset takes effect immediately, like the desktop
       workbench: the server fills this side's motif/length/position and keeps
       the run-level nuclease in step, so a TnpB side can never keep an old
       SpCas9 nuclease until ``Apply`` is pressed.  The ``Use for Run``
       radio, not a preset change, decides which side the run scores. */
    applySidePreset(side, {activate: false});
  });
  const apply = el('button', {type: 'button', text: 'Apply'});
  apply.addEventListener('click', function () { applySidePreset(side); });
  row.appendChild(select);
  row.appendChild(apply);
  wrap.appendChild(row);
  wrap.appendChild(el('div', {class: 'hint', text: 'Preset fills this TAM side'}));
  if (state.side_presets[side] === 'tnpb') {
    wrap.appendChild(renderTnpbSubtype());
  }
  return wrap;
}

function renderTnpbSubtype() {
  const wrap = el('div', {class: 'field'});
  wrap.appendChild(el('label', {text: 'TnpB subtype'}));
  const select = el('select');
  ((state.schema && state.schema.tnpb_subtypes) || []).forEach(function (item) {
    select.appendChild(el('option', {value: item.value, text: item.label}));
  });
  select.value = state.tnpb_subtype || 'unknown';
  select.addEventListener('change', function () {
    state.tnpb_subtype = select.value;
    schedulePreview();
  });
  wrap.appendChild(select);
  return wrap;
}

function renderUseForRun(side) {
  const wrap = el('div', {class: 'field'});
  const line = el('label', {class: 'inline'});
  const radio = el('input', {type: 'radio', name: 'active-side', value: side});
  radio.checked = state.active_side === side;
  radio.addEventListener('change', function () { useForRun(side); });
  line.appendChild(radio);
  line.appendChild(document.createTextNode(' Use for Run'));
  wrap.appendChild(line);
  return wrap;
}

function modelDisplayLabel(model) {
  const labels = (state.schema && state.schema.model_labels) || {};
  return Object.prototype.hasOwnProperty.call(labels, model) ? labels[model] : model;
}

function splitModelKeys(value) {
  return String(value || '').split(/[,;]/)
    .map(function (item) { return item.trim(); })
    .filter(Boolean);
}

/* Option text is always the server's ``model_labels`` value - the same
   ``model_display_name`` the desktop picker shows - so the front end never
   keeps a second copy of the names. The first selected option is the primary
   one and gets a ``[P] `` prefix from the first user change on; the first
   render keeps the plain labels so the DOM stays comparable with
   /api/schema. */
function paintModelOptions(select, markPrimary) {
  const selected = Array.prototype.slice.call(select.selectedOptions);
  Array.prototype.forEach.call(select.options, function (option) {
    const primary = markPrimary && selected.length > 0 && option === selected[0];
    option.text = (primary ? '[P] ' : '') + modelDisplayLabel(option.value);
  });
}

const MODEL_SELECT_HINT =
  'Ctrl/Cmd-click to select several models; the first selection is primary.';

function sideModelHint(side) {
  let text = MODEL_SELECT_HINT;
  const onTarget = splitModelKeys(state.side_on_target_models[side]).map(modelDisplayLabel);
  const offTarget = splitModelKeys(state.side_off_target_models[side]).map(modelDisplayLabel);
  if (onTarget.length) {
    text += ' Primary: ' + onTarget.join(', ') + '.';
  }
  if (offTarget.length) {
    text += ' Primary (Off-target): ' + offTarget.join(', ') + '.';
  }
  return text;
}

function modelSelect(side, role, options, selected, refreshHint) {
  const list = options && options.length ? options : [''];
  const select = el('select', {
    multiple: 'multiple',
    size: String(Math.min(Math.max(list.length, 2), 5)),
  });
  const chosen = splitModelKeys(selected);
  list.forEach(function (model) {
    const option = el('option', {value: model, text: model});
    if (chosen.indexOf(model) >= 0) {
      option.selected = true;
    }
    select.appendChild(option);
  });
  select.addEventListener('change', function () {
    const values = Array.prototype.slice.call(select.selectedOptions)
      .map(function (option) { return option.value; });
    if (role === 'on') {
      state.side_on_target_models[side] = values.join(',');
    } else {
      state.side_off_target_models[side] = values.join(',');
    }
    paintModelOptions(select, true);
    if (refreshHint) {
      refreshHint();
    }
    schedulePreview();
  });
  paintModelOptions(select, false);
  return select;
}

function renderSideModels(side) {
  const wrap = el('div', {class: 'field'});
  const options = state.side_model_options[side] || {on_target: [], off_target: []};
  const hint = el('div', {class: 'hint', text: MODEL_SELECT_HINT});
  const refreshHint = function () { hint.textContent = sideModelHint(side); };
  wrap.appendChild(el('label', {text: 'On-target Model'}));
  wrap.appendChild(modelSelect(
    side, 'on', options.on_target, state.side_on_target_models[side], refreshHint));
  wrap.appendChild(el('label', {text: 'Off-target Model'}));
  wrap.appendChild(modelSelect(
    side, 'off', options.off_target, state.side_off_target_models[side], refreshHint));
  wrap.appendChild(hint);
  refreshHint();
  return wrap;
}

function renderCommon() {
  const container = $('designer-common-fields');
  if (!container) {
    return;
  }
  container.innerHTML = '';
  const designer = state.schema.designer;

  const inputBox = el('div', {class: 'group'});
  inputBox.appendChild(el('h4', {text: 'Input'}));
  const row = el('div', {class: 'row'});
  [['sequence', 'Sequence (FASTA)'], ['bed', 'BED Regions']].forEach(function (pair) {
    const line = el('label', {class: 'inline'});
    const radio = el('input', {type: 'radio', name: 'input-mode', value: pair[0]});
    radio.checked = state.input_mode === pair[0];
    radio.addEventListener('change', function () {
      state.input_mode = pair[0];
      renderDesigner();
      schedulePreview();
    });
    line.appendChild(radio);
    line.appendChild(document.createTextNode(' ' + pair[1]));
    row.appendChild(line);
  });
  inputBox.appendChild(row);
  container.appendChild(inputBox);

  const common = el('div', {class: 'group'});
  common.appendChild(el('h4', {text: 'Common Inputs'}));
  (designer.common_fields || []).forEach(function (field) {
    if (field.input_modes && field.input_modes.indexOf(state.input_mode) < 0) {
      return;
    }
    common.appendChild(renderField(field));
  });
  container.appendChild(common);
}

/* Slot -> main-area column (task 1.2). Each slot owns a dedicated child
 * container: `renderPattern()` clears those, never the columns themselves
 * (`#designer-common-col` also holds the static Common Inputs block). */
const SLOT_CONTAINERS = {
  left: 'designer-left-col',
  middle: 'designer-middle-col',
  right: 'designer-right-col',
};

function renderPatternSlot(slot, group) {
  const container = $(SLOT_CONTAINERS[slot]);
  if (!container) {
    return;
  }
  const box = el('div', {class: 'group'});
  box.appendChild(el('h4', {text: group.title}));
  (group.fields || []).forEach(function (field) {
    if (field.type === 'side_preset') {
      box.appendChild(renderSidePreset(field.side));
    } else if (field.type === 'use_for_run') {
      box.appendChild(renderUseForRun(field.side));
    } else if (field.type === 'side_models') {
      box.appendChild(renderSideModels(field.side));
    } else {
      box.appendChild(renderField(field));
    }
  });
  container.appendChild(box);
}

function renderPattern() {
  ['left', 'middle', 'right'].forEach(function (slot) {
    const container = $(SLOT_CONTAINERS[slot]);
    if (!container) {
      return;
    }
    container.innerHTML = '';
  });
  const forms = (state.schema.designer.pattern_forms || {})[state.mode] || {};
  ['left', 'middle', 'right'].forEach(function (slot) {
    const group = forms[slot];
    if (group) {
      renderPatternSlot(slot, group);
    }
  });
}

function renderRun() {
  const container = $('designer-run-col');
  if (!container) {
    return;
  }
  container.innerHTML = '';
  const designer = state.schema.designer;

  const runBox = el('div', {class: 'group'});
  (designer.run_fields || []).forEach(function (field) {
    runBox.appendChild(renderField(field));
  });
  const confirmLine = el('label', {class: 'inline'});
  const confirm = el('input', {type: 'checkbox'});
  confirm.checked = state.confirm_policy !== 'no';
  confirm.addEventListener('change', function () {
    state.confirm_policy = confirm.checked ? 'yes' : 'no';
  });
  confirmLine.appendChild(confirm);
  confirmLine.appendChild(document.createTextNode(' Auto-confirm CONFIRM_REQUIRED prompts'));
  runBox.appendChild(confirmLine);
  container.appendChild(runBox);

  const policyBox = el('div', {class: 'group'});
  policyBox.appendChild(el('h4', {text: 'PairRank prediction_only policy'}));
  (state.schema.pair_rank_fields || []).forEach(function (name) {
    policyBox.appendChild(renderField({key: 'pair_rank_' + name, label: name, type: 'text'}));
  });
  container.appendChild(policyBox);
}

function renderDesigner() {
  if (!state.schema) {
    return;
  }
  renderCommon();
  renderPattern();
  renderRun();
}

/* Which table the Results block shows and exports: the run's deliverable
   output table ("full") or the historical candidate columns ("concise"). */
function resultsView() {
  const select = $('designer-export-columns');
  return select ? select.value : 'concise';
}

function setResultsView(view) {
  const select = $('designer-export-columns');
  if (select && select.value !== view) {
    select.value = view;
  }
  fillExportFormats(state.schema || {});
}

function fillExportFormats(schema) {
  const select = $('designer-export-format');
  if (!select) {
    return;
  }
  const formats = (schema.export_formats || ['csv']).filter(function (fmt) {
    return resultsView() !== 'full'
      || TABULAR_EXPORT_FORMATS.indexOf(fmt) >= 0;
  });
  const previous = select.value;
  select.innerHTML = '';
  formats.forEach(function (fmt) {
    select.appendChild(el('option', {value: fmt, text: fmt}));
  });
  /* Keep the user's format when it is still on offer. */
  if (formats.indexOf(previous) >= 0) {
    select.value = previous;
  }
}

/* --------------------------------------------------------- designer state */

function payload(extra) {
  const base = {
    mode: state.mode,
    input_mode: state.input_mode,
    nuclease: state.nuclease,
    tnpb_subtype: state.tnpb_subtype,
    require_pam: state.require_pam,
    active_side: state.active_side,
    side_presets: state.side_presets,
    side_on_target_models: state.side_on_target_models,
    side_off_target_models: state.side_off_target_models,
    values: state.values,
  };
  return Object.assign(base, extra || {});
}

function applyUpdates(updates) {
  Object.keys(updates || {}).forEach(function (key) {
    const value = updates[key];
    if (key === 'nuclease') {
      state.nuclease = String(value);
    } else if (key === 'tnpb_subtype') {
      state.tnpb_subtype = String(value);
    } else if (key === 'require_pam') {
      state.require_pam = !!value;
    } else if (typeof value === 'boolean') {
      state.values[key] = value ? '1' : '';
    } else {
      state.values[key] = String(value);
    }
  });
}

function applyModelSelection(side, result) {
  if (result.models) {
    state.side_model_options[side] = result.models;
  }
  const selection = result.selection || {};
  if (selection.on_target) {
    state.side_on_target_models[side] = selection.on_target;
  }
  if (selection.off_target) {
    state.side_off_target_models[side] = selection.off_target;
  }
}

function schedulePreview() {
  if (state.previewTimer) {
    clearTimeout(state.previewTimer);
  }
  state.previewTimer = setTimeout(previewNow, 250);
}

async function previewNow() {
  if (!state.schema) {
    return;
  }
  try {
    const result = await api('/api/designer/preview', {method: 'POST', body: payload()});
    state.pattern_name = result.pattern_name || '';
    const batchPatternInput = $('batch-pattern-id');
    if (batchPatternInput && !batchPatternInput.value.trim()) {
      batchPatternInput.placeholder = state.pattern_name || 'pattern id';
    }
    $('designer-describe').textContent = result.describe || '(pattern is not valid yet)';
    const badge = $('designer-ready');
    if (result.errors && result.errors.length) {
      badge.textContent = 'Missing: ' + result.errors[0];
      badge.className = 'ready-badge missing';
    } else {
      badge.textContent = 'Ready';
      badge.className = 'ready-badge ready';
    }
    if (result.warnings && result.warnings.length) {
      showBanner(result.warnings.join(' | '), false);
    }
  } catch (err) {
    const badge = $('designer-ready');
    badge.textContent = 'Preview failed: ' + err.message;
    badge.className = 'ready-badge missing';
  }
}

/* "Load sample data" (NAR :138): fill the Designer from the bundled example
   so a reviewer can try the workbench without typing any path. Clicking twice
   writes the same values again (idempotent) and never starts a run. */
async function loadSampleData() {
  try {
    const sample = await api('/api/sample');
    if (sample.mode) {
      state.mode = sample.mode;
      const modeSelect = $('designer-mode');
      if (modeSelect) {
        modeSelect.value = sample.mode;
      }
    }
    if (sample.input_mode) {
      state.input_mode = sample.input_mode;
    }
    if (sample.nuclease) {
      state.nuclease = String(sample.nuclease);
    }
    [sample.fields || {}, sample.run || {}].forEach(function (group) {
      Object.keys(group).forEach(function (key) {
        state.values[key] = String(group[key]);
      });
    });
    const genome = (sample.fields || {}).genome_fasta || sample.genome_fasta;
    const drawerGenome = $('dp-genome');
    if (drawerGenome && genome) {
      drawerGenome.value = genome;
    }
    renderDesigner();
    schedulePreview();
    showBanner('Loaded sample data from ' + (sample.batch_spec || 'sample_data')
      + ' - press Find Targets to run it.', false);
  } catch (err) {
    showBanner('Could not load sample data: ' + err.message, true);
  }
}

async function applySidePreset(side, options) {
  const activate = !(options && options.activate === false);
  try {
    const result = await api('/api/designer/preset', {
      method: 'POST',
      body: {side: side, preset: state.side_presets[side]},
    });
    state.side_presets[side] = result.preset;
    applyUpdates(result.updates);
    applyModelSelection(side, result);
    if (activate) {
      state.active_side = side;
    }
    renderDesigner();
    previewNow();
  } catch (err) {
    showBanner('Apply preset failed: ' + err.message, true);
  }
}

async function useForRun(side) {
  state.active_side = side;
  try {
    const result = await api('/api/designer/active-side', {
      method: 'POST',
      body: payload({active_side: side}),
    });
    applyUpdates(result.updates);
    applyModelSelection(side, result);
    renderDesigner();
    previewNow();
  } catch (err) {
    showBanner('Switching the run side failed: ' + err.message, true);
  }
}
/* ------------------------------------------------------------- data prep */

function fillSelect(select, options) {
  if (!select) {
    return;
  }
  select.innerHTML = '';
  options.forEach(function (option) {
    select.appendChild(el('option', {value: option.value, text: option.label}));
  });
}

function labelled(values) {
  return (values || []).map(function (value) {
    return {value: value, label: value};
  });
}

function fillDataPrepOptions(schema) {
  const dp = schema.dataprep || {};
  fillSelect($('dp-species'), labelled(dp.species));
  ['dp-target-region', 'dp-mask-region'].forEach(function (id) {
    fillSelect($(id), labelled(dp.region_types));
  });
  ['dp-target-id-type', 'dp-mask-id-type'].forEach(function (id) {
    fillSelect($(id), labelled(dp.id_types));
  });
  $('dp-skip-mask').checked = !!dp.skip_mask_default;
  $('dp-mask-same').checked = dp.mask_same_as_target_default !== false;
  $('dp-skip-mask').addEventListener('change', syncMaskFields);
  $('dp-mask-same').addEventListener('change', syncMaskFields);
  syncMaskFields();
}

function syncMaskFields() {
  const skip = $('dp-skip-mask').checked;
  const same = $('dp-mask-same').checked;
  ['dp-mask-id', 'dp-mask-id-type', 'dp-mask-region', 'dp-mask-num'].forEach(function (id) {
    $(id).disabled = skip || same;
  });
  if (skip) {
    $('dp-mask-id').value = '';
    $('dp-mask-num').value = '';
  }
}

function dpPayload(extra) {
  return Object.assign({
    species: $('dp-species').value,
    genome: $('dp-genome').value.trim(),
    annotation: $('dp-annotation').value.trim(),
    output_dir: $('dp-output').value.trim(),
    blastdb: $('dp-blastdb').value.trim(),
    target_id: $('dp-target-id').value.trim(),
    target_region: $('dp-target-region').value,
    target_num: $('dp-target-num').value.trim(),
    target_id_type: $('dp-target-id-type').value,
    skip_mask: $('dp-skip-mask').checked,
    mask_same_as_target: $('dp-mask-same').checked,
    mask_id: $('dp-mask-id').value.trim(),
    mask_region: $('dp-mask-region').value,
    mask_num: $('dp-mask-num').value.trim(),
    mask_id_type: $('dp-mask-id-type').value,
    prefix: $('dp-index-prefix').value.trim(),
  }, extra || {});
}

function dpDownloadPayload() {
  return dpPayload({output_dir: $('dp-download-output').value.trim()});
}

function renderJobBox(box, job, logText) {
  box.classList.remove('hidden');
  box.innerHTML = '';
  const head = el('div', {class: 'row'});
  head.appendChild(el('strong', {text: job.title || job.job_id}));
  head.appendChild(el('span', {
    class: 'status status-' + job.status,
    text: job.status,
  }));
  box.appendChild(head);
  const bar = el('div', {class: 'progress'});
  const fill = el('div');
  fill.style.width = Math.max(0, Math.min(100, job.progress || 0)) + '%';
  bar.appendChild(fill);
  box.appendChild(bar);
  box.appendChild(el('div', {class: 'muted', text: job.message || ''}));
  box.appendChild(el('pre', {class: 'log', text: logText || job.log_tail || ''}));
  if (job.result) {
    const result = el('div', {class: 'result'});
    result.appendChild(el('h5', {text: 'Result'}));
    Object.keys(job.result).forEach(function (key) {
      const line = el('div', {class: 'kv'});
      line.appendChild(document.createTextNode(key + ': '));
      line.appendChild(el('code', {text: String(job.result[key])}));
      result.appendChild(line);
    });
    box.appendChild(result);
  }
  return box;
}

/* Poll one job into a box; ``offsetKey`` tracks the log cursor in ``state``. */
async function pollJobInto(jobId, boxId, offsetKey, onDone) {
  try {
    const job = await api('/api/jobs/' + jobId);
    let logText = job.log_tail || '';
    if (state[offsetKey] > 0) {
      const chunk = await api('/api/jobs/' + jobId + '/log?offset=' + state[offsetKey]);
      state[offsetKey] = chunk.offset;
      logText += (chunk.text || '');
    } else {
      state[offsetKey] = logText.length;
    }
    renderJobBox($(boxId), job, logText);
    if (job.status === 'succeeded' && job.kind === 'dataprep' && job.result) {
      applyDataPrepResult(job.result);
    }
    if (DONE_STATUSES.indexOf(job.status) >= 0) {
      setRecentJob(job);
      applyJobOutputs(job);
    }
    if (onDone) {
      onDone(job, logText);
    }
    if (DONE_STATUSES.indexOf(job.status) < 0) {
      state[offsetKey + 'Timer'] = setTimeout(function () {
        pollJobInto(jobId, boxId, offsetKey, onDone);
      }, 1000);
    } else if (job.status !== 'succeeded') {
      showBanner('Job ' + jobId + ' ' + job.status + ': ' + (job.message || ''), true);
    } else {
      showBanner('Job ' + jobId + ' finished.', false);
    }
  } catch (err) {
    showBanner('Job ' + jobId + ' status failed: ' + err.message, true);
  }
}

async function startDataPrepJob(url, body, title, boxId) {
  try {
    const response = await api(url, {method: 'POST', body: body});
    showBanner(title + ' queued as job ' + response.job_id + '.', false);
    state.dpJobId = response.job_id;
    state.dpLogOffset = 0;
    $(boxId).textContent = 'Queued...';
    resetRecentJob(response.job_id, 'dataprep', title);
    pollJobInto(response.job_id, boxId, 'dpLogOffset');
  } catch (err) {
    showBanner(title + ' failed: ' + err.message, true);
  }
}

function applyDataPrepResult(result) {
  if (result.genome) {
    $('dp-genome').value = result.genome;
  }
  if (result.annotation) {
    $('dp-annotation').value = result.annotation;
  }
  if (result.output_dir) {
    $('dp-output').value = result.output_dir;
  }
  if (result.download_output) {
    $('dp-download-output').value = result.download_output;
    $('dp-output').value = result.download_output;
  }
  if (result.target_fasta) {
    state.targetFasta = result.target_fasta;
    $('dp-target-num').title = result.target_fasta;
  }
  if (result.mask_fasta) {
    state.maskFasta = result.mask_fasta;
  }
  if (result.blastdb) {
    $('dp-blastdb').value = result.blastdb;
  }
  if (result.index_prefix) {
    $('dp-index-prefix').value = result.index_prefix;
  }
}

function initDataPrep() {
  $('dp-download').addEventListener('click', function () {
    startDataPrepJob('/api/dataprep/download', dpDownloadPayload(), 'Download', 'dp-job');
  });
  $('dp-extract-target').addEventListener('click', function () {
    startDataPrepJob('/api/dataprep/extract-target', dpPayload(), 'Extract Target', 'dp-job');
  });
  $('dp-extract-mask').addEventListener('click', function () {
    startDataPrepJob('/api/dataprep/extract-mask', dpPayload(), 'Extract Mask', 'dp-job');
  });
  $('dp-prepare').addEventListener('click', function () {
    startDataPrepJob('/api/dataprep/prepare', dpPayload(), 'Prepare data', 'dp-job');
  });
  $('dp-build-blastdb-button').addEventListener('click', function () {
    startDataPrepJob('/api/dataprep/build-blastdb', dpPayload(), 'Build BLAST DB', 'dp-job');
  });
  $('dp-build-index').addEventListener('click', function () {
    if (!$('dp-index-prefix').value.trim() && !$('dp-output').value.trim()) {
      showBanner('Set an index prefix or an output directory first.', true);
      return;
    }
    startDataPrepJob('/api/dataprep/build-index', dpPayload(), 'Build genome index', 'dp-job');
  });
}

/* ---------------------------------------------------------------- models */

function formatSize(bytes) {
  if (bytes === null || bytes === undefined || bytes === '') {
    return '';
  }
  const value = Number(bytes);
  if (isNaN(value)) {
    return '';
  }
  if (value < 1024) {
    return value + ' B';
  }
  if (value < 1024 * 1024) {
    return (value / 1024).toFixed(1) + ' KB';
  }
  return (value / (1024 * 1024)).toFixed(1) + ' MB';
}

async function loadModels() {
  const container = $('models-groups');
  container.textContent = 'Loading...';
  try {
    const data = await api('/api/models');
    const groups = data.groups || [];
    container.innerHTML = '';
    groups.forEach(function (group) {
      const box = el('div', {class: 'group'});
      box.appendChild(el('h4', {text: group.label || group.protein}));
      const table = el('table', {class: 'models-table'});
      const head = el('tr');
      ['Model', 'Status', 'Path', 'Description', ''].forEach(function (label) {
        head.appendChild(el('th', {text: label}));
      });
      table.appendChild(head);
      (group.models || []).forEach(function (model) {
        const row = el('tr');
        row.appendChild(el('td', {text: model.name || model.key}));
        const statusCell = el('td');
        const status = model.status || 'not_downloaded';
        statusCell.appendChild(el('span', {
          class: 'status status-' + status,
          text: model.status_label || status,
        }));
        row.appendChild(statusCell);
        row.appendChild(el('td', {
          class: 'muted',
          text: model.path || model.url || '',
        }));
        row.appendChild(el('td', {class: 'muted', text: model.description || ''}));
        const actions = el('td');
        if (model.downloadable !== false) {
          const download = el('button', {type: 'button', text: 'Download'});
          download.addEventListener('click', function () {
            startModelAction(model.key, 'download');
          });
          actions.appendChild(download);
        }
        if (model.has_file) {
          const remove = el('button', {type: 'button', text: 'Delete'});
          remove.addEventListener('click', function () {
            startModelAction(model.key, 'delete');
          });
          actions.appendChild(remove);
        }
        row.appendChild(actions);
        table.appendChild(row);
      });
      box.appendChild(table);
      container.appendChild(box);
    });
    const deepKeys = Object.keys(data.deep_statuses || {});
    if (deepKeys.length) {
      const box = el('div', {class: 'group'});
      box.appendChild(el('h4', {text: 'Deep-learning runtime'}));
      deepKeys.forEach(function (key) {
        const line = el('div', {class: 'kv'});
        line.appendChild(document.createTextNode(key + ': '));
        line.appendChild(el('code', {text: String(data.deep_statuses[key])}));
        box.appendChild(line);
      });
      container.appendChild(box);
    }
    $('models-dir').textContent = data.models_dir
      ? ('Model directory: ' + data.models_dir) : '';
  } catch (err) {
    container.textContent = 'Could not load models: ' + err.message;
    showBanner('Could not load models: ' + err.message, true);
  }
}

async function startModelAction(key, action) {
  try {
    const response = await api('/api/models/' + key + '/' + action, {
      method: 'POST',
      body: {},
    });
    showBanner('Model ' + key + ': job ' + response.job_id + ' queued.', false);
    state.modelLogOffset = 0;
    $('models-job').textContent = 'Queued...';
    resetRecentJob(response.job_id, 'models', 'Model ' + key + ' ' + action);
    pollJobInto(response.job_id, 'models-job', 'modelLogOffset', function (job) {
      if (DONE_STATUSES.indexOf(job.status) >= 0) {
        loadModels();
      }
    });
  } catch (err) {
    showBanner('Model ' + key + ' ' + action + ' failed: ' + err.message, true);
  }
}

function initModels() {
  $('models-refresh').addEventListener('click', loadModels);
}
/* -------------------------------------------------------- designer runs */

function setDesignerProgress(percent, label) {
  $('designer-progress-bar').style.width = Math.max(0, Math.min(100, percent || 0)) + '%';
  $('designer-progress-label').textContent = label || '';
}

function appendDesignerLog(text) {
  if (!text) {
    return;
  }
  const pre = $('designer-log');
  pre.textContent += text;
  pre.scrollTop = pre.scrollHeight;
}

async function startDesignerJob(stage) {
  const title = stage === 'find' ? 'Find Targets' : 'Score & Off-target';
  try {
    const response = await api('/api/designer/jobs', {
      method: 'POST',
      body: payload({stage: stage, confirm_policy: state.confirm_policy}),
    });
    state.jobId = response.job_id;
    state.logOffset = 0;
    state.candidates = null;
    state.results = null;
    resetRecentJob(response.job_id, 'designer', title);
    $('designer-export-name').value = '';
    $('designer-log').textContent = '';
    $('designer-candidates-info').textContent = '';
    renderCandidates(null);
    setDesignerProgress(1, title + ' queued as ' + response.job_id + ' ...');
    pollDesignerJob(response.job_id);
  } catch (err) {
    showBanner(title + ' failed: ' + err.message, true);
    setDesignerProgress(0, title + ' failed');
  }
}

async function pollDesignerJob(jobId) {
  try {
    const job = await api('/api/jobs/' + jobId);
    const chunk = await api('/api/jobs/' + jobId + '/log?offset=' + state.logOffset);
    state.logOffset = chunk.offset;
    appendDesignerLog(chunk.text);
    setDesignerProgress(job.progress,
      job.message ? (job.message + ' (' + (job.progress || 0) + '%)')
        : job.status);
    if (DONE_STATUSES.indexOf(job.status) < 0) {
      state.pollTimer = setTimeout(function () { pollDesignerJob(jobId); }, 1000);
      return;
    }
    setRecentJob(job);
    if (job.status === 'succeeded') {
      showBanner('Job ' + jobId + ' finished: ' + job.message, false);
      /* A scored run now has a full output table; show it unless the user
         pinned the concise view by hand. */
      if (job.outputs && job.outputs.scores && !state.resultsViewPinned) {
        setResultsView('full');
      }
      await refreshResultTable();
    } else {
      showBanner('Job ' + jobId + ' ' + job.status + ': ' + (job.message || ''), true);
    }
  } catch (err) {
    showBanner('Job ' + jobId + ' status failed: ' + err.message, true);
  }
}

function pathBaseName(path) {
  const text = String(path || '');
  const cut = Math.max(text.lastIndexOf('/'), text.lastIndexOf('\\'));
  return cut >= 0 ? text.slice(cut + 1) : text;
}

function renderCandidates(data, view) {
  const table = $('designer-candidates');
  const head = table.querySelector('thead');
  const body = table.querySelector('tbody');
  head.innerHTML = '';
  body.innerHTML = '';
  const mode = view || resultsView();
  const kind = mode === 'full' ? 'output' : 'candidate';
  if (!data || !data.rows || !data.rows.length) {
    $('designer-candidates-info').textContent = data
      ? 'No ' + kind + ' rows yet.' : '';
    return;
  }
  const headRow = el('tr');
  headRow.appendChild(el('th', {class: 'pick', text: '#'}));
  data.columns.forEach(function (column) {
    headRow.appendChild(el('th', {text: column}));
  });
  head.appendChild(headRow);
  data.rows.forEach(function (row, index) {
    const tr = el('tr');
    const cell = el('td', {class: 'pick'});
    const box = el('input', {type: 'checkbox'});
    box.dataset.index = String(index);
    cell.appendChild(box);
    tr.appendChild(cell);
    data.columns.forEach(function (column) {
      tr.appendChild(el('td', {text: String(row[column] === undefined ? '' : row[column])}));
    });
    body.appendChild(tr);
  });
  $('designer-candidates-info').textContent = mode === 'full'
    ? data.total + ' output row(s), same as ' + (pathBaseName(data.file) || 'the run output table') + '.'
    : data.total + ' candidate row(s).';
}

async function loadCandidates(jobId) {
  try {
    const data = await api('/api/jobs/' + jobId + '/candidates');
    state.candidates = data;
    renderCandidates(data, 'concise');
    return data;
  } catch (err) {
    $('designer-candidates-info').textContent = 'Candidates unavailable: ' + err.message;
    return null;
  }
}

async function loadResults(jobId) {
  try {
    const data = await api('/api/jobs/' + jobId + '/results');
    state.results = data;
    return data;
  } catch (err) {
    state.results = null;
    return null;
  }
}

/* Show exactly the table the export will write: the run's deliverable output
   table in the "full" view, the candidate columns in the "concise" view. */
async function refreshResultTable() {
  const jobId = state.jobId;
  if (!jobId) {
    renderCandidates(null);
    return null;
  }
  if (resultsView() === 'full') {
    const data = await loadResults(jobId);
    if (data && data.available) {
      renderCandidates(data, 'full');
      return data;
    }
    /* No scored output yet (Find Targets only): fall back to candidates. */
    setResultsView('concise');
    const fallback = await loadCandidates(jobId);
    const info = $('designer-candidates-info');
    if (info) {
      info.textContent = 'No output table yet (run Score & Off-target); '
        + 'showing candidates'
        + (fallback && fallback.total !== undefined
          ? ' (' + fallback.total + ' row(s))' : '') + '.';
    }
    return fallback;
  }
  return await loadCandidates(jobId);
}

function selectedRowIndexes() {
  const boxes = document.querySelectorAll('#designer-candidates input[type=checkbox]');
  const indexes = [];
  Array.prototype.slice.call(boxes).forEach(function (box) {
    if (box.checked) {
      indexes.push(Number(box.dataset.index));
    }
  });
  return indexes;
}

function downloadUrl(url) {
  const link = el('a', {href: url, download: ''});
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

async function exportCandidates(all) {
  if (!state.jobId) {
    showBanner('Run Find Targets before exporting.', true);
    return;
  }
  const rows = all ? 'all' : selectedRowIndexes();
  if (!all && !rows.length) {
    showBanner('Select at least one row, or use Export All.', true);
    return;
  }
  try {
    const response = await api('/api/jobs/' + state.jobId + '/export', {
      method: 'POST',
      body: {
        format: $('designer-export-format').value,
        columns: resultsView(),
        rows: rows,
        filename: $('designer-export-name').value.trim() || null,
      },
    });
    showBanner('Wrote ' + response.written + ' row(s) to ' + response.file + '.', false);
    downloadUrl(response.download_url);
  } catch (err) {
    showBanner('Export failed: ' + err.message, true);
  }
}

function initDesigner() {
  $('designer-mode').addEventListener('change', function () {
    state.mode = $('designer-mode').value;
    renderDesigner();
    schedulePreview();
  });
  $('designer-find').addEventListener('click', function () {
    startDesignerJob('find');
  });
  $('designer-sample').addEventListener('click', loadSampleData);
  $('designer-score').addEventListener('click', function () {
    startDesignerJob('score');
  });
  $('designer-export').addEventListener('click', function () {
    exportCandidates(false);
  });
  $('designer-export-all').addEventListener('click', function () {
    exportCandidates(true);
  });
  $('designer-export-columns').addEventListener('change', function () {
    state.resultsViewPinned = true;
    fillExportFormats(state.schema || {});
    refreshResultTable();
  });
}

/* --------------------------------------------------------------- results */

async function loadJobs() {
  const table = $('jobs-table');
  const body = table.querySelector('tbody') || table;
  body.innerHTML = '';
  try {
    const data = await api('/api/jobs');
    const jobs = data.jobs || [];
    if (!jobs.length) {
      const row = el('tr');
      row.appendChild(el('td', {colspan: '6', text: 'No jobs yet.'}));
      body.appendChild(row);
      return;
    }
    jobs.forEach(function (job) {
      const row = el('tr', {class: 'job-row'});
      row.appendChild(el('td', {text: job.job_id || ''}));
      row.appendChild(el('td', {text: job.kind || ''}));
      row.appendChild(el('td', {text: job.title || ''}));
      const statusCell = el('td');
      statusCell.appendChild(el('span', {
        class: 'status status-' + job.status,
        text: job.status,
      }));
      row.appendChild(statusCell);
      row.appendChild(el('td', {text: String(job.progress || 0) + '%'}));
      row.appendChild(el('td', {text: (job.created || '').replace('T', ' ')}));
      row.addEventListener('click', function () {
        showJobDetail(job.job_id);
      });
      body.appendChild(row);
    });
  } catch (err) {
    body.innerHTML = '';
    const row = el('tr');
    row.appendChild(el('td', {colspan: '6', text: 'Could not load jobs: ' + err.message}));
    body.appendChild(row);
  }
}

async function showJobDetail(jobId) {
  state.detailJobId = jobId;
  state.detailLogOffset = 0;
  const box = $('job-detail');
  box.classList.remove('hidden');
  $('job-detail-title').textContent = 'Job ' + jobId;
  $('job-log').textContent = '';
  $('job-result').innerHTML = '';
  $('job-outputs').innerHTML = '';
  $('job-candidates').innerHTML = '';
  $('job-cancel').classList.remove('hidden');
  pollJobDetail();
}

async function pollJobDetail() {
  const jobId = state.detailJobId;
  if (!jobId) {
    return;
  }
  try {
    const job = await api('/api/jobs/' + jobId);
    setRecentJob(job);
    const chunk = await api('/api/jobs/' + jobId + '/log?offset=' + state.detailLogOffset);
    state.detailLogOffset = chunk.offset;
    if (chunk.text) {
      appendLogTo('job-log', chunk.text);
    } else if (state.detailLogOffset === 0) {
      $('job-log').textContent = job.log_tail || '';
      state.detailLogOffset = (job.log_tail || '').length;
    }
    $('job-progress-bar').style.width = Math.max(0, Math.min(100, job.progress || 0)) + '%';
    $('job-detail-status').textContent = [
      job.status,
      job.message || '',
      job.kind ? ('kind: ' + job.kind) : '',
      job.created ? ('created: ' + job.created.replace('T', ' ')) : '',
      job.finished ? ('finished: ' + job.finished.replace('T', ' ')) : '',
    ].filter(Boolean).join('  |  ');
    if (job.result) {
      const box = $('job-result');
      box.innerHTML = '';
      box.appendChild(el('h4', {text: 'Result'}));
      Object.keys(job.result).forEach(function (key) {
        const line = el('div', {class: 'kv'});
        line.appendChild(document.createTextNode(key + ': '));
        line.appendChild(el('code', {text: String(job.result[key])}));
        box.appendChild(line);
      });
    }
    const outputsBox = $('job-outputs');
    if (outputsBox) {
      outputsBox.innerHTML = '';
      const outputs = job.outputs || {};
      if (Object.keys(outputs).length) {
        outputsBox.appendChild(el('h4', {text: 'Outputs'}));
        Object.keys(outputs).forEach(function (key) {
          const line = el('div', {class: 'kv'});
          line.appendChild(document.createTextNode(key + ': '));
          line.appendChild(el('code', {text: String(outputs[key])}));
          outputsBox.appendChild(line);
        });
      }
    }
    if (job.kind === 'designer') {
      await loadDetailCandidates(jobId);
    }
    if (DONE_STATUSES.indexOf(job.status) < 0) {
      state.detailTimer = setTimeout(pollJobDetail, 1000);
    } else {
      $('job-cancel').classList.add('hidden');
    }
  } catch (err) {
    $('job-detail-status').textContent = 'Could not read job: ' + err.message;
  }
}

function appendLogTo(id, text) {
  const pre = $(id);
  pre.textContent += text;
  pre.scrollTop = pre.scrollHeight;
}

async function loadDetailCandidates(jobId) {
  try {
    const data = await api('/api/jobs/' + jobId + '/candidates');
    const box = $('job-candidates');
    box.innerHTML = '';
    if (!data.rows || !data.rows.length) {
      return;
    }
    box.appendChild(el('h4', {text: 'Candidates (' + data.total + ')'}));
    const table = el('table');
    const head = el('tr');
    data.columns.forEach(function (column) {
      head.appendChild(el('th', {text: column}));
    });
    table.appendChild(head);
    data.rows.slice(0, 200).forEach(function (row) {
      const tr = el('tr');
      data.columns.forEach(function (column) {
        tr.appendChild(el('td', {text: String(row[column] === undefined ? '' : row[column])}));
      });
      table.appendChild(tr);
    });
    box.appendChild(table);
  } catch (err) {
    $('job-candidates').textContent = 'Candidates unavailable: ' + err.message;
  }
}

async function cancelJob() {
  const jobId = state.detailJobId;
  if (!jobId) {
    return;
  }
  try {
    const status = await api('/api/jobs/' + jobId + '/cancel', {
      method: 'POST',
      body: {},
    });
    showBanner('Job ' + jobId + ' ' + (status.status || 'cancelled') + '.', false);
    pollJobDetail();
  } catch (err) {
    showBanner('Cancel failed: ' + err.message, true);
  }
}

async function loadOutputs() {
  const target = $('outputs-dir').value.trim();
  const box = $('outputs-list');
  if (!target) {
    box.textContent = 'Enter an absolute directory path first.';
    return;
  }
  box.textContent = 'Loading...';
  try {
    const data = await api('/api/outputs?dir=' + encodeURIComponent(target));
    box.innerHTML = '';
    if (!data.files.length) {
      box.textContent = 'No listed files in ' + data.dir + '.';
      return;
    }
    const table = el('table');
    const head = el('tr');
    ['File', 'Size', 'Modified'].forEach(function (label) {
      head.appendChild(el('th', {text: label}));
    });
    table.appendChild(head);
    data.files.forEach(function (file) {
      const row = el('tr');
      row.appendChild(el('td', {text: file.name}));
      row.appendChild(el('td', {text: formatSize(file.size)}));
      row.appendChild(el('td', {
        text: new Date(file.modified * 1000).toLocaleString(),
      }));
      table.appendChild(row);
    });
    box.appendChild(table);
  } catch (err) {
    box.textContent = 'Could not list ' + target + ': ' + err.message;
  }
}

function initResults() {
  $('results-refresh').addEventListener('click', loadJobs);
  $('job-cancel').addEventListener('click', cancelJob);
  $('outputs-load').addEventListener('click', loadOutputs);
}

/* ------------------------------------------------------------------ picker */

/* Every path field shares one self-drawn dialog. The browser cannot hand out
 * server-side absolute paths (``<input type="file">`` gives a name and
 * ``showDirectoryPicker()`` gives a handle), so the page lists directories
 * through ``GET /api/fs/list`` and writes the chosen path back itself. */

const PICKER_DIR_KEY = 'crispr.pickerDir';
const PICKER_RECENT_KEY = 'crispr.pickerRecent';
const PICKER_HIDDEN_KEY = 'crispr.pickerHidden';
const PICKER_RECENT_MAX = 5;
const PICKER_HISTORY_MAX = 50;
const PICKER_KINDS = ['any', 'dir', 'fasta', 'annotation', 'bed', 'db', 'index'];

/* Hand-written path inputs (schema does not generate them): id -> kind. */
const PICKER_INPUT_KINDS = {
  'dp-download-output': 'dir',
  'dp-genome': 'fasta',
  'dp-annotation': 'annotation',
  'dp-output': 'dir',
  'dp-blastdb': 'db',
  'dp-index-prefix': 'index',
  'outputs-dir': 'dir',
};

const picker = {
  open: false,
  kind: 'any',
  dir: null,
  parent: null,
  home: null,
  roots: [],
  strip: [],
  entries: [],
  truncated: false,
  selected: null,
  onPick: null,
  /* The field's value while the dialog is up, and the value to look for in
     the first listing that comes back (so the dialog opens on what the field
     already holds). */
  value: '',
  highlight: null,
  showHidden: false,
  /* Request counter: a listing that comes back after a newer one was asked for
     is stale and must not overwrite the newer one. */
  seq: 0,
  /* Navigation generation: opening a field walks a few candidate directories,
     and any navigation the user starts meanwhile cancels the rest of that walk
     (otherwise a late candidate would overwrite what the user asked for). */
  gen: 0,
  /* Visited directories (oldest first) and where we are inside them. */
  history: [],
  historyAt: -1,
};

function isPickerOpen() {
  return picker.open;
}

function pickerKind(kind) {
  return PICKER_KINDS.indexOf(kind) >= 0 ? kind : 'any';
}

function browseButton(input, kind) {
  const button = el('button', {
    class: 'browse-btn',
    type: 'button',
    text: 'Browse...',
    'data-kind': pickerKind(kind),
  });
  button.addEventListener('click', function () {
    openPicker(button.getAttribute('data-kind'), input.value, function (picked) {
      /* Same write-back as typing: the ``input`` event is what feeds
         state.values and the preview (see the text-input listener above). */
      input.value = picked;
      input.dispatchEvent(new Event('input', {bubbles: true}));
    });
  });
  return button;
}

function attachBrowseButton(input, kind) {
  if (!input || !input.parentNode) {
    return;
  }
  const line = el('div', {class: 'row path-row'});
  input.parentNode.insertBefore(line, input);
  line.appendChild(input);
  line.appendChild(browseButton(input, kind));
}

function dirNameOf(path) {
  const text = cleanText(path).replace(/[\\/]+$/, '');
  const cut = Math.max(text.lastIndexOf('\\'), text.lastIndexOf('/'));
  if (cut < 0) {
    return '';
  }
  const head = text.slice(0, cut);
  if (!head) {
    return text.slice(0, 1);
  }
  if (head.length === 2 && head.charAt(1) === ':') {
    /* Keep the separator the path already uses: "C:/x" must not become
       "C:\x" just because the page happens to run on Windows. */
    return head + (text.charAt(cut) || '\\');
  }
  return head;
}

/* The separator a path is written with. Crumbs must never flip it: a POSIX
   path has to keep "/", and a Windows path typed with forward slashes should
   keep them too. Backslash-free text (which includes every POSIX path) is
   treated as forward-slash. */
function pathSeparator(path) {
  return path.indexOf('\\') >= 0 ? '\\' : '/';
}

async function fetchPickerDir(dir) {
  const query = 'kind=' + encodeURIComponent(picker.kind)
    + (dir ? '&dir=' + encodeURIComponent(dir) : '')
    + (picker.showHidden ? '&hidden=1' : '');
  return api('/api/fs/list?' + query);
}

async function loadPickerDir(dir) {
  const seq = (picker.seq += 1);
  let data;
  try {
    data = await fetchPickerDir(dir);
  } catch (error) {
    return false;
  }
  if (seq !== picker.seq) {
    return false;
  }
  applyPickerListing(data);
  pushPickerHistory(data.dir);
  return true;
}

/* List one directory in the dialog. ``record`` decides whether the directory
   joins the Back/Forward history: the address bar, the crumbs, the places and
   double-clicked rows do, while the Back/Forward buttons themselves must not
   (they would otherwise rewrite the history they are walking). */
async function pickerLoad(dir, record) {
  picker.gen += 1;
  const seq = (picker.seq += 1);
  setPickerListText('Loading...');
  let data;
  try {
    data = await fetchPickerDir(dir);
  } catch (error) {
    if (seq !== picker.seq) {
      return false;
    }
    resetPickerListing();
    setPickerListText('Could not list ' + (dir || '(drives)')
      + ': ' + error.message);
    return false;
  }
  if (seq !== picker.seq) {
    return false;
  }
  applyPickerListing(data);
  if (record) {
    pushPickerHistory(data.dir);
  }
  return true;
}

async function openPicker(kind, currentValue, onPick) {
  const dialog = $('picker');
  const scrim = $('picker-scrim');
  if (!dialog || !scrim) {
    return;
  }
  resetPickerListing();
  picker.open = true;
  picker.kind = pickerKind(kind);
  picker.onPick = onPick || null;
  picker.gen += 1;
  const gen = picker.gen;
  picker.value = cleanText(currentValue);
  picker.highlight = picker.value;
  picker.showHidden = readStorage(PICKER_HIDDEN_KEY) === '1';
  picker.history = [];
  picker.historyAt = -1;
  const hiddenBox = $('picker-hidden');
  if (hiddenBox) {
    hiddenBox.checked = picker.showHidden;
  }
  /* Drop the previous listing before the first candidate loads, so the dialog
     never shows the last field's rows (or an empty box) while it waits. */
  setPickerListText('Loading...');
  dialog.classList.remove('hidden');
  scrim.classList.remove('hidden');
  const pathInput = $('picker-path');
  pathInput.value = picker.value;
  pathInput.focus();
  pathInput.select();
  renderPickerPlaces();
  updatePickerNav();
  updatePickerFoot();

  /* Root mode is asked for first: it is where ``home`` comes from, and it is
     the last candidate to fall back to, so the request is never wasted. */
  let rootData = null;
  try {
    rootData = await fetchPickerDir('');
  } catch (error) {
    rootData = null;
  }
  picker.home = rootData ? rootData.home : null;
  renderPickerPlaces();

  /* Candidates in order: the current value, its directory, the last directory
     this picker used, home, then root mode. A 4xx just means "try the next
     one", so the first open never lands on an empty dialog. ``home`` only
     stands in for a field value that could not be listed: a blank field has
     no current directory to locate, so it keeps the round 1 drive list (Home
     is still one click away in the places bar). */
  const candidates = [];
  if (picker.value) {
    candidates.push(picker.value);
    const parent = dirNameOf(picker.value);
    if (parent && parent !== picker.value) {
      candidates.push(parent);
    }
  }
  const remembered = cleanText(readStorage(PICKER_DIR_KEY));
  if (remembered) {
    candidates.push(remembered);
  }
  if (picker.value && picker.home) {
    candidates.push(picker.home);
  }
  for (let index = 0; index < candidates.length; index += 1) {
    if (gen !== picker.gen) {
      return;
    }
    if (await loadPickerDir(candidates[index])) {
      return;
    }
  }
  if (gen !== picker.gen) {
    return;
  }
  if (rootData) {
    applyPickerListing(rootData);
    return;
  }
  setPickerListText('No readable directory to start from.');
}

function applyPickerListing(data) {
  picker.kind = pickerKind(data.kind);
  picker.dir = data.dir;
  picker.parent = data.parent;
  picker.home = data.home || picker.home;
  picker.roots = data.roots || [];
  picker.strip = data.strip || [];
  picker.entries = data.entries || [];
  picker.truncated = !!data.truncated;
  picker.selected = null;
  $('picker-path').value = data.dir === null ? '' : data.dir;
  $('picker-selected').textContent = '';
  renderPickerRoots(picker.roots);
  renderPickerPlaces();
  renderPickerCrumbs(data.dir);
  renderPickerCount(data);
  renderPickerList(data);
  updatePickerNav();
  updatePickerFoot();
  highlightPickerValue();
}

function resetPickerListing() {
  picker.dir = null;
  picker.parent = null;
  picker.roots = [];
  picker.strip = [];
  picker.entries = [];
  picker.truncated = false;
  picker.selected = null;
  $('picker-selected').textContent = '';
  $('picker-roots').innerHTML = '';
  $('picker-crumbs').innerHTML = '';
  $('picker-count').textContent = '';
  updatePickerNav();
  updatePickerFoot();
}

function renderPickerRoots(roots) {
  const box = $('picker-roots');
  box.innerHTML = '';
  roots.forEach(function (root) {
    const button = el('button',
      {class: 'picker-root', type: 'button', text: root});
    button.addEventListener('click', function () { pickerGoTo(root); });
    box.appendChild(button);
  });
}

/* ---- back / forward history ---------------------------------------- */

function pushPickerHistory(dir) {
  if (!dir) {
    return;
  }
  if (picker.historyAt >= 0 && picker.history[picker.historyAt] === dir) {
    return;
  }
  picker.history = picker.history.slice(0, picker.historyAt + 1);
  picker.history.push(dir);
  if (picker.history.length > PICKER_HISTORY_MAX) {
    picker.history = picker.history.slice(
      picker.history.length - PICKER_HISTORY_MAX);
  }
  picker.historyAt = picker.history.length - 1;
  updatePickerNav();
}

function pickerBackOrForward(step) {
  const at = picker.historyAt + step;
  if (at < 0 || at >= picker.history.length) {
    return;
  }
  picker.historyAt = at;
  const target = picker.history[at];
  $('picker-path').value = target;
  pickerLoad(target, false);
}

function updatePickerNav() {
  const back = $('picker-back');
  const forward = $('picker-forward');
  if (back) {
    back.disabled = picker.historyAt <= 0;
  }
  if (forward) {
    forward.disabled = picker.historyAt < 0
      || picker.historyAt >= picker.history.length - 1;
  }
}

/* ---- crumbs, places, entry count ----------------------------------- */

/* 'C:\data\programfile' -> [{'C:\', 'C:\'}, {'data', 'C:\data'}, ...]
   A POSIX path keeps its own "/" instead of being rewritten with backslashes. */
function pickerCrumbs(dir) {
  const text = cleanText(dir);
  if (!text) {
    return [];
  }
  const separator = pathSeparator(text);
  const segments = text.split(/[\\/]+/).filter(function (part) { return !!part; });
  const crumbs = [];
  let prefix = '';
  if (/^[A-Za-z]:/.test(text)) {
    prefix = segments.shift() + separator;
    crumbs.push({label: prefix, path: prefix});
  } else if (text.charAt(0) === '/') {
    prefix = '/';
    crumbs.push({label: '/', path: '/'});
  }
  segments.forEach(function (part) {
    const tail = prefix.charAt(prefix.length - 1);
    if (prefix && tail !== '/' && tail !== '\\') {
      prefix += separator;
    }
    prefix += part;
    crumbs.push({label: part, path: prefix});
  });
  return crumbs;
}

function renderPickerCrumbs(dir) {
  const box = $('picker-crumbs');
  if (!box) {
    return;
  }
  box.innerHTML = '';
  const crumbs = pickerCrumbs(dir);
  crumbs.forEach(function (crumb, index) {
    if (index) {
      box.appendChild(el('span', {class: 'picker-crumb-sep', text: '>'}));
    }
    const button = el('button', {class: 'picker-crumb', type: 'button',
      text: crumb.label, title: crumb.path});
    if (index === crumbs.length - 1) {
      /* The last segment is the directory already on screen: it renders, but
         clicking it does nothing. */
      button.disabled = true;
    } else {
      button.addEventListener('click', function () { pickerGoTo(crumb.path); });
    }
    box.appendChild(button);
  });
  const last = box.lastElementChild;
  if (last && last.scrollIntoView) {
    last.scrollIntoView({block: 'nearest', inline: 'nearest'});
  }
}

function pickerRecent() {
  const raw = readStorage(PICKER_RECENT_KEY);
  if (!raw) {
    return [];
  }
  try {
    const items = JSON.parse(raw);
    if (!Array.isArray(items)) {
      return [];
    }
    return items.filter(function (item) {
      return typeof item === 'string' && !!item;
    });
  } catch (error) {
    return [];
  }
}

function rememberPickerDir(dir) {
  if (!dir) {
    return;
  }
  writeStorage(PICKER_DIR_KEY, dir);
  const items = pickerRecent().filter(function (item) { return item !== dir; });
  items.unshift(dir);
  writeStorage(PICKER_RECENT_KEY,
    JSON.stringify(items.slice(0, PICKER_RECENT_MAX)));
  renderPickerPlaces();
}

function renderPickerPlaces() {
  const box = $('picker-places');
  if (!box) {
    return;
  }
  box.innerHTML = '';
  const places = [];
  if (picker.home) {
    places.push({label: 'Home', path: picker.home});
  }
  pickerRecent().forEach(function (dir) {
    places.push({label: dir, path: dir});
  });
  places.forEach(function (place) {
    const button = el('button', {class: 'picker-place', type: 'button',
      text: place.label, title: place.path});
    button.addEventListener('click', function () { pickerGoTo(place.path); });
    box.appendChild(button);
  });
}

function renderPickerCount(data) {
  const node = $('picker-count');
  if (!node) {
    return;
  }
  if (!data || data.dir === null || data.dir === undefined) {
    node.textContent = '';
    return;
  }
  let folders = 0;
  let files = 0;
  (data.entries || []).forEach(function (entry) {
    if (entry.type === 'dir') {
      folders += 1;
    } else {
      files += 1;
    }
  });
  let text = folders + ' folder' + (folders === 1 ? '' : 's')
    + ', ' + files + ' file' + (files === 1 ? '' : 's');
  if (data.truncated) {
    text += ' (listing truncated)';
  }
  node.textContent = text;
}

/* ---- rows ----------------------------------------------------------- */

function formatStamp(seconds) {
  if (typeof seconds !== 'number' || !isFinite(seconds) || seconds <= 0) {
    return '';
  }
  const date = new Date(seconds * 1000);

  function pad(value) {
    return value < 10 ? '0' + value : String(value);
  }

  return date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-'
    + pad(date.getDate()) + ' ' + pad(date.getHours()) + ':'
    + pad(date.getMinutes());
}

function pickerBaseName(path) {
  const text = cleanText(path).replace(/[\\/]+$/, '');
  const cut = Math.max(text.lastIndexOf('\\'), text.lastIndexOf('/'));
  return cut < 0 ? text : text.slice(cut + 1);
}

function sameName(left, right) {
  return String(left) === String(right)
    || String(left).toLowerCase() === String(right).toLowerCase();
}

function samePath(left, right) {
  const one = cleanText(left).replace(/[\\/]+$/, '').toLowerCase();
  const two = cleanText(right).replace(/[\\/]+$/, '').toLowerCase();
  return !!one && one === two;
}

function pickerRowsInOrder() {
  return Array.prototype.slice.call(
    $('picker-list').querySelectorAll('.picker-row'));
}

function pickerRowNamed(name) {
  const rows = pickerRowsInOrder();
  for (let index = 0; index < rows.length; index += 1) {
    const node = rows[index].querySelector('.picker-name');
    if (node && sameName(node.textContent, name)) {
      return rows[index];
    }
  }
  return null;
}

/* The row holding the value the field already had, if this listing has one.
   ``db`` / ``index`` fields store a prefix, so one of their member files
   (``<prefix>.nin``, ``<prefix>.ggi``) counts as the same thing. */
function pickerValueRow(value) {
  const name = pickerBaseName(value);
  if (!name || !picker.dir || samePath(value, picker.dir)) {
    return null;
  }
  if (picker.kind === 'db' || picker.kind === 'index') {
    const exact = pickerRowNamed(name);
    if (exact) {
      return exact;
    }
    const suffixes = picker.strip || [];
    for (let index = 0; index < suffixes.length; index += 1) {
      const member = pickerRowNamed(name + suffixes[index]);
      if (member) {
        return member;
      }
    }
    return null;
  }
  const row = pickerRowNamed(name);
  if (!row) {
    return null;
  }
  if (picker.kind === 'dir' && row.getAttribute('data-type') !== 'dir') {
    return null;
  }
  return row;
}

/* Runs once per open, on the first listing that came back. */
function highlightPickerValue() {
  const value = picker.highlight;
  picker.highlight = null;
  if (!value) {
    return;
  }
  const row = pickerValueRow(value);
  if (!row) {
    return;
  }
  selectPickerRow(row);
  row.scrollIntoView({block: 'nearest'});
}

function pickerRow(entry) {
  const row = el('div', {
    class: 'picker-row',
    'data-path': entry.path,
    'data-type': entry.type,
  });
  row.appendChild(el('span', {class: 'picker-icon',
    text: entry.type === 'dir' ? '\u25B8' : ''}));
  row.appendChild(el('span', {class: 'picker-name', text: entry.name}));
  /* .picker-meta stays the container (round 1 used it for the size alone). */
  const meta = el('span', {class: 'picker-meta'});
  meta.appendChild(el('span', {class: 'picker-size',
    text: entry.type === 'file' ? formatSize(entry.size) : ''}));
  meta.appendChild(el('span', {class: 'picker-mod',
    text: formatStamp(entry.modified)}));
  row.appendChild(meta);
  row.addEventListener('click', function () { selectPickerRow(row); });
  row.addEventListener('dblclick', function () { activatePickerRow(row); });
  return row;
}

/* The column header; it must not use .picker-row (probes count those). */
function pickerHeadRow() {
  const row = el('div', {class: 'picker-head-row'});
  row.appendChild(el('span', {class: 'picker-head-icon', text: ''}));
  row.appendChild(el('span', {class: 'picker-head-name', text: 'Name'}));
  row.appendChild(el('span', {class: 'picker-head-size', text: 'Size'}));
  row.appendChild(el('span', {class: 'picker-head-mod', text: 'Modified'}));
  return row;
}

function renderPickerList(data) {
  const box = $('picker-list');
  box.innerHTML = '';
  if (data.dir === null) {
    box.appendChild(el('div', {class: 'muted picker-note',
      text: 'Pick a drive above, or type an absolute path.'}));
    return;
  }
  if (!data.entries.length) {
    box.appendChild(el('div', {class: 'muted picker-note',
      text: 'Nothing to show in ' + data.dir + '.'}));
    return;
  }
  box.appendChild(pickerHeadRow());
  data.entries.forEach(function (entry) { box.appendChild(pickerRow(entry)); });
  if (data.truncated) {
    box.appendChild(el('div', {class: 'muted picker-note',
      text: 'Listing truncated at ' + data.entries.length + ' entries.'}));
  }
}

function setPickerListText(text) {
  $('picker-list').textContent = text;
}

function selectPickerRow(row) {
  const rows = $('picker-list').querySelectorAll('.picker-row');
  Array.prototype.forEach.call(rows, function (item) {
    item.classList.remove('selected');
  });
  row.classList.add('selected');
  picker.selected = {
    path: row.getAttribute('data-path'),
    type: row.getAttribute('data-type'),
  };
  $('picker-selected').textContent = picker.selected.path;
  updatePickerFoot();
}

/* File fields need a row to write back; with nothing selected there is
   nothing to pick, so OK stays disabled. Directory fields always have the
   "use the directory on screen" answer instead. */
function updatePickerFoot() {
  const dirKind = picker.kind === 'dir';
  const here = $('picker-here');
  if (here) {
    here.classList.toggle('hidden', !dirKind);
  }
  const ok = $('picker-ok');
  if (ok) {
    ok.disabled = !dirKind && !picker.selected;
  }
  const selected = $('picker-selected');
  if (selected && !picker.selected && !dirKind) {
    selected.textContent = 'Select a file';
  }
}

function movePickerSelection(step) {
  const rows = pickerRowsInOrder();
  if (!rows.length) {
    return;
  }
  let at = -1;
  for (let index = 0; index < rows.length; index += 1) {
    if (rows[index].classList.contains('selected')) {
      at = index;
      break;
    }
  }
  let next = at + step;
  if (at < 0) {
    next = step > 0 ? 0 : rows.length - 1;
  }
  if (next < 0 || next >= rows.length) {
    return;  /* stopped at the end: the selection stays put */
  }
  selectPickerRow(rows[next]);
  rows[next].scrollIntoView({block: 'nearest'});
}

function activatePickerSelection() {
  const rows = pickerRowsInOrder();
  for (let index = 0; index < rows.length; index += 1) {
    if (rows[index].classList.contains('selected')) {
      activatePickerRow(rows[index]);
      return;
    }
  }
}

function activatePickerRow(row) {
  if (row.getAttribute('data-type') === 'dir') {
    pickerGoTo(row.getAttribute('data-path'));
    return;
  }
  selectPickerRow(row);
  confirmPicker();
}

async function pickerGo() {
  await pickerLoad(cleanText($('picker-path').value), true);
}

function pickerGoTo(dir) {
  $('picker-path').value = dir;
  return pickerGo();
}

function pickerUp() {
  if (picker.parent === null || picker.parent === undefined) {
    return;
  }
  pickerGoTo(picker.parent);
}

function stripPickerSuffix(path, strip) {
  const lower = String(path).toLowerCase();
  for (let index = 0; index < (strip || []).length; index += 1) {
    const suffix = String(strip[index] || '');
    if (suffix && lower.endsWith(suffix.toLowerCase())) {
      return path.slice(0, path.length - suffix.length);
    }
  }
  return path;
}

function confirmPicker() {
  let picked = null;
  if (picker.selected) {
    picked = picker.kind === 'dir'
      ? picker.selected.path
      : stripPickerSuffix(picker.selected.path, picker.strip);
  } else if (picker.kind === 'dir' && picker.dir) {
    /* Nothing selected: for a directory field "OK" means the directory on
       screen; for a file field it means "leave the field alone". */
    picked = picker.dir;
  }
  if (!picked) {
    /* Never answer a confirm with silence: the dialog stays open and the
       hint line says what is missing. */
    const hint = $('picker-selected');
    if (hint) {
      hint.textContent = picker.kind === 'dir'
        ? 'Pick a drive or a folder to confirm.'
        : 'Select a file';
    }
    return;
  }
  rememberPickerDir(picker.dir);
  const onPick = picker.onPick;
  closePicker();
  if (onPick) {
    onPick(picked);
  }
}

/* "Use this folder": write back the directory on screen (dir fields only). */
function usePickerDir() {
  if (picker.kind !== 'dir' || !picker.dir) {
    return;
  }
  picker.selected = null;
  confirmPicker();
}

function togglePickerHidden() {
  const box = $('picker-hidden');
  picker.showHidden = !!(box && box.checked);
  writeStorage(PICKER_HIDDEN_KEY, picker.showHidden ? '1' : '0');
  if (picker.open) {
    pickerLoad(picker.dir || '', false);
  }
}

function closePicker() {
  picker.open = false;
  picker.onPick = null;
  const dialog = $('picker');
  const scrim = $('picker-scrim');
  if (dialog) {
    dialog.classList.add('hidden');
  }
  if (scrim) {
    scrim.classList.add('hidden');
  }
}

function initPicker() {
  if (!$('picker')) {
    return;
  }
  $('picker-go').addEventListener('click', pickerGo);
  $('picker-path').addEventListener('keydown', function (event) {
    if (event.key === 'Enter') {
      event.preventDefault();
      pickerGo();
    }
  });
  $('picker-up').addEventListener('click', pickerUp);
  $('picker-back').addEventListener('click', function () {
    pickerBackOrForward(-1);
  });
  $('picker-forward').addEventListener('click', function () {
    pickerBackOrForward(1);
  });
  $('picker-close').addEventListener('click', closePicker);
  $('picker-cancel').addEventListener('click', closePicker);
  $('picker-ok').addEventListener('click', confirmPicker);
  $('picker-here').addEventListener('click', usePickerDir);
  $('picker-scrim').addEventListener('click', closePicker);
  $('picker-hidden').addEventListener('change', togglePickerHidden);
  /* Keyboard while the dialog is up. The address bar only handles Escape
     here: its Enter means "list this path", and typing a path must not move
     the selection. The drawer's own Esc handler (initLayout) checks
     isPickerOpen(), so Esc only ever closes the picker. */
  document.addEventListener('keydown', function (event) {
    if (!picker.open) {
      return;
    }
    if (event.key === 'Escape') {
      event.stopPropagation();
      closePicker();
      return;
    }
    if (document.activeElement === $('picker-path')) {
      return;
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      movePickerSelection(event.key === 'ArrowDown' ? 1 : -1);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      activatePickerSelection();
    } else if (event.key === 'Backspace') {
      event.preventDefault();
      pickerUp();
    }
  });
  Object.keys(PICKER_INPUT_KINDS).forEach(function (id) {
    attachBrowseButton($(id), PICKER_INPUT_KINDS[id]);
  });
}

/* -------------------------------------------------------------------- batch */

/* Multi search-scope x multi pattern batches (see docs/WEBAPP.md). */
const batchState = {
  scopes: [],
  patterns: [],
  newScopeIds: null,
  jobId: null,
  runId: '',
};

const BATCH_FASTA_SUFFIXES = ['.fasta.gz', '.fa.gz', '.fna.gz', '.fasta', '.fa', '.fna'];
const BATCH_BED_SUFFIXES = ['.bed.gz', '.bed'];

function batchPathKind(scope) {
  return (scope.kind || 'sequence') === 'bed' ? 'bed' : 'fasta';
}

function batchStripSuffix(name, suffixes) {
  const lower = name.toLowerCase();
  const ordered = suffixes.slice().sort(function (a, b) { return b.length - a.length; });
  for (let i = 0; i < ordered.length; i += 1) {
    if (lower.endsWith(ordered[i])) {
      return name.slice(0, name.length - ordered[i].length);
    }
  }
  return name;
}

function batchDeriveScopeId(scope) {
  const path = String(scope.path || '').trim();
  const base = path.split(/[\\/]/).pop() || '';
  const isBed = (scope.kind || 'sequence') === 'bed';
  const stem = batchStripSuffix(base, isBed ? BATCH_BED_SUFFIXES : BATCH_FASTA_SUFFIXES);
  return stem || 'scope';
}

/* Mirror services/batch.py scope_id derivation so checkbox values match the server. */
function batchEffectiveScopeIds() {
  const used = {};
  return batchState.scopes.map(function (scope) {
    let base = String(scope.scopeId || '').trim() || batchDeriveScopeId(scope);
    const count = (used[base] || 0) + 1;
    used[base] = count;
    if (count > 1) {
      base = base + '_' + count;
      if (used[base] === undefined) {
        used[base] = 0;
      }
    }
    return base;
  });
}

function batchScopeCheckbox(scopeId, checked, onToggle) {
  const checkbox = el('input', {type: 'checkbox', value: scopeId});
  checkbox.checked = checked;
  checkbox.addEventListener('change', onToggle);
  return el('label', {class: 'inline'}, [
    checkbox,
    document.createTextNode(scopeId),
  ]);
}

function renderBatchNewScopes() {
  const box = $('batch-pattern-scopes');
  if (!box) {
    return;
  }
  box.innerHTML = '';
  batchEffectiveScopeIds().forEach(function (scopeId) {
    const checked = batchState.newScopeIds === null
      || batchState.newScopeIds.indexOf(scopeId) >= 0;
    box.appendChild(batchScopeCheckbox(scopeId, checked, function () {
      batchState.newScopeIds = Array.prototype.slice.call(box.querySelectorAll('input[type=checkbox]'))
        .filter(function (node) { return node.checked; })
        .map(function (node) { return node.value; });
    }));
  });
}

function renderBatchScopes() {
  const table = $('batch-scope-table');
  const tbody = table ? table.querySelector('tbody') : null;
  if (!tbody) {
    return;
  }
  tbody.innerHTML = '';
  batchState.scopes.forEach(function (scope, index) {
    const idInput = el('input', {type: 'text', value: scope.scopeId || '', placeholder: 'scope id'});
    idInput.addEventListener('input', function () {
      scope.scopeId = idInput.value.trim();
      renderBatchNewScopes();
    });
    const pathInput = el('input', {type: 'text', value: scope.path || '', placeholder: 'path'});
    pathInput.addEventListener('input', function () {
      scope.path = pathInput.value;
      renderBatchNewScopes();
    });
    const browse = browseButton(pathInput, batchPathKind(scope));
    const kindSelect = el('select');
    ['sequence', 'bed'].forEach(function (kind) {
      const option = el('option', {value: kind, text: kind});
      if ((scope.kind || 'sequence') === kind) {
        option.selected = true;
      }
      kindSelect.appendChild(option);
    });
    kindSelect.addEventListener('change', function () {
      scope.kind = kindSelect.value;
      renderBatchScopes();
    });
    const maskCheckbox = el('input', {type: 'checkbox'});
    maskCheckbox.checked = scope.maskSameAsTarget !== false;
    const maskInput = el('input', {
      type: 'text',
      value: scope.maskFasta || '',
      placeholder: 'mask fasta',
    });
    const maskBrowse = browseButton(maskInput, 'fasta');
    maskInput.disabled = maskCheckbox.checked;
    maskBrowse.disabled = maskCheckbox.checked;
    maskCheckbox.addEventListener('change', function () {
      scope.maskSameAsTarget = maskCheckbox.checked;
      maskInput.disabled = maskCheckbox.checked;
      maskBrowse.disabled = maskCheckbox.checked;
    });
    maskInput.addEventListener('input', function () {
      scope.maskFasta = maskInput.value;
    });
    const remove = el('button', {type: 'button', text: 'Remove'});
    remove.addEventListener('click', function () {
      batchState.scopes.splice(index, 1);
      renderBatchScopes();
    });
    const pathCell = el('td', {}, [el('div', {class: 'row'}, [pathInput, browse])]);
    const maskCell = el('td', {}, [
      el('div', {class: 'row'}, [
        el('label', {class: 'muted'}, [
          maskCheckbox,
          document.createTextNode(' Same as scope'),
        ]),
        maskInput,
        maskBrowse,
      ]),
    ]);
    tbody.appendChild(el('tr', {}, [
      el('td', {}, [idInput]),
      pathCell,
      el('td', {}, [kindSelect]),
      maskCell,
      el('td', {}, [remove]),
    ]));
  });
  renderBatchNewScopes();
  renderBatchPatterns();
}

function renderBatchPatterns() {
  const table = $('batch-pattern-table');
  const tbody = table ? table.querySelector('tbody') : null;
  if (!tbody) {
    return;
  }
  tbody.innerHTML = '';
  const scopeIds = batchEffectiveScopeIds();
  batchState.patterns.forEach(function (pattern, index) {
    const box = el('div', {class: 'scope-checks'});
    scopeIds.forEach(function (scopeId) {
      const checked = pattern.scopeIds === null
        || pattern.scopeIds.indexOf(scopeId) >= 0;
      box.appendChild(batchScopeCheckbox(scopeId, checked, function () {
        pattern.scopeIds = Array.prototype.slice.call(box.querySelectorAll('input[type=checkbox]'))
          .filter(function (node) { return node.checked; })
          .map(function (node) { return node.value; });
      }));
    });
    const remove = el('button', {type: 'button', text: 'Remove'});
    remove.addEventListener('click', function () {
      batchState.patterns.splice(index, 1);
      renderBatchPatterns();
    });
    tbody.appendChild(el('tr', {}, [
      el('td', {text: pattern.pattern_id}),
      el('td', {text: pattern.designer.mode}),
      el('td', {}, [box]),
      el('td', {}, [remove]),
    ]));
  });
}

function addBatchScope() {
  batchState.scopes.push({
    scopeId: '',
    path: '',
    kind: 'sequence',
    maskSameAsTarget: true,
    maskFasta: '',
  });
  renderBatchScopes();
}

function addBatchPattern() {
  const input = $('batch-pattern-id');
  let patternId = input ? input.value.trim() : '';
  if (!patternId) {
    patternId = String(state.pattern_name || '').trim();
  }
  if (!patternId) {
    showBanner('Enter a pattern id first.', true);
    return;
  }
  const exists = batchState.patterns.some(function (pattern) {
    return pattern.pattern_id === patternId;
  });
  if (exists) {
    showBanner('Pattern id already added: ' + patternId, true);
    return;
  }
  /* Snapshot the current Designer form so later edits do not change it. */
  batchState.patterns.push({
    pattern_id: patternId,
    designer: JSON.parse(JSON.stringify(payload({}))),
    scopeIds: batchState.newScopeIds === null ? null : batchState.newScopeIds.slice(),
  });
  batchState.newScopeIds = null;
  if (input) {
    input.value = '';
  }
  renderBatchNewScopes();
  renderBatchPatterns();
}

function batchPayload() {
  const scopeIds = batchEffectiveScopeIds();
  const scopes = batchState.scopes.map(function (scope, index) {
    const item = {scope_id: scopeIds[index]};
    if ((scope.kind || 'sequence') === 'bed') {
      item.regions = scope.path || '';
    } else {
      item.search_fasta = scope.path || '';
    }
    if (scope.maskSameAsTarget === false) {
      item.mask_fasta = scope.maskFasta || '';
      item.mask_same_as_target = false;
    } else {
      item.mask_same_as_target = true;
    }
    return item;
  });
  const patterns = batchState.patterns.map(function (pattern) {
    return Object.assign({}, pattern.designer, {pattern_id: pattern.pattern_id});
  });
  const assignments = {};
  batchState.patterns.forEach(function (pattern) {
    if (pattern.scopeIds !== null) {
      assignments[pattern.pattern_id] = pattern.scopeIds.slice();
    }
  });
  const body = {
    scopes: scopes,
    patterns: patterns,
    resume: $('batch-resume') ? $('batch-resume').checked : true,
  };
  if (Object.keys(assignments).length) {
    body.assignments = assignments;
  }
  const label = $('batch-label') ? $('batch-label').value.trim() : '';
  if (label) {
    body.batch_label = label;
  }
  return Object.assign(payload({}), body);
}

/* The units table is shared: preview shows the plan, a lookup shows results. */
const BATCH_UNIT_COLUMNS = ['unit_id', 'scope_id', 'pattern_id'];

function setBatchUnitHeader(columns) {
  const table = $('batch-units');
  if (!table) {
    return null;
  }
  const thead = table.querySelector('thead');
  if (thead) {
    thead.innerHTML = '';
    thead.appendChild(el('tr', {}, columns.map(function (column) {
      return el('th', {text: column});
    })));
  }
  const tbody = table.querySelector('tbody');
  if (tbody) {
    tbody.innerHTML = '';
  }
  return tbody;
}

function fillBatchUnitRows(tbody, columns, rows) {
  if (!tbody) {
    return;
  }
  (rows || []).forEach(function (row) {
    tbody.appendChild(el('tr', {}, columns.map(function (column) {
      const value = row[column];
      return el('td', {text: value === undefined || value === null ? '' : String(value)});
    })));
  });
}

function renderBatchUnits(data) {
  fillBatchUnitRows(setBatchUnitHeader(BATCH_UNIT_COLUMNS), BATCH_UNIT_COLUMNS, data.units);
  const note = $('batch-preview-note');
  if (note) {
    const parts = [];
    (data.warnings || []).forEach(function (message) {
      parts.push('WARN: ' + message);
    });
    if (data.batch_root) {
      parts.push('Output: ' + data.batch_root);
    }
    note.textContent = parts.join('  |  ');
  }
}

async function batchPreview() {
  try {
    const data = await api('/api/batch/preview', {method: 'POST', body: batchPayload()});
    renderBatchUnits(data);
    if (data.errors && data.errors.length) {
      showBanner(data.errors[0], true);
    } else {
      showBanner((data.units || []).length + ' unit(s) ready', false);
    }
  } catch (err) {
    showBanner('Batch preview failed: ' + err.message, true);
  }
}

/* A run folder offers the same downloads as a finished job, in the same order. */
const RUN_EXPORT_FILES = [
  'manifest.tsv',
  'summary/batch_scores.tsv',
  'run.log',
  'run.json',
  'batch.json',
];

function renderArtifactButtons(box, entries) {
  if (!box) {
    return;
  }
  box.innerHTML = '';
  (entries || []).forEach(function (entry) {
    if (!entry || !entry[1]) {
      return;
    }
    const button = el('button', {type: 'button', text: entry[0]});
    button.addEventListener('click', function () { downloadUrl(entry[1]); });
    box.appendChild(button);
  });
}

function renderBatchArtifacts(job) {
  const outputs = (job && job.outputs) || {};
  const base = '/api/jobs/' + ((job && job.job_id) || '') + '/download?file=';
  renderArtifactButtons($('batch-artifacts'), [
    ['manifest.tsv', outputs.manifest ? base + encodeURIComponent('export/manifest.tsv') : ''],
    ['batch_scores.tsv', outputs.summary ? base + encodeURIComponent('export/batch_scores.tsv') : ''],
    ['run.log', outputs.log ? base + encodeURIComponent('export/run.log') : ''],
    ['run.json', outputs.download_meta ? base + encodeURIComponent('export/run.json') : ''],
  ]);
}

function renderRunArtifacts(data) {
  const code = data.run_id || '';
  const present = {};
  (data.files || []).forEach(function (file) { present[file.name] = true; });
  const entries = RUN_EXPORT_FILES.filter(function (name) {
    return present[name];
  }).map(function (name) {
    const url = '/api/batch/runs/' + encodeURIComponent(code) +
      '/download?file=' + encodeURIComponent(name);
    return [name.split('/').pop(), url];
  });
  renderArtifactButtons($('batch-artifacts'), entries);
}

async function startBatchJob() {
  try {
    const created = await api('/api/batch/jobs', {method: 'POST', body: batchPayload()});
    batchState.jobId = created.job_id;
    setBatchCode(created.run_id);
    state.batchLogOffset = 0;
    const artifacts = $('batch-artifacts');
    if (artifacts) {
      artifacts.innerHTML = '';
    }
    const box = $('batch-job-box');
    if (box) {
      box.classList.remove('hidden');
    }
    pollJobInto(created.job_id, 'batch-job-box', 'batchLogOffset', function (job) {
      renderBatchArtifacts(job);
      refreshBatchRun(created.run_id, {silent: true});
    });
  } catch (err) {
    showBanner('Batch job failed: ' + err.message, true);
  }
}

/* One batch = one task code (run id). Show it, copy it and look up any code. */
function setBatchCode(runId) {
  batchState.runId = runId ? String(runId) : '';
  const node = $('batch-current-code');
  if (node) {
    node.textContent = batchState.runId || '-';
  }
  const input = $('batch-code-input');
  if (input && batchState.runId) {
    input.value = batchState.runId;
  }
}

function copyBatchCode() {
  const code = batchState.runId;
  if (!code) {
    showBanner('No task code yet; run a batch first.', true);
    return;
  }
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(code).then(
      function () { showBanner('Copied task code ' + code, false); },
      function () { showBanner('Copy failed; select the code manually.', true); });
  } else {
    showBanner('Clipboard unavailable; the code is ' + code, true);
  }
}

function batchKv(parent, key, value) {
  const line = el('div', {class: 'kv'});
  line.appendChild(document.createTextNode(key + ': '));
  line.appendChild(el('code', {text: value}));
  parent.appendChild(line);
}

function renderBatchRunFiles(data) {
  const box = $('batch-run-files');
  if (!box) {
    return;
  }
  box.innerHTML = '';
  const code = data.run_id || '';
  (data.files || []).forEach(function (file) {
    const url = '/api/batch/runs/' + encodeURIComponent(code) +
      '/download?file=' + encodeURIComponent(file.name);
    const button = el('button', {type: 'button', text: file.name});
    button.addEventListener('click', function () { downloadUrl(url); });
    box.appendChild(button);
  });
}

function renderBatchRunDetail(data) {
  const box = $('batch-run-detail');
  if (!box) {
    return;
  }
  box.classList.remove('hidden');
  box.innerHTML = '';
  const units = data.units || {};
  batchKv(box, 'Task code', data.run_id || '');
  batchKv(box, 'Batch label', data.batch_label || '-');
  batchKv(box, 'Created', data.created || '-');
  batchKv(box, 'Path', data.path || '');
  batchKv(box, 'Units', 'total ' + (data.unit_count || 0) +
    ' | ok ' + (units.ok || 0) + ' | failed ' + (units.failed || 0) +
    ' | skipped ' + (units.skipped || 0) + ' | stopped ' + (units.stopped || 0));
  renderBatchRunFiles(data);
  renderBatchRunRows(data);
  renderRunArtifacts(data);
}

/* A looked-up run fills the results table and the export row, like a fresh run. */
function renderBatchRunRows(data) {
  const columns = data.columns && data.columns.length ? data.columns : BATCH_UNIT_COLUMNS;
  fillBatchUnitRows(setBatchUnitHeader(columns), columns, data.rows);
  const note = $('batch-preview-note');
  if (note) {
    const units = data.units || {};
    note.textContent = 'Task ' + (data.run_id || '') +
      '  |  ok ' + (units.ok || 0) +
      ' | failed ' + (units.failed || 0) +
      ' | skipped ' + (units.skipped || 0) +
      ' | stopped ' + (units.stopped || 0) +
      '  |  Output: ' + (data.path || '');
  }
}

function renderBatchRuns(data) {
  const table = $('batch-runs-table');
  const wrap = $('batch-run-list');
  const tbody = table ? table.querySelector('tbody') : null;
  if (!tbody || !wrap) {
    return;
  }
  wrap.classList.remove('hidden');
  tbody.innerHTML = '';
  (data.runs || []).forEach(function (run) {
    const units = run.units || {};
    const open = el('button', {type: 'button', text: run.run_id || ''});
    open.addEventListener('click', function () { loadBatchRun(run.run_id); });
    const codeCell = el('td');
    codeCell.appendChild(open);
    tbody.appendChild(el('tr', {}, [
      codeCell,
      el('td', {text: run.batch_label || '-'}),
      el('td', {text: 'ok ' + (units.ok || 0) + ' / ' + (run.unit_count || 0)}),
      el('td', {text: run.created || '-'}),
    ]));
  });
}

async function refreshBatchRun(code, options) {
  const opts = options || {};
  try {
    const data = await api('/api/batch/runs/' + encodeURIComponent(code));
    setBatchCode(data.run_id);
    renderBatchRunDetail(data);
    if (!opts.silent) {
      showBanner('Task ' + data.run_id + ' loaded.', false);
    }
    return data;
  } catch (err) {
    if (!opts.silent) {
      showBanner('Task code lookup failed: ' + err.message, true);
    }
    return null;
  }
}

async function loadBatchRun(ref) {
  /* Accept 20261006-0114, 20261006/0114 and the bare 0114. */
  const code = String(ref || '').trim().replace(/[\/_]+/g, '-').replace(/^-+|-+$/g, '');
  if (!code) {
    showBanner('Enter a task code to view.', true);
    return;
  }
  await refreshBatchRun(code);
}

async function listBatchRuns() {
  try {
    const data = await api('/api/batch/runs?limit=20');
    renderBatchRuns(data);
    if (!(data.runs || []).length) {
      showBanner('No batch runs yet.', false);
    }
  } catch (err) {
    showBanner('Run list failed: ' + err.message, true);
  }
}

function initBatch() {
  if (!$('batch-wrap')) {
    return;
  }
  $('batch-scope-add').addEventListener('click', addBatchScope);
  $('batch-pattern-add').addEventListener('click', addBatchPattern);
  $('batch-preview').addEventListener('click', batchPreview);
  $('batch-run').addEventListener('click', startBatchJob);
  const copy = $('batch-code-copy');
  if (copy) {
    copy.addEventListener('click', copyBatchCode);
  }
  const lookup = $('batch-code-load');
  if (lookup) {
    lookup.addEventListener('click', function () {
      loadBatchRun($('batch-code-input') ? $('batch-code-input').value : '');
    });
  }
  const recent = $('batch-code-recent');
  if (recent) {
    recent.addEventListener('click', listBatchRuns);
  }
  const input = $('batch-code-input');
  if (input) {
    input.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') {
        loadBatchRun(input.value);
      }
    });
  }
  renderBatchScopes();
}

/* ------------------------------------------------------------------ init */

function init() {
  initLayout();
  initPicker();
  loadSchema();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
