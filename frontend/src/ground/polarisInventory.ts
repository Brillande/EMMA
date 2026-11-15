// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * La copia de Polaris, ordenada para leerla: que filtro deja ver que, y como se nombra cada estado.
 *
 * Por que existe aparte del panel: lo que se puede equivocar aqui es logica, no pintura. Un
 * filtro que cuente como "en uso" lo que solo viaja con la copia, o un "no carga" pintado en
 * cian (que en la tabla F.5-1 es "dato ausente", no "no disponible"), dirian algo falso sobre
 * codigo de terceros. Esta en un `.ts` para que lo pruebe `polarisInventory.test.ts`.
 *
 * Los estados son tres, no dos: el inventario del backend no importa las herramientas que hacen
 * algo solo con importarse, y de esas no se sabe si cargarian (`carga` es `null`). Contarlas
 * entre las que "no cargan" seria afirmar un fallo que nadie ha visto.
 *
 * Nada de aqui redacta: el estado, el motivo, la ficha y los cambios son los de `GET /api/polaris/estado`,
 * que a su vez los lee de `polaris/` tal cual (commit en `polaris/ADOPTADO.txt`). Este fichero
 * no contiene codigo de Polaris.
 */

import type { PolarisChange, PolarisTool } from "../lib/api";
import { formatSourceDate } from "../lib/format";
import { type StateMark, mark } from "../lib/marks";
import { tr } from "../lib/i18n";

export type PolarisFilter = "all" | "loads" | "fails" | "skipped" | "used" | "unused";

/** Rotulos de interfaz, en el orden en que se ofrecen. */
export const POLARIS_FILTERS: { id: PolarisFilter; label: string }[] = [
  { id: "all", label: tr("Todas", "All") },
  { id: "loads", label: tr("Cargan", "Load") },
  { id: "fails", label: tr("No cargan", "Do not load") },
  { id: "skipped", label: tr("No se importan", "Not imported") },
  { id: "used", label: tr("En uso por EMMA", "In use by EMMA") },
  { id: "unused", label: tr("Copiadas sin uso", "Copied, unused") },
];

const MATCHES: Record<PolarisFilter, (tool: PolarisTool) => boolean> = {
  all: () => true,
  loads: (tool) => tool.carga === true,
  fails: (tool) => tool.carga === false,
  skipped: (tool) => tool.carga === null,
  used: (tool) => tool.en_uso,
  unused: (tool) => !tool.en_uso,
};

/** Las herramientas de un filtro cuyo nombre contiene `text` (sin distinguir mayusculas). */
export function filterTools(tools: PolarisTool[], filter: PolarisFilter, text = ""): PolarisTool[] {
  const needle = text.trim().toLowerCase();
  return tools.filter(
    (tool) => MATCHES[filter](tool) && (needle === "" || tool.herramienta.toLowerCase().includes(needle)),
  );
}

/** Cuantas herramientas deja ver cada filtro: va en el rotulo del boton. */
export function countByFilter(tools: PolarisTool[]): Record<PolarisFilter, number> {
  const count = (filter: PolarisFilter) => tools.filter(MATCHES[filter]).length;
  return {
    all: count("all"),
    loads: count("loads"),
    fails: count("fails"),
    skipped: count("skipped"),
    used: count("used"),
    unused: count("unused"),
  };
}

/** La marca de un estado de herramienta (`lib/marks.ts`) con su palabra: la palabra va siempre con el dibujo. */
export interface ToolState extends StateMark {
  word: string;
}

/**
 * "No carga" es "no disponible aqui": gris (F.5-1, *unavailable*), con el aspa y la palabra
 * (F.5.10 e). Que cargue no lleva color: no es una alerta ni un visto bueno clinico, solo que
 * importa; lleva la marca de hecho.
 *
 * "No se importa" tambien es gris, porque tampoco esta disponible aqui, pero con otro dibujo (el
 * anillo barrado): no ha fallado, no se ha intentado. No es cian: no falta un dato, se ha
 * decidido no pedirlo.
 *
 * La palabra es la del backend (`estado`), tal cual: aqui solo se eligen el pictograma y el color.
 */
export function loadStyle(tool: PolarisTool): ToolState {
  if (tool.carga === null) return { ...mark("slash-circle", "gray"), word: tool.estado };
  return tool.carga
    ? { ...mark("check", null), word: tool.estado }
    : { ...mark("cross", "gray"), word: tool.estado };
}

/**
 * Si el codigo de EMMA la pide por su nombre (el enchufe: EMMA la enchufa) o solo viaja con la
 * copia (el enchufe tachado). Son los dos unicos dibujos de Tierra que no conservan su caracter:
 * eran un disco lleno y un anillo, que son las formas de "medido" y del nivel mas bajo de riesgo,
 * y en un inventario de software se leerian como un estado clinico. Sin color: no es una alerta.
 */
export function useStyle(tool: PolarisTool): ToolState {
  return tool.en_uso
    ? { ...mark("plug", null), word: tr("en uso por EMMA", "in use by EMMA") }
    : { ...mark("plug-slash", null), word: tr("copiada sin uso", "copied, unused") };
}

const SHORT_COMMIT = 7;

/** El commit como lo escribe git en corto, o `null` si la instalacion no trae `ADOPTADO.txt`. */
export function shortCommit(commit: string | null): string | null {
  return commit === null || commit === "" ? null : commit.slice(0, SHORT_COMMIT);
}

/** La fecha de un cambio en ISO 8601, o `null` si el fichero no la trae con esa forma: no se completa. */
export function changeDate(change: PolarisChange): string | null {
  if (change.fecha === null) return null;
  try {
    return formatSourceDate(change.fecha);
  } catch {
    return null;
  }
}
