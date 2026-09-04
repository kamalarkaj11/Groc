/* Headless check that clicking the Categories trigger toggles the menu,
 * re-locating the trigger immediately before each click (real user timing).
 */
const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const url = process.argv[2] || 'http://127.0.0.1:8000/';
const delay = (ms) => new Promise((r) => setTimeout(r, ms));
async function getJson(u) { const res = await fetch(u); return res.json(); }

async function main() {
  const port = 21433 + Math.floor(Math.random() * 1000);
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), 'edge-click-'));
  const proc = spawn(EDGE, ['--headless=new', '--no-first-run', '--ignore-certificate-errors',
    '--remote-debugging-port=' + port, '--user-data-dir=' + userData, 'about:blank'], { stdio: 'ignore' });
  let targets = [];
  for (let i = 0; i < 60; i++) { try { targets = await getJson(`http://127.0.0.1:${port}/json`); } catch (e) {} if (targets.length) break; await delay(100); }
  if (!targets.length) { console.error('CDP not reachable'); proc.kill(); process.exit(1); }
  const page = targets.find((t) => t.type === 'page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id = 0; const pending = new Map();
  const send0 = (method, params = {}) => new Promise((resolve) => { const mid = ++id; pending.set(mid, resolve); ws.send(JSON.stringify({ id: mid, method, params })); });
  ws.onmessage = (ev) => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } };
  await new Promise((r) => (ws.onopen = r));
  const send = send0;
  const evalJS = async (expr) => {
    const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    if (r.result && r.result.exceptionDetails) return 'JSERR:' + (r.result.exceptionDetails.exception?.description || r.result.exceptionDetails.text);
    return r.result?.result?.value;
  };
  const click = async (x, y) => {
    await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y });
    await delay(60);
    await send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 });
    await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });
  };
  const trigCenter = async () => JSON.parse(await evalJS(`(function(){ var t=document.getElementById('catDropdownTrigger').getBoundingClientRect(); return JSON.stringify({x:Math.round(t.left+t.width/2),y:Math.round(t.top+t.height/2)}); })()`));
  const openState = async () => evalJS(`JSON.stringify({open:document.getElementById('catDropdown').classList.contains('menu-open'), vis:getComputedStyle(document.querySelector('.cat-dropdown-menu')).visibility, aria:document.getElementById('catDropdownTrigger').getAttribute('aria-expanded')})`);

  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url });
  for (let i = 0; i < 40; i++) {
    await delay(250);
    const st = await evalJS(`(function(){ if(!document.getElementById('catDropdown')) return 'NOT-READY'; var l=document.getElementById('grochub-loader'); if(!l) return 'OK'; var c=getComputedStyle(l); return (c.display==='none'||c.pointerEvents==='none')?'OK':'WIP'; })()`);
    if (st === 'OK') break;
  }
  await delay(200);

  // 1) Click to OPEN
  let c = await trigCenter();
  await click(c.x, c.y);
  await delay(350);
  console.log('click-open:', await openState());

  // 2) Click again to CLOSE
  c = await trigCenter();
  await click(c.x, c.y);
  await delay(350);
  console.log('click-close:', await openState());

  // 3) Click outside closes
  await click(c.x, c.y);
  await delay(300);
  await click(60, 860);
  await delay(350);
  console.log('click-away:', await openState());

  // 4) Escape closes
  c = await trigCenter();
  await click(c.x, c.y);
  await delay(300);
  await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape' });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape' });
  await delay(300);
  console.log('escape:', await openState());

  proc.kill();
  try { fs.rmSync(userData, { recursive: true, force: true }); } catch (e) {}
}
main().catch((e) => { console.error(e); process.exit(1); });