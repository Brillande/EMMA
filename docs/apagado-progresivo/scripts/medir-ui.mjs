// Mide la interfaz de EMMA por situaciones y guarda el resumen y TODAS las muestras de GPU.
//
// Por qué existe: las cifras de la consola del inventario del apagado progresivo
// (docs/apagado-progresivo-inventario.md §F) tienen que poder rehacerse. Arranca el backend con la
// interfaz compilada, un Chrome aparte con perfil limpio (micrófono y cámara FALSOS de Chrome:
// --use-fake-device-for-media-stream), y en cada situación mide durante PHASE_S segundos:
//   * CPU de todos los procesos de ese Chrome: KernelModeTime + UserModeTime de Win32_Process
//     (segundos de CPU) → % de un núcleo.
//   * CPU del backend (proceso y sus hijos), igual.
//   * Tiempo de tareas de la página: métrica TaskDuration del protocolo de depuración de Chrome
//     (Performance.getMetrics). No incluye workers.
//   * GPU dedicada: nvidia-smi cada 0,5 s (W y % de uso). Chrome suele dibujar con la GPU integrada,
//     que nvidia-smi no ve: lo que no aparezca aquí no está medido.
//
// Uso, desde la raíz del repositorio:
//   cd frontend && npx vite build --outDir ../docs/apagado-progresivo/datos/dist --emptyOutDir && cd ..
//   node docs/apagado-progresivo/scripts/medir-ui.mjs
// Salida: docs/apagado-progresivo/datos/ui-<fecha>.json y ui-<fecha>-gpu.csv
import { spawn, execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const BE = join(REPO, "backend");
const OUT = join(REPO, "docs/apagado-progresivo/datos");
const DIST = join(OUT, "dist");
const CHROME = process.env.CHROME ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PROFILE = join(OUT, "perfil-chrome-medida");
const PORT = 9377, URL = "http://127.0.0.1:8012/";
const PHASE_S = Number(process.env.PHASE_S ?? 30);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
rmSync(PROFILE, { recursive: true, force: true }); mkdirSync(PROFILE, { recursive: true });

const backend = spawn(join(BE, ".venv/Scripts/python.exe"), ["-m", "uvicorn", "app.main:app", "--port", "8012"],
  { cwd: BE, env: { ...process.env, EMMA_OFFLINE: "true", EMMA_ASSISTANT_WARMUP: "false", EMMA_FRONTEND_DIST: DIST }, stdio: "ignore" });
for (let i = 0; i < 100; i++) { try { if ((await fetch(URL + "api/indicators")).ok) break; } catch {} await sleep(300); }
const H = { method: "POST", headers: { "X-EMMA-Console": "1" } };
await fetch(URL + "api/simulate", H);
const SUBJ = (await (await fetch(URL + "api/status")).json()).subject;

const cpuOf = (filter) => Number(execFileSync("powershell", ["-NoProfile", "-c",
  `$t=0; Get-CimInstance Win32_Process | ? { ${filter} } | % { $t += $_.KernelModeTime + $_.UserModeTime }; $t`]).toString().trim()) / 1e7;
const chromeCpu = () => cpuOf(`$_.Name -eq 'chrome.exe' -and $_.CommandLine -like '*perfil-chrome-medida*'`);
const backendCpu = () => cpuOf(`$_.ProcessId -eq ${backend.pid} -or $_.ParentProcessId -eq ${backend.pid}`);

const gpu = []; let sampling = true, phaseName = "inicio";
// Vatios de la CPU (RAPL, Energy Meter de Windows) en un proceso aparte: cpu_rapl.py escribe un CSV.
const RAPL_CSV = join(OUT, "_rapl-ui.csv");
const rapl = spawn("python", [join(REPO, "docs/apagado-progresivo/scripts/cpu_rapl.py"), "7200", RAPL_CSV], { stdio: "ignore" });
(async () => { while (sampling) { const o = execFileSync("nvidia-smi", ["--query-gpu=power.draw,utilization.gpu", "--format=csv,noheader,nounits"]).toString(); const [w, u] = o.trim().split(",").map(Number); gpu.push([Date.now(), phaseName, w, u]); await sleep(500); } })();

const chrome = spawn(CHROME, [`--remote-debugging-port=${PORT}`, `--user-data-dir=${PROFILE}`, "--no-first-run", "--no-default-browser-check",
  "--window-size=1672,941", "--window-position=40,40", ...(process.env.CAMARA_REAL ? [] : ["--use-fake-device-for-media-stream"]), "--use-fake-ui-for-media-stream",
  // Una ventana tapada por otras deja de dibujarse: se mide como si estuviera a la vista.
  "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding", "--disable-background-timer-throttling", "about:blank"], { stdio: "ignore" });
let target;
for (let i = 0; i < 50; i++) { try { target = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find((t) => t.type === "page"); if (target) break; } catch {} await sleep(200); }
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r, { once: true }));
let id = 1; const pend = new Map();
ws.addEventListener("message", (e) => { const m = JSON.parse(e.data); if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); } });
// Cada orden a Chrome tiene 30 s: una que no contesta corta la tanda con su nombre, no la cuelga.
const send = (method, params = {}) => new Promise((r, rej) => { const i = id++; pend.set(i, r); ws.send(JSON.stringify({ id: i, method, params }));
  setTimeout(() => { if (pend.has(i)) { pend.delete(i); rej(new Error(`Chrome no contestó a ${method} en 30 s`)); } }, 30000); });
const ev = async (expression) => (await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true })).result?.result?.value;
await send("Performance.enable");
const taskS = async () => Object.fromEntries((await send("Performance.getMetrics")).result.metrics.map((m) => [m.name, m.value])).TaskDuration;

const rows = [];
async function measure(name, note = {}) {
  console.error(new Date().toISOString(), "fase", name);
  await sleep(4000); // que se asiente lo recién abierto
  note = { ...note, estado: await ev(`[...document.querySelectorAll("*")].map(e => e.childElementCount === 0 ? e.textContent.trim() : "").filter(t => /Di «EMMA»|No se ve ninguna cara|Pausa$/.test(t)).slice(0, 3).join(" | ")`) };
  const c0 = chromeCpu(), b0 = backendCpu(), t0 = await taskS(), g0 = Date.now(); phaseName = name;
  await sleep(PHASE_S * 1000);
  phaseName = "entre-fases"; const c1 = chromeCpu(), b1 = backendCpu(), t1 = await taskS(), g1 = Date.now();
  const g = gpu.filter((x) => x[0] >= g0 && x[0] <= g1), avg = (i) => g.reduce((s, x) => s + x[i], 0) / g.length;
  rows.push({ fase: name, s: PHASE_S, t0: g0 / 1000, t1: g1 / 1000, chrome_cpu_pct_nucleo: +(100 * (c1 - c0) / PHASE_S).toFixed(1),
    pagina_tareas_pct: +(100 * (t1 - t0) / PHASE_S).toFixed(1), backend_cpu_pct_nucleo: +(100 * (b1 - b0) / PHASE_S).toFixed(1),
    gpu_w_media: +avg(2).toFixed(1), gpu_uso_pct: Math.round(avg(3)), muestras_gpu: g.length, ...note });
  console.log(JSON.stringify(rows.at(-1)));
}
async function open(section) {
  await send("Page.navigate", { url: URL });
  for (let i = 0; i < 120; i++) { if (await ev(`document.querySelectorAll('[role="tab"][id^="crew-tab-"]').length > 0`)) break; await sleep(500); }
  await ev(`document.getElementById("crew-tab-${section}")?.click(); true`); await sleep(3000);
}
const click = (text) => ev(`(() => { const el = [...document.querySelectorAll("button")].find(e => e.textContent.trim() === ${JSON.stringify(text)}); if (!el) return "no encontrado"; el.scrollIntoView({block:"center"}); el.click(); return "ok"; })()`);
const toggle = (text) => ev(`(() => { const el = [...document.querySelectorAll("button")].find(e => e.textContent.includes(${JSON.stringify(text)})); if (!el) return "no encontrado"; el.click(); return "ok"; })()`);
async function drag(box, name) {
  let on = true;
  const loop = (async () => { let t = 0; await send("Input.dispatchMouseEvent", { type: "mousePressed", x: box.x, y: box.y, button: "left", clickCount: 1 });
    while (on) { t += 0.1; await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: box.x + Math.sin(t) * box.w / 3, y: box.y, button: "left", buttons: 1 }); await sleep(33); }
    await send("Input.dispatchMouseEvent", { type: "mouseReleased", x: box.x, y: box.y, button: "left", clickCount: 1 }); })();
  await measure(name, { arrastre: "30 Hz, sintético" }); on = false; await loop;
}

// Visor 3D de Polaris (NiiVue, dentro de un <iframe> del mismo origen): el arrastre del protocolo de
// depuración no le llega, así que se le mandan eventos de ratón desde su propio documento, sobre el
// lienzo del render 3D (el segundo), a 30 Hz. NiiVue gira con ellos igual que con la mano.
async function polaris() {
  await open("imaging");
  await fetch(URL + `api/volumes/samples/higado-1?subject=${SUBJ}`, H);
  await click("Abdomen: hígado 1"); await sleep(12000);
  const ok = await ev(`(() => { const f = document.querySelector("iframe"); if (!f) return "sin iframe"; f.scrollIntoView({block:"start"}); const c = f.contentDocument.querySelectorAll("canvas"); return c.length + " lienzos"; })()`);
  await measure("visor_polaris_quieto", { visor: ok });
  await ev(`(() => { const d = document.querySelector("iframe").contentDocument, w = d.defaultView, c = d.querySelectorAll("canvas")[1], r = c.getBoundingClientRect();
    const x0 = r.x + r.width / 2, y0 = r.y + r.height / 2, opt = (x, y, b) => ({ bubbles: true, clientX: x, clientY: y, button: 0, buttons: b, view: w });
    c.dispatchEvent(new w.MouseEvent("mousedown", opt(x0, y0, 1))); let t = 0;
    w.__giro = w.setInterval(() => { t += 0.1; c.dispatchEvent(new w.MouseEvent("mousemove", opt(x0 + Math.sin(t) * r.width / 3, y0, 1))); }, 33); return true; })()`);
  await measure("visor_polaris_girando", { arrastre: "eventos de ratón en el lienzo 3D, 30 Hz" });
  await ev(`(() => { const w = document.querySelector("iframe").contentWindow; w.clearInterval(w.__giro); return true; })()`);
}

try {
  if (process.env.SOLO === "polaris") { await polaris(); throw new Error("fin: solo polaris"); }
  if (process.env.SOLO === "cara") {
    // Con CAMARA_REAL=1: la cámara de verdad, con una persona delante.
    await open("home"); await measure("inicio_quieta");
    await toggle("Seguir la cara (demo)");
    await measure("seguir_cara_encendido", { camara: process.env.CAMARA_REAL ? "real, con una persona delante" : "falsa de Chrome, sin cara" });
    await toggle("Seguir la cara (demo)");
    throw new Error("fin: solo cara");
  }
  await measure("chrome_en_blanco");
  await open("home"); await measure("inicio_quieta");
  // Palabra de activación: primer arranque con perfil limpio (sin el modelo en IndexedDB).
  const w0 = Date.now(), wc0 = chromeCpu();
  await toggle("Escuchar «EMMA»");
  for (let i = 0; i < 480; i++) { if (await ev(`document.body.innerText.includes("Di «EMMA»")`)) break; await sleep(250); }
  rows.push({ fase: "vosk_primer_arranque", s_hasta_escuchar: (Date.now() - w0) / 1000, chrome_cpu_s: +(chromeCpu() - wc0).toFixed(1) });
  console.log(JSON.stringify(rows.at(-1)));
  await measure("escuchar_emma_encendido", { microfono: "falso de Chrome" });
  await toggle("Escuchar «EMMA»"); await sleep(3000);
  await toggle("Seguir la cara (demo)");
  await measure("seguir_cara_encendido", { camara: "falsa de Chrome, sin cara" });
  await toggle("Seguir la cara (demo)");
  await open("log");
  const body = await ev(`(() => { const c = [...document.querySelectorAll("canvas")].sort((a,b)=>b.width*b.height-a.width*a.height)[0]; c.scrollIntoView({block:"center"}); const r = c.getBoundingClientRect(); return {x:r.x+r.width/2, y:r.y+r.height/2, w:r.width}; })()`);
  await measure("dolor_cuerpo3d_quieto");
  await drag(body, "dolor_cuerpo3d_girando");
  await open("imaging");
  await fetch(URL + `api/imaging/samples/liver-1?subject=${SUBJ}`, H);
  await click("Hígado 1"); await sleep(5000);
  await measure("ecografia_quieta");
  await click("Reproducir"); await measure("ecografia_cine_10fps"); await click("Pausa");
  await open("home");
  const { result } = await send("Browser.getWindowForTarget");
  await send("Browser.setWindowBounds", { windowId: result.windowId, bounds: { windowState: "minimized" } });
  await measure("inicio_ventana_minimizada");
} finally {
  sampling = false; ws.close(); chrome.kill(); rapl.kill();
  const { readFileSync } = await import("node:fs");
  const raplRows = readFileSync(RAPL_CSV, "utf-8").trim().split(/\r?\n/).slice(1).map((l) => l.split(",").map(Number));
  for (const r of rows) {
    if (r.t0 === undefined) continue;
    const w = raplRows.filter((x) => x[0] >= r.t0 && x[0] <= r.t1);
    if (w.length) { r.cpu_pkg_w_media = +(w.reduce((a, x) => a + x[1], 0) / w.length).toFixed(2); r.cpu_nucleos_w_media = +(w.reduce((a, x) => a + x[2], 0) / w.length).toFixed(2); r.muestras_cpu_w = w.length; }
  }
  execFileSync("taskkill", ["/T", "/F", "/PID", String(backend.pid)]);
  const stamp = new Date().toISOString().slice(0, 16).replace(":", "");
  const gpuName = execFileSync("nvidia-smi", ["--query-gpu=name,driver_version", "--format=csv,noheader"]).toString().trim();
  writeFileSync(join(OUT, `ui-${stamp}.json`), JSON.stringify({ equipo: { fecha: new Date().toISOString(), gpu: gpuName,
    nota: "Portátil de desarrollo. GPU dedicada en W (nvidia-smi); CPU en % de un núcleo y en W (RAPL); pantalla sin medir." }, fases: rows }, null, 1));
  writeFileSync(join(OUT, `ui-${stamp}-gpu.csv`), "t_ms,fase,gpu_w,gpu_uso_pct\n" + gpu.map((x) => x.join(",")).join("\n") + "\n");
  rmSync(PROFILE, { recursive: true, force: true });
  writeFileSync(join(OUT, `ui-${stamp}-cpu-w.csv`), readFileSync(RAPL_CSV, "utf-8")); rmSync(RAPL_CSV, { force: true });
  console.log("guardado en", join(OUT, `ui-${stamp}.json`));
}
