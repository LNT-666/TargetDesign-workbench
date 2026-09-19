/* Master-side focused probe 2 (round 1): the four ambiguous points from probe 1.
 *  - every designer mode: which schema path fields render, and do they get a
 *    browse button with the right data-kind (bed_regions only in bed modes)
 *  - the Index Prefix flow with slow, verbose waits (probe 1 saw no row)
 *  - OK on a file field with nothing selected (does the dialog close?)
 *  - what the global banner says while the picker reports a bad path
 *  - candidate fallback: a field holding a *file* path opens on its directory
 */
(async function () {
  const FIXTURE = 'R:\\songji\\programfile\\docs\\handoff\\webapp-file-picker\\assets\\fixture';
  const out = {};
  const errors = [];
  window.addEventListener('error', function (e) { errors.push(String(e.message || e)); });

  function $(id) { return document.getElementById(id); }
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function visible(el) {
    if (!el) { return false; }
    return !el.classList.contains('hidden') && getComputedStyle(el).display !== 'none';
  }
  function fire(el, type) { el.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true})); }
  function click(el) { fire(el, 'click'); }
  function doubleClick(el) { fire(el, 'click'); fire(el, 'dblclick'); }
  function rows() {
    return Array.prototype.map.call(
      document.querySelectorAll('#picker-list .picker-row'),
      function (row) {
        return {name: row.querySelector('.picker-name').textContent,
                type: row.getAttribute('data-type'),
                path: row.getAttribute('data-path') || ''};
      });
  }
  function rowByName(name) {
    const all = Array.prototype.slice.call(document.querySelectorAll('#picker-list .picker-row'));
    for (let i = 0; i < all.length; i += 1) {
      if (all[i].querySelector('.picker-name').textContent === name) { return all[i]; }
    }
    return null;
  }
  function browseButton(id) {
    const input = $(id);
    if (!input || !input.parentNode || !input.parentNode.querySelector) { return null; }
    return input.parentNode.querySelector('.browse-btn');
  }
  async function settle(ms) {
    /* wait for the dialog to stop saying Loading... */
    await sleep(ms || 300);
    for (let i = 0; i < 60; i += 1) {
      const text = $('picker-list').textContent;
      if (text.indexOf('Loading...') < 0) { return; }
      await sleep(100);
    }
  }
  async function openFor(id) {
    const button = browseButton(id);
    if (!button) { return false; }
    click(button);
    await sleep(200);
    return visible($('picker'));
  }

  /* ---- 1. path fields per designer mode */
  const select = $('designer-mode');
  const modes = Array.prototype.map.call(select.options, function (o) { return o.value; });
  const perMode = {};
  for (let i = 0; i < modes.length; i += 1) {
    select.value = modes[i];
    select.dispatchEvent(new Event('change', {bubbles: true}));
    await sleep(400);
    const found = {};
    ['search_fasta', 'bed_regions', 'genome_fasta', 'mask_fasta', 'output_dir',
     'blastdb', 'index_path'].forEach(function (key) {
      const input = $('field-' + key);
      if (!input) { return; }
      const button = browseButton('field-' + key);
      found[key] = button ? button.getAttribute('data-kind') : '(no button)';
    });
    perMode[modes[i]] = found;
  }
  out.pathFieldsPerMode = perMode;
  out.schemaFieldCounts = Object.keys(perMode).map(function (mode) {
    return mode + ':' + Object.keys(perMode[mode]).length;
  });
  out.bedModeHasButton = Object.keys(perMode).some(function (mode) {
    return perMode[mode].bed_regions === 'bed';
  });
  window.localStorage.removeItem('crispr.pickerDir');

  /* ---- 2. Index Prefix flow, slow and verbose */
  const trace = [];
  function snapshot() {
    return {path: $('picker-path').value,
            list: $('picker-list').textContent.slice(0, 80),
            rows: rows().map(function (r) { return r.name + '/' + r.type; })};
  }
  $('dp-index-prefix').value = '';
  trace.push({step: 'before open', visible: visible($('picker')), state: snapshot()});
  out.indexOpenOk = await openFor('dp-index-prefix');
  await settle(400);
  trace.push({step: 'after open', state: snapshot()});
  $('picker-path').value = FIXTURE;
  click($('picker-go'));
  await settle(600);
  trace.push({step: 'after Go', state: snapshot()});
  const indexRow = rowByName('miniindex.json');
  out.indexRowFoundSlow = !!indexRow;
  if (indexRow) { doubleClick(indexRow); }
  await sleep(400);
  out.indexValueSlow = $('dp-index-prefix').value;
  out.indexStrippedSlow = $('dp-index-prefix').value === FIXTURE + '\\miniindex';
  out.indexTrace = trace;

  /* ---- 3. ggi row as well (the other index suffix) */
  $('dp-index-prefix').value = '';
  await openFor('dp-index-prefix');
  await settle(400);
  $('picker-path').value = FIXTURE;
  click($('picker-go'));
  await settle(400);
  const ggiRow = rowByName('miniindex.ggi');
  out.ggiRowFound = !!ggiRow;
  if (ggiRow) { doubleClick(ggiRow); }
  await sleep(400);
  out.ggiValue = $('dp-index-prefix').value;
  out.ggiStripped = $('dp-index-prefix').value === FIXTURE + '\\miniindex';

  /* ---- 4. OK on a fasta field with nothing selected */
  $('dp-genome').value = 'KEEP-FILE';
  await openFor('dp-genome');
  await settle(400);
  const rowsBeforeOk = rows().length;
  click($('picker-ok'));
  await sleep(400);
  out.fileOk_rowsListed = rowsBeforeOk;
  out.fileOk_dialogStillOpen = visible($('picker'));
  out.fileOk_fieldValue = $('dp-genome').value;
  out.fileOk_listText = $('picker-list').textContent.slice(0, 60);
  click($('picker-cancel'));
  await sleep(200);

  /* ---- 5. banner state while the picker reports a bad path */
  const bannerBefore = $('global-banner').className + ' | ' + $('global-banner').textContent.slice(0, 80);
  await openFor('dp-output');
  await settle(400);
  $('picker-path').value = 'R:\\no\\such\\dir';
  click($('picker-go'));
  await settle(500);
  out.bannerBefore = bannerBefore;
  out.bannerAfterError = $('global-banner').className + ' | ' + $('global-banner').textContent.slice(0, 80);
  out.errorListText = $('picker-list').textContent.slice(0, 90);
  out.pickerStillOpenOnError = visible($('picker'));
  click($('picker-cancel'));
  await sleep(200);

  /* ---- 6. candidate fallback: field holds a file path -> opens its directory */
  $('dp-output').value = FIXTURE + '\\mini.fna';
  await openFor('dp-output');
  await settle(600);
  out.filePathCandidate_path = $('picker-path').value;
  out.filePathCandidate_landsOnDir = out.filePathCandidate_path === FIXTURE;
  out.filePathCandidate_rows = rows().map(function (r) { return r.name + '/' + r.type; });
  click($('picker-cancel'));
  await sleep(200);

  /* ---- 7. localStorage root button only in root mode, drives listed */
  window.localStorage.removeItem('crispr.pickerDir');
  $('dp-output').value = '';
  await openFor('dp-output');
  await settle(600);
  out.rootMode_rootsShown = Array.prototype.map.call(
    document.querySelectorAll('#picker-roots .picker-root'),
    function (b) { return b.textContent; });
  click($('picker-cancel'));
  await sleep(200);

  out.windowErrors = errors;
  return JSON.stringify(out, null, 2);
})()