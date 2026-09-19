/* Master verification probe for webapp-file-picker round 2 (added by master).
   Independent of assets/probe_picker_explorer.js. Covers what that probe and
   the six round 1 probes do not: clicking an intermediate crumb, Back/Forward
   history semantics (no rewrite, forward resets after a new navigation), the
   Show hidden preference surviving a close/reopen, the root-mode chrome
   (crumbs / count / places), the address bar swallowing the arrow keys, OK
   staying inert for a file field with nothing selected, "Use this folder"
   ignoring a selected row, and an enumeration of the drawer elements that
   overflow the drawer at its 380px minimum (with a control run that drops the
   round 2 .path-row class). Returns the result as a JSON string. */
(async function () {
  const FIXTURE = 'R:\\songji\\programfile\\docs\\handoff\\webapp-file-picker\\assets\\fixture';
  const FIXTURE2 = 'R:\\songji\\programfile\\docs\\handoff\\webapp-file-picker\\assets\\fixture2';
  const SUB = FIXTURE + '\\sub';
  const ASSETS = 'R:\\songji\\programfile\\docs\\handoff\\webapp-file-picker\\assets';
  const out = {};
  const windowErrors = [];
  window.addEventListener('error', function (e) {
    windowErrors.push(String((e && e.message) || e));
  });

  function $(id) { return document.getElementById(id); }
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function nodes(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }
  function rows() { return nodes('#picker-list .picker-row'); }
  function rowName(row) {
    const node = row.querySelector('.picker-name');
    return node ? node.textContent : null;
  }
  function names() { return rows().map(rowName); }
  function selected() {
    return rows().filter(function (row) {
      return row.classList.contains('selected');
    }).map(rowName);
  }
  function rowByName(name) {
    return rows().filter(function (row) { return rowName(row) === name; })[0] || null;
  }
  function open() { return !$('picker').classList.contains('hidden'); }
  function visible(el) {
    return !!el && !el.classList.contains('hidden')
      && getComputedStyle(el).display !== 'none';
  }
  function click(el) {
    el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
  }
  function key(name) {
    document.dispatchEvent(new KeyboardEvent('keydown',
      {key: name, bubbles: true, cancelable: true}));
  }
  function browseOf(id) {
    const input = $(id);
    return input && input.parentNode ? input.parentNode.querySelector('.browse-btn') : null;
  }
  function crumbs() { return nodes('#picker-crumbs .picker-crumb'); }
  function crumbTexts() {
    return crumbs().map(function (node) { return node.textContent; });
  }
  function placeTexts() {
    return nodes('#picker-places .picker-place').map(function (node) {
      return node.textContent;
    });
  }
  function blurPath() {
    if (document.activeElement === $('picker-path')) { $('picker-path').blur(); }
  }
  function label(el) {
    if (!el) { return null; }
    let text = el.tagName.toLowerCase();
    if (el.id) { text += '#' + el.id; }
    if (el.className && typeof el.className === 'string') {
      text += '.' + el.className.trim().split(/\s+/).join('.');
    }
    return text;
  }
  function box(el) {
    const r = el.getBoundingClientRect();
    return {left: Math.round(r.left), right: Math.round(r.right),
      width: Math.round(r.width)};
  }
  function settled() {
    const text = $('picker-list').textContent;
    return rows().length > 0 || nodes('#picker-roots .picker-root').length > 0
      || text.indexOf('Nothing to show') >= 0 || text.indexOf('Could not list') >= 0;
  }
  async function waitFor(check, timeout) {
    const end = Date.now() + (timeout || 12000);
    while (Date.now() < end) {
      if (check()) { return true; }
      await sleep(100);
    }
    return false;
  }
  async function waitListing(timeout) {
    return waitFor(function () {
      return $('picker-list').textContent.indexOf('Loading...') < 0 && settled();
    }, timeout);
  }
  async function openFor(id) {
    const button = browseOf(id);
    if (!button) { return false; }
    click(button);
    await waitFor(function () { return visible($('picker')); });
    await waitListing();
    return true;
  }
  async function goTo(dir) {
    $('picker-path').value = dir;
    click($('picker-go'));
    const trimmed = dir.replace(/[\\/]+$/, '');
    const cut = Math.max(trimmed.lastIndexOf('\\'), trimmed.lastIndexOf('/'));
    const tail = trimmed.slice(cut + 1) || trimmed;
    await waitFor(function () {
      return $('picker-list').textContent.indexOf('Loading...') < 0
        && crumbTexts().slice(-1)[0] === tail;
    }, 15000);
    await sleep(200);
  }
  async function closeAll() {
    if (open()) { click($('picker-cancel')); }
    await sleep(250);
  }
  async function setHidden(checked) {
    const boxEl = $('picker-hidden');
    const before = names().join('|');
    boxEl.checked = checked;
    boxEl.dispatchEvent(new Event('change', {bubbles: true}));
    const changed = await waitFor(function () {
      return $('picker-list').textContent.indexOf('Loading...') < 0
        && names().join('|') !== before;
    }, 12000);
    await sleep(200);
    return changed;
  }

  const genome = $('dp-genome');
  const output = $('dp-output');
  let inputEvents = 0;
  genome.addEventListener('input', function () { inputEvents += 1; });

  try {
    localStorage.removeItem('crispr.pickerDir');
    localStorage.removeItem('crispr.pickerRecent');
    localStorage.removeItem('crispr.pickerHidden');
  } catch (error) { /* storage disabled */ }

  /* ---- 1. an intermediate crumb is clickable and jumps to that level ---- */
  genome.value = FIXTURE + '\\mini.fna';
  await openFor('dp-genome');
  out.crumbsAtFixture = crumbTexts();
  const assetsCrumb = crumbs().filter(function (node) {
    return node.textContent === 'assets';
  })[0] || null;
  out.crumbAssetsFound = !!assetsCrumb;
  out.crumbAssetsDisabled = assetsCrumb ? assetsCrumb.disabled : null;
  if (assetsCrumb) {
    click(assetsCrumb);
    out.crumbJumpLanded = await waitFor(function () {
      return $('picker-path').value === ASSETS;
    });
  }
  await waitListing();
  await sleep(150);
  out.crumbJump = {
    path: $('picker-path').value,
    tail: crumbTexts().slice(-1)[0],
    rowCount: names().length,
  };
  out.crumbJumpOk = $('picker-path').value === ASSETS;

  /* ---- 2. Back / Forward semantics ---- */
  out.historyAfterCrumbJump = {
    backEnabled: !$('picker-back').disabled,
    forwardDisabled: $('picker-forward').disabled,
  };
  click($('picker-back'));
  out.backLandsOnFixture = await waitFor(function () {
    return $('picker-path').value === FIXTURE;
  });
  await waitListing();
  out.forwardEnabledAfterBack = !$('picker-forward').disabled;
  click($('picker-back'));
  await sleep(700);
  out.secondBackIsNoop = $('picker-path').value === FIXTURE;
  await goTo(SUB);
  out.forwardDisabledAfterNewNavigation = $('picker-forward').disabled;
  click($('picker-back'));
  out.backAfterNewNavigation = await waitFor(function () {
    return $('picker-path').value === FIXTURE;
  });
  await waitListing();
  out.forwardEnabledAfterNewNavigation = !$('picker-forward').disabled;

  /* ---- 3. Show hidden is remembered across a close/reopen ---- */
  genome.value = '';
  await closeAll();
  await openFor('dp-genome');
  await goTo(FIXTURE2);
  out.hiddenBeforeToggle = names();
  out.hiddenToggleChanged = await setHidden(true);
  out.hiddenAfterToggle = names();
  await closeAll();
  await openFor('dp-genome');
  await goTo(FIXTURE2);
  out.hiddenReopen = {
    checkboxChecked: $('picker-hidden').checked,
    stored: localStorage.getItem('crispr.pickerHidden'),
    names: names(),
  };
  out.hiddenReopenOk = $('picker-hidden').checked
    && $('picker-hidden').checked === true
    && out.hiddenReopen.names.indexOf('.dotfile.fna') >= 0;
  out.hiddenUntoggleChanged = await setHidden(false);
  out.hiddenAfterUntoggle = names();

  /* ---- 4. root mode still renders the round 1 chrome correctly ---- */
  $('dp-annotation').value = '';
  await closeAll();
  await openFor('dp-annotation');
  out.rootMode = {
    path: $('picker-path').value,
    crumbs: crumbTexts().length,
    count: $('picker-count').textContent,
    rowCount: names().length,
    rootButtons: nodes('#picker-roots .picker-root').length,
    places: placeTexts(),
    listNote: $('picker-list').textContent.slice(0, 60),
  };
  out.rootModeOk = out.rootMode.path === '' && out.rootMode.crumbs === 0
    && out.rootMode.count === '' && out.rootMode.rowCount === 0
    && out.rootMode.rootButtons === 3 && out.rootMode.places.indexOf('Home') >= 0;

  /* ---- 5. the address bar keeps the arrow keys (spec: only Escape there) ---- */
  genome.value = '';
  await closeAll();
  await openFor('dp-genome');
  await goTo(FIXTURE);
  $('picker-path').focus();
  key('ArrowDown');
  await sleep(200);
  out.arrowWhilePathFocused = selected();
  blurPath();
  key('ArrowDown');
  await sleep(200);
  out.arrowAfterBlur = selected();
  out.addressBarSwallowsArrows = out.arrowWhilePathFocused.length === 0
    && out.arrowAfterBlur.length === 1;

  /* ---- 6. OK does nothing for a file field with nothing selected ---- */
  await goTo(FIXTURE);
  genome.value = 'KEEP-ME';
  out.okDisabledWithNoSelection = $('picker-ok').disabled;
  click($('picker-ok'));
  await sleep(400);
  out.okClickKeptDialogOpen = open();
  out.okClickKeptFieldValue = genome.value;
  out.okInertForFileKind = out.okDisabledWithNoSelection
    && out.okClickKeptDialogOpen && genome.value === 'KEEP-ME';
  await closeAll();

  /* ---- 7. "Use this folder" writes the browsed directory, not the row ---- */
  output.value = '';
  await openFor('dp-output');
  await goTo(FIXTURE);
  click(rowByName('sub'));
  await sleep(200);
  out.hereSelection = selected();
  out.hereVisibleWithDirKind = visible($('picker-here'));
  click($('picker-here'));
  await sleep(400);
  out.hereFieldValue = output.value;
  out.hereWritesBrowsedDir = output.value === FIXTURE;
  out.hereClosedDialog = !open();
  await closeAll();

  /* ---- 8. drawer overflow at the 380px minimum, with attribution ---- */
  if ($('drawer').getAttribute('aria-hidden') === 'true') {
    click($('drawer-toggle'));
    await sleep(400);
  }
  document.documentElement.style.setProperty('--drawer-width', '380px');
  await sleep(600);
  const drawer = $('drawer');
  const dbox = drawer.getBoundingClientRect();
  out.drawer = {
    box: box(drawer),
    clientWidth: drawer.clientWidth,
    scrollWidth: drawer.scrollWidth,
    overflowX: getComputedStyle(drawer).overflowX,
    padding: getComputedStyle(drawer).padding,
    borderRight: getComputedStyle(drawer).borderRightWidth,
  };
  const inside = nodes('*').filter(function (el) { return drawer.contains(el); });
  const widest = inside.map(function (el) {
    return {el: label(el), width: Math.round(el.getBoundingClientRect().width)};
  }).sort(function (a, b) { return b.width - a.width; }).slice(0, 8);
  out.drawerWidest = widest;
  const offenders = inside.filter(function (el) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) { return false; }
    const style = getComputedStyle(el);
    return r.right > dbox.right + 1
      || (el.scrollWidth > el.clientWidth + 1 && style.overflowX !== 'visible')
      || r.width > dbox.width + 1;
  }).map(function (el) {
    const style = getComputedStyle(el);
    return {el: label(el), box: box(el), scrollWidth: el.scrollWidth,
      clientWidth: el.clientWidth, overflowX: style.overflowX,
      minWidth: style.minWidth, width: style.width};
  });
  out.drawerOffenders = offenders.slice(0, 10);
  out.drawerOffenderCount = offenders.length;
  const modelsTable = document.querySelector('.models-table');
  if (modelsTable) {
    out.modelsTable = {box: box(modelsTable),
      width: getComputedStyle(modelsTable).width,
      minWidth: getComputedStyle(modelsTable).minWidth,
      tableLayout: getComputedStyle(modelsTable).tableLayout,
      scrollWidth: modelsTable.scrollWidth,
      clientWidth: modelsTable.clientWidth};
  }
  /* control A: drop the round 2 .path-row class and measure again */
  const pathRows = nodes('.path-row');
  out.pathRowCount = pathRows.length;
  pathRows.forEach(function (row) { row.classList.remove('path-row'); });
  await sleep(400);
  out.drawerWithoutPathRow = {
    clientWidth: drawer.clientWidth, scrollWidth: drawer.scrollWidth,
    offenders: nodes('*').filter(function (el) {
      return drawer.contains(el) && el.getBoundingClientRect().right > dbox.right + 1;
    }).length,
  };
  pathRows.forEach(function (row) { row.classList.add('path-row'); });
  await sleep(300);
  /* control B: the picker's own DOM is outside the drawer scroll box */
  genome.value = '';
  await openFor('dp-genome');
  await waitListing();
  out.drawerWhilePickerOpen = {
    clientWidth: drawer.clientWidth, scrollWidth: drawer.scrollWidth,
  };
  await closeAll();

  out.nativeFileInputs = document.querySelectorAll('input[type=file]').length;
  out.inputEventsOnGenome = inputEvents;
  out.windowErrors = windowErrors;
  return JSON.stringify(out, null, 2);
})()