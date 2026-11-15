/**
 * La marca de un estado: pictograma y color, para la palabra que da el backend.
 *
 * Por qué existe: una docena de tablas de la interfaz (`advisor/resources.ts`, `habitat/flow.ts`,
 * `habitat/systems.ts`, `ground/framework.ts`…) resolvían lo mismo cada una a su manera, con un
 * carácter como glifo. Esta es la forma única con la que pasan a pictogramas: `mark(pictogram,
 * color)`, y `UNKNOWN_MARK` para el estado que la interfaz no conoce, que se enseña con su palabra
 * y sin significado (un punto, texto normal) en vez de disfrazarse de otro.
 *
 * El color es un token de la paleta o `null` (sin color con significado); `className` es la clase
 * `c-<token>` lista para el elemento, o `undefined`. El pictograma puede ser `null` cuando el
 * estado no lleva señal (confianza declarada, por ejemplo): entonces va solo la palabra.
 *
 * `MISSING_MARK` es la marca de «dato ausente o caducado» de la tabla F.5-1 (cian con el anillo
 * punteado): la misma en toda la interfaz, en vez de `mark("ring-dotted", "cyan")` escrito en
 * cada tabla. Y `prefixedPictogram` resuelve los nombres que llevan prefijo (`domain-<clave>`,
 * `ridge-<clave>`): si la clave del backend no tiene dibujo sale el de «desconocido», nunca uno
 * supuesto ni una excepción desde un render.
 */

import { type PictogramName, isPictogramName } from "../icons/registry";
import { ApiError } from "./api";
import type { Token } from "./palette";

export interface StateMark {
  readonly pictogram: PictogramName | null;
  readonly color: Token | null;
  readonly className: string | undefined;
}

export function mark(pictogram: PictogramName | null, color: Token | null): StateMark {
  return { pictogram, color, className: color === null ? undefined : `c-${color}` };
}

/** El dibujo de «desconocido», un punto: para las tablas que necesitan un pictograma, nunca nulo. */
export const UNKNOWN_PICTOGRAM: PictogramName = "dot-small";

/** Un estado que la interfaz no conoce: lo dice la palabra del backend, sin significado propio. */
export const UNKNOWN_MARK: StateMark = mark(UNKNOWN_PICTOGRAM, "text");

/** Dato ausente o caducado (tabla F.5-1, *missing or stale data*): cian con el anillo punteado. */
export const MISSING_MARK: StateMark = mark("ring-dotted", "cyan");

/*
 * Las cuatro marcas de los estados de un panel (segunda pasada, 2026-10-21, §5.33): cada panel
 * pintaba «no disponible», «falló», «cargando» y «listo» a su manera, con o sin dibujo. Son estas,
 * en toda la interfaz, y cada una con su palabra al lado, que sigue siendo la del panel o la del
 * backend.
 */

/** No disponible (tabla F.5-1, *not available*): gris con el círculo tachado. */
export const UNAVAILABLE_MARK: StateMark = mark("slash-circle", "gray");

/**
 * Indeterminado: hay datos, pero no deciden entre dos respuestas (la sububicación estimada cuando
 * dos módulos compiten, 2026-11-10). La interrogación sin color: no falta ni caduca nada (no es el
 * cian), sí está disponible (no es el gris) y no pide actuar (no es el amarillo). La palabra la da
 * el backend.
 */
export const INDETERMINATE_MARK: StateMark = mark("question", null);

/**
 * Una petición que falló: la cruz en rojo, con el motivo al lado. Es la petición que no llegó a
 * tener respuesta (sin red, `TypeError` de `fetch`), cuya respuesta fue un fallo del backend
 * (5xx) o un 409 del registro firmado roto (`isIntegrityBreak`): algo se rompió. Un «no» del
 * backend con su motivo (4xx) es `REFUSED_MARK`; quién es cuál lo decide `requestMark`, no cada
 * panel (decisión del usuario, 2026-10-21, §5.34.14).
 */
export const FAILURE_MARK: StateMark = mark("cross", "red");

/** Cargando: la flecha que gira, sin color (esperar no es una alerta) y sin animación. */
export const LOADING_MARK: StateMark = mark("refresh", null);

/** Hecho, sin nada que señalar: la marca de visto, sin color. */
export const OK_MARK: StateMark = mark("check", null);

/**
 * Una petición que el backend rechazó con su motivo (una firma, una declaración, un registro que
 * se corrige y se repite): el triángulo en amarillo, «hay que mirarlo» (tabla F.5-1), y al lado el
 * motivo del backend. Nació en el hábitat (`habitat/systems.ts`, §5.33.4) y el asesor tenía la
 * suya con otro nombre (`REQUEST_WARNING_MARK`); la limpieza (§5.33.12) la sube aquí y la usan
 * todos los rechazos que se pintaban en amarillo con el triángulo escrito a mano.
 *
 * Decisión del usuario (2026-10-21): un rechazo del backend (4xx) va así en toda la interfaz,
 * también el modo seguro; la petición caída (5xx, sin red) va con `FAILURE_MARK`. Hasta entonces
 * cada panel elegía una de las dos para todo lo que le saliera mal (§5.34.14).
 */
export const REFUSED_MARK: StateMark = mark("shape-triangle", "yellow");

/**
 * El `detail` del 409 de la ecografía cuando la calibración firmada de un estudio no se puede leer
 * (`api/imaging._regions`). Ese 409 no trae `integrity_ok`, así que se reconoce por su texto exacto;
 * `lib/marks.test.ts` comprueba que el backend lo sigue escribiendo así.
 */
export const UNREADABLE_CALIBRATION = "calibración del estudio ilegible";

/**
 * El backend contestó 409 porque el registro firmado no respalda lo que se pidió: un asiento
 * manipulado (el manejador de `TamperedRecordError` de `main.py`, que lo marca con
 * `integrity_ok: false`, en cualquier ruta) o la calibración firmada ilegible de un estudio de
 * ecografía. No hay nada que corregir y repetir, como en un rechazo: algo se rompió, y va con
 * `FAILURE_MARK` (decisión del usuario, 2026-10-22, §5.35.12). Hasta entonces, por ser un 4xx,
 * salía en amarillo con el triángulo (§5.34.14).
 */
export function isIntegrityBreak(reason: unknown): reason is ApiError {
  return (
    reason instanceof ApiError &&
    reason.status === 409 &&
    (reason.integrityBroken || reason.detail === UNREADABLE_CALIBRATION)
  );
}

/**
 * El backend contestó y dijo que no (4xx): su motivo es algo que mirar y corregir, no un fallo de
 * la consola. Un 5xx, o una petición que ni llegó (`TypeError` de `fetch`, cualquier otra
 * excepción), sí lo son, y también el 409 del registro roto (`isIntegrityBreak`), que es un 4xx
 * pero no un «no». Vivía en `imaging/Attention.tsx`, donde la ecografía y los informes ya
 * separaban los dos; desde §5.34.14 lo usa toda la interfaz.
 */
export function isRefusal(reason: unknown): reason is ApiError {
  return reason instanceof ApiError && reason.status >= 400 && reason.status < 500 && !isIntegrityBreak(reason);
}

/**
 * La marca de lo que salió mal en una petición, por lo que es y no por el panel que la hizo:
 * rechazo del backend (4xx) → `REFUSED_MARK`; fallo (5xx, sin red, excepción, o el 409 del
 * registro firmado roto) → `FAILURE_MARK`.
 * Por qué existe: hasta la decimocuarta ronda cada panel elegía una marca para todo lo que le
 * saliera mal, y el mismo 422 salía en amarillo en el asesor y en rojo en el modo seguro, y una
 * caída de red en amarillo en el diario. Rechazo o fallo solo se decide aquí; `App.tsx` mira
 * además el 404 del estado, que no es un error que pintar sino el almacén vacío.
 */
export function requestMark(reason: unknown): StateMark {
  return isRefusal(reason) ? REFUSED_MARK : FAILURE_MARK;
}

/** Lo que salió mal en una petición, ya clasificado: su marca y el texto que se enseña. */
export interface RequestOutcome {
  readonly mark: StateMark;
  readonly text: string;
}

/**
 * La marca (`requestMark`) y el texto: el motivo del backend tal cual (`detail`) o, si no llegó
 * respuesta, el error. Es lo que guarda un panel para pintarlo después: guardar solo el texto
 * pierde el código de estado, y con él si fue un «no» o un fallo.
 */
export function requestOutcome(reason: unknown): RequestOutcome {
  return { mark: requestMark(reason), text: reason instanceof ApiError ? reason.detail : String(reason) };
}

/**
 * Un registro de a bordo sin nada todavía («Sin estudios registrados», «Sin informes de dolor
 * registrados», «Ninguna prueba de este tripulante en el registro»): el anillo punteado sin color.
 * No es un dato que falte o caduque (el cian de `MISSING_MARK`), es que aún no se ha registrado
 * nada; y no es «hecho» (`OK_MARK`), que es la respuesta de una consulta sin nada que contar. La
 * ecografía, el dolor, los informes y los volúmenes lo pintaban así a mano y el diario y la PVT en
 * cian: un concepto con dos marcas, que la limpieza (§5.33.12) dejó en esta. En Tierra, lo que aún
 * no ha llegado sí es dato ausente (va un tiempo de luz por detrás) y sigue en cian.
 */
export const EMPTY_MARK: StateMark = mark("ring-dotted", null);

/** Un valor por encima de la escala de su medidor: la flecha hacia arriba, sin color (neutro). */
export const ABOVE_SCALE_MARK: StateMark = mark("arrow-up", null);

/** Un valor por debajo de la escala de su medidor: la flecha hacia abajo, sin color. */
export const BELOW_SCALE_MARK: StateMark = mark("arrow-down", null);

/**
 * Dónde cae un valor respecto de la escala `[min, max]` de un medidor (`components/Meter.tsx`):
 * `null` dentro, y fuera la flecha de su lado. Una sola prueba de rango para el medidor y para
 * quien escribe la cifra a su lado y no quiere escribirla dos veces (el dosímetro, la escala de
 * carrera): hasta la limpieza (§5.33.12) eran tres copias, y la de `radiation/marks.ts` solo
 * valía con mínimo cero.
 */
export function scaleMark(value: number, min: number, max: number): StateMark | null {
  if (value > max) return ABOVE_SCALE_MARK;
  if (value < min) return BELOW_SCALE_MARK;
  return null;
}

/** Sin señal: solo la palabra (una posición del diario que no tiene nada que marcar). */
export const NO_MARK: StateMark = mark(null, null);

/**
 * La marca de quien anotó una lectura de autoinforme: ninguna si consta el nombre; «no
 * disponible» (`UNAVAILABLE_MARK`) si no. La usan el diario y los descriptivos: vivía en
 * `diary/position.ts` y los descriptivos la importaban de allí (§5.33.7).
 */
export function recordedByMark(recordedBy: string | null): StateMark {
  return recordedBy === null ? UNAVAILABLE_MARK : NO_MARK;
}

/** El dibujo `<prefijo>-<clave>` si existe en el registro; si no, el de «desconocido». */
export function prefixedPictogram(prefix: "domain" | "ridge", key: string): PictogramName {
  const name = `${prefix}-${key}`;
  return isPictogramName(name) ? name : UNKNOWN_PICTOGRAM;
}
