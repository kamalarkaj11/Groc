/* Live verification of the Categories mega-dropdown against the real Django
 * header. Uses Edge DevTools Protocol (CDP).
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
  const port = 15433 + Math.floor(Math.random() * 1000);
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), 'edge-live-'));
  const proc = spawn(EDGE, [
    '--headless=new', '--no-first-run', '--ignore-certificate-errors',
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
  let id = 0;
  const pending = new Map();
  const send0 = (method, params = {}) => new Promise((resolve) => {
    const mid = ++id;
    pending.set(mid, resolve);
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
    if (r.result && r.result.exceptionDetails) return 'JSERR:' + (r.result.exceptionDetails.text || '') + ':' + (r.result.exceptionDetails.exception?.description || '');
    return r.result?.result?.value;
  };
  const mouseMove = (x, y) => send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y });
  const mouseClick = async (x, y) => {
    await send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 });
    await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });
  };
  const key = async (k) => {
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key: k, code: k });
    await send('Input.dispatchKeyEvent', { type: 'keyUp', key: k, code: k });
  };

  const state = async () => evalJS(`(function(){
    var li=document.getElementById('catDropdown');
    var trig=document.getElementById('catDropdownTrigger');
    var menu=document.querySelector('.cat-dropdown-menu');
    var account=document.getElementById('accountMenu');
    var notify=document.getElementById('notificationCenter');
    if(!li||!trig||!menu) return {missing:true};
    var mcs=getComputedStyle(menu);
    var tr=trig.getBoundingClientRect(), m=menu.getBoundingClientRect();
    return {
      open: li.classList.contains('menu-open'),
      vis: mcs.visibility, op: mcs.opacity,
      aria: trig.getAttribute('aria-expanded'),
      trigBottom: Math.round(tr.bottom), menuTop: Math.round(m.top),
      menuLeft: Math.round(m.left), menuRight: Math.round(m.right), menuWidth: Math.round(m.width),
      zIndex: mcs.zIndex, pointerEvents: mcs.pointerEvents,
      searchExpanded: !!document.getElementById('siteHeader').classList.contains('search-expanded'),
      accountOpen: !!account && account.classList.contains('open'),
      notifOpen: !!notify && notify.classList.contains('open')
    };
  })()`);
const linkReport = async () => evalJS(`(function(){
    var out={total:0,hrefs:0,dead:0,noPE:0,firstLinkTop:'none',firstLinkIsSelf:false};
    var menu=document.querySelector('.cat-dropdown-menu');
    if(!menu) return out;
    var links=menu.querySelectorAll('a');
    out.total=links.length;
    links.forEach(function(a){
      var href=(a.getAttribute('href')||'').trim();
      if(href && href!=='#') out.hrefs++; else out.dead++;
      if(getComputedStyle(a).pointerEvents==='none') out.noPE++;
    });
    var first=menu.querySelector('.mega-sidebar-link, .cat-dropdown-menu a');
    if(first){
      var r=first.getBoundingClientRect();
      var el=document.elementFromPoint(Math.round(r.left+r.width/2), Math.round(r.top+r.height/2));
      out.firstLinkTop=el ? (el.id||el.className||el.tagName) : 'none';
      out.firstLinkIsSelf = !!first.contains(el);
    }
    return out;
  })()`);
const widths = [1920, 1440, 1366, 1280, 1200, 1150, 1101, 1024, 992, 800, 500, 375];

  for (const w of widths) {
    await send('Emulation.setDeviceMetricsOverride', { width: w, height: 900, deviceScaleFactor: 1, mobile: false });
    await send('Page.navigate', { url });
    // Wait for the fullscreen page loader to clear (as a real user would).
    let loaderGone = false;
    let loaderMs = 0;
    for (let i = 0; i < 40; i++) {
      await delay(250);
      loaderMs = (i + 1) * 250;
      const ready = await evalJS(`(function(){
        if(!document.getElementById('catDropdown')) return 'NOT-READY';
        var l=document.getElementById('grochub-loader');
        if(!l) return 'NO-LOADER';
        var cs=getComputedStyle(l);
        if(cs.display==='none') return 'HIDDEN';
        if(cs.pointerEvents==='none') return 'LEAVING';
        return 'SHOWING'; })()`);
      loaderGone = ready === 'HIDDEN' || ready === 'LEAVING' || ready === 'NO-LOADER';
      if (loaderGone) break;
    }
    console.log('loader-cleared @' + loaderMs + 'ms', loaderGone ? '(auto)' : '(forced)');
    await evalJS(`(function(){ var l=document.getElementById('grochub-loader'); if(l) l.classList.add('grochub-hidden'); })()`);
    await delay(150);
    const s0 = await state();
    console.log('==== width ' + w + ' ====');
    if (s0.missing) { console.log('MISSING dropdown elements'); continue; }
    console.log('closed-state:', JSON.stringify(s0));
    if (s0.vis === 'visible') console.log('  !! dropdown visible while closed (BUG)');

    const navVis = await evalJS(`getComputedStyle(document.getElementById('navWrap')).display`);
    if (navVis === 'flex') {
      const c = JSON.parse(await evalJS(`(function(){ var t=document.getElementById('catDropdownTrigger').getBoundingClientRect(); return JSON.stringify({x:Math.round(t.left+t.width/2),y:Math.round(t.top+t.height/2),b:Math.round(t.bottom)}); })()`));
      await mouseMove(c.x, c.y);
      await delay(400);
      const s1 = await state();
      console.log('hover-> :', s1.open ? 'OPEN' : 'FAIL(closed)', 'vis=' + s1.vis);
      let sweptOk = true;
      for (let i = 1; i <= 8; i++) {
        const y = Math.round(c.b + ((s1.menuTop - c.b) * i) / 8);
        await mouseMove(c.x, y);
        await delay(50);
        const si = await state();
        if (!si.open || si.vis !== 'visible') { sweptOk = false; console.log('  gap sweep y=' + y + ' closed: ' + JSON.stringify(si)); break; }
      }
      console.log('gap-sweep:', sweptOk ? 'PASS' : 'FAIL');
      await mouseMove(Math.round((s1.menuLeft + s1.menuRight) / 2), s1.menuTop + 80);
      await delay(200);
      const s2 = await state();
      console.log('inside-menu:', s2.open && s2.vis === 'visible' ? 'PASS' : 'FAIL');
      await mouseMove(10, 860);
      await delay(800);
      const s3 = await state();
      console.log('leave-close:', !s3.open && s3.vis === 'hidden' ? 'PASS' : 'FAIL');

      await mouseClick(c.x, c.y);
      await delay(400);
      const s4 = await state();
      console.log('click-open:', s4.open ? 'PASS' : 'FAIL');

      await mouseClick(Math.round(w / 2), 880);
      await delay(400);
      const s5 = await state();
      console.log('click-away:', !s5.open ? 'PASS' : 'FAIL');

      await mouseClick(c.x, c.y);
      await delay(300);
      await key('Escape');
      await delay(300);
      const s6 = await state();
      console.log('escape:', !s6.open ? 'PASS' : 'FAIL');
    } else {
      console.log('mobile nav active (navWrap hidden)');
    }
    const lr = await linkReport();
    console.log('links:', JSON.stringify(lr));
    if (lr.total > 0 && lr.dead > 0) console.log('  !! dead links present');
    const ov = await evalJS(`(function(){ var d=document.documentElement; return JSON.stringify({sW:d.scrollWidth,cW:d.clientWidth,over:d.scrollWidth>d.clientWidth}); })()`);
    console.log('h-overflow:', ov);
  }

  proc.kill();
  try { fs.rmSync(userData, { recursive: true, force: true }); } catch (e) {}
}

main().catch((e) => { console.error(e); process.exit(1); });