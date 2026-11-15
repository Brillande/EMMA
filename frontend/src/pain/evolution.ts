/**
 * Evolucion del dolor por zona a lo largo de los informes.
 *
 * Cada informe es una foto del cuerpo entero: una zona que no aparece en un informe no duele
 * en ese momento (0), no "falta el dato". Por eso la serie de una zona empieza en el primer
 * informe que la marca y sigue con 0 en los que no la marcan. Lo que no hay es informe: entre
 * dos informes no se sabe nada, y no se rellena.
 *
 * Informa, no alerta. El cambio se muestra con palabras y colores neutros ("sube", "baja"):
 * la intensidad de una zona no genera alertas por si sola, y pintarla de rojo o amarillo
 * seria una alerta sin validar (invariante 5). Mismo criterio que `imaging/evolution.ts`.
 */

import type { PainReport } from "../lib/api";

export type Change = "sube" | "baja" | "igual" | "nueva";

export interface ZoneEvolution {
  zone: string;
  /** Intensidad en cada informe desde el primero que marco la zona. */
  series: { effective: string; intensity: number }[];
  latest: number;
  previous: number | null;
  change: Change;
}

/** Zonas marcadas alguna vez, de la mas intensa ahora a la menos. */
export function evolution(reports: readonly PainReport[]): ZoneEvolution[] {
  const ordered = [...reports].sort(
    (a, b) => Date.parse(a.effective) - Date.parse(b.effective),
  );
  const series = new Map<string, { effective: string; intensity: number }[]>();
  for (const report of ordered) {
    const marked = new Map(report.zones.map((item) => [item.zone, item.intensity]));
    for (const zone of marked.keys()) if (!series.has(zone)) series.set(zone, []);
    for (const [zone, points] of series) {
      points.push({ effective: report.effective, intensity: marked.get(zone) ?? 0 });
    }
  }
  const result: ZoneEvolution[] = [];
  for (const [zone, points] of series) {
    const latest = points[points.length - 1]?.intensity ?? 0;
    const previous = points.length > 1 ? (points[points.length - 2]?.intensity ?? null) : null;
    result.push({ zone, series: points, latest, previous, change: changeOf(latest, previous) });
  }
  return result.sort((a, b) => b.latest - a.latest || a.zone.localeCompare(b.zone));
}

function changeOf(latest: number, previous: number | null): Change {
  if (previous === null) return "nueva";
  if (latest > previous) return "sube";
  if (latest < previous) return "baja";
  return "igual";
}
