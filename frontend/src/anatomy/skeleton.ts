import {
  type PainOnSubjectSkeleton,
  SKELETON_IMAGE_URL,
  type SubjectSkeleton,
} from "../lib/api";
import { tr } from "../lib/i18n";
import { type StateMark, MISSING_MARK, mark } from "../lib/marks";

/**
 * Logica de la figura del esqueleto, fuera del componente para poder probarla.
 *
 * Por que existe: desde que la figura puede salir del TAC del tripulante hay DOS esqueletos con
 * el mismo contrato, y dos peticiones (la figura y el dolor colocado sobre ella) que llegan por
 * separado. Si entre una y otra se registra un TAC, las marcas de una figura se pintarian sobre
 * la otra, y un esqueleto es lo bastante simetrico para que no se note. Aqui se decide que imagen
 * corresponde a la respuesta y si las marcas son de ESA figura; lo demas es texto del backend.
 */

/** La imagen que corresponde a esa respuesta: la del asiento de su segmentacion, o la de referencia. */
export function skeletonImageUrl(skeleton: SubjectSkeleton): string {
  if (skeleton.source === "own-ct" && skeleton.ledger !== null) {
    return `/api/anatomy/skeleton/own/${skeleton.ledger.segmentation_index}.png`;
  }
  return SKELETON_IMAGE_URL;
}

/** El dolor se coloco sobre esta misma figura (misma fuente y, si es un TAC, mismo asiento). */
export function painIsOnThisFigure(
  skeleton: SubjectSkeleton,
  pain: PainOnSubjectSkeleton,
): boolean {
  const index = skeleton.source === "own-ct" ? (skeleton.ledger?.segmentation_index ?? null) : null;
  return pain.source === skeleton.source && pain.segmentation_index === index;
}

/** La marca de un estado con la palabra que lo nombra. */
export interface SourceMark extends StateMark {
  readonly word: string;
}

/**
 * De donde sale la figura, con pictograma y palabra ademas de color (F.5.10 e). Que sea el TAC o
 * la referencia no es una alerta: va sin color, con el marco lleno (imagen propia) o el marco
 * vacio (figura de referencia), como el alcance de lectura en el resto de la consola. Lo que si
 * tiene significado en la tabla F.5-1 es por que NO se ve el del tripulante: no tiene (dato
 * ausente, anillo punteado cian) o no se puede usar (no disponible, cruz gris).
 */
export function sourceTone(skeleton: SubjectSkeleton): SourceMark {
  if (skeleton.source === "own-ct") {
    return {
      ...mark("frame-filled", null),
      word: skeleton.simulated ? tr("TAC de ejemplo", "Sample CT") : tr("TAC del tripulante", "Crew member's CT"),
    };
  }
  if (skeleton.fallback_kind === "no-segmentation") {
    return { ...MISSING_MARK, word: tr("Referencia", "Reference") };
  }
  if (skeleton.fallback_kind === "not-usable") {
    return { ...mark("cross", "gray"), word: tr("Referencia", "Reference") };
  }
  return { ...mark("frame-empty", null), word: tr("Referencia", "Reference") };
}

/**
 * Color y pictograma de un aviso del control de la segmentacion (backend `volumes/spine.py`),
 * como en el panel de volumenes: un nivel que esta interfaz no conoce no se rebaja a dato
 * ausente, se ensena como atencion.
 */
export function noticeTone(level: string): StateMark {
  return level === "dato_ausente" ? MISSING_MARK : mark("shape-triangle", "yellow");
}
