import type {
  ContrastPhaseComparison,
  ContrastPhaseDeclaration,
  ContrastPhaseView,
  ContrastPhaseVocabulary,
} from "../lib/api";
import { formatUtc } from "../lib/format";

/**
 * La fase de contraste de un TAC, declarada por una persona (backend `volumes/contrast_phase.py`).
 *
 * Por que existe aparte del panel: lo que se ensena tiene cuatro casos que no se pueden confundir
 * (F.5-1), y la regla de cual es cual merece su prueba. La fase no aplica (el estudio no es un
 * TAC: gris, no disponible), nadie la ha declarado (cian, dato ausente), una persona declaro una
 * fase, o una persona declaro que no se sabe. Aqui no se redacta nada: el nombre de cada fase, el
 * de "sin declarar", el rotulo y los textos de la comparacion son del backend. La interfaz no
 * propone ninguna fase: el selector empieza vacio.
 */
export type PhaseShown =
  | { kind: "no-aplica"; reason: string | null }
  | { kind: "sin-declarar"; display: string; label: string }
  | { kind: "declarada"; declaration: ContrastPhaseDeclaration; label: string; earlier: ContrastPhaseDeclaration[] };

/** Lo que consta de la fase de un estudio; `null` si el backend no lo dice (un backend anterior). */
export function phaseShown(study: { contrast_phase?: ContrastPhaseView | null }): PhaseShown | null {
  const view = study.contrast_phase ?? null;
  if (view === null) return null;
  if (!view.applicable) return { kind: "no-aplica", reason: view.not_applicable_reason };
  if (view.current === null) return { kind: "sin-declarar", display: view.undeclared_display, label: view.label };
  return {
    kind: "declarada",
    declaration: view.current,
    label: view.label,
    // Las anteriores, de la mas reciente a la mas antigua; la vigente no se repite.
    earlier: view.history.filter((item) => item.ledger_index !== view.current?.ledger_index).reverse(),
  };
}

/**
 * Quien la declaro y cuando se firmo. El instante es el del asiento (`recorded`), que el backend
 * da en UTC: es la hora del ordenador que firmo, no un instante de la mision (F.6.1).
 */
export function declaredBy(declaration: ContrastPhaseDeclaration): string {
  return `${declaration.declared_by} · ${formatUtc(new Date(declaration.recorded))}`;
}

/**
 * Si se puede enviar una declaracion: la fase tiene que ser una del vocabulario del backend y
 * quien declara tiene que haber puesto su nombre. Es lo mismo que exige el backend (422); aqui
 * solo evita un boton que acabaria en ese rechazo.
 */
export function canDeclare(
  shown: PhaseShown | null,
  vocabulary: ContrastPhaseVocabulary | null,
  code: string,
  operator: string,
): boolean {
  if (shown === null || shown.kind === "no-aplica" || vocabulary === null) return false;
  return operator.trim() !== "" && vocabulary.phases.some((phase) => phase.code === code);
}

/**
 * Un lado de la comparacion: la fase que consta, o que no consta ninguna. El codigo viaja con la
 * palabra para que el panel le ponga el dibujo de la fase (`marks.ts`).
 */
export type PhaseSide =
  | { kind: "declarada"; code: string; display: string; declaredBy: string }
  | { kind: "sin-declarar"; display: string };

/**
 * Con que significado se pinta lo que el backend dice de las dos fases. `igual`: constan y son la
 * misma (sin color: no es un estado ni un visto bueno). `no-aplica`: algun estudio no es un TAC
 * (gris). Todo lo demas —fases distintas, falta alguna, o un estado que esta interfaz no conoce—
 * es `atencion` (amarillo): un estado desconocido no se rebaja a "igual".
 */
export type PhaseTone = "igual" | "atencion" | "no-aplica";

export interface PhaseComparisonShown {
  tone: PhaseTone;
  texto: string;
  antes: PhaseSide;
  despues: PhaseSide;
}

/** Lo que la comparacion de dos estudios dice de sus fases; `null` si el backend no lo da. */
export function comparisonPhase(comparison: object): PhaseComparisonShown | null {
  const block = (comparison as { fase_contraste?: ContrastPhaseComparison | null }).fase_contraste ?? null;
  if (block === null) return null;
  const side = (declaration: ContrastPhaseDeclaration | null): PhaseSide =>
    declaration === null
      ? { kind: "sin-declarar", display: block.sin_declarar }
      : {
          kind: "declarada",
          code: declaration.code,
          display: declaration.display,
          declaredBy: declaration.declared_by,
        };
  const tone: PhaseTone =
    block.estado === "same" ? "igual" : block.estado === "not-applicable" ? "no-aplica" : "atencion";
  return { tone, texto: block.texto, antes: side(block.antes), despues: side(block.despues) };
}
