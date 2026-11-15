/**
 * Lo que el asistente hace en la pantalla para llegar a un panel: abrir su pestaña, desplegar sus
 * pliegues, ponerlo a la vista y leer lo que pone. Todo por el atributo `data-ui` del inventario
 * (`backend/app/data/assistant_ui.json`), nunca por el texto visible: renombrar un panel no rompe
 * la orden en silencio (lo avisó el informe de la unidad anterior), y un id que deja de existir lo
 * caza `uiInventory.test.ts`.
 *
 * LO ÚNICO QUE SE PULSA ES UNA PESTAÑA. `clickTab` comprueba que el elemento es un `role="tab"`
 * antes de pulsarlo; abrir un pliegue es poner `open` en su `<details>` (como hace el propio
 * navegador al pulsar el rótulo) o quitar el `hidden` del cuerpo de un «Ver detalle», y
 * `revealable` no admite como destino nada que no sea un panel o
 * un pliegue, ni nada que sea un mando o esté dentro de un formulario. Firmar, enviar, reconocer,
 * redactar o dar una segunda firma solo se hace por las intenciones de escritura del catálogo, con
 * su propuesta y «confirmo» (`intents.ts`). Lo vigila `uiInventory.test.ts`.
 */

import { tr } from "../lib/i18n";

export const UI_ATTRIBUTE = "data-ui";

/** Lo mínimo de un elemento que se mira aquí: así las pruebas pasan uno de mentira. */
export interface UiNode {
  tagName: string;
  getAttribute(name: string): string | null;
  closest(selector: string): unknown;
}

/** Los mandos: nada de esto es un destino del asistente. */
const CONTROLS = "button, input, select, textarea, a[href], [role='button'], [role='tab']";

/**
 * Si el asistente puede llevar a la vista este elemento: un panel (`<section>`) o un pliegue
 * (`<details>`) del inventario, que no sea un mando ni esté dentro de uno. Un pliegue dentro de un
 * formulario («Por qué es texto libre») se puede desplegar: desplegar no envía nada, y el envío
 * sigue siendo el botón del formulario, que el asistente no pulsa.
 */
export function revealable(node: UiNode): boolean {
  const tag = node.tagName.toUpperCase();
  if (tag !== "SECTION" && tag !== "DETAILS") return false;
  if (node.getAttribute(UI_ATTRIBUTE) === null) return false;
  return node.closest(CONTROLS) === null;
}

/** Pulsa la pestaña de una consola, si de verdad es una pestaña y no está ya abierta. */
export function clickTab(element: HTMLElement | null): boolean {
  if (element === null || element.getAttribute("role") !== "tab") return false;
  if (element.getAttribute("aria-selected") !== "true") element.click();
  return true;
}

/** La pestaña de una sección: la suya, o para `env-*` la de entorno abierta o la primera. */
export function tabElement(doc: Document, consoleId: string, section: string): HTMLElement | null {
  if (section !== "env-*") return doc.getElementById(`${consoleId}-tab-${section}`);
  const tabs = [...doc.querySelectorAll<HTMLElement>(`[role="tab"][id^="${consoleId}-tab-env-"]`)];
  return tabs.find((tab) => tab.getAttribute("aria-selected") === "true") ?? tabs[0] ?? null;
}

/** El primer elemento con ese id del inventario que está en una pestaña a la vista. */
export function findPanel(doc: Document, id: string): HTMLElement | null {
  const all = doc.querySelectorAll<HTMLElement>(`[${UI_ATTRIBUTE}="${CSS.escape(id)}"]`);
  return [...all].find((element) => !hiddenOutsideDetail(element) && revealable(element)) ?? null;
}

/** Lo que se mira de un elemento para saber si está oculto: las pruebas pasan uno de mentira. */
export interface HiddenNode {
  hidden: boolean | string;
  classList: { contains(token: string): boolean };
  parentElement: HiddenNode | null;
}

/** El cuerpo de un «Ver detalle» del tablero (`components/BoardDetail.tsx`). */
const BOARD_DETAIL_BODY = "board-detail-body";

/**
 * Si el elemento está oculto por algo que no sea un «Ver detalle» cerrado: una pestaña que no es la
 * abierta, un panel que no toca. Un «Ver detalle» cerrado de la pestaña a la vista no cuenta (lote
 * «muestra», 2026-11-08): guarda el texto largo de un panel y puede guardar pliegues del inventario;
 * `reveal` lo abre igual que abre un `<details>`.
 */
export function hiddenOutsideDetail(element: HiddenNode): boolean {
  for (let node: HiddenNode | null = element; node !== null; node = node.parentElement) {
    if (node.hidden !== false && !node.classList.contains(BOARD_DETAIL_BODY)) return true;
  }
  return false;
}

/** Despliega el pliegue y los que lo contienen, y lo lleva a la vista. */
export function reveal(element: HTMLElement): void {
  for (let node: HTMLElement | null = element; node !== null; node = node.parentElement) {
    if (node instanceof HTMLDetailsElement && !node.open) node.open = true;
    // Un «Ver detalle» cerrado se abre quitando su `hidden`, como un `<details>` con `open`: el
    // componente lo ve y pasa a abierto (`BoardDetail`). No se pulsa su mando.
    if (node.hidden && node.classList.contains(BOARD_DETAIL_BODY)) node.hidden = false;
  }
  element.scrollIntoView({ block: "start" });
  // Los paneles de encima pueden estar aún cargando y crecer (la pestaña recién abierta pide sus
  // datos), y el propio panel pasa de «cargando» a su contenido con otro elemento del mismo
  // `data-ui`: se vuelve a buscar por el id y a poner a la vista cuando la maqueta se asienta
  // (visto en el recorrido de Playwright: «los bancos de prueba» quedaban debajo de «Marco de NASA»).
  const id = element.getAttribute(UI_ATTRIBUTE);
  const doc = element.ownerDocument;
  for (const ms of SETTLE_MS) {
    setTimeout(() => {
      const now = id === null ? null : findPanel(doc, id);
      now?.scrollIntoView({ block: "start" });
    }, ms);
  }
}

const SETTLE_MS = [600, 1500, 3000];

const FIND_MS = 8000;
const FIND_STEP_MS = 50;

/**
 * Repite `look` cada 50 ms hasta que da `true`, ocho segundos como mucho (por reloj, no por
 * fotogramas, que un equipo cargado espacia): la pestaña
 * recién abierta tarda en montarse, y un pliegue como el glosario no existe hasta que llegan sus
 * datos (visto en el recorrido de Playwright: con un segundo, a veces no llegaba).
 */
export function untilFound(look: () => boolean, ms = FIND_MS, giveUp: () => void = () => undefined): void {
  const deadline = Date.now() + ms;
  const step = () => {
    if (look()) return;
    if (Date.now() < deadline) setTimeout(step, FIND_STEP_MS);
    else giveUp();
  };
  setTimeout(step, 0);
}

/** Los paneles de primer nivel de la pestaña abierta: los `data-ui` sin otro `data-ui` encima. */
export function topPanels(doc: Document, consoleId: string): HTMLElement[] {
  const open = [...doc.querySelectorAll<HTMLElement>(`[role="tabpanel"][id^="${consoleId}-panel-"]`)].find(
    (element) => !element.hidden,
  );
  if (open === undefined) return [];
  return [...open.querySelectorAll<HTMLElement>(`[${UI_ATTRIBUTE}]`)].filter(
    (element) => element.parentElement?.closest(`[${UI_ATTRIBUTE}]`) === null && revealable(element),
  );
}

/** Si el panel está tapado por la privacidad (`ConsoleTabs`: difuminado e `inert`). */
export function covered(element: HTMLElement): boolean {
  return element.closest(".privacy-cover, [inert]") !== null;
}

/** Cuántas líneas se leen de un panel como mucho; el resto queda en pantalla. */
export const MAX_READ_LINES = 40;
export const MORE_ON_SCREEN = tr("Hay más en pantalla.", "There is more on screen.");
export const PANEL_COVERED = tr(
  "Ese panel está tapado por la privacidad: no lo leo.",
  "That panel is covered by privacy: I am not reading it.",
);
export const PANEL_NOT_FOUND = tr(
  "No encuentro ese panel en pantalla: no lo leo.",
  "I cannot find that panel on screen: I am not reading it.",
);
export const NAME_COVERED = tr("tripulante tapado", "crew member hidden");

/**
 * Lo que pone el panel, línea a línea, tal como se ve (`innerText`: lo plegado y lo oculto no
 * cuenta). Con la privacidad, cada nombre que se tapa en pantalla se dice como «tripulante tapado».
 */
export function readableLines(text: string, names: readonly string[]): string[] {
  const shown = names.filter((name) => name.trim() !== "");
  const lines: string[] = [];
  for (const raw of text.split(/\n+/)) {
    let line = raw.replace(/\s+/g, " ").trim();
    if (line === "") continue;
    for (const name of shown) line = line.split(name).join(NAME_COVERED);
    if (lines[lines.length - 1] !== line) lines.push(line);
  }
  if (lines.length <= MAX_READ_LINES) return lines;
  return [...lines.slice(0, MAX_READ_LINES), MORE_ON_SCREEN];
}
