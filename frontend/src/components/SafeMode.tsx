import { useEffect, useRef, useState } from "react";

import { Pictogram, type PictogramName } from "../icons";
import { type HaltNoticeText, type SafeModeState, api } from "../lib/api";
import { formatUtc } from "../lib/format";
import { tr } from "../lib/i18n";
import { useOperator } from "../lib/operator";
import { MISSING_MARK, type RequestOutcome, requestOutcome } from "../lib/marks";
import { Command } from "./Command";
import { FieldLabel } from "./FieldLabel";
import { Fold } from "./Fold";
import { Mark, MarkOf } from "./Mark";

/**
 * Cada cuánto se vuelve a leer el estado de la red. El freno HALT de Polaris es un fichero: puede
 * aparecer con la consola abierta (lo pone una persona o una herramienta de Polaris), y avisar
 * por sí solo es que se vea sin recargar. El mismo ritmo que el estado del tripulante (`App.tsx`).
 *
 * Límite que se declara: en la consola de Tierra este estado es el del momento, sin el retardo
 * de la luz que lleva el resto de su franja. Ya era así con el modo seguro; el freno lo hereda.
 */
export const SAFE_MODE_REFRESH_MS = 30_000;

/** Lo que la franja sabe de la red: el estado leído, si está sin actualizar y cómo cambiarlo. */
export interface NetworkWatch {
  readonly state: SafeModeState | null;
  readonly stale: boolean;
  /** Activa o levanta el modo seguro; lanza lo que diga el backend para que se pinte su marca. */
  readonly apply: (body: SafeModeChange) => Promise<void>;
}

type SafeModeChange = { active: boolean; reason: string; declared_by: string };

/** Las dos operaciones del gancho, sin React: lo que decide qué respuesta se enseña. */
export interface NetworkSync {
  /** Relee el estado; la respuesta se enseña solo si nadie la ha dejado vieja (abajo). */
  readonly load: () => void;
  /** Activa o levanta el modo seguro; la respuesta se enseña si no la ha dejado vieja otro cambio. */
  readonly apply: (body: SafeModeChange) => Promise<void>;
}

/**
 * Qué respuesta gana entre relecturas y cambios del modo seguro. Hasta §5.37.18 un solo contador
 * valía para las dos: una relectura que salía después de activar el modo seguro y volvía antes que
 * la respuesta de la activación ganaba (era «la última») y enseñaba el estado de antes; así hasta
 * la relectura siguiente (30 s), con el modo seguro puesto y la franja diciendo «abierta». El
 * arreglo de §5.37.18 contaba peticiones en el cliente y, con dos cambios cruzados, no sabía en qué
 * orden los había aplicado el servidor: lo resolvía releyendo al final.
 *
 * Desde §5.38.13 el estado lleva su versión (`version`, la cuenta de cambios firmados, que el
 * backend sube en uno con cada cambio y devuelve en la lectura y en la respuesta de cada cambio), y
 * la regla es una: **se enseña la versión más alta que haya llegado**, venga de una relectura o de
 * un cambio y llegue en el orden que llegue. Una respuesta de versión más baja que la que se ve es
 * vieja y se descarta. Con dos cambios cruzados, la respuesta del que el servidor firmó después
 * lleva la versión más alta y gana, sin preguntar.
 *
 * La versión cuenta los cambios de UN almacén, y el backend lo sustituye al cambiar de escenario o
 * al reiniciarse (vuelve a 0): por eso el estado lleva también `store_epoch`, que crece con cada
 * almacén, y se compara primero. Lo de un almacén posterior gana aunque su versión sea más baja.
 * Lo de uno anterior se descarta, salvo que sea la última relectura pedida y nada haya llegado
 * desde que salió: es lo que dice hoy el servidor (un backend reiniciado con el reloj atrasado
 * tendría una época menor), y una relectura que salió antes de otra respuesta ya no cumple eso.
 *
 * Con la misma versión, el modo seguro es el mismo y solo puede cambiar el freno HALT, que no se
 * versiona (es un fichero, `halt_notice`): lo actualiza solo la última relectura pedida; una
 * relectura anterior o la respuesta de un cambio no lo pisan, pero dicen que lo que se ve está al
 * día (`markFresh`: quitan el «sin actualizar»).
 *
 * Releer solo hace falta si se puede haber perdido una versión: un cambio que falla (la petición
 * pudo caerse después de que el servidor lo firmara) deja sin saber si existe una versión más
 * nueva que no ha llegado, y al acabar el último cambio en vuelo se relee. Un cambio, o varios
 * cruzados, que salen bien no releen: sus respuestas traen todas las versiones. El fallo de un
 * cambio que otro pedido después dejó viejo no se lanza (no pinta un error bajo un estado que sí se
 * aplicó). Una relectura que falla marca «sin actualizar» si es la última pedida, no va ningún
 * cambio (su respuesta lo dirá) y nada ha llegado desde que salió. El mando, además, no deja pedir
 * otro cambio mientras uno va (`SafeMode`).
 *
 * Sin React para poder probarlo con respuestas que llegan en el orden que diga la prueba.
 */
export function networkSync(
  read: () => Promise<SafeModeState>,
  write: (body: SafeModeChange) => Promise<SafeModeState>,
  show: (state: SafeModeState) => void,
  markStale: () => void,
  markFresh: () => void = () => {},
): NetworkSync {
  let epoch: number | null = null; // de qué almacén es lo que se enseña; null antes de nada
  let shown = -1; // la versión que se enseña
  let heard = 0; // cuántas respuestas han dicho algo al día (enseñadas o confirmadas)
  let reads = 0; // la última relectura pedida
  let writes = 0; // el último cambio pedido
  let pending = 0; // cambios sin respuesta todavía
  let failed = false; // si alguno de los cambios en vuelo desde que no había ninguno falló

  /**
   * Enseña `next` si es más nueva que lo que se ve. `refresh`: es la última relectura pedida;
   * `untouched`: además, nada ha llegado desde que salió (solo una relectura lo sabe).
   */
  const offer = (next: SafeModeState, refresh: boolean, untouched: boolean) => {
    const sameStore = next.store_epoch === epoch;
    const newer =
      epoch === null || next.store_epoch > epoch || (sameStore && next.version > shown);
    const same = sameStore && next.version === shown;
    const earlierStore = !sameStore && !newer;
    if (newer || (same && refresh) || (earlierStore && refresh && untouched)) {
      epoch = next.store_epoch;
      shown = next.version;
      heard += 1;
      show(next);
    } else if (same) {
      heard += 1;
      markFresh();
    }
  };

  const load = () => {
    const request = ++reads;
    const before = heard;
    read().then(
      (next) => offer(next, request === reads, heard === before),
      () => {
        if (request === reads && pending === 0 && heard === before) markStale();
      },
    );
  };

  const apply = async (body: SafeModeChange) => {
    const request = ++writes;
    if (pending === 0) failed = false;
    pending += 1;
    let next: SafeModeState | undefined;
    let failure: unknown;
    try {
      next = await write(body);
    } catch (error) {
      failure = error;
      failed = true;
    }
    pending -= 1;
    if (next !== undefined) offer(next, false, false);
    // Un cambio fallido pudo firmarse igualmente: la versión que dejó no ha llegado. Al acabar el
    // último en vuelo se relee, y esa relectura trae la más nueva que haya.
    if (pending === 0 && failed) load();
    // El fallo de un cambio que otro pedido después ya dejó viejo no es lo que se ve: no se lanza.
    if (next === undefined && request === writes) throw failure;
  };

  return { load, apply };
}

/**
 * El estado de la red, leído al montar y cada `SAFE_MODE_REFRESH_MS`. Vive en un gancho y no en
 * `SafeMode` porque lo leen dos sitios: la celda de la franja y, debajo de la franja y ya en la
 * página, la explicación del freno cuando se despliega (`HaltDetails`, §5.35.12).
 */
export function useNetworkWatch(): NetworkWatch {
  const [state, setState] = useState<SafeModeState | null>(null);
  // Una relectura que falla no borra lo que ya se veia (un modo seguro o un freno puestos no
  // pueden desaparecer de la franja por un fallo de red): se conserva y se marca sin actualizar.
  const [stale, setStale] = useState(false);
  // Qué respuesta gana entre relecturas y cambios lo decide `networkSync`: una relectura vieja no
  // pisa el estado que dejó activar o levantar el modo seguro, ni al revés.
  const [sync] = useState(() =>
    networkSync(
      () => api.safeMode(),
      (body) => api.setSafeMode(body),
      (next) => {
        setState(next);
        setStale(false);
      },
      () => setStale(true),
      () => setStale(false),
    ),
  );

  useEffect(() => {
    sync.load();
    // Con la ventana oculta no se pregunta: al volver, la siguiente vuelta lo pone al dia.
    const timer = setInterval(() => {
      if (typeof document === "undefined" || !document.hidden) sync.load();
    }, SAFE_MODE_REFRESH_MS);
    return () => clearInterval(timer);
  }, [sync]);

  return { state, stale, apply: sync.apply };
}

/**
 * Modo seguro en la franja comun (F.4.2: mensajes del sistema siempre visibles). Corta toda salida
 * a internet; la IA es local y sigue (regla de Polaris `codigo_rojo`: lo activa cualquiera con
 * motivo, lo levanta solo una persona). Activo = precaucion (amarillo con triangulo, F.5-1).
 * Los controles solo a bordo: Tierra ve el estado, no lo cambia.
 *
 * Debajo, el freno HALT de Polaris (`HaltNotice`) cuando esta puesto: tambien corta la red, y
 * por eso la celda de la red no dice "abierta" mientras exista.
 *
 * Pictogramas (§5.32): el rotulo lleva el mastil con ondas (la red); la red abierta, la puerta
 * abierta; el modo seguro, el triangulo de precaucion. El mando para activarlo lleva el mismo
 * triangulo sin color de alerta (es una orden, no un aviso) y el de levantarlo, la puerta.
 * Segunda pasada (§5.33.11): los rotulos del formulario llevan el signo de su concepto («Quién»,
 * la persona; «Motivo», el bocadillo de lo que alguien dice). Lo que sale mal al activarlo o
 * levantarlo lleva la marca de lo que es (`requestOutcome`, §5.34.14): el rechazo del backend con
 * su motivo (un 4xx: falta quién o el motivo) en amarillo con el triangulo, la peticion caida en
 * rojo con la cruz. Hasta entonces todo iba en rojo.
 *
 * Franja compacta (§5.40, 2026-11-04): la celda («Red» y lo que la corta) va con las demás celdas,
 * y el mando que la cambia (`SafeModeCommand`), con los demás mandos de la franja, en la misma
 * fila. Antes iban apilados en una columna de tres renglones. Lo que hacen no cambia.
 */
export function SafeMode({
  network,
  haltOpen = false,
  onHaltToggle,
}: {
  network: NetworkWatch;
  /** Si la explicación del freno está desplegada en la página (`HaltDetails`, §5.35.12). */
  haltOpen?: boolean;
  onHaltToggle?: () => void;
}) {
  const { state, stale } = network;
  if (state === null) return null;
  return (
    <div className="cell">
      <span className="label">
        <Pictogram name="antenna" />
        {tr("Red", "Network")}
        {stale && (
          <>
            {" · "}
            <MarkOf mark={MISSING_MARK}>
              {tr("sin actualizar", "not updated")}
            </MarkOf>
          </>
        )}
      </span>
      <NetworkStatus state={state} haltOpen={haltOpen} onHaltToggle={onHaltToggle} />
    </div>
  );
}

/**
 * El mando del modo seguro, solo a bordo: un plegable compacto en la fila de mandos de la franja
 * cuyo formulario (quién, motivo y la orden) se abre encima de la página, colgado del mando, sin
 * hacer crecer la franja fija (`.strip-pop`).
 */
export function SafeModeCommand({ network }: { network: NetworkWatch }) {
  const { state } = network;
  const [operator, setOperator] = useOperator();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<RequestOutcome | null>(null);
  // Mientras va un cambio no se pide otro: un doble clic cruzaba dos peticiones (§5.37.18).
  const [sending, setSending] = useState(false);

  const change = async (active: boolean) => {
    setError(null);
    setSending(true);
    try {
      await network.apply({ active, reason: reason.trim(), declared_by: operator.trim() });
      setReason("");
    } catch (failure) {
      setError(requestOutcome(failure));
    } finally {
      setSending(false);
    }
  };

  if (state === null) return null;
  // El mando enseña a donde lleva: a cerrar la red (triangulo) o a abrirla de nuevo (puerta).
  const command: PictogramName = state.active ? "door-open" : "shape-triangle";
  return (
    <Fold pictogram={command} className="safe-mode strip-pop" label={state.active ? tr("Levantar", "Lift") : tr("Modo seguro", "Safe mode")}>
      <div className="silence-form">
        <FieldLabel concept="person">
          {tr("Quién", "Who")}{" "}
          <input value={operator} maxLength={64} onChange={(event) => setOperator(event.target.value)} />
        </FieldLabel>
        {!state.active && (
          <FieldLabel concept="reason">
            {tr("Motivo", "Reason")} <input value={reason} maxLength={300} onChange={(event) => setReason(event.target.value)} />
          </FieldLabel>
        )}
        <button
          className="command"
          disabled={sending || operator.trim() === "" || (!state.active && reason.trim() === "")}
          onClick={() => void change(!state.active)}
        >
          <Mark pictogram={command}>
            {state.active ? tr("Levantar modo seguro", "Lift safe mode") : tr("Activar modo seguro", "Activate safe mode")}
          </Mark>
        </button>
        {error !== null && (
          <p>
            <MarkOf mark={error.mark}>{error.text}</MarkOf>
          </p>
        )}
      </div>
    </Fold>
  );
}

/**
 * Lo que corta la red: el modo seguro y, aparte, el freno HALT. Con cualquiera de los dos la red
 * no se rotula "abierta"; con los dos se ven los dos, porque se levantan por separado.
 */
export function NetworkStatus({
  state,
  haltOpen = false,
  onHaltToggle,
}: {
  state: SafeModeState;
  haltOpen?: boolean;
  onHaltToggle?: (() => void) | undefined;
}) {
  const halt = state.halt?.notice ?? null;
  // Motivo y persona, los que haya: sin ninguno no hay tooltip, no un «·» solo.
  const who = [state.reason, state.declared_by].filter((item) => item !== null && item !== "").join(" · ");
  return (
    <>
      {state.active ? (
        <Mark pictogram="shape-triangle" color="yellow" title={who === "" ? undefined : who}>
          {tr("Modo seguro · sin salida a internet", "Safe mode · no internet access")}
        </Mark>
      ) : (
        halt === null && (
          <Mark pictogram="door-open" className="secondary">
            {tr("abierta", "open")}
          </Mark>
        )
      )}
      <HaltNotice notice={halt} open={haltOpen} onToggle={onHaltToggle} />
    </>
  );
}

/** El `id` de la explicación desplegada en la página, al que apunta el mando de la franja. */
export const haltDetailsId = "halt-details";

/**
 * El aviso del freno HALT de Polaris, tal cual lo redacta el backend (`halt_notice`): que es,
 * desde cuando, que corta y que no. Sin freno, nada. Va en la franja comun, en las dos consolas:
 * que el freno esta puesto y desde cuando se ve sin abrir nada (F.4.2).
 *
 * En la franja, una linea: el triangulo con el titulo y el titular, la fecha y el mando con el
 * rotulo del backend que despliega lo demas (`HaltDetails`) dentro de la pagina, debajo de la
 * franja. Por que no en la franja (decision del usuario, 2026-10-22, §5.35.12): la franja es fija
 * arriba, y con la explicacion abierta en ella ocupaba unos 640 de 900 px (§5.34.15) y tapaba la
 * pagina que hay que mirar. Hasta §5.34.14 el resumen y el rotulo iban tambien a la vista, en tres
 * renglones apilados; despues, en un pliegue dentro de la franja.
 *
 * Amarillo con triangulo, como el modo seguro: tabla F.5-1, "off-nominal, attention required".
 * No es rojo (no ha fallado nada ni es una emergencia) ni cian: el dato no falta, lo que falta es
 * la salida a la red. La fecha, la del fichero, pasa por `formatUtc`; su rotulo del backend va como
 * `title` (para quien pase el raton) y, con la fecha, en la explicacion (un lector de pantalla o
 * una pantalla tactil no leen un `title`). El mando lleva el circulo con la i de «cómo leerlo»
 * (`howToRead`) y dice con `aria-expanded` si la explicacion esta desplegada.
 */
export function HaltNotice({
  notice,
  open = false,
  onToggle,
}: {
  notice: HaltNoticeText | null;
  open?: boolean;
  onToggle?: (() => void) | undefined;
}) {
  if (notice === null) return null;
  return (
    <div className="halt-notice">
      {/* Lo que se anuncia solo es el aviso; el mando va fuera de la region viva, a su lado. */}
      <span className="halt-line" role="status">
        <Mark pictogram="shape-triangle" color="yellow">
          {notice.title} · {notice.headline}
        </Mark>
        {notice.since !== null && (
          <span className="secondary num" title={notice.since_label}>
            {formatUtc(new Date(notice.since))}
          </span>
        )}
      </span>
      <Command
        type="button"
        concept="howToRead"
        aria-expanded={open}
        // Solo apunta a la explicacion cuando existe: cerrada no esta en la pagina.
        aria-controls={open ? haltDetailsId : undefined}
        onClick={onToggle}
      >
        {notice.details_label}
      </Command>
    </div>
  );
}

/**
 * La explicacion del freno, desplegada en la pagina y no en la franja fija (§5.35.12): lo que
 * sigue funcionando, el rotulo de la fecha con la fecha y la explicacion larga, tal cual las da
 * el backend. Va justo debajo de la franja (`StatusStrip`, que la pone detras de su `<header>`) y
 * se desplaza con la pagina; el mando que la cierra sigue en la franja, siempre a la vista.
 */
export function HaltDetails({ notice }: { notice: HaltNoticeText }) {
  const ref = useRef<HTMLElement>(null);
  // Al abrirla desde la franja con la pagina desplazada, la explicacion queda arriba, fuera de la
  // vista: se lleva justo debajo de la franja y recibe el foco, para que se vea (y se lea) que el
  // mando hizo algo. Solo al montarse: cada apertura la monta de nuevo.
  useEffect(() => {
    const section = ref.current;
    if (section === null) return;
    const above = section.previousElementSibling;
    const covered = above instanceof HTMLElement ? above.getBoundingClientRect().bottom : 0;
    const top = section.getBoundingClientRect().top;
    if (top < covered || top > window.innerHeight) window.scrollBy({ top: top - covered });
    section.focus({ preventScroll: true });
  }, []);
  return (
    <section ref={ref} tabIndex={-1} className="halt-details" id={haltDetailsId} aria-label={notice.details_label}>
      <p>{notice.summary}</p>
      {notice.since !== null && (
        <p className="secondary">
          {notice.since_label} <span className="num">{formatUtc(new Date(notice.since))}</span>
        </p>
      )}
      <ul>
        {notice.details.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </section>
  );
}
