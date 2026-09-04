const fs = require('fs');
const path = require('path');
const found = [];
function walk(d) {
  let ns;
  try { ns = fs.readdirSync(d); } catch (e) { return; }
  for (const n of ns) {
    if (n === 'node_modules' || n === '.git' || n === '__pycache__') continue;
    const p = path.join(d, n);
    let s;
    try { s = fs.statSync(p); } catch (e) { continue; }
    if (s.isDirectory()) walk(p);
    else if (/header\.html$/i.test(n)) found.push(p);
  }
}
walk(path.resolve('.'));
console.log(found.join('\n') || 'none');