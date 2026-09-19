/* Master-side focused probe 3 (round 1): the two things probe 1/2 could not settle.
 *  - the BED input mode renders bed_regions with a kind=bed browse button
 *  - the narrow-drawer layout the task called out as a known trap: at the 380px
 *    minimum, every path input keeps a usable width and never overlaps its button
 *  - which text inputs the new `.row > input[type=text]` rule now touches
 */
(async function () {
  const out = {};
  const errors = [];
  window.addEventListener('error', function (e) { errors.push(String(e.message || e)); });

  function $(id) { return document.getElementById(id); }
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function fire(el, type, init) {
    el.dispatchEvent(new MouseEvent(type, Object.assign({bubbles: true, cancelable: true}, init || {})));
  }
  function click(el) { fire(el, 'click'); }
  function browseButton(id) {
    const input = $(id);
    if (!input || !input.parentNode || !input.parentNode.querySelector) { return null; }
    return input.parentNode.querySelector('.browse-btn');
  }
  function describe(id) {
    const input = $(id);
    if (!input) { return null; }
    const button = browseButton(id);
    const box = input.getBoundingClientRect();
    const bout = button ? button.getBoundingClientRect() : null;
    return {
      inputWidth: Math.round(box.width),
      buttonWidth: bout ? Math.round(bout.width) : null,
      sameLine: bout ? Math.abs(bout.top - box.top) < 24 : null,
      overlaps: bout ? box.right > bout.left + 1 : null,
      kind: button ? button.getAttribute('data-kind') : null,
      type: button ? button.getAttribute('type') : null,
    };
  }

  /* ---- 1. BED input mode */
  const radios = Array.prototype.slice.call(
    document.querySelectorAll('#designer-common-fields input[name="input-mode"]'));
  out.inputModeRadios = radios.map(function (r) { return r.value; });
  const bedRadio = radios.filter(function (r) { return r.value === 'bed'; })[0];
  if (bedRadio) {
    bedRadio.checked = true;
    bedRadio.dispatchEvent(new Event('change', {bubbles: true}));
  }
  await sleep(700);
  out.bedMode_fieldRendered = !!$('field-bed_regions');
  out.bedMode_button = browseButton('field-bed_regions')
    ? browseButton('field-bed_regions').getAttribute('data-kind') : null;
  out.bedMode_searchFastaRendered = !!$('field-search_fasta');
  const sequenceRadio = radios.filter(function (r) { return r.value === 'sequence'; })[0];
  if (sequenceRadio) {
    sequenceRadio.checked = true;
    sequenceRadio.dispatchEvent(new Event('change', {bubbles: true}));
  }
  await sleep(500);
  out.sequenceMode_bedRegionsRendered = !!$('field-bed_regions');

  /* ---- 2. which text inputs the new flex rule reaches */
  out.textInputsInRows = Array.prototype.map.call(
    document.querySelectorAll('.row > input[type=text]'),
    function (input) { return input.id || input.className || '(anonymous)'; });

  /* ---- 3. narrow drawer geometry */
  if ($('drawer').getAttribute('aria-hidden') === 'true') { click($('drawer-toggle')); }
  await sleep(400);
  document.documentElement.style.setProperty('--drawer-width', '380px');
  await sleep(500);
  out.drawerWidth = Math.round($('drawer').getBoundingClientRect().width);
  out.drawerScrollFits = $('drawer').scrollWidth <= $('drawer').clientWidth + 2;
  const ids = ['dp-download-output', 'dp-genome', 'dp-annotation', 'dp-output',
    'dp-blastdb', 'dp-index-prefix', 'dp-species'];
  out.narrow = {};
  ids.forEach(function (id) { out.narrow[id] = describe(id); });
  const pathIds = ids.slice(0, 6);
  out.narrowAllUsable = pathIds.every(function (id) {
    const info = out.narrow[id];
    return info && info.inputWidth >= 100 && info.sameLine === true && info.overlaps === false;
  });

  /* ---- 4. the designer pane keeps its own width (no layout bleed) */
  out.workspace = {
    drawerWidth: Math.round($('drawer').getBoundingClientRect().width),
    mainWidth: Math.round($('main-area').getBoundingClientRect().width),
  };
  out.outputsDir = describe('outputs-dir');

  out.windowErrors = errors;
  return JSON.stringify(out, null, 2);
})()