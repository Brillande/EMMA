/**
 * Girar la vista siguiendo el giroscopio de la tableta, desde un «esto es arriba» que fija la
 * persona.
 *
 * Por qué existe: el giro automático del sistema operativo decide la orientación con el
 * acelerómetro, es decir, con la gravedad. En microgravedad no hay gravedad que medir y el sistema
 * no sabe dónde es «abajo»: gira la pantalla al azar o no la gira. El giroscopio no necesita la
 * gravedad: mide cuánto ha girado la tableta sobre su propio plano desde una referencia. Esa
 * referencia no la puede adivinar ningún sensor; la fija la persona con un botón («esto es
 * arriba»: la vista tal como la ve ahora está derecha), y desde ahí la vista se gira lo contrario
 * de lo que gire la tableta (§5.40 de `compliance/hmi-state-of-the-art.md`).
 *
 * La vista solo se pone en cuatro posiciones (0, 90, 180, 270°, las del giro manual), la del
 * cuadrante más cercano, con histéresis: cerca de 45° no salta de una a otra, y nunca se anima.
 * Una vista que parpadea entre dos giros es justo lo que WCAG 2.3.1 pide evitar.
 *
 * Fuentes. La que vale en el espacio es la velocidad angular cruda de `Gyroscope` (Generic
 * Sensor API), integrando solo el eje perpendicular a la pantalla (z). No se usan
 * `RelativeOrientationSensor` ni `AbsoluteOrientationSensor`: el navegador los calcula fundiendo
 * giroscopio con acelerómetro (y magnetómetro), y en caída libre el acelerómetro marca casi cero,
 * así que su corrección de inclinación no tiene referencia. Si solo hay el evento
 * `deviceorientation`, que se calcula igual, se usa como respaldo declarado «solo en Tierra»
 * (`source: "earth"`). Sin ninguno (portátil, Electron de escritorio) se declara «no disponible» y
 * el giro manual sigue siendo el respaldo.
 *
 * Límites físicos, que no arregla ningún código:
 * - Un giroscopio MEMS sin corregir deriva, y la integración acumula ese error: «esto es arriba»
 *   está siempre a mano para volver a fijar la referencia, y se dice desde cuándo vale. Por debajo
 *   de `DEAD_ZONE_RAD_S` no se integra, para no sumar el ruido de la tableta quieta.
 * - El giroscopio mide el giro de la tableta en el espacio inercial, no respecto a quien la mira:
 *   si la persona y la tableta giran juntas, la vista giraría sin motivo.
 * - Una estación orientada a la Tierra da una vuelta por órbita: una tableta fija a la pared la
 *   vería girar sola, aunque nadie la mueva.
 * - Lo que de verdad dice dónde es «arriba» para quien mira es su cara, con la cámara (idea del
 *   equipo, en el audio del seguimiento ocular). Está como demostración sin validar en
 *   `faceOrientation.ts`; con los dos modos encendidos, manda la cara mientras la ve.
 * Por eso el modo no va por defecto: lo enciende la persona.
 *
 * Aquí va casi todo como funciones puras con prueba (`orientation.test.ts`); solo
 * `watchOrientation` toca el navegador, y no se ha probado con un sensor real.
 */

import type { Rotation } from "../components/displayModes";

/** Grados de más, sobre los 45 de la mitad del cuadrante, que hay que pasar para cambiar de giro. */
export const HYSTERESIS_DEGREES = 15;

/** Cuánto se espera una lectura antes de declarar el sensor no disponible. */
export const SENSOR_WAIT_MS = 3000;

/** Un hueco entre lecturas más largo que esto no se integra: no se sabe qué giró en él. */
export const MAX_GAP_SECONDS = 0.5;

/**
 * Zona muerta: una velocidad angular por debajo de esta (rad/s, ≈ 1,1 °/s) no se integra, para
 * no acumular el ruido de la tableta en reposo. Es un parámetro de diseño de EMMA, sin fuente:
 * elegido para que un giro deliberado de la tableta la supere de sobra. Un giro más lento que
 * esto no se sigue.
 */
export const DEAD_ZONE_RAD_S = 0.02;

/** Un ángulo cualquiera llevado a [0, 360). */
export function normalizeDegrees(angle: number): number {
  const turned = angle % 360;
  const positive = turned < 0 ? turned + 360 : turned;
  // `-0 % 360` y redondeos como `359.9999999` + algo pueden dar 360: es 0.
  return positive >= 360 ? 0 : positive + 0;
}

/** Lo que va de `from` a `to` por el camino corto, en (-180, 180]. */
export function signedDelta(from: number, to: number): number {
  const delta = normalizeDegrees(to - from);
  return delta > 180 ? delta - 360 : delta;
}

/** El cuadrante más cercano a un ángulo (45° exactos van al siguiente en el sentido del reloj). */
export function nearestQuadrant(angle: number): Rotation {
  const index = Math.floor((normalizeDegrees(angle) + 45) / 90) % 4;
  return ([0, 90, 180, 270] as const)[index] ?? 0;
}

/**
 * El giro que toca con el ángulo de ahora, sin saltar en el borde: se sigue en el cuadrante actual
 * mientras el ángulo no se aleje de él más de 45° + `band`. Con la banda de partida (15°), de 0 se
 * pasa a 90 al llegar a 60°, y para volver a 0 hay que bajar de 30°.
 */
export function followQuadrant(current: Rotation, angle: number, band = HYSTERESIS_DEGREES): Rotation {
  if (Math.abs(signedDelta(current, angle)) <= 45 + band) return current;
  return nearestQuadrant(angle);
}

/**
 * La referencia de «esto es arriba»: el giro de la vista que la persona dio por derecho (`base`),
 * cuánto había girado la tableta en ese momento (`turn`) y el giro que el sistema operativo tenía
 * aplicado a la pantalla (`screen`). `base` es uno de los cuatro giros cuando lo fija la persona,
 * y el ángulo de la cara tal cual cuando lo fija la cara (`faceOrientation.ts`), para que el
 * giroscopio siga desde donde está de verdad la cara y no desde el cuadrante.
 */
export interface UpReference {
  readonly base: number;
  readonly turn: number;
  readonly screen: number;
}

/**
 * De dónde sale la lectura: el giroscopio crudo, que vale en microgravedad, o la orientación que
 * funde el navegador con el acelerómetro, que solo vale en Tierra.
 */
export type SensorSource = "gyroscope" | "earth";

/** Una lectura: giro acumulado de la tableta sobre su plano y giro aplicado por el sistema. */
export interface OrientationReading {
  readonly source: SensorSource;
  /** Grados, en sentido contrario al reloj mirando la pantalla de frente, desde el arranque. */
  readonly turn: number;
  /** `screen.orientation.angle`: lo que el sistema operativo ya giró por su cuenta. */
  readonly screen: number;
}

/** Lo de una lectura que cuenta para el ángulo. */
export type TurnReading = Pick<OrientationReading, "turn" | "screen">;

export function upReference(base: number, reading: TurnReading): UpReference {
  return { base, turn: reading.turn, screen: reading.screen };
}

/**
 * El ángulo al que habría que girar la vista para que siga derecha. Si la tableta gira θ en
 * sentido contrario al reloj, la vista gira θ en el del reloj (el de `rotate()` de CSS); lo que el
 * sistema operativo ya haya girado por su cuenta desde la referencia se descuenta, para no girar
 * dos veces.
 */
export function viewAngle(reference: UpReference, reading: TurnReading): number {
  return normalizeDegrees(reference.base + (reading.turn - reference.turn) - (reading.screen - reference.screen));
}

/**
 * Suma al giro acumulado lo girado en `dtSeconds` a `rate` rad/s. Un hueco largo, una velocidad
 * dentro de la zona muerta o una lectura rota no se suman.
 */
export function integrateTurn(turn: number, rate: number, dtSeconds: number, deadZone = DEAD_ZONE_RAD_S): number {
  if (!Number.isFinite(rate) || !(dtSeconds > 0) || dtSeconds > MAX_GAP_SECONDS) return turn;
  if (Math.abs(rate) < deadZone) return turn;
  return turn + (rate * dtSeconds * 180) / Math.PI;
}

/** Cuaternión de rotación (w, x, y, z), del sistema del equipo al de referencia. */
export interface Quaternion {
  readonly w: number;
  readonly x: number;
  readonly y: number;
  readonly z: number;
}

function multiply(a: Quaternion, b: Quaternion): Quaternion {
  return {
    w: a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z,
    x: a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y,
    y: a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
    z: a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w,
  };
}

function conjugate(q: Quaternion): Quaternion {
  return { w: q.w, x: -q.x, y: -q.y, z: -q.z };
}

function axis(degrees: number, which: "x" | "y" | "z"): Quaternion {
  const half = (degrees * Math.PI) / 360;
  return { w: Math.cos(half), x: 0, y: 0, z: 0, [which]: Math.sin(half) };
}

/** Los ángulos de `deviceorientation` (Z-X'-Y'' intrínsecos, en grados) como cuaternión. */
export function quaternionFromEuler(alpha: number, beta: number, gamma: number): Quaternion {
  return multiply(multiply(axis(alpha, "z"), axis(beta, "x")), axis(gamma, "y"));
}

/**
 * Cuánto ha girado `current` respecto de `start` sobre el eje perpendicular a la pantalla (la
 * parte «giro» de la descomposición giro-inclinación), en grados. Es exacto si la tableta gira en
 * su plano; con mucha inclinación es una aproximación, y si la pantalla se ha dado casi la vuelta
 * no hay giro que leer (`null`).
 */
export function screenTwist(start: Quaternion, current: Quaternion): number | null {
  const relative = multiply(conjugate(start), current);
  if (Math.hypot(relative.w, relative.z) < 0.2) return null;
  return (2 * Math.atan2(relative.z, relative.w) * 180) / Math.PI;
}

/** Cómo va el sensor, para decirlo en la interfaz. */
export type SensorStatus = "off" | "waiting" | "reading" | "unavailable";

// --- Lo que toca el navegador ------------------------------------------------------------------
// Los tipos del Generic Sensor API no vienen en `lib.dom`: lo mínimo que se usa.

interface GenericSensor extends EventTarget {
  start(): void;
  stop(): void;
  readonly timestamp?: number | null;
}

interface GyroscopeSensor extends GenericSensor {
  readonly z?: number | null;
}

type SensorConstructor<T> = new (options: { frequency: number; referenceFrame: "device" }) => T;

interface SensorWindow {
  Gyroscope?: SensorConstructor<GyroscopeSensor>;
  DeviceOrientationEvent?: unknown;
}

interface PermissionRequester {
  requestPermission?: () => Promise<string>;
}

function currentScreenAngle(): number {
  try {
    const angle = window.screen?.orientation?.angle;
    return typeof angle === "number" ? angle : 0;
  } catch {
    return 0;
  }
}

/**
 * Pide permiso para el evento de orientación donde hay que pedirlo (Safari de iOS, y solo desde un
 * gesto: se llama al pulsar el mando). En el resto no hace nada. Nunca lanza.
 */
export function requestOrientationPermission(): void {
  try {
    const event = (window as unknown as SensorWindow).DeviceOrientationEvent as PermissionRequester | undefined;
    void event?.requestPermission?.().catch(() => undefined);
  } catch {
    // Sin permiso, el sensor se declara no disponible al no llegar lecturas.
  }
}

/**
 * Escucha el sensor de giro y da lecturas; si no llega ninguna a tiempo, o el que hay no se puede
 * usar, lo dice una vez con `unavailable`. Devuelve con qué pararlo. Sin probar con sensor real.
 */
export function watchOrientation(handlers: {
  reading: (reading: OrientationReading) => void;
  unavailable: () => void;
}): () => void {
  let stopped = false;
  let received = false;
  let declared = false;
  let stopSource: (() => void) | null = null;
  const sensors = (typeof window === "undefined" ? {} : window) as unknown as SensorWindow;

  const unavailable = () => {
    if (stopped || received || declared) return;
    declared = true;
    handlers.unavailable();
  };
  const emit = (source: SensorSource, turn: number) => {
    if (stopped) return;
    received = true;
    handlers.reading({ source, turn, screen: currentScreenAngle() });
  };
  const timer = setTimeout(unavailable, SENSOR_WAIT_MS);

  // Cada fuente arranca la siguiente si falla al construirse o con su evento `error`.
  const sources: (() => void)[] = [startGyroscope, startOrientationEvent, unavailable];
  const next = () => {
    stopSource?.();
    stopSource = null;
    if (stopped) return;
    const start = sources.shift();
    start?.();
  };

  function startSensor<T extends GenericSensor>(
    Ctor: SensorConstructor<T> | undefined,
    onReading: (sensor: T) => void,
  ): void {
    if (Ctor === undefined) return next();
    let sensor: T;
    try {
      sensor = new Ctor({ frequency: 20, referenceFrame: "device" });
    } catch {
      return next();
    }
    let failed = false;
    sensor.addEventListener("reading", () => onReading(sensor));
    sensor.addEventListener("error", () => {
      if (failed || received) return;
      failed = true;
      next();
    });
    stopSource = () => sensor.stop();
    try {
      sensor.start();
    } catch {
      next();
    }
  }

  function startGyroscope(): void {
    let turn = 0;
    let last: number | null = null;
    startSensor(sensors.Gyroscope, (sensor) => {
      const time = sensor.timestamp;
      const rate = sensor.z;
      if (typeof time !== "number" || typeof rate !== "number") return;
      if (last !== null) turn = integrateTurn(turn, rate, (time - last) / 1000);
      last = time;
      emit("gyroscope", turn);
    });
  }

  // Respaldo solo para Tierra: el navegador funde este evento con el acelerómetro.
  function startOrientationEvent(): void {
    if (typeof window === "undefined" || sensors.DeviceOrientationEvent === undefined) return next();
    let start: Quaternion | null = null;
    const listener = (event: DeviceOrientationEvent) => {
      const { alpha, beta, gamma } = event;
      // Sin sensor, Chrome de escritorio manda un evento con todo a `null`.
      if (alpha === null || beta === null || gamma === null) return unavailable();
      const current = quaternionFromEuler(alpha, beta, gamma);
      start ??= current;
      const twist = screenTwist(start, current);
      if (twist !== null) emit("earth", twist);
    };
    window.addEventListener("deviceorientation", listener);
    stopSource = () => window.removeEventListener("deviceorientation", listener);
  }

  next();
  return () => {
    stopped = true;
    clearTimeout(timer);
    stopSource?.();
    stopSource = null;
  };
}
