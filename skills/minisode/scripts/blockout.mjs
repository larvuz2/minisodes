#!/usr/bin/env node
// Gray-box a location from a JSON layout, like a Blender blockout: walls, furniture, actor marks and cameras.
//
//   node blockout.mjs blockout/glasshouse.json -o blockout/glasshouse/ [--size 1080x1920] [--only cu_nora,wide]
//
// Writes, for every camera: <cam>.png (clay with colored mannequins on their marks), <cam>_empty.png (no people,
// for location plates), <cam>_labels.png (names drawn on, for you to read); <cam>_move.mp4 when the camera has a
// "move" (a gray camera-move clip, a last-resort video reference); plan.png (top view: furniture, marks, camera
// frustums, 1 m grid); <name>.glb (opens in Blender); manifest.json. The layout format is in templates/layout.json.
//
// Needs Node 18+, ffmpeg for moves, and playwright (or playwright-core) with Chromium. Three.js is served from
// node_modules/three when installed (npm i three@0.160.0), else loaded from jsDelivr.
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';

const argv = process.argv.slice(2);
const opt = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? argv.splice(i, 2)[1] : d; };
const out = opt('-o', 'blockout');
const only = opt('--only', '');
const layoutFile = argv[0];
if (!layoutFile) { console.error('usage: node blockout.mjs layout.json -o out/ [--size 1080x1920] [--only cam1,cam2]'); process.exit(1); }
const layout = JSON.parse(fs.readFileSync(layoutFile, 'utf8'));
const defSize = (layout.aspect_ratio || '9:16') === '16:9' ? '1920x1080' : '1080x1920';
const [W, H] = opt('--size', layout.size || defSize).split('x').map(Number);
fs.mkdirSync(out, { recursive: true });

function req(name) {
  for (const base of [process.cwd(), path.dirname(new URL(import.meta.url).pathname)]) {
    try { return createRequire(path.join(base, 'x.js'))(name); } catch { /* next */ }
  }
  return null;
}
function threeDir() {
  for (const base of [process.cwd(), path.dirname(new URL(import.meta.url).pathname)]) {
    try { return path.dirname(createRequire(path.join(base, 'x.js')).resolve('three/package.json')); } catch { /* next */ }
  }
  return null;
}
const pw = req('playwright') || req('playwright-core');
if (!pw) { console.error('playwright is not installed (npm i playwright-core)'); process.exit(1); }
const local = threeDir();
const THREE_URL = local ? '/three' : 'https://cdn.jsdelivr.net/npm/three@0.160.0';

const PAGE = `<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;background:#222}</style>
<script type="importmap">{"imports":{"three":"${THREE_URL}/build/three.module.js","three/addons/":"${THREE_URL}/examples/jsm/"}}</script>
</head><body><script type="module">
import * as THREE from 'three';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';
const D = Math.PI / 180;
const CLAY = { obj: 0xbdbdbd, floor: 0x8f8f8f, wall: 0xcfcfcf, dark: 0x6d6d6d };
const ACTOR_COLORS = ['#8b5cf6', '#14b8a6', '#f59e0b', '#ef4444', '#3b82f6', '#84cc16'];
let L, renderer, scene, actorsGroup, labelsList = [];

function mat(c, extra = {}) { return new THREE.MeshStandardMaterial({ color: c, roughness: 0.88, metalness: 0, ...extra }); }
function boxAt(g, w, h, d, x, y, z, m) {
  const b = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m); b.position.set(x, y + h / 2, z);
  b.castShadow = b.receiveShadow = true; g.add(b); return b;
}
function cylAt(g, r, h, x, y, z, m, seg = 32) {
  const c = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, seg), m); c.position.set(x, y + h / 2, z);
  c.castShadow = c.receiveShadow = true; g.add(c); return c;
}

// Furniture presets, built from boxes and cylinders. Local front is +z; "rot" turns around Y in degrees.
const PRESETS = {
  box(o, g, m) { const [w, h, d] = o.size || [1, 1, 1]; boxAt(g, w, h, d, 0, 0, 0, m); },
  cylinder(o, g, m) { const [w, h] = o.size || [1, 1, 1]; cylAt(g, w / 2, h, 0, 0, 0, m); },
  sphere(o, g, m) { const s = (o.size || [1])[0]; const p = new THREE.Mesh(new THREE.SphereGeometry(s / 2, 32, 16), m); p.position.y = s / 2; p.castShadow = true; g.add(p); },
  plane(o, g, m) { const [w, , d] = o.size || [2, 0, 2]; boxAt(g, w, 0.01, d, 0, 0, 0, o.color ? m : mat(0xa8a8a8)); },
  table(o, g, m) { const [w, h, d] = o.size || [1.6, 0.75, 0.9]; boxAt(g, w, 0.05, d, 0, h - 0.05, 0, m);
    for (const sx of [-1, 1]) for (const sz of [-1, 1]) boxAt(g, 0.06, h - 0.05, 0.06, sx * (w / 2 - 0.08), 0, sz * (d / 2 - 0.08), m); },
  round_table(o, g, m) { const [w, h] = o.size || [1.6, 0.75]; if (o.cloth) cylAt(g, w / 2, h, 0, 0, 0, m, 48);
    else { cylAt(g, w / 2, 0.04, 0, h - 0.04, 0, m, 48); cylAt(g, 0.06, h - 0.04, 0, 0, 0, m); cylAt(g, 0.3, 0.03, 0, 0, 0, m); } },
  chair(o, g, m) { const [w, h, d] = o.size || [0.46, 0.9, 0.5]; boxAt(g, w, 0.05, d, 0, 0.44, 0, m);
    boxAt(g, w, h - 0.49, 0.05, 0, 0.49, -d / 2 + 0.025, m);
    for (const sx of [-1, 1]) for (const sz of [-1, 1]) boxAt(g, 0.04, 0.44, 0.04, sx * (w / 2 - 0.03), 0, sz * (d / 2 - 0.03), m); },
  sofa(o, g, m) { const [w, h, d] = o.size || [2.0, 0.85, 0.9]; boxAt(g, w, 0.42, d, 0, 0, 0, m);
    boxAt(g, w, h - 0.42, 0.2, 0, 0.42, -d / 2 + 0.1, m); for (const s of [-1, 1]) boxAt(g, 0.2, 0.2, d, s * (w / 2 - 0.1), 0.42, 0, m); },
  bed(o, g, m) { const [w, h, d] = o.size || [1.6, 0.55, 2.05]; boxAt(g, w, h, d, 0, 0, 0, m); boxAt(g, w, 1.1, 0.08, 0, 0, -d / 2, m); },
  counter(o, g, m) { const [w, h, d] = o.size || [2.0, 0.92, 0.6]; boxAt(g, w, h, d, 0, 0, 0, m); },
  shelf(o, g, m) { const [w, h, d] = o.size || [1.0, 2.0, 0.35]; for (let i = 0; i <= 4; i++) boxAt(g, w, 0.03, d, 0, i * (h - 0.03) / 4, 0, m);
    for (const s of [-1, 1]) boxAt(g, 0.03, h, d, s * (w / 2 - 0.015), 0, 0, m); },
  door(o, g, m) { const [w, h] = o.size || [0.9, 2.1]; boxAt(g, w, h, 0.05, 0, 0, 0, mat(CLAY.dark)); },
  window(o, g, m) { const [w, h] = o.size || [1.4, 1.4]; const sill = o.sill ?? 0.9;
    boxAt(g, w, h, 0.03, 0, sill, 0, new THREE.MeshStandardMaterial({ color: 0xdfe8ee, emissive: 0x6f7c88, roughness: 0.2 })); },
  lamp(o, g, m) { const h = (o.size || [0.4, 1.6])[1]; cylAt(g, 0.02, h, 0, 0, 0, m); cylAt(g, 0.18, 0.25, 0, h - 0.1, 0, new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xbbbbbb })); },
  plant(o, g, m) { const h = (o.size || [0.5, 1.2])[1]; cylAt(g, 0.18, 0.35, 0, 0, 0, m); const s = new THREE.Mesh(new THREE.SphereGeometry(0.35, 16, 12), m); s.position.y = h - 0.3; s.castShadow = true; g.add(s); },
  screen(o, g, m) { const [w, h] = o.size || [1.2, 0.7]; boxAt(g, w, h, 0.04, 0, o.elev ?? 1.0, 0, mat(0x2a2a2a)); },
  column(o, g, m) { const [w, h] = o.size || [0.4, 3]; cylAt(g, w / 2, h, 0, 0, 0, m); },
  stairs(o, g, m) { const [w, h, d] = o.size || [1.0, 1.8, 3.0]; const n = o.steps || 10; for (let i = 0; i < n; i++) boxAt(g, w, h / n * (i + 1), d / n, 0, 0, -d / 2 + d / n * (i + 0.5), m); },
  flowers(o, g, m) { const s = (o.size || [0.35])[0]; cylAt(g, 0.06, 0.25, 0, o.elev ?? 0, 0, m); const f = new THREE.Mesh(new THREE.SphereGeometry(s / 2, 16, 12), mat(0xe6e6e6)); f.position.y = (o.elev ?? 0) + 0.25 + s / 3; g.add(f); },
};

function addStringLights(o) {
  const [a, b] = [new THREE.Vector3(...o.from), new THREE.Vector3(...o.to)];
  const n = o.bulbs || 24, sag = o.sag ?? 0.3; const bulb = new THREE.MeshBasicMaterial({ color: 0xfff6e0 });
  const pts = [];
  for (let i = 0; i <= n; i++) { const t = i / n; const p = a.clone().lerp(b, t); p.y -= sag * 4 * t * (1 - t); pts.push(p);
    const s = new THREE.Mesh(new THREE.SphereGeometry(0.035, 8, 6), bulb); s.position.copy(p); scene.add(s); }
  scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: 0x555555 })));
}

function addRoom(r) {
  const g = new THREE.Group(); const { w, d, h } = r;
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(w, d), mat(CLAY.floor)); floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; g.add(floor);
  const glass = r.glass;
  const wm = glass ? new THREE.MeshStandardMaterial({ color: 0x9fb0c0, transparent: true, opacity: 0.18, roughness: 0.1, depthWrite: false }) : mat(CLAY.wall);
  const walls = r.walls || ['north', 'south', 'east', 'west'];
  const spec = { north: [w, 0, -d / 2, 0], south: [w, 0, d / 2, 0], east: [d, w / 2, 0, 90], west: [d, -w / 2, 0, 90] };
  for (const name of walls) {
    const [len, x, z, rot] = spec[name];
    const wall = new THREE.Mesh(new THREE.BoxGeometry(len, h, 0.1), wm); wall.position.set(x, h / 2, z); wall.rotation.y = rot * D;
    wall.receiveShadow = !glass; wall.castShadow = !glass; g.add(wall);
    if (glass) { // mullions every 1.5 m so the glass reads as a conservatory
      const n = Math.max(2, Math.round(len / 1.5));
      for (let i = 0; i <= n; i++) { const t = -len / 2 + len * i / n; const m = new THREE.Mesh(new THREE.BoxGeometry(0.06, h, 0.12), mat(CLAY.dark));
        const v = new THREE.Vector3(t, h / 2, 0).applyAxisAngle(new THREE.Vector3(0, 1, 0), rot * D); m.position.set(x + v.x, h / 2, z + v.z); m.castShadow = true; g.add(m); }
    }
  }
  if (r.ceiling && !glass) { const c = new THREE.Mesh(new THREE.PlaneGeometry(w, d), mat(CLAY.wall)); c.rotation.x = Math.PI / 2; c.position.y = h; g.add(c); }
  scene.add(g);
}

function mannequin(a, i) {
  const g = new THREE.Group(); const color = new THREE.Color(a.color || ACTOR_COLORS[i % ACTOR_COLORS.length]);
  const m = mat(color, { roughness: 0.6 }); const h = a.height || 1.75; const sit = a.pose === 'sit';
  const torso = sit ? h * 0.36 : h * 0.62, base = sit ? 0.45 : 0;
  const body = new THREE.Mesh(new THREE.CapsuleGeometry(h * 0.11, torso - h * 0.22, 6, 16), m); body.position.y = base + torso / 2 + (sit ? 0.05 : 0); body.castShadow = true; g.add(body);
  if (sit) { const legs = new THREE.Mesh(new THREE.BoxGeometry(h * 0.2, 0.12, 0.45), m); legs.position.set(0, 0.5, 0.2); g.add(legs);
    const shins = new THREE.Mesh(new THREE.BoxGeometry(h * 0.18, 0.45, 0.1), m); shins.position.set(0, 0.22, 0.42); g.add(shins); }
  const headY = base + torso + h * 0.06 + (sit ? 0.05 : 0);
  const head = new THREE.Mesh(new THREE.SphereGeometry(h * 0.065, 24, 16), m); head.position.y = headY; head.castShadow = true; g.add(head);
  const nose = new THREE.Mesh(new THREE.ConeGeometry(h * 0.02, h * 0.06, 12), m); nose.rotation.x = Math.PI / 2; nose.position.set(0, headY, h * 0.075); g.add(nose);
  g.position.set(...a.pos); g.rotation.y = (a.rot || 0) * D; g.userData = { label: a.name || a.id, top: headY + 0.15 };
  return g;
}

window.setup = (layout) => {
  L = layout;
  renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  renderer.setSize(${W}, ${H}, false); renderer.setPixelRatio(1);
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  document.body.appendChild(renderer.domElement);
  scene = new THREE.Scene(); scene.background = new THREE.Color(L.background || '#3b3e44');
  scene.add(new THREE.HemisphereLight(0xffffff, 0x3a3a3a, 1.4));
  const sun = new THREE.DirectionalLight(0xffffff, L.sun?.intensity ?? 2.2);
  const dir = new THREE.Vector3(...(L.sun?.dir || [-0.4, -1, -0.3])).normalize();
  sun.position.copy(dir.clone().multiplyScalar(-20)); sun.castShadow = true; sun.shadow.mapSize.set(2048, 2048);
  const s = Math.max(L.room?.w || 10, L.room?.d || 10); Object.assign(sun.shadow.camera, { left: -s, right: s, top: s, bottom: -s, far: 60 }); scene.add(sun);
  for (const p of L.practicals || []) { const pl = new THREE.PointLight(0xffffff, p.intensity ?? 3, p.range ?? 8); pl.position.set(...p.pos); scene.add(pl); }
  if (L.room) addRoom(L.room);
  for (const o of L.objects || []) {
    if (o.type === 'string_lights') { addStringLights(o); continue; }
    const g = new THREE.Group(); (PRESETS[o.type] || PRESETS.box)(o, g, mat(o.color || CLAY.obj));
    g.position.set(...(o.pos || [0, 0, 0])); g.rotation.y = (o.rot || 0) * D; g.userData = { label: o.label || o.id, top: (o.size?.[1] ?? 1) + 0.1 };
    if (o.label !== false) labelsList.push(g); scene.add(g);
  }
  actorsGroup = new THREE.Group(); (L.actors || []).forEach((a, i) => { const m = mannequin(a, i); actorsGroup.add(m); labelsList.push(m); }); scene.add(actorsGroup);
  return { actors: (L.actors || []).map((a, i) => ({ id: a.id, color: a.color || ACTOR_COLORS[i % ACTOR_COLORS.length] })) };
};

function lensFov(mm, aspect) { // the long edge of the frame spans 36 mm, as on a full-frame sensor turned to the frame
  const half = aspect < 1 ? 18 : 18 / aspect; return 2 * Math.atan(half / mm) / D;
}
function camAt(c, t) {
  const e = c.move?.ease === 'linear' ? t : t * t * (3 - 2 * t);
  const p = new THREE.Vector3(...c.pos), l = new THREE.Vector3(...c.look);
  if (c.move) { p.lerp(new THREE.Vector3(...c.move.pos), e); l.lerp(new THREE.Vector3(...(c.move.look || c.look)), e); }
  const lens = c.move?.lens ? c.lens + (c.move.lens - c.lens) * e : c.lens;
  const cam = new THREE.PerspectiveCamera(lensFov(lens || 35, ${W} / ${H}), ${W} / ${H}, 0.05, 200);
  cam.position.copy(p); cam.lookAt(l); if (c.roll) cam.rotateZ(c.roll * D); return cam;
}
function withLabels(cam, list) {
  const c2 = document.createElement('canvas'); c2.width = ${W}; c2.height = ${H}; const x = c2.getContext('2d');
  x.drawImage(renderer.domElement, 0, 0);
  x.font = 'bold ' + Math.round(${H} / 60) + 'px sans-serif'; x.textAlign = 'center';
  for (const g of list) { const v = g.position.clone(); v.y += g.userData.top || 1; v.project(cam);
    if (v.z > 1 || Math.abs(v.x) > 1.1 || Math.abs(v.y) > 1.1) continue;
    const sx = (v.x + 1) / 2 * ${W}, sy = (1 - v.y) / 2 * ${H}; const t = g.userData.label; if (!t) continue;
    const tw = x.measureText(t).width + 12; x.fillStyle = 'rgba(0,0,0,.65)'; x.fillRect(sx - tw / 2, sy - ${H} / 50, tw, ${H} / 40);
    x.fillStyle = '#fff'; x.fillText(t, sx, sy); }
  return c2.toDataURL('image/png');
}
window.shot = (id, { actors = true, labels = false, t = 0 } = {}) => {
  const c = L.cameras.find(c => c.id === id); actorsGroup.visible = actors; const cam = camAt(c, t);
  renderer.render(scene, cam); return labels ? withLabels(cam, labelsList) : renderer.domElement.toDataURL('image/png');
};
window.plan = () => {
  // top view at its own size (the room's shape, 1600 px wide), north up, 1 m grid
  const r = L.room || { w: 10, d: 10 }; const pad = 1.5; const vw = r.w + pad * 2, vh = r.d + pad * 2;
  const PW = 1600, PH = Math.round(PW * vh / vw);
  renderer.setSize(PW, PH, false);
  const cam = new THREE.OrthographicCamera(-vw / 2, vw / 2, vh / 2, -vh / 2, 0.1, 100); cam.position.set(0, 50, 0); cam.up.set(0, 0, -1); cam.lookAt(0, 0, 0);
  actorsGroup.visible = true; renderer.render(scene, cam);
  const c2 = document.createElement('canvas'); c2.width = PW; c2.height = PH; const x = c2.getContext('2d'); x.drawImage(renderer.domElement, 0, 0);
  renderer.setSize(${W}, ${H}, false);
  const toS = (px, pz) => [(px / vw + 0.5) * PW, (pz / vh + 0.5) * PH]; const u = PW / vw;
  x.strokeStyle = 'rgba(255,255,255,.10)'; x.lineWidth = 1;
  for (let gx = Math.ceil(-vw / 2); gx <= vw / 2; gx++) { const [sx] = toS(gx, 0); x.beginPath(); x.moveTo(sx, 0); x.lineTo(sx, PH); x.stroke(); }
  for (let gz = Math.ceil(-vh / 2); gz <= vh / 2; gz++) { const [, sy] = toS(0, gz); x.beginPath(); x.moveTo(0, sy); x.lineTo(PW, sy); x.stroke(); }
  x.textAlign = 'center';
  for (const c of L.cameras || []) { const [sx, sy] = toS(c.pos[0], c.pos[2]); const ang = Math.atan2(c.look[2] - c.pos[2], c.look[0] - c.pos[0]);
    const vert = ${W} / ${H} < 1; const half = Math.atan(Math.tan(lensFov(c.lens || 35, ${W} / ${H}) * D / 2) * (vert ? ${W} / ${H} : 1));
    const len = u * 1.6;
    x.fillStyle = 'rgba(250,204,21,.18)'; x.strokeStyle = '#facc15'; x.lineWidth = 2; x.beginPath(); x.moveTo(sx, sy);
    x.lineTo(sx + Math.cos(ang - half) * len, sy + Math.sin(ang - half) * len); x.lineTo(sx + Math.cos(ang + half) * len, sy + Math.sin(ang + half) * len); x.closePath(); x.fill(); x.stroke();
    if (c.move) { const [mx, my] = toS(c.move.pos[0], c.move.pos[2]); x.setLineDash([6, 6]); x.beginPath(); x.moveTo(sx, sy); x.lineTo(mx, my); x.stroke(); x.setLineDash([]); }
    x.font = 'bold ' + Math.round(u * 0.2) + 'px sans-serif'; x.fillStyle = '#facc15'; x.fillText(c.id + ' ' + (c.lens || 35), sx - Math.cos(ang) * u * 0.35, sy - Math.sin(ang) * u * 0.35 + 4); }
  x.font = 'bold ' + Math.round(u * 0.24) + 'px sans-serif';
  for (const g of labelsList) { const [sx, sy] = toS(g.position.x, g.position.z); const t = g.userData.label; if (!t) continue;
    const tw = x.measureText(t).width + 10; x.fillStyle = 'rgba(0,0,0,.65)'; x.fillRect(sx - tw / 2, sy - u * 0.42, tw, u * 0.3); x.fillStyle = '#fff'; x.fillText(t, sx, sy - u * 0.2); }
  x.fillStyle = '#fff'; x.fillRect(u * 0.5, PH - u * 0.6, u, 6); x.fillText('1 m', u, PH - u * 0.72); x.fillText('N', u * 0.6, u * 0.6);
  return c2.toDataURL('image/png');
};
window.glb = () => new Promise((ok, ko) => new GLTFExporter().parse(scene, b => {
  const u = new Uint8Array(b); let s = ''; for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000)); ok(btoa(s)); }, ko, { binary: true }));
window.ready = true;
</script></body></html>`;

const server = http.createServer((q, s) => {
  if (q.url === '/' || q.url.startsWith('/index')) { s.writeHead(200, { 'content-type': 'text/html' }); return s.end(PAGE); }
  if (local && q.url.startsWith('/three/')) {
    const f = path.join(local, decodeURIComponent(q.url.slice(7).split('?')[0]));
    if (f.startsWith(local) && fs.existsSync(f)) { s.writeHead(200, { 'content-type': 'text/javascript' }); return s.end(fs.readFileSync(f)); }
  }
  s.writeHead(404); s.end();
}).listen(0);
const port = server.address().port;

const launch = { headless: true, args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] };
let browser;
try { browser = await pw.chromium.launch(launch); } catch (e) {
  const exe = ['/opt/pw-browsers/chromium', '/usr/bin/chromium', '/usr/bin/google-chrome'].find(p => fs.existsSync(p));
  if (!exe) throw e; browser = await pw.chromium.launch({ ...launch, executablePath: exe });
}
const page = await browser.newPage({ viewport: { width: Math.min(W, 1920), height: Math.min(H, 1920) } });
const errors = [];
page.on('pageerror', e => errors.push(String(e)));
page.on('console', m => m.type() === 'error' && errors.push(m.text()));
await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: 'load' });
await page.waitForFunction(() => window.ready === true, null, { timeout: 60000 }).catch(() => {});
if (errors.length) { console.error(errors.slice(0, 3).join('\n')); }
const info = await page.evaluate(l => window.setup(l), layout);
const save = (name, dataUrl) => { const f = path.join(out, name); fs.writeFileSync(f, Buffer.from(dataUrl.split(',')[1], 'base64')); return f; };
const manifest = { layout: path.basename(layoutFile), size: [W, H], actors: info.actors, cameras: {} };

save('plan.png', await page.evaluate(() => window.plan()));
const wanted = only ? only.split(',') : (layout.cameras || []).map(c => c.id);
for (const c of layout.cameras || []) {
  if (!wanted.includes(c.id)) continue;
  const files = {
    actors: save(`${c.id}.png`, await page.evaluate(id => window.shot(id, { actors: true }), c.id)),
    empty: save(`${c.id}_empty.png`, await page.evaluate(id => window.shot(id, { actors: false }), c.id)),
    labels: save(`${c.id}_labels.png`, await page.evaluate(id => window.shot(id, { actors: true, labels: true }), c.id)),
  };
  if (c.move) {
    const fps = 24, n = Math.max(2, Math.round((c.move.seconds || 4) * fps)); const dir = fs.mkdtempSync(path.join(out, '.move-'));
    for (let i = 0; i < n; i++) {
      const d = await page.evaluate(([id, t, a]) => window.shot(id, { t, actors: a }), [c.id, i / (n - 1), c.move.actors !== false]);
      fs.writeFileSync(path.join(dir, String(i).padStart(4, '0') + '.png'), Buffer.from(d.split(',')[1], 'base64'));
    }
    files.move = path.join(out, `${c.id}_move.mp4`);
    execFileSync('ffmpeg', ['-v', 'error', '-y', '-framerate', String(fps), '-i', path.join(dir, '%04d.png'),
      '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p', '-c:v', 'libx264', '-crf', '20', files.move]);
    fs.rmSync(dir, { recursive: true, force: true });
  }
  manifest.cameras[c.id] = Object.fromEntries(Object.entries(files).map(([k, v]) => [k, path.basename(v)]));
  console.log(`${c.id}: ${Object.values(manifest.cameras[c.id]).join(', ')}`);
}
const name = layout.name || path.basename(layoutFile, '.json');
fs.writeFileSync(path.join(out, `${name}.glb`), Buffer.from(await page.evaluate(() => window.glb()), 'base64'));
manifest.glb = `${name}.glb`; manifest.plan = 'plan.png';
fs.writeFileSync(path.join(out, 'manifest.json'), JSON.stringify(manifest, null, 1));
await browser.close(); server.close();
console.log(`plan.png, ${name}.glb, manifest.json in ${out}${errors.length ? `  (${errors.length} page errors)` : ''}`);
