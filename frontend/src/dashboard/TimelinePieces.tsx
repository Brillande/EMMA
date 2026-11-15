import { type CSSProperties, type ReactNode, useEffect, useState } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { BoardOnly } from "../components/BoardOnly";
import { Command } from "../components/Command";
import { DomainName } from "../components/DomainName";
import { Fold } from "../components/Fold";
import { IndicatorName } from "../components/IndicatorName";
import { LevelBadge } from "../components/LevelBadge";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { StatTile } from "../components/StatTile";
import { Loading } from "../components/Unavailable";
import {
  type AlertHistory,
  type ChronicleEvent,
  type ChronicleView,
  type CrewStatus,
  type DependsView,
  type RoutineState,
  type RoutineStreaks,
  type TimelineAsOf,
  type WaitingView,
  type WeekView,
  api,
} from "../lib/api";
import { formatDay, formatMet, formatNumber, formatUtc, missionElapsedSeconds } from "../lib/format";
import { tr } from "../lib/i18n";
import { ROUTINE_WORDS } from "../lib/routineWords";
import { isLevel } from "../lib/levels";
import { OK_MARK, type RequestOutcome, type StateMark, requestOutcome } from "../lib/marks";
import { cssVar } from "../lib/palette";
import {
  RECOMPUTED_PICTOGRAM,
  closedCount,
  episodeRows,
  eventMark,
  historyNotes,
} from "./alertHistory";
import { ImpactBar, Ring } from "./HomeCharts";
import {
  INCONGRUENCE_MARK,
  SEVERITY_MARKS,
  STREAK_MARK,
  asOfMark,
  dependsModeMark,
  eventKindMark,
  routineMark,
  stagePictogram,
} from "./timelineMarks";

/*
 * Tres piezas de Polaris con datos de EMMA (`app/timeline.py`): la cronica, lo que vence esta
 * semana y que depende de un dato. Todo el texto sale del backend; aqui solo se ordena. Van en el
 * tiempo de los datos, no en el del ordenador: cada una dice hasta cuando cuenta (`as_of`) y de
 * donde sale ese ahora. Los unicos colores son los de la tabla F.5-1, con su sentido, y cada
 * señal lleva su pictograma junto a la palabra (F.5.10 e; tablas en `timelineMarks.ts`).
 *
 * Cada pieza esta partida en dos: la que pide los datos (`Chronicle`, `Routines`, `Waiting`,
 * `DependsOn`) y la que los pinta (`ChronicleBody`, `RoutineList`, `WaitingBody`, `DependsList`).
 * La segunda no tiene estado ni efectos, y por eso se puede probar pintandola con un ejemplo.
 *
 * Tablero (decisión del usuario, 2026-11-07: cada sección como «Inicio»): las piezas de cifra
 * grande, anillo, píldora y barra (`HomeCharts`, `StatTile`) van dentro de `BoardOnly`, solo en la
 * concha de la maqueta, y salen de los datos que cada pieza ya tenía: ninguna pide nada nuevo ni
 * inventa una escala (la del anillo es «cuántas de las que se deben»; la de la barra de una racha,
 * su racha más larga). La clásica (`#clasica`) sigue pintando lo de siempre.
 */

type Met = (iso: string) => string;

/**
 * La variable `--lvl` que tiñe una píldora de recuento (`.ref-pill`) con el color REAL de su marca,
 * como `LevelPill` hace con el nivel: el amarillo de una medida rota o el gris de lo que nunca
 * corrió ya van en la marca junto a la palabra (tabla F.5-1); aquí solo se extiende al filete. Una
 * marca sin color deja la píldora en el tono neutro de la hoja. La usan también las notas de Tierra
 * (`GroundNotesPanel`); su sitio natural es junto a `levelTint` en `HomeCharts.tsx`, que esta
 * unidad no edita.
 */
export function markTint(mark: StateMark): CSSProperties | undefined {
  return mark.color === null ? undefined : ({ "--lvl": `var(${cssVar(mark.color)})` } as CSSProperties);
}

/**
 * La palabra de lo que nunca corrió, una sola vez para la píldora y la frase de abajo. Las de
 * «atrasada» y «rota» viven en `lib/routineWords.ts` (compartidas con la voz); esta debería ir allí
 * con ellas cuando esa tabla se toque.
 */
const NEVER_RUN_WORD = tr("sin ninguna lectura", "with no reading");

function useMet(status: CrewStatus): Met {
  return (iso: string) => formatMet(missionElapsedSeconds(status.mission.start, new Date(iso)));
}

/**
 * Hasta cuando cuenta una pieza de la linea temporal y de donde sale ese ahora (texto del
 * backend). Si no sale de las lecturas es que faltan: cian con su anillo punteado, "dato ausente"
 * (F.5-1). El reloj real no es tiempo de mision: se escribe en UTC, no como MET.
 */
export function AsOf({ view, met }: { view: TimelineAsOf; met: Met }) {
  const moment =
    view.as_of_source === "clock" ? formatUtc(new Date(view.as_of)) : met(view.as_of);
  const signal = asOfMark(view.as_of_source);
  return (
    <p className={signal.pictogram === null ? "secondary" : undefined}>
      <Mark pictogram={signal.pictogram} color={signal.color}>
        A fecha de <span className="num">{moment}</span> · {view.as_of_basis}
      </Mark>
    </p>
  );
}

/**
 * La insignia de un hecho que es una alerta: su nivel con pictograma, palabra y color (F.5.10 e),
 * delante de la frase. Las demas señales van pegadas a la frase (`EventText`).
 */
function EventSignal({ event }: { event: ChronicleEvent }) {
  if (eventMark(event) !== "level" || event.level === null || !isLevel(event.level)) return null;
  return (
    <>
      <LevelBadge level={event.level} />{" "}
    </>
  );
}

/**
 * La frase de un hecho, con el pictograma de su tipo delante (`tipo` del backend: alerta,
 * contramedida, mision, habitat...; sin `title`: la clave de la API no es texto para la
 * tripulacion, y la frase ya dice que paso) y, si la tiene, su señal pegada a la frase: una
 * excursion de cabina lleva el amarillo con triangulo del limite normativo o el azul con rombo
 * de la zona de confort o del rango objetivo, como en el panel del habitat. Solo el pictograma
 * toma ese color: la frase sigue en el color del texto (`c-text`), como la de una alerta junto a
 * su insignia, para que una excursion no pese mas que una alerta clinica. Lo recalculado hoy
 * (`alertHistory.ts`) no es ninguna de las dos cosas: su pictograma y todo lo demas en secundario,
 * y la frase del backend empieza por su rotulo.
 */
function EventText({ event }: { event: ChronicleEvent }) {
  const kind = eventKindMark(event.tipo);
  const signal = eventMark(event);
  let text: ReactNode = event.que;
  if (signal === "recomputed") {
    text = <Mark pictogram={RECOMPUTED_PICTOGRAM}>{event.que}</Mark>;
  } else if (signal === "health" || signal === "performance" || signal === "target") {
    const look = SEVERITY_MARKS[signal];
    text = (
      <Mark pictogram={look.pictogram} color={look.color}>
        <span className="c-text">{event.que}</span>
      </Mark>
    );
  }
  return (
    <Mark pictogram={kind.pictogram} color={kind.color} className={signal === "recomputed" ? "secondary" : undefined}>
      {text}
    </Mark>
  );
}

/**
 * La historia de las alertas ya cerradas, RECALCULADA: episodios por dominio, con el nivel
 * maximo como palabra (del backend) y no como insignia, porque no es una alerta activa. Lo que
 * es, lo que no es y hasta donde llega va siempre a la vista, tal cual lo redacta el backend; lo
 * que alguien firmo en esos pasos va al lado de cada episodio, sin mezclarlo.
 */
function RecomputedHistory({ history, met }: { history: AlertHistory; met: Met }) {
  const notes = historyNotes(history);
  if (notes === null) return null;
  return (
    <section data-ui="recomputed-history" aria-label={history.label}>
      <PanelTitle as="h3" pictogram={RECOMPUTED_PICTOGRAM}>
        {history.label} · <span className="num">{formatNumber(closedCount(history))}</span>{tr(" episodios cerrados", " closed episodes")}
      </PanelTitle>
      {notes.map((note) => (
        <p key={note} className="secondary">
          {note}
        </p>
      ))}
      <p className="secondary">
        {tr("Tope: ", "Cap: ")}<span className="num">{formatNumber(history.max_steps)}</span>{tr(" pasos de", " steps of")}{" "}
        <span className="num">{formatNumber(history.window_hours)}</span> h (
        {history.max_steps_basis}) · {history.rules_version}
      </p>
      {history.none_display !== null && <p className="secondary">{history.none_display}</p>}
      <ul className="drivers">
        {episodeRows(history).map((episode) => (
          <li key={episode.id}>
            {/* Solo el pictograma de recalculo va en secundario; el dominio, en el color del texto. */}
            <Mark pictogram={RECOMPUTED_PICTOGRAM} className="secondary">
              <span className="c-text">
                <DomainName domain={episode.domain} label={episode.domain_display} />
              </span>
            </Mark>
            : {episode.peak_level_display} ·{" "}
            <span className="num">{met(episode.first_step_start)}</span>{tr(" a", " to")}{" "}
            <span className="num">{met(episode.last_step_end)}</span> ·{" "}
            <span className="num">{formatNumber(episode.steps)}</span>{tr(" pasos ·", " steps ·")}{" "}
            {episode.state_display}
            {episode.start_note !== null && (
              <span className="secondary"> · {episode.start_note}</span>
            )}
            {episode.signed.length > 0 && (
              <ul className="drivers">
                {episode.signed.map((entry) => (
                  <li key={entry.ledger_index} className="secondary">
                    {tr("firmado aparte: ", "signed separately: ")}{entry.kind_display} ·{" "}
                    <span className="num">{met(entry.reference_time)}</span> · {entry.by}{tr(" · asiento", " · entry")}{" "}
                    <span className="num">{formatNumber(entry.ledger_index)}</span>
                    {/* Con qué reglas se firmó (§5.39.9): la frase del backend, sin color. */}
                    {entry.rules ? ` · ${entry.rules.text}` : ""}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * Un hito de la crónica que es un momento de «Cuerpo» (`event.moment`, lo decide el backend):
 * pulsarlo elige ese momento allí. El rótulo del momento, del backend, va en el `title`; el mando
 * lleva el dibujo del cuerpo, el de su panel. Sin `onMoment` (Tierra, o una prueba) no se pinta.
 */
function MomentLink({ event, onMoment }: { event: ChronicleEvent; onMoment?: OnMoment | undefined }) {
  const moment = event.moment ?? null;
  if (moment === null || onMoment === undefined) return null;
  return (
    <>
      {" "}
      <Command concept="body" title={moment.display} onClick={() => onMoment(moment.key)}>
        {tr("Ver en «Cuerpo»", "View in «Body»")}
      </Command>
    </>
  );
}

/**
 * El instante de un hecho, en su reloj: el de los datos, en tiempo de misión; una fecha que
 * declaró una persona para su carrera (misiones previas, `declared`), el día tal cual, sin hora
 * ni tiempo de misión, que serían una precisión que nadie declaró; y lo que solo tiene hora de
 * firma, en UTC.
 */
export function EventInstant({ event, met }: { event: ChronicleEvent; met: Met }) {
  if (event.time_basis === "data") return <>{met(event.at)}</>;
  if (event.time_basis === "declared") return <>{formatDay(event.fecha)}</>;
  return <>{formatUtc(new Date(event.at))}</>;
}

/** Elegir en «Cuerpo» el momento de un hito de la crónica, por su clave. */
export type OnMoment = (key: string) => void;

/**
 * La cronica pintada: su ahora, las etapas de la especificacion (§10) con su pictograma, cada
 * hecho con su instante en tiempo de mision, su tipo, su señal, quien y su fuente, y debajo la
 * historia recalculada. Sin estado: lo que llega se pinta tal cual, con lo ultimo arriba. Con
 * `onMoment`, cada hito que es un momento de «Cuerpo» lleva el mando que lo elige allí.
 */
export function ChronicleBody({
  view,
  met,
  onMoment,
}: {
  view: ChronicleView;
  met: Met;
  onMoment?: OnMoment | undefined;
}) {
  return (
    <>
      <AsOf view={view} met={met} />
      {view.events.length === 0 && (
        <p className="secondary">
          <MarkOf mark={OK_MARK}>{tr("sin hechos que contar todavía", "no events to report yet")}</MarkOf>
        </p>
      )}
      {view.stages
        .filter((stage) => stage.count > 0)
        .map((stage) => (
          <section data-ui="chronicle-stage" key={stage.key} aria-label={stage.display}>
            <PanelTitle as="h3" pictogram={stagePictogram(stage.key)}>
              {stage.display} · <span className="num">{formatNumber(stage.count)}</span>
            </PanelTitle>
            <ul className="drivers">
              {view.events
                .filter((event) => event.stage === stage.key)
                .reverse()
                .map((event) => (
                  <li key={event.clave}>
                    <span className="num">
                      <EventInstant event={event} met={met} />
                    </span>{" "}
                    <EventSignal event={event} />
                    <EventText event={event} />{" "}
                    <span className="secondary">
                      ({event.quien} · {event.fuente})
                    </span>
                    <MomentLink event={event} onMoment={onMoment} />
                  </li>
                ))}
            </ul>
          </section>
        ))}
      {view.recomputed !== null && <RecomputedHistory history={view.recomputed} met={met} />}
    </>
  );
}

/**
 * Cronica: lo que paso (alertas, fases, cabina) y lo que se decidio (asientos del ledger), por las
 * etapas de la especificacion (§10) y con lo ultimo arriba. Cada hecho, con su instante en tiempo
 * de mision, quien y su fuente; lo que solo tiene hora de firma va en su grupo y en UTC.
 *
 * Se pide al abrirla: para contarla el backend calcula el estado otra vez, y no merece la pena
 * en cada refresco de una consola que la tiene plegada.
 */
export function Chronicle({ status, onMoment }: { status: CrewStatus; onMoment?: OnMoment | undefined }) {
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<ChronicleView | null>(null);
  const [error, setError] = useState<RequestOutcome | null>(null);
  const met = useMet(status);
  useEffect(() => {
    if (!open) return;
    // Cada refresco pide otra vez: una respuesta vieja que llega tarde no pisa a la nueva, y un
    // refresco que falla no borra la crónica que ya se veía.
    let current = true;
    setError(null);
    api
      .chronicle(status.subject)
      .then((body) => {
        if (current) setView(body);
      })
      .catch((cause: unknown) => {
        if (current) setError(requestOutcome(cause));
      });
    return () => {
      current = false;
    };
  }, [status, open]);
  return (
    <Fold data-ui="chronicle"
      concept="history"
      onToggle={(event) => setOpen(event.currentTarget.open)}
      label={
        <>
          {tr("Crónica", "Chronicle")}
          {view !== null && (
            <>
              {" "}
              · <span className="num">{formatNumber(view.events.length)}</span>{tr(" hechos", " events")}
            </>
          )}
        </>
      }
    >
      {/* Contarla tarda (el backend recalcula el estado): mientras, la marca de carga; si
          falla, la de fallo con el motivo, en vez de un plegable vacío. */}
      {view === null && error === null && (
        <Loading />
      )}
      {view === null && error !== null && (
        <p>
          <MarkOf mark={error.mark}>{tr("No se pudo completar: ", "Could not complete: ")}{error.text}</MarkOf>
        </p>
      )}
      {view !== null && <ChronicleBody view={view} met={met} onMoment={onMoment} />}
    </Fold>
  );
}

/**
 * Lo que vence en los proximos dias: fin de seguimientos, horizontes y eventos de mision. Los
 * dias se cuentan desde el ahora de los datos, que se enseña, no desde hoy.
 */
export function ThisWeek({ status }: { status: CrewStatus }) {
  const [week, setWeek] = useState<WeekView | null>(null);
  const met = useMet(status);
  useEffect(() => {
    api
      .week(status.subject)
      .then(setWeek)
      .catch(() => setWeek(null));
  }, [status]);
  if (week === null) return null;
  return (
    <section data-ui="this-week" className="panel" aria-label={tr("Esta semana", "This week")}>
      <PanelTitle concept="nextDays">
        {tr("Próximos ", "Next ")}<span className="num">{formatNumber(week.days)}</span>{tr(" días", " days")}
      </PanelTitle>
      {/* Tablero: cuántas cosas tienen fecha en la ventana, como cifra grande; `0` es un recuento
          real (la frase de abajo lo dice con su marca), no un dato ausente. Sin semana no se monta
          el panel, así que la ficha nunca está sin valor. */}
      <BoardOnly>
        <div className="board-stats">
          <StatTile concept="nextDays" label={tr("Con fecha", "Dated")} value={week.items.length} unit={tr(`en ${formatNumber(week.days)} días`, `in ${formatNumber(week.days)} days`)} />
        </div>
      </BoardOnly>
      {/* Tablero (2026-11-08): el «a fecha de» que sale de las lecturas no señala nada y es una
          frase larga; va detrás de «Ver detalle». Si sale del corte o del reloj lleva la marca cian
          de dato ausente, y esa no se pliega. */}
      {week.as_of_source === "data" ? (
        <BoardDetail label={tr("a fecha de", "as of")}>
          <AsOf view={week} met={met} />
        </BoardDetail>
      ) : (
        <AsOf view={week} met={met} />
      )}
      {week.items.length === 0 ? (
        <p className="secondary">
          <MarkOf mark={OK_MARK}>{tr("nada con fecha en la ventana", "nothing dated in the window")}</MarkOf>
        </p>
      ) : (
        <ul className="drivers">
          {week.items.map((item) => (
            <li key={`${item.titulo}:${item.vence}`}>
              <span className="num">{met(item.vence)}</span> {item.titulo}
              {item.siguiente_accion !== "" && (
                <span className="secondary"> — {item.siguiente_accion}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/**
 * Que se recalcula solo (chip) y que tiene que revisar una persona (persona) si cambian estos
 * datos: el modo lo da el backend (`auto` / `humano`), el pictograma va junto al rotulo.
 */
export function DependsList({
  views,
  names = {},
}: {
  views: DependsView[];
  names?: Readonly<Record<string, string>> | undefined;
}) {
  if (views.length === 0) return <span className="secondary">—</span>;
  return (
    <ul className="drivers">
      {views.map((view) => {
        const human = view.affected.filter((item) => item.mode === "humano");
        const auto = view.affected.filter((item) => item.mode === "auto");
        return (
          <li key={view.key}>
            <IndicatorName
              indicatorKey={view.key}
              displayEs={Object.hasOwn(names, view.key) ? (names[view.key] ?? view.key) : view.key}
            />:{" "}
            <Mark pictogram={dependsModeMark("auto").pictogram}>
              {tr("se recalcula ", "recomputed: ")}{auto.map((item) => item.title).join(", ") || "—"}
            </Mark>
            {human.length > 0 && (
              <>
                {" · "}
                <Mark pictogram={dependsModeMark("humano").pictogram}>
                  {tr("a revisar por una persona: ", "for a person to review: ")}{human.map((item) => item.title).join(", ")}
                </Mark>
              </>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export function DependsOn({ keys, names }: { keys: string[]; names?: Readonly<Record<string, string>> }) {
  const [views, setViews] = useState<DependsView[]>([]);
  const joined = keys.join(",");
  useEffect(() => {
    if (joined === "") {
      setViews([]);
      return;
    }
    Promise.all(joined.split(",").map((key) => api.dependsOn(key).catch(() => null)))
      .then((all) => setViews(all.filter((view): view is DependsView => view !== null)))
      .catch(() => setViews([]));
  }, [joined]);
  return <DependsList views={views} names={names} />;
}

/** El orden del tablero: lo que hay que mirar primero, lo que va bien al final. */
const ROUTINE_BOARD_ORDER: readonly RoutineState["state"][] = ["rota", "atrasada", "nunca-corrio", "al-dia"];

/** La palabra de cada estado en el tablero: las de `ROUTINE_WORDS`, la de lo que nunca corrió y «al día». */
function routineWord(state: RoutineState["state"]): string {
  if (state === "al-dia") return tr("al día", "on time");
  if (state === "nunca-corrio") return NEVER_RUN_WORD;
  return ROUTINE_WORDS[state];
}

/**
 * La marca de un estado en el tablero: la de siempre (`routineMark`), y para «al día», que en la
 * lista no lleva ninguna, la de visto sin color (`OK_MARK`): el mosaico y la ficha necesitan un
 * dibujo junto a la palabra, y esa es la marca de «hecho, sin nada que señalar».
 */
function boardRoutineMark(state: RoutineState["state"]): StateMark {
  return state === "al-dia" ? OK_MARK : routineMark(state);
}

/**
 * Medidas que no llegan a su ritmo (Polaris `estado_rutina`), pintadas. "Rota" en amarillo con
 * triangulo: falta un dato, hay que mirarlo (F.5-1), pero no es una alarma clinica; "atrasada"
 * con su reloj de arena, sin color. Lo que nunca corrio va en gris ("no disponible") con el
 * circulo tachado, contado y sin lista: en un escenario sin esas medidas es lo esperado. El
 * nombre de cada medida lleva el dibujo de su familia (`IndicatorName`) y el estado, su marca
 * junto a su palabra; si todas van a su ritmo, la marca de visto (`OK_MARK`).
 *
 * Mientras dura un evento solar (2026-11-02) el backend acorta el periodo de las medidas clave y
 * las pone primero: la lista conserva su orden, y la frase del panel (`note`) y la de cada medida
 * (`period_note`) salen tal cual del backend. Sin evento no se pinta nada nuevo.
 */
export function RoutineList({ items, met, note }: { items: RoutineState[]; met: Met; note?: string | null }) {
  // Lo que el nivel de misión suspende no se debe: ni atrasada ni pendiente (`suspended`).
  const owed = items.filter((item) => item.suspended !== true);
  const late = owed.filter((item) => item.state === "atrasada" || item.state === "rota");
  const never = owed.filter((item) => item.state === "nunca-corrio").length;
  const none = routineMark("nunca-corrio");
  // Tablero: cuántas van al día de las que se deben (el anillo), un mosaico por estado con su
  // marca, su palabra y su recuento (los cuatro siempre: un 0 es un recuento real, no un hueco), y
  // debajo cada medida que se debe como ficha con la marca de su estado, lo roto y lo atrasado
  // primero. Todo sale de la lista que ya llega (`/timeline/routines`).
  const onTime = owed.filter((item) => item.state === "al-dia").length;
  const tiles = ROUTINE_BOARD_ORDER.map((state) => ({
    state,
    look: boardRoutineMark(state),
    word: routineWord(state),
    count: owed.filter((item) => item.state === state).length,
  }));
  const chips = [...owed].sort(
    (a, b) => ROUTINE_BOARD_ORDER.indexOf(a.state) - ROUTINE_BOARD_ORDER.indexOf(b.state),
  );
  return (
    <>
      {note ? <p className="secondary">{note}</p> : null}
      <BoardOnly>
        {owed.length > 0 && (
          <>
            <div className="board-row routine-board">
              <div className="ref-ring-col">
                <Ring done={onTime} total={owed.length} label={tr("medidas al día", "measurements on time")}>
                  <span className="num ref-ring-value">{formatNumber(onTime)}</span>
                  <span className="num secondary">/ {formatNumber(owed.length)}</span>
                </Ring>
                <p className="secondary ref-ring-caption">{tr("al día", "on time")}</p>
              </div>
              <ul className="routine-tiles" aria-label={tr("Medidas por estado", "Measurements by state")}>
                {tiles.map((tile) => (
                  <li
                    key={tile.state}
                    className="routine-tile"
                    data-count={tile.count}
                    // Un estado con 0 conserva su marca (es la leyenda de las fichas), pero su filete
                    // queda neutro: un amarillo alrededor de un 0 llamaría la atención sin motivo.
                    style={tile.count > 0 ? markTint(tile.look) : undefined}
                  >
                    <span className="num routine-tile-num">{formatNumber(tile.count)}</span>{" "}
                    <MarkOf mark={tile.look}>{tile.word}</MarkOf>
                  </li>
                ))}
              </ul>
            </div>
            {/* Cada medida con la marca de su estado, en una línea; la palabra va en el mosaico de
                arriba (la leyenda), y el nombre entero con ella en el `title` y para el lector de
                pantalla: la ficha no repite la palabra 27 veces ni crece a tres líneas. */}
            <ul className="routine-chips" aria-label={tr("Medidas que se deben", "Measurements due")}>
              {chips.map((item) => {
                const look = boardRoutineMark(item.state);
                return (
                  <li
                    key={item.key}
                    className="routine-chip"
                    style={markTint(look)}
                    title={`${item.display_es}: ${routineWord(item.state)}`}
                  >
                    <MarkOf mark={look}>{item.display_es}</MarkOf>
                    <span className="sr-only">: {routineWord(item.state)}</span>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </BoardOnly>
      {late.length === 0 ? (
        <p className="secondary">
          <MarkOf mark={OK_MARK}>{tr("Todas las que llegan, a su ritmo.", "All that arrive are on schedule.")}</MarkOf>
        </p>
      ) : (
        <ul className="drivers">
          {late.map((item) => {
            const look = routineMark(item.state);
            return (
              <li key={item.key}>
                <IndicatorName indicatorKey={item.key} displayEs={item.display_es} />:{" "}
                <MarkOf mark={look}>{ROUTINE_WORDS[item.state === "rota" ? "rota" : "atrasada"]}</MarkOf>{" "}
                <span className="secondary">
                  {tr("· última ", "· last ")}{item.last_run === null ? "—" : <span className="num">{met(item.last_run)}</span>}
                  {tr(" · cada ", " · every ")}<span className="num">{formatNumber(item.period_hours)}</span> h ({item.basis})
                  {item.period_note ? <> · {item.period_note}</> : null}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      {never > 0 && (
        <p>
          <MarkOf mark={none}>
            <span className="num">{formatNumber(never)}</span>{tr(" medidas ", " measurements ")}{NEVER_RUN_WORD}
          </MarkOf>
        </p>
      )}
    </>
  );
}

/**
 * Rachas de las medidas periodicas (`routines.streaks`, gamificacion del reto): cuantos periodos
 * de diseño seguidos llego cada una con lectura buena, como cifra (`formatNumber`) junto a la fila
 * de puntos de «periodica», sin color. Sin porcentaje, sin color ni animacion de premio (la tabla
 * F.5-1 no tiene ese significado) y fuera del riesgo. El texto de la racha (rotulo, nota, unidad y
 * «la mas larga») lo da el backend; lo unico de aqui es el «cada N h (base)» que ya escribe
 * `RoutineList` para el mismo periodo. Solo las medidas que han tenido alguna racha; plegado, para no competir con lo que
 * falta, que es lo que hay que mirar. El dibujo, en `timelineMarks.ts` (`STREAK_MARK`).
 *
 * Tablero: junto a las dos cifras, la barra de la racha actual sobre la más larga (`ImpactBar`,
 * adorno junto a la cifra que se lee); la escala es la propia serie (`longest`, que aquí es > 0),
 * no un objetivo, y la barra no lleva color ni porcentaje escrito: sigue siendo un recuento.
 */
export function RoutineStreakList({ view }: { view: RoutineStreaks }) {
  const shown = view.routines.filter((item) => item.longest > 0);
  if (shown.length === 0) return null;
  return (
    <Fold data-ui="routine-streaks" mark={STREAK_MARK} label={view.label}>
      <p className="secondary">{view.note}</p>
      <ul className="drivers">
        {shown.map((item) => (
          <li key={item.key}>
            <IndicatorName indicatorKey={item.key} displayEs={item.display_es} />:{" "}
            <MarkOf mark={STREAK_MARK}>
              <span className="num">{formatNumber(item.current)}</span> {item.unit}
            </MarkOf>{" "}
            <BoardOnly>
              <ImpactBar share={item.current / item.longest} />{" "}
            </BoardOnly>
            <span className="secondary">
              · {view.longest_label} <span className="num">{formatNumber(item.longest)}</span>{tr(" · cada", " · every")}{" "}
              <span className="num">{formatNumber(item.period_hours)}</span> h ({item.basis})
            </span>
          </li>
        ))}
      </ul>
    </Fold>
  );
}

export function Routines({ status }: { status: CrewStatus }) {
  const [items, setItems] = useState<RoutineState[] | null>(null);
  const [streaks, setStreaks] = useState<RoutineStreaks | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [suspendedNote, setSuspendedNote] = useState<string | null>(null);
  const met = useMet(status);
  useEffect(() => {
    api
      .routines(status.subject)
      .then((body) => {
        setItems(body.routines);
        setStreaks(body.streaks ?? null);
        setNote(body.event_note ?? null);
        setSuspendedNote(body.suspended_note ?? null);
      })
      .catch(() => {
        setItems(null);
        setStreaks(null);
        setNote(null);
        setSuspendedNote(null);
      });
  }, [status]);
  if (items === null) return null;
  return (
    <section data-ui="routines" className="panel" aria-label={tr("Medidas periódicas", "Periodic measurements")}>
      <PanelTitle concept="routines">{tr("Medidas periódicas", "Periodic measurements")}</PanelTitle>
      {suspendedNote !== null && <p className="secondary">{suspendedNote}</p>}
      <RoutineList items={items} met={met} note={note} />
      {/* Tablero (2026-11-08): las rachas son el ritmo de diseño, una lectura de apoyo: detrás de
          «Ver detalle», con su pliegue dentro (mismo `data-ui`). */}
      {streaks !== null && streaks.routines.some((item) => item.longest > 0) && (
        <BoardDetail label={tr("ritmo de diseño", "design cadence")}>
          <RoutineStreakList view={streaks} />
        </BoardDetail>
      )}
    </section>
  );
}

/**
 * Lo que lleva dias esperando a alguien (Polaris `atascos`), pintado: reconocer, resolver,
 * confirmar, firmar o volver a medir. Es informacion, sin color propio; lo que no cuadra entre
 * analiticas va en amarillo con triangulo.
 */
export function WaitingBody({ view }: { view: WaitingView }) {
  return (
    <>
      {view.incongruences.map((item) => (
        <p key={`${item.sample}:${item.key}`}>
          <Mark pictogram={INCONGRUENCE_MARK.pictogram} color={INCONGRUENCE_MARK.color}>
            {item.key}, {item.sample}{tr(": dos informes no coinciden", ": two reports do not match")}
          </Mark>
        </p>
      ))}
      {view.waiting.length > 0 && (
        <ul className="drivers">
          {view.waiting.map((item, index) => (
            <li key={`${item.kind}:${item.title}:${index}`}>
              {item.title} <span className="secondary">· <span className="num">{formatNumber(item.days)}</span>{tr(" días", " days")}</span>
            </li>
          ))}
        </ul>
      )}
      {view.threshold_days !== null && (
        <p className="secondary">
          {tr("Solo lo que lleva ", "Only what has been waiting ")}<span className="num">{formatNumber(view.threshold_days)}</span>{tr(" días o más.", " days or more.")}
        </p>
      )}
    </>
  );
}

/** EMMA no actua solo, y lo que espera se olvida si nadie lo junta. */
export function Waiting({ subject }: { subject: string }) {
  const [view, setView] = useState<WaitingView | null>(null);
  useEffect(() => {
    api
      .waiting(subject)
      .then(setView)
      .catch(() => setView(null));
  }, [subject]);
  if (view === null || (view.waiting.length === 0 && view.incongruences.length === 0)) return null;
  return (
    <section data-ui="waiting" className="panel" aria-label={tr("Espera por una persona", "Waiting on a person")}>
      <PanelTitle concept="waiting">{tr("Espera por una persona", "Waiting on a person")}</PanelTitle>
      <WaitingBody view={view} />
    </section>
  );
}
