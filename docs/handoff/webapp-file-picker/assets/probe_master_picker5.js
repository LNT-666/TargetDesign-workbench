/* Master-side probe 5 (round 1): attribute the Results-pane layout change.
 * Measures the output-directory row as shipped, then the same row with the
 * picker wrapper removed -- which reproduces the pre-round DOM (input and
 * "List files" directly inside .actions) without touching any file.
 */
(async function () {
  const out = {};
  function $(id) { return document.getElementById(id); }
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function box(el) {
    const r = el.getBoundingClientRect();
    return {left: Math.round(r.left), right: Math.round(r.right),
            top: Math.round(r.top), width: Math.round(r.width)};
  }
  function label(el) {
    return el.tagName.toLowerCase() + (el.id ? ('#' + el.id) : '')
      + (el.className && typeof el.className === 'string' ? ('.' + el.className.trim().split(/\s+/).join('.')) : '');
  }
  await sleep(300);
  const input = $('outputs-dir');
  const row = input.parentNode;
  const actions = row.parentNode;
  const browse = row.querySelector('.browse-btn');
  const load = $('outputs-load');

  out.actions = {el: label(actions), box: box(actions)};
  out.asShipped = {
    row: label(row), rowBox: box(row),
    input: box(input), browse: box(browse), load: box(load),
    inputOnOwnLine: Math.abs(box(input).top - box(browse).top) >= 24,
    loadSharesLineWithInput: Math.abs(box(load).top - box(input).top) < 24,
  };

  /* reproduce the pre-round DOM: input and List files back inside .actions */
  actions.insertBefore(input, row);
  row.remove();
  await sleep(250);
  out.preRoundDom = {
    actions: box(actions), input: box(input), load: box(load),
    loadSharesLineWithInput: Math.abs(box(load).top - box(input).top) < 24,
    inputWidthGain: Math.round(box(input).width) - out.asShipped.input.width,
  };
  return JSON.stringify(out, null, 2);
})()