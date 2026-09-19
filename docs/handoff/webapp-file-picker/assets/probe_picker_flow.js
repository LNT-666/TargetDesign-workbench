/* Servant probe for task webapp-file-picker (round 1).

   Drives the in-page path picker end to end: Browse... button presence on a
   schema-rendered field (genome_fasta), on a drawer input (dp-blastdb) and on a
   Run Settings field (index_path), the fasta/db/dir/kinds of the listing, the
   write-back (value + input event), the suffix strip, and the Esc rule that
   keeps the Data prep drawer open while the picker is up.

   Run as a page-internal expression: the runner does
   Runtime.evaluate({awaitPromise: true, returnByValue: true}) and this file must
   return a string. */
(async function () {
  const FIXTURE = 'R:\\songji\\programfile\\docs\\handoff\\webapp-file-picker\\assets\\fixture';
  const EXPECTED_GENOME = FIXTURE + '\\mini.fna';
  const EXPECTED_BLASTDB = FIXTURE + '\\mini.blastdb';
  const EXPECTED_INDEX = FIXTURE + '\\miniindex';

  const out = {fixture: FIXTURE, expectedGenomeFastaValue: EXPECTED_GENOME};
  const windowErrors = [];
  window.addEventListener('error', function (event) {
    windowErrors.push(String((event && event.message) || event));
  });
  try {
    /* Start from a known state so the first open really falls back to root
       mode; the pick below must store the directory again. */
    localStorage.removeItem('crispr.pickerDir');
  } catch (error) { /* storage disabled */ }

  function $(id) { return document.getElementById(id); }
  function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function click(node) { node.dispatchEvent(new MouseEvent('click', {bubbles: true})); }
  function dblclick(node) {
    node.dispatchEvent(new MouseEvent('click', {bubbles: true}));
    node.dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));
  }
  function rows() {
    return Array.prototype.slice.call(
      document.querySelectorAll('#picker-list .picker-row'));
  }
  function rowNames() {
    return rows().map(function (row) {
      const node = row.querySelector('.picker-name');
      return node ? node.textContent : null;
    });
  }
  function rowTypes() {
    return rows().map(function (row) { return row.getAttribute('data-type'); });
  }
  function rowByName(name) {
    return rows().filter(function (row) {
      const node = row.querySelector('.picker-name');
      return node && node.textContent === name;
    })[0] || null;
  }
  function pickerOpen() { return !$('picker').classList.contains('hidden'); }
  function drawerOpen() { return $('drawer').classList.contains('open'); }
  function roots() {
    return Array.prototype.slice.call(
      document.querySelectorAll('#picker-roots .picker-root')
    ).map(function (node) { return node.textContent; });
  }
  function browseOf(input) {
    const field = input ? input.closest('.field') || input.parentNode : null;
    return field ? field.querySelector('.browse-btn') : null;
  }
  /* The first listing of a directory walks a network share, so poll for the
     result instead of guessing a delay. */
  async function waitForRows(timeout) {
    const deadline = Date.now() + (timeout || 10000);
    while (Date.now() < deadline) {
      if (rows().length) { return true; }
      await wait(100);
    }
    return false;
  }
  async function waitForListing(timeout) {
    const deadline = Date.now() + (timeout || 10000);
    while (Date.now() < deadline) {
      if (rows().length || roots().length) { return true; }
      await wait(100);
    }
    return false;
  }
  async function waitForOpen(timeout) {
    const deadline = Date.now() + (timeout || 10000);
    while (Date.now() < deadline) {
      if (pickerOpen()) {
        await waitForListing(3000);
        return true;
      }
      await wait(100);
    }
    return false;
  }
  async function goTo(dir) {
    $('picker-path').value = dir;
    click($('picker-go'));
    return waitForRows();
  }
  async function browseInto(input, dir) {
    click(browseOf(input));
    await waitForOpen();
    await goTo(dir);
  }

  /* 1. The schema-rendered genome_fasta field carries a Browse... button. */
  const genomeInput = $('field-genome_fasta');
  const genomeField = genomeInput ? genomeInput.closest('.field') : null;
  const genomeBrowse = genomeField ? genomeField.querySelector('.browse-btn') : null;
  out.genomeFastaLabel = genomeField && genomeField.querySelector('label')
    ? genomeField.querySelector('label').textContent : null;
  out.genomeFastaInsideCommonInputs = !!(genomeField
    && genomeField.closest('#designer-common-fields'));
  out.genomeFastaHasBrowseButton = !!genomeBrowse;
  out.genomeFastaBrowseText = genomeBrowse ? genomeBrowse.textContent : null;
  out.genomeFastaBrowseKind =
    genomeBrowse ? genomeBrowse.getAttribute('data-kind') : null;

  let inputEvents = 0;
  if (genomeInput) {
    genomeInput.addEventListener('input', function () { inputEvents += 1; });
  }

  /* 2. Opening it shows the dialog and focuses the path box. */
  if (genomeBrowse) { click(genomeBrowse); }
  await waitForOpen();
  out.pickerOpenAfterClick = pickerOpen();
  out.pickerScrimVisibleAfterClick = !$('picker-scrim').classList.contains('hidden');
  out.pickerPathFocused = !!(document.activeElement
    && document.activeElement.id === 'picker-path');
  out.pickerPathValueAtOpen = $('picker-path').value;
  out.rootsShownAtOpen = roots();

  /* 3. kind=fasta listing of the fixture directory. */
  await goTo(FIXTURE);
  out.fastaRowNames = rowNames();
  out.fastaRowTypes = rowTypes();
  out.fastaHidesNotesTxt = out.fastaRowNames.indexOf('notes.txt') < 0;
  out.fastaHidesBlastdb = out.fastaRowNames.indexOf('mini.blastdb.nin') < 0;
  out.fastaNamesExactly = JSON.stringify(out.fastaRowNames)
    === JSON.stringify(['sub', 'mini.fna']);
  out.pickerPathAfterGo = $('picker-path').value;

  /* 3b. Up walks to the parent directory, Go comes back. */
  click($('picker-up'));
  await waitForRows();
  out.upParentDir = $('picker-path').value;
  out.upLandsOnParent = out.upParentDir === FIXTURE.replace(/\\fixture$/, '');
  await goTo(FIXTURE);
  out.fastaRowNamesBackAfterUp = rowNames();

  /* 4. Single click selects, double click on a file confirms and writes back. */
  const fastaRow = rowByName('mini.fna');
  out.fastaRowFound = !!fastaRow;
  if (fastaRow) {
    click(fastaRow);
    out.clickSelectsRow = fastaRow.classList.contains('selected');
    out.pickerSelectedText = $('picker-selected').textContent;
    dblclick(fastaRow);
  }
  await wait(600);
  out.pickerClosedAfterPick = !pickerOpen();
  out.pickerScrimHiddenAfterPick = $('picker-scrim').classList.contains('hidden');
  out.genomeFastaValue = genomeInput ? genomeInput.value : null;
  out.genomeFastaValueIsExpected = out.genomeFastaValue === EXPECTED_GENOME;
  out.inputEventFired = inputEvents > 0;
  out.inputEventCount = inputEvents;
  out.pickerDirStored = localStorage.getItem('crispr.pickerDir');

  /* 5. kind=db from the drawer input: the BLAST prefix is written back. */
  const blastInput = $('dp-blastdb');
  const blastBrowse = browseOf(blastInput);
  out.blastdbHasBrowseButton = !!blastBrowse;
  out.blastdbBrowseKind = blastBrowse ? blastBrowse.getAttribute('data-kind') : null;
  await browseInto(blastInput, FIXTURE);
  out.dbRowNames = rowNames();
  const ninRow = rowByName('mini.blastdb.nin');
  out.dbNinRowFound = !!ninRow;
  if (ninRow && pickerOpen()) {
    click(ninRow);
    click($('picker-ok'));
  }
  await wait(400);
  out.blastdbValueAfterPick = blastInput ? blastInput.value : null;
  out.blastdbSuffixStripped = out.blastdbValueAfterPick === EXPECTED_BLASTDB;

  /* 6. kind=index from Run Settings: the index prefix is written back. */
  const runWrap = $('run-settings-wrap');
  if (runWrap) { runWrap.open = true; }
  const indexInput = $('field-index_path');
  const indexBrowse = browseOf(indexInput);
  out.indexPathHasBrowseButton = !!indexBrowse;
  out.indexPathBrowseKind = indexBrowse ? indexBrowse.getAttribute('data-kind') : null;
  await browseInto(indexInput, FIXTURE);
  out.indexRowNames = rowNames();
  const ggiRow = rowByName('miniindex.ggi');
  out.indexGgiRowFound = !!ggiRow;
  if (ggiRow && pickerOpen()) {
    click(ggiRow);
    click($('picker-ok'));
  }
  await wait(400);
  out.indexPathValueAfterPick = indexInput ? indexInput.value : null;
  out.indexSuffixStripped = out.indexPathValueAfterPick === EXPECTED_INDEX;

  /* 7. kind=dir: no row selected means "use the directory on screen". */
  const outputInput = $('field-output_dir');
  const outputBrowse = browseOf(outputInput);
  out.outputDirBrowseKind = outputBrowse ? outputBrowse.getAttribute('data-kind') : null;
  await browseInto(outputInput, FIXTURE);
  out.dirKindRowNames = rowNames();
  out.dirKindRowTypes = rowTypes();
  if (pickerOpen()) { click($('picker-ok')); }
  await wait(400);
  out.outputDirValueAfterOk = outputInput ? outputInput.value : null;
  out.outputDirUsedBrowsedDirectory = out.outputDirValueAfterOk === FIXTURE;

  /* 8. Cancel/close leaves the field alone. */
  if (genomeBrowse) { click(genomeBrowse); }
  await waitForOpen();
  if (pickerOpen()) { click($('picker-cancel')); }
  await wait(200);
  out.cancelKeepsFieldValue =
    (genomeInput ? genomeInput.value : null) === EXPECTED_GENOME;
  out.pickerClosedAfterCancel = !pickerOpen();

  /* 9. Esc closes the picker but not the Data prep drawer. */
  const toggle = $('drawer-toggle');
  if (toggle && !drawerOpen()) { click(toggle); }
  await wait(400);
  out.drawerOpenBeforeEsc = drawerOpen();
  if (blastBrowse) { click(blastBrowse); }
  await waitForOpen();
  out.pickerOpenBeforeEsc = pickerOpen();
  document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
  await wait(300);
  out.pickerClosedAfterEsc = !pickerOpen();
  out.drawerStillOpenAfterEsc = drawerOpen();
  out.escKeepsDrawerOpen = out.pickerClosedAfterEsc && out.drawerStillOpenAfterEsc;
  out.genomeFastaUnchangedAfterEsc =
    (genomeInput ? genomeInput.value : null) === EXPECTED_GENOME;

  /* 10. At the drawer's minimum width the path box must stay usable next to
     its Browse... button (the .row flex rule). */
  const drawerGenome = $('dp-genome');
  if (drawerGenome && typeof applyDrawerWidth === 'function') {
    applyDrawerWidth(380);
    await wait(400);
    const drawerGenomeBrowse = browseOf(drawerGenome);
    const boxRect = drawerGenome.getBoundingClientRect();
    const buttonRect = drawerGenomeBrowse.getBoundingClientRect();
    out.drawerWidthAtMin = Math.round($('drawer').getBoundingClientRect().width);
    out.drawerNarrowInputWidth = Math.round(boxRect.width);
    out.drawerNarrowButtonWidth = Math.round(buttonRect.width);
    out.drawerNarrowInputUsable = boxRect.width >= 120
      && boxRect.width > buttonRect.width;
    out.drawerNarrowNoOverlap = boxRect.right <= buttonRect.left + 1;
  }

  out.windowErrors = windowErrors;
  return JSON.stringify(out, null, 2);
})()
