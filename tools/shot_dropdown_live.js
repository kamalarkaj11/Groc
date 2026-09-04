/* Direct verification that the mega-dropdown paints below the header. */
const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const url = process.argv[2] || 'http://127.0.0.1:8000/';
const outDir = path.resolve('.gh_test/sh');
fs.mkdirSync(outDir, { recursive: true });
const delay = (ms) => new Promise((r) => setTimeout(r, ms));
async function getJson(u) { const res = await fetch(u); return res.json(); }

async function main() {
  const port = 19433 + Math.floor(Math.random() * 1000);
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), 'edge-shot2-'));
  const proc = spawn(EDGE, [
    '--headless=new', '--no-first-run', '--ignore-certificate-errors', '--window-size=1440,900',
    '--remote-debugging-port=' + port, '--user-data-dir=' + userData, 'about:blank'
  ], { stdio: 'ignore' });

  let targets = [];
  for (let i = 0; i < 60; i++) {
    try { targets = await getJson(`http://127.0.0.1:${port}/json`); } catch (e) {}
    if (targets.length) break;
    await delay(100);
  }
  if (!targets.length) { console.error('CDP not reachable'); proc.kill(); process.exit(1); }
  const page = targets.find((t) => t.type === 'page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id = 0; const pending = new Map();
  const send0 = (method, params = {}) => new Promise((resolve) => {
    const mid = ++id; pending.set(mid, resolve);
    ws.send(JSON.stringify({ id: mid, method, params }));
  });
  ws.onmessage = (ev) => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } };
  await new Promise((r) => (ws.onopen = r));
  const send = send0;
  const evalJS = async (expr) => {
    const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    if (r.result && r.result.exceptionDetails) return 'JSERR:' + (r.result.exceptionDetails.exception?.description || r.result.exceptionDetails.text);
    return r.result?.result?.value;
  };
  const mouseMove = (x, y) => send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y });
  const shot = async (name) => {
    const f = await send('Page.captureScreenshot', { format: 'png' });
    if (f.result) fs.writeFileSync(path.join(outDir, name), Buffer.from(f.result.data, 'base64'));
    return name;
  };

  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url });
  for (let i = 0; i < 40; i++) {
    await delay(250);
    const st = await evalJS(`(function(){
      if(!document.getElementById('catDropdown')) return 'NOT-READY';
      var l=document.getElementById('grochub-loader');
      if(!l) return 'OK';
      var cs=getComputedStyle(l);
      return (cs.display==='none'||cs.pointerEvents==='none') ? 'OK' : 'WIP';
    })()`);
    if (st === 'OK') { console.log('ready @', (i + 1) * 250, 'ms'); break; }
    if (i === 39) await evalJS(`(function(){ var l=document.getElementById('grochub-loader'); if(l) l.classList.add('grochub-hidden'); })()`);
  }
  await delay(150);

  const c = JSON.parse(await evalJS(`(function(){ var t=document.getElementById('catDropdownTrigger').getBoundingClientRect(); return JSON.stringify({x:Math.round(t.left+t.width/2),y:Math.round(t.top+t.height/2)}); })()`));
  await mouseMove(c.x, c.y);
  await delay(550);

  const info = await evalJS(`JSON.stringify((function(){
    var h=document.getElementById('siteHeader'), m=document.querySelector('.cat-dropdown-menu');
    var hr=h.getBoundingClientRect(), mr=m.getBoundingClientRect();
    return {overflowX:getComputedStyle(h).overflowX, headerBottom:Math.round(hr.bottom), menuTop:Math.round(mr.top), menuBottom:Math.round(mr.bottom), menuLeft:Math.round(mr.left), menuRight:Math.round(mr.right)};
  })())`);
  console.log('FIXED state:', info);
  await shot('2_fixed_menu.png');

  const inj = await evalJS(`(function(){
    var st=document.createElement('style'); st.id='ctlC2';
    st.textContent='#siteHeader{overflow-x:clip !important; overflow-y:visible !important}';
    document.head.appendChild(st);
    return getComputedStyle(document.getElementById('siteHeader')).overflowX;
  })()`);
  await delay(120);
  console.log('after clip inject, computed overflowX =', inj);
  await shot('2_clipped_menu.png');
  console.log('clipped state:', await evalJS(`(function(){ var m=document.querySelector('.cat-dropdown-menu'); return JSON.stringify({vis:getComputedStyle(m).visibility, cls:document.getElementById('catDropdown').className}); })()`));

  await evalJS(`(function(){ var s=document.getElementById('ctlC2'); if(s) s.remove(); })()`);
  await delay(150);
  await shot('2_restored_menu.png');

  await evalJS(`(function(){ var m=document.querySelector('.cat-dropdown-menu'); m.style.visibility='hidden'; })()`);
  await delay(150);
  await shot('2_menu_hidden_control.png');

  proc.kill();
  try { fs.rmSync(userData, { recursive: true, force: true }); } catch (e) {}
}
main().catch((e) => { console.error(e); process.exit(1); });