/* Headless measurement + screenshot of the DESKTOP navbar across viewport
 * widths, using Edge DevTools Protocol (CDP).
 * Usage: node tools/measure_desktop.js [harnessFile]
 */
const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const harnessPath = path.resolve(process.argv[2] || '.gh_test/harness_anon.html');
const fileUrl = 'file:///' + harnessPath.replace(/\\/g, '/');
const widths = [1920, 1440, 1280, 1200, 1150, 1101];
const shotDir = path.resolve('.gh_test/sh');
fs.mkdirSync(shotDir, { recursive: true });

const delay = (ms) => new Promise((r) => setTimeout(r, ms));
async function getJson(url) { const res = await fetch(url); return res.json(); }

async function main() {
  const port = 12433 + Math.floor(Math.random() * 1000);
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), 'edge-dsk-'));
  const proc = spawn(EDGE, [
    '--headless=new', '--disable-gpu', '--no-first-run',
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
    if (msg.id && pending.has(msg.id)) {
      pending.get(msg.id)(msg);
      pending.delete(msg.id);
    }
  };
  await new Promise((r) => (ws.onopen = r));
  const send = send0;

  const evalJS = async (expr) => {
    const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    if (r.result && r.result.exceptionDetails) return 'JSERR:' + (r.result.exceptionDetails.text || '');
    return r.result?.result?.value;
  };
  const mouseMove = (x, y) => send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y });
  const mouseClick = (x, y) => send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 }) && send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });

  const measureExpr = `(() => {
    const r = (sel) => {
      const el = document.querySelector(sel);
      if (!el) return null;
      const b = el.getBoundingClientRect();
      return { x: Math.round(b.left), w: Math.round(b.width), r: Math.round(b.right), t: Math.round(b.top), h: Math.round(b.height) };
    };
    const doc = document.documentElement;
    const header = r('.site-header');
    const shell = r('.header-shell');
    const brand = r('.brand-link');
    const navWrap = r('.nav-wrap');
    const nav = r('.primary-nav');
    const search = r('.header-search');
    const searchInput = r('.header-search input');
    const actions = r('.header-actions');
    const cart = r('.desktop-cart');
    const account = r('.account-menu');
    const cat = r('#catDropdown');

    // Collision audit: horizontally-adjacent shell children must not overlap.
    const rects = (el) => { if (!el) return null; const b = el.getBoundingClientRect(); return { l: b.left, r: b.right }; };
    const pairs = [
      [document.querySelector('.brand-link'), document.getElementById('navWrap')],
      [document.querySelector('.primary-nav'), document.querySelector('.header-search')],
      [document.querySelector('.header-search'), document.querySelector('.header-actions')]
    ];
    const collisions = pairs.map(([a, b]) => {
      if (!a || !b) return null;
      const ra = rects(a), rb = rects(b);
      const overlap = Math.min(ra.r, rb.r) - Math.max(ra.l, rb.l);
      return { a: (a.className || a.id).slice(0, 24), b: (b.className || b.id).slice(0, 24), overlap: Math.round(overlap * 10) / 10 };
    }).filter(Boolean);

    // Containment: all key children must fit within the header shell.
    const shellR = shell ? { l: shell.x, r: shell.x + shell.w } : null;
    const inside = (el, name) => {
      if (!el) return null;
      const rr = rects(el);
      if (!shellR) return null;
      return { name, inBounds: rr.l >= shellR.l && rr.r <= shellR.r, left: Math.round(rr.l - shellR.l), right: Math.round(shellR.r - rr.r) };
    };
    const containment = [
      inside(document.querySelector('.brand-link'), 'brand'),
      inside(document.getElementById('navWrap'), 'navWrap'),
      inside(document.querySelector('.primary-nav'), 'nav'),
      inside(document.querySelector('.header-search'), 'search'),
      inside(document.querySelector('.header-actions'), 'actions')
    ].filter(Boolean);

    return JSON.stringify({
      vw: window.innerWidth,
      docClient: doc.clientWidth,
      docScroll: doc.scrollWidth,
      hscroll: doc.scrollWidth > doc.clientWidth,
      navWrapDisplay: getComputedStyle(document.getElementById('navWrap')).display,
      header, shell, brand, nav, navWrap, search, searchInput, actions, cart, account, cat,
      collisions, containment,
      pageHeadOverflow: document.body.scrollWidth > document.body.clientWidth
    });
  })()`;

  for (const w of widths) {
    await send('Emulation.setDeviceMetricsOverride', { width: w, height: 1000, deviceScaleFactor: 1, mobile: false });
    await send('Page.navigate', { url: fileUrl });
    await delay(1100);
    const value = await evalJS(measureExpr);
    let out;
    try { out = JSON.parse(value); } catch (e) { out = { raw: value }; }
    console.log('==== width ' + w + ' ====');
    console.log(JSON.stringify(out));
    const file = await send('Page.captureScreenshot', { format: 'png' });
    if (file.result) {
      fs.writeFileSync(path.join(shotDir, `desktop_${w}.png`), Buffer.from(file.result.data, 'base64'));
    }
  }

  // Functional search-expand / mega-open check at a representative desktop width.
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url: fileUrl });
  await delay(1100);
  const sc = JSON.parse(await evalJS(`(function(){ var b=document.getElementById('globalProductSearch').getBoundingClientRect(); return JSON.stringify({ x: Math.round(b.left+b.width/2), y: Math.round(b.top+b.height/2) }); })()` ) || '{}');
  await mouseClick(sc.x, sc.y);
  await delay(700);
  const f2 = await evalJS(`(function(){ var h=document.getElementById('siteHeader'), n=document.querySelector('.primary-nav'), s=document.querySelector('.header-search'), a=document.querySelector('.header-actions'); var sr=s.getBoundingClientRect(); var ar=a.getBoundingClientRect(); return JSON.stringify({ expanded: h.classList.contains('search-expanded'), navVisible: n.getBoundingClientRect().width>0, searchRight: Math.round(sr.right), actionsLeft: Math.round(ar.left), overlap: sr.right>ar.left+1 }); })()`);
  console.log('==== functional search (1440) ====');
  console.log(f2);

  // Close the expanded search (click outside it) and let the nav restore,fixed
  const shellC = JSON.parse(await evalJS(`(function(){ var b=document.querySelector('.header-shell').getBoundingClientRect(); return JSON.stringify({ x: Math.round(b.left+10), y: Math.round(b.top+20), inside: document.querySelector('.header-search').getBoundingClientRect().left > b.left+10 }); })()` ) || '{}');
  await mouseClick(shellC.x, shellC.y);
  await delay(650);

  const catC = JSON.parse(await evalJS(`(function(){ var t=document.getElementById('catDropdownTrigger').getBoundingClientRect(); return JSON.stringify({ x: Math.round(t.left+t.width/2), y: Math.round(t.top+t.height/2) }); })()` ) || '{}');
  await mouseMove(catC.x, catC.y);
  await delay(450);
  const f4 = await evalJS(`(function(){ var m=document.querySelector('.cat-dropdown-menu'); if(!m)return 'no-menu'; var b=m.getBoundingClientRect(); return JSON.stringify({ visible: getComputedStyle(m).visibility==='visible', left: Math.round(b.left), right: Math.round(b.right), width: Math.round(b.width), within: b.right<=window.innerWidth+1 }); })()`);
  console.log('==== functional mega hover (1440) ====');
  console.log(f4);
  await mouseMove(10, 900);
  await delay(1200);
  const f5 = await evalJS(`(function(){ var m=document.querySelector('.cat-dropdown-menu'); var c=document.getElementById('catDropdown'); return JSON.stringify({ vis: m?getComputedStyle(m).visibility:'no-menu', menuOpen: c?c.classList.contains('menu-open'):null, hover: c?c.matches(':hover'):null }); })()`);
  console.log('mega closed after leave:', f5);

  proc.kill();
  try { fs.rmSync(userData, { recursive: true, force: true }); } catch (e) {}
}

main().catch((e) => { console.error(e); process.exit(1); });