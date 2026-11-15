// Saca una captura de cada pestaña de la interfaz real (no de la maqueta: eso es docs/maquetas/).
//
// Por qué existe: la interfaz no tiene rutas —la consola y la pestaña son estado de React—, así que no
// basta con un navegador sin interfaz apuntando a una URL como en `docs/maquetas/capturar.ps1`; hay que
// pulsar cada pestaña. Usa `playwright-core` con el Edge del sistema para no añadir dependencias al repo.
//
// Uso (con backend en :8000 y `npm run dev` en :5173):
//   NODE_PATH=<carpeta con node_modules/playwright-core> node docs/capturas/capturar.cjs [url-base]
const path = require("node:path");
const fs = require("node:fs");
const { chromium } = require("playwright-core");

const BASE = process.argv[2] || "http://localhost:5173/";
const OUT = __dirname;
const SHELLS = [
  { name: "referencia", hash: "" },
  { name: "clasica", hash: "#clasica" },
];
const CONSOLES = {
  crew: ["home", "radiation", "hazards", "routines", "body", "mission", "data", "log", "imaging", "planner", "library"],
  ground: ["received", "history", "trends", "habitat", "framework", "ledger", "library"],
};

async function settle(page, ms = 900) {
  await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => {});
  // Algunos paneles piden sus datos al montarse y muestran «Consultando…» o «Cargando…» mientras tanto.
  await page
    .waitForFunction(() => !/Consultando|Cargando/.test(document.querySelector("main")?.innerText ?? document.body.innerText), null, {
      timeout: 20000,
    })
    .catch(() => {});
  await page.waitForTimeout(ms);
}

(async () => {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  for (const shell of SHELLS) {
    const dir = path.join(OUT, shell.name);
    fs.mkdirSync(dir, { recursive: true });
    const page = await browser.newPage({ viewport: { width: 1672, height: 941 }, deviceScaleFactor: 1 });
    await page.goto(BASE + shell.hash);
    await page.waitForSelector('[data-console="crew"]', { timeout: 30000 });
    await settle(page, 1500);
    let n = 1;
    for (const [consoleKey, tabs] of Object.entries(CONSOLES)) {
      await page.click(`[data-console="${consoleKey}"]`);
      await settle(page);
      for (const key of tabs) {
        const file = path.join(dir, `${String(n).padStart(2, "0")}-${consoleKey}-${key}.png`);
        n++;
        const tab = page.locator(`#${consoleKey}-tab-${key}`);
        if ((await tab.count()) === 0) {
          console.log(`falta: ${shell.name} ${consoleKey}-${key}`);
          continue;
        }
        await tab.click();
        await settle(page);
        await page.screenshot({ path: file });
        console.log(`ok: ${path.relative(OUT, file)}`);
      }
    }
    await page.close();
  }
  await browser.close();
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
