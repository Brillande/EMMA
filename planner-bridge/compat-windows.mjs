// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Lo que a Marplanner le falta en Windows, sin tocar su copia (como `app/polaris/compat/`).
 *
 * Por qué existe: Marplanner se escribió para Linux y macOS. Para que una copia o un renombrado
 * sobrevivan a un corte de luz abre el fichero —o el DIRECTORIO— en solo lectura y le hace
 * `fsync`. En Windows eso da EPERM en los dos casos: `FlushFileBuffers` exige un descriptor con
 * permiso de escritura, y a un directorio no se le puede hacer. Su copia previa a una migración
 * fallaba entera.
 *
 * Aquí, solo en Windows:
 *   - fichero abierto en solo lectura: se vuelve a abrir con escritura y se fuerza ESE, de modo
 *     que la garantía que Marplanner pide se cumple de verdad;
 *   - directorio: en NTFS el renombrado ya va al diario del sistema de ficheros y no hay nada que
 *     forzar; el EPERM se trata como hecho.
 * Cualquier otro fallo de `fsync` llega tal cual.
 */
import fs from "node:fs";
import { syncBuiltinESMExports } from "node:module";

if (process.platform === "win32") {
  const paths = new Map();
  const { openSync, closeSync, fsyncSync } = fs;

  fs.openSync = function patchedOpenSync(file, flags, mode) {
    const fd = openSync(file, flags, mode);
    if (typeof file === "string" || file instanceof URL || Buffer.isBuffer(file)) paths.set(fd, file);
    return fd;
  };
  fs.closeSync = function patchedCloseSync(fd) {
    paths.delete(fd);
    return closeSync(fd);
  };
  fs.fsyncSync = function patchedFsyncSync(fd) {
    try {
      return fsyncSync(fd);
    } catch (error) {
      if (error?.code !== "EPERM") throw error;
      if (fs.fstatSync(fd).isDirectory()) return undefined;
      const file = paths.get(fd);
      if (file === undefined) throw error;
      const writable = openSync(file, "r+");
      try {
        return fsyncSync(writable);
      } finally {
        closeSync(writable);
      }
    }
  };
  // Que también lo vea quien importa `{ fsyncSync }` con nombre.
  syncBuiltinESMExports();
}
