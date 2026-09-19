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
  function options() {
    var s = q('designer-mode');
    if (!s) { return null; }
    return Array.prototype.slice.call(s.options).map(function (o) { return o.value; });
  }
  function snap() {
    return {
      mode: q('designer-mode') ? q('designer-mode').value : null,
      hasCommonInputsWrap: !!q('common-inputs-wrap'),
      hasCommonFields: !!q('designer-common-fields'),
      hasLoadedHint: !!q('designer-loaded-hint'),
      commonFieldsRendered: q('designer-common-fields')
        ? q('designer-common-fields').querySelectorAll('.field').length : -1,
      leftHeads: heads('designer-common-col'),
      middleHeads: heads('designer-middle-col'),
      rightHeads: heads('designer-right-col'),
      leftHasGenomeInput: !!(q('designer-common-col') && q('designer-common-col').querySelector('input, select'))
    };
  }
  var out = {modes: options(), before: snap()};
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