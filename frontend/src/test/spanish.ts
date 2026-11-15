/**
 * La suite corre en castellano (`setupFiles` de vitest): es el idioma de sus asertos y de las
 * guardas que leen las fuentes. Se ejecuta antes de cada fichero de pruebas, así que las tablas
 * a nivel de módulo se evalúan ya en castellano. El inglés se prueba en ficheros `*.en.test.ts`,
 * que empiezan importando `./english`.
 */
import { setLanguageForTests } from "../lib/i18n";

setLanguageForTests("es");
