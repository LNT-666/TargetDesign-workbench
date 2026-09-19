const fs = require('fs');
const CDP_PORT = Number(process.env.CDP_PORT || 9333);
const APP_URL = process.env.APP_URL || 'http://127.0.0.1:8351/';
const WAIT_MS = Number(process.env.WAIT_MS || 9000);
const probePath = process.argv[2];

async function main() {
  const expression = fs.readFileSync(probePath, 'utf8');
  const list = await (await fetch('http://127.0.0.1:' + CDP_PORT + '/json/list')).json();
  const page = list.find((t) => t.type === 'page' && t.url.indexOf('edge://') !== 0)
    || list.find((t) => t.type === 'page');
  if (!page) { throw new Error('no page target'); }
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let nextId = 1;
  const pending = new Map();
  const events = [];
  ws.addEventListener('message', (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const entry = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) { entry.reject(new Error(JSON.stringify(msg.error))); }
      else { entry.resolve(msg.result); }
      return;
    }
    if (msg.method === 'Runtime.exceptionThrown') {
      const d = msg.params && msg.params.exceptionDetails;
      events.push({
        method: msg.method,
        text: (d && d.exception && d.exception.description) || (d && d.text) || '',
        line: d && d.lineNumber,
        url: d && d.url,
      });
    } else if (msg.method === 'Runtime.consoleAPICalled' && msg.params.type === 'error') {
      events.push({method: msg.method, text: JSON.stringify(msg.params.args.map((a) => a.value))});
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
  await send('Page.navigate', {url: APP_URL});
  await new Promise((r) => setTimeout(r, WAIT_MS));
  const before = events.length;
  const res = await send('Runtime.evaluate',
    {expression, returnByValue: true, awaitPromise: true});
  const report = {
    url: APP_URL,
    probe: res.result ? res.result.value : null,
    probeError: res.exceptionDetails ? JSON.stringify(res.exceptionDetails) : null,
    cdpExceptionsDuringLoad: events.slice(0, before).length,
    cdpExceptionsTotal: events.length,
    cdpEvents: events,
  };
  console.log(JSON.stringify(report, null, 2));
  ws.close();
}
main().catch((e) => { console.error('PROBE FAILED: ' + e.message); process.exit(1); });