/* Servant probe for task webapp-file-picker (round 2): the explorer-style
   picker. Covers opening on the field's current value, crumbs, the column
   header, the entry count, arrow/Enter/Backspace navigation, Back/Forward,
   the places bar, the disabled-OK rule for file fields and the Show hidden
   toggle (fixture2, plus a direct /api/fs/list check).

   Run through assets/probe_browser_cdp.js: this is a page-internal expression
   and returns a string. */
(async function () {
  const FIXTURE = 'R:\\songji\\programfile\\docs\\handoff\\webapp-file-picker\\assets\\fixture';
  const FIXTURE2 = 'R:\\songji\\programfile\\docs\\handoff\\webapp-file-picker\\assets\\fixture2';
  const FASTA_FILE = FIXTURE + '\\mini.fna';
  const SUB = FIXTURE + '\\sub';

  const out = {fixture: FIXTURE, fixture2: FIXTURE2};
  const windowErrors = [];
  window.addEventListener('error', function (event) {
    windowErrors.push(String((event && event.message) || event));
  });

  function $(id) { return document.getElementById(id); }
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function visible(el) {
    if (!el) { return false; }
    return !el.classList.contains('hidden')
      && getComputedStyle(el).display !== 'none';
  }
  function fire(el, type) {
    el.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true}));
  }
  function click(el) { fire(el, 'click'); }
  function key(name) {
    document.dispatchEvent(new KeyboardEvent('keydown',
      {key: name, bubbles: true, cancelable: true}));
  }
  function blurPath() {
    if (document.activeElement === $('picker-path')) {
      $('picker-path').blur();
    }
  }
  function nodes(selector) {
    return Array.prototype.slice.call(document.querySelectorAll(selector));
  }
  function rows() { return nodes('#picker-list .picker-row'); }
  function rowName(row) {
    const node = row.querySelector('.picker-name');
    return node ? node.textContent : null;
  }
  function names() { return rows().map(rowName); }
  function rowByName(name) {
    const found = rows().filter(function (row) {
      return rowName(row) === name;
    });
    return found[0] || null;
  }
  function selectedNames() {
    return rows().filter(function (row) {
      return row.classList.contains('selected');
    }).map(rowName);
  }
  function pickerOpen() { return !$('picker').classList.contains('hidden'); }
  function crumbTexts() {
    return nodes('#picker-crumbs .picker-crumb').map(function (node) {
      return node.textContent;
    });
  }
  function headCells() {
    const head = document.querySelector('#picker-list .picker-head-row');
    if (!head) { return null; }
    return Array.prototype.slice.call(head.children).map(function (node) {
      return node.textContent;
    });
  }
  function browseOf(id) {
    const input = $(id);
    const row = input ? input.parentNode : null;
    return row ? row.querySelector('.browse-btn') : null;
  }
  function placeTexts() {
    return nodes('#picker-places .picker-place').map(function (node) {
      return node.textContent;
    });
  }
  async function waitFor(check, timeout) {
    const deadline = Date.now() + (timeout || 10000);
    while (Date.now() < deadline) {
      if (check()) { return true; }
      await sleep(100);
    }
    return false;
  }
  function listingSettled() {
    const text = $('picker-list').textContent;
    return rows().length > 0 || text.indexOf('Nothing to show') >= 0
      || text.indexOf('Could not list') >= 0
      || nodes('#picker-roots .picker-root').length > 0;
  }
  async function waitForListing(timeout) {
    return waitFor(listingSettled, timeout || 8000);
  }
  async function openFor(id) {
    const button = browseOf(id);
    if (!button) { return false; }
    click(button);
    const opened = await waitFor(function () { return visible($('picker')); });
    await waitForListing();
    return opened;
  }
  async function goToList(dir) {
    $('picker-path').value = dir;
    click($('picker-go'));
    /* Wait for the *crumbs* to show the target: rows alone can still be the
       previous directory's while the new request is in flight. */
    const trimmed = dir.replace(/[\\/]+$/, '');
    const cut = Math.max(trimmed.lastIndexOf('\\'), trimmed.lastIndexOf('/'));
    const label = trimmed.slice(cut + 1) || trimmed;
    await waitFor(function () {
      const crumbs = crumbTexts();
      return $('picker-list').textContent.indexOf('Loading...') < 0
        && crumbs.length > 0
        && crumbs[crumbs.length - 1] === label;
    }, 12000);
    await sleep(150);
  }
  async function closeAll() {
    if (pickerOpen()) { click($('picker-cancel')); }
    await sleep(150);
  }
  function listingSignature() {
    return names().join('|') + '#' + $('picker-count').textContent;
  }
  /* Ticking the box re-lists the directory on screen; wait for that listing to
     land instead of reading the old rows. */
  async function setHidden(checked) {
    const box = $('picker-hidden');
    const before = listingSignature();
    box.checked = checked;
    box.dispatchEvent(new Event('change', {bubbles: true}));
    const changed = await waitFor(function () {
      return $('picker-list').textContent.indexOf('Loading...') < 0
        && listingSignature() !== before;
    }, 12000);
    await sleep(200);
    return changed;
  }
  async function apiNames(url) {
    const response = await fetch(url);
    const data = await response.json();
    return {
      status: response.status,
      names: (data.entries || []).map(function (entry) { return entry.name; }),
    };
  }

  try {
    localStorage.removeItem('crispr.pickerDir');
    localStorage.removeItem('crispr.pickerRecent');
    localStorage.removeItem('crispr.pickerHidden');
  } catch (error) { /* storage disabled */ }
  out.nativeFileInputs = document.querySelectorAll('input[type=file]').length;

  /* ---- 0. an empty field with no stored history keeps the round 1 drive
     list: master's probes 2/13 pin ``#picker-roots`` on that path. ``home``
     only stands in for a field value that cannot be listed, and it is always
     one click away in the places bar (asserted in section 8). ---- */
  const rootPayload = await (await fetch('/api/fs/list?kind=any')).json();
  out.serverHome = rootPayload.home;
  out.serverRoots = rootPayload.roots;
  const annotation = $('dp-annotation');
  annotation.value = '';
  await openFor('dp-annotation');
  out.emptyFieldStartPath = $('picker-path').value;
  out.emptyFieldStartIsHome = !!out.serverHome
    && $('picker-path').value.toLowerCase() === out.serverHome.toLowerCase();
  out.driveButtonsShownForEmptyField =
    nodes('#picker-roots .picker-root').length;
  out.emptyFieldStartShowsDriveList =
    out.emptyFieldStartPath === '' && out.driveButtonsShownForEmptyField > 0;
  await closeAll();

  /* ---- 1. open on the field's current value: fall back to its directory and
     select the row that holds the value. ---- */
  const genome = $('dp-genome');
  let inputEvents = 0;
  genome.addEventListener('input', function () { inputEvents += 1; });
  genome.value = FASTA_FILE;
  out.openOkForGenomeValue = await openFor('dp-genome');
  out.openLandedOnDir = await waitFor(function () {
    return $('picker-path').value === FIXTURE;
  });
  await waitFor(function () { return rows().length > 0; });
  await sleep(200);
  out.openHighlightsCurrentValue = {
    selectedRows: selectedNames(),
    selectedText: $('picker-selected').textContent,
    expected: FASTA_FILE,
  };
  out.openHighlightMatchesValue = selectedNames().length === 1
    && selectedNames()[0] === 'mini.fna'
    && $('picker-selected').textContent === FASTA_FILE;
  out.okEnabledWithHighlightedFile = !$('picker-ok').disabled;

  /* ---- 2. crumbs, column header and entry count of the fasta listing ---- */
  await goToList(FIXTURE);
  out.fastaNames = names();
  out.crumbCount = crumbTexts().length;
  out.crumbTexts = crumbTexts();
  const crumbNodes = nodes('#picker-crumbs .picker-crumb');
  out.lastCrumbDisabled = crumbNodes.length
    ? crumbNodes[crumbNodes.length - 1].disabled : null;
  out.headRowCells = headCells();
  out.headRowLabels = (headCells() || []).filter(function (text) { return !!text; });
  out.countText = $('picker-count').textContent;
  out.rowCount = rows().length;
  out.rowTypes = rows().map(function (row) {
    return row.getAttribute('data-type');
  });
  out.selectionClearedByRelist = selectedNames().length === 0;

  /* ---- 3. arrow keys move the selection and stop at the ends ---- */
  blurPath();
  key('ArrowDown');
  await sleep(80);
  const downOne = selectedNames();
  key('ArrowDown');
  await sleep(80);
  const downTwo = selectedNames();
  for (let i = 0; i < 4; i += 1) { key('ArrowDown'); await sleep(40); }
  const atEnd = selectedNames();
  for (let i = 0; i < 4; i += 1) { key('ArrowUp'); await sleep(40); }
  const atTop = selectedNames();
  out.downArrowMovesSelection = {first: downOne, second: downTwo, end: atEnd, top: atTop};
  out.downArrowWorks = downOne[0] === 'sub' && downTwo[0] === 'mini.fna';
  out.arrowStopsAtEnd = atEnd[0] === 'mini.fna';
  out.arrowStopsAtTop = atTop[0] === 'sub';

  /* ---- 4. Enter on a selected directory enters it ---- */
  const subRow = rowByName('sub');
  click(subRow);
  blurPath();
  key('Enter');
  out.enterEnteredSub = await waitFor(function () {
    return $('picker-path').value === SUB;
  });
  await waitForListing(4000);
  await sleep(150);
  out.enterEntersDir = {
    path: $('picker-path').value,
    stillOpen: pickerOpen(),
    rows: names(),
    listText: $('picker-list').textContent.slice(0, 40),
  };
  out.enterEntersDirOk = out.enterEnteredSub && pickerOpen();
  out.crumbCountInSub = crumbTexts().length;

  /* ---- 5. Back / Forward walk the history; Backspace goes up ---- */
  out.backButtonEnabled = !$('picker-back').disabled;
  out.forwardDisabledAtTip = $('picker-forward').disabled;
  click($('picker-back'));
  out.backGoesBack = await waitFor(function () {
    return $('picker-path').value === FIXTURE;
  });
  await waitForListing(4000);
  out.forwardEnabledAfterBack = !$('picker-forward').disabled;
  click($('picker-forward'));
  out.forwardGoesForward = await waitFor(function () {
    return $('picker-path').value === SUB;
  });
  await waitForListing(4000);
  blurPath();
  key('Backspace');
  out.backspaceGoesUp = await waitFor(function () {
    return $('picker-path').value === FIXTURE;
  });
  await waitForListing(4000);
  await sleep(100);

  /* ---- 6. Enter on a selected file confirms and writes back ---- */
  genome.value = '';
  await closeAll();
  await openFor('dp-genome');
  await goToList(FIXTURE);
  const fileRow = rowByName('mini.fna');
  click(fileRow);
  blurPath();
  key('Enter');
  await sleep(350);
  out.enterConfirmsFile = {
    closed: !pickerOpen(),
    value: genome.value,
    inputEvents: inputEvents,
  };
  out.enterConfirmsFileOk = !pickerOpen() && genome.value === FASTA_FILE
    && inputEvents > 0;

  /* ---- 7. Show hidden: fixture2 with and without the toggle ---- */
  genome.value = '';
  await closeAll();
  await openFor('dp-genome');
  await goToList(FIXTURE2);
  out.hiddenCheckboxAtFixture2 = $('picker-hidden').checked;
  out.hiddenStoredAtFixture2 = localStorage.getItem('crispr.pickerHidden');
  const hiddenBefore = names();
  out.hiddenRelistHappened = await setHidden(true);
  const hiddenAfter = names();
  out.hiddenToggleHidesDotfile = {before: hiddenBefore, after: hiddenAfter};
  out.hiddenToggleWorks = hiddenBefore.indexOf('.dotfile.fna') < 0
    && hiddenBefore.indexOf('plain.fna') >= 0
    && hiddenAfter.indexOf('.dotfile.fna') >= 0
    && hiddenAfter.length === hiddenBefore.length + 1;
  out.hiddenStored = localStorage.getItem('crispr.pickerHidden');
  out.hiddenCheckboxChecked = $('picker-hidden').checked;
  out.hiddenCrumbTexts = crumbTexts();
  out.hiddenToggleRestores = await setHidden(false);
  out.hiddenAfterUncheck = names();
  out.hiddenStoredAfterUncheck = localStorage.getItem('crispr.pickerHidden');

  const dirQuery = 'dir=' + encodeURIComponent(FIXTURE2) + '&kind=fasta';
  out.fixture2ApiDefault = await apiNames('/api/fs/list?' + dirQuery);
  out.fixture2ApiHidden = await apiNames('/api/fs/list?' + dirQuery + '&hidden=1');
  await closeAll();

  /* ---- 8. OK is disabled for a file field with nothing selected ---- */
  genome.value = '';
  await openFor('dp-genome');
  await goToList(FIXTURE);
  out.okDisabledForFileKindWithoutSelection = $('picker-ok').disabled === true;
  out.selectedHintForFileKind = $('picker-selected').textContent;
  out.hereHiddenForFileKind = $('picker-here').classList.contains('hidden');
  click(rowByName('mini.fna'));
  out.okEnabledAfterFileSelection = $('picker-ok').disabled === false;
  out.selectedTextAfterFileSelection = $('picker-selected').textContent;
  await closeAll();

  /* ---- 9. dir fields: "Use this folder" writes the browsed directory ---- */
  const output = $('dp-output');
  output.value = '';
  await openFor('dp-output');
  await goToList(FIXTURE);
  out.hereVisibleForDirKind = !$('picker-here').classList.contains('hidden')
    && visible($('picker-here'));
  out.okEnabledForDirKindWithoutSelection = $('picker-ok').disabled === false;
  out.dirKindRowTypes = rows().map(function (row) {
    return row.getAttribute('data-type');
  });
  click($('picker-here'));
  await sleep(300);
  out.hereWritesCurrentDir = output.value === FIXTURE;
  out.hereClosedPicker = !pickerOpen();
  out.pickerDirStored = localStorage.getItem('crispr.pickerDir');
  out.recentStored = localStorage.getItem('crispr.pickerRecent');
  out.placesAfterConfirm = placeTexts();

  /* ---- 10. the places bar: Home jumps to the server-reported home ---- */
  output.value = '';
  await openFor('dp-output');
  await waitForListing();
  const homePlace = nodes('#picker-places .picker-place').filter(function (node) {
    return node.textContent === 'Home';
  })[0] || null;
  out.homePlaceFound = !!homePlace;
  if (homePlace) {
    const home = homePlace.getAttribute('title') || '';
    click(homePlace);
    out.homePlaceWorks = await waitFor(function () {
      return $('picker-path').value.toLowerCase() === home.toLowerCase();
    });
    await waitForListing(6000);
  }
  await closeAll();
  out.finalHiddenStored = localStorage.getItem('crispr.pickerHidden');

  /* ---- 11. a bad path is reported inside the dialog, not in the banner
     (opening a field fires no input events, so nothing else can touch it) ---- */
  output.value = '';
  await openFor('dp-output');
  const bannerBefore = $('global-banner').className;
  $('picker-path').value = 'R:\\no\\such\\dir';
  click($('picker-go'));
  out.pickerErrorShownInList = await waitFor(function () {
    return $('picker-list').textContent.indexOf('Could not list') >= 0;
  });
  out.pickerErrorText = $('picker-list').textContent.slice(0, 80);
  out.errorKeepsPickerOpen = pickerOpen();
  out.bannerBeforeError = bannerBefore;
  out.bannerAfterError = $('global-banner').className;
  out.bannerUnchangedByPickerError =
    $('global-banner').className === bannerBefore;
  await closeAll();

  out.windowErrors = windowErrors;
  return JSON.stringify(out, null, 2);
})()
