/* Servant helper (evidence only): opens the Data prep panel through the real
   toggle button and writes a PNG, because headless `msedge --screenshot` cannot
   click. No product code is touched and no debug switch is added. */
const fs = require('fs');
const CDP_PORT = Number(process.env.CDP_PORT || 9333);
const APP_URL = process.env.APP_URL || 'http://127.0.0.1:8351/';
const OUT = process.argv[2] || 'out\\big_panel_open.png';

async function main() {
  const list = await (await fetch('http://127.0.0.1:' + CDP_PORT + '/json/list')).json();
  const page = list.find((t) => t.type === 'page' && t.url.indexOf('edge://') !== 0)
    || list.find((t) => t.type === 'page');
  if (!page) { throw new Error('no page target'); }
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let nextId = 1;
  const pending = new Map();
  ws.addEventListener('message', (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const entry = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) { entry.reject(new Error(JSON.stringify(msg.error))); }
      else { entry.resolve(msg.result); }
    }
  });
  await new Promise((resolve, reject) => {
    ws.addEventListener('open', resolve);
    ws.addEventListener('error', reject);
  });
  const send = (method, params) => new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, {resolve, reject});
    ws.send(JSON.stringify({id, method, params: params || {}}));
  });
  await send('Runtime.enable');
  await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride',
    {width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false});
  await send('Page.navigate', {url: APP_URL});
  await new Promise((r) => setTimeout(r, 9000));
  const width = await send('Runtime.evaluate', {
    expression: "(function () {"
      + "var d = document.getElementById('drawer');"
      + "if (!d.classList.contains('open')) { document.getElementById('drawer-toggle').click(); }"
      + "document.getElementById('drawer-resizer')"
      + ".dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));"
      + "return Math.round(d.getBoundingClientRect().width); })()",
    returnByValue: true,
  });
  await new Promise((r) => setTimeout(r, 700));
  const shot = await send('Page.captureScreenshot', {format: 'png'});
  fs.writeFileSync(OUT, Buffer.from(shot.data, 'base64'));
  console.log('panel width = ' + (width.result ? width.result.value : '?') + 'px');
  console.log('wrote ' + OUT + ' (' + fs.statSync(OUT).size + ' bytes)');
  ws.close();
}
main().catch((e) => { console.error('SHOT FAILED: ' + e.message); process.exit(1); });