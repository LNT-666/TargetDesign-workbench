/* Servant probe for task 1.3 item 4: at the default width the fields flow into
   four columns, and at the 380px minimum the grid falls back to one column.
   The panel is opened only when needed and the width is reset with the
   documented double-click gesture first, so the readings do not depend on
   whatever the previous run left in localStorage. */
(function () {
  function $(id) { return document.getElementById(id); }
  function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function columns() {
    var grids = document.querySelectorAll('.drawer-block .grid');
    if (!grids.length) { return null; }
    return getComputedStyle(grids[0]).gridTemplateColumns;
  }
  function width() { return Math.round($('drawer').getBoundingClientRect().width); }
  function drag(pointerId, targetClientX) {
    var handle = $('drawer-resizer');
    var from = handle.getBoundingClientRect().left + 3;
    handle.dispatchEvent(new PointerEvent('pointerdown',
      {bubbles: true, pointerId: pointerId, clientX: from}));
    handle.dispatchEvent(new PointerEvent('pointermove',
      {bubbles: true, pointerId: pointerId, clientX: targetClientX}));
    handle.dispatchEvent(new PointerEvent('pointerup',
      {bubbles: true, pointerId: pointerId, clientX: targetClientX}));
  }
  async function run() {
    var out = {viewport: {w: window.innerWidth, h: window.innerHeight}};
    if (!$('drawer').classList.contains('open')) { $('drawer-toggle').click(); }
    await wait(400);
    /* Deterministic start: double-clicking the handle restores the default (D5). */
    $('drawer-resizer').dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));
    await wait(200);
    out.atDefault = {width: width(), columns: columns()};

    /* Drag the handle far to the left: the clamp must stop at 380px. */
    drag(1, 0);
    await wait(300);
    out.afterDragToZero = {width: width(), columns: columns()};

    /* Drag far to the right: the clamp must stop at viewport - 48. */
    drag(2, $('drawer-resizer').getBoundingClientRect().left + 4000);
    await wait(300);
    out.afterDragToMax = {width: width(), columns: columns()};

    out.windowErrors = [];
    return JSON.stringify(out, null, 2);
  }
  return run();
})()