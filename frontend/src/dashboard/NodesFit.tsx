/**
 * «Ajustar a pantalla» de «Distancia y nodos»: la pestaña entera se encoge hasta caber en la
 * ventana, como la maqueta de la ISS (lote «reservas», 2026-11-14).
 *
 * Por qué existe: con la letra mínima de 0,875 rem (NASA-STD-3001 Vol 2, legibilidad; la vigilan las
 * pruebas de cada hoja) la pestaña mide el doble de la ventana. El usuario eligió escalarla
 * (2026-11-14, «un diseño responsivo que en este caso entre ahí»), sabiendo que así la letra queda
 * por debajo de esa regla. Es una desviación declarada (`compliance/hmi-state-of-the-art.md`) y
 * acotada:
 *   * Solo con la rejilla ancha (≥ 1401 px, la de la maqueta); por debajo las columnas se apilan, ni
 *     encogida cabría, y la pestaña se desplaza con su letra de siempre.
 *   * Un interruptor la pone y la quita, y la elección se guarda en este equipo (`emma.nodes.fit`).
 *     Viene puesto: a 0,9 la letra se lee (estuvo quitado unas horas del 2026-11-15, cuando a 0,8
 *     «se siguen viendo enanas»).
 *   * No encoge por debajo de `FIT_MIN`: si ni así cabe, lo que sobra se desplaza.
 *   * Las hojas no cambian: sus tamaños siguen cumpliendo la regla y sus pruebas siguen valiendo;
 *     lo que cambia es el `zoom` de la rejilla, que este componente pone y quita.
 *
 * Con `zoom` la rejilla ocupa menos ancho; para que siga llenando la fila se le da un ancho, en
 * píxeles, del de su contenedor entre el zoom, y como entonces caben más cosas por línea y la altura cambia, el factor se recalcula
 * unas pocas veces hasta que se estabiliza.
 */
import { useEffect, useRef, useState } from "react";

import { Command } from "../components/Command";
import { type PreferenceStore, browserStore } from "../components/displayModes";
import { tr } from "../lib/i18n";

export const NODES_FIT_KEY = "emma.nodes.fit";
/**
 * El menor factor: 0,9 deja la letra de 14 px en unos 12,6 px. Empezó en 0,5 (unos 8 px) y el
 * usuario lo vio: «las letras se ven muy pequeñas»; a 0,8, «se siguen viendo enanas» (2026-11-15).
 * Eligió 0,9: lo que no quepa así queda a un poco de desplazamiento.
 */
export const FIT_MIN = 0.9;
/** Desde este ancho de ventana se ajusta; por debajo, la rejilla ya apila las columnas. */
export const FIT_FROM_WIDTH = 1401;
const BOTTOM_MARGIN_PX = 12;

export function readNodesFit(store: PreferenceStore | null): boolean {
  try {
    return store?.getItem(NODES_FIT_KEY) !== "false";
  } catch {
    return true;
  }
}

export function writeNodesFit(store: PreferenceStore | null, on: boolean): void {
  try {
    store?.setItem(NODES_FIT_KEY, on ? "true" : "false");
  } catch {
    // Sin almacenamiento, la elección dura lo que la página.
  }
}

/**
 * El siguiente factor: el alto libre entre el alto natural (a zoom 1), entre `FIT_MIN` y 1.
 * `measured` es el alto que se ve con el zoom `zoom` puesto.
 */
export function nextZoom(available: number, measured: number, zoom: number): number {
  if (measured <= 0 || available <= 0) return 1;
  const natural = measured / zoom;
  return Math.min(1, Math.max(FIT_MIN, available / natural));
}

function clear(board: HTMLElement) {
  board.style.removeProperty("zoom");
  board.style.removeProperty("width");
  delete board.dataset.fit;
}

export function NodesFit({ active, fixed = false }: { active: boolean; fixed?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const [stored, setOn] = useState(() => readNodesFit(browserStore()));
  // `fixed`: siempre ajustada y sin interruptor («Aislamiento», 2026-11-15: «el botón ajustar a
  // pantalla no lo queremos»). La preferencia guardada es la de «Distancia y nodos» y no la toca.
  const on = fixed || stored;

  useEffect(() => {
    const board = ref.current?.closest<HTMLElement>(".section-body");
    if (!board) return;
    if (!on || !active) {
      clear(board);
      return;
    }
    let frame = 0;
    const fit = () => {
      frame = 0;
      if (window.innerWidth < FIT_FROM_WIDTH || board.offsetParent === null) {
        clear(board);
        return;
      }
      board.dataset.fit = "true";
      let zoom = Number(board.style.zoom) || 1;
      for (let pass = 0; pass < 5; pass += 1) {
        const rect = board.getBoundingClientRect();
        const available = window.innerHeight - rect.top - BOTTOM_MARGIN_PX;
        const next = nextZoom(available, rect.height, zoom);
        if (Math.abs(next - zoom) < 0.004) break;
        zoom = next;
        board.style.zoom = String(zoom);
        // En píxeles: un ancho en % no lo escala el zoom y la rejilla se saldría por la derecha.
        const room = board.parentElement?.clientWidth ?? 0;
        board.style.width = zoom === 1 || room === 0 ? "" : `${room / zoom}px`;
      }
    };
    const schedule = () => {
      if (frame === 0) frame = window.requestAnimationFrame(fit);
    };
    fit();
    window.addEventListener("resize", schedule);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(schedule);
    observer?.observe(board);
    return () => {
      if (frame !== 0) window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", schedule);
      observer?.disconnect();
      clear(board);
    };
  }, [on, active]);

  if (fixed) return <div ref={ref} className="nodes-fit" hidden />;
  return (
    <div ref={ref} className="nodes-fit">
      <Command
        pictogram="monitor-grid"
        type="button"
        aria-pressed={on}
        title={
          on
            ? tr(
                "La pestaña se encoge para caber en la ventana; la letra queda más pequeña que la regla de legibilidad",
                "The tab shrinks to fit the window; the text ends up smaller than the legibility rule",
              )
            : tr("La pestaña con su letra de siempre; se desplaza", "The tab at its usual text size; it scrolls")
        }
        onClick={() => {
          writeNodesFit(browserStore(), !on);
          setOn(!on);
        }}
      >
        <span>{tr("Ajustar a pantalla", "Fit to screen")}</span>
      </Command>
    </div>
  );
}
