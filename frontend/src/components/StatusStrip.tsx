import { type ReactNode, type RefObject, createContext, useContext, useEffect, useRef, useState } from "react";

import { causeMark, reducedMark } from "../dashboard/monitoring";
import { declaredLinkNotice } from "../habitat/systems";
import type { PictogramName } from "../icons";
import { ANNUNCIATION_MARKS, type AlertCounts } from "../lib/alerts";
import { DISCREPANCY_MARK, commsMark, commsStatusOf } from "../lib/commsStatus";
import type { CrewStatus, LinkSync } from "../lib/api";
import { formatMet, formatMinutes, formatNumber, missionElapsedSeconds } from "../lib/format";
import { LEVELS, LEVEL_ORDER, type Level } from "../lib/levels";
import { LINK_DOWN_MARK, groundLinkMark } from "../lib/linkSync";
import { freshnessOf } from "../lib/staleness";
import { LOADING_MARK, MISSING_MARK, OK_MARK } from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";
import { tr } from "../lib/i18n";
import { FieldLabel } from "./FieldLabel";
import { Mark, MarkOf } from "./Mark";
import { HaltDetails, SafeMode, SafeModeCommand, useNetworkWatch } from "./SafeMode";

/**
 * La franja comun: NASA-STD-3001 Vol 2, F.4.2, *"a common dedicated area for the
 * display of key information to be visible at all times (e.g., time, system
 * messages, alerts, communication status)"*. Es la misma en las dos consolas.
 *
 * Cada estado va con su pictograma junto a la palabra (§5.32): la celda lleva en su rotulo el
 * dibujo de lo que mide y en su valor el de su estado (la forma del nivel, el anillo punteado del
 * dato caducado, la marca de hecho o de fallo). El color sigue siendo el de la tabla F.5-1 y nunca
 * va solo. Desde la segunda pasada (§5.33.11) el dibujo de cada rotulo sale del vocabulario de la
 * interfaz (`lib/uiMarks.ts`), el mismo que lleva ese concepto en cualquier panel: reloj, faro de
 * la vigilancia, campana, arcos del retardo con Tierra, candado; «Modo», que no es un concepto de
 * ningun panel, lleva el mando giratorio de un selector (`icons/sets/shell.ts`). «EMMA» va sin
 * dibujo: delante del nombre seria un logotipo.
 *
 * Debajo de la franja, ya en la pagina, la explicacion del freno HALT cuando se despliega
 * (`HaltDetails`): la franja es fija arriba y no crece con ella (§5.35.12). El aviso en una linea y
 * su mando siguen en la franja.
 *
 * Franja compacta (§5.40, 2026-11-04): con la franja apilada (titulo, celdas, mandos de la voz, una
 * linea larga de atajos, «Red» y «Modo seguro», cada uno en su renglon) se iban unos 300 px de 900
 * antes de llegar a nada. Ahora todo va en una sola corriente que se parte en filas de alto fijo:
 * el titulo, las celdas y, al final, los mandos (`.strip-controls`). Lo que se abre desde un mando
 * (los atajos, el formulario del modo seguro) cuelga encima de la pagina y no hace crecer la franja.
 *
 * La concha de la maqueta (2026-11-07, decisión del usuario de hacerla consola): el tripulante y el
 * escenario vienen a la franja (`crew` y `tools`, delante de la voz), la celda del retardo dice además el
 * enlace simulado con Tierra caído o retenido (`sync`: la «señal» de la maqueta, con dato detrás) y
 * el título admite el logotipo de la maqueta (`brand`), que es adorno declarado en `compliance/`.
 *
 * La cabecera de la muestra (lote «muestra», 2026-11-08: «cabecera y menú como la muestra»): con el
 * logotipo (`brand`, solo en la concha nueva) la franja se pinta en dos filas. Arriba, el logotipo
 * grande con «EMMA» y su nombre largo, una barra y el lema (rótulos de la interfaz, no texto
 * clínico), y a la derecha los iconos grandes de la muestra: la red (la misma celda de siempre), la
 * campana con la suma de las alertas activas, «Ayuda» (abre los atajos de la voz, lo mismo que
 * «Atajos») y la ficha del tripulante (`crew`). Debajo, el título de la consola y el resto de celdas
 * de F.4.2 como fichas, y los mandos. Nada de lo que decía la franja se quita ni cambia de palabra
 * o de color: la campana repite una cifra que la celda «Alertas activas» sigue dando entera, clase a
 * clase. Sin el logotipo (la concha clásica, `#clasica`), la franja es la de antes.
 *
 * Tercera ronda (R3-2): esas dos filas medían 193 px a 1672 de ancho; la marca y el título pasaron a
 * la izquierda y el resto a una sola corriente a su lado, en dos filas de alto táctil (90 px).
 *
 * Cuarta ronda (R4-1): 90 px seguía siendo el doble que la muestra. Ahora son dos franjas
 * (`shell/header.css`). Arriba, la línea de lectura (`.masthead-status`): «Arriba» y las celdas de
 * F.4.2 (`.masthead-cells`), cada una con su dibujo, un rótulo corto a la vista y su valor en la
 * misma línea (`ShortLabel`: el rótulo entero va para el lector de pantalla y en el `title` de la
 * palabra corta). Debajo, la fila de alto táctil (`.masthead-bar`): la marca, el título, el lema y,
 * en `.masthead-tools`, los mandos y los iconos. El orden del documento es el de lectura, de arriba
 * abajo y de izquierda a derecha. Ninguna celda pierde valor, marca ni color.
 *
 * Quinta ronda (R5-1): con los textos reales esas dos franjas medían 126 px (la línea de lectura en
 * dos renglones y los mandos en dos filas). Ahora es una franja, como la muestra: a la izquierda, a
 * todo el alto, la marca; a la derecha (`.masthead-main`), arriba la línea de lectura y debajo el
 * título, los mandos y los iconos. Lectura, modo, alertas y registro enseñan solo su dibujo delante
 * del valor (`ShortLabel` sin palabra corta), y la vigilancia también (recortada por la hoja); el
 * retardo enseña la edad de sus efemérides.
 */
export function StatusStrip({
  status,
  loading,
  counts,
  consoleTitle,
  consolePictogram,
  controls = false,
  edge,
  voice,
  tools,
  sync = null,
  brand,
  crew,
  shortcuts = false,
  onAlerts,
}: {
  status: CrewStatus | null;
  loading: boolean;
  counts: AlertCounts;
  consoleTitle: string;
  /** El dibujo de la consola que se ve, el mismo que en su pestaña; sin el, solo el titulo. */
  consolePictogram?: PictogramName | undefined;
  /** Solo a bordo se cambia el modo seguro; Tierra ve el estado. */
  controls?: boolean;
  /** La referencia de «arriba» de la pantalla (§5.40): una fila propia en el borde de arriba. */
  edge?: ReactNode;
  /** «Leer en voz alta» (§5.40, components/ReadAloud.tsx): en la franja, a mano en las dos consolas. */
  voice?: ReactNode;
  /** El selector de tripulante y el escenario: con los mandos, delante de la voz. */
  tools?: ReactNode;
  /** El enlace simulado con Tierra (`GET /api/link-sync`): caído o retenido se dice junto al retardo. */
  sync?: LinkSync | null | undefined;
  /** El logotipo de la maqueta delante de «EMMA»; sin él, solo la palabra. Con él, la cabecera de la muestra. */
  brand?: ReactNode;
  /** El selector de tripulante: con la cabecera de la muestra, su ficha arriba a la derecha; sin ella, el primero de los mandos. */
  crew?: ReactNode;
  /** Si la voz pinta sus «Atajos» (solo con la voz disponible): entonces la cabecera lleva «Ayuda», que los abre. */
  shortcuts?: boolean;
  /**
   * Lo que hace la campana al pulsarla: llevar a la lista de alertas de la consola que se ve (lote
   * de arreglos, 2026-11-09: «la campana no enseña las alertas»). Sin él, la campana solo cuenta.
   */
  onAlerts?: (() => void) | undefined;
}) {
  const network = useNetworkWatch();
  const halt = network.state?.halt?.notice ?? null;
  // Se despliega la explicacion de un aviso concreto (su fecha, que es la del fichero, y su
  // texto), no "la del freno": si se quita y se vuelve a poner, aunque sea entre dos relecturas,
  // el aviso nuevo sale en su linea y no desplegado de antes.
  const haltKey = halt === null ? null : [halt.since ?? "", halt.title, halt.headline].join("|");
  const [openFor, setOpenFor] = useState<string | null>(null);
  const haltOpen = haltKey !== null && openFor === haltKey;
  const header = useRef<HTMLElement>(null);
  const help = useRef<HTMLButtonElement>(null);
  // Lo que se abre desde un mando de la franja cuelga encima de la pagina (`.strip-pop`): tocar
  // fuera lo cierra, para que no se quede tapando datos. Lo escrito en el formulario no se pierde
  // (el estado es del componente). Escape no: es de la voz (parar, y tres seguidos, la emergencia).
  useEffect(() => {
    const onDown = (event: PointerEvent) => {
      const root = header.current;
      if (root === null || !(event.target instanceof Node)) return;
      // «Ayuda» abre y cierra los atajos por su cuenta: tocarla no cuenta como tocar fuera de ellos,
      // pero sí de cualquier otro plegable abierto (el formulario del modo seguro se cierra).
      const onHelp = help.current?.contains(event.target) === true;
      for (const open of root.querySelectorAll<HTMLDetailsElement>("details.strip-pop[open]")) {
        if (onHelp && open.classList.contains("shortcuts")) continue;
        if (!open.contains(event.target)) open.open = false;
      }
    };
    document.addEventListener("pointerdown", onDown);
    return () => document.removeEventListener("pointerdown", onDown);
  }, []);
  // Sin voz y sin estado de la red aun, el mando del modo seguro no se pinta: no queda un grupo vacio.
  const command = controls && network.state !== null;
  const masthead = brand !== undefined;
  const title =
    consolePictogram === undefined ? consoleTitle : <Mark pictogram={consolePictogram}>{consoleTitle}</Mark>;
  const cells = (
    <CompactLabels.Provider value={masthead}>
        {loading ? (
          <MarkOf mark={LOADING_MARK} className="secondary">
            {tr("Cargando…", "Loading…")}
          </MarkOf>
        ) : status === null ? (
          <MarkOf mark={MISSING_MARK}>
            {tr("Sin datos del tripulante", "No data for this crew member")}
          </MarkOf>
        ) : (
          <>
            <MissionClock status={status} />
            <ModeTag mode={status.mission.mode} />
            <Monitoring monitoring={status.monitoring} />
            <Alerts counts={counts} />
            <Comms status={status} sync={sync} />
            <Integrity ok={status.data.integrity_ok} />
          </>
        )}
    </CompactLabels.Provider>
  );
  const net = (
    <SafeMode network={network} haltOpen={haltOpen} onHaltToggle={() => setOpenFor(haltOpen ? null : haltKey)} />
  );
  const crewInControls = masthead ? undefined : crew;
  // Los mandos, juntos al final de la fila: tripulante y escenario, la voz, sus atajos y el modo seguro.
  const commands = (crewInControls !== undefined || tools !== undefined || voice !== undefined || command) && (
    <div className="strip-controls">
      {crewInControls}
      {tools}
      {voice}
      {command && <SafeModeCommand network={network} />}
    </div>
  );
  return (
    <>
      <header className={masthead ? "strip strip-masthead" : "strip"} role="banner" ref={header}>
        {masthead ? (
          <>
            {/* A la izquierda, a todo el alto de la franja, la marca. El logotipo y el nombre largo
                de la muestra son rótulo, no dato: «EMMA» se ve aquí y el `h1` lo lleva solo para el
                lector de pantalla, con el título de siempre. */}
            <div className="masthead-brand">
              {brand}
              <span className="masthead-name">
                <span className="masthead-emma">EMMA</span>
                <span className="masthead-long">Environment and Medical Monitoring Assistant</span>
              </span>
            </div>
            {/* A la derecha, en el mismo alto, dos pisos: arriba la línea de lectura (la referencia
                de «arriba» y las celdas de F.4.2); debajo el título, el lema (adorno: solo si sobra
                ancho), los mandos y los iconos. */}
            <div className="masthead-main">
              <div className="masthead-status">
                {edge !== undefined && <div className="strip-edge">{edge}</div>}
                <div className="masthead-cells">{cells}</div>
              </div>
              <div className="masthead-bar">
                {/* F.4.2: el título único de la pantalla, junto a la marca, como el subtítulo de la muestra. */}
                <h1 className="title">
                  <span className="sr-only">EMMA · </span>
                  {title}
                </h1>
                <p className="masthead-motto">
                  {tr(
                    "Monitorización · Prevención · Rendimiento · Salud de la Tripulación",
                    "Monitoring · Prevention · Performance · Crew Health",
                  )}
                </p>
                <div className="masthead-tools">
                  {commands}
                  <div className="masthead-icons">
                    {net}
                    {!loading && status !== null && <AlertBell counts={counts} onOpen={onAlerts} />}
                    {shortcuts && <HelpButton header={header} button={help} />}
                    {crew !== undefined && <div className="masthead-crew">{crew}</div>}
                  </div>
                </div>
              </div>
            </div>
          </>
        ) : (
          <>
            {edge !== undefined && <div className="strip-edge">{edge}</div>}
            {/* F.4.2: cada pantalla con un titulo unico en un sitio fijo. Es el `h1` de la página: el
                lector de pantalla lo da como encabezado principal, y los paneles cuelgan de él en `h2`. */}
            <h1 className="title">EMMA · {title}</h1>
            {cells}
            {net}
            {commands}
          </>
        )}
      </header>
      {haltOpen && halt !== null && <HaltDetails notice={halt} />}
    </>
  );
}

/**
 * La campana de la muestra: la suma de las alertas activas (aviso, precaución y advertencia), la
 * misma cuenta que la celda «Alertas activas» da clase a clase. El globo solo sale si hay alguna, y
 * lleva la forma y el color de la clase más grave que haya, como su contador: el color nunca va
 * solo. A cero, la campana y su palabra, sin globo (un «0» en rojo sería color sin aviso).
 *
 * Con `onOpen` es un mando, como «Ayuda»: lleva a la lista de alertas (2026-11-09). Su nombre para el
 * lector de pantalla dice la cuenta y adónde lleva, que el globo solo lo dice a la vista. Sin él
 * queda la marca de siempre, que solo cuenta.
 */
export function AlertBell({ counts, onOpen }: { counts: AlertCounts; onOpen?: (() => void) | undefined }) {
  const classes = alertClasses(counts);
  const total = classes.reduce((sum, { count }) => sum + count, 0);
  // `alertClasses` va de la más grave a la menos: la primera con alguna activa.
  const top = classes.find(({ count }) => count > 0);
  const style = top === undefined ? null : LEVELS[LEVEL_OF_CLASS[top.alertClass]];
  const content = (
    <>
      <Mark pictogram={uiPictogram("alerts")}>{tr("Alertas", "Alerts")}</Mark>
      {style !== null && (
        <Mark pictogram={style.pictogram} color={style.color} className="bell-badge num">
          {formatNumber(total)}
        </Mark>
      )}
    </>
  );
  if (onOpen === undefined) return <span className="masthead-icon masthead-bell">{content}</span>;
  const label = tr(
    `Alertas: ${formatNumber(total)} ${total === 1 ? "activa" : "activas"}, ver`,
    `Alerts: ${formatNumber(total)} active, view`,
  );
  return (
    <button type="button" className="masthead-icon masthead-bell" aria-label={label} title={label} onClick={onOpen}>
      {content}
    </button>
  );
}

/**
 * «Ayuda», el signo de la muestra: abre y cierra el plegable «Atajos» de la voz (las teclas y el
 * gesto de emergencia), que sigue en su sitio y con su texto; este mando solo lo acerca. Si la voz
 * no está disponible no hay atajos que abrir, y la franja no lo pinta (`shortcuts`).
 */
function HelpButton({
  header,
  button,
}: {
  header: RefObject<HTMLElement | null>;
  button: RefObject<HTMLButtonElement | null>;
}) {
  const [open, setOpen] = useState(false);
  // Abiertos o cerrados desde su rótulo, desde «Ayuda» o al tocar fuera: el mando dice cómo están.
  useEffect(() => {
    const root = header.current;
    if (root === null) return;
    const onToggle = (event: Event) => {
      if (event.target instanceof HTMLDetailsElement && event.target.classList.contains("shortcuts")) {
        setOpen(event.target.open);
      }
    };
    root.addEventListener("toggle", onToggle, true);
    return () => root.removeEventListener("toggle", onToggle, true);
  }, [header]);
  return (
    <button
      ref={button}
      type="button"
      className="masthead-icon masthead-help"
      aria-expanded={open}
      onClick={() => {
        const shortcuts = header.current?.querySelector<HTMLDetailsElement>("details.shortcuts");
        if (shortcuts != null) shortcuts.open = !shortcuts.open;
      }}
    >
      <Mark pictogram={uiPictogram("howToRead")}>{tr("Ayuda", "Help")}</Mark>
    </button>
  );
}

/** Si las celdas van en la línea de lectura de la cabecera de la muestra (`ShortLabel`). */
const CompactLabels = createContext(false);

/**
 * El rótulo de una celda: en la cabecera de la muestra, a la vista la palabra corta (con el rótulo
 * entero en su `title`, para quien pase el ratón) y, para el lector de pantalla, solo el rótulo
 * entero de siempre, sin decir nada dos veces; en la franja clásica, el rótulo entero.
 *
 * Sin palabra corta (R5-1), en la cabecera de la muestra solo se ve el dibujo del rótulo, delante
 * de su valor, que ya dice lo que es («MET 39/…», «Simulación», «Reducida · 2 sin datos»,
 * «W 0 C 0 A 1», «Íntegro»): el
 * rótulo entero sigue para el lector de pantalla y, para el ratón, en el `title` de la celda
 * (`useCellTitle`). Así la línea de lectura cabe en un renglón encima de los mandos.
 */
function ShortLabel({ full, short }: { full: string; short?: string }) {
  if (!useContext(CompactLabels)) return <>{full}</>;
  if (short === undefined) return <span className="sr-only">{full}</span>;
  return (
    <>
      <span className="label-short" aria-hidden="true" title={full}>
        {short}
      </span>
      <span className="sr-only">{full}</span>
    </>
  );
}

/** El rótulo entero como `title` de la celda, solo si en la cabecera de la muestra se ve sin palabra. */
function useCellTitle(full: string): string | undefined {
  return useContext(CompactLabels) ? full : undefined;
}

function MissionClock({ status }: { status: CrewStatus }) {
  const at = new Date(status.data.reference_time);
  const met = formatMet(missionElapsedSeconds(status.mission.start, at));
  return (
    <div className="cell" title={useCellTitle(tr("Última lectura analizada", "Last reading analyzed"))}>
      <FieldLabel as="span" className="label" concept="time">
        <ShortLabel full={tr("Última lectura analizada", "Last reading analyzed")} />
      </FieldLabel>
      <span className="num">{met}</span>
    </div>
  );
}

const MODE_LABEL = {
  simulation: tr("Simulación", "Simulation"),
  mixed: tr("Mezcla: simulado y real", "Mixed: simulated and real"),
  mission: tr("Misión", "Mission"),
} as const;

/**
 * El dibujo de cada modo, con el significado que ya tiene como entorno de la evidencia
 * (`icons/sets/provenance.ts`, tabla de §5.32): la onda generada es lo simulado, el cohete el
 * vuelo real, y la mezcla lleva media onda y el disco lleno de lo medido.
 */
const MODE_PICTOGRAM: Record<CrewStatus["mission"]["mode"], PictogramName> = {
  simulation: "wave-zigzag",
  mixed: "wave-dot",
  mission: "rocket",
};

/** F.4.2: el modo simulacion tiene que verse distinto del de mision. */
function ModeTag({ mode }: { mode: CrewStatus["mission"]["mode"] }) {
  return (
    <div className="cell" title={useCellTitle(tr("Modo", "Mode"))}>
      <FieldLabel as="span" className="label" pictogram="knob-ticks">
        <ShortLabel full={tr("Modo", "Mode")} />
      </FieldLabel>
      <Mark pictogram={MODE_PICTOGRAM[mode]} className={mode === "mission" ? undefined : "mode-tag"}>
        {MODE_LABEL[mode]}
      </Mark>
    </div>
  );
}

/**
 * F.6.2: *"an indication of the current level of automation"*. La vigilancia se
 * reduce por dos causas que la tabla F.5-1 distingue: un dato que falta (cian,
 * "Missing or stale data") o una decision de la tripulacion (amarillo, "manual
 * override"). Una inhibicion no es un dato ausente, y no se pinta como tal.
 *
 * «Reducida» lleva la marca de su causa (`reducedMark`, la misma que el panel de vigilancia):
 * la del dato ausente si falta alguno, la de la decision manual si solo hay de esas, y la de
 * «desconocido» si el backend da una causa que la interfaz no conoce. Detras, cada causa contada
 * con su marca, porque pueden ser las dos.
 */
function Monitoring({ monitoring }: { monitoring: CrewStatus["monitoring"] }) {
  const missing = monitoring.capabilities.filter((item) => item.cause === "missing").length;
  const manual = monitoring.capabilities.filter((item) => item.cause === "manual").length;
  const reduced = reducedMark(monitoring.capabilities);
  return (
    // «Vigilancia» se escribe solo aquí, tal cual (`lib/wording.test.ts`): en la cabecera de la
    // muestra la recorta la hoja al ancho de su dibujo (`.cell-monitoring`), y la palabra sigue en el
    // texto para el lector de pantalla.
    <div className="cell cell-monitoring">
      <FieldLabel as="span" className="label" concept="monitoring">{tr("Vigilancia", "Monitoring")}</FieldLabel>
      {monitoring.level === "full" ? (
        <MarkOf mark={OK_MARK}>{tr("Completa", "Full")}</MarkOf>
      ) : (
        <span>
          <MarkOf mark={reduced}>{tr("Reducida", "Reduced")}</MarkOf>
          {missing > 0 && (
            <>
              {" · "}
              <MarkOf mark={MISSING_MARK}>
                <span className="num">{formatNumber(missing)}</span> {tr("sin datos", "without data")}
              </MarkOf>
            </>
          )}
          {manual > 0 && (
            <>
              {" · "}
              <MarkOf mark={causeMark("manual")}>
                <span className="num">{formatNumber(manual)}</span> {tr("por decisión manual", "by manual decision")}
              </MarkOf>
            </>
          )}
        </span>
      )}
    </div>
  );
}

type AlertClass = "W" | "C" | "A";

/**
 * Las clases de alerta activas con su cuenta, de la más grave a la menos: la misma lista para el
 * contador «Alertas activas» y para la campana de la cabecera, que no pueden decir cosas distintas.
 */
function alertClasses(counts: AlertCounts): readonly { alertClass: AlertClass; count: number }[] {
  return [
    { alertClass: "W", count: counts.warning },
    { alertClass: "C", count: counts.caution },
    { alertClass: "A", count: counts.advisory },
  ];
}

/**
 * El nivel de riesgo de cada clase de alerta del Apendice F (F.6.4), leido una vez de la tabla
 * de niveles al cargar el modulo: si una clase se quedara sin nivel fallaria aqui, al importar,
 * y no al pintar la franja.
 */
const LEVEL_OF_CLASS: Readonly<Record<AlertClass, Level>> = Object.fromEntries(
  (["W", "C", "A"] as const).map((alertClass) => {
    const level = LEVEL_ORDER.find((candidate) => LEVELS[candidate].alertClass === alertClass);
    if (level === undefined) throw new RangeError(`clase de alerta sin nivel: ${alertClass}`);
    return [alertClass, level];
  }),
) as Record<AlertClass, Level>;

/**
 * F.6.4: aviso, precaucion y advertencia activos, y los que nadie ha reconocido. Cada clase lleva
 * la forma y el color de su nivel cuando hay alguna; a cero, la forma en gris de texto secundario.
 * Nada parpadea aqui: el parpadeo es de la alerta critica en su fila, no del contador.
 */
function Alerts({ counts }: { counts: AlertCounts }) {
  const classes = alertClasses(counts);
  return (
    <div className="cell" title={useCellTitle(tr("Alertas activas", "Active alerts"))}>
      <FieldLabel as="span" className="label" concept="alerts">
        <ShortLabel full={tr("Alertas activas", "Active alerts")} />
      </FieldLabel>
      <span className="counts num">
        {classes.map(({ alertClass, count }) => {
          const style = LEVELS[LEVEL_OF_CLASS[alertClass]];
          return (
            <Mark
              key={alertClass}
              pictogram={style.pictogram}
              color={count > 0 ? style.color : null}
              className={count > 0 ? undefined : "secondary"}
            >
              {alertClass} {count}
            </Mark>
          );
        })}
        <Mark pictogram="box-empty" className="secondary">
          {tr("sin reconocer", "unacknowledged")} {counts.unacknowledged}
        </Mark>
        {/* Lo silenciado se ve siempre: nunca debe parecer que no hay alertas. Con la marca de su
            anuncio, la misma que en la fila de la alerta (`lib/alerts.ts`): la campana tachada de
            lo suprimido y la campana enmarcada de lo inhibido, que hasta la segunda pasada
            llevaba aqui tambien la tachada. */}
        {counts.suppressed > 0 && (
          <MarkOf mark={ANNUNCIATION_MARKS.suppressed}>
            {tr("suprimidas", "suppressed")} {counts.suppressed}
          </MarkOf>
        )}
        {counts.inhibited > 0 && (
          <MarkOf mark={ANNUNCIATION_MARKS.inhibited}>
            {tr("inhibidas", "inhibited")} {counts.inhibited}
          </MarkOf>
        )}
      </span>
    </div>
  );
}

/**
 * Estado de comunicaciones. Sin efemerides, el retardo no se inventa: se dice
 * que falta, en cian (tabla F.5-1, "Missing or stale data"); caducado, la cifra se
 * conserva y lleva el mismo cian con el anillo punteado. El rotulo lleva los arcos de la señal
 * (`lightTime`), no el globo: el globo es Tierra como entorno de la evidencia, y lo que se mide
 * aqui es el retardo. Debajo, si una persona declaro el enlace degradado o caido, lo que declaro
 * (`DeclaredLinkLine`): el «communication status» de F.4.2 que EMMA no mide y si puede decir.
 */
function Comms({ status, sync }: { status: CrewStatus; sync: LinkSync | null }) {
  const state = freshnessOf(status.freshness?.comms);
  // El estado del retardo lo dice el backend (`comms_status`, 2026-11-11): «Sin efemérides» en cian
  // solo si de verdad falta; un perfil sin objetivo, «No aplica» en gris; con retardo, su fuente.
  const comms = commsStatusOf(status);
  const link = (
    <>
      <DiscrepancyLine status={status} />
      <DeclaredLinkLine status={status} />
      {sync !== null && <SimulatedLinkLine sync={sync} />}
    </>
  );
  if (status.comms === null) {
    return (
      <div className="cell">
        <FieldLabel as="span" className="label" concept="lightTime">
          <ShortLabel full={tr("Retardo con Tierra", "Delay to Earth")} short={tr("Retardo", "Delay")} />
        </FieldLabel>
        <MarkOf mark={commsMark(comms.state)} title={comms.text === comms.word ? undefined : comms.text}>
          {comms.word}
        </MarkOf>
        {link}
      </div>
    );
  }
  const delay = (
    <>
      {tr("ida", "one way")} {formatMinutes(status.comms.one_way_minutes)} · {tr("ida y vuelta", "round trip")}{" "}
      {formatMinutes(status.comms.round_trip_minutes)}
    </>
  );
  // La edad de las efemérides es dato: también a la vista en la cabecera de la muestra, donde va sola
  // detrás de los arcos de la señal (R5-1: «Retardo · » no cabía en el renglón; «ida … · ida y
  // vuelta …» ya dice qué es la cifra, y la palabra entera sigue para el lector y en el `title`).
  const dated = status.comms_data_age ?? tr("sin fecha", "undated");
  const age = tr(`efemérides ${dated}`, `ephemeris ${dated}`);
  // La fuente del retardo (SPICE en local o JPL Horizons), en la palabra entera del rótulo.
  const source = comms.source_text === null ? "" : ` · ${comms.source_text}`;
  return (
    <div className="cell">
      <FieldLabel as="span" className="label" concept="lightTime">
        <ShortLabel full={`${tr("Retardo con Tierra", "Delay to Earth")}${source} · ${age}`} short={age} />
      </FieldLabel>
      {state === "fresh" ? (
        <span className="num">{delay}</span>
      ) : (
        <MarkOf mark={MISSING_MARK} className="num">
          {delay}
        </MarkOf>
      )}
      {link}
    </div>
  );
}

/**
 * La discrepancia del cálculo local (SPICE) con JPL Horizons del día (2026-11-11), debajo del
 * retardo, en las dos consolas: la palabra del backend con el triángulo en amarillo (dato
 * contradictorio, F.5-1 «attention required»), y su frase entera en el `title`. Sin discrepancia no
 * hay línea, y la franja no crece.
 */
function DiscrepancyLine({ status }: { status: CrewStatus }) {
  const discrepancy = commsStatusOf(status).discrepancy;
  if (discrepancy === null) return null;
  return (
    <MarkOf mark={DISCREPANCY_MARK} className="link-declared" title={discrepancy.text}>
      {discrepancy.word}
    </MarkOf>
  );
}

/**
 * El enlace con Tierra declarado degradado o fuera de servicio (KB §2.1), debajo del retardo: la
 * frase corta del backend, con quién y desde cuándo y el rótulo «declarado por una persona, no
 * telemetría», y la marca de su estado del panel de sistemas. Solo texto: la cifra del retardo es
 * la de las efemérides y no cambia. Sin nada que señalar no hay línea, y la franja no crece. La
 * línea va acotada en ancho (`.link-declared`): parte en renglones en vez de ensanchar la celda y
 * empujar las demás a otra fila.
 */
function DeclaredLinkLine({ status }: { status: CrewStatus }) {
  const notice = declaredLinkNotice(status.declared_link);
  if (notice === null) return null;
  return (
    <MarkOf mark={notice.mark} className="link-declared">
      {notice.headline}
    </MarkOf>
  );
}

/**
 * El enlace simulado con Tierra (§5.47, `lib/linkSync.ts`), debajo del retardo: caído, con la marca
 * de lo fuera de servicio y la palabra del backend; restablecido pero con el corte de Tierra aún
 * retenido en la caída, con la marca del dato que falta. Arriba y al día, nada: la franja no crece.
 */
function SimulatedLinkLine({ sync }: { sync: LinkSync }) {
  const mark = sync.state === "down" ? LINK_DOWN_MARK : groundLinkMark(sync);
  if (mark === null) return null;
  return (
    <MarkOf mark={mark} className="link-declared">
      {sync.state_display}
    </MarkOf>
  );
}

/** Si la cadena firmada no verifica, se ve aqui, en rojo, en todas las pantallas. */
function Integrity({ ok }: { ok: boolean }) {
  return (
    <div className="cell" title={useCellTitle(tr("Registro firmado", "Signed ledger"))}>
      <FieldLabel as="span" className="label" concept="signedLedger">
        <ShortLabel full={tr("Registro firmado", "Signed ledger")} />
      </FieldLabel>
      {/* La rotura del registro firmado es su propia señal (cruz en rojo), no la de una
          peticion que fallo: escrita aqui, para que un ajuste de `FAILURE_MARK` no la arrastre. */}
      {ok ? (
        <MarkOf mark={OK_MARK}>{tr("Íntegro", "Intact")}</MarkOf>
      ) : (
        <Mark pictogram="cross" color="red">
          {tr("Integridad comprometida", "Integrity compromised")}
        </Mark>
      )}
    </div>
  );
}
