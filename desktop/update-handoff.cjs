/**
 * Comprobación del traspaso de una actualización: del backend al proceso principal.
 *
 * POR QUE EXISTE
 * --------------
 * El backend consulta y descarga el instalador nuevo por `backend/app/core/egress.py` (la única
 * salida a internet de EMMA) y lo deja en la carpeta de actualización con `listo.json`; cuando una
 * persona pulsa «Instalar y reiniciar», escribe además `instalar.json`. Quien lanza el instalador es
 * el proceso principal de Electron, que no sale a internet y no se fía de esa carpeta: es un fichero
 * que pide ejecutar un programa. Antes de lanzarlo se comprueba aquí que el nombre no saca la ruta
 * de la carpeta, que la versión es posterior a la que corre y que el SHA-256 del ejecutable, medido
 * otra vez aquí, es el de `instalar.json` y el de `listo.json`.
 *
 * Va en un módulo aparte, sin Electron, para que la suite del backend lo pruebe con `node`
 * (`backend/tests/test_desktop_update.py`). Sin red: solo `fs`, `path` y `crypto`.
 */

"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const READY_FILE = "listo.json";
const REQUEST_FILE = "instalar.json";
const SHA256_HEX = /^[0-9a-f]{64}$/;
// Solo X.Y.Z (con «v» delante si viene de la etiqueta de la release): es lo que publica EMMA.
const SEMVER = /^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;

/**
 * Un nombre de fichero simple: sin separadores, sin `..`, sin unidad ni flujo alternativo de NTFS
 * (`:`), sin caracteres de control, y terminado en `.exe`.
 */
function isSafeFileName(name) {
  if (typeof name !== "string" || name.length === 0 || name.length > 255) return false;
  if (/[\\/:*?"<>|\u0000-\u001f]/.test(name)) return false;
  if (name === "." || name === ".." || name.includes("..")) return false;
  // Windows ignora los puntos y espacios del final: «x.exe.» abriría «x.exe».
  if (/[. ]$/.test(name)) return false;
  // Nombres de dispositivo de Windows («NUL.exe», «com1.exe»): no son un fichero de la carpeta.
  if (/^(con|prn|aux|nul|com[0-9¹²³]|lpt[0-9¹²³])(\.|$)/i.test(name)) return false;
  return name.toLowerCase().endsWith(".exe");
}

/** La ruta del fichero dentro de `dir`, o `null` si al resolverla queda fuera. */
function resolveInside(dir, name) {
  if (!isSafeFileName(name)) return null;
  const base = path.resolve(dir);
  const target = path.resolve(base, name);
  const relative = path.relative(base, target);
  if (relative === "" || relative.startsWith("..") || path.isAbsolute(relative)) return null;
  if (path.dirname(target) !== base) return null;
  return target;
}

/** `[mayor, menor, parche]`, o `null` si no es X.Y.Z. */
function parseSemver(version) {
  if (typeof version !== "string") return null;
  const match = SEMVER.exec(version.trim());
  return match === null ? null : [Number(match[1]), Number(match[2]), Number(match[3])];
}

/** Cierto solo si `candidate` es una versión X.Y.Z estrictamente posterior a `current`. */
function isNewerVersion(candidate, current) {
  const a = parseSemver(candidate);
  const b = parseSemver(current);
  if (a === null || b === null) return false;
  for (let i = 0; i < 3; i += 1) {
    if (a[i] !== b[i]) return a[i] > b[i];
  }
  return false;
}

function normalizeSha(value) {
  return typeof value === "string" ? value.trim().toLowerCase() : "";
}

/** SHA-256 de un fichero, leído por trozos: el instalador pesa cientos de MB. */
function sha256File(file) {
  return new Promise((resolve, reject) => {
    const hash = crypto.createHash("sha256");
    const stream = fs.createReadStream(file);
    stream.on("error", reject);
    stream.on("data", (chunk) => hash.update(chunk));
    stream.on("end", () => resolve(hash.digest("hex")));
  });
}

function readJson(file) {
  const data = JSON.parse(fs.readFileSync(file, "utf8"));
  if (data === null || typeof data !== "object" || Array.isArray(data)) throw new Error("no es un objeto");
  return data;
}

/**
 * Lo que pide `instalar.json`, comprobado contra `listo.json` y contra el propio ejecutable.
 * Devuelve `{ ok: true, exe, version }` o `{ ok: false, reason }`; nunca lanza.
 */
async function validateHandoff(dir, currentVersion) {
  const fail = (reason) => ({ ok: false, reason });
  let request;
  let ready;
  try {
    request = readJson(path.join(dir, REQUEST_FILE));
  } catch (err) {
    return fail(`${REQUEST_FILE} ilegible: ${err.message}`);
  }
  try {
    ready = readJson(path.join(dir, READY_FILE));
  } catch (err) {
    return fail(`${READY_FILE} ilegible: ${err.message}`);
  }

  const exe = resolveInside(dir, request.file);
  if (exe === null) return fail("nombre de fichero no admitido");
  if (ready.file !== request.file) return fail(`${READY_FILE} habla de otro fichero`);
  if (parseSemver(request.version) === null) return fail("versión no X.Y.Z");
  if (ready.version !== request.version) return fail(`${READY_FILE} habla de otra versión`);
  if (!isNewerVersion(request.version, currentVersion)) {
    return fail(`la versión ${request.version} no es posterior a ${currentVersion}`);
  }
  const wanted = normalizeSha(request.sha256);
  if (!SHA256_HEX.test(wanted)) return fail("sha256 mal formado");
  if (normalizeSha(ready.sha256) !== wanted) return fail(`el sha256 de ${READY_FILE} no coincide`);

  let stat;
  try {
    stat = fs.lstatSync(exe);
  } catch {
    return fail("el instalador no está");
  }
  // Ni enlaces ni directorios: se mide y se ejecuta el fichero que hay, no al que apunte.
  if (!stat.isFile()) return fail("el instalador no es un fichero normal");
  if (typeof ready.size === "number" && ready.size !== stat.size) return fail("el tamaño no coincide");

  let actual;
  try {
    actual = await sha256File(exe);
  } catch (err) {
    return fail(`no se pudo leer el instalador: ${err.message}`);
  }
  if (actual !== wanted) return fail("el sha256 del instalador no coincide");
  return { ok: true, exe, version: request.version };
}

module.exports = {
  READY_FILE,
  REQUEST_FILE,
  isSafeFileName,
  resolveInside,
  parseSemver,
  isNewerVersion,
  sha256File,
  validateHandoff,
};
