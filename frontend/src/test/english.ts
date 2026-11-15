/**
 * Para probar la interfaz en inglés: un fichero `*.en.test.ts` importa este módulo LO PRIMERO,
 * antes que cualquier otro, y todo lo que importe después se evalúa en inglés (también las tablas
 * a nivel de módulo). No se mezclan los dos idiomas en un mismo fichero de pruebas.
 */
import { setLanguageForTests } from "../lib/i18n";

setLanguageForTests("en");
