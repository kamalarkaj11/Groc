/* Sample PNG pixels to prove the dropdown renders below the header (fixed CSS)
 * vs is clipped/invisible with the old overflow-x:clip (control).
 * Usage: node tools/png_sample.js <file1> <file2> ...
 */
const fs = require('fs');
const zlib = require('zlib');

function decodePNG(buf) {
  if (buf.readUInt32BE(0) !== 0x89504e47) throw new Error('not a PNG');
  let pos = 8, width = 0, height = 0, bitDepth = 0, colorType = 0, interlace = 0;
  const idat = [];
  while (pos < buf.length) {
    const len = buf.readUInt32BE(pos);
    const type = buf.toString('ascii', pos + 4, pos + 8);
    const data = buf.slice(pos + 8, pos + 8 + len);
    if (type === 'IHDR') {
      width = data.readUInt32BE(0); height = data.readUInt32BE(4);
      bitDepth = data[8]; colorType = data[9]; interlace = data[12];
    } else if (type === 'IDAT') {
      idat.push(data);
    }
    pos += 12 + len;
    if (type === 'IEND') break;
  }
  if (bitDepth !== 8 || interlace !== 0) throw new Error('unsupported PNG depth/interlace: ' + bitDepth + '/' + interlace);
  const channels = colorType === 6 ? 4 : colorType === 2 ? 3 : colorType === 0 ? 1 : -1;
  if (channels < 0) throw new Error('unsupported colorType ' + colorType);
  const raw = zlib.inflateSync(Buffer.concat(idat));
  const stride = width * channels;
  const out = Buffer.alloc(height * stride);
  const paeth = (a, b, c) => {
    const p = a + b - c, pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c);
    return pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
  };
  for (let y = 0; y < height; y++) {
    const ft = raw[y * (stride + 1)];
    const line = out.slice(y * stride);
    const prev = y ? out.slice((y - 1) * stride) : null;
    for (let x = 0; x < stride; x++) {
      const i = y * (stride + 1) + 1 + x;
      const a = x >= channels ? line[x - channels] : 0;
      const b = prev ? prev[x] : 0;
      const c = x >= channels && prev ? prev[x - channels] : 0;
      let v = raw[i];
      if (ft === 1) v = (v + a) & 0xff;
      else if (ft === 2) v = (v + b) & 0xff;
      else if (ft === 3) v = (v + ((a + b) >> 1)) & 0xff;
      else if (ft === 4) v = (v + paeth(a, b, c)) & 0xff;
      line[x] = v;
    }
  }
  return { width, height, channels, data: out };
}

function regionStats(img, x0, y0, x1, y1) {
  let n = 0, r = 0, g = 0, b = 0, lum = 0, lumMin = 255, lumMax = 0;
  for (let y = y0; y <= y1; y++) {
    for (let x = x0; x <= x1; x++) {
      const i = (y * img.width + x) * img.channels;
      const rr = img.data[i], gg = img.data[i + 1], bb = img.data[i + 2];
      r += rr; g += gg; b += bb;
      const l = 0.2126 * rr + 0.7152 * gg + 0.0722 * bb;
      lum += l; n++;
      if (l < lumMin) lumMin = l;
      if (l > lumMax) lumMax = l;
    }
  }
  return { n, avgR: Math.round(r / n), avgG: Math.round(g / n), avgB: Math.round(b / n), avgLum: Math.round(lum / n), lumMin: Math.round(lumMin), lumMax: Math.round(lumMax) };
}

const sampleStats = regionStats;

for (const f of process.argv.slice(2)) {
  try {
    const img = decodePNG(fs.readFileSync(f));
    const res = {
      size: [img.width, img.height],
      menuSidebar: sampleStats(img, 200, 200, 420, 500),
      menuBody: sampleStats(img, 500, 200, 1150, 600),
      pageBelow: sampleStats(img, 20, 800, 1420, 880)
    };
    console.log(f, JSON.stringify(res));
  } catch (e) {
    console.log(f, 'ERR', e.message);
  }
}