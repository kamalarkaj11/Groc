/* Diagnose exactly what intercepts pointer hit-tests between trigger and menu. */
const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const harnessPath = path.resolve('.gh_test/harness_anon.html');
const fileUrl = 'file:///' + harnessPath.replace(/\\/g, '/');
const delay = (ms) => new Promise(r => setTimeout(r, ms));
async function getJson(url) { const res = await fetch(url); return res.json(); }

async function main() {
  const port = 11433 + Math.floor(Math.random() * 1000);
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), 'edge-diag-'));
  const proc = spawn(EDGE, [
    '--headless=new', '--no-first-run',
    '--remote-debugging-port=' + port, '--user-data-dir=' + userData, 'about:blank'
  ], { stdio: 'ignore' });
  let targets = [];
  for (let i = 0; i < 60; i++) {
    try { targets = await getJson(`http://127.0.0.1:${port}/json`); } catch (e) {}
    if (targets.length) break;
    await delay(100);
  }
  const page = targets.find(t => t.type === 'page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id = 0;
  const pending = new Map();
  const send = (method, params = {}) => new Promise(resolve => {
    const mid = ++id;
    pending.set(mid, resolve);
    ws.send(JSON.stringify({ id: mid, method, params }));
  });
  ws.onmessage = ev => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
  };
  await new Promise(r => (ws.onopen = r));
  const evalJS = async (expr) => {
    const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true });
    if (r.result && r.result.exceptionDetails) return 'JSERR:' + JSON.stringify(r.result.exceptionDetails).slice(0, 300);
    return r.result?.result?.value;
  };
  const mouseMove = (x, y) => send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y });
  await send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false });

  const probeExpr = (x, y) => `(function(){
    var li=document.getElementById('catDropdown'), menu=document.querySelector('.cat-dropdown-menu');
    var es=document.elementsFromPoint(${x},${y}).slice(0,4).map(function(e){
      return (e.tagName||'?') + '#' + (e.id||'') + '.' + String(e.className||'').split(' ')[0];
    });
    var af = getComputedStyle(li, '::after');
    return JSON.stringify({
      chain: es,
      liHover: li.matches(':hover'),
      open: li.classList.contains('menu-open'),
      afterVis: af.visibility, afterTop: af.top, afterH: af.height, afterZ: af.zIndex
    });
  })()`;

  const rectsExpr = `JSON.stringify((function(){
    function r(el){ if(!el) return null; var b=el.getBoundingClientRect();
      return {top:Math.round(b.top),bottom:Math.round(b.bottom),left:Math.round(b.left),right:Math.round(b.right),h:Math.round(b.height)}; }
    var li=document.getElementById('catDropdown');
    var menu=document.querySelector('.cat-dropdown-menu');
    var sh=li && li.closest('.header-shell');
    var hd=document.getElementById('siteHeader');
    var tr=document.getElementById('catDropdownTrigger');
    var af=getComputedStyle(li,'::after');
    function pos(el){ return el ? getComputedStyle(el).position : null; }
    return {trigger:r(tr), li:r(li), shell:r(sh), header:r(hd), menu:r(menu),
      liPos:pos(li), shellPos:pos(sh), headerPos:pos(hd),
      afTop:af.top, afHeight:af.height, afWidth:af.width};
  })())`;

  await send('Page.navigate', { url: fileUrl });
  await delay(1400);
  console.log('RECTS closed:', await evalJS(rectsExpr));
  const s0 = JSON.parse(await evalJS(`JSON.stringify((function(){
    var t=document.getElementById('catDropdownTrigger');
    var r=t.getBoundingClientRect();
    return {x:Math.round(r.left+r.width/2), y:Math.round(r.top+r.height/2), b:Math.round(r.bottom)};
  })())`));
  await mouseMove(5, 5); await delay(80);
  await mouseMove(s0.x, s0.y); await delay(500);
  console.log('opened:', await evalJS(`document.getElementById('catDropdown').classList.contains('menu-open')`));
  console.log('RECTS open:', await evalJS(rectsExpr));
  for (const y of [92, 95, 99, 103, 107, 111, 115, 117, 118, 119, 120, 121, 123, 130]) {
    await mouseMove(s0.x, y); await delay(120);
    console.log('REAL y=' + y, await evalJS(probeExpr(s0.x, y)));
  }

  // ---- Control experiments: is hit-testing below the header globally broken? ----
  const chainExpr = (x, y) => `JSON.stringify(document.elementsFromPoint(${x},${y}).slice(0,3).map(function(e){return (e.tagName||'?')+'#'+(e.id||'')+'.'+String(e.className||'').split(' ')[0];}))`;
  console.log('CTRL base y=115 :', await evalJS(chainExpr(s0.x, 115)));
  console.log('CTRL base y=400 :', await evalJS(chainExpr(640, 400)));
  await evalJS(`document.getElementById('siteHeader').style.position='static'`);
  await delay(100);
  console.log('CTRL header static y=115:', await evalJS(chainExpr(s0.x, 115)));
  console.log('CTRL header static y=400:', await evalJS(chainExpr(640, 400)));
  await evalJS(`document.getElementById('siteHeader').style.position=''`);
  await evalJS(`var sh=document.querySelector('.header-shell'); sh.style.overflowX='visible'`);
  await delay(100);
  console.log('CTRL shell ovx visible y=115:', await evalJS(chainExpr(s0.x, 115)));
  await evalJS(`document.getElementById('siteHeader').style.backdropFilter='none'`);
  await delay(100);
  console.log('CTRL no backdrop y=115:', await evalJS(chainExpr(s0.x, 115)));
  proc.kill();
  try { fs.rmSync(userData, { recursive: true, force: true }); } catch (e) {}
}
main().catch(e => { console.error(e); process.exit(1); });
