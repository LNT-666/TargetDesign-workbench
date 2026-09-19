/* Master-side independent probe (round 1): the path picker end to end.
 *
 * Run through the shared CDP runner:
 *   node probe_browser_cdp.js probe_master_picker.js
 * Reads only public DOM/handlers -- it never calls picker internals, so it
 * checks the contract the browser actually exposes.
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
  function pickerRows() {
    return Array.prototype.map.call(
      document.querySelectorAll('#picker-list .picker-row'),
      function (row) {
        return {
          name: row.querySelector('.picker-name').textContent,
          type: row.getAttribute('data-type'),
          path: row.getAttribute('data-path') || '',
        };
      });
  }
  function pickerNames() { return pickerRows().map(function (r) { return r.name; }); }
  function rowByName(name) {
    const all = Array.prototype.slice.call(document.querySelectorAll('#picker-list .picker-row'));
    for (let i = 0; i < all.length; i += 1) {
      if (all[i].querySelector('.picker-name').textContent === name) { return all[i]; }
    }
    return null;
  }
  async function waitFor(fn, ms) {
    const limit = ms || 6000;
    for (let waited = 0; waited <= limit; waited += 50) {
      let value = false;
      try { value = fn(); } catch (e) { value = false; }
      if (value) { return value; }
      await sleep(50);
    }
    return null;
  }
  function browseButton(id) {
    const input = $(id);
    if (!input || !input.parentNode || !input.parentNode.querySelector) { return null; }
    return input.parentNode.querySelector('.browse-btn');
  }
  async function openFor(id) {
    const button = browseButton(id);
    if (!button) { return false; }
    click(button);
    return !!(await waitFor(function () { return visible($('picker')); }));
  }
  async function goToList(dir) {
    $('picker-path').value = dir;
    click($('picker-go'));
    await waitFor(function () {
      const text = $('picker-list').textContent;
      return pickerRows().length > 0 || text.indexOf('Nothing to show') >= 0
        || text.indexOf('Could not list') >= 0;
    });
    await sleep(150);
  }
  async function listFastaFixture() {
    await goToList(FIXTURE);
    return pickerNames();
  }
  function drawerHidden() { return $('drawer').getAttribute('aria-hidden'); }

  /* ---- 1. no native file input anywhere, and every path field has a button */
  out.nativeFileInputs = document.querySelectorAll('input[type=file]').length;

  const declaredFields = ['search_fasta', 'bed_regions', 'genome_fasta', 'mask_fasta',
    'output_dir', 'blastdb', 'index_path'];
  const declared = {};
  declaredFields.forEach(function (key) {
    const button = browseButton('field-' + key);
    declared[key] = button ? button.getAttribute('data-kind') : null;
  });
  out.declaredFieldKinds = declared;

  const handwritten = {'dp-download-output': 'dir', 'dp-genome': 'fasta',
    'dp-annotation': 'annotation', 'dp-output': 'dir', 'dp-blastdb': 'db',
    'dp-index-prefix': 'index', 'outputs-dir': 'dir'};
  const actual = {};
  Object.keys(handwritten).forEach(function (id) {
    const button = browseButton(id);
    actual[id] = button ? button.getAttribute('data-kind') : null;
  });
  out.handwrittenFieldKinds = actual;
  out.handwrittenKindsMatch = Object.keys(handwritten).every(function (id) {
    return actual[id] === handwritten[id];
  });
  out.browseButtonLabels = Array.prototype.map.call(
    document.querySelectorAll('.browse-btn'), function (b) { return b.textContent; });

  /* ---- 2. stacking order (D7) */
  out.pickerZIndex = getComputedStyle($('picker')).zIndex;
  out.pickerScrimZIndex = getComputedStyle($('picker-scrim')).zIndex;
  out.pickerAria = {
    role: $('picker').getAttribute('role'),
    modal: $('picker').getAttribute('aria-modal'),
    labelledby: $('picker').getAttribute('aria-labelledby'),
  };

  /* ---- 3. open from a hand-written field, list the fixture as fasta */
  let inputEvents = 0;
  $('dp-genome').addEventListener('input', function () { inputEvents += 1; });
  out.genomeBrowseButtonFound = !!browseButton('dp-genome');
  out.pickerOpenAfterClick = await openFor('dp-genome');
  out.pickerScrimVisibleAtOpen = visible($('picker-scrim'));
  out.pathFocusedAtOpen = document.activeElement === $('picker-path');

  await goToList(FIXTURE);
  out.fastaRows = pickerRows();
  out.fastaNamesExact = out.fastaRows.map(function (r) { return r.name; }).join('|') === 'sub|mini.fna';
  out.fastaWorksOnNotesTxt = out.fastaRows.some(function (r) { return r.name === 'notes.txt'; });
  out.fastaPathsUnderFixture = out.fastaRows.every(function (r) {
    return r.path.indexOf(FIXTURE + '\\') === 0;
  });

  /* ---- 4. double-click a directory row enters it (stays open) */
  const subRow = rowByName('sub');
  out.subRowFound = !!subRow;
  if (subRow) { doubleClick(subRow); }
  await waitFor(function () { return $('picker-path').value !== FIXTURE; });
  await sleep(150);
  out.pathAfterDirEnter = $('picker-path').value;
  out.enterDirKeepsPickerOpen = visible($('picker'));
  out.enterDirExpectedPath = out.pathAfterDirEnter === FIXTURE + '\\sub';
  out.rowsInsideSub = pickerNames();

  click($('picker-up'));
  await waitFor(function () { return $('picker-path').value === FIXTURE; });
  await sleep(150);
  out.pathAfterUp = $('picker-path').value;
  out.namesAfterUp = pickerNames().join('|');

  /* ---- 5. Enter in the path box lists the typed directory */
  $('picker-path').value = FIXTURE;
  $('picker-path').dispatchEvent(new KeyboardEvent('keydown',
    {key: 'Enter', bubbles: true, cancelable: true}));
  await waitFor(function () { return pickerRows().length > 0; });
  await sleep(150);
  out.enterKeyLists = pickerNames().join('|');

  /* ---- 6. double-click a file row confirms and writes back */
  const fastaRow = rowByName('mini.fna');
  out.fastaRowFound = !!fastaRow;
  if (fastaRow) { doubleClick(fastaRow); }
  await sleep(250);
  out.pickerClosedAfterPick = !visible($('picker'));
  out.genomeFastaValueAfterPick = $('dp-genome').value;
  out.genomeFastaValueExpected = $('dp-genome').value === FIXTURE + '\\mini.fna';
  out.inputEventsFired = inputEvents;
  out.storedPickerDir = window.localStorage.getItem('crispr.pickerDir');

  /* ---- 7. db strip uses the longest suffix first (.source.json, not .json) */
  out.blastdbBrowseKind = (browseButton('dp-blastdb') || {}).getAttribute
    ? browseButton('dp-blastdb').getAttribute('data-kind') : null;
  await openFor('dp-blastdb');
  await goToList(FIXTURE);
  out.dbRows = pickerNames();
  const sourceRow = rowByName('mini.blastdb.source.json');
  if (sourceRow) { doubleClick(sourceRow); }
  await sleep(250);
  out.blastdbValueAfterSourceJson = $('dp-blastdb').value;
  out.blastdbStrippedToPrefix = $('dp-blastdb').value === FIXTURE + '\\mini.blastdb';

  /* ---- 8. index strip on miniindex.json */
  await openFor('dp-index-prefix');
  await goToList(FIXTURE);
  const indexRow = rowByName('miniindex.json');
  out.indexRowFound = !!indexRow;
  if (indexRow) { doubleClick(indexRow); }
  await sleep(250);
  out.indexValueAfterPick = $('dp-index-prefix').value;
  out.indexStrippedToPrefix = $('dp-index-prefix').value === FIXTURE + '\\miniindex';

  /* ---- 9. directory field: OK with nothing selected writes the browsed dir */
  await openFor('dp-output');
  out.dirKindRows = (await goToList(FIXTURE), pickerRows());
  out.dirKindOnlyDirs = out.dirKindRows.every(function (r) { return r.type === 'dir'; });
  click($('picker-ok'));
  await sleep(200);
  out.outputDirValueAfterOk = $('dp-output').value;
  out.outputDirUsedBrowsedDir = $('dp-output').value === FIXTURE;
  out.pickerClosedAfterDirOk = !visible($('picker'));

  /* ---- 10. directory field: single click selects, OK confirms that row */
  await openFor('dp-output');
  await goToList(FIXTURE);
  const subRow2 = rowByName('sub');
  if (subRow2) { click(subRow2); }
  out.selectedRowClass = subRow2 ? subRow2.classList.contains('selected') : null;
  out.selectedText = $('picker-selected').textContent;
  click($('picker-ok'));
  await sleep(200);
  out.outputDirValueAfterRowPick = $('dp-output').value;
  out.outputDirUsedSelectedRow = $('dp-output').value === FIXTURE + '\\sub';

  /* ---- 11. Cancel / scrim keep the field value */
  $('dp-output').value = 'KEEP-ME';
  await openFor('dp-output');
  await goToList(FIXTURE);
  const cancelRow = rowByName('sub');
  if (cancelRow) { click(cancelRow); }
  click($('picker-cancel'));
  await sleep(150);
  out.cancelKeptValue = $('dp-output').value === 'KEEP-ME';
  out.pickerClosedAfterCancel = !visible($('picker'));

  await openFor('dp-output');
  await goToList(FIXTURE);
  click($('picker-scrim'));
  await sleep(150);
  out.scrimClickKeptValue = $('dp-output').value === 'KEEP-ME';
  out.pickerClosedAfterScrim = !visible($('picker'));

  /* ---- 12. file field: OK with nothing selected leaves the field alone */
  $('dp-genome').value = 'KEEP-FILE';
  await openFor('dp-genome');
  await goToList(FIXTURE);
  click($('picker-ok'));
  await sleep(200);
  out.fileOkKeptValue = $('dp-genome').value === 'KEEP-FILE';
  out.pickerClosedAfterFileOk = !visible($('picker'));

  /* ---- 13. blank field opens on the drive list; a root button lists that root */
  window.localStorage.removeItem('crispr.pickerDir');
  $('dp-output').value = '';
  await openFor('dp-output');
  await sleep(600);
  const rootButtons = document.querySelectorAll('#picker-roots .picker-root');
  out.rootButtonCount = rootButtons.length;
  out.rootButtonTexts = Array.prototype.map.call(rootButtons, function (b) { return b.textContent; });
  out.rootModeHasNoRows = pickerRows().length === 0;
  out.rootModeNote = $('picker-list').textContent.slice(0, 60);
  if (rootButtons.length) { click(rootButtons[0]); }
  await waitFor(function () { return pickerRows().length > 0; });
  await sleep(200);
  out.pathAfterRootClick = $('picker-path').value;
  out.rootClickListedRoot = out.pathAfterRootClick === out.rootButtonTexts[0];
  out.nodesUnderRoot = pickerRows().slice(0, 6).map(function (r) { return r.name + '/' + r.type; });

  /* ---- 14. a bad path reports inside the dialog, not in the banner */
  $('picker-path').value = 'R:\\no\\such\\dir';
  click($('picker-go'));
  await waitFor(function () { return $('picker-list').textContent.indexOf('Could not list') >= 0; });
  await sleep(200);
  out.errorTextInList = $('picker-list').textContent.slice(0, 90);
  out.errorKeepsPickerOpen = visible($('picker'));
  out.bannerStayedHidden = $('global-banner').classList.contains('hidden');
  out.noRowsAfterError = pickerRows().length === 0;
  click($('picker-cancel'));
  await sleep(150);
  out.cleanupAfterError = !visible($('picker'));

  /* ---- 15. drive root: no parent, Up does nothing */
  await openFor('dp-output');
  await goToList('R:\\');
  out.driveRootPath = $('picker-path').value;
  click($('picker-up'));
  await sleep(400);
  out.pathAfterUpAtDriveRoot = $('picker-path').value;
  out.driveRootUpIsNoop = out.pathAfterUpAtDriveRoot === out.driveRootPath;
  click($('picker-cancel'));
  await sleep(150);

  /* ---- 16. Esc closes only the picker while the drawer stays open */
  if (drawerHidden() === 'false') { click($('drawer-close')); await sleep(200); }
  click($('drawer-toggle'));
  await sleep(300);
  out.drawerOpenBeforeEsc = drawerHidden() === 'false';
  await openFor('dp-genome');
  out.pickerOpenBeforeEsc = visible($('picker'));
  document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
  await sleep(250);
  out.pickerClosedAfterEsc = !visible($('picker'));
  out.drawerStillOpenAfterEsc = drawerHidden() === 'false';
  document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
  await sleep(250);
  out.drawerClosedAfterSecondEsc = drawerHidden() === 'true';

  /* ---- 17. schema-rendered field writes back through the input event */
  let schemaEvents = 0;
  const schemaInput = $('field-genome_fasta');
  schemaInput.addEventListener('input', function () { schemaEvents += 1; });
  await openFor('field-genome_fasta');
  await goToList(FIXTURE);
  const schemaRow = rowByName('mini.fna');
  if (schemaRow) { doubleClick(schemaRow); }
  await sleep(250);
  out.schemaFieldValue = schemaInput.value;
  out.schemaFieldValueExpected = schemaInput.value === FIXTURE + '\\mini.fna';
  out.schemaInputEvents = schemaEvents;

  out.windowErrors = errors;
  out.finishedAt = new Date().toISOString();
  return JSON.stringify(out, null, 2);
})()