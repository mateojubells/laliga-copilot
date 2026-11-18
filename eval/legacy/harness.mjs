// Arnés Node del prototipo antiguo (legacy/index.html) para el banco de pruebas.
// Protocolo: una línea JSON por petición por stdin, una línea JSON por respuesta por stdout.
//   {"cmd":"reset"}                 -> {"ok":true}
//   {"cmd":"analyze","text":"..."}  -> {"entities":[{"kind","name"}], "events":[{"sit","fallback","links":[{"kind","ent","role"}]}]}
// Se ejecutan las funciones reales del prototipo (handleText -> detect, CAT.find, CAT.link); solo se observan
// sus entradas/salidas envolviéndolas. NO se carga situaciones.js (modelo estadístico: no produce eventos con roles).
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import readline from "node:readline";
import { fileURLToPath } from "node:url";

const LEGACY = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "legacy");

// Objeto que acepta cualquier propiedad/llamada (DOM simulado).
function dummy() {
  const target = function () {};
  const p = new Proxy(target, {
    get(_, k) {
      if (k === Symbol.toPrimitive) return () => "";
      if (k === "length") return 0;
      if (k === "then") return undefined;
      if (k === "forEach" || k === "map" || k === "filter") return () => [];
      if (k === "style" || k === "classList" || k === "dataset") return dummy();
      return dummy();
    },
    set() { return true; },
    apply() { return dummy(); },
    construct() { return dummy(); },
  });
  return p;
}

const sandbox = {
  console: { log() {}, warn() {}, error: (...a) => process.stderr.write(a.join(" ") + "\n") },
  performance, Date, Math, JSON, Intl, Map, Set, Array, Object, String, Number, RegExp, Symbol, Error,
  setTimeout: () => 0, setInterval: () => 0, clearTimeout() {}, clearInterval() {},
  requestAnimationFrame: () => 0, cancelAnimationFrame() {},
  document: dummy(), localStorage: dummy(), navigator: { userAgent: "node" },
  window: null,
};
sandbox.window = sandbox;
sandbox.self = sandbox;
vm.createContext(sandbox);

const run = (code, name) => vm.runInContext(code, sandbox, { filename: name });
for (const f of ["data.js", "catalogo.js", "plantillas.js", "estadisticas.js", "comunes.js"]) {
  run(fs.readFileSync(path.join(LEGACY, f), "utf8"), f);
}
const html = fs.readFileSync(path.join(LEGACY, "index.html"), "utf8");
const inline = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
if (inline.length !== 1) throw new Error("se esperaba un único <script> inline, hay " + inline.length);
run(inline[0], "index.html");

// Captura: envolver detect y CAT.link para observar lo que usa handleText en cada frase.
run(`
var __cap = null;
(function () {
  const d0 = detect, l0 = CAT.link;
  detect = function (toks, from, interim) { const r = d0(toks, from, interim); if (__cap) __cap.ents.push(...r.ents); return r; };
  CAT.link = function (toks, ents, hits, ctx) { const r = l0(toks, ents, hits, ctx); if (__cap) __cap.events.push(...r); return r; };
})();
function __reset() { subject = null; subjectT = 0; sitLog = []; lexLast = {}; sitShown = []; cards = []; selectedId = null; }
function __analyze(text) {
  __cap = { ents: [], events: [] };
  handleText("k" + (uid++), text, true);
  const c = __cap; __cap = null;
  const name = (kind, ent) => kind === "player" ? (PL.get(ent) || {}).name || ent : ent;
  const seen = new Set(), entities = [];
  for (const e of c.ents) { const k = e.kind + "|" + e.ent; if (seen.has(k)) continue; seen.add(k); entities.push({ kind: e.kind, name: name(e.kind, e.ent) }); }
  const events = c.events.map(ev => ({ sit: ev.sit, fallback: !!ev.fallback,
    links: ev.links.map(l => ({ kind: l.kind, ent: name(l.kind, l.ent), role: l.role })) }));
  return JSON.stringify({ entities, events });
}
`, "capture");

const rl = readline.createInterface({ input: process.stdin });
rl.on("line", (line) => {
  if (!line.trim()) return;
  let out;
  try {
    const req = JSON.parse(line);
    if (req.cmd === "reset") { run("__reset()", "reset"); out = { ok: true }; }
    else if (req.cmd === "analyze") {
      sandbox.__text = String(req.text ?? "");
      out = JSON.parse(run("__analyze(__text)", "analyze"));
    } else out = { error: "cmd desconocido" };
  } catch (e) { out = { error: String(e && e.stack || e) }; }
  process.stdout.write(JSON.stringify(out) + "\n");
});
