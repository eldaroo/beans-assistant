// Generates the Bitácora AI PWA app icons (maskable, brand-aligned).
// Pure Node, no deps — draws a cream coffee bean on a coffee-brown field
// and PNG-encodes by hand. Re-run with `node gen-icons.mjs` if the brand changes.
//
// Brand reference (base.html tokens):
//   coffee-500 ≈ oklch(0.50 0.13 55)  → field   #6b4326
//   cream-50   ≈ oklch(0.985 ... 80)  → bean     #f6ecd9
import { deflateSync } from "node:zlib";
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const DIR = dirname(fileURLToPath(import.meta.url));

const FIELD = [0x6b, 0x43, 0x26]; // coffee
const BEAN = [0xf6, 0xec, 0xd9]; // cream
const GROOVE = [0x5a, 0x37, 0x1f]; // darker coffee for the bean's groove

function mix(a, b, t) {
  return [
    Math.round(a[0] + (b[0] - a[0]) * t),
    Math.round(a[1] + (b[1] - a[1]) * t),
    Math.round(a[2] + (b[2] - a[2]) * t),
  ];
}

// CRC32 for PNG chunks.
const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();
function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const typeBuf = Buffer.from(type, "ascii");
  const body = Buffer.concat([typeBuf, data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body), 0);
  return Buffer.concat([len, body, crc]);
}
function encodePNG(size, rgb) {
  // rgb: Uint8Array length size*size*3
  const stride = size * 3;
  const raw = Buffer.alloc((stride + 1) * size);
  for (let y = 0; y < size; y++) {
    raw[y * (stride + 1)] = 0; // filter: none
    rgb.copy
      ? rgb.copy(raw, y * (stride + 1) + 1, y * stride, y * stride + stride)
      : Buffer.from(rgb.subarray(y * stride, y * stride + stride)).copy(raw, y * (stride + 1) + 1);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 2; // color type: truecolor RGB
  ihdr[10] = 0;
  ihdr[11] = 0;
  ihdr[12] = 0;
  const sig = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  return Buffer.concat([
    sig,
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(raw, { level: 9 })),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

function draw(size) {
  const buf = Buffer.alloc(size * size * 3);
  const cx = size / 2;
  const cy = size / 2;
  // Bean geometry: rotated ellipse. Keep within the maskable safe zone (~80%).
  const a = size * 0.30; // half major axis
  const b = size * 0.205; // half minor axis
  const ang = (-28 * Math.PI) / 180;
  const ca = Math.cos(ang);
  const sa = Math.sin(ang);
  const aa = 1.5; // edge softness in px

  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      let col = FIELD;
      const dx = x + 0.5 - cx;
      const dy = y + 0.5 - cy;
      // rotate into bean frame
      const u = dx * ca + dy * sa; // along major axis
      const v = -dx * sa + dy * ca; // along minor axis
      const r = Math.hypot(u / a, v / b); // 1.0 at ellipse edge
      if (r < 1 + aa / a) {
        // anti-aliased bean fill
        const edge = Math.min(1, Math.max(0, (1 + aa / a - r) / ((2 * aa) / a)));
        let beanCol = BEAN;
        // groove: a sine curve down the major axis
        const grooveV = b * 0.34 * Math.sin((Math.PI * u) / a);
        const gd = Math.abs(v - grooveV);
        const gw = size * 0.022;
        if (gd < gw && r < 0.92) {
          const gt = Math.min(1, Math.max(0, (gw - gd) / gw));
          beanCol = mix(BEAN, GROOVE, gt * 0.85);
        }
        col = mix(FIELD, beanCol, edge);
      }
      const i = (y * size + x) * 3;
      buf[i] = col[0];
      buf[i + 1] = col[1];
      buf[i + 2] = col[2];
    }
  }
  return buf;
}

for (const size of [192, 512]) {
  const png = encodePNG(size, draw(size));
  const out = join(DIR, `icon-${size}.png`);
  writeFileSync(out, png);
  console.log(`wrote ${out} (${png.length} bytes)`);
}
