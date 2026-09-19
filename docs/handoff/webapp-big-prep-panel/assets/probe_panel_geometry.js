/* Servant probe for P0-1 / P0-2 (webapp-big-prep-panel).

   Drives the real page over CDP: opens the panel from the top bar, measures the
   geometry, counts the drawer grid children, checks the scrim + the four close
   paths, and reports the layout again after the panel is hidden. */

(function () {
  function $(id) {
    return document.getElementById(id);
  }

  function drawerBlock() {
    var aside = $('drawer');
    if (!aside) {
      return null;
    }
    var blocks = aside.querySelectorAll('.drawer-block');
    return blocks.length ? blocks[0] : null;
  }

  function rect(id) {
    var node = $(id);
    if (!node) {
      return null;
    }
    var box = node.getBoundingClientRect();
    return {
      left: Math.round(box.left),
      right: Math.round(box.right),
      width: Math.round(box.width),
    };
  }

  function cssWidth() {
    return getComputedStyle(document.documentElement)
      .getPropertyValue('--drawer-width').trim();
  }

  function gridInfo(pick) {
    if (!pick) {
      return null;
    }
    return {
      grids: pick.querySelectorAll('.grid').length,
      fields: pick.querySelectorAll('.grid > .field').length,
      bareLabels: pick.querySelectorAll('.grid > label').length,
      bareInputs: pick.querySelectorAll('.grid > input').length,
      bareSelects: pick.querySelectorAll('.grid > select').length,
      inlineChecks: pick.querySelectorAll('label.inline').length,
      firstColumns: pick.querySelector('.grid')
        ? getComputedStyle(pick.querySelector('.grid')).gridTemplateColumns : null,
    };
  }

  function wait(ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, ms);
    });
  }

  try {
    window.localStorage.removeItem('crispr.drawerWidth');
    window.localStorage.removeItem('crispr.drawerOpen');
  } catch (e) { /* storage disabled */ }

  var errors = [];
  window.addEventListener('error', function (e) {
    errors.push('window.error: ' + (e && e.message ? e.message : String(e)));
  });

  async function run() {
    var out = {
      viewport: {w: window.innerWidth, h: window.innerHeight},
      pageLoaded: !!$('drawer-toggle'),
      resizerInsidePanel: !!($('drawer') && $('drawer').querySelector('#drawer-resizer')),
      dpLoadedHintExists: !!$('dp-loaded-hint'),
      scrimExists: !!$('drawer-scrim'),
    };

    var toggle = $('drawer-toggle');
    if (!toggle) {
      out.windowErrors = errors;
      return JSON.stringify(out, null, 2);
    }

    toggle.click();
    await wait(600);
    var aside = $('drawer');
    out.open = {
      drawerClasses: aside.className,
      ariaHidden: aside.getAttribute('aria-hidden'),
      ariaExpanded: toggle.getAttribute('aria-expanded'),
      cssVar: cssWidth(),
      drawerRect: rect('drawer'),
      scrimHidden: $('drawer-scrim') ? $('drawer-scrim').classList.contains('hidden') : null,
      scrimRect: rect('drawer-scrim'),
      resizerRect: rect('drawer-resizer'),
      drawerGrids: gridInfo(drawerBlock()),
    };

    var resizer = $('drawer-resizer');
    if (resizer) {
      resizer.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowLeft', bubbles: true}));
      await wait(120);
      out.afterArrowLeft = rect('drawer');
      var stored = null;
      try {
        stored = window.localStorage.getItem('crispr.drawerWidth');
      } catch (err) {
        stored = 'unavailable';
      }
      out.storedWidth = stored;
      resizer.dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));
      await wait(120);
      out.afterDoubleClick = rect('drawer');
      out.cssVarAfterReset = cssWidth();
    }

    var scrim = $('drawer-scrim');
    if (scrim) {
      scrim.click();
      await wait(600);
      out.afterScrimClick = {
        drawerClasses: aside.className,
        ariaHidden: aside.getAttribute('aria-hidden'),
        scrimHidden: scrim.classList.contains('hidden'),
        drawerRight: rect('drawer') ? rect('drawer').right : null,
      };
    }

    toggle.click();
    await wait(400);
    out.reopened = {
      drawerClasses: aside.className,
      scrimHidden: scrim ? scrim.classList.contains('hidden') : null,
    };

    var close = $('drawer-close');
    if (close) {
      close.click();
      await wait(400);
      out.afterCloseButton = {
        drawerClasses: aside.className,
        ariaHidden: aside.getAttribute('aria-hidden'),
        scrimHidden: scrim ? scrim.classList.contains('hidden') : null,
        drawerRight: rect('drawer') ? rect('drawer').right : null,
      };
    }

    out.windowErrors = errors;
    return JSON.stringify(out, null, 2);
  }

  return run();
})()