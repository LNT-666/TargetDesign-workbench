/* Servant probe (supplementary): reports every ".drawer-block .grid" block, not
   just the first one. The Download block holds 2 fields, so auto-fit correctly
   yields 2 columns there; the 5-field Genome / annotation block is where the
   four-column reading has to show up at the default width. The panel is opened
   only when needed and reset with the documented double-click gesture first. */
(function () {
  function $(id) { return document.getElementById(id); }
  function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function grids() {
    return Array.prototype.slice.call(document.querySelectorAll('.drawer-block .grid'))
      .map(function (g, i) {
        return {
          index: i,
          fields: g.querySelectorAll(':scope > .field').length,
          columns: getComputedStyle(g).gridTemplateColumns
        };
      });
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
    $('drawer-resizer').dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));
    await wait(200);
    out.atDefault = {width: width(), grids: grids()};

    drag(11, 0);
    await wait(300);
    out.atMinimum = {width: width(), grids: grids()};

    out.windowErrors = [];
    return JSON.stringify(out, null, 2);
  }
  return run();
})()