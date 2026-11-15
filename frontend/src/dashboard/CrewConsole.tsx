import { useEffect, useRef, useState } from "react";

import { FollowupsPanel } from "../advisor/FollowupsPanel";
import { ANATOMY_PANEL_ID, AnatomyPanel } from "../anatomy/AnatomyPanel";
import { useAnatomyState } from "../anatomy/useAnatomyState";
import { HabitatPanel } from "../habitat/HabitatPanel";
import { RecommendationList } from "../advisor/RecommendationList";
import { BoardOnly } from "../components/BoardOnly";
import { type ConsoleSection, ConsoleTabs, personal, useStoredSection, visibleSections } from "../components/ConsoleTabs";
import { useDisplayModes } from "../components/DisplayControls";
import {
  browserStore,
  type HomeBlock,
  readHomeBlock,
  readHomeSecondary,
  writeHomeBlock,
  writeHomeSecondary,
} from "../components/displayModes";
import { HomeDiagnostics } from "./HomeDiagnostics";
import { HomeDistance } from "./HomeDistance";
import { HomeReserves } from "./HomeReserves";
import { NodesEmergencyKit } from "./NodesEmergencyKit";
import { NodesFit } from "./NodesFit";
import { NodesOutlook } from "./NodesOutlook";
import "./nodesBoard.css";
import { FieldLabel } from "../components/FieldLabel";
import { LevelBadge } from "../components/LevelBadge";
import { Mark, MarkOf } from "../components/Mark";
import { OperatorInput } from "../components/OperatorInput";
import { PanelTitle } from "../components/PanelTitle";
import type { Alert, AlertCounts } from "../lib/alerts";
import { type CrewStatus, type LinkSync, missionProfileApi } from "../lib/api";
import { commsStatusOf } from "../lib/commsStatus";
import { tr } from "../lib/i18n";
import { baselineRefreshKey, twinsRefreshKey } from "../lib/crew";
import { OK_MARK } from "../lib/marks";
import { useOperator } from "../lib/operator";
import { uiPictogram } from "../lib/uiMarks";
import { UltrasoundPanel } from "../imaging/UltrasoundPanel";
import { ReportsPanel } from "../reports/ReportsPanel";
import { VolumesPanel } from "../volumes/VolumesPanel";
import { DiaryPanel } from "../diary/DiaryPanel";
import { DescriptivePanel } from "../indicators/DescriptivePanel";
import { FoodAcceptabilityPanel } from "../nutrition/FoodAcceptabilityPanel";
import { PainPanel } from "../pain/PainPanel";
import { PvtPanel } from "../pvt/PvtPanel";
import { CognitionPanel } from "../cognition/CognitionPanel";
import {
  PlannerCalendarPanel,
  PlannerChoresPanel,
  PlannerMenuPanel,
  PlannerRemindersPanel,
} from "../planner/PlannerPanels";
import { PlannerAnnouncementsPanel } from "../planner/AnnouncementsPanel";
import { PlannerBriefingPanel } from "../planner/BriefingPanel";
import { PlannerRecipesPanel, PlannerWeekMenuPanel } from "../planner/MealsPanels";
import {
  PlannerDayPeriodsPanel,
  PlannerMealPlansPanel,
  PlannerMessagesPanel,
} from "../planner/HouseholdPanels";
import { PlannerMembersPanel } from "../planner/MembersPanel";
import { PlannerRoutinesPanel } from "../planner/RoutinesPanel";
import { DoseMeter } from "../radiation/DoseMeter";
import { RadiationScales } from "../radiation/RadiationScales";
import { type AlertActions, AlertRow } from "./AlertRow";
import { BaselineProfilePanel } from "./BaselineProfilePanel";
import { CycleSection } from "../cycle/CycleSection";
import { DomainsPanel } from "./DomainsPanel";
import {
  ActiveEnvironment,
  type DeclareProfile,
  ENVIRONMENTS_GROUP,
  environmentSections,
  useProfileMatrix,
} from "./Environments";
import { AlertTally, CountPill, DomainLevelTally, HazardCards } from "./HazardCards";
import {
  HomeCrewColumn,
  HomeDivider,
  HomeEssential,
  hasNewAlert,
  HomeFooter,
  HomeGlobal,
  type HomeLinks,
  HomePlaces,
  HomeQuickHazards,
  HomeRiskColumn,
  HomeRoutes,
  useHomeData,
} from "./HomeBoard";
import { GroundNotesPanel } from "./GroundNotesPanel";
import { InferredPanel } from "./InferredPanel";
import { type DeclareEvent, MissionTimeline } from "./MissionTimeline";
import { Basis, MonitoringPanel } from "./MonitoringBasis";
import { Predictions } from "./Predictions";
import { QualityPanel } from "./QualityPanel";
import { HeartBandPanel } from "./HeartBandPanel";
import { SensorBindingsPanel } from "./SensorBindingsPanel";
import { SharingPanel } from "./SharingPanel";
import { SummaryTiles } from "./SummaryTiles";
import { ResourcesPanel } from "../advisor/ResourcesPanel";
import { LibraryPanel } from "../advisor/LibraryPanel";
import { GuidesPanel } from "../guides/GuidesPanel";
import { MissionModePanel } from "../components/MissionMode";
import { LinkSyncPanel } from "../components/LinkSync";
import { Routines, ThisWeek, Waiting } from "./TimelinePieces";
import { TwinQuestionsPanel } from "./TwinQuestions";
import { radiationPanels, useRadiationData } from "../radiation/RadiationBoard";
import { isolationPanels, useIsolationData } from "../isolation/IsolationBoard";
import { environmentPanels, useEnvironmentData } from "../environment/EnvironmentBoard";
import { gravityPanels, useGravityData } from "../gravity/GravityBoard";

/**
 * Consola de tripulacion: poco y relevante.
 *
 * Referente: Crew Dragon, donde *"minimum crew interaction"* fue criterio de
 * exito. Primero lo que requiere atencion, con su recomendacion al lado; el
 * detalle, en la consola de Tierra. Ningun texto clinico se escribe aqui: todo
 * sale del backend (invariante 7).
 */
/** Decisiones humanas sobre contramedidas: se firman en el ledger (especificacion §14). */
export interface CountermeasureActions {
  adopt: (countermeasureId: string, by: string) => Promise<void>;
  /** «No adoptar», con el motivo de quien decide: no retira la recomendacion. */
  decline: (countermeasureId: string, by: string, reason: string) => Promise<void>;
  close: (adoptionIndex: number, by: string, reason: string) => Promise<void>;
  declareProfile: (missions: number, doseMsv: number | null, by: string) => Promise<void>;
  declareEvent: DeclareEvent;
}

export function CrewConsole({
  status,
  alerts,
  counts,
  actions,
  countermeasureActions,
  onProfileDeclared,
  sync,
  onLinkDeclared,
  onChooseSubject,
}: {
  status: CrewStatus;
  alerts: Alert[];
  /** Los contadores de la franja: el recuento de la pestaña de alertas es el mismo. */
  counts: AlertCounts;
  actions: AlertActions;
  countermeasureActions: CountermeasureActions;
  /** Tras declarar otro entorno de la misión: relee el estado, y con él la cabecera. */
  onProfileDeclared?: () => Promise<void>;
  /** El enlace con Tierra simulado (`GET /api/link-sync`), el mismo que da el corte de Tierra. */
  sync: LinkSync;
  /** Tras declararlo caído o restablecido: relee el estado y el corte de Tierra. */
  onLinkDeclared: () => Promise<void>;
  /** Pasa la consola a otro tripulante: la banda de pulso la lleva al suyo (`HeartBandPanel`). */
  onChooseSubject?: (subject: string) => void;
}) {
  const recommendations = status.recommendations;
  const [operator, setOperator] = useOperator();
  const { modes, update } = useDisplayModes();
  // Una contramedida con seguimiento abierto no se vuelve a ofrecer para adoptar.
  const following = new Set(
    status.followups
      .filter((item) => item.state !== "closed")
      .map((item) => item.countermeasure.id),
  );
  const decides = alerts.length > 0 || recommendations.length > 0 || status.followups.length > 0;
  // La calidad del dato: el detalle en «Calidad del dato»; lo dudoso por dominio lo calcula
  // `DomainsPanel`.
  const quality = status.data.quality;
  // Una ubicacion puede ser de otro tripulante: no cambia el estado de este, que es lo que
  // hace volver a pedir el habitat. Se cuenta aqui cada declaracion para que la vista de
  // tripulacion muestre la hipotesis tal y como queda firmada, no la de antes.
  const [declared, setDeclared] = useState(0);
  const declareEvent: DeclareEvent = async (...declaration) => {
    await countermeasureActions.declareEvent(...declaration);
    setDeclared((count) => count + 1);
  };
  // El estado por regiones y la region elegida son de la consola: la silueta del resumen y el
  // modo anatomico ensenan la misma respuesta, y pulsar una region en la silueta la abre abajo.
  const anatomy = useAnatomyState(status);
  const [region, setRegion] = useState<string | null>(null);
  // El momento de «Cuerpo» también es de la consola: lo elige su selector y lo elige un hito de la
  // crónica (§5.35.8). Desde la crónica, además, se trae el panel a la vista. Va con su
  // tripulante: las claves se repiten entre tripulantes («preflight», «R+1») y, al cambiar de
  // tripulante, un momento elegido para otro no se abre solo.
  const [chosenMoment, setChosenMoment] = useState<{ subject: string; key: string } | null>(null);
  const moment = chosenMoment !== null && chosenMoment.subject === status.subject ? chosenMoment.key : null;
  const setMoment = (key: string | null) =>
    setChosenMoment(key === null ? null : { subject: status.subject, key });
  // La sección abierta es de la consola, no solo del carril: elegir un momento en la crónica
  // («Misión») abre «Cuerpo» y lleva el modo anatómico a la vista cuando ya está montado.
  const [section, setSection] = useStoredSection("crew");
  const [scrollToAnatomy, setScrollToAnatomy] = useState(false);
  // El tablero «Inicio» (la maqueta, `HomeBoard.tsx`): sus peticiones secundarias, sobre la misma
  // anatomía y región que el modo anatómico; sus accesos abren secciones de esta consola.
  // Sin sección guardada (primera visita) `ConsoleTabs` abre la primera, «Inicio», y la deja guardada
  // en su efecto; se pide ya, sin esperar a ese vuelta (lo señaló la revisión de la unidad 11).
  const home = useHomeData(status, {
    anatomy,
    region,
    setRegion,
    // «Radiación» reutiliza el marco RIDGE y los perfiles del tablero (2026-11-14); «Aislamiento», el
    // catálogo de indicadores (nombres, unidades y decimales) y los perfiles (2026-11-15).
    active: section === null || section === "home" || section === "radiation" || section === "isolation" || section === "gravity" || section === "environment" || section === "nodes",
  });
  const radiation = useRadiationData(home, section === "radiation");
  const isolation = useIsolationData(home, section === "isolation");
  const gravity = useGravityData(home, section === "gravity");
  const environment = useEnvironmentData(home, section === "environment");
  // Lo secundario de «Inicio» (bajo el acceso rápido RIDGE) se pliega con `HomeDivider`; la elección
  // es de este equipo, como los modos de pantalla, y no toca ningún dato.
  const [homeSecondary, setHomeSecondary] = useState(() => readHomeSecondary(browserStore()));
  const toggleHomeSecondary = () => {
    setHomeSecondary((open) => {
      writeHomeSecondary(browserStore(), !open);
      return !open;
    });
  };
  // Los bloques plegables de la pestaña «Distancia y nodos» (maqueta de la ISS, lote «reservas»,
  // 2026-11-14): cada uno con su separador y recordado por equipo como lo secundario de «Inicio».
  const [homeBlocks, setHomeBlocks] = useState<Record<HomeBlock, boolean>>(() => ({
    distance: readHomeBlock(browserStore(), "distance"),
    reserves: readHomeBlock(browserStore(), "reserves"),
  }));
  const toggleHomeBlock = (block: HomeBlock) => {
    setHomeBlocks((open) => {
      writeHomeBlock(browserStore(), block, !open[block]);
      return { ...open, [block]: !open[block] };
    });
  };
  const onNodes = section === "nodes";
  // Una alerta nueva pliega lo secundario sola (2026-11-14): lo principal llena la pantalla mientras
  // se atiende. Solo pliega, nunca despliega, y no se guarda como elección: quien vuelva a abrirlo lo
  // tiene abierto hasta la siguiente alerta nueva. Una que se fue y vuelve cuenta como nueva.
  const seenAlerts = useRef<ReadonlySet<string>>(new Set());
  useEffect(() => {
    const ids = alerts.map((alert) => alert.id);
    const fresh = hasNewAlert(seenAlerts.current, ids);
    seenAlerts.current = new Set(ids);
    if (fresh) setHomeSecondary(false);
  }, [alerts]);
  // Un acceso de «Inicio» solo se enseña si su sección está a la vista: en modo esencial, abrir una
  // no esencial devolvía a «Inicio» sin decir nada (`visibleSections`, efecto de `ConsoleTabs`).
  // Los nombres se leen al pintar el tablero, cuando `sections` (más abajo) ya existe; no se llama
  // durante este render. La tabla se hace una vez por render, no una por acceso.
  let visibleNames: ReadonlyMap<string, string> | null = null;
  const homeLinks: HomeLinks = {
    openSection: setSection,
    sectionName: (key) => {
      visibleNames ??= new Map(visibleSections(sections, modes.essential).map((item) => [item.key, item.label]));
      return visibleNames.get(key) ?? null;
    },
    essential: () => update({ essential: true }),
  };
  const chooseMomentFromChronicle = (key: string) => {
    setMoment(key);
    setSection("body");
    setScrollToAnatomy(true);
  };
  useEffect(() => {
    if (!scrollToAnatomy) return;
    document.getElementById(ANATOMY_PANEL_ID)?.scrollIntoView({ block: "start" });
    setScrollToAnatomy(false);
  }, [scrollToAnatomy, section]);
  // Se relee cuando el estado trae otro entorno vigente: la columna señalada lo sigue.
  const environments = useProfileMatrix(status.mission.profile?.id);
  const declareProfile: DeclareProfile = async (body) => {
    await missionProfileApi.set(body);
    await onProfileDeclared?.();
  };

  // La tabla de la consola: sección → paneles, en el orden en que se ven (§5.40). Un panel nuevo es
  // una línea en la lista de su sección; `personal(…)` lo tapa en modo privacidad aunque su
  // sección quede a la vista. Los paneles no cambian: solo dónde se montan.
  // Las ocho últimas (de «Rutinas y notas» a «Biblioteca») están apartadas de esta versión
  // (`setAside`, decisión del usuario, 2026-11-15): siguen en la tabla y no se montan.
  const sections: ConsoleSection[] = [
    {
      // La pantalla principal de la especificación (§10): estado de misión y tripulación, tendencias
      // de 24 h y excepciones primero. Es la maqueta del usuario, en la rejilla de 12 columnas.
      key: "home",
      label: tr("Inicio", "Home"),
      pictogram: uiPictogram("habitat"),
      essential: true,
      shared: true,
      className: "ref-home",
      panels: [
        <HomePlaces home={home} />,
        personal(<HomeGlobal home={home} links={homeLinks} />),
        personal(<HomeCrewColumn home={home} links={homeLinks} />),
        <HomeRiskColumn home={home} links={homeLinks} />,
        <HomeQuickHazards home={home} links={homeLinks} />,
        // Lo principal queda arriba; lo secundario, debajo de esta raya y plegable (2026-11-14).
        <HomeDivider open={homeSecondary} onToggle={toggleHomeSecondary} />,
        homeSecondary && <HomeRoutes home={home} />,
        homeSecondary && <HomeFooter home={home} links={homeLinks} />,
        // El modo esencial no es secundario: plegado lo demás, queda abajo y a lo ancho.
        !homeSecondary && <HomeEssential home={home} links={homeLinks} wide />,
      ],
    },
    {
      // La maqueta «Panel EMMA: Radiación y Salud Espacial» (2026-11-14) con el estilo de «Inicio»: la
      // misma rejilla y las mismas tarjetas (`ref-home`), y la ubicación de «Inicio» arriba. Solo
      // datos del backend: ver `radiation/RadiationBoard.tsx`.
      key: "radiation",
      label: tr("Radiación", "Radiation"),
      pictogram: uiPictogram("radiation"),
      className: "ref-home rad-home",
      panels: [<HomePlaces home={home} />, ...radiationPanels(radiation)],
    },
    {
      // La maqueta «Panel de Aislamiento y Salud Psicosocial ISS» (2026-11-14), con el estilo de
      // «Inicio» y «Radiación»: solo datos del backend; lo que EMMA no mide se dice (ver
      // `isolation/IsolationBoard.tsx`).
      key: "isolation",
      label: tr("Aislamiento", "Isolation"),
      pictogram: "ridge-isolation",
      className: "ref-home iso-home",
      panels: [<HomePlaces home={home} />, ...isolationPanels({ ...isolation, links: homeLinks }, section === "isolation").map((panel) => personal(panel))],
    },
    {
      // La maqueta «Panel EMMA: Salud Gravitacional de la Tripulación» (2026-11-15), con el estilo de
      // «Inicio»: los cuerpos 2D (varón o mujer) en tres estilos y solo datos del backend (ver
      // `gravity/GravityBoard.tsx`).
      key: "gravity",
      label: tr("Gravedad", "Gravity"),
      pictogram: "ridge-gravity",
      className: "ref-home grav-home",
      panels: [<HomePlaces home={home} />, ...gravityPanels(gravity, section === "gravity", homeLinks).map((panel) => personal(panel))],
    },
    {
      // La maqueta «Panel ambiental EMMA en la ISS» (2026-11-15), con el estilo de «Inicio»: las
      // lecturas del hábitat firmadas y sus límites del backend, y el cuerpo en holograma cian (ver
      // `environment/EnvironmentBoard.tsx`).
      key: "environment",
      label: tr("Entorno", "Environment"),
      pictogram: "ridge-environment",
      className: "ref-home env-home",
      panels: [<HomePlaces home={home} />, ...environmentPanels(environment, section === "environment").map((panel) => personal(panel))],
    },
    {
      // La maqueta «Panel médico espacial EMMA para la ISS» (lote «reservas», 2026-11-14): su pestaña
      // propia, no «Inicio» («no tiene que salir en inicio»), con el estilo de «Inicio» y «Radiación»
      // y la ubicación arriba; cada bloque sigue al perfil elegido y se pliega con su raya.
      key: "nodes",
      label: tr("Distancia y nodos", "Distance and nodes"),
      pictogram: uiPictogram("habitat"),
      className: "ref-home nodes-home",
      panels: [
        <HomePlaces home={home} />,
        // «Ajustar a pantalla»: la pestaña cabe en la ventana, como la maqueta (`NodesFit`).
        <NodesFit active={onNodes} />,
        // Arriba, como en la maqueta: el marco global compacto, el tripulante y el riesgo
        // (`nodesBoard.css` deja fuera los vitales, la tendencia, la bitácora y las próximas acciones).
        personal(<HomeGlobal home={home} links={homeLinks} />),
        personal(<HomeCrewColumn home={home} links={homeLinks} />),
        <HomeRiskColumn home={home} links={homeLinks} notices />,
        // Distancia y comunicaciones + sincronización, según el perfil elegido arriba.
        <HomeDistance profileId={home.shownRoute} status={status} sync={sync} active={onNodes} />,
        // El diagnóstico no se pliega («el diagnóstico no se oculta», «el botón sobra»).
        personal(<HomeDiagnostics home={home} links={homeLinks} profileId={home.shownRoute} active={onNodes} />),
        // «Ayuda urgente» al lado del diagnóstico, como «Respuesta a emergencias» en la maqueta.
        <HomeEssential home={home} links={homeLinks} side>
          <NodesEmergencyKit active={onNodes} />
        </HomeEssential>,
        <HomeDivider
          open={homeBlocks.reserves}
          onToggle={() => toggleHomeBlock("reserves")}
          name={tr("las reservas", "the reserves")}
          what={tr("Medicamentos, equipamiento médico y abastecimiento", "Medication, medical equipment and supplies")}
          // Plegadas, lo de arriba llena la ventana, como en «Inicio».
          pictogram="clipboard"
        />,
        homeBlocks.reserves && (
          <HomeReserves profileId={home.shownRoute} subject={status.subject} reference={home.reference} active={onNodes} v2 />
        ),
        // La última fila de la maqueta: riesgos de la distancia, correlaciones y escenarios.
        personal(<NodesOutlook home={home} links={homeLinks} profileId={home.shownRoute} active={onNodes} />),
      ],
    },
    {
      key: "hazards",
      label: tr("Peligros y alertas", "Hazards and alerts"),
      pictogram: uiPictogram("hazards"),
      essential: true,
      alerts: true,
      shared: true,
      panels: [
        // El nivel del backend también en el filete del titular (§5.40, tableta): el mismo
        // `data-level` que las tarjetas de dominio; la palabra y la forma siguen en la insignia.
        <section data-ui="summary" className="panel summary" data-level={status.overall_level} aria-label={tr("Resumen", "Summary")}>
          <LevelBadge level={status.overall_level} />
          <p>{status.summary}</p>
          {/* Tablero (2026-11-07): cuántos dominios hay en cada nivel y un segmento por dominio en
              el color real del suyo (`HazardCards.tsx`); solo niveles y recuentos: la sección es
              compartida. */}
          <BoardOnly>
            <DomainLevelTally domains={status.domains} />
          </BoardOnly>
        </section>,
        personal(<SummaryTiles status={status} alerts={alerts.length} />),
        <HazardCards status={status} />,
        <section data-ui="alerts" className="panel" aria-label={tr("Alertas", "Alerts")}>
          <PanelTitle concept="alerts">{tr("Alertas activas", "Active alerts")}</PanelTitle>
          {/* Tablero (2026-11-07): los recuentos de F.6.4 de la franja (`counts`), lo sin reconocer y
              lo silenciado, como píldoras (`HazardCards.tsx`). Sin quién: la sección es compartida. */}
          <BoardOnly>
            <AlertTally counts={counts} />
          </BoardOnly>
          {decides && (
            <FieldLabel concept="person" className="operator">
              {tr("Tripulante en consola", "Crew member at the console")}{" "}
              {/* Con la privacidad, ni en pantalla ni en el lector de pantalla (`OperatorInput`). */}
              <OperatorInput value={operator} onChange={setOperator} privacy={modes.privacy} />
              <span className="secondary">
                {" "}
                {tr(
                  "Queda firmado en el registro con cada reconocimiento, supresión, inhibición o contramedida adoptada.",
                  "Signed in the record with every acknowledgement, suppression, inhibition or adopted countermeasure.",
                )}
              </span>
            </FieldLabel>
          )}
          {alerts.length === 0 ? (
            <p className="secondary">
              <MarkOf mark={OK_MARK}>{tr("Ningún dominio fuera de lo nominal.", "No domain off nominal.")}</MarkOf>
            </p>
          ) : (
            alerts.map((alert) => (
              <AlertRow
                key={alert.id}
                alert={alert}
                state={status.alerts.find((item) => item.id === alert.id)}
                status={status}
                operator={operator}
                actions={actions}
                sync={sync}
              />
            ))
          )}
        </section>,
        <section data-ui="recommendations" className="panel" aria-label={tr("Recomendaciones", "Recommendations")}>
          <PanelTitle concept="recommendations">{tr("Qué hacer", "What to do")}</PanelTitle>
          {/* Tablero (2026-11-07): cuántas recomendaciones hay y cuántos seguimientos siguen abiertos
              (los mismos que cuenta «Inicio»: `followups` no cerrados, no las contramedidas distintas
              de `following`), como píldoras neutras con el dibujo de su concepto; el magenta de «lo
              propone la automatización» sigue en el filete de cada tarjeta. */}
          <BoardOnly>
            <div className="board-tally" role="group" aria-label={tr("Recuento de recomendaciones", "Recommendation counts")}>
              <CountPill
                pictogram={uiPictogram("recommendations")}
                count={recommendations.length}
                one={tr("recomendación", "recommendation")}
                many={tr("recomendaciones", "recommendations")}
              />
              <CountPill
                pictogram={uiPictogram("followUp")}
                count={status.followups.filter((item) => item.state !== "closed").length}
                one={tr("seguimiento abierto", "open follow-up")}
                many={tr("seguimientos abiertos", "open follow-ups")}
              />
            </div>
          </BoardOnly>
          {recommendations.length === 0 ? (
            <p className="secondary">
              <Mark pictogram={OK_MARK.pictogram} color={OK_MARK.color}>
                {tr("Sin recomendaciones: nada requiere acción.", "No recommendations: nothing requires action.")}
              </Mark>
            </p>
          ) : (
            // En rejilla de tarjetas (§5.40, tableta): una columna en vertical, dos en apaisado.
            <div className="recommendations">
              <RecommendationList
                items={recommendations}
                operator={operator}
                following={following}
                onAdopt={countermeasureActions.adopt}
                onDecline={countermeasureActions.decline}
              />
            </div>
          )}
        </section>,
      ],
    },
    {
      key: "routines",
      setAside: true,
      label: "Rutinas y notas",
      pictogram: uiPictogram("routines"),
      panels: [
        <ThisWeek status={status} />,
        <Routines status={status} />,
        <Waiting subject={status.subject} />,
        <FollowupsPanel status={status} operator={operator} onClose={countermeasureActions.close} />,
        // Lo que Tierra ha firmado para este tripulante o para todos, ya llegado (§5.38.1).
        <GroundNotesPanel subject={status.subject} oneWayMinutes={status.comms?.one_way_minutes ?? null} comms={commsStatusOf(status)} />,
      ],
    },
    {
      key: "body",
      setAside: true,
      label: "Cuerpo",
      pictogram: uiPictogram("body"),
      // Lo corto arriba y el modo anatómico, largo, al final a todo el ancho (tablero, 2026-11-07).
      panels: [
        <DomainsPanel status={status} anatomy={anatomy} region={region} setRegion={setRegion} />,
        <Predictions predictions={status.predictions} onlyConcerning />,
        <InferredPanel inferred={status.inferred} />,
        <AnatomyPanel
          status={status}
          view={anatomy}
          selected={region}
          onSelect={setRegion}
          momentKey={moment}
          onMoment={setMoment}
          operator={operator}
          following={following}
          onAdopt={countermeasureActions.adopt}
        />,
      ],
    },
    {
      key: "mission",
      setAside: true,
      label: "Misión y hábitat",
      pictogram: uiPictogram("habitat"),
      panels: [
        // El nivel de misión (desconexión progresiva): se declara desde esta consola.
        <MissionModePanel controls />,
        // El enlace con Tierra simulado: lo pendiente de enviar y el mando para declararlo (§5.47).
        <LinkSyncPanel sync={sync} referenceTime={status.data.reference_time} onDeclared={onLinkDeclared} />,
        // Cada panel es un ítem de la rejilla del tablero (2026-11-07): dosis y escalas ya no van en
        // una `grid-2` propia, y lo largo (crónica, gemelos, hábitat) queda al final a todo el ancho.
        <DoseMeter dose={status.dose} />,
        <RadiationScales
          status={status}
          operator={operator}
          onDeclareProfile={countermeasureActions.declareProfile}
        />,
        <ResourcesPanel
          missionStart={status.mission.start}
          referenceTime={status.data.reference_time}
          operator={operator}
        />,
        <MissionTimeline
          status={status}
          operator={operator}
          onDeclareEvent={declareEvent}
          onMoment={chooseMomentFromChronicle}
        />,
        // La misma clave que en Tierra, sin corte (`twinsRefreshKey`, §5.37.17).
        <TwinQuestionsPanel subject={status.subject} refreshKey={twinsRefreshKey(status)} />,
        <HabitatPanel
          missionStart={status.mission.start}
          refreshKey={`${status.data.reference_time}|${status.mission.sources.join(",")}|${declared}`}
          operator={operator}
        />,
      ],
    },
    {
      key: "data",
      setAside: true,
      label: "Calidad y sensores",
      pictogram: uiPictogram("dataQuality"),
      panels: [
        <MonitoringPanel monitoring={status.monitoring} />,
        <Basis status={status} />,
        <QualityPanel quality={quality} />,
        // Junto a la calidad del dato: qué lecturas cuentan, y contra qué base se juzgan.
        <BaselineProfilePanel
          subject={status.subject}
          refreshKey={baselineRefreshKey(status)}
        />,
        // Junto a la base: el sexo declarado y el ciclo, con la frase de la base por fase (lote «ciclo»).
        <CycleSection
          subject={status.subject}
          refreshKey={baselineRefreshKey(status)}
          phaseBaseline={status.cycle_phase?.reason ?? null}
        />,
        // Conectar una banda de pulso real (petición del usuario, 2026-11-12).
        // Firma para el tripulante real de la banda y, con su primera lectura, la consola pasa a él.
        <HeartBandPanel subject={status.subject} onChooseSubject={onChooseSubject} />,
        <SensorBindingsPanel
          subject={status.subject}
          missionStart={status.mission.start}
          referenceTime={status.data.reference_time}
          operator={operator}
        />,
        // Junto a los sensores: a dónde va cada dato que entra por ellos y por la consola.
        <SharingPanel />,
      ],
    },
    {
      key: "log",
      setAside: true,
      label: "Diario y pruebas",
      pictogram: uiPictogram("diary"),
      panels: [
        // Lo que se rellena a mano y las pruebas cortas arriba; descriptivos y batería, largos, al
        // final a todo el ancho (tablero, 2026-11-07).
        <DiaryPanel subject={status.subject} />,
        <FoodAcceptabilityPanel
          subject={status.subject}
          refreshKey={`${status.data.reference_time}|${status.data.observations}`}
        />,
        <PainPanel subject={status.subject} />,
        <PvtPanel subject={status.subject} />,
        <DescriptivePanel
          subject={status.subject}
          refreshKey={`${status.data.reference_time}|${status.data.observations}`}
        />,
        <CognitionPanel subject={status.subject} />,
      ],
    },
    {
      key: "imaging",
      setAside: true,
      label: "Imagen e informes",
      pictogram: "picture",
      panels: [
        <UltrasoundPanel subject={status.subject} />,
        <ReportsPanel subject={status.subject} />,
        <VolumesPanel subject={status.subject} />,
      ],
    },
    {
      // El planificador de la casa (Marplanner, decisión del usuario 2026-11-12): tareas, menú,
      // calendario y recordatorios, con el estilo de EMMA. No es dato de salud.
      key: "planner",
      setAside: true,
      label: "Planificador",
      pictogram: uiPictogram("nextDays"),
      panels: [
        <PlannerChoresPanel />,
        <PlannerMenuPanel />,
        <PlannerWeekMenuPanel />,
        <PlannerCalendarPanel />,
        <PlannerRemindersPanel />,
        <PlannerMessagesPanel />,
        <PlannerBriefingPanel subject={status.subject} />,
        <PlannerAnnouncementsPanel />,
        <PlannerRoutinesPanel />,
        <PlannerRecipesPanel />,
        <PlannerMealPlansPanel />,
        <PlannerMembersPanel />,
        <PlannerDayPeriodsPanel />,
      ],
    },
    {
      key: "library",
      setAside: true,
      label: "Biblioteca",
      pictogram: uiPictogram("countermeasureLibrary"),
      panels: [<LibraryPanel />, <GuidesPanel />],
    },
    // Una pestaña por entorno, tal y como los sirve el backend (`Environments.tsx`); se eligen en la cabecera,
    // bajo «Entorno de la misión» (`headerGroup`), no en el carril.
    // A bordo se puede declarar otro entorno (`DeclareEnvironment`); en Tierra, no.
    ...environmentSections(environments, declareProfile),
  ];

  return (
    <ConsoleTabs
      id="crew"
      label={tr("Secciones de la consola de tripulación", "Crew console sections")}
      sections={sections}
      counts={counts}
      header={<ActiveEnvironment profile={status.mission.profile} />}
      headerGroup={ENVIRONMENTS_GROUP}
      stored={section}
      onChoose={setSection}
    />
  );
}
