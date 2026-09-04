/* Isolate the JS click/keyboard path by disabling the CSS :hover rule,
 * so we can verify click-to-open, click-to-close, aria, escape, click-away
 * independent of :hover. Re-locates trigger before each interaction.
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
  const port = 22433 + Math.floor(Math.random() * 1000);
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), 'edge-js-'));
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
  const disp = async (type, x, y) => send('Input.dispatchMouseEvent', { type, x, y, button: 'left', clickCount: 1 });
  const trigCenter = async () => JSON.parse(await evalJS(`(function(){ var t=document.getElementById('catDropdownTrigger').getBoundingClientRect(); return JSON.stringify({x:Math.round(t.left+t.width/2),y:Math.round(t.top+t.height/2)}); })()`));
  const st = async () => evalJS(`JSON.stringify({open:document.getElementById('catDropdown').classList.contains('menu-open'), vis:getComputedStyle(document.querySelector('.cat-dropdown-menu')).visibility, aria:document.getElementById('catDropdownTrigger').getAttribute('aria-expanded')})`);

  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url });
  for (let i = 0; i < 40; i++) {
    await delay(250);
    const r = await evalJS(`(function(){ if(!document.getElementById('catDropdown')) return 'NOT-READY'; var l=document.getElementById('grochub-loader'); if(!l) return 'OK'; var c=getComputedStyle(l); return (c.display==='none'||c.pointerEvents==='none')?'OK':'WIP'; })()`);
    if (r === 'OK') break;
  }
  await delay(200);
  // Disable the CSS :hover open so JS click path is isolated.
  await evalJS(`(function(){ var s=document.createElement('style'); s.id='nohover'; s.textContent='.cat-dropdown:hover .cat-dropdown-menu{visibility:hidden !important;} .cat-dropdown:hover::after{visibility:hidden !important;}'; document.head.appendChild(s); })()`);

  const results = [];
  // Click open
  let c = await trigCenter();
  await disp('mousePressed', c.x, c.y); await disp('mouseReleased', c.x, c.y);
  await delay(350);
  results.push('click-open: ' + await st());

  // Click close
  c = await trigCenter();
  await disp('mousePressed', c.x, c.y); await disp('mouseReleased', c.x, c.y);
  await delay(350);
  results.push('click-close: ' + await st());

  // Reopen then click away
  c = await trigCenter();
  await disp('mousePressed', c.x, c.y); await disp('mouseReleased', c.x, c.y);
  await delay(300);
  await disp('mousePressed', 60, 860); await disp('mouseReleased', 60, 860);
  await delay(350);
  results.push('click-away: ' + await st());

  // Reopen then Escape
  c = await trigCenter();
  await disp('mousePressed', c.x, c.y); await disp('mouseReleased', c.x, c.y);
  await delay(300);
  await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape' });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape' });
  await delay(300);
  results.push('escape: ' + await st());

  // Keyboard Enter toggles open
  await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', text: '\r', windowsVirtualKeyCode: 13 });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
  await delay(300);
  results.push('keyboard-enter: ' + await st());

  console.log(results.join('\n'));
  proc.kill();
  try { fs.rmSync(userData, { recursive: true, force: true }); } catch (e) {}
}
main().catch((e) => { console.error(e); process.exit(1); });