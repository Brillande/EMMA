/**
 * Proceso principal de la aplicacion de escritorio de EMMA.
 *
 * POR QUE ELECTRON Y NO TAURI
 * ---------------------------
 * Chromium fijado dentro de cada version: IEC 62304 pide identificar la version de
 * cada componente de terceros, y un motor de renderizado que el sistema operativo
 * actualiza por su cuenta (WebView2 evergreen, lo que usa Tauri por defecto) cambia
 * por debajo de un sistema clinico sin que nadie lo decida. El razonamiento
 * completo esta en `compliance/hmi-state-of-the-art.md`.
 *
 * QUE HACE
 * --------
 * 1. Busca un puerto libre en 127.0.0.1 y arranca `emma-backend.exe` en el.
 * 2. Espera a que `/api/health` responda y abre la ventana en ese origen: la
 *    interfaz la sirve el propio backend, asi que no se cruzan origenes y el CORS
 *    no se toca.
 * 3. Al cerrar, mata el backend y todo lo que haya lanzado.
 *
 * SEGURIDAD
 * ---------
 * La pagina no necesita nada del sistema: solo habla HTTP con el backend local.
 * Por eso no hay preload ni IPC, y la pagina corre en sandbox sin Node. La
 * navegacion queda restringida al backend local; los enlaces de evidencia (HRP,
 * OSDR) se abren en el navegador del sistema, nunca dentro de la aplicacion.
 */

"use strict";

const { app, BrowserWindow, Menu, dialog, globalShortcut, session, shell } = require("electron");
const { execFile, spawn } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");

const LOOPBACK = "127.0.0.1";
// Lo que tarda en responder el backend congelado es ~1 s; se deja margen para un
// disco lento o un antivirus que inspeccione el ejecutable la primera vez.
const STARTUP_TIMEOUT_MS = 60_000;

/** @type {import("node:child_process").ChildProcess | null} */
let backend = null;
let quitting = false;

/** Rutas del backend y de la interfaz, empaquetadas o en el repositorio. */
function locations() {
  if (app.isPackaged) {
    const resources = process.resourcesPath;
    return {
      command: path.join(resources, "backend", "emma-backend.exe"),
      args: [],
      cwd: path.join(resources, "backend"),
      frontendDist: path.join(resources, "frontend"),
    };
  }
  // Desarrollo: el mismo punto de entrada, con el Python del venv del backend.
  const repo = path.resolve(__dirname, "..");
  return {
    command: path.join(repo, "backend", ".venv", "Scripts", "python.exe"),
    args: [path.join(repo, "backend", "desktop_entry.py")],
    cwd: path.join(repo, "backend"),
    frontendDist: path.join(repo, "frontend", "dist"),
  };
}

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, LOOPBACK, () => {
      const { port } = /** @type {import("node:net").AddressInfo} */ (server.address());
      server.close(() => resolve(port));
    });
  });
}

function healthy(port) {
  return new Promise((resolve) => {
    const request = http.get({ host: LOOPBACK, port, path: "/api/health", timeout: 2_000 }, (res) => {
      res.resume();
      resolve(res.statusCode === 200);
    });
    request.on("error", () => resolve(false));
    request.on("timeout", () => {
      request.destroy();
      resolve(false);
    });
  });
}

async function waitForBackend(port) {
  const deadline = Date.now() + STARTUP_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (backend === null || backend.exitCode !== null) return false;
    if (await healthy(port)) return true;
    await new Promise((r) => setTimeout(r, 250));
  }
  return false;
}

// Tope de `backend.log`. DISEÑO DE EMMA, sin norma detras: el backend arranca en nivel
// `warning` (desktop_entry.py), asi que 5 MB son muchas sesiones de avisos y trazas, y con el
// fichero anterior conservado el registro no ocupa en disco mas de unas dos veces el tope.
const MAX_LOG_BYTES = 5 * 1024 * 1024;

/**
 * Cuando toca rotar: lo escrito mas lo que llega pasaria del tope. Un fichero vacio no se
 * rota (un solo trozo mayor que el tope se escribe entero: rotar no lo haria caber).
 * Funcion pura; es toda la decision de la rotacion.
 */
function shouldRotate(writtenBytes, incomingBytes, limitBytes) {
  return writtenBytes > 0 && writtenBytes + incomingBytes > limitBytes;
}

/**
 * El registro del backend, con tope y un fichero anterior (`backend.log.1`).
 *
 * POR QUE: antes era un flujo en modo anadir, sin tope ni rotacion. Vive en el perfil del
 * usuario y nadie lo borra, asi que guardaba para siempre todo lo que el backend hubiera
 * escrito. El backend ya no escribe contenido personal en el (backend/app/core/log_privacy.py);
 * esto acota ademas cuanto tiempo y cuanto se conserva.
 *
 * Escritura sincrona: son avisos y trazas, pocos y pequenos, y asi no hay que coordinar la
 * rotacion con un flujo a medio vaciar. Un fallo al escribir o al rotar no tumba la aplicacion:
 * el registro es para diagnosticar, no parte de la funcion.
 */
function openLog(logDir, limitBytes = MAX_LOG_BYTES) {
  const current = path.join(logDir, "backend.log");
  const previous = `${current}.1`;
  let fd = null;
  let written = 0;

  const open = () => {
    fd = fs.openSync(current, "a");
    written = fs.fstatSync(fd).size;
  };
  const rotate = () => {
    if (fd !== null) fs.closeSync(fd);
    fd = null;
    // `renameSync` sustituye al anterior si existe: solo se conserva uno.
    fs.renameSync(current, previous);
    open();
  };
  const write = (chunk) => {
    const data = Buffer.isBuffer(chunk) ? chunk : Buffer.from(String(chunk), "utf8");
    try {
      if (fd === null) open();
      if (shouldRotate(written, data.length, limitBytes)) {
        try {
          rotate();
        } catch {
          // No se pudo rotar (el fichero anterior abierto en otro programa, p. ej.): se sigue
          // anadiendo en el actual y se reintenta en la siguiente escritura.
          if (fd === null) open();
        }
      }
      fs.writeSync(fd, data);
      written += data.length;
    } catch {
      // Sin registro se sigue funcionando; la siguiente escritura lo vuelve a intentar.
    }
  };
  return { write };
}

function startBackend(port, extraEnv = {}) {
  const where = locations();
  const userData = app.getPath("userData");
  const logDir = path.join(userData, "logs");
  fs.mkdirSync(logDir, { recursive: true });
  const log = openLog(logDir);
  log.write(`\n--- ${new Date().toISOString()} puerto ${port}\n`);

  backend = spawn(where.command, [...where.args, "--port", String(port)], {
    cwd: where.cwd,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
    env: {
      ...process.env,
      // La configuracion del backend se lee de variables EMMA_* (app/core/config.py).
      EMMA_FRONTEND_DIST: where.frontendDist,
      // La cache de datos externos va al directorio del usuario: la instalacion
      // en Archivos de programa no se puede escribir.
      EMMA_CACHE_DIR: path.join(userData, "cache"),
      // Esa cache nace vacia: sin red, la meteorologia espacial sale de la instantanea fechada
      // de NASA DONKI del paquete, declarada como tal (app/environment/donki.py).
      EMMA_DONKI_SNAPSHOT: "true",
      ...extraEnv,
    },
  });
  backend.stdout?.on("data", log.write);
  backend.stderr?.on("data", log.write);
  backend.on("exit", (code) => {
    log.write(`--- backend terminado con codigo ${code}\n`);
    if (!quitting) {
      dialog.showErrorBox(
        "EMMA",
        // En inglés: la concha de escritorio no tiene almacén de idioma y el inglés es el de partida.
        `The EMMA service has stopped (code ${code}). The application will close.\n\n` +
          `Log: ${path.join(logDir, "backend.log")}`,
      );
      app.quit();
    }
  });
}

/**
 * Mata el backend y su arbol de procesos. En Windows, `kill()` solo termina el
 * proceso directo; `taskkill /T` se lleva tambien lo que haya lanzado.
 */
function stopBackend() {
  if (backend === null || backend.exitCode !== null || backend.pid === undefined) return;
  if (process.platform === "win32") {
    execFile("taskkill", ["/pid", String(backend.pid), "/T", "/F"], { windowsHide: true });
  } else {
    backend.kill("SIGTERM");
  }
}

// --- El planificador (Marplanner) -------------------------------------------------------------
//
// Decisión del usuario (2026-11-12): Marplanner entra en EMMA entero, salvo lo que saca datos fuera.
// Corre como un proceso aparte en loopback con el Node que ya trae Electron (un `utilityProcess`:
// Node 24, el que pide Marplanner; sin encender el fusible `runAsNode`), con su base en el ledger del backend (`planner-bridge/`). Va
// compilado por `planner-bridge/build-marplanner.mjs`, que deja `undici` fuera del paquete para que
// su salida a internet también pase por la puerta de EMMA. Si no arranca, EMMA sigue: el
// planificador no es parte del análisis y su sección lo dirá como no disponible.

/** @type {Electron.UtilityProcess | null} */
let planner = null;

function plannerLocations() {
  if (app.isPackaged) {
    const resources = process.resourcesPath;
    return { runtime: path.join(resources, "marplanner"), bridge: path.join(resources, "planner-bridge") };
  }
  const repo = path.resolve(__dirname, "..");
  return { runtime: path.join(repo, "desktop", "build", "marplanner"), bridge: path.join(repo, "planner-bridge") };
}

/**
 * Las claves de Marplanner de esta instalación: aleatorias, creadas la primera vez y guardadas solo
 * para el usuario. Nunca las de ejemplo de su `.env.example` (las conoce cualquiera que lea su
 * README). La clave de arranque la usa también el backend (`app/planner_link.py`).
 */
function plannerCredentials(dir) {
  const file = path.join(dir, "credentials.json");
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    const crypto = require("node:crypto");
    const token = (prefix) => `${prefix}${crypto.randomBytes(24).toString("base64url")}`;
    const credentials = {
      accessToken: token("mpg-"),
      bootstrapKey: token("mpk-"),
      adminPin: String(crypto.randomInt(0, 1_000_000)).padStart(6, "0"),
    };
    fs.writeFileSync(file, JSON.stringify(credentials, null, 2), { mode: 0o600 });
    return credentials;
  }
}

function plannerSetup() {
  const where = plannerLocations();
  if (!fs.existsSync(path.join(where.runtime, "server", "index.js"))) return null;
  const dataDir = path.join(app.getPath("userData"), "marplanner");
  fs.mkdirSync(dataDir, { recursive: true });
  return { ...where, dataDir, credentials: plannerCredentials(dataDir) };
}

/** Lo que el backend necesita saber del planificador (`app/planner_link.py`, `app/planner_ground.py`). */
function plannerBackendEnv(setup, plannerPort, summaryPort) {
  if (setup === null) return {};
  return {
    EMMA_PLANNER_URL: `http://${LOOPBACK}:${plannerPort}`,
    EMMA_PLANNER_BOOTSTRAP_KEY: setup.credentials.bootstrapKey,
    // El resumen de Tierra lo da un servicio local en un utilityProcess (`summary-server.mjs`).
    EMMA_PLANNER_SUMMARY_URL: `http://${LOOPBACK}:${summaryPort}/summary`,
  };
}

/** @type {Electron.UtilityProcess | null} */
let summaryService = null;

/**
 * Un proceso de Node propio de Electron (`utilityProcess`): EMMA.exe tiene apagado a propósito el
 * fusible `runAsNode` (no puede usarse como intérprete de Node cualquiera), y así se respeta
 * (decisión del usuario, 2026-11-12). Lo que escribe va al registro dado.
 */
function forkNode(script, args, { cwd, env, execArgv, logName, label }) {
  const { utilityProcess } = require("electron");
  const logDir = path.join(app.getPath("userData"), "logs");
  const log = fs.createWriteStream(path.join(logDir, logName), { flags: "a" });
  log.write(`
--- ${new Date().toISOString()} ${label}
`);
  const child = utilityProcess.fork(script, args, {
    cwd,
    env: { ...process.env, ...env },
    execArgv,
    stdio: "pipe",
    serviceName: label,
  });
  child.stdout?.on("data", (data) => log.write(data));
  child.stderr?.on("data", (data) => log.write(data));
  child.on("exit", (code) => log.write(`--- ${label} terminado con codigo ${code}
`));
  return child;
}

function startPlanner(setup, plannerPort, summaryPort, backendPort) {
  // `run-marplanner.mjs` carga el puente antes que el servidor (el `--import` no vale aquí).
  planner = forkNode(path.join(setup.bridge, "run-marplanner.mjs"), [path.join(setup.runtime, "server", "index.js")], {
    cwd: setup.runtime,
    execArgv: [],
    logName: "planner.log",
    label: `planificador puerto ${plannerPort}`,
    env: {
      HOST: LOOPBACK,
      PORT: String(plannerPort),
      DATA_DIR: setup.dataDir,
      DATABASE_PATH: "marplanner.db",
      EMMA_PLANNER_LEDGER: `http://${LOOPBACK}:${backendPort}/api/planner`,
      MP_ACCESS_TOKEN: setup.credentials.accessToken,
      MP_BOOTSTRAP_KEY: setup.credentials.bootstrapKey,
      MP_ADMIN_PIN: setup.credentials.adminPin,
      // El tiempo de Open-Meteo saca la ubicación del hogar: apagado (y sin propósito en la puerta).
      WEATHER_ENABLED: "0",
    },
  });
  summaryService = forkNode(path.join(setup.bridge, "summary-server.mjs"), [], {
    cwd: setup.runtime,
    execArgv: [],
    logName: "planner.log",
    label: `resumen de Tierra puerto ${summaryPort}`,
    env: {
      EMMA_PLANNER_SUMMARY_PORT: String(summaryPort),
      EMMA_PLANNER_SUMMARY_BUNDLE: path.join(setup.runtime, "summary-modules.js"),
    },
  });
}

function stopPlanner() {
  for (const child of [planner, summaryService]) {
    if (child !== null && child.pid !== undefined) child.kill();
  }
}

// --- El paquete de modelos ---------------------------------------------------------------------
//
// Decisión del usuario (2026-11-15): los modelos se instalan con EMMA como un paquete aparte, desde
// disco o USB y sin red (`backend/packaging/models_pack.py`, que deja `instalar.cmd` dentro). Aquí
// solo se usa si su instalador terminó de comprobarlo (`instalado.json`); sin él, cada función que
// depende de un modelo se declara no disponible, como sin paquete.

/** @type {import("node:child_process").ChildProcess | null} */
let ollama = null;

/** Dónde se instala el paquete: `EMMA_MODELS_DIR` o `%LOCALAPPDATA%\EMMA-modelos`. */
function modelsDir() {
  if (process.env.EMMA_MODELS_DIR) return process.env.EMMA_MODELS_DIR;
  const local = process.env.LOCALAPPDATA ?? path.join(app.getPath("home"), "AppData", "Local");
  return path.join(local, "EMMA-modelos");
}

/**
 * Lo que el backend necesita para usar cada pieza del paquete que esté instalada. Función pura
 * sobre lo que hay en disco (`exists`): las rutas son las que deja `models_pack.py`.
 */
function modelsEnv(dir, exists = fs.existsSync) {
  if (!exists(path.join(dir, "instalado.json"))) return null;
  const env = {
    // Las copias de Python del paquete no deben ver los paquetes del usuario.
    PYTHONNOUSERSITE: "1",
  };
  const voice = path.join(dir, "voice");
  if (exists(path.join(voice, "python.exe"))) env.BTP_VENV_VOICE = voice;
  const seg = path.join(dir, "segmentation");
  if (exists(path.join(seg, "python.exe"))) {
    env.EMMA_TOTALSEG_CMD = path.join(seg, "python.exe");
    env.TOTALSEG_HOME_DIR = path.join(seg, "home");
  }
  const tesseract = path.join(dir, "tesseract", "tesseract.exe");
  if (exists(tesseract)) env.EMMA_TESSERACT_CMD = tesseract;
  const server = path.join(dir, "ollama", "ollama.exe");
  return { env, ollama: exists(server) ? server : null, models: path.join(dir, "ollama", "models") };
}

/**
 * El Ollama del paquete, solo en loopback y en un puerto propio: no choca con otro Ollama que
 * tenga el equipo. Solo el servidor (`serve`); la aplicación de bandeja no viaja en el paquete.
 */
function startOllama(setup, port) {
  const logDir = path.join(app.getPath("userData"), "logs");
  fs.mkdirSync(logDir, { recursive: true });
  const log = fs.createWriteStream(path.join(logDir, "ollama.log"), { flags: "a" });
  log.write(`\n--- ${new Date().toISOString()} puerto ${port}\n`);
  ollama = spawn(setup.ollama, ["serve"], {
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, OLLAMA_HOST: `${LOOPBACK}:${port}`, OLLAMA_MODELS: setup.models },
  });
  ollama.stdout?.on("data", (data) => log.write(data));
  ollama.stderr?.on("data", (data) => log.write(data));
  ollama.on("exit", (code) => log.write(`--- ollama terminado con codigo ${code}\n`));
  ollama.on("error", (err) => log.write(`--- ollama no arranco: ${err.message}\n`));
}

function stopOllama() {
  if (ollama === null || ollama.exitCode !== null || ollama.pid === undefined) return;
  if (process.platform === "win32") {
    execFile("taskkill", ["/pid", String(ollama.pid), "/T", "/F"], { windowsHide: true });
  } else {
    ollama.kill("SIGTERM");
  }
}

function lockDown(origin) {
  // Ningun permiso del navegador (ni notificaciones ni ningun otro) salvo `sensors` y el `media`
  // acotado de mas abajo. `sensors`:
  // el giroscopio con el que la vista gira sola (frontend/src/lib/orientation.ts). En
  // microgravedad el giro automatico del sistema usa el acelerometro, que no sabe donde es
  // abajo; el giroscopio si sirve. Es un permiso de solo lectura que no saca nada del equipo.
  // Las comprobaciones (`setPermissionCheckHandler`) siguen como estaban: este cambio solo deja
  // pasar la peticion de `sensors`. Sin probar con un equipo que tenga giroscopio.
  //
  // Y `media` solo si pide video y nada mas: la vista que sigue la cara (demostracion,
  // frontend/src/lib/faceCamera.ts) usa la camara frontal para sacar el giro de la cara sobre la
  // pantalla. En microgravedad el giroscopio no sabe si la persona gira con la tableta; su cara
  // si. Ningun fotograma se guarda ni sale del equipo.
  //
  // O `media` solo si pide audio y nada mas: el microfono del asistente (frontend/src/assistant/),
  // que graba mientras se mantiene pulsado «Hablar con EMMA» o Ctrl+Espacio, y el del modo
  // «Escuchar "EMMA"» (manos libres, frontend/src/assistant/wake/), que oye la palabra con Vosk
  // dentro de la pagina y graba solo la frase que sigue. El audio va al Whisper local del backend
  // en loopback (`POST /api/assistant/audio`); no sale del equipo ni se guarda en el navegador.
  // Es la regla mas estricta que deja funcionar a los tres: cada uno pide un solo tipo, asi que
  // una peticion de camara y microfono a la vez, o sin tipos declarados, se deniega, y tambien la
  // de cualquier origen que no sea el de la propia aplicacion. Limites: el permiso no sabe si el
  // modo que lo pide esta puesto; y esta peticion no distingue la camara y el microfono de la
  // captura de pantalla antigua (`chromeMediaSource: "desktop"`, que tambien llega como `video` o
  // `audio`); `getDisplayMedia` sigue denegado porque no hay `setDisplayMediaRequestHandler`, y en
  // el origen de la aplicacion solo corre el codigo de EMMA. Sin probar con un microfono real en
  // la aplicacion empaquetada.
  session.defaultSession.setPermissionRequestHandler((_wc, permission, callback, details) => {
    if (permission === "sensors") return callback(true);
    if (permission === "media") {
      const types = Array.isArray(details?.mediaTypes) ? details.mediaTypes : [];
      let sameOrigin = false;
      try {
        sameOrigin = new URL(details?.requestingUrl ?? "").origin === origin;
      } catch {
        sameOrigin = false;
      }
      const only = (kind) => types.length > 0 && types.every((type) => type === kind);
      return callback(sameOrigin && (only("video") || only("audio")));
    }
    return callback(false);
  });

  app.on("web-contents-created", (_event, contents) => {
    contents.on("will-navigate", (event, url) => {
      if (new URL(url).origin !== origin) event.preventDefault();
    });
    contents.setWindowOpenHandler(({ url }) => {
      // La evidencia enlazada (HRP, OSDR) se abre fuera, en el navegador del sistema.
      if (url.startsWith("https://")) void shell.openExternal(url);
      return { action: "deny" };
    });
    contents.on("will-attach-webview", (event) => event.preventDefault());
  });
}

// El atajo de emergencia de la voz, del sistema: funciona aunque la ventana de EMMA no tenga el
// foco (otra aplicacion delante, la ventana minimizada). Lo pidio el usuario (2026-11): quien se
// queda sin ver de repente no puede buscar la ventana ni el boton. Trae la ventana al frente y le
// pide el gesto de emergencia (frontend/src/lib/emergencyVoice.ts): encender la voz y leer.
//
// Ctrl+Alt+V: no es atajo de Windows (los del sistema llevan la tecla Windows) y en el teclado
// espanol AltGr+V (que Windows recibe como Ctrl+Alt+V) no escribe nada. Choca con el «Pegado
// especial» de Office: mientras EMMA este abierta, el atajo es suyo en todo el equipo. Si otra
// aplicacion ya lo tiene, `register` devuelve falso y queda el gesto de la pagina (triple Escape).
const EMERGENCY_SHORTCUT = "Control+Alt+V";
// El mismo nombre que `EMERGENCY_EVENT` en frontend/src/lib/emergencyVoice.ts (una prueba lo vigila).
const EMERGENCY_EVENT = "emma:emergency-voice";
// Mantener el atajo pulsado repite el aviso del sistema: el que llega antes de este tiempo desde el
// anterior no se atiende (si no, la lectura volveria a empezar con cada repeticion). DISENO DE
// EMMA, sin fuente.
const EMERGENCY_REPEAT_MS = 1_500;

/**
 * Registra el atajo de emergencia para esta ventana. Por que `executeJavaScript` y no tres Escape
 * con `sendInputEvent`: por la norma HTML una pulsacion de Escape no cuenta como gesto de la
 * persona, y Chromium solo deja hablar tras uno; `executeJavaScript(..., true)` corre como gesto
 * (`userGesture`). Y el codigo es una cadena fija que solo lanza un suceso del DOM: ni preload ni
 * IPC, la pagina sigue sin ningun acceso al proceso principal.
 *
 * Se registra cuando la pagina ha terminado de cargar (`did-finish-load`): antes, la consola aun no
 * escucha el suceso y el atajo no haria nada, y la ventana se ensenaria a medio pintar.
 */
function registerEmergencyShortcut(window) {
  const code = `window.dispatchEvent(new Event(${JSON.stringify(EMERGENCY_EVENT)}))`;
  let last = -Infinity;
  const ok = globalShortcut.register(EMERGENCY_SHORTCUT, () => {
    if (window.isDestroyed()) return;
    // Cada repeticion corre el plazo: mantenerlo pulsado no vuelve a pedirlo nunca.
    const now = Date.now();
    const quiet = now - last >= EMERGENCY_REPEAT_MS;
    last = now;
    if (!quiet) return;
    if (window.isMinimized()) window.restore();
    window.show();
    window.focus();
    window.webContents.executeJavaScript(code, true).catch(() => undefined);
  });
  if (!ok) console.warn(`EMMA: el atajo ${EMERGENCY_SHORTCUT} ya lo tiene otra aplicacion`);
}

/** Plazo de búsqueda de la banda de pulso en curso (`select-bluetooth-device`). */
let bluetoothTimer = null;

function createWindow(origin) {
  const window = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 960,
    minHeight: 600,
    title: "EMMA",
    // El mismo fondo que la interfaz: sin destello blanco al abrir.
    backgroundColor: "#0A0D12",
    // El icono de EMMA también en `npm start`: empaquetado, Windows ya lo toma del .exe, pero
    // sin esto la ventana de desarrollo lleva el de Electron (build/brand/README.md).
    icon: path.join(__dirname, "build", "icon.ico"),
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      spellcheck: false,
    },
  });
  window.once("ready-to-show", () => window.show());
  // Banda de pulso por Bluetooth (frontend/src/dashboard/HeartBandPanel.tsx, petición del usuario
  // 2026-11-12). Electron no trae el selector de dispositivos de Chrome: sin este manejador,
  // `navigator.bluetooth.requestDevice` no termina nunca. Chromium ya filtra por el servicio de
  // pulso que pide la página, así que se elige la primera banda que aparezca; si en 30 s no aparece
  // ninguna, se cancela y la página lo dice. Solo la página de la aplicación llega aquí (lockDown).
  window.webContents.on("select-bluetooth-device", (event, devices, callback) => {
    event.preventDefault();
    if (devices.length > 0) {
      clearTimeout(bluetoothTimer);
      bluetoothTimer = null;
      callback(devices[0].deviceId);
      return;
    }
    if (bluetoothTimer === null) {
      bluetoothTimer = setTimeout(() => {
        bluetoothTimer = null;
        callback("");
      }, 30_000);
    }
  });
  window.webContents.once("did-finish-load", () => registerEmergencyShortcut(window));
  void window.loadURL(`${origin}/`);
}

// Escenario que se carga al abrir (decisión del usuario, 2026-11-12: «directamente me tiene que
// mostrar la pantalla de inicio con el modo que más podamos mostrar que están pasando cosas»).
// El evento de partículas solares afecta a los cuatro tripulantes a la vez: medido ese día, es el
// que más estados en vigilancia deja (4 «concern» y 4 «watch»). Sus lecturas quedan firmadas como
// simuladas, igual que si se pulsara el botón. EMMA_DESKTOP_SCENARIO="" lo apaga.
const STARTUP_SCENARIO = process.env.EMMA_DESKTOP_SCENARIO ?? "spe-event";

/** Carga el escenario de arranque. Un fallo no impide abrir: queda la pantalla de elegir. */
function loadStartupScenario(port) {
  if (!STARTUP_SCENARIO) return Promise.resolve();
  return new Promise((resolve) => {
    const request = http.request(
      {
        host: LOOPBACK,
        port,
        method: "POST",
        path: `/api/simulate?scenario=${encodeURIComponent(STARTUP_SCENARIO)}`,
        headers: { "X-EMMA-Console": "1" },
        timeout: 120_000,
      },
      (res) => {
        res.resume();
        if (res.statusCode !== 201) console.error(`escenario de arranque: HTTP ${res.statusCode}`);
        resolve();
      },
    );
    request.on("error", (err) => {
      console.error(`escenario de arranque: ${err.message}`);
      resolve();
    });
    request.on("timeout", () => request.destroy(new Error("sin respuesta")));
    request.end();
  });
}

async function main() {
  if (!app.requestSingleInstanceLock()) {
    app.quit();
    return;
  }
  await app.whenReady();
  if (app.isPackaged) Menu.setApplicationMenu(null);

  const port = await freePort();
  const origin = `http://${LOOPBACK}:${port}`;
  lockDown(origin);
  const plannerSetupInfo = plannerSetup();
  const plannerPort = plannerSetupInfo === null ? 0 : await freePort();
  const summaryPort = plannerSetupInfo === null ? 0 : await freePort();
  const models = modelsEnv(modelsDir());
  const modelsBackendEnv = models === null ? {} : { ...models.env };
  if (models !== null && models.ollama !== null) {
    const ollamaPort = await freePort();
    startOllama(models, ollamaPort);
    // El backend lo comprueba en cada petición: si aún no responde, la función sale «no disponible».
    modelsBackendEnv.EMMA_LLM_URL = `http://${LOOPBACK}:${ollamaPort}`;
  }
  // «Descargar también los modelos de IA», marcado en el instalador (`installer.nsh` deja la marca
  // junto al ejecutable). Mientras no haya paquete instalado, el backend lo baja al arrancar
  // (`app/api/models_pack.py: autostart`); una vez instalado, la marca ya no cuenta.
  if (models === null && fs.existsSync(path.join(path.dirname(app.getPath("exe")), "descargar-modelos"))) {
    modelsBackendEnv.EMMA_MODELS_AUTODOWNLOAD = "true";
  }
  startBackend(port, {
    ...modelsBackendEnv,
    ...plannerBackendEnv(plannerSetupInfo, plannerPort, summaryPort),
  });

  if (!(await waitForBackend(port))) {
    if (!quitting) {
      dialog.showErrorBox(
        "EMMA",
        "The EMMA service did not start. See the log at " +
          path.join(app.getPath("userData"), "logs", "backend.log"),
      );
    }
    quitting = true;
    stopBackend();
    stopOllama();
    app.quit();
    return;
  }
  // El planificador, después del backend: su base es el ledger del backend.
  if (plannerSetupInfo !== null) startPlanner(plannerSetupInfo, plannerPort, summaryPort, port);
  await loadStartupScenario(port);
  createWindow(origin);
}

app.on("second-instance", () => {
  const [window] = BrowserWindow.getAllWindows();
  if (window) {
    if (window.isMinimized()) window.restore();
    window.focus();
  }
});

app.on("before-quit", () => {
  quitting = true;
  stopPlanner();
  stopBackend();
  stopOllama();
});

app.on("window-all-closed", () => app.quit());

// El atajo es del sistema: se suelta al salir, para que no quede robado a otras aplicaciones.
app.on("will-quit", () => globalShortcut.unregisterAll());

void main();
