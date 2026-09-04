const fs = require('fs');
const path = require('path');
const roots = ['templates', 'static', 'staticfiles'];
const out = [];
const rx = /overflow-x\s*:\s*clip|\.site-header\s*\{/gi;
function walk(d) {
  for (const n of fs.readdirSync(d)) {
    const p = path.join(d, n);
    const s = fs.statSync(p);
    if (s.isDirectory()) { walk(p); continue; }
    if (!/\.(html|css)$/i.test(n)) continue;
    const t = fs.readFileSync(p, 'utf8');
    let m;
    const lines = t.split('\n');
    while ((m = rx.exec(t))) {
      const ln = t.substring(0, m.index).split('\n').length;
      out.push(p + ':' + ln + ': ' + lines[ln - 1].trim());
    }
  }
}
roots.forEach(r => { if (fs.existsSync(r)) walk(r); });
console.log(out.join('\n') || 'NO overflow-x:clip or .site-header selector found outside header.html');