/**
 * Lo poco que el panel decide por si mismo del estado declarado de los sistemas del habitat:
 * con que pictograma y que color se pinta cada estado, que filas se ensenan y que se manda al
 * firmar.
 *
 * Por que existe: EMMA no lee el estado de ningun sistema; lo declara una persona y el backend
 * lo entrega con su rotulo, sus nombres y sus frases (`environment/systems.py`). La interfaz no
 * redacta nada de eso. Lo que si elige —la marca— tiene reglas que merecen prueba:
 *
 * - «Sin declarar» es un dato AUSENTE (cian, anillo punteado; tabla F.5-1), nunca la marca de
 *   «funciona». Un sistema del que nadie ha dicho nada no esta bien: no se sabe.
 * - El color nunca va solo: pictograma propio de cada estado y la palabra del backend.
 * - Degradado y fuera de servicio van en amarillo («off-nominal, attention required»). El rojo
 *   no se usa: es el del nivel mas alto de alerta de EMMA, y una declaracion no es una alerta
 *   ni mueve ninguna. Los distingue el pictograma (triangulo; circulo tachado) y la palabra.
 * - Un estado que esta version no conoce se pinta sin significado, con su palabra, en vez de
 *   fallar o de disfrazarse de otro.
 *
 * Los dibujos son los de los glifos que habia (✓ △ ⊘ ◌), ahora como pictogramas SVG.
 */

import type { DeclaredLink, HabitatSystemStatus, HabitatSystems } from "../lib/api";
import { type StateMark, MISSING_MARK, UNKNOWN_MARK, mark } from "../lib/marks";

const MARKS: Record<string, StateMark> = {
  nominal: mark("check", "text"),
  degraded: mark("shape-triangle", "yellow"),
  "out-of-service": mark("slash-circle", "yellow"),
  undeclared: MISSING_MARK,
};

/** La marca de un estado. Uno desconocido no lleva significado: lo dice la palabra del backend. */
export function stateMark(state: string): StateMark {
  return MARKS[state] ?? UNKNOWN_MARK;
}

/**
 * El aviso del enlace con Tierra declarado (KB §2.1, pérdida de comunicaciones) para la franja y
 * la ficha de Tierra: la frase corta del backend con la marca de su estado, la misma que ese
 * estado lleva en el panel de sistemas (un dibujo por concepto, §5.33): el triángulo en amarillo
 * si está degradado, el círculo tachado en amarillo si está fuera de servicio. `headline` es la
 * frase corta (la franja y la ficha de Tierra) y `sentence` la entera (el párrafo bajo la ficha
 * de Tierra, que además dice que el retardo no cambia con la declaración y lleva la nota de quien
 * lo declaró). `null` si el backend no pide señalar nada (sin declarar
 * o declarado sin problema): la franja no crece.
 */
export function declaredLinkNotice(
  link: Pick<DeclaredLink, "attention" | "state" | "headline" | "sentence"> | undefined,
): { mark: StateMark; headline: string; sentence: string } | null {
  if (link === undefined || !link.attention || link.headline === null) return null;
  return { mark: stateMark(link.state), headline: link.headline, sentence: link.sentence };
}

export interface SystemRow {
  /** Clave estable para React: sistema y modulo (o el sistema entero). */
  key: string;
  system: string;
  status: HabitatSystemStatus;
  mark: StateMark;
  /** Solo si la declaracion habla de un modulo: su clave (para el pictograma) y su nombre, tal y como lo da el backend. */
  where: { key: string; display: string } | null;
}

/** Una fila por estado vigente de cada sistema: el sistema entero y, si los hay, sus modulos. */
export function systemRows(overview: Pick<HabitatSystems, "systems">): SystemRow[] {
  return overview.systems.flatMap((system) =>
    system.statuses.map((status) => ({
      key: `${system.key}:${status.module ?? ""}`,
      system: system.key,
      status,
      mark: stateMark(status.state),
      where: status.module === null ? null : { key: status.module, display: status.module_display },
    })),
  );
}

export interface StateCount {
  state: string;
  /** La palabra del backend para ese estado, la de su primera fila. */
  display: string;
  mark: StateMark;
  count: number;
}

/**
 * Cuántas filas hay en cada estado, en el orden en que aparece cada uno (tablero, lote «muestra»,
 * 2026-11-08: las píldoras que quedan a la vista cuando la lista va tras «Ver detalle»). Un estado
 * que esta versión no conoce sale con su palabra y sin significado, como en su fila.
 */
export function stateTally(rows: readonly SystemRow[]): StateCount[] {
  const seen = new Map<string, StateCount>();
  for (const row of rows) {
    const entry = seen.get(row.status.state);
    if (entry !== undefined) entry.count += 1;
    else seen.set(row.status.state, { state: row.status.state, display: row.status.state_display, mark: row.mark, count: 1 });
  }
  return [...seen.values()];
}

/** Los estados que una persona puede firmar: «sin declarar» no es uno de ellos. */
export function declarableStates(
  overview: Pick<HabitatSystems, "states">,
): HabitatSystems["states"] {
  return overview.states.filter((state) => state.declarable);
}

export interface DeclarationForm {
  system: string;
  state: string;
  /** "" = el sistema entero. */
  module: string;
  note: string;
}

export const EMPTY_FORM: DeclarationForm = { system: "", state: "", module: "", note: "" };

/** Se puede firmar con un sistema, un estado y el nombre de quien declara. La nota es opcional. */
export function canDeclare(form: DeclarationForm, operator: string | undefined): boolean {
  return form.system !== "" && form.state !== "" && (operator ?? "").trim() !== "";
}

/**
 * El instante al que se refiere la declaracion: el de los datos (la ultima lectura de cabina)
 * si lo hay, porque una mision simulada no vive en el reloj del ordenador; si no, ahora.
 */
export function declarationInstant(referenceTime: string | null, now: Date): string {
  return referenceTime ?? now.toISOString();
}

export interface DeclarationBody {
  system: string;
  state: string;
  module?: string;
  at: string;
  note: string;
  declared_by: string;
}

/** El cuerpo que se firma. El modulo solo viaja si se eligio uno. */
export function declarationBody(
  form: DeclarationForm,
  operator: string,
  at: string,
): DeclarationBody {
  return {
    system: form.system,
    state: form.state,
    ...(form.module === "" ? {} : { module: form.module }),
    at,
    note: form.note.trim(),
    declared_by: operator.trim(),
  };
}
