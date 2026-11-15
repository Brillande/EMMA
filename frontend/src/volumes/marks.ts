/**
 * Las marcas (pictograma y color) de los estados que ensenan los paneles de volumenes.
 *
 * Por que existe: `VolumesPanel`, `LesionComparison` y `ContrastPhasePanel` tenian cada uno su
 * tabla de glifos de texto (△ ◌ ◇) y resolvian el mismo significado por separado. Aqui esta una
 * vez cada uno, con la forma unica de `lib/marks.ts`, y con el significado de la tabla F.5-1 que
 * ya tenia su color: amarillo con triangulo para lo que requiere atencion, cian con anillo
 * punteado para el dato ausente, gris con circulo tachado para lo no disponible (o que no aplica
 * a este estudio). La palabra sigue siendo la del backend o el rotulo que ya existia, y va al lado.
 *
 * Lo que es procedencia y no estado va sin color: la modalidad del estudio, la fase de contraste
 * que una persona declaro, dos fases que coinciden, la cabecera limpiada al entrar. Un codigo
 * que esta interfaz no conoce (una fase o una modalidad nuevas del backend) se ensena con su
 * palabra y la marca de «desconocido», sin suponerle un dibujo.
 */

import type { SpineNoticeLevel } from "../lib/api";
import { type StateMark, MISSING_MARK, UNAVAILABLE_MARK, UNKNOWN_MARK, mark } from "../lib/marks";
import type { PhaseTone } from "./contrastPhase";

export const ATTENTION_MARK: StateMark = mark("shape-triangle", "yellow");
/** No disponible: la de toda la interfaz (`lib/marks.ts`), reexportada para los paneles de aquí. */
export { UNAVAILABLE_MARK };
/** La cabecera del NIfTI que EMMA vacio al entrar (§5.25): procedencia, sin color. */
export const CLEANED_MARK: StateMark = mark("eraser", null);

const MODALITY_MARKS: Readonly<Record<string, StateMark>> = {
  CT: mark("gantry", null),
  MR: mark("magnet", null),
};

export function modalityMark(modality: string): StateMark {
  return MODALITY_MARKS[modality] ?? UNKNOWN_MARK;
}

/** Una fase del vocabulario cerrado del backend (`volumes/contrast_phase.py`), por su codigo. */
const PHASE_MARKS: Readonly<Record<string, StateMark>> = {
  "non-contrast": mark("drop-slash", null),
  arterial: mark("tube-wave", null),
  "portal-venous": mark("branches", null),
  delayed: mark("hourglass", null),
  unknown: mark("question", null),
};

/** Los codigos de fase con dibujo propio, en el orden del vocabulario. */
export const KNOWN_PHASES: readonly string[] = Object.keys(PHASE_MARKS);

export function phaseMark(code: string): StateMark {
  return PHASE_MARKS[code] ?? UNKNOWN_MARK;
}

/**
 * Lo que el backend dice de las fases de dos estudios: constan y coinciden (igual, sin color: no
 * es un visto bueno), piden atencion (distintas, falta alguna o un estado desconocido), o no
 * aplica a alguno de los dos.
 */
export const PHASE_TONE_MARK: Readonly<Record<PhaseTone, StateMark>> = {
  igual: mark("equals", null),
  atencion: ATTENTION_MARK,
  "no-aplica": UNAVAILABLE_MARK,
};

/**
 * El nivel de un aviso del control de la cadena vertebral, que declara el backend con su
 * significado de F.5-1. Un nivel que esta interfaz no conoce no se rebaja a dato ausente: se
 * pinta como atencion.
 */
export function spineNoticeMark(level: SpineNoticeLevel | string): StateMark {
  return level === "dato_ausente" ? MISSING_MARK : ATTENTION_MARK;
}
