(async function () {
  const out = {};
  function $(id) { return document.getElementById(id); }
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function click(el) { el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true})); }
  function label(el) {
    let s = el.tagName.toLowerCase();
    if (el.id) { s += '#' + el.id; }
    if (typeof el.className === 'string' && el.className) { s += '.' + el.className.trim().split(/\s+/).join('.'); }
    return s;
  }
  out.drawerHiddenAtStart = $('drawer').getAttribute('aria-hidden');
  if (out.drawerHiddenAtStart === 'true') { click($('drawer-toggle')); }
  await sleep(3000);
  out.modelsGroupsText = $('models-groups').textContent.slice(0, 80);
  out.modelsGroupChildren = $('models-groups').children.length;
  out.modelsTableCount = document.querySelectorAll('.models-table').length;
  const t = document.querySelector('.models-table');
  if (t) {
    const r = t.getBoundingClientRect();
    out.modelsTable = {width: Math.round(r.width), left: Math.round(r.left),
      right: Math.round(r.right), scrollWidth: t.scrollWidth,
      clientWidth: t.clientWidth, cssWidth: getComputedStyle(t).width,
      minWidth: getComputedStyle(t).minWidth};
  }
  document.documentElement.style.setProperty('--drawer-width', '380px');
  await sleep(800);
  const d = $('drawer');
  out.drawer = {clientWidth: d.clientWidth, scrollWidth: d.scrollWidth,
    boxRight: Math.round(d.getBoundingClientRect().right)};
  out.widest = Array.prototype.slice.call(d.querySelectorAll('*')).map(function (el) {
    const r = el.getBoundingClientRect();
    return {el: label(el), width: Math.round(r.width), right: Math.round(r.right)};
  }).sort(function (a, b) { return b.width - a.width; }).slice(0, 8);
  out.overRight = Array.prototype.slice.call(d.querySelectorAll('*')).filter(function (el) {
    return el.getBoundingClientRect().right > d.getBoundingClientRect().right + 1;
  }).map(label).slice(0, 10);
  return JSON.stringify(out, null, 2);
})()