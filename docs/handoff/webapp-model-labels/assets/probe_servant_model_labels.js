/* Servant probe for docs/handoff/webapp-model-labels/task.md section 6.
   Runs inside the page through assets/probe_browser_cdp.js (headless Edge +
   CDP) and returns exactly one JSON string. */
(async () => {
  const out = {};
  const errors = [];
  window.addEventListener('error', (ev) => {
    errors.push('error: ' + String((ev && ev.message) || ev));
  });
  window.addEventListener('unhandledrejection', (ev) => {
    errors.push('unhandledrejection: ' + String((ev && ev.reason) || ev));
  });

  const hintOf = (node) => {
    if (!node) { return null; }
    const field = node.closest('.field');
    const hint = field ? field.querySelector('.hint') : null;
    return hint ? hint.textContent : null;
  };
  const groupTitleOf = (node) => {
    const group = node ? node.closest('.group') : null;
    const title = group ? group.querySelector('h4') : null;
    return title ? title.textContent : null;
  };

  const schema = await (await fetch('/api/schema')).json();
  const labels = schema.model_labels || {};
  out.modelLabelCount = Object.keys(labels).length;
  out.modelLabelsSample = {
    cropsr: labels.cropsr || null,
    cfd: labels.cfd || null,
    rules: labels.rules || null,
  };

  const selects = Array.from(document.querySelectorAll('select[multiple]'));
  out.multiSelectCount = selects.length;
  const first = selects[0];
  out.firstSelectFound = !!first;
  out.selectMultipleStillTrue = !!first && first.multiple === true;
  out.sizeAfter = first ? first.size : null;
  out.firstSelectGroupTitle = groupTitleOf(first);
  out.optionValues = first ? Array.from(first.options).map((o) => o.value) : null;
  out.optionLabels = first ? Array.from(first.options).map((o) => o.text) : null;
  out.expectedLabels = (out.optionValues || []).map((value) => labels[value]);
  out.optionLabelsEqualExpectedLabels = !!out.optionLabels &&
    out.optionLabels.length === out.expectedLabels.length &&
    out.optionLabels.every((text, i) => text === out.expectedLabels[i]);
  out.hintBeforePicks = hintOf(first);
  out.hintHasPrimaryLineBeforePicks = !!out.hintBeforePicks &&
    out.hintBeforePicks.indexOf('Primary:') >= 0;

  out.selectDetails = selects.map((sel, index) => {
    const values = Array.from(sel.options).map((o) => o.value);
    const texts = Array.from(sel.options).map((o) => o.text);
    const expected = values.map((value) => labels[value]);
    return {
      index,
      groupTitle: groupTitleOf(sel),
      multiple: sel.multiple === true,
      size: sel.size,
      values,
      texts,
      expected,
      labelsEqualExpected: texts.length === expected.length &&
        texts.every((text, i) => text === expected[i]),
    };
  });

  /* Two picks on the first select[multiple]. The default cas9 preset offers a
     single on-target option, so switch that side's System Preset to custom
     through the real control; its on-target list shows cropsr, rules, ... */
  let picked = first;
  if (picked) {
    const group = picked.closest('.group');
    const presetSelect = group ? group.querySelector('select') : null;
    out.presetSelectFound = !!presetSelect;
    out.presetValueBefore = presetSelect ? presetSelect.value : null;
    out.stateBeforePicks = JSON.stringify({
      on: state.side_on_target_models,
      off: state.side_off_target_models,
    });
    if (presetSelect) {
      presetSelect.value = 'custom';
      presetSelect.dispatchEvent(new Event('change', {bubbles: true}));
    }
    out.presetValueAfter = presetSelect ? presetSelect.value : null;
    picked = document.querySelector('select[multiple]');
    out.optionCountAfterPresetSwitch = picked ? picked.options.length : null;
    picked.options[0].selected = true;
    if (picked.options[1]) {
      picked.options[1].selected = true;
    }
    picked.dispatchEvent(new Event('change', {bubbles: true}));
    const selected = Array.from(picked.selectedOptions);
    out.selectedValuesAfterTwoPicks = selected.map((o) => o.value);
    out.stateAfterTwoPicks = state.side_on_target_models.target;
    out.stateAfterTwoPicksAll = JSON.stringify({
      on: state.side_on_target_models,
      off: state.side_off_target_models,
    });
    out.labelsAfterTwoPicks = Array.from(picked.options).map((o) => o.text);
    out.primaryMarkedInLabels = selected.length >= 2 &&
      selected[0].text.indexOf('[P] ') === 0 &&
      selected[1].text.indexOf('[P] ') !== 0;
    out.hintAfterPicks = hintOf(picked);
    out.hintHasPrimaryLine = !!out.hintAfterPicks &&
      out.hintAfterPicks.indexOf('Primary:') >= 0;
  }

  /* Models panel: description column + url fallback */
  out.loadModelsError = null;
  try {
    await loadModels();
  } catch (err) {
    out.loadModelsError = String(err);
  }
  const api = await (await fetch('/api/models')).json();
  const flat = [];
  (api.groups || []).forEach((group) => {
    (group.models || []).forEach((model) => { flat.push(model); });
  });
  /* The panel renders one table per protein group, so walk every table. */
  const tables = Array.from(document.querySelectorAll('#models-groups table.models-table'));
  out.modelsTableCount = tables.length;
  out.modelsTableExists = tables.length > 0;
  out.modelsApiRowCount = flat.length;
  if (tables.length) {
    out.modelsHeadersPerTable = tables.map((table) => {
      const head = table.querySelector('tr');
      return head ? Array.from(head.querySelectorAll('th')).map((th) => th.textContent) : [];
    });
    out.modelsHeaderCells = out.modelsHeadersPerTable[0];
    out.modelsHeaderHasDescription = out.modelsHeaderCells.indexOf('Description') >= 0;
    out.modelsRows = [];
    tables.forEach((table) => {
      Array.from(table.querySelectorAll('tr')).slice(1).forEach((tr) => {
        const cells = Array.from(tr.querySelectorAll('td')).map((td) => td.textContent);
        const model = flat[out.modelsRows.length] || {};
        const expectedPath = model.path || model.url || '';
        out.modelsRows.push({
          index: out.modelsRows.length,
          key: model.key,
          nameCell: cells[0],
          pathCell: cells[2],
          descriptionCell: cells[3],
          expectedPath,
          expectedDescription: model.description,
          pathMatches: cells[2] === expectedPath,
          descriptionMatches: cells[3] === model.description,
        });
      });
    });
    out.modelsRowCount = out.modelsRows.length;
    out.eachRowDescriptionMatchesRegistry = out.modelsRows.length > 0 &&
      out.modelsRows.every((row) => row.descriptionMatches === true);
    out.eachRowPathMatchesRegistry = out.modelsRows.every((row) => row.pathMatches === true);
    const teepRow = out.modelsRows.filter((row) => row.key === 'teep')[0];
    const teepModel = flat.filter((model) => model.key === 'teep')[0] || {};
    out.teepPathCell = teepRow ? teepRow.pathCell : null;
    out.teepUrl = teepModel.url || '';
    out.teepPathCellMatchesUrl = !!teepRow && teepRow.pathCell === (teepModel.url || '');
  }

  out.windowErrors = errors;
  return JSON.stringify(out);
})()
