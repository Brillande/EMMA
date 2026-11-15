import { useCallback, useLayoutEffect, useRef, useState, useSyncExternalStore } from "react";

import { arrivalCut } from "./crew";

/**
 * Cuándo vuelve a mirar la consola de Tierra si ha llegado algo de lo que viaja al firmarse:
 * ecografías, informes de dolor, historial misión a misión (§5.37.17, §5.38.12).
 *
 * Por qué existe: los tres paneles llevaban cada uno su copia del temporizador de 30 s y de la
 * cuenta del corte, y dos de ellos (ecografías y dolor) volvían a pedir cada vez que el tiempo de
 * luz del estado cambiaba unas centésimas. Lo que llega es lo que cruza el corte con el paso del
 * tiempo, sin que cambie nada más en la pantalla; el tiempo de luz solo mueve ese corte, así que
 * no hace falta pedir por él: se lee el último en el momento de pedir (`cutNow`). Se vuelve a
 * pedir cada 30 s y al llegar o perderse las efemérides (con ellas hay corte; sin ellas, todo lo
 * de a bordo). La idea es la del historial en Tierra (§5.36.4), ahora escrita una vez.
 *
 * Desde §5.38.12 es también un solo reloj: un temporizador para todos los paneles que lo
 * escuchan (`arrivalClock`), y un solo instante de corte para lo que piden juntos. Antes cada panel
 * llevaba el suyo y cortaba con su propio `Date.now()`, así que un informe firmado justo en el corte
 * podía verse en un panel hasta 30 s antes que en otro.
 */
export const ARRIVAL_CHECK_MS = 30_000;

/**
 * El reloj compartido. Arranca con el primer panel que lo escucha y se para con el último: sin
 * paneles de Tierra en pantalla no hay temporizador. Fuera de React para que todos los paneles
 * lean el mismo, sin un proveedor que montar (y sin que un panel fuera de él vuelva a llevar el
 * suyo en silencio).
 *
 * El instante de corte es el de ahora, pero uno solo para todo lo que se pide en la misma tanda:
 * los efectos de un mismo pintado (una vuelta, un cambio de tripulante, la llegada de las
 * efemérides, el montaje) se ejecutan seguidos, sin soltar el hilo, y el instante se olvida en la
 * siguiente microtarea. Así los tres paneles cortan en el mismo instante y ninguno corta con uno
 * viejo: guardar el de la última vuelta habría hecho que un panel que pide entre vueltas (otro
 * tripulante, efemérides recién llegadas) cortara hasta 30 s atrás (revisión de código).
 */
export interface ArrivalClock {
  /** Escucha las vueltas; devuelve cómo dejar de escucharlas. Lo que pide `useSyncExternalStore`. */
  subscribe: (listener: () => void) => () => void;
  /** Cuántas vueltas ha dado: cambia cada 30 s mientras alguien escucha. */
  turns: () => number;
  /** El instante (ms) con que corta esta tanda: el de ahora, el mismo hasta la siguiente microtarea. */
  instant: () => number;
}

// `() => Date.now()` y no `Date.now`: lee el `Date` de cada momento, también el de una prueba con
// reloj falso instalado después de importar este módulo.
export function createArrivalClock(now: () => number = () => Date.now()): ArrivalClock {
  const listeners = new Set<() => void>();
  let turns = 0;
  let batch: number | null = null;
  let timer: ReturnType<typeof setInterval> | null = null;

  const turn = () => {
    turns += 1;
    for (const listener of [...listeners]) listener();
  };

  return {
    subscribe(listener) {
      if (timer === null) timer = setInterval(turn, ARRIVAL_CHECK_MS);
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
        if (listeners.size === 0 && timer !== null) {
          clearInterval(timer);
          timer = null;
        }
      };
    },
    turns: () => turns,
    instant: () => {
      if (batch === null) {
        batch = now();
        queueMicrotask(() => {
          batch = null;
        });
      }
      return batch;
    },
  };
}

/** El de la consola de Tierra: uno para toda la página. */
export const arrivalClock = createArrivalClock();

export interface ArrivalCheck {
  /** Va en las dependencias del efecto que pide: cambia cada 30 s y al llegar o perderse las efemérides. */
  checkKey: string;
  /** El corte del reloj compartido, con el último tiempo de luz (`arrivalCut`). */
  cutNow: () => Date | undefined;
}

export function useArrivalCheck(oneWayMinutes: number | null, clock: ArrivalClock = arrivalClock): ArrivalCheck {
  // `turns` también como instantánea del servidor: las pruebas pintan con `renderToStaticMarkup`.
  const tick = useSyncExternalStore(clock.subscribe, clock.turns, clock.turns);
  // El último tiempo de luz, leído al pedir y no al pintar: no dispara una petición nueva. Se
  // guarda en un efecto de maquetación, que va antes que los efectos que piden, y no al pintar:
  // un pintado que React descarta no deja en él un valor que nunca llegó a pantalla.
  const oneWay = useRef(oneWayMinutes);
  useLayoutEffect(() => {
    oneWay.current = oneWayMinutes;
  }, [oneWayMinutes]);

  const cutNow = useCallback(() => arrivalCut(oneWay.current, clock.instant()), [clock]);
  return { checkKey: arrivalCheckKey(oneWayMinutes, tick), cutNow };
}

/** La clave de `useArrivalCheck`, aparte para probarla: el tiempo de luz solo cuenta si existe o no. */
export function arrivalCheckKey(oneWayMinutes: number | null, tick: number): string {
  return `${oneWayMinutes === null ? "sin-efemerides" : "con-efemerides"}|${tick}`;
}

/**
 * Lo fijo que un panel de llegada necesita para pintar (el catálogo de protocolos, el de
 * indicadores, el de zonas de dolor): se pide una vez por panel montado y no en cada vuelta del
 * reloj (§5.38.12). Antes las ecografías volvían a pedir sus dos catálogos cada 30 s, y el dolor
 * el suyo. Una petición que falla o no vuelve no se guarda: la siguiente vuelta la reintenta,
 * porque sin catálogo los hallazgos de una ecografía no se pueden leer.
 *
 * `request` ha de ser una función del módulo, sin nada del tripulante ni de las propiedades: se
 * queda la del primer pintado. Lo que depende del tripulante no es fijo y va en el efecto.
 */
export function useFixedRequest<T>(request: () => Promise<T>): () => Promise<T> {
  // Una por panel montado: `useState` la crea una vez y la conserva entre pintados.
  const [fixed] = useState(() => onceRequest(request));
  return fixed;
}

/**
 * La regla de `useFixedRequest`, sin React para probarla: guarda lo que ha salido bien, no lo que
 * falla ni lo que aún no ha vuelto. Una petición colgada (sin red, una conexión que no se cierra:
 * `request` no tiene plazo) no se reutiliza: la vuelta siguiente pide otra, como antes de §5.38.12;
 * guardarla habría dejado el panel cargando para siempre (revisión de código).
 */
export function onceRequest<T>(request: () => Promise<T>): () => Promise<T> {
  let done: Promise<T> | null = null;
  return () => {
    if (done !== null) return done;
    const pending = request();
    pending.then(
      () => {
        done ??= pending;
      },
      () => {},
    );
    return pending;
  };
}
