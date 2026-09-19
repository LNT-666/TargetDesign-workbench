/* Servant probe (supplementary to assets/probe_mode_switch.js, which is reused
   verbatim). Same switch, but the headings are scoped to the slot containers so
   that the two <h4>s rendered by renderCommon() inside the static Common Inputs
   block are not counted. Task 8.6's `leftHeads == ["Target TAM"]` was measured
   before the P0-0 fix, when renderPattern() had already wiped that column. */
(function () {
  var errors = [];
  window.addEventListener('error', function (e) {
    errors.push('window.error: ' + (e && e.message ? e.message : String(e)));
  });
  function q(id) { return document.getElementById(id); }
  function heads(id) {
    var n = q(id);
    if (!n) { return null; }
    return Array.prototype.slice.call(n.querySelectorAll('h4'))
      .map(function (h) { return h.textContent.trim(); });
  }
  function directChildren(id) {
    var n = q(id);
    if (!n) { return null; }
    return Array.prototype.slice.call(n.children)
      .map(function (c) { return c.id || c.tagName.toLowerCase(); });
  }
  function snap() {
    return {
      mode: q('designer-mode') ? q('designer-mode').value : null,
      commonColDirectChildren: directChildren('designer-common-col'),
      staticBlockHeads: heads('common-inputs-wrap'),
      leftSlotHeads: heads('designer-left-col'),
      middleSlotHeads: heads('designer-middle-col'),
      rightSlotHeads: heads('designer-right-col'),
      inputMode: (function () {
        var r = document.querySelector('input[name="input-mode"]:checked');
        return r ? r.value : null;
      })()
    };
  }
  var out = {before: snap()};
  var select = q('designer-mode');
  if (select && select.options.length > 1) {
    select.value = select.options[select.options.length - 1].value;
    out.switchedTo = select.value;
    try {
      select.dispatchEvent(new Event('change', {bubbles: true}));
    } catch (err) {
      out.exception = String(err);
    }
  }
  out.after = snap();
  out.windowErrors = errors;
  return JSON.stringify(out, null, 2);
})()