// Congela el backend con un entorno Python limpio, solo con dependencias de
// ejecucion + PyInstaller (ver backend/packaging/freeze.py para el porque).
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const backend = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "backend");
const devPython = join(backend, ".venv", "Scripts", "python.exe");
const venv = join(backend, "build", "venv-desktop");
const python = join(venv, "Scripts", "python.exe");

const run = (command, args) => execFileSync(command, args, { cwd: backend, stdio: "inherit" });

if (!existsSync(python)) {
  console.log("Creando el entorno de empaquetado (solo dependencias de ejecucion)...");
  run(devPython, ["-m", "venv", venv]);
}
// Siempre: si cambian las dependencias del backend, el ejecutable las recoge. El extra [spice]
// (spiceypy con CSPICE) va dentro: el retardo con Tierra sale sin red desde el primer arranque
// (decision del usuario, 2026-11-11). Los nucleos los comprueba y empaqueta freeze.py.
run(python, ["-m", "pip", "install", "--quiet", "--upgrade", ".[desktop,spice]"]);
run(python, [join("packaging", "freeze.py")]);
