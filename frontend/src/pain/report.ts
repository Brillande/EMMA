/**
 * Formulario de un informe de dolor: que zonas, cuanto y como.
 *
 * Una zona marcada no tiene intensidad por defecto: el tripulante la elige. Un valor
 * precargado se enviaria sin que nadie lo hubiera dicho, y un dolor de 5 que nadie informo
 * pasaria al analisis. El formulario no se envia mientras falte una intensidad; el backend
 * lo exige igual. "Sin dolor" es un informe sin zonas, no un formulario vacio.
 */

export interface ZoneEntry {
  zone: string;
  intensity: number | null;
  characters: string[];
}

/** En el orden en que se marcaron: asi se leen en la lista. */
export type PainForm = ZoneEntry[];

export const INTENSITIES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] as const;

/** Marca la zona, o la desmarca si ya estaba. Un segundo clic en el mismo sitio la quita. */
export function toggleZone(form: PainForm, zone: string): PainForm {
  return form.some((entry) => entry.zone === zone)
    ? form.filter((entry) => entry.zone !== zone)
    : [...form, { zone, intensity: null, characters: [] }];
}

export function withIntensity(form: PainForm, zone: string, intensity: number): PainForm {
  return form.map((entry) => (entry.zone === zone ? { ...entry, intensity } : entry));
}

export function toggleCharacter(form: PainForm, zone: string, character: string): PainForm {
  return form.map((entry) =>
    entry.zone !== zone
      ? entry
      : {
          ...entry,
          characters: entry.characters.includes(character)
            ? entry.characters.filter((item) => item !== character)
            : [...entry.characters, character],
        },
  );
}

export function missingIntensities(form: PainForm): number {
  return form.filter((entry) => entry.intensity === null).length;
}

export interface PainReportBody {
  zones: { zone: string; intensity: number; characters: string[] }[];
  reported_by: string;
}

/** Lo que se envia. `null` si falta algo: no se envia un informe a medias. */
export function toBody(form: PainForm, reportedBy: string): PainReportBody | null {
  const who = reportedBy.trim();
  if (who === "" || missingIntensities(form) > 0) return null;
  return {
    zones: form.map((entry) => ({
      zone: entry.zone,
      intensity: entry.intensity ?? 0,
      characters: entry.characters,
    })),
    reported_by: who,
  };
}
