(async function () {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const $ = (id) => document.getElementById(id);
  const out = {windowErrors: []};
  window.addEventListener('error', (e) => { out.windowErrors.push(String(e.message)); });
  function click(el) {
    el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
  }
  async function waitFor(fn, timeoutMs) {
    const until = Date.now() + timeoutMs;
    while (Date.now() < until) {
      try { if (fn()) { return true; } } catch (e) {}
      await sleep(200);
    }
    return false;
  }
  const pickerOpen = () => !$('picker').classList.contains('hidden');
  const btnFor = (id) => $(id).parentNode.querySelector('.browse-btn');
  function setField(id, value) {
    const input = $(id);
    input.value = value;
    input.dispatchEvent(new Event('input', {bubbles: true}));
  }
  function describe(el) {
    if (!el) { return 'null'; }
    return el.tagName + '#' + (el.id || '') + '.' + (el.className || '')
      + '[' + (el.textContent || '').slice(0, 18) + ']';
  }
  function box(sel) {
    const el = document.querySelector(sel);
    if (!el) { return null; }
    const r = el.getBoundingClientRect();
    return {top: Math.round(r.top), bottom: Math.round(r.bottom), h: Math.round(r.height)};
  }
  /* The browser dispatches a real mouse click to whatever element is painted
     at that point; dispatching there is the closest thing to a real click. */
  function realClickAt(sel) {
    const el = document.querySelector(sel);
    const r = el.getBoundingClientRect();
    const x = Math.round(r.left + r.width / 2);
    const y = Math.round(r.top + r.height / 2);
    const top = document.elementFromPoint(x, y);
    const record = {x: x, y: y, top: describe(top),
                    hitsTarget: !!(top && (top === el || el.contains(top)))};
    if (top) { click(top); }
    return record;
  }
  const FIX = 'R:\\songji\\programfile\\docs\\handoff\\webapp-file-picker\\assets\\fixture';
  out.viewport = {w: window.innerWidth, h: window.innerHeight};

  // dir-kind field
  setField('dp-output', FIX);
  click(btnFor('dp-output'));
  await waitFor(() => pickerOpen() && picker.dir, 20000);
  await sleep(600);
  out.dirGeometry = {
    dialog: box('#picker'), list: box('.picker-list'), toolbar: box('.picker-toolbar'),
    foot: box('.picker-foot'), ok: box('#picker-ok'), here: box('#picker-here'),
  };
  const subRow = Array.prototype.slice.call($('picker-list').querySelectorAll('.picker-row'))
    .filter((r) => r.getAttribute('data-type') === 'dir')[0];
  out.dirRowRealClick = subRow ? realClickAt('.picker-row[data-type="dir"]') : null;
  await sleep(400);
  out.dirBeforeOk = {selected: picker.selected && picker.selected.path,
                     value: $('dp-output').value, open: pickerOpen()};
  out.dirOkRealClick = realClickAt('#picker-ok');
  await sleep(1200);
  out.dirAfterOk = {value: $('dp-output').value, open: pickerOpen()};
  if (pickerOpen()) { click($('picker-cancel')); await sleep(300); }

  // fasta-kind field
  setField('dp-genome', FIX + '\\mini.fna');
  click(btnFor('dp-genome'));
  await waitFor(() => pickerOpen() && picker.dir, 20000);
  await sleep(600);
  out.fileGeometry = {foot: box('.picker-foot'), ok: box('#picker-ok')};
  out.fileBeforeOk = {selected: picker.selected && picker.selected.path,
                      value: $('dp-genome').value, open: pickerOpen()};
  out.fileOkRealClick = realClickAt('#picker-ok');
  await sleep(1200);
  out.fileAfterOk = {value: $('dp-genome').value, open: pickerOpen()};
  if (pickerOpen()) { click($('picker-cancel')); }
  return JSON.stringify(out);
})()
