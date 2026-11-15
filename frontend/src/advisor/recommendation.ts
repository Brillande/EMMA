import type { PictogramName } from "../icons/registry";
import type { Countermeasure, CountermeasureEffects, Recommendation } from "../lib/api";
import { tr } from "../lib/i18n";
import { UNKNOWN_PICTOGRAM } from "../lib/marks";

/**
 * Lo que la tarjeta de una recomendacion decide antes de pintar.
 *
 * Por que existe: la tarjeta ofrece ahora una tercera accion, «no adoptar», que exige motivo, y
 * pinta dos cosas que antes callaba (la contraindicacion y por que una entrada no lista
 * recursos). Cuando se puede firmar, que se ensena y que no son reglas con prueba, no detalles
 * del JSX. Ningun texto clinico se escribe aqui: todo lo que se muestra llega del backend.
 *
 * Tambien que pictograma acompana a cada palabra del backend (§5.32.5): la urgencia, el respaldo
 * de la contramedida y el estado de la respuesta previa. El dibujo nunca va solo ni sustituye a la
 * palabra; un valor que esta version no conoce sale con el dibujo de «desconocido».
 */

/** Urgencia: uno, dos y tres galones, con la palabra «rutina / pronto / inmediata» al lado. */
export const URGENCY_PICTOGRAMS: Record<Recommendation["urgency"], PictogramName> = {
  routine: "chevron-right",
  soon: "chevrons-right-double",
  immediate: "chevrons-right-triple",
};

export function urgencyPictogram(urgency: string): PictogramName {
  return (URGENCY_PICTOGRAMS as Record<string, PictogramName>)[urgency] ?? UNKNOWN_PICTOGRAM;
}

/**
 * Respaldo de la contramedida: una hoja con renglones si la respalda un protocolo o una fuente
 * (hay un documento), y el guion de «no aplica» si es una entrada demo, que solo la respalda el
 * riesgo del dominio (no hay documento que dibujar).
 */
export const BASIS_PICTOGRAMS: Record<Countermeasure["basis"], PictogramName> = {
  "evidence-backed": "sheet-lines",
  demo: "dash",
};

export function basisPictogram(basis: string): PictogramName {
  return (BASIS_PICTOGRAMS as Record<string, PictogramName>)[basis] ?? UNKNOWN_PICTOGRAM;
}

/**
 * Estado de la respuesta previa (`prior_response.state`): nada que contar (guion), la ultima
 * adopcion sigue abierta (en curso) o se cerro (hecho). Sin color: es historia, no un aviso.
 */
const PRIOR_PICTOGRAMS: Record<string, PictogramName> = {
  none: "dash",
  open: "refresh",
  closed: "check",
};

export function priorPictogram(state: string): PictogramName {
  return PRIOR_PICTOGRAMS[state] ?? UNKNOWN_PICTOGRAM;
}

/** El mismo tope que impone la API (`DeclineIn.reason`). */
export const DECLINE_REASON_MAX = 500;

export interface DeclineState {
  /** El formulario de «no adoptar» se ofrece. */
  offered: boolean;
  /** Se puede firmar ya. */
  ready: boolean;
  /** Que falta para poder firmar, o `null`. Texto de interfaz, no clinico. */
  missing: string | null;
}

/**
 * «No adoptar» se ofrece mientras no haya un seguimiento abierto de esa contramedida: decir que
 * no a lo que se esta siguiendo lo rechaza el backend (422), asi que no se ofrece. Firmar exige
 * quien decide y un motivo que no sea solo espacios.
 */
export function declineState(input: {
  hasHandler: boolean;
  adopted: boolean;
  operator: string;
  reason: string;
  busy: boolean;
}): DeclineState {
  if (!input.hasHandler || input.adopted) return { offered: false, ready: false, missing: null };
  const missing =
    input.operator.trim() === ""
      ? tr("Escriba quién está en consola", "Enter who is at the console")
      : input.reason.trim() === ""
        ? tr("Escriba el motivo: queda firmado con la decisión", "Enter the reason: it is signed with the decision")
        : null;
  return { offered: true, ready: missing === null && !input.busy, missing };
}

/** Los recursos, o lo que la entrada declara cuando no lista ninguno. `null`: nada que decir. */
export function resourcesLine(measure: Countermeasure): string | null {
  if (measure.resources.length > 0) return measure.resources.join(" · ");
  const note = measure.resources_note?.trim() ?? "";
  return note === "" ? null : note;
}

/**
 * La contraindicacion tal y como la da el backend: la escrita por la revision medica o, si no hay
 * ninguna, que esta pendiente. `pending` solo cambia el peso tipografico. Un backend anterior que
 * no mande el texto no hace que la interfaz lo invente: no se pinta nada.
 */
export function contraindicationsLine(
  measure: Countermeasure,
): { text: string; pending: boolean } | null {
  const text = measure.contraindications_display?.trim() ?? "";
  if (text === "") return null;
  return { text, pending: measure.contraindications_note === null };
}

/** La nota de lo decidido sobre una recomendacion, con los dos textos del backend. */
export function decisionNote(item: Recommendation): { text: string; meaning: string } | null {
  const decision = item.decision ?? null;
  if (decision === null) return null;
  return { text: decision.text, meaning: decision.meaning };
}

/** Una adopcion anterior, en las lineas que la tarjeta pinta. Todas son texto del backend. */
export interface PriorAdoptionView {
  key: number;
  lines: string[];
}

export interface PriorResponseView {
  /** El dibujo del estado de la ultima adopcion, que acompana al resumen. */
  pictogram: PictogramName;
  /** Cuantas veces y cuando la ultima, o que no hay adopciones anteriores. */
  summary: string;
  /** La ultima adopcion; `null` si no hubo ninguna. */
  last: PriorAdoptionView | null;
  /** Las anteriores a la ultima, de la mas reciente a la mas antigua. */
  earlier: PriorAdoptionView[];
  /** Con que compara la evaluacion; solo si alguna adopcion pintada trae evaluacion. */
  basis: string | null;
  /** La advertencia: lo que paso despues no prueba una causa. Va SIEMPRE con el bloque. */
  caveat: string;
}

/**
 * La respuesta previa a una contramedida, tal y como la da el backend (`prior_response`).
 *
 * Aqui solo se ordena lo que se pinta: no se cuenta cuantas veces «fue bien», no se resume ni
 * se colorea ningun resultado. Es historia, no un aviso. Si el backend manda el bloque sin su
 * advertencia no se pinta nada: la historia sin la advertencia se leeria como una prueba.
 *
 * Con que compara cada evaluacion —con el nivel que guardo el cierre o, si aquel cierre no lo
 * guardo, con el estado actual— lo dice el backend DENTRO de `evaluation_text` y de
 * `evaluation_basis`: aqui no se elige entre las dos ni se rotula nada (`closeLevel.test.ts`).
 */
export function priorResponse(item: Recommendation): PriorResponseView | null {
  const prior = item.prior_response ?? null;
  if (prior === null) return null;
  const caveat = prior.caveat?.trim() ?? "";
  if (caveat === "") return null;
  const views = prior.adoptions.map((adoption) => ({
    key: adoption.adoption_index,
    lines: [
      adoption.adopted_text,
      adoption.state_text,
      adoption.checks_text,
      adoption.evaluation_text,
    ].filter((line): line is string => line !== null && line.trim() !== ""),
  }));
  const evaluated = prior.adoptions.some((adoption) => adoption.evaluation !== null);
  const latest = views[views.length - 1] ?? null;
  return {
    pictogram: priorPictogram(prior.state),
    summary: prior.text,
    // El resumen ya dice cuando y quien adopto la ultima: no se repite debajo.
    last: latest === null ? null : { key: latest.key, lines: latest.lines.slice(1) },
    earlier: views.slice(0, -1).reverse(),
    basis: evaluated ? prior.evaluation_basis : null,
    caveat,
  };
}

/**
 * Si la respuesta previa tiene algo que plegar: las lineas de alguna adopcion o la base de la
 * comparacion. Sin nada de eso («sin adopciones anteriores») no se pinta un desplegable vacio.
 */
export function priorHasDetail(view: PriorResponseView): boolean {
  return (
    (view.last !== null && view.last.lines.length > 0) ||
    view.earlier.length > 0 ||
    view.basis !== null
  );
}

/** Los efectos de una contramedida, en las lineas que se pintan. Todas son texto del backend. */
export interface EffectsView {
  /** «Beneficio esperado: sobre el dominio …». Sin magnitud. */
  benefit: string;
  /** Donde cae cada efecto adverso declarado: el nombre, lo que la nota dice y de donde sale. */
  adverse: { key: string; display: string; text: string; basis: string }[];
  /** La frase de «no declarado» cuando la entrada no escribe ninguno; `null` si los declara. */
  adverseText: string | null;
  /**
   * El backend dice que declara efectos y no manda ninguna linea legible (ni la frase de «no
   * declarado»): un hueco que se pinta como tal, con la marca del registro vacio, no como «no tiene».
   */
  adverseEmpty: boolean;
  /** Con que otras esta (o iria) adoptada a la vez, una nota por cada una. */
  coAdopted: { key: string; text: string; adopted: boolean }[];
  coAdoptionBasis: string;
}

/**
 * Los efectos de una contramedida tal y como los da el backend (`effects`, §5.39.17): sobre que
 * se espera el beneficio, donde cae cada efecto adverso que la biblioteca declara y con que otras
 * esta adoptada a la vez. Aqui solo se ordena lo que se pinta: no se resume, no se colorea y no se
 * decide nada. Sin la frase del beneficio no se pinta nada, y sin la frase de «no declarado» la
 * interfaz no la inventa: un hueco es un hueco, no un «no tiene».
 */
export function effectsView(effects: CountermeasureEffects | null | undefined): EffectsView | null {
  if (effects === null || effects === undefined) return null;
  const benefit = effects.benefit?.text?.trim() ?? "";
  if (benefit === "") return null;
  const adverseText = effects.adverse_text?.trim() ?? "";
  const adverse = (effects.adverse ?? [])
    .filter((item) => (item.text ?? "").trim() !== "")
    .map((item, index) => ({
      key: `${item.affects}:${item.key}:${index}`,
      display: item.display ?? "",
      text: item.text,
      basis: item.basis ?? "",
    }));
  return {
    benefit,
    adverse,
    adverseText: adverseText === "" ? null : adverseText,
    adverseEmpty: adverse.length === 0 && adverseText === "",
    coAdopted: (effects.co_adopted ?? [])
      .filter((note) => (note.text ?? "").trim() !== "")
      .map((note) => ({
        key: `${note.countermeasure_id}:${note.adoption_index}`,
        text: note.text,
        adopted: note.adopted,
      })),
    coAdoptionBasis: effects.co_adoption_basis?.trim() ?? "",
  };
}
