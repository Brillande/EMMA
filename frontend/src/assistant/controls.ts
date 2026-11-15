/**
 * Los botones que hay a la vista, para que el asistente pueda pulsar uno por voz.
 *
 * Por qué existe: el asistente abría pestañas y paneles, pero no pulsaba nada dentro («abdomen
 * hígado 1 de volúmenes 3D», el usuario, 2026-11-06). Los botones cambian con cada panel y con los
 * datos, así que no hay inventario fijo: con cada turno se manda al backend el rótulo de cada botón
 * del contenido (`<main>`) que se ve, y si pulsarlo guarda algo. El backend elige uno de ESTOS, o
 * ninguno (`backend/app/assistant/controls.py`); aquí se vuelve a buscar por su rótulo y se pulsa.
 *
 * Qué guarda: todo botón, salvo el que lleve `data-ui-view` (él o un antepasado), que declara que
 * solo cambia la vista. En la duda se pregunta: un botón sin marcar no se pulsa sin «confirmo»
 * (decisión del usuario del 2026-11-06: «confirmar solo si guarda»). Lo que guarde lo guarda el
 * propio botón, por su ruta de siempre: el asistente no firma nada.
 *
 * Fuera de la lista: los del propio asistente (están fuera de `<main>`), los desactivados y los
 * que no se ven.
 */

import type { AssistantControl } from "../lib/api";

export const MAX_CONTROLS = 200;
export const MAX_LABEL = 120;

/** El rótulo de un botón tal como se lee: su `aria-label` o su texto, en una línea. */
export function controlLabel(button: HTMLElement): string {
  const raw = button.getAttribute("aria-label") ?? button.textContent ?? "";
  return raw.replace(/\s+/g, " ").trim().slice(0, MAX_LABEL);
}

/** Para comparar rótulos: sin mayúsculas, tildes ni puntuación (como `plain` del backend). */
export function sameLabel(a: string, b: string): boolean {
  const plain = (text: string) =>
    text
      .normalize("NFD")
      .replace(/\p{Diacritic}/gu, "")
      .toLowerCase()
      .replace(/[^\p{L}\p{N}]+/gu, " ")
      .trim();
  return plain(a) === plain(b);
}

function shown(button: HTMLButtonElement): boolean {
  if (button.disabled || button.closest("[hidden], [aria-hidden='true'], [inert]") !== null) return false;
  // Las pestañas no: ya las abre `open_tab` por su nombre, y «misión y hábitat» no debe acabar en
  // «¿pulso Misión y hábitat?».
  if (button.getAttribute("role") === "tab" || button.closest("[role='tablist'], nav") !== null) return false;
  return button.getClientRects().length > 0;
}

function buttonsIn(root: ParentNode): HTMLButtonElement[] {
  return Array.from(root.querySelectorAll<HTMLButtonElement>("main button")).filter(shown);
}

/** Los botones a la vista, sin repetir rótulo, como mucho `MAX_CONTROLS`. */
export function visibleControls(root: ParentNode = document): AssistantControl[] {
  const out: AssistantControl[] = [];
  const seen = new Set<string>();
  for (const button of buttonsIn(root)) {
    const label = controlLabel(button);
    const key = label.toLowerCase();
    if (label === "" || seen.has(key)) continue;
    seen.add(key);
    out.push({ label, writes: button.closest("[data-ui-view]") === null });
    if (out.length >= MAX_CONTROLS) break;
  }
  return out;
}

/** El botón a la vista con ese rótulo, o null si ya no está (se cerró el panel, cambió el dato). */
export function findControl(label: string, root: ParentNode = document): HTMLButtonElement | null {
  return buttonsIn(root).find((button) => sameLabel(controlLabel(button), label)) ?? null;
}

/** ¿Pulsar ese botón guarda algo? (lo que se le dijo al backend). */
export function controlWrites(button: HTMLElement): boolean {
  return button.closest("[data-ui-view]") === null;
}

/** Lo lleva a la vista y lo pulsa como lo haría una persona. Devuelve si estaba. */
export function pressControl(label: string, root: ParentNode = document): boolean {
  const button = findControl(label, root);
  if (button === null) return false;
  button.scrollIntoView({ block: "nearest" });
  button.focus({ preventScroll: true });
  button.click();
  return true;
}
