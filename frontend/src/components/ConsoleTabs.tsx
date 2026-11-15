import {
  type KeyboardEvent,
  type ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";

import type { PictogramName } from "../icons/registry";
import { type AlertCounts } from "../lib/alerts";
import { formatNumber } from "../lib/format";
import { LEVELS, LEVEL_ORDER, type Level } from "../lib/levels";
import { uiPictogram } from "../lib/uiMarks";
import { EarthNightArt, SectionArt } from "../dashboard/HomeArt";
import { BoardOnly, useLook } from "./BoardOnly";
import { Command } from "./Command";
import { DisplayControls, useDisplayModes } from "./DisplayControls";
import {
  type RailPlacement,
  type Rotation,
  browserStore,
  nextTabIndex,
  railPlacement,
  readSection,
  resolveSection,
  writeSection,
} from "./displayModes";
import { Fold } from "./Fold";
import { Mark } from "./Mark";

/**
 * El armazón de pestañas de cada consola (§5.40): un carril lateral, como el de una tableta, con
 * las secciones en vertical y su contenido al lado. Lo pidieron las notas de voz del equipo
 * (2026-11): «una interfaz tipo tablet con pestañas laterales».
 *
 * Por qué una tabla declarativa: los paneles iban uno tras otro en cada consola, y otras unidades
 * los añaden en paralelo. Cada consola declara aquí su lista `sección → paneles`; añadir un panel
 * es añadir una línea a la lista de su sección, sin tocar este fichero ni el panel.
 *
 * Lo que no cambia: la franja común sigue fija arriba con los contadores de alertas (F.4.2,
 * F.6.4), así que una alerta sin reconocer se ve sea cual sea la pestaña; y la pestaña que contiene
 * la lista de alertas lleva además su recuento, con la forma y el color de su nivel y la misma
 * palabra que la franja. Aquí no se redacta ningún nivel ni ningún texto clínico: los rótulos son
 * de navegación.
 *
 * Accesibilidad: `role="tablist"` con `aria-orientation="vertical"` (`"horizontal"` cuando el carril
 * va arriba), tabulación itinerante (solo la pestaña abierta entra en el orden del tabulador) y
 * flechas, Inicio y Fin (`nextTabIndex`, que acepta las cuatro flechas en los dos casos).
 * La pestaña abierta se marca con la barra lateral y la negrita, no solo con el color. La sección
 * abierta se guarda en el equipo (`displayModes.ts`).
 */

/**
 * Lo que va en lo alto del carril, encima de las pestañas: en la concha de la maqueta (`App` con
 * `look="reference"`, 2026-11-07), el conmutador de consola, que así es la primera entrada de la barra
 * lateral. Por contexto y no por prop: las dos consolas montan el carril sin saberlo, y la de Tierra
 * no se toca. Sin valor, el carril empieza por las pestañas, como siempre.
 */
export const RailTopContext = createContext<ReactNode>(null);

/** Una pieza de la lista de paneles: el panel, o el panel marcado como personal. */
export type PanelEntry = ReactNode | { readonly personal: ReactNode };

/** Marca un panel como personal: en modo privacidad se tapa aunque su sección quede a la vista. */
export function personal(panel: ReactNode): PanelEntry {
  return { personal: panel };
}

function isPersonal(entry: PanelEntry): entry is { readonly personal: ReactNode } {
  return typeof entry === "object" && entry !== null && !Array.isArray(entry) && "personal" in entry;
}

export interface ConsoleSection {
  /** Clave estable: la que se guarda como sección abierta. */
  key: string;
  /** Rótulo de navegación de la pestaña. */
  label: string;
  pictogram: PictogramName;
  /** Grupo del carril; sin grupo, el primero (las secciones de la consola). */
  group?: string;
  /** Una línea secundaria bajo el rótulo (p. ej. «entorno de la misión»). */
  note?: ReactNode;
  /** Visible en modo esencial: lo imprescindible para actuar. */
  essential?: boolean;
  /**
   * Apartada de esta versión (decisión del usuario, 2026-11-15): la pestaña no se monta ni se
   * ofrece, y su código se queda. El inventario del asistente la marca igual (`set_aside` en
   * `backend/app/data/assistant_ui.json`); lo comprueba `assistant/uiInventory.test.ts`.
   */
  setAside?: boolean;
  /** Contiene la lista de alertas: lleva su recuento en la pestaña. */
  alerts?: boolean;
  /** A la vista en modo privacidad (alertas y estado general), salvo sus paneles `personal`. */
  shared?: boolean;
  /** Clases extra del cuerpo de la sección: «Inicio» monta sus paneles en la rejilla de la maqueta. */
  className?: string;
  panels: readonly PanelEntry[];
}

/** Consolas ya montadas desde que se abrió la página. */
const mountedThisPage = new Set<string>();

/**
 * La sección abierta de una consola, guardada en el equipo. Al abrir la página se empieza siempre por
 * la primera («Inicio»): Ellande quiere entrar directamente ahí, no en la última que quedó abierta
 * (2026-11-09). Lo guardado sigue valiendo al volver a una consola sin recargar.
 */
export function useStoredSection(consoleId: string): [string | null, (key: string) => void] {
  const [stored, setStored] = useState<string | null>(() => {
    if (!mountedThisPage.has(consoleId)) {
      mountedThisPage.add(consoleId);
      return null;
    }
    return readSection(browserStore(), consoleId);
  });
  const choose = useCallback(
    (key: string) => {
      setStored(key);
      writeSection(browserStore(), consoleId, key);
    },
    [consoleId],
  );
  return [stored, choose];
}

/** El tamaño de la ventana, que cambia al girar la tableta o redimensionar. */
function subscribeResize(changed: () => void): () => void {
  window.addEventListener("resize", changed);
  return () => window.removeEventListener("resize", changed);
}

/**
 * Dónde va el carril ahora (`railPlacement`): al lado en una tableta apaisada o un escritorio, arriba
 * en una tableta en vertical. Sin ventana (pruebas sin navegador), al lado.
 */
export function useRailPlacement(rotation: Rotation, lowVision: boolean): RailPlacement {
  // La instantánea es ya el sitio, no el tamaño: arrastrar el borde de la ventana no repinta las
  // secciones mientras el carril no cambia de sitio.
  return useSyncExternalStore(
    subscribeResize,
    () => railPlacement(window.innerWidth, window.innerHeight, rotation, lowVision),
    () => "side",
  );
}

/** Las secciones de esta versión: todas menos las apartadas (`setAside`). */
export function shippedSections(sections: readonly ConsoleSection[]): ConsoleSection[] {
  return sections.filter((section) => section.setAside !== true);
}

/**
 * Las secciones a la vista con los modos de ahora: las de esta versión y, en modo esencial, solo
 * las esenciales.
 */
export function visibleSections(sections: readonly ConsoleSection[], essential: boolean): ConsoleSection[] {
  const shipped = shippedSections(sections);
  return essential ? shipped.filter((section) => section.essential === true) : shipped;
}

export function ConsoleTabs({
  id,
  label,
  sections,
  counts,
  header,
  headerGroup,
  stored,
  onChoose,
}: {
  /** Prefijo de los `id` y clave de la sección guardada: `crew` o `ground`. */
  id: string;
  /** Nombre del carril para el lector de pantalla. */
  label: string;
  sections: readonly ConsoleSection[];
  counts: AlertCounts;
  /** Lo que va encima de las pestañas: el entorno activo de la misión. */
  header?: ReactNode;
  /**
   * El grupo cuyas pestañas se eligen en la cabecera, debajo de `header`, y no en el carril: los
   * entornos se eligen donde se dice el entorno de la misión (`dashboard/Environments.tsx`).
   */
  headerGroup?: string;
  stored: string | null;
  onChoose: (key: string) => void;
}) {
  const { modes, update, namesMasked = true } = useDisplayModes();
  const railTop = useContext(RailTopContext);
  const visible = visibleSections(sections, modes.essential);
  const visibleKeys = visible.map((section) => section.key);
  const activeKey = resolveSection(visibleKeys, stored);
  // Lo que oculta el modo esencial: una pestaña apartada no cuenta, no vuelve al quitarlo.
  const hidden = shippedSections(sections).length - visible.length;
  const buttons = useRef(new Map<string, HTMLButtonElement>());
  const placement = useRailPlacement(modes.rotation, modes.lowVision);
  const board = useLook() === "reference";

  // Si la guardada no está a la vista se abre otra, y esa queda como elegida: si no, la guardada
  // podría aparecer después (las pestañas de entorno llegan con su petición) y la consola saltaría
  // sola a ella mientras alguien lee las alertas.
  useEffect(() => {
    if (activeKey !== null && activeKey !== stored) onChoose(activeKey);
  }, [activeKey, stored, onChoose]);

  // Las secciones ya abiertas siguen montadas, ocultas: cambiar de pestaña para reconocer una
  // alerta no pierde una medida guiada, una prueba en curso ni un borrador (§5.40).
  const [opened, setOpened] = useState<ReadonlySet<string>>(() => new Set());
  const mounted = activeKey === null || opened.has(activeKey) ? opened : new Set([...opened, activeKey]);
  useEffect(() => {
    if (mounted !== opened) setOpened(mounted);
  }, [mounted, opened]);

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const next = nextTabIndex(visible.length, index, event.key);
    if (next === null) return;
    const target = visible[next];
    if (target === undefined) return;
    event.preventDefault();
    onChoose(target.key);
    const button = buttons.current.get(target.key);
    // Una pestaña de entorno con su pliegue cerrado (en la concha nueva se cierra al salir de ellos)
    // no toma el foco: se abre antes, y su `toggle` pone el estado al día.
    const fold = button?.closest("details");
    if (fold != null && !fold.open) fold.open = true;
    button?.focus();
  };

  const groups: { name: string | undefined; items: { section: ConsoleSection; index: number }[] }[] = [];
  visible.forEach((section, index) => {
    const last = groups[groups.length - 1];
    if (last !== undefined && last.name === section.group) last.items.push({ section, index });
    else groups.push({ name: section.group, items: [{ section, index }] });
  });

  // En la cabecera, el grupo va sin su nombre a la vista: ya lo dice «Entorno de la misión».
  const tabList = (group: (typeof groups)[number], inHeader = false) => {
    // Tabulación itinerante por grupo: cada lista de pestañas tiene una en el orden del
    // tabulador, la abierta o, si la abierta es de otro grupo, la primera.
    const holdsActive = group.items.some(({ section }) => section.key === activeKey);
    return (
      <div className="rail-group" key={group.name ?? ""}>
        {group.name !== undefined && !inHeader && <p className="rail-group-name secondary">{group.name}</p>}
        <div
          role="tablist"
          aria-orientation={placement === "top" ? "horizontal" : "vertical"}
          aria-label={group.name ?? label}
          className="rail-tabs"
        >
          {group.items.map(({ section, index }, position) => {
            const selected = section.key === activeKey;
            const tabbable = selected || (!holdsActive && position === 0);
            return (
              <button
                key={section.key}
                ref={(element) => {
                  if (element === null) buttons.current.delete(section.key);
                  else buttons.current.set(section.key, element);
                }}
                type="button"
                role="tab"
                id={`${id}-tab-${section.key}`}
                aria-controls={`${id}-panel-${section.key}`}
                aria-selected={selected}
                tabIndex={tabbable ? 0 : -1}
                // En la cabecera de la concha nueva, cada entorno con su nombre entero en el `title`: el de
                // la aclaración, que no se ve, y el de los demás, para que no hereden el del pliegue.
                title={inHeader && board ? section.label : undefined}
                onClick={() => onChoose(section.key)}
                onKeyDown={(event) => onKeyDown(event, index)}
              >
                <Mark pictogram={section.pictogram}>{tabLabel(section.label, inHeader && board)}</Mark>
                {section.note !== undefined && <span className="tab-note secondary">{section.note}</span>}
                {section.alerts === true && <TabAlerts counts={counts} />}
              </button>
            );
          })}
        </div>
      </div>
    );
  };

  // Las pestañas de la cabecera (los entornos) van plegadas bajo «Entorno de la misión»: abiertas,
  // los cinco entornos con rótulos de dos líneas se comían el carril o, arriba, media pantalla. Se
  // abren al tocar el rótulo, y solas mientras se mira uno de ellos.
  const headerItems = groups.filter((group) => headerGroup !== undefined && group.name === headerGroup);
  const headerActive = headerItems.some((group) => group.items.some(({ section }) => section.key === activeKey));
  const [headerOpen, setHeaderOpen] = useState(headerActive);
  // En la concha nueva, se cierran al dejar el entorno por otra pestaña (lote «muestra», 2026-11-08):
  // abiertos se quedaban para siempre y los cinco entornos empujaban las pestañas de la consola fuera
  // de la vista. La clásica sigue como estaba.
  const wasHeaderActive = useRef(headerActive);
  useEffect(() => {
    if (headerActive) setHeaderOpen(true);
    else if (wasHeaderActive.current && board) setHeaderOpen(false);
    wasHeaderActive.current = headerActive;
  }, [headerActive, board]);

  // En la concha nueva, el conmutador de consola y el entorno de la misión van en una sola franja fina
  // sobre el menú (lote «muestra», ronda 4, 2026-11-08): la muestra no tiene cajas encima del menú y
  // EMMA tenía dos. El rótulo del pliegue de los entornos queda en el texto del `<summary>` (lo lee el
  // lector de pantalla y lo dice el `title`); en la franja se ve su dibujo, al lado del entorno.
  const strip = board && railTop !== null;
  const top = railTop !== null && <div className="rail-top">{railTop}</div>;
  const headerBox = (header !== undefined || groups.some((group) => group.name === headerGroup)) && (
    <div className="rail-header">
      {header}
      {headerItems.length > 0 && (
        <Fold
          data-ui="environment-choices"
          concept="compare"
          className="rail-header-choices"
          label={strip ? <span className="rail-choices-word">Ver o elegir otro entorno</span> : "Ver o elegir otro entorno"}
          title={strip ? "Ver o elegir otro entorno" : undefined}
          open={headerOpen}
          onToggle={(event) => {
            const now = event.currentTarget.open;
            if (now !== headerOpen) setHeaderOpen(now);
          }}
        >
          {headerItems.map((group) => tabList(group, true))}
        </Fold>
      )}
    </div>
  );

  return (
    <div className="console-layout" data-rail={placement}>
      <nav className="rail" aria-label={label}>
        {strip ? (
          <div className="rail-strip">
            {top}
            {headerBox}
          </div>
        ) : (
          <>
            {top}
            {headerBox}
          </>
        )}
        {groups.filter((group) => headerGroup === undefined || group.name !== headerGroup).map((group) => tabList(group))}
        {/* Al pie del carril, plegados: el carril es de las pestañas (§5.40). */}
        <DisplayControls folded />
        {/* La Tierra de noche al pie del carril, en el hueco que dejan las pestañas (adorno de la muestra):
            va la última y solo ocupa lo que sobra, así que nunca queda detrás de un texto. */}
        {board && <EarthNightArt />}
      </nav>
      <div className="console-panels">
        {modes.essential && (
          <p className="panel mode-notice">
            <Mark pictogram={uiPictogram("essential")}>
              Modo esencial: solo lo necesario para actuar.{" "}
              <span className="num">{formatNumber(hidden)}</span> secciones ocultas.
            </Mark>{" "}
            <Command concept="essential" onClick={() => update({ essential: false })}>
              Ver todas las secciones
            </Command>
          </p>
        )}
        {modes.privacy && (
          <p className="panel mode-notice">
            <Mark pictogram={uiPictogram("privacy")}>
              {namesMasked
                ? "Privacidad activa: nombres, notas y paneles personales tapados, también los nombres dentro de las frases. El estado general y las alertas, con sus motivos, quedan a la vista."
                : "Privacidad activa: este navegador no sabe tapar solo los nombres dentro de las frases, así que todas las secciones quedan tapadas."}
            </Mark>{" "}
            <Command concept="privacy" onClick={() => update({ privacy: false })}>
              Quitar privacidad
            </Command>
          </p>
        )}
        {sections
          .filter((section) => mounted.has(section.key))
          .map((section) => {
            const shown = section.key === activeKey && visibleKeys.includes(section.key);
            return (
              <div
                key={section.key}
                className={section.className === undefined ? "section-body" : `section-body ${section.className}`}
                role="tabpanel"
                id={`${id}-panel-${section.key}`}
                aria-labelledby={`${id}-tab-${section.key}`}
                hidden={!shown}
              >
                {/* Tablero: el marco titulado de la sección, como «Panel global» en «Inicio». Solo adorno:
                    el lector de pantalla ya oye el nombre en la pestaña que etiqueta el cuerpo. */}
                {section.className === undefined && (
                  <BoardOnly>
                    <p className="board-frame-h" aria-hidden="true">
                      <Mark pictogram={section.pictogram}>{section.label}</Mark>
                      <SectionArt section={section.key} console={id} />
                    </p>
                  </BoardOnly>
                )}
                {section.panels.map((entry, index) => {
                  const panel = isPersonal(entry) ? entry.personal : entry;
                  // Un hueco de la tabla (`cond && <Panel/>` que no se cumple) no se tapa: no hay nada.
                  if (panel === null || panel === undefined || panel === false) return null;
                  // Sin poder tapar solo los nombres de las frases, lo compartido se tapa entero.
                  const covered =
                    modes.privacy && (section.shared !== true || isPersonal(entry) || !namesMasked);
                  return (
                    <Slot key={index} covered={covered}>
                      {panel}
                    </Slot>
                  );
                })}
              </div>
            );
          })}
      </div>
    </div>
  );
}

/**
 * Dónde empieza la aclaración entre paréntesis de un rótulo («Órbita baja terrestre (estación
 * espacial)»), o `null` si no la lleva.
 */
export function asideAt(label: string): number | null {
  const at = label.lastIndexOf(" (");
  if (at <= 0 || !label.endsWith(")")) return null;
  // Solo la última aclaración, y entera: sin otro paréntesis dentro.
  return /[()]/.test(label.slice(at + 2, -1)) ? null : at;
}

/**
 * El rótulo de una pestaña. En la cabecera de la concha nueva (`short`), los entornos van en filas de
 * una línea, como los de la muestra: la aclaración entre paréntesis sigue en el texto de la pestaña
 * (`tab-aside`, fuera de la vista pero en lo que lee el lector de pantalla y busca el asistente) y en
 * su `title`, y se ve entera en el cuerpo del entorno.
 */
function tabLabel(label: string, short: boolean): ReactNode {
  const at = short ? asideAt(label) : null;
  if (at === null) return label;
  return (
    <>
      {label.slice(0, at)}
      <span className="tab-aside sr-only">{label.slice(at)}</span>
    </>
  );
}

/**
 * El sitio de un panel. Con la privacidad, difuminado, fuera del foco y del lector de pantalla
 * (`inert`), con la palabra encima; sin ella, las dos cajas no cuentan para la maqueta
 * (`display: contents`). El árbol es el mismo en los dos casos: poner o quitar la privacidad no
 * desmonta el panel, que queda como estaba (lo que se estaba escribiendo, incluido).
 */
function Slot({ covered, children }: { covered: boolean; children: ReactNode }) {
  return (
    <div className={covered ? "slot privacy-cover" : "slot"}>
      <div
        className={covered ? "slot-body privacy-blur" : "slot-body"}
        inert={covered}
        aria-hidden={covered ? true : undefined}
      >
        {children}
      </div>
      {covered && (
        <p className="privacy-label">
          <Mark pictogram={uiPictogram("privacy")}>Tapado por privacidad</Mark>
        </p>
      )}
    </div>
  );
}

/** El nivel de cada clase de alerta de F.6.4, de la misma tabla que la franja (`lib/levels.ts`). */
const LEVEL_OF_CLASS = Object.fromEntries(
  LEVEL_ORDER.flatMap((level) => {
    const alertClass = LEVELS[level].alertClass;
    return alertClass === null ? [] : [[alertClass, level]];
  }),
) as Record<"W" | "C" | "A", Level>;

/**
 * El recuento de alertas en su pestaña: las activas con la forma y el color del nivel más alto
 * que hay (tabla F.5-1, la misma de la franja) y las que nadie ha reconocido, con la misma palabra
 * que la franja. Sin alertas, nada. No parpadea: el parpadeo es de la fila de la alerta crítica.
 */
export function TabAlerts({ counts }: { counts: AlertCounts }) {
  const active = counts.warning + counts.caution + counts.advisory;
  if (active === 0) return null;
  const top = LEVELS[LEVEL_OF_CLASS[counts.warning > 0 ? "W" : counts.caution > 0 ? "C" : "A"]];
  return (
    <span className="tab-alerts">
      <Mark pictogram={top.pictogram} color={top.color}>
        <span className="num">{formatNumber(active)}</span> activas
      </Mark>
      {counts.unacknowledged > 0 && (
        <Mark pictogram="box-empty" className="secondary">
          sin reconocer <span className="num">{formatNumber(counts.unacknowledged)}</span>
        </Mark>
      )}
    </span>
  );
}
