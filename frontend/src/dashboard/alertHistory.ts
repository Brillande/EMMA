/**
 * Como se presenta la historia recalculada de las alertas (`app/analysis/alert_history.py`).
 *
 * Existe para que la cronica no confunda tres cosas que no son lo mismo: lo que alguien firmo,
 * lo que dice el estado de ahora, y lo que se ha vuelto a calcular hoy con las reglas de hoy.
 * Lo recalculado NO es lo que el sistema enseño entonces, asi que no puede llevar la insignia
 * de una alerta activa (color, pictograma de nivel, parpadeo): lleva un pictograma propio y el
 * color del texto secundario, y su rotulo y sus limites, que redacta el backend, van siempre a la
 * vista. Aqui no se escribe ninguna palabra de nivel: se pinta la que llega.
 */

import type { PictogramName } from "../icons/registry";
import type { AlertHistory, AlertHistoryEpisode, ChronicleEvent } from "../lib/api";

/**
 * Forma propia de lo recalculado: la señal que no depende del color (F.5.10 e). La flecha que
 * vuelve sobre si misma (antes el caracter ↺), que no es la de ningun nivel ni la de dato ausente.
 */
export const RECOMPUTED_PICTOGRAM: PictogramName = "refresh";

export type EventMark = "recomputed" | "level" | "health" | "performance" | "target" | null;

/**
 * Que señal lleva un hecho de la cronica. Lo recalculado gana a todo: aunque llegara con un
 * nivel, no se pinta con la insignia de una alerta activa.
 */
export function eventMark(
  event: Pick<ChronicleEvent, "recomputed" | "level" | "severity">,
): EventMark {
  if (event.recomputed) return "recomputed";
  if (event.level !== null) return "level";
  return event.severity;
}

/** Los episodios, lo ultimo arriba. Los que siguen abiertos son las alertas activas de ahora. */
export function episodeRows(history: Pick<AlertHistory, "episodes">): AlertHistoryEpisode[] {
  return [...history.episodes].sort(
    (a, b) =>
      new Date(b.last_step_end).getTime() - new Date(a.last_step_end).getTime() ||
      a.domain.localeCompare(b.domain),
  );
}

export function closedCount(history: Pick<AlertHistory, "episodes">): number {
  return history.episodes.filter((episode) => !episode.open).length;
}

/**
 * Lo que la interfaz tiene que enseñar SIEMPRE junto a la historia, en este orden: hasta donde
 * llega el recalculo (y lo que quedo sin mirar) y despues lo que es y lo que no es. Texto del
 * backend, sin tocar. Si faltara (`null`), la historia no se pinta: sin su rotulo de limites
 * pasaria por historia registrada.
 */
export function historyNotes(
  history: Pick<AlertHistory, "coverage" | "basis">,
): string[] | null {
  const basis = history.basis.filter((text) => text.trim() !== "");
  if (history.coverage.trim() === "" || basis.length === 0) return null;
  return [history.coverage, ...basis];
}
