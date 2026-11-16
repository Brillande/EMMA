import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { showRowOf } from "./components/RowPages";
import { About } from "./About";
import { Assistant } from "./assistant/Assistant";
import type { IntentEffects, TabRef } from "./assistant/intents";
import {
  PANEL_COVERED,
  PANEL_NOT_FOUND,
  UI_ATTRIBUTE,
  clickTab,
  covered,
  findPanel,
  readableLines,
  reveal,
  tabElement,
  topPanels,
  untilFound,
} from "./assistant/uiTargets";
import { silenceFor } from "./assistant/proactive";
import { useProactive } from "./assistant/useProactive";
import { AlertAnnouncer } from "./components/AlertAnnouncer";
import { Command } from "./components/Command";
import { RailTopContext } from "./components/ConsoleTabs";
import { EmergencyVoice } from "./components/EmergencyVoice";
import { HelpBanner } from "./components/HelpBanner";
import {
  DisplayControls,
  DisplayModesContext,
  ScreenTop,
  usePrivateNameMask,
  useStoredDisplayModes,
} from "./components/DisplayControls";
import { FieldLabel } from "./components/FieldLabel";
import { Mark, MarkOf } from "./components/Mark";
import { PanelTitle } from "./components/PanelTitle";
import { ReadAloud, VoiceAvailabilityContext, useSpeaker, useVoiceShortcut } from "./components/ReadAloud";
import { StatusStrip } from "./components/StatusStrip";
import { CrewConsole } from "./dashboard/CrewConsole";
import { type ConsoleLook, LookContext } from "./components/BoardOnly";
import { BrandLogo, Gradients, StarField } from "./dashboard/HomeArt";
import { GroundConsole } from "./ground/GroundConsole";
import type { PictogramName } from "./icons";
import { type ConsoleKey, useConsoleData } from "./dashboard/useConsoleData";
import { type Scenario, type UiPlace, api } from "./lib/api";
import { tr } from "./lib/i18n";
import { domainLabel, levelStyle } from "./lib/levels";
import { LOADING_MARK, type RequestOutcome, UNKNOWN_MARK, requestOutcome } from "./lib/marks";
import { storedOperator } from "./lib/operator";
import { requestOrientationPermission } from "./lib/orientation";
import { applyPalette } from "./lib/palette";
import { namesMaskable, privateNames } from "./lib/privacyNames";
import { newAlertSpeech, newAlerts, spokenAlert, statusSpeech } from "./lib/speech";
import "./consoleShell.css";
import "./shell/index.css";

/**
 * El aspecto de la concha: «classic», la de pestañas de siempre, o «reference», la de la maqueta
 * «Panel EMMA: Rutas Espaciales y Salud» (decisión del usuario, 2026-11-07, de hacerla consola): fondo,
 * cabecera, barra lateral y tarjetas de la maqueta (`consoleShell.css`) sobre el mismo armazón, con el
 * conmutador de consola en lo alto del carril. Lo decide `main.tsx` al arrancar.
 */
export type { ConsoleLook };

const CONSOLES: Record<ConsoleKey, string> = {
  crew: tr("Consola de tripulación", "Crew console"),
  ground: tr("Consola de Tierra", "Earth console"),
};

// El dibujo de cada consola, en su pestaña y en el titulo de la franja: el casco para quien
// esta a bordo y el globo, que ya significa «Tierra» como entorno de la evidencia
// (`icons/sets/provenance.ts`, tabla de §5.32).
const CONSOLE_PICTOGRAMS: Record<ConsoleKey, PictogramName> = {
  crew: "helmet",
  ground: "globe",
};

// Nombres de los escenarios del simulador ante el usuario; la clave es la de la API.
// Exportados, con sus dibujos y el almacen vacio, para que `App.test.ts` los mire por separado.
// Los dibujos van en una tabla aparte (`SCENARIO_PICTOGRAMS`), no en esta: `lib/wording.test.ts`
// declara el literal `nominal: "Nominal"` de aqui carácter a carácter, y `App.test.ts` vigila
// que las dos tablas tengan las mismas claves.
export const SCENARIO_LABELS: Record<string, string> = {
  nominal: "Nominal",
  "spe-event": tr("Evento de partículas solares (toda la tripulación)", "Solar particle event (whole crew)"),
  "spe-event-recovery": tr(
    "Evento de partículas solares y vuelta a la normalidad (toda la tripulación)",
    "Solar particle event and return to normal (whole crew)",
  ),
  "progressive-insomnia": tr("Insomnio progresivo", "Progressive insomnia"),
  "transient-sleep-loss": tr("Falta de sueño pasajera (cesa)", "Transient sleep loss (it ends)"),
  "co2-fatigue": tr("CO2 de cabina (toda la tripulación)", "Cabin CO2 (whole crew)"),
  dehydration: tr("Deshidratación", "Dehydration"),
  "menu-fatigue": tr("Fatiga de menú (hipótesis)", "Menu fatigue (hypothesis)"),
  arrhythmia: tr("Arritmia", "Arrhythmia"),
  "cardiovascular-deconditioning": tr("Desacondicionamiento cardiovascular", "Cardiovascular deconditioning"),
  "immune-reactivation": tr("Reactivación inmune", "Immune reactivation"),
  phantom: tr("Fantoma ecográfico", "Ultrasound phantom"),
};

/**
 * El dibujo de cada escenario: el del dominio o la familia de indicador que perturba, con el
 * significado que ya tienen en el resto de la interfaz (`icons/sets/domains.ts`,
 * `icons/sets/indicators.ts`). Lo nominal lleva la forma del nivel nominal; el CO2 de cabina, la
 * nube del entorno cerrado (RIDGE); la deshidratacion, el vaso con el agua baja; el fantoma, un
 * cubo (un bloque de pruebas). La falta de sueño pasajera no lleva la luna del insomnio (dos
 * escenarios no comparten dibujo) sino la flecha de «recuperándose» de la trayectoria de cada
 * dominio (`CrewConsole.tsx`): lo que la distingue es que cesa. El evento solar con vuelta a la
 * normalidad lleva el sol de la radiación del entorno (`ridge-radiation`, del núcleo:
 * el que el hábitat da al evento solar), no el dominio de radiación del evento que no cesa. Un escenario que la interfaz no conoce sale con su nombre y el
 * dibujo de «desconocido».
 */
export const SCENARIO_PICTOGRAMS: Record<string, PictogramName> = {
  nominal: "shape-circle",
  "spe-event": "domain-radiation",
  "spe-event-recovery": "ridge-radiation",
  "progressive-insomnia": "moon-z",
  "transient-sleep-loss": "arrow-down-right",
  "co2-fatigue": "ridge-environment",
  dehydration: "glass-waterline",
  "menu-fatigue": "fork-knife",
  arrhythmia: "heart-pulse",
  "cardiovascular-deconditioning": "domain-cardiovascular",
  "immune-reactivation": "domain-immune",
  phantom: "cube",
};

function scenarioPictogram(key: string): PictogramName | null {
  return SCENARIO_PICTOGRAMS[key] ?? UNKNOWN_MARK.pictogram;
}

// El destino de «Saltar al contenido»: `tabIndex={-1}` para que el foco llegue aunque no sea un mando.
const MAIN_ID = "contenido";

export function App({ look = "classic" }: { look?: ConsoleLook } = {}) {
  const display = useStoredDisplayModes();
  const modes = display.modes;
  const [active, setActive] = useState<ConsoleKey>("crew");
  // La capa de datos (`dashboard/useConsoleData.ts`): estado y sondeo, tripulación, corte de Tierra,
  // alertas derivadas y las acciones firmadas. La misma para la concha de la maqueta.
  const {
    load,
    subject,
    members,
    options,
    choose,
    refresh,
    shown,
    viewed,
    alerts,
    acknowledged,
    silenced,
    counts,
    actions,
    countermeasureActions,
  } = useConsoleData(active);

  // La voz propia (§5.40, `lib/speech.ts`): lee el resumen y las alertas de lo que se ve, con las
  // frases del backend, y con el modo voz anuncia una vez cada alerta nueva.
  const speaker = useSpeaker();
  const spoken = useMemo(
    () =>
      alerts.map((alert) =>
        // La palabra del nivel, la misma de la insignia (`levelStyle`, del backend).
        spokenAlert(alert, (level) => levelStyle(level).label, domainLabel, silenced.get(alert.id)),
      ),
    [alerts, silenced],
  );
  const readout = useMemo(
    () =>
      shown === null
        ? []
        : statusSpeech({
            console: CONSOLES[active],
            subject: viewed,
            summary: shown.summary,
            alerts: spoken,
            privacy: modes.privacy,
          }),
    [shown, active, viewed, spoken, modes.privacy],
  );
  useVoiceShortcut(speaker, readout);
  // El gesto de emergencia (`lib/emergencyVoice.ts`): enciende el modo voz y lee, sin mirar.
  const { update: updateModes } = display;
  const enableVoice = useCallback(() => updateModes({ voice: true }), [updateModes]);
  // Lo ya anunciado, por consola y tripulante (`newAlerts`). La primera vez que se mira cada una
  // no se anuncia lo que ya había; volver a ella anuncia lo que llegó mientras tanto. Un estado
  // que falta un momento (una relectura fallida, Tierra sin nada recibido aún) no borra lo visto:
  // si no, la alerta que llegara justo después se daría por vista sin decirla. Solo apagar la voz,
  // o quedarse sin voz local, empieza de cero.
  const announced = useRef(new Map<string, ReadonlySet<string>>());
  const { say } = speaker;
  // Con «EMMA toma la iniciativa» las alertas nuevas las dice ella (`assistant/proactive.ts`, con
  // el criterio de `lib/announce.ts`); el modo voz calla las suyas para no decirlas dos veces.
  const proactiveOn = modes.proactive && speaker.availability === "ready";
  const voiceOn = modes.voice && !proactiveOn && speaker.availability === "ready";
  useProactive({
    enabled: proactiveOn,
    speaker,
    scope: `${active}|${viewed}`,
    consoleName: CONSOLES[active],
    subject: viewed,
    status: shown,
    alerts,
    annunciation: silenced,
    acknowledged,
    privacy: modes.privacy,
    routines: active === "crew" ? viewed : null,
  });
  useEffect(() => {
    if (!voiceOn) {
      announced.current.clear();
      return;
    }
    if (shown === null) return;
    const key = `${active}|${viewed}`;
    const { announce, seen } = newAlerts(announced.current.get(key) ?? null, spoken);
    announced.current.set(key, seen);
    if (announce.length > 0) say(announce.map(newAlertSpeech), false);
  }, [voiceOn, shown, active, viewed, spoken, say]);

  // Lo que el asistente hace con una intención de lectura (`assistant/intents.ts`): con lo que ya
  // hay en pantalla. Las pestañas se abren pulsando la suya del carril, así la sección queda
  // guardada como si la hubiera elegido la persona; los modos, por el mismo `update` de los mandos.
  // Los paneles se buscan por su `data-ui` del inventario, nunca por su texto (`assistant/uiTargets.ts`):
  // se cambia de consola si hace falta, se pulsa su pestaña y se busca unos fotogramas, hasta que
  // está montado (un equipo lento tarda más). Lo único que se pulsa es la pestaña.
  const lastPanel = useRef<string | null>(null);
  const revealThen = (id: string, place: UiPlace, then: (panel: HTMLElement) => void, missing: () => void = () => undefined) => {
    if (place.console !== active) setActive(place.console);
    untilFound(() => {
      if (place.section !== null && !clickTab(tabElement(document, place.console, place.section))) return false;
      const panel = findPanel(document, id);
      if (panel === null) return false;
      // En una pestaña por filas (`RowPages`) el panel puede estar en otra página: se abre la suya y
      // se vuelve a mirar en el siguiente intento, ya a la vista.
      if (showRowOf(panel)) return false;
      reveal(panel);
      lastPanel.current = id;
      then(panel);
      return true;
    }, undefined, missing);
  };
  const assistantEffects: IntentEffects = {
    console: active,
    tabs: () => consoleTabs(active),
    openTab: (key) => clickTab(document.getElementById(`${active}-tab-${key}`)),
    switchConsole: setActive,
    revealPanel: (id, place) => revealThen(id, place, () => undefined),
    // Lo que pone el panel en pantalla, tal cual (texto del backend y rótulos), sin el modelo. Con
    // la privacidad, un panel tapado no se lee y los nombres se dicen «tripulante tapado».
    readPanel: (id, place) => {
      if (speaker.availability !== "ready") return false;
      revealThen(id, place, (panel) => {
        if (covered(panel)) {
          speaker.say([PANEL_COVERED], true);
          return;
        }
        const names = modes.privacy
          ? privateNames([...members, subject, viewed, storedOperator()], load.state === "ready" ? [load.onboard, load.received] : [])
          : [];
        speaker.say(readableLines(panel.innerText, names), true);
      }, () => speaker.say([PANEL_NOT_FOUND], true));
      return true;
    },
    stepPanel: (delta) => {
      const panels = topPanels(document, active);
      if (panels.length === 0) return false;
      const ids = panels.map((panel) => panel.getAttribute(UI_ATTRIBUTE));
      let index = lastPanel.current === null ? -1 : ids.indexOf(lastPanel.current);
      if (index < 0) {
        // Sin uno de partida: el que asoma primero bajo la franja fija.
        const top = document.querySelector(".strip")?.getBoundingClientRect().bottom ?? 0;
        index = panels.findIndex((panel) => panel.getBoundingClientRect().bottom > top);
      }
      const target = panels[index + delta];
      if (target === undefined) return false;
      reveal(target);
      lastPanel.current = target.getAttribute(UI_ATTRIBUTE);
      return true;
    },
    scroll: (direction) => {
      const page = Math.round(window.innerHeight * 0.8);
      if (direction === "top") window.scrollTo({ top: 0 });
      else if (direction === "bottom") window.scrollTo({ top: document.documentElement.scrollHeight });
      else window.scrollBy({ top: direction === "down" ? page : -page });
    },
    requestOrientation: requestOrientationPermission,
    modes,
    // «Silencio»: el mismo de la iniciativa propia, que calla lo no crítico (lo crítico, nunca).
    silence: (ms) => silenceFor(ms),
    // «Deja de escuchar»: apaga el modo «Escuchar "EMMA"» (`assistant/wake/`) y cierra el micrófono.
    stopListening: () => display.update({ wakeWord: false }),
    updateModes: display.update,
    readStatus: () => {
      if (speaker.availability !== "ready" || readout.length === 0) return false;
      speaker.say(readout, true);
      return true;
    },
    // Las alertas son los trozos de después del resumen (`statusSpeech`): el recuento y cada una.
    readAlerts: () => {
      if (speaker.availability !== "ready" || readout.length < 2) return false;
      speaker.say(readout.slice(1), true);
      return true;
    },
    stopVoice: speaker.stop,
    repeatVoice: speaker.repeat,
  };

  // El alto de la franja fija, para que el carril de pestañas quede pegado justo debajo (§5.40).
  const shell = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const root = shell.current;
    const strip = root?.querySelector(".strip");
    if (root == null || strip == null || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      // Con baja visión `.app` va ampliada (`zoom`): la medida sale ampliada y la variable se usa
      // dentro de lo ampliado, así que se pasa a píxeles sin ampliar.
      const zoom = Number.parseFloat(getComputedStyle(root).zoom) || 1;
      root.style.setProperty("--strip-h", `${Math.ceil(strip.getBoundingClientRect().height / zoom)}px`);
    });
    observer.observe(strip);
    return () => observer.disconnect();
  }, [modes.lowVision]);

  // Alto contraste (§5.40): la otra paleta de `lib/palette.ts`, volcada en las mismas variables y en
  // la raíz del documento, para que también lo de fuera de `.app` (diálogos, el fondo) cambie. Antes
  // de pintar, para que no se vea un fotograma con la paleta de antes.
  useLayoutEffect(() => {
    applyPalette(document.documentElement, modes.highContrast ? "highContrast" : "base");
  }, [modes.highContrast]);

  // Privacidad: los nombres que el backend escribe dentro de las frases que quedan a la vista se
  // tapan al pintar, sin tocar el texto (§5.40, `lib/privacyNames.ts`).
  const [maskable] = useState(namesMaskable);
  usePrivateNameMask(shell, modes.privacy, () =>
    privateNames(
      [...members, subject, viewed, storedOperator()],
      load.state === "ready" ? [load.onboard, load.received] : [],
    ),
  );

  // El conmutador de consola, el único `tablist` de la barra, con tabulación itinerante y flechas
  // (§5.40.2). El tripulante y el escenario van en la franja, con los mandos: no son pestañas.
  const consoleSwitch = (
      <div
        className="console-switch"
        role="tablist"
        aria-label={tr("Consolas", "Consoles")}
        onKeyDown={(event) => {
          const keys = Object.keys(CONSOLES) as ConsoleKey[];
          const at = keys.indexOf(active);
          const next =
            event.key === "ArrowRight" || event.key === "ArrowDown"
              ? keys[(at + 1) % keys.length]
              : event.key === "ArrowLeft" || event.key === "ArrowUp"
                ? keys[(at - 1 + keys.length) % keys.length]
                : event.key === "Home"
                  ? keys[0]
                  : event.key === "End"
                    ? keys[keys.length - 1]
                    : undefined;
          if (next === undefined) return;
          event.preventDefault();
          setActive(next);
          event.currentTarget.querySelector<HTMLElement>(`[data-console="${next}"]`)?.focus();
        }}
      >
        {(Object.keys(CONSOLES) as ConsoleKey[]).map((key) => (
          <button
            key={key}
            role="tab"
            aria-selected={active === key}
            tabIndex={active === key ? 0 : -1}
            data-console={key}
            onClick={() => setActive(key)}
          >
            <Mark pictogram={CONSOLE_PICTOGRAMS[key]}>{CONSOLES[key]}</Mark>
          </button>
        ))}
      </div>
  );

  return (
    <DisplayModesContext.Provider value={{ ...display, namesMasked: maskable }}>
    <LookContext.Provider value={look}>
    <VoiceAvailabilityContext.Provider value={speaker.availability}>
    <div
      className="app"
      ref={shell}
      data-look={look === "reference" ? look : undefined}
      data-mode={load.state === "ready" ? load.onboard.mission.mode : undefined}
      data-low-vision={modes.lowVision ? "on" : undefined}
      data-high-contrast={modes.highContrast ? "on" : undefined}
      data-privacy={modes.privacy ? "on" : undefined}
      data-rotation={modes.rotation === 0 ? undefined : String(modes.rotation)}
    >
      {/* Lo primero que encuentra el tabulador (§5.41): salta la franja y las pestañas de consola,
          que se repiten en cada pantalla, y deja el foco en el contenido. */}
      <a className="skip-link" href={`#${MAIN_ID}`}>
        {tr("Saltar al contenido", "Skip to content")}
      </a>
      {/* El fondo de la maqueta (adorno declarado): las estrellas; sus degradados, con los del tablero
          «Inicio», al final del contenedor. La Tierra de noche va solo al pie del carril
          (`EarthNightArt`): la segunda, al pie de la página, se montaba encima de ella en las
          secciones cortas (Ellande, 2026-11-09). */}
      {look === "reference" && <StarField />}
      {/* Las alertas nuevas, dichas al lector de pantalla una vez (`lib/announce.ts`). Fuera de
          las secciones: se anuncian sea cual sea la pestaña abierta, como la franja las cuenta. */}
      <AlertAnnouncer
        ready={shown !== null}
        scope={`${active}|${viewed}`}
        alerts={alerts}
        annunciation={silenced}
        acknowledged={acknowledged}
        privacy={modes.privacy}
      />
      <StatusStrip
        edge={<ScreenTop />}
        status={shown}
        loading={load.state === "loading"}
        counts={counts}
        // En la franja fija, de quien es lo que se ve: no hay que subir hasta el selector.
        // En modo privacidad, el nombre del tripulante no va en la franja (§5.40).
        consoleTitle={`${CONSOLES[active]} · ${modes.privacy ? tr("tripulante tapado", "crew member hidden") : viewed}`}
        consolePictogram={CONSOLE_PICTOGRAMS[active]}
        brand={look === "reference" ? <BrandLogo /> : undefined}
        controls={active === "crew"}
        voice={<ReadAloud speaker={speaker} read={readout} />}
        // «Ayuda» abre los «Atajos» de la voz: solo si la voz los pinta.
        shortcuts={speaker.availability === "ready"}
        // Con la cabecera de la muestra, el tripulante va en su ficha arriba a la derecha; en la
        // clásica, el primero de los mandos, como antes (`StatusStrip`).
        crew={
          options.length > 1 ? (
            <label className="crew-selector">
              <Mark pictogram="person" className="secondary">
                {tr("Tripulante", "Crew member")}
              </Mark>
              {/* Con la privacidad va difuminado en pantalla y, con `inert`, fuera del foco y del
                  lector de pantalla, que si no leería el nombre igual (§5.41). */}
              <select value={subject} inert={modes.privacy} onChange={(event) => choose(event.target.value)}>
                {options.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
          ) : undefined
        }
        tools={
          load.state === "ready" && load.onboard.mission.mode === "simulation" ? (
            <ScenarioSwitcher
              current={currentScenario(load.onboard.mission.sources)}
              onSwitched={() => void refresh()}
            />
          ) : undefined
        }
        sync={load.state === "ready" ? load.sync : null}
        // La campana lleva a la lista de alertas de la consola que se ve (2026-11-09): a bordo,
        // «Alertas activas» de «Peligros y alertas»; en Tierra, «Estado recibido». Las dos secciones
        // son esenciales y compartidas, así que están también en modo esencial y con la privacidad;
        // `revealThen` abre la pestaña, despliega el panel si está plegado y lo pone a la vista.
        onAlerts={() =>
          revealThen(
            active === "crew" ? "alerts" : "received-state",
            { console: active, section: active === "crew" ? "hazards" : "received" },
            () => undefined,
          )
        }
      />
      {/* La barra: el conmutador de consola, el único `tablist`, con tabulación itinerante y flechas
          (§5.40.2). El tripulante y el escenario van en la franja, con los mandos (concha de la
          maqueta, 2026-11-07): no son pestañas y así quedan a la vista en las dos consolas. */}
      {/* La barra: solo en la concha clásica o mientras no hay consola montada; en la concha de la
          maqueta el conmutador va en lo alto del carril (`RailTopContext`). */}
      {(look === "classic" || load.state !== "ready") && (
        <nav className="tabs" aria-label={tr("Consolas", "Consoles")}>
          {consoleSwitch}
        </nav>
      )}
      <RailTopContext.Provider value={look === "reference" ? consoleSwitch : null}>
      <main id={MAIN_ID} tabIndex={-1}>
        {load.state === "loading" && (
          <p className="secondary">
            <MarkOf mark={LOADING_MARK}>{tr("Cargando estado…", "Loading status…")}</MarkOf>
          </p>
        )}
        {load.state === "error" && (
          <p className="panel error">
            <MarkOf mark={load.outcome.mark}>
              {tr("No se pudo obtener el estado:", "Could not get the status:")} {load.outcome.text}
            </MarkOf>
          </p>
        )}
        {load.state === "empty" && <EmptyStore subject={subject} onLoaded={() => void refresh()} />}
        {/* Sin consola montada no hay carril: los mandos de pantalla van aquí, a mano igual. En la
            concha de la maqueta, plegados tras «Pantalla» como en el carril: desplegados ocupaban toda
            la página mientras cargaba y parecía que había que elegir algo antes de ver «Inicio»
            (Ellande, 2026-11-09). */}
        {load.state !== "ready" && <DisplayControls folded={look === "reference"} />}
        {/* Ayuda urgente (2026-11-14): encima de cualquier sección, en las dos consolas; en Tierra, con
            su corte de reloj. Otra consola, otra lista: lo ya dicho en una no se calla en la otra. */}
        {load.state === "ready" && (
          <HelpBanner
            key={active}
            console={active}
            oneWayMinutes={load.onboard.comms?.one_way_minutes ?? null}
            sync={load.sync}
            speaker={speaker}
          />
        )}
        {load.state === "ready" &&
          (active === "crew" ? (
            <CrewConsole
              status={load.onboard}
              alerts={alerts}
              counts={counts}
              actions={actions}
              countermeasureActions={countermeasureActions}
              onProfileDeclared={refresh}
              sync={load.sync}
              onLinkDeclared={refresh}
              onChooseSubject={choose}
            />
          ) : (
            <GroundConsole status={load.onboard} received={load.received} sync={load.sync} counts={counts} />
          ))}
      </main>
      </RailTopContext.Provider>
      {/* Triple Escape, tres dedos o el atajo del escritorio: voz y lectura sin ver la pantalla.
          Al final: las regiones vivas de las alertas siguen siendo lo primero tras el salto (§5.41). */}
      <EmergencyVoice speaker={speaker} readout={readout} voiceOn={modes.voice} enableVoice={enableVoice} />
      {/* Los avisos de hora del planificador (`planner/TimeAnnouncer.tsx`) no se montan en esta versión:
          «Planificador» está apartada (`setAside` en `dashboard/CrewConsole.tsx`, 2026-11-15). */}
      <About />
      {/* El asistente, siempre a mano sea cual sea la pestaña (`assistant/`). */}
      <Assistant
        console={active}
        subject={viewed}
        privacy={modes.privacy}
        speaker={speaker}
        effects={assistantEffects}
        onSigned={() => void refresh()}
      />
      {/* Los degradados de los dibujos de la maqueta (el fondo de la concha y las piezas de «Inicio»,
          que se montan en las dos conchas), definidos una sola vez: un `svg` vacío al final, fuera del
          orden del tabulador y de lo que miden las pruebas del marcado clásico. */}
      <Gradients />
    </div>
    </VoiceAvailabilityContext.Provider>
    </LookContext.Provider>
    </DisplayModesContext.Provider>
  );
}

/** Las pestañas del carril de una consola tal como están en pantalla (`ConsoleTabs`). */
function consoleTabs(consoleKey: ConsoleKey): TabRef[] {
  const prefix = `${consoleKey}-tab-`;
  return [...document.querySelectorAll<HTMLElement>(`[role="tab"][id^="${prefix}"]`)].map((element) => ({
    key: element.id.slice(prefix.length),
    label: element.textContent ?? "",
  }));
}

/** El escenario en curso, por el firmante de las lecturas: `simulator:<escenario>`. */
export function currentScenario(sources: readonly string[]): string | null {
  const [only] = sources;
  return sources.length === 1 && only !== undefined && only.startsWith("simulator:")
    ? only.slice("simulator:".length)
    : null;
}

/**
 * Cambiar de escenario sin cerrar la aplicacion. Sustituye la sesion simulada
 * entera —reconocimientos incluidos—, asi que pide confirmacion (F.4.3.2 c: una
 * accion que pierde datos exige dos acciones). Solo aparece en modo simulacion, y
 * el backend se niega igualmente si hubiera una sola lectura real.
 *
 * Segunda pasada (§5.33.11): el rotulo «Escenario:» y el mando «Cambiar…» llevan el signo de
 * cambiar de escenario (la onda generada, `changeScenario`); «Confirmar cambio», la marca de dar
 * por bueno con la cinta de lo irreversible, y «Cancelar», la cruz de no seguir. Un fallo del
 * backend va con la marca de la peticion que fallo, no solo en rojo.
 */
export function ScenarioSwitcher({
  current,
  onSwitched,
}: {
  current: string | null;
  onSwitched: () => void;
}) {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [choice, setChoice] = useState<string>("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<RequestOutcome | null>(null);

  useEffect(() => {
    api
      .scenarios()
      .then((payload) => setScenarios(payload.scenarios))
      .catch((reason: unknown) => setError(requestOutcome(reason)));
  }, []);

  const label = (key: string) => SCENARIO_LABELS[key] ?? key;
  const others = scenarios.filter((scenario) => scenario.key !== current);

  const change = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.simulate(choice, true);
      setConfirming(false);
      setChoice("");
      onSwitched();
    } catch (reason) {
      setError(requestOutcome(reason));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="scenario-switcher">
      <span className="secondary scenario-current">
        {/* Rotulo del escenario en curso, no del selector de al lado (que elige el siguiente): por
            eso no lo nombra con `htmlFor`. Va encima del nombre (§5.40.2). */}
        <FieldLabel concept="changeScenario">
          {tr("Escenario:", "Scenario:")}
        </FieldLabel>{" "}
        <strong className="c-text">
          {current !== null ? <Mark pictogram={scenarioPictogram(current)}>{label(current)}</Mark> : "—"}
        </strong>
      </span>
      {busy ? (
        <MarkOf mark={LOADING_MARK} className="secondary">
          {tr(`Cargando ${label(choice)}…`, `Loading ${label(choice)}…`)}
        </MarkOf>
      ) : confirming ? (
        // La pregunta y sus dos mandos van juntos en su propia fila, debajo del escenario en curso
        // (§5.34.14): sueltos en la barra, el rótulo cedía y a 1400 px eran tres renglones.
        <span className="scenario-confirm">
          <span>
            {tr("¿Descartar la sesión simulada y cargar", "Discard the simulated session and load")}{" "}
            <Mark pictogram={scenarioPictogram(choice)}>{label(choice)}</Mark>?
          </span>
          <Command concept="confirmChange" hazard onClick={() => void change()}>
            {tr("Confirmar cambio", "Confirm change")}
          </Command>
          <Command concept="cancel" onClick={() => setConfirming(false)}>
            {tr("Cancelar", "Cancel")}
          </Command>
        </span>
      ) : (
        // El selector y su mando, juntos: si no caben al lado del nombre bajan los dos (§5.40.2).
        <span className="scenario-actions">
          {/* Nombre propio para el lector de pantalla (§5.41): «Escenario:» es el rótulo del que está
              en curso, y la primera opción («Cambiar a…») no le da nombre al selector. */}
          <select
            value={choice}
            aria-label={tr("Escenario al que cambiar", "Scenario to change to")}
            onChange={(event) => setChoice(event.target.value)}
          >
            <option value="">{tr("Cambiar a…", "Change to…")}</option>
            {others.map((scenario) => (
              <option key={scenario.key} value={scenario.key}>
                {label(scenario.key)}
              </option>
            ))}
          </select>
          <Command concept="changeScenario" disabled={choice === ""} onClick={() => setConfirming(true)}>
            {tr("Cambiar…", "Change…")}
          </Command>
        </span>
      )}
      {error !== null && <MarkOf mark={error.mark}>{error.text}</MarkOf>}
    </div>
  );
}

/**
 * Sin datos, el backend responde 404 en vez de inventarlos, y la interfaz tampoco
 * los inventa: ofrece cargar un escenario del simulador, que queda firmado como
 * simulado. Para cambiar despues de escenario esta `ScenarioSwitcher`.
 */
/** El escenario que se carga solo con el almacén vacío (`EmptyStore`). */
export const AUTO_SCENARIO = "nominal";

export function EmptyStore({ onLoaded }: { subject: string; onLoaded: () => void }) {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<RequestOutcome | null>(null);

  useEffect(() => {
    api
      .scenarios()
      .then((payload) => setScenarios(payload.scenarios))
      .catch((reason: unknown) => setError(requestOutcome(reason)));
  }, []);

  // CARGA AUTOMÁTICA (petición del usuario, 2026-11-15: «queríamos que cargase un escenario
  // automáticamente»). El almacén vive en memoria: cada reinicio del backend lo vacía y la consola se
  // quedaba en este selector. Con el almacén vacío se carga sola el escenario nominal, firmado como
  // simulado igual que si se pulsara; los botones siguen para elegir otro o datos reales. Solo una vez
  // por montaje: si falla, se dice y se queda el selector.
  const autoLoaded = useRef(false);
  useEffect(() => {
    if (autoLoaded.current) return;
    autoLoaded.current = true;
    void loadScenario(AUTO_SCENARIO);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadScenario = async (key: string) => {
    setBusy(key);
    setError(null);
    try {
      await api.simulate(key);
      onLoaded();
    } catch (reason) {
      setError(requestOutcome(reason));
      setBusy(null);
    }
  };

  return (
    <>
      <section className="panel">
        {/* Tabla F.5-1: lo que falta va en cian con el anillo punteado, aqui como en la franja. */}
        <PanelTitle pictogram="ring-dotted" className="c-cyan">
          {tr("No hay lecturas del tripulante", "No readings for this crew member")}
        </PanelTitle>
        <p className="secondary" style={{ margin: "8px 0 16px" }}>
          {tr(
            "EMMA no muestra cifras sin origen. Conecte un wearable o cargue un escenario del simulador; sus lecturas quedarán firmadas como simuladas.",
            "EMMA does not show figures without a source. Connect a wearable or load a simulator scenario; its readings will be signed as simulated.",
          )}
        </p>
        <div className="summary">
          <RealDataButton onLoaded={onLoaded} />
          {scenarios.map((scenario) => (
            <button
              key={scenario.key}
              className="command"
              disabled={busy !== null}
              onClick={() => void loadScenario(scenario.key)}
            >
              {busy === scenario.key ? (
                <MarkOf mark={LOADING_MARK}>{tr("Cargando…", "Loading…")}</MarkOf>
              ) : (
                <Mark pictogram={scenarioPictogram(scenario.key)}>
                  {SCENARIO_LABELS[scenario.key] ?? scenario.label}
                </Mark>
              )}
            </button>
          ))}
        </div>
        {error !== null && (
          <p>
            <MarkOf mark={error.mark}>{error.text}</MarkOf>
          </p>
        )}
      </section>
      {/* La ecografía y los volúmenes que aquí se podían registrar sin constantes van con «Imagen e
          informes», apartada de esta versión (`setAside` en `dashboard/CrewConsole.tsx`, 2026-11-15). */}
    </>
  );
}

/**
 * Datos reales publicados, no simulados: el hemograma de los cuatro tripulantes de
 * Inspiration4 (NASA OSDR, OSD-569), colocado en la linea de tiempo de la mision. Lo que se
 * aparta por incoherente en origen se dice, no se esconde. Si la carga sale mal, el motivo va con la
 * marca de lo que fue (`requestOutcome`: rechazo o caida, §5.34.14); antes salia en gris, como si
 * fuera el resumen de lo cargado.
 */
function RealDataButton({ onLoaded }: { onLoaded: () => void }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<
    { kind: "loaded"; text: string } | { kind: "failed"; outcome: RequestOutcome } | null
  >(null);
  const load = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const result = await api.replayInspiration4();
      setMessage({
        kind: "loaded",
        text:
          tr(
            `${result.recorded} lecturas reales de ${result.subjects.length} tripulantes. `,
            `${result.recorded} real readings from ${result.subjects.length} crew members. `,
          ) +
          (result.excluded.length > 0
            ? tr(
                `Apartadas en origen: ${result.excluded.join("; ")}. `,
                `Set aside at the source: ${result.excluded.join("; ")}. `,
              )
            : "") +
          result.citation,
      });
      onLoaded();
    } catch (reason) {
      setMessage({ kind: "failed", outcome: requestOutcome(reason) });
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      {/* Un mando como los demas, con el cohete del vuelo real (`icons/sets/provenance.ts`, tabla
          de §5.32): datos de una mision tripulada, no un escenario; no es un mando peligroso ni
          lleva color de alerta. */}
      <button className="command" disabled={busy} onClick={() => void load()}>
        {busy ? (
          <MarkOf mark={LOADING_MARK}>{tr("Cargando…", "Loading…")}</MarkOf>
        ) : (
          <Mark pictogram="rocket">
            {tr("Analíticas reales de Inspiration4 (NASA OSDR)", "Real Inspiration4 lab results (NASA OSDR)")}
          </Mark>
        )}
      </button>
      {message !== null &&
        (message.kind === "failed" ? (
          <p>
            <MarkOf mark={message.outcome.mark}>{message.outcome.text}</MarkOf>
          </p>
        ) : (
          <p className="secondary">{message.text}</p>
        ))}
    </>
  );
}

