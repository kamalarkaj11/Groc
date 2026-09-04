/* Headed (real compositor) verification of the categories dropdown sweep. */
const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const url = process.argv[2] || 'http://127.0.0.1:8000/';
const logPath = path.resolve('.gh_test/headed_out.txt');
const log = (s) => fs.appendFileSync(logPath, s + '\n');
const delay = (ms) => new Promise((r) => setTimeout(r, ms));
async function getJson(u) { const res = await fetch(u); return res.json(); }

async function main() {
  fs.writeFileSync(logPath, '=== headed test ===\n');
  const port = 17433 + Math.floor(Math.random() * 1000);
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), 'edge-headed-'));
  const proc = spawn(EDGE, [
    '--no-first-run', '--ignore-certificate-errors', '--window-size=1440,900',
    '--remote-debugging-port=' + port, '--user-data-dir=' + userData, 'about:blank'
  ], { stdio: 'ignore' });

  let targets = [];
  for (let i = 0; i < 60; i++) {
    try { targets = await getJson(`http://127.0.0.1:${port}/json`); } catch (e) {}
    if (targets.length) break;
    await delay(100);
  }
  if (!targets.length) { log('CDP not reachable'); proc.kill(); process.exit(1); }
  const page = targets.find((t) => t.type === 'page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id = 0; const pending = new Map();
  const send0 = (method, params = {}) => new Promise((resolve) => {
    const mid = ++id; pending.set(mid, resolve);
    ws.send(JSON.stringify({ id: mid, method, params }));
  });
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
  };
  await new Promise((r) => (ws.onopen = r));
  const send = send0;
const evalJS = async (expr) => {
    const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    if (r.result && r.result.exceptionDetails) return 'JSERR:' + (r.result.exceptionDetails.exception?.description || r.result.exceptionDetails.text);
    return r.result?.result?.value;
  };
  const md = () => send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
  const mouseMove = (x,y) => send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y });
  const mouseClick = async (x,y) => {
    await send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 });
    await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });
  };
  const key = async (k) => {
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key: k, code: k });
    await send('Input.dispatchKeyEvent', { type: 'keyUp', key: k, code: k });
  };

  const state = async () => JSON.parse(await evalJS(`JSON.stringify((function(){
    var li=document.getElementById('catDropdown');
    var trig=document.getElementById('catDropdownTrigger');
    var menu=document.querySelector('.cat-dropdown-menu');
    var m=menu.getBoundingClientRect(), t=trig.getBoundingClientRect();
    return {
      open: li.classList.contains('menu-open'),
      vis: getComputedStyle(menu).visibility,
      trigBottom: Math.round(t.bottom), menuTop: Math.round(m.top),
      top: (document.elementsFromPoint(Math.round(t.left+t.width/2), Math.round((t.bottom+m.top)/2)) || []).map(function(e){return e.id||e.className||e.tagName;}).slice(0,3).join('>')
    };
  })())`) );

await md();
  await send('Page.navigate', { url });

  // ── Poll until the fullscreen page loader is actually gone (up to ~10s). ──
  let loaderGone = false;
  for (let i = 0; i < 40; i++) {
    await delay(250);
    const st = await evalJS(`(function(){ var l=document.getElementById('grochub-loader');
      if(!l) return 'ABSENT';
      var cs=getComputedStyle(l);
      if(cs.display==='none') return 'HIDDEN';
      // leaving = opacity 0 + pointer-events none → no longer intercepts
      if(cs.pointerEvents==='none') return 'LEAVING(noPE)';
      return 'SHOWING('+cs.opacity+','+document.readyState+')'; })()`);
    loaderGone = st === 'HIDDEN' || st === 'LEAVING(noPE)';
    if (loaderGone) { log('loader-gone after ~' + (i*250) + 'ms: ' + st); break; }
  }
  if (!loaderGone) log('WARN: loader still intercepting; forcing hide');
  await evalJS(`(function(){ var l=document.getElementById('grochub-loader'); if(l) l.classList.add('grochub-hidden'); })()`);
  await delay(200);

  await evalJS(`(function(){ window.__liLeaves=0; window.__liEnters=0;
    var li=document.getElementById('catDropdown');
    li.addEventListener('mouseleave', function(){ window.__liLeaves++; });
    li.addEventListener('mouseenter', function(){ window.__liEnters++; });
  })()`);

  const c = JSON.parse(await evalJS(`(function(){ var t=document.getElementById('catDropdownTrigger').getBoundingClientRect(); return JSON.stringify({x:Math.round(t.left+t.width/2),y:Math.round(t.top+t.height/2)}); })()`));
  await mouseMove(c.x, c.y);
  await delay(450);
  let s = await state();
  log('after hover: ' + JSON.stringify(s) + ' ev:' + await evalJS(`window.__liEnters+'/'+window.__liLeaves`));

  let sweepEnd = s.menuTop + 40;
  let ok = true;
  for (let y = s.trigBottom + 1; y <= sweepEnd; y += 2) {
    await mouseMove(c.x, y);
    await delay(40);
    const si = await state();
    if (!si.open) {
      ok = false;
      log('  SWEEP CLOSED at y=' + y + ' ' + JSON.stringify(si) + ' ev:' + await evalJS(`window.__liEnters+'/'+window.__liLeaves`));
      break;
    }
  }
  log('sweep: ' + (ok ? 'PASS' : 'FAIL'));
if (ok) {
    const link = JSON.parse(await evalJS(`(function(){ var a=document.querySelector('.cat-dropdown-menu .mega-sidebar-link'); var r=a.getBoundingClientRect(); return JSON.stringify({x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2),href:a.getAttribute('href')}); })()`));
    await mouseMove(link.x, link.y);
    await delay(200);
    const sA = await state();
    log('over-link open:', sA.open);
    const before = await evalJS('location.href');
    await mouseClick(link.x, link.y);
    await delay(900);
    const after = await evalJS('location.href');
    log('link click nav:', before !== after ? 'NAVIGATED ' + after : 'no-nav', 'href=' + link.href);
  }

  await mouseMove(5, 5);
  await delay(700);
  s = await state();
  log('leave closes:', !s.open ? 'PASS' : 'FAIL', 'ev:', await evalJS(`window.__liEnters+'/'+window.__liLeaves`));

  const c2 = JSON.parse(await evalJS(`(function(){ var t=document.getElementById('catDropdownTrigger').getBoundingClientRect(); return JSON.stringify({x:Math.round(t.left+t.width/2),y:Math.round(t.top+t.height/2)}); })()`));
  await mouseClick(c2.x, c2.y);
  await delay(350);
  s = await state();
  log('click toggle open:', s.open ? 'PASS' : 'FAIL');
  await mouseClick(c2.x, c2.y);
  await delay(350);
  s = await state();
 log('click toggle close:', !s.open ? 'PASS' : 'FAIL');

  await mouseClick(c2.x, c2.y); await delay(300);
  await key('Escape'); await delay(300);
 s = await state();
 log('escape closes:', !s.open ? 'PASS' : 'FAIL');

 proc.kill();
 try { fs.rmSync(userData, { recursive: true, force: true }); } catch (e) {}
}
main().catch((e) => { console.error(e); process.exit(1); });