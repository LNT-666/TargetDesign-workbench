(async () => {
  const out = {};
  const errors = [];
  window.addEventListener('error', (e) => errors.push(String(e.message)));

  const schema = await (await fetch('/api/schema')).json();
  const labels = schema.model_labels || {};
  const expectLabel = (k) => (Object.prototype.hasOwnProperty.call(labels, k) ? labels[k] : k);
  const qt = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  const pickSelects = () => qt('.field select[multiple]');

  const sels = pickSelects();
  out.selectCount = sels.length;
  out.initialPlainLabels = sels.every((s) => qt('option', s).every((o) => o.text === expectLabel(o.value)));
  out.initialMultiple = sels.map((s) => s.multiple === true);
  out.initialSize = sels.map((s) => s.size);
  out.initialValues = sels.map((s) => qt('option', s).map((o) => o.value));
  out.initialTexts = sels.map((s) => qt('option', s).map((o) => o.text));
  out.initialSelected = sels.map((s) => Array.from(s.selectedOptions).map((o) => o.value));
  const hint0 = sels[0].closest('.field').querySelector('.hint');
  out.hintInitial = hint0 ? hint0.textContent : null;

  let presetSwitched = false;
  if (qt('option', sels[0]).length < 2) {
    const group = sels[0].closest('.group');
    const preset = group.querySelector('select:not([multiple])');
    preset.value = 'custom';
    preset.dispatchEvent(new Event('change', {bubbles: true}));
    await new Promise((r) => setTimeout(r, 400));
    presetSwitched = preset.value === 'custom';
  }
  out.presetSwitched = presetSwitched;
  const s0 = pickSelects()[0];
  qt('option', s0).forEach((o, i) => { o.selected = i < 2; });
  s0.dispatchEvent(new Event('change', {bubbles: true}));
  const picked = qt('option', s0).filter((o) => o.selected);
  out.pickedKeys = picked.map((o) => o.value);
  out.stateAfterTwoPicks = state.side_on_target_models.target;
  out.primaryPrefixOnFirst = picked.length > 1 ? picked[0].text.indexOf('[P] ') === 0 : null;
  out.primaryPrefixOnSecond = picked.length > 1 ? picked[1].text.indexOf('[P] ') === 0 : null;
  out.unselectedHaveNoPrefix = qt('option', s0).filter((o) => !o.selected).every((o) => o.text.indexOf('[P] ') !== 0);
  out.labelsAfterPicksMatchSchema = picked.every((o) => o.text.replace(/^\[P\] /, '') === expectLabel(o.value));
  const hint1 = s0.closest('.field').querySelector('.hint');
  out.hintAfterPicks = hint1 ? hint1.textContent : null;
  out.hintNamesPrimaryLabel = hint1 && picked.length ? hint1.textContent.indexOf(expectLabel(picked[0].value)) >= 0 : null;

  const s1 = pickSelects()[1];
  qt('option', s1).forEach((o) => { o.selected = false; });
  s1.dispatchEvent(new Event('change', {bubbles: true}));
  out.offTargetAfterDeselectAll = state.side_off_target_models.target;

  await loadModels();
  const tables = qt('#models-groups table.models-table');
  out.modelsTableCount = tables.length;
  out.modelsHeaders = tables.map((t) => qt('th', t).map((th) => th.textContent));
  const apiModels = await (await fetch('/api/models')).json();
  const expected = [];
  (apiModels.groups || []).forEach((g) => (g.models || []).forEach((m) => expected.push({
    key: m.key, name: m.name, path: m.path || m.url || '', description: m.description || '',
  })));
  const domRows = [];
  tables.forEach((t) => qt('tr', t).slice(1).forEach((tr) => {
    const cells = qt('td', tr).map((td) => td.textContent);
    domRows.push({name: cells[0], path: cells[2], description: cells[3], actions: cells[4]});
  }));
  out.domRowCount = domRows.length;
  out.apiRowCount = expected.length;
  out.eachRowPathMatches = expected.length === domRows.length && expected.every((e, i) => domRows[i].path === e.path);
  out.eachRowDescriptionMatches = expected.length === domRows.length && expected.every((e, i) => domRows[i].description === e.description);
  out.rowDescriptionsNonEmpty = domRows.every((r) => r.description && r.description.length > 0);
  const teep = expected.findIndex((e) => e.key === 'teep');
  out.teepPathCell = teep >= 0 ? domRows[teep].path : null;
  out.teepApiPath = teep >= 0 ? expected[teep].path : null;
  out.windowErrors = errors;
  return JSON.stringify(out, null, 1);
})()