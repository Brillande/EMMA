import { Mark, MarkOf } from "../components/Mark";
import type { CrewLocation, LocationState } from "../lib/api";
import { formatAge } from "../lib/format";
import { tr } from "../lib/i18n";
import { INDETERMINATE_MARK, MISSING_MARK, type StateMark, UNAVAILABLE_MARK, UNKNOWN_MARK } from "../lib/marks";
import { OBSERVATION_TYPES } from "../lib/provenance";
import { uiPictogram } from "../lib/uiMarks";
import { modulePictogram } from "./pictograms";

/**
 * La sububicación de un tripulante, igual en los tres sitios donde se pinta (Inicio, la tripulación
 * del hábitat y la radiación de la tripulación).
 *
 * Por qué existe: la ubicación dejó de ser simulada (2026-11-10, «no las queremos simuladas, las
 * queremos reales»). Ahora sale de dos sitios que no valen lo mismo: lo que declara una persona en la
 * consola, que manda, y lo que estiman las anclas de módulo de la nave a partir de lo que oye el
 * wearable, que es una inferencia por intensidad de señal sin respaldo en un módulo metálico. Una
 * estimada no puede pasar por declarada: lleva la palabra «estimada», el dibujo de lo INFERIDO
 * (`lib/provenance.ts`, el mismo de un dato calculado por un modelo) y su antigüedad frente a la
 * referencia; cuando el backend la da por caducada, el cian y la cursiva de dato caducado (F.5-1).
 *
 * Sin ubicación, la marca la decide `location_state` y el texto es el del backend:
 * - `unavailable` (no hay anclas declaradas, no se puede medir): gris, «no disponible»;
 * - `missing` y `stale`: cian, dato ausente o caducado;
 * - `ambiguous` (dos módulos compiten): la interrogación de lo indeterminado, sin color.
 * Un estado que no llegue (un backend anterior en `/crew`) se pinta como ausente, que es lo que era.
 */

/** La marca de una ubicación que no hay, por lo que el backend sabe de ella. */
export function locationAbsentMark(state: LocationState | undefined): StateMark {
  if (state === "unavailable") return UNAVAILABLE_MARK;
  if (state === "ambiguous") return INDETERMINATE_MARK;
  return MISSING_MARK;
}

/** Minutos desde la última lectura de anclas hasta la referencia; `null` si no hay lectura. */
export function locationAgeMinutes(location: Pick<CrewLocation, "last_seen">, reference: string): number | null {
  if (location.last_seen == null) return null;
  const minutes = (Date.parse(reference) - Date.parse(location.last_seen)) / 60_000;
  return Number.isFinite(minutes) ? minutes : null;
}

/**
 * Quién puso la ubicación: «declarada» (la consola, con el dibujo de declarar) o «estimada · hace
 * N min» (las anclas). La caducada va en cian y en cursiva.
 */
export function LocationSource({
  location,
  state,
  reference,
}: {
  location: Pick<CrewLocation, "source" | "last_seen">;
  state: LocationState | undefined;
  /** El instante de referencia de los datos: la antigüedad se cuenta desde ahí, no desde el reloj. */
  reference: string;
}) {
  if (location.source === "console") {
    return <Mark pictogram={uiPictogram("declare")}>{tr("declarada", "declared")}</Mark>;
  }
  if (location.source !== "anchors") {
    // Una fuente que la interfaz no conoce (un backend anterior que aún dice `simulator`): con el
    // nombre con que firmó y la marca de desconocido, nunca como estimada ni como declarada.
    return <MarkOf mark={UNKNOWN_MARK}>{String(location.source)}</MarkOf>;
  }
  const age = locationAgeMinutes(location, reference);
  const words = age === null ? tr("estimada", "estimated") : tr(`estimada · hace ${formatAge(age)}`, `estimated · ${formatAge(age)} ago`);
  if (state === "stale") {
    return (
      <MarkOf mark={MISSING_MARK} stale>
        {words}
      </MarkOf>
    );
  }
  return <Mark pictogram={OBSERVATION_TYPES.inferred.pictogram}>{words}</Mark>;
}

/**
 * La línea entera: el módulo con su dibujo y el nombre del backend, el tramo en tiempo de misión y
 * quién la puso; o, sin ubicación, la marca de su estado con el texto del backend.
 */
export function LocationLine({
  location,
  state,
  missingText,
  reference,
  met,
}: {
  location: CrewLocation | null;
  state: LocationState | undefined;
  missingText: string | null | undefined;
  reference: string;
  met: (iso: string) => string;
}) {
  if (location == null) {
    return <MarkOf mark={locationAbsentMark(state)}>{missingText ?? ""}</MarkOf>;
  }
  return (
    <>
      <Mark pictogram={modulePictogram(location.module)} stale={state === "stale"}>
        {location.display}
      </Mark>{" "}
      <span className="secondary">
        ({tr("de", "from")} <span className="num">{met(location.start)}</span> {tr("a", "to")} <span className="num">{met(location.end)}</span>)
      </span>{" "}
      <LocationSource location={location} state={state} reference={reference} />
    </>
  );
}
