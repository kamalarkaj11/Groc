/* Probe live page geometry + computed styles of the categories dropdown. */
const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const url = process.argv[2] || 'http://127.0.0.1:8000/';
const delay = (ms) => new Promise((r) => setTimeout(r, ms));
async function getJson(u) { const res = await fetch(u); return res.json(); }

async function main() {
  const port = 16433 + Math.floor(Math.random() * 1000);
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), 'edge-probe-'));
  const proc = spawn(EDGE, ['--headless=new', '--no-first-run', '--ignore-certificate-errors',
    '--remote-debugging-port=' + port, '--user-data-dir=' + userData, 'about:blank'], { stdio: 'ignore' });
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

  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url });
  await delay(1500);

  const probe = await evalJS(`JSON.stringify((function(){
    function cs(el, name){ return el ? getComputedStyle(el)[name] : null; }
    function r(el){ if(!el) return null; var b=el.getBoundingClientRect(); return {l:Math.round(b.left),t:Math.round(b.top),r:Math.round(b.right),b:Math.round(b.bottom),w:Math.round(b.width),h:Math.round(b.height)}; }
    var li=document.getElementById('catDropdown');
    var trig=document.getElementById('catDropdownTrigger');
    var menu=document.querySelector('.cat-dropdown-menu');
    var shell=document.querySelector('.header-shell');
    var header=document.getElementById('siteHeader');
    var navWrap=document.getElementById('navWrap');
    var pNav=document.querySelector('.primary-nav');
    var csm=getComputedStyle(menu);
    var out={
      header:r(header), shell:r(shell), navWrap:r(navWrap), pNav:r(pNav),
      li:r(li), trig:r(trig), menu:r(menu),
      liPos:cs(li,'position'), navWrapPos:cs(navWrap,'position'), pNavPos:cs(pNav,'position'),
      liTransform:cs(li,'transform'), pNavTransform:cs(pNav,'transform'),
      menuPos:csm.position, menuTop:csm.top, menuLeft:csm.left, menuWidth:csm.width,
      menuTransform:csm.transform, menuOverflow:csm.overflow, menuVisibility:csm.visibility,
      menuTransition:csm.transition, menuPointerEvents:csm.pointerEvents,
      shellOverflowX:cs(shell,'overflowX'), headerOverflowX:cs(header,'overflowX'),
      idxLi: cs(li,'zIndex')
    };
    // bridge
    var bs=getComputedStyle(li,'::after');
    out.bridge={display:bs.display, pos:bs.position, top:bs.top, height:bs.height, width:bs.width, z:bs.zIndex, pe:bs.pointerEvents, vis:bs.visibility};
    // Which elements are at the gap midpoint & inside menu (while closed)?
    if(li && trig && menu){
      var tb=trig.getBoundingClientRect(), mb=menu.getBoundingClientRect();
      var gapY=Math.round(tb.bottom + (mb.top-tb.bottom)/2);
      var gapX=Math.round(tb.left+tb.width/2);
      var gapEl=document.elementFromPoint(gapX, gapY);
      out.gapHit = gapEl ? (gapEl.id || gapEl.className || gapEl.tagName) : 'none';
      var menuEl=document.elementFromPoint(Math.round(mb.left+mb.width/2), Math.round(mb.top+30));
      out.menuHitClosed = menuEl ? (menuEl.id || menuEl.className || menuEl.tagName) : 'none';
    }
    return out;
  })())`);
  console.log(JSON.stringify(JSON.parse(probe), null, 1));

  proc.kill();
  try { fs.rmSync(userData, { recursive: true, force: true }); } catch (e) {}
}
main().catch((e) => { console.error(e); process.exit(1); });