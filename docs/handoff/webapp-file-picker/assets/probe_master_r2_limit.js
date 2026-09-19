/* Master verification probe (round 2): the 2000-entry cap end to end. Opens
   the picker on a local directory holding 2001 files + 1 subdirectory, lists
   it, and reads back the row count and the #picker-count text (the spec wants
   " (listing truncated)" appended). */
(async function () {
  const LIMIT = 'C:\\Users\\ASUS\\AppData\\Local\\Temp\\pickerlimit_r2';
  const out = {};
  const windowErrors = [];
  window.addEventListener('error', function (e) {
    windowErrors.push(String((e && e.message) || e));
  });
  function $(id) { return document.getElementById(id); }
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function nodes(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }
  function rows() { return nodes('#picker-list .picker-row'); }
  function click(el) { el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true})); }
  function crumbTexts() {
    return nodes('#picker-crumbs .picker-crumb').map(function (n) { return n.textContent; });
  }
  async function waitFor(check, timeout) {
    const end = Date.now() + timeout;
    while (Date.now() < end) {
      if (check()) { return true; }
      await sleep(200);
    }
    return false;
  }
  const genome = $('dp-genome');
  genome.value = '';
  const button = genome.parentNode.querySelector('.browse-btn');
  click(button);
  await waitFor(function () { return !$('picker').classList.contains('hidden'); }, 10000);
  $('picker-path').value = LIMIT;
  click($('picker-go'));
  out.crumbLanded = await waitFor(function () {
    return $('picker-list').textContent.indexOf('Loading...') < 0
      && crumbTexts().slice(-1)[0] === 'pickerlimit_r2';
  }, 30000);
  out.rowsRendered = await waitFor(function () { return rows().length >= 2000; }, 60000);
  await sleep(500);
  out.rowCount = rows().length;
  out.countText = $('picker-count').textContent;
  out.countHasTruncatedSuffix = $('picker-count').textContent.indexOf(' (listing truncated)') >= 0;
  out.firstRow = rows().length ? rows()[0].querySelector('.picker-name').textContent : null;
  out.lastRow = rows().length ? rows()[rows().length - 1].querySelector('.picker-name').textContent : null;
  out.headRowPresent = !!document.querySelector('#picker-list .picker-head-row');
  out.listTextTail = $('picker-list').textContent.slice(-40);
  click($('picker-cancel'));
  await sleep(200);
  out.windowErrors = windowErrors;
  return JSON.stringify(out, null, 2);
})()