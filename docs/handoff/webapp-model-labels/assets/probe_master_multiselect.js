(async () => {
  const out = {};
  out.multiSelectCount = document.querySelectorAll('select[multiple]').length;
  const sel = document.querySelector('select[multiple]');
  out.firstSelectFound = !!sel;
  if (sel) {
    out.multiple = sel.multiple === true;
    out.size = sel.size;
    out.optionLabels = Array.from(sel.options).map(o => o.text);
    out.optionValues = Array.from(sel.options).map(o => o.value);
    out.labelsEqualValues = out.optionLabels.every((t, i) => t === out.optionValues[i]);
    out.stateBefore = JSON.stringify(state.side_on_target_models);
    sel.options[0].selected = true;
    if (sel.options[1]) { sel.options[1].selected = true; }
    sel.dispatchEvent(new Event('change', {bubbles: true}));
    out.selectedOptionsAfter = Array.from(sel.selectedOptions).map(o => o.value);
    out.stateAfter = JSON.stringify(state.side_on_target_models);
    const field = sel.closest('.field');
    out.hintText = field && field.querySelector('.hint') ? field.querySelector('.hint').textContent : '';
  }
  try { await loadModels(); } catch (err) { out.loadModelsError = String(err); }
  const table = document.querySelector('#models-groups table.models-table');
  out.modelsTableExists = !!table;
  if (table) {
    const rows = table.querySelectorAll('tr');
    out.modelsHeaderCells = Array.from(rows[0].querySelectorAll('th')).map(th => th.textContent);
    out.modelsFirstRowCells = rows[1] ? Array.from(rows[1].querySelectorAll('td')).map(td => td.textContent) : null;
  }
  return JSON.stringify(out);
})()