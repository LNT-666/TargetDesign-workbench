/* Master-side focused probe 4 (round 1): geometry details behind two flags
 * from probe 3 -- the outputs-dir row wrapping, and what overflows the drawer
 * at its 380px minimum width.
 */
(async function () {
  const out = {};
  function $(id) { return document.getElementById(id); }
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function fire(el, type) {
    el.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true}));
  }
  function box(el) {
    const r = el.getBoundingClientRect();
    return {left: Math.round(r.left), right: Math.round(r.right),
            top: Math.round(r.top), bottom: Math.round(r.bottom),
            width: Math.round(r.width), height: Math.round(r.height)};
  }
  function label(el) {
    if (!el) { return null; }
    return el.tagName.toLowerCase() + (el.id ? ('#' + el.id) : '')
      + (el.className && typeof el.className === 'string' ? ('.' + el.className.trim().split(/\s+/).join('.')) : '');
  }

  if ($('drawer').getAttribute('aria-hidden') === 'true') { fire($('drawer-toggle'), 'click'); }
  await sleep(300);
  document.documentElement.style.setProperty('--drawer-width', '380px');
  await sleep(400);

  /* ---- A. outputs-dir row, at the current main-area width */
  const outputsInput = $('outputs-dir');
  const outputsRow = outputsInput.parentNode;
  const outputsButton = outputsRow.querySelector('.browse-btn');
  out.outputsRow = {
    row: label(outputsRow),
    rowBox: box(outputsRow),
    rowWrap: getComputedStyle(outputsRow).flexWrap,
    inputBox: box(outputsInput),
    buttonBox: box(outputsButton),
    buttonBelowInput: box(outputsButton).top >= box(outputsInput).bottom - 1,
    horizontalOverlap: box(outputsInput).right > box(outputsButton).left + 1,
    verticalOverlap: !(box(outputsInput).bottom <= box(outputsButton).top + 1
      || box(outputsButton).bottom <= box(outputsInput).top + 1),
    sameLine: Math.abs(box(outputsButton).top - box(outputsInput).top) < 24,
  };
  const outputsField = outputsRow.parentNode;
  out.outputsField = {field: label(outputsField), fieldBox: box(outputsField),
    fieldWidth: getComputedStyle(outputsField).width};
  /* the widest text input in the results pane, for comparison */
  out.outputsInputsAll = Array.prototype.map.call(
    document.querySelectorAll('#outputs-dir, #outputs-load, #results-refresh'),
    function (el) { return label(el) + ' ' + Math.round(el.getBoundingClientRect().width); });

  /* ---- B. what sticks out of the drawer at 380px */
  const drawer = $('drawer');
  const drawerBox = drawer.getBoundingClientRect();
  const offenders = [];
  Array.prototype.slice.call(drawer.querySelectorAll('*')).forEach(function (el) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) { return; }
    const overflowsRight = r.right > drawerBox.right + 1;
    const scrolls = el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).overflowX !== 'visible';
    const tooWide = r.width > drawerBox.width + 1;
    if (overflowsRight || scrolls || tooWide) {
      offenders.push({
        el: label(el),
        box: box(el),
        scrollWidth: el.scrollWidth,
        clientWidth: el.clientWidth,
        overflowX: getComputedStyle(el).overflowX,
        minWidth: getComputedStyle(el).minWidth,
        flex: getComputedStyle(el).flexBasis + ' / ' + getComputedStyle(el).flexShrink,
      });
    }
  });
  out.drawerBox = box(drawer);
  out.drawerClientWidth = drawer.clientWidth;
  out.drawerScrollWidth = drawer.scrollWidth;
  out.drawerOverflowX = getComputedStyle(drawer).overflowX;
  out.offenders = offenders.slice(0, 20);
  out.offenderCount = offenders.length;

  /* ---- C. the same measurement for the path rows themselves */
  out.pathRows = {};
  ['dp-genome', 'dp-blastdb', 'outputs-dir'].forEach(function (id) {
    const input = $(id);
    const row = input.parentNode;
    const button = row.querySelector('.browse-btn');
    out.pathRows[id] = {row: box(row), input: box(input), button: box(button),
      rowStyle: getComputedStyle(row).flexWrap + ' / gap ' + getComputedStyle(row).gap};
  });

  return JSON.stringify(out, null, 2);
})()