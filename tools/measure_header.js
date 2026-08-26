/* Headless measurement of the mobile nav drawer across viewport widths.
 * Uses Edge DevTools Protocol (CDP) to set exact device metrics.
 * Usage: node tools/measure_header.js [harnessFile]
 */
const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const harnessPath = path.resolve(process.argv[2] || '.gh_test/harness_anon.html');
const fileUrl = 'file:///' + harnessPath.replace(/\\/g, '/');
const widths = [320, 360, 375, 390, 414, 430, 768, 991, 992, 1200];

async function getJson(url) {
  const res = await fetch(url);
  return res.json();
}
const delay = (ms) => new Promise((r) => setTimeout(r, ms));

async function functionalTest(send) {
  // Evaluated expression returns a structured JSON of assertions.
  const expr = `(async function(){
    var out = {};
    function get(id){ return document.getElementById(id); }
    var drawer = get('mobileNavDrawer');
    var overlay = get('mobileOverlay');
    var toggle = get('menuToggle');
    var catToggle = get('mobileCatToggle');
    var accToggle = get('mobileAccountToggle');
    var accBtn = get('mobileAccountBtn');
    var searchBtn = get('mobileSearchBtn');
    var searchInput = get('mobileSearchInput');
    function wait(ms){ return new Promise(function(r){ setTimeout(r, ms); }); }

    out.pageErrors = window.__ghErr || 'none';

    // Log every document-level click to diagnose outside-click handling.
    window.__clicks = [];
    document.addEventListener('click', function (e) {
      window.__clicks.push({
        t: e.target.id || e.target.tagName,
        inHeader: !!document.getElementById('siteHeader').contains(e.target),
        inDrawer: !!document.getElementById('mobileNavDrawer').contains(e.target),
        inOverlay: !!document.getElementById('mobileOverlay').contains(e.target)
      });
    });

    // Ensure a clean starting state (reset drawer AND any submenu state the
    // measurement inline script may have left behind).
    catToggle.setAttribute('aria-expanded', 'false');
    accToggle.setAttribute('aria-expanded', 'false');
    get('mobileCategoriesList').style.maxHeight = '';
    get('mobileAccountList').style.maxHeight = '';
    catToggle.closest('.mobile-has-submenu').classList.remove('expanded');
    accToggle.closest('.mobile-account-section').classList.remove('expanded');
    if (drawer.classList.contains('open')) {
      overlay.click();
      await wait(330);
    }
    out.startClosed = { drawerOpen: drawer.classList.contains('open'),
      overlayOpen: overlay.classList.contains('open') };

    out.toggleInfo = { found: !!toggle, tag: toggle ? toggle.tagName : null,
      cls: toggle ? toggle.className : null,
      displayed: toggle ? getComputedStyle(toggle).display : null };

    var probeHits = 0;
    toggle.addEventListener('click', function () { probeHits++; });
    toggle.click();
    out.afterToggleSync = { drawerOpen: drawer.classList.contains('open'),
      overlayOpen: overlay.classList.contains('open'),
      bodyOverflow: document.body.style.overflow,
      toggleX: toggle.innerHTML.indexOf('bi-x-lg') > -1,
      menuOpenOnHeader: document.getElementById('siteHeader').classList.contains('menu-open'),
      drawerAria: drawer.getAttribute('aria-hidden'),
      probeHits: probeHits,
      clicksLen: window.__clicks.length };
    await wait(330);
    out.afterToggle = { drawerOpen: drawer.classList.contains('open'),
      overlayOpen: overlay.classList.contains('open'),
      bodyOverflow: document.body.style.overflow,
      toggleX: toggle.innerHTML.indexOf('bi-x-lg') > -1,
      drawerRight: Math.round(drawer.getBoundingClientRect().right),
      drawerWidth: Math.round(drawer.getBoundingClientRect().width),
      vw: window.innerWidth,
      clicks: window.__clicks.slice(-6) };

    catToggle.click();
    out.afterCatSync = { ariaExpanded: catToggle.getAttribute('aria-expanded'),
      catMaxH: getComputedStyle(get('mobileCategoriesList')).maxHeight,
      chevronRotated: catToggle.closest('.mobile-has-submenu').classList.contains('expanded'),
      catCount: get('mobileCategoriesList').children.length };
    await wait(330);
    out.afterCat = { ariaExpanded: catToggle.getAttribute('aria-expanded'),
      catMaxH: getComputedStyle(get('mobileCategoriesList')).maxHeight,
      chevronRotated: catToggle.closest('.mobile-has-submenu').classList.contains('expanded') };

    accToggle.click();
    await wait(330);
    out.afterAcc = { ariaExpanded: accToggle.getAttribute('aria-expanded') };

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    await wait(330);
    out.afterEscape = { drawerOpen: drawer.classList.contains('open'),
      overlayOpen: overlay.classList.contains('open'),
      bodyOverflow: document.body.style.overflow };

    searchBtn.click();
    await wait(330);
    out.afterSearchBtn = { drawerOpen: drawer.classList.contains('open'),
      focusedInput: document.activeElement === searchInput,
      drawerRight: Math.round(drawer.getBoundingClientRect().right),
      vw2: window.innerWidth };

    overlay.click();
    await wait(330);
    out.afterOverlayClick = { drawerOpen: drawer.classList.contains('open') };

    accBtn.click();
    await wait(330);
    out.afterAccountBtn = { drawerOpen: drawer.classList.contains('open'),
      accExpanded: accToggle.getAttribute('aria-expanded') };

    out.pageErrorsEnd = window.__ghErr || 'none';
    return JSON.stringify(out);
  })()`;
  const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
  try {
    console.log(JSON.stringify(JSON.parse(r.result.result.value), null, 1));
  } catch (e) {
    console.log('functional output: ' + (r.result?.result?.value || JSON.stringify(r.result)));
  }
}

async function main() {
  const port = 9333 + Math.floor(Math.random() * 1000);
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), 'edge-gh-'));
  const proc = spawn(EDGE, [
    '--headless', '--disable-gpu', '--no-first-run',
    '--remote-debugging-port=' + port,
    '--user-data-dir=' + userData,
    'about:blank'
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

  for (const w of widths) {
    await send('Emulation.setDeviceMetricsOverride', {
      width: w, height: 900, deviceScaleFactor: 0, mobile: false
    });
    await send('Page.navigate', { url: fileUrl });
    // Wait until the inline measure script has run.
    let text = '';
    for (let i = 0; i < 30; i++) {
      await delay(120);
      const r = await send('Runtime.evaluate', {
        expression: `document.getElementById('results')?.textContent || ''`,
        returnByValue: true
      });
      text = r.result?.result?.value || '';
      if (text) break;
    }
    const lines = text.split('\n').filter(Boolean);
    console.log(`==== width ${w} ====`);
    lines.forEach((l) => console.log(l));
    if (!lines.length) console.log('(no measurements captured)');
  }

  console.log('==== functional (width 390) ====');
  await send('Emulation.setDeviceMetricsOverride', {
    width: 390, height: 900, deviceScaleFactor: 0, mobile: false
  });
  await send('Page.navigate', { url: fileUrl });
  await delay(600);
  await functionalTest(send);

  proc.kill();
  try { fs.rmSync(userData, { recursive: true, force: true }); } catch (e) {}
}

main().catch((e) => { console.error(e); process.exit(1); });
