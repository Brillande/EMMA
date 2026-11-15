/**
 * Como se presenta el perfil de mision declarado (`app/evidence/mission_profiles.py`).
 *
 * Existe para que el panel no decida nada: cada frase la da el backend, y aqui solo se fija con
 * que señal se pinta lo que falta. La tabla F.5-1 de NASA-STD-3001 Vol 2 reserva el cian para
 * "Missing or stale data": un aspecto «sin verificar» es un dato que no se tiene, y lleva su
 * pictograma ademas del color (F.5.10 e). Un perfil que no casaba con el cuerpo de las efemerides
 * era una precaucion sobre la configuracion (ambar); desde el 2026-11-11 el perfil decide ese
 * cuerpo y el estado ya no se da. Un perfil sin objetivo lleva su frase sin señal.
 *
 * La conjuncion solar (`environment/conjunction.py`) sigue la misma regla: dentro del umbral leido
 * es una precaucion sobre el enlace con Tierra (ambar con su triangulo, como un sistema degradado:
 * solo se dice); fuera, la frase sin señal; sin efemerides, sin elongacion guardada o sin umbral
 * leido para ese objetivo, un dato que no se tiene (cian con su anillo punteado).
 *
 * El perfil es descriptivo: nada de aqui toca niveles ni alertas, que no pasan por este fichero.
 */

import type { EphemerisCoverage, EphemerisCoverageState, MissionProfile, ProfileAspect, SolarConjunctionState } from "../lib/api";
import { type StateMark, MISSING_MARK, UNAVAILABLE_MARK, mark } from "../lib/marks";
import { tr } from "../lib/i18n";

const PRESENT: StateMark = mark(null, null);
/** El mismo que usa el estado «degradado» de los sistemas del habitat. */
const CAUTION: StateMark = mark("shape-triangle", "yellow");

/** Un perfil que el backend no reconoce es un dato ausente: su frase, con esa señal. */
export const UNKNOWN_PROFILE_MARK: StateMark = MISSING_MARK;

const ASPECT_STYLES: Record<ProfileAspect["status"], StateMark> = {
  read: PRESENT,
  unverified: MISSING_MARK,
};

/*
 * Desde el 2026-11-11 el perfil decide el objetivo de efemerides (`mission_profiles.ephemeris_target`)
 * y el backend ya no da «mismatch» ni «unchecked»; se dejan para no tumbar una vista con un backend
 * anterior. «no_target» (un perfil sin objetivo: el retardo no se calcula) no es un fallo ni un dato
 * que falte: la frase del backend, sin señal. Va aqui, y no en `lib/api.ts`, porque ese fichero lo
 * esta editando otra sesion; al volver a el, `ProfileEphemerisState` debe añadirlo.
 */
type EphemerisState = NonNullable<MissionProfile["ephemeris"]>["state"] | "no_target";

const EPHEMERIS_STYLES: Record<EphemerisState, StateMark> = {
  consistent: PRESENT,
  no_target: PRESENT,
  mismatch: CAUTION,
  unchecked: MISSING_MARK,
};

/** Un estado que la interfaz no conoce no se pinta como "leido en la fuente": se dice. */
export function aspectStyle(status: string): StateMark {
  if (!(status in ASPECT_STYLES)) throw new RangeError(`estado de aspecto desconocido: ${status}`);
  return ASPECT_STYLES[status as ProfileAspect["status"]];
}

/**
 * Para pintar sin tumbar la vista: un estado que la interfaz no conoce no se pinta como leído ni
 * rompe la pestaña entera (§5.40), queda «no disponible» (gris con el círculo tachado, tabla F.5-1)
 * y el panel dice el estado tal cual llegó. `aspectStyle` sigue fallando: el contrato es suyo.
 */
export function aspectDisplay(status: string): { mark: StateMark; known: boolean } {
  return Object.hasOwn(ASPECT_STYLES, status)
    ? { mark: aspectStyle(status), known: true }
    : { mark: UNAVAILABLE_MARK, known: false };
}

export function ephemerisStyle(state: string): StateMark {
  if (!(state in EPHEMERIS_STYLES)) {
    throw new RangeError(`estado de efemerides desconocido: ${state}`);
  }
  return EPHEMERIS_STYLES[state as keyof typeof EPHEMERIS_STYLES];
}

const CONJUNCTION_STYLES: Record<SolarConjunctionState, StateMark> = {
  within: CAUTION,
  clear: PRESENT,
  no_threshold: MISSING_MARK,
  not_recorded: MISSING_MARK,
  no_ephemeris: MISSING_MARK,
};

export function conjunctionStyle(state: string): StateMark {
  if (!(state in CONJUNCTION_STYLES)) {
    throw new RangeError(`estado de conjuncion desconocido: ${state}`);
  }
  return CONJUNCTION_STYLES[state as SolarConjunctionState];
}

/*
 * La cobertura de efemerides de la mision (`environment/ephemeris_coverage.py`, §5.37.18): con todos
 * los dias en cache, la frase sin señal; si falta alguno, un dato que no se tiene (cian con su
 * anillo punteado, F.5-1 "Missing or stale data"), porque sin red esos dias el retardo y la
 * conjuncion salen sin dato. No es una precaucion en amarillo: no ha fallado nada, falta precargar.
 */
const COVERAGE_STYLES: Record<EphemerisCoverageState, StateMark> = {
  complete: PRESENT,
  partial: MISSING_MARK,
  none: MISSING_MARK,
};

export function coverageStyle(state: string): StateMark {
  if (!(state in COVERAGE_STYLES)) {
    throw new RangeError(`estado de cobertura de efemerides desconocido: ${state}`);
  }
  return COVERAGE_STYLES[state as EphemerisCoverageState];
}

/**
 * Lo que vale con la red cortada, sumando el cálculo local (SPICE) y la caché de Horizons
 * (2026-11-11). Con SPICE primero, `state` y `day.covered` de la cobertura siguen siendo los de la
 * caché de Horizons, y pintarlos en cian decía «sin efemérides» de días que SPICE calcula. El
 * backend da ahora `offline_state`, `offline_covered_days` y, del día del estado, `offline_covered`
 * y su frase (`served_text`); con un backend anterior, lo de la caché, como antes. Los campos se
 * leen aquí y no en `lib/api.ts` porque ese fichero lo edita otra sesión.
 */
type Run = EphemerisCoverage["missing"][number];
type OfflineFields = {
  offline_state?: string;
  offline_covered_days?: number;
  offline_missing?: Run[];
  day: EphemerisCoverage["day"] & { offline_covered?: boolean; served_text?: string };
};

export function offlineCoverage(coverage: EphemerisCoverage): {
  offline: boolean;
  state: string;
  covered: number;
  dayCovered: boolean;
  dayText: string | null;
  /** Los tramos sin ninguna de las dos fuentes (`offline_missing`); sin el dato, los sin caché. */
  missing: Run[];
} {
  const given = coverage as EphemerisCoverage & OfflineFields;
  if (given.offline_state === undefined || given.offline_covered_days === undefined) {
    return {
      offline: false,
      state: coverage.state,
      covered: coverage.covered_days,
      dayCovered: coverage.day.covered,
      dayText: null,
      missing: coverage.missing,
    };
  }
  return {
    offline: true,
    state: given.offline_state,
    covered: given.offline_covered_days,
    dayCovered: given.day.offline_covered ?? coverage.day.covered,
    dayText: given.day.served_text ?? null,
    missing: given.offline_missing ?? [],
  };
}

/** Un dia o un tramo de dias: en cache, sin señal; sin su efemeride, el mismo dato ausente. */
export function cachedStyle(covered: boolean): StateMark {
  return covered ? PRESENT : MISSING_MARK;
}

/**
 * Las cifras de las efemérides (distancia y retardo) junto a un perfil de «Rutas espaciales» de
 * «Inicio» (lógica 6). Antes salían sin señal siempre que el perfil fuera el declarado y hubiera
 * efemérides, y eso contradecía dos cosas que la consola ya dice en otro sitio:
 * - con el perfil y las efemérides que no casan (`ephemeris.state = "mismatch"`: el perfil
 *   declara un cuerpo y el tiempo de luz se calcula hacia otro), la distancia y el retardo de otro cuerpo se leían como los del
 *   perfil; ahora va la precaución en ámbar con la palabra de la línea temporal
 *   (`MissionWarnings`), y no la cifra;
 * - con las efemérides caducadas, la franja y el resumen pintan la cifra en cian con el anillo
 *   punteado (tabla F.5-1) y aquí iba limpia; ahora va igual (`stale`).
 * Desde el 2026-11-11, un perfil sin objetivo de efemérides (`ephemeris.state = "no_target"`) no
 * tiene cifras que enseñar y no es que falten: gris «no disponible» (F.5-1) con su palabra, no el
 * cian de «sin efemérides».
 */
export type RouteFigures = { kind: "absent"; mark: StateMark; word: string } | { kind: "shown"; stale: boolean };

export function routeFigures(
  declared: boolean,
  hasComms: boolean,
  freshness: "fresh" | "stale" | "missing",
  ephemerisState: string | null | undefined,
): RouteFigures {
  if (!declared) return { kind: "absent", mark: MISSING_MARK, word: tr("solo del perfil declarado", "declared profile only") };
  if (ephemerisState === "no_target") {
    return { kind: "absent", mark: UNAVAILABLE_MARK, word: tr("sin objetivo de efemérides", "no ephemeris target") };
  }
  if (!hasComms) return { kind: "absent", mark: MISSING_MARK, word: tr("sin efemérides", "no ephemeris") };
  if (ephemerisState === "mismatch") {
    return { kind: "absent", mark: ephemerisStyle("mismatch"), word: tr("perfil y efemérides no casan", "profile and ephemeris do not match") };
  }
  return { kind: "shown", stale: freshness !== "fresh" };
}
