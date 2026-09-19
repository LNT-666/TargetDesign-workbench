/* Master verification probe (round 2, gaps): the column header is not a sort
   control, the row cells carry size/modified (and the directory icon), and the
   places bar keeps a de-duplicated most-recent-first list of browsed
   directories. */
(async function () {
  const FIXTURE = 'R:\\songji\\programfile\\docs\\handoff\\webapp-file-picker\\assets\\fixture';
  const SUB = FIXTURE + '\\sub';
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
  function rowByName(name) {
    return rows().filter(function (row) { return rowName(row) === name; })[0] || null;
  }
  function click(el) {
    el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
  }
  function placeTexts() {
    return nodes('#picker-places .picker-place').map(function (n) { return n.textContent; });
  }
  function crumbTexts() {
    return nodes('#picker-crumbs .picker-crumb').map(function (n) { return n.textContent; });
  }
  async function waitFor(check, timeout) {
    const end = Date.now() + timeout;
    while (Date.now() < end) {
      if (check()) { return true; }
      await sleep(100);
    }
    return false;
  }
  async function openFor(id) {
    const input = $(id);
    const button = input.parentNode.querySelector('.browse-btn');
    click(button);
    await waitFor(function () { return !$('picker').classList.contains('hidden'); }, 10000);
    await waitFor(function () {
      return $('picker-list').textContent.indexOf('Loading...') < 0;
    }, 12000);
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
  async function close() {
    click($('picker-cancel'));
    await sleep(250);
  }

  const output = $('dp-output');
  const genome = $('dp-genome');
  try {
    localStorage.removeItem('crispr.pickerRecent');
    localStorage.removeItem('crispr.pickerDir');
  } catch (error) { /* storage disabled */ }

  /* ---- 1. header is not a sort control (fasta field, so files are listed) ---- */
  genome.value = FIXTURE + '\\mini.fna';
  await openFor('dp-genome');
  await goTo(FIXTURE);
  const before = names();
  const head = document.querySelector('#picker-list .picker-head-row');
  out.headCells = Array.prototype.map.call(head.children, function (cell) {
    return {text: cell.textContent, cls: cell.className};
  });
  Array.prototype.forEach.call(head.children, function (cell) { click(cell); });
  await sleep(500);
  out.namesBeforeHeaderClicks = before;
  out.namesAfterHeaderClicks = names();
  out.headerClickDoesNotSort = JSON.stringify(before) === JSON.stringify(names());

  /* ---- 2. row cells ---- */
  const fileRow = rowByName('mini.fna');
  const dirRow = rowByName('sub');
  out.fileRowCells = {
    size: fileRow.querySelector('.picker-size') ? fileRow.querySelector('.picker-size').textContent : null,
    mod: fileRow.querySelector('.picker-mod') ? fileRow.querySelector('.picker-mod').textContent : null,
    icon: fileRow.querySelector('.picker-icon').textContent,
    metaPresent: !!fileRow.querySelector('.picker-meta'),
  };
  out.dirRowCells = {
    size: dirRow.querySelector('.picker-size') ? dirRow.querySelector('.picker-size').textContent : null,
    mod: dirRow.querySelector('.picker-mod') ? dirRow.querySelector('.picker-mod').textContent : null,
    icon: dirRow.querySelector('.picker-icon').textContent,
  };
  out.modifiedLooksLikeStamp = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(out.fileRowCells.mod || '');
  out.sizeLooksLikeBytes = /B$/.test(out.fileRowCells.size || '');
  out.dirRowHasNoSize = out.dirRowCells.size === '';
  out.dirRowIconOk = out.dirRowCells.icon === '\u25B8';

  /* ---- 3. places: de-duplicated, most recent first ---- */
  click($('picker-cancel'));
  await sleep(300);
  output.value = '';
  await openFor('dp-output');
  await goTo(FIXTURE);
  click($('picker-here'));
  await sleep(600);
  out.placesAfterFixture = placeTexts();
  output.value = '';
  await openFor('dp-output');
  await goTo(SUB);
  click($('picker-here'));
  await sleep(600);
  out.placesAfterSub = placeTexts();
  output.value = '';
  await openFor('dp-output');
  await goTo(FIXTURE);
  click($('picker-here'));
  await sleep(600);
  out.placesAfterFixtureAgain = placeTexts();
  out.recentStored = localStorage.getItem('crispr.pickerRecent');
  const recent = JSON.parse(out.recentStored || '[]');
  out.recentMostRecentFirst = recent[0] === FIXTURE && recent[1] === SUB;
  out.recentDeduped = recent.filter(function (d) { return d === FIXTURE; }).length === 1;
  out.recentCapHonoured = recent.length <= 5;
  out.placesShapeOk = JSON.stringify(out.placesAfterFixture) === JSON.stringify(['Home', FIXTURE])
    && JSON.stringify(out.placesAfterSub) === JSON.stringify(['Home', SUB, FIXTURE])
    && JSON.stringify(out.placesAfterFixtureAgain) === JSON.stringify(['Home', FIXTURE, SUB]);
  out.windowErrors = windowErrors;
  return JSON.stringify(out, null, 2);
})()