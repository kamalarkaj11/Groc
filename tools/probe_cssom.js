/* Find which CSS rule sets overflow on #siteHeader in the LIVE served page. */
const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const url = process.argv[2] || 'http://127.0.0.1:8000/';
const delay = (ms) => new Promise((r) => setTimeout(r, ms));
async function getJson(u) { const res = await fetch(u); return res.json(); }

async function main() {
  const port = 20433 + Math.floor(Math.random() * 1000);
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), 'edge-cssom-'));
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

  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url });
  for (let i = 0; i < 40; i++) {
    await delay(250);
    const ok = await evalJS(`!!document.getElementById('siteHeader')`);
    if (ok) break;
  }
  const out = await evalJS(`JSON.stringify((function(){
    var h=document.getElementById('siteHeader');
    var res={computedOverflowX:getComputedStyle(h).overflowX, computedOverflow:getComputedStyle(h).overflow, rules:[]};
    for(var i=0;i<document.styleSheets.length;i++){
      var ss=document.styleSheets[i]; var href=ss.href||'inline';
      try{
        for(var j=0;j<ss.cssRules.length;j++){
          var r=ss.cssRules[j];
          if(r.selectorText && /(^|\\s|,)\\s*\\.?site-header([\\s.,:#]|$)/.test(r.selectorText)){
            var dec={}; for(var k=0;k<r.style.length;k++){ var pn=r.style[k]; dec[pn]=r.style.getPropertyValue(pn).trim(); }
            res.rules.push({href:href, sel:r.selectorText, overflowX:dec['overflow-x']||null, overflow:dec['overflow']||null});
          }
        }
      }catch(e){}
    }
    return res;
  })())`);
  console.log(out);
  proc.kill();
  try { fs.rmSync(userData, { recursive: true, force: true }); } catch (e) {}
}
main().catch((e) => { console.error(e); process.exit(1); });