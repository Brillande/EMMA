import { type ReactNode, useSyncExternalStore } from "react";

import { HomeDivider } from "../dashboard/HomeBoard";
import { type PreferenceStore, browserStore } from "./displayModes";

/**
 * Lo secundario de cada pestaña, plegable con la misma raya que «Inicio» (decisión del usuario,
 * 2026-11-15: «reducir los componentes en interfaz con un botón desplegable como el que hay en inicio
 * en el resto de pestañas»). Viene plegado, como «Inicio», y la elección se recuerda por equipo.
 *
 * Por qué un almacén de módulo y no un `useState` en la consola: la raya y los paneles que pliega son
 * entradas distintas del array de paneles de la pestaña, y cada tablero (Radiación, Aislamiento…)
 * monta las suyas sin que `CrewConsole`/`GroundConsole` tengan que llevar un estado por pestaña.
 * Cada panel secundario se envuelve por separado (`Folded`): así `personal()` y el `Slot` de
 * `ConsoleTabs` siguen siendo por panel, y un panel plegado no ocupa celda en la rejilla.
 *
 * Plegar no cambia ningún dato, solo qué se pinta. Lo que se pliega lo nombra la raya (`what`).
 * Nunca se pliega una alerta, un aviso de riesgo ni un estado clínico activo: eso queda arriba.
 */

const PREFIX = "emma.fold.";

export function foldKey(id: string): string {
  return PREFIX + id;
}

/** Lo guardado; sin nada, sin almacén o con almacén roto, plegado (como «Inicio»). */
export function readFold(store: PreferenceStore | null, id: string): boolean {
  try {
    return store?.getItem(foldKey(id)) === "true";
  } catch {
    return false;
  }
}

export function writeFold(store: PreferenceStore | null, id: string, open: boolean): void {
  try {
    store?.setItem(foldKey(id), open ? "true" : "false");
  } catch {
    // Sin almacén dura lo que la sesión.
  }
}

const state = new Map<string, boolean>();
const listeners = new Set<() => void>();

function isOpen(id: string): boolean {
  let open = state.get(id);
  if (open === undefined) {
    open = readFold(browserStore(), id);
    state.set(id, open);
  }
  return open;
}

export function setFoldOpen(id: string, open: boolean): void {
  state.set(id, open);
  writeFold(browserStore(), id, open);
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Si lo secundario de `id` está a la vista. */
export function useFoldOpen(id: string): boolean {
  // Sin hidratación en la consola: el pintado estático (pruebas) lee el mismo estado.
  const read = () => isOpen(id);
  return useSyncExternalStore(subscribe, read, read);
}

/** Solo para pruebas: olvida lo leído para que la siguiente lectura vaya al almacén. */
export function resetFoldsForTests(): void {
  state.clear();
}

/** La raya con su mando: entrada propia del array de paneles, entre lo principal y lo secundario. */
export function FoldDivider({
  id,
  what,
  name,
  pictogram,
}: {
  id: string;
  /** Qué se pliega, dicho en el propio mando (con `tr`). */
  what: string;
  /** El nombre de lo plegado; por defecto, «lo secundario». */
  name?: string | undefined;
  pictogram?: Parameters<typeof HomeDivider>[0]["pictogram"];
}) {
  const open = useFoldOpen(id);
  return (
    <HomeDivider
      open={open}
      onToggle={() => setFoldOpen(id, !open)}
      what={what}
      {...(name === undefined ? {} : { name })}
      {...(pictogram === undefined ? {} : { pictogram })}
      // `--home-fill` es cosa de la rejilla de «Inicio»: aquí no se mide.
      fill={false}
    />
  );
}

/** Un panel secundario: se pinta solo si la raya `id` está desplegada. */
export function Folded({ id, children }: { id: string; children: ReactNode }) {
  return useFoldOpen(id) ? <>{children}</> : null;
}
