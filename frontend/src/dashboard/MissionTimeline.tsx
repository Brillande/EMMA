import { useEffect, useState } from "react";

import { statePictogram } from "../advisor/followups";
import { BoardDetail } from "../components/BoardDetail";
import { BoardOnly } from "../components/BoardOnly";
import { Chosen } from "../components/Chosen";
import { Command } from "../components/Command";
import { FieldLabel } from "../components/FieldLabel";
import { Fold } from "../components/Fold";
import { Mark, MarkOf } from "../components/Mark";
import { Meter } from "../components/Meter";
import { type CrewStatus, type HabitatModules, type ShiftBasis, api } from "../lib/api";
import { formatMet, formatNumber, missionElapsedSeconds } from "../lib/format";
import { type RequestOutcome, requestOutcome } from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";
import { RouteArt } from "./HomeArt";
import { EphemerisCoverageView, MissionBoardWarnings, MissionProfileView } from "./MissionProfileView";
import { eventPictogram, gravityPictogram, phasePictogram } from "./missionPictograms";
import { Chronicle, type OnMoment } from "./TimelinePieces";

const EVENT_LABEL = {
  eva: "EVA",
  workload: "bloque de trabajo",
  location: "ubicación",
  shift: "cambio de turno",
} as const;

/** De quien es una ubicacion declarada y en que modulo de la lista del backend. */
export interface DeclaredWhere {
  subject: string;
  module: string;
}

export type DeclareEvent = (
  kind: string,
  start: string,
  end: string,
  label: string,
  by: string,
  where?: DeclaredWhere,
) => Promise<void>;

/**
 * Linea temporal de la especificacion (§10): prevuelo → dia de mision → intervencion →
 * seguimiento → posvuelo. Cada fase lleva su pictograma junto a la palabra del backend
 * (`missionPictograms.ts`), y la actual se marca ademas con el anillo con punto de «elegido /
 * actual» (`ring-dot`; el disco lleno es «medido») y la palabra (F.5.10 e), no solo con color; las intervenciones son las contramedidas adoptadas y en
 * seguimiento; los eventos del plan (EVA, bloques de trabajo, cambios de turno y ubicacion, §3
 * MissionContext) los declara una persona y quedan firmados, cada tipo con su dibujo. La base de
 * los limites de fase la da el backend: son de diseno. Los nombres de las fases tambien: este panel tenia su propia
 * lista y no coincidia con la suya. La gravedad es la frase del backend (`gravity_display`): en
 * posvuelo, la del momento y la de la mision. Antes se pintaba la de configuracion, y en posvuelo
 * decia «microgravedad». Solo en posvuelo lleva dibujo (la bola en el suelo), porque solo ahi la
 * fija el backend; no se lee la de configuracion para elegir uno.
 *
 * `onMoment` (decimoquinta ronda, §5.35.8): con él, cada hito de la crónica que es un momento de
 * «Cuerpo» (un cambio de fase, una toma posvuelo) lleva el mando que elige ese momento allí.
 *
 * Tablero (decisión del usuario, 2026-11-07): bajo la concha de la maqueta, entre las fases y la
 * línea del día, el día de misión sobre la duración prevista en el medidor neutro (la escala la da
 * el backend; fuera de ella no se recorta: el medidor dice la fase que nombra el backend, como las
 * baldosas del resumen) y, en píldoras, las intervenciones en seguimiento y cerradas y los eventos
 * declarados. Son las mismas cifras de la línea de abajo, que las dice con palabras; los dibujos son
 * los de su concepto (la lupa del seguimiento, el visto de lo cerrado, la pluma de lo declarado). La
 * clásica no monta nada de esto (`BoardOnly`).
 */
export function MissionTimeline({
  status,
  operator,
  onDeclareEvent,
  onMoment,
}: {
  status: CrewStatus;
  operator?: string;
  onDeclareEvent?: DeclareEvent;
  onMoment?: OnMoment;
}) {
  const mission = status.mission;
  const open = status.followups.filter((item) => item.state !== "closed").length;
  const closed = status.followups.length - open;
  const met = (iso: string) => formatMet(missionElapsedSeconds(mission.start, new Date(iso)));
  // Solo en Tierra hay dibujo; en vuelo la frase de configuracion va sola (`missionPictograms.ts`).
  const gravity = gravityPictogram(mission.phase);
  return (
    <section data-ui="mission-timeline" className="panel timeline" aria-label="Línea temporal de la misión">
      <ol className="phases">
        {mission.phases.map((phase) => {
          const current = phase.key === mission.phase;
          const name = <Mark pictogram={phasePictogram(phase.key)}>{phase.display}</Mark>;
          return (
            <li key={phase.key} aria-current={current ? "step" : undefined}>
              <Chosen chosen={current}>{name}</Chosen>
            </li>
          );
        })}
      </ol>
      <BoardOnly>
        <div className="board-row timeline-board">
          {/* El dibujo de la ruta de «Inicio» (Tierra, trayectoria, nave y destino), como la tarjeta
              «Rutas espaciales» de la maqueta: adorno; el destino sale del perfil declarado. */}
          {mission.profile != null && mission.profile.known && (
            <RouteArt target={mission.profile.display} targetId={mission.profile.id} />
          )}
          {mission.duration_days > 0 && (
            <Meter
              value={mission.mission_day}
              max={mission.duration_days}
              label="Día de misión sobre la duración prevista"
              outOfRange={{ word: mission.phase_display }}
            />
          )}
          <ul className="board-tally" aria-label="Intervenciones y eventos declarados">
            <li className="ref-pill board-pill">
              <Mark pictogram={uiPictogram("followUp")}>en seguimiento</Mark> <span className="num">{formatNumber(open)}</span>
            </li>
            <li className="ref-pill board-pill">
              <Mark pictogram={statePictogram("closed")}>cerradas</Mark> <span className="num">{formatNumber(closed)}</span>
            </li>
            <li className="ref-pill board-pill">
              <Mark pictogram={uiPictogram("declare")}>eventos declarados</Mark>{" "}
              <span className="num">{formatNumber(mission.events.length)}</span>
            </li>
          </ul>
        </div>
      </BoardOnly>
      <p className="secondary">
        Día <span className="num">{formatNumber(mission.mission_day, 1)}</span> de{" "}
        <span className="num">{formatNumber(mission.duration_days)}</span> ·{" "}
        {gravity === null ? mission.gravity_display : <Mark pictogram={gravity}>{mission.gravity_display}</Mark>} ·
        intervenciones en seguimiento <span className="num">{formatNumber(open)}</span>, cerradas{" "}
        <span className="num">{formatNumber(closed)}</span>
      </p>
      {/* Lote «muestra» (2026-11-08, una pantalla por sección). Segunda ronda: la línea temporal
          medía 640 px y la mitad eran las frases del perfil, la conjunción y las efemérides. A la
          vista quedan las fases, la ruta, el medidor del día, las píldoras, la línea del día y una
          fila de píldoras con la marca de cada aviso (`MissionBoardWarnings`); la lista de eventos,
          la base de las fases, las frases enteras del perfil y las efemérides, la crónica y el
          formulario de declarar, tras un «Ver detalle» (antes eran cuatro a la vista; dentro siguen
          los dos del perfil y las efemérides, con sus notas y fuentes). La clásica no cambia:
          `BoardDetail` pinta allí los hijos en el mismo orden de siempre. */}
      <BoardOnly>
        <MissionBoardWarnings profile={mission.profile} coverage={mission.ephemeris_coverage} />
      </BoardOnly>
      <BoardDetail
        label={
          onDeclareEvent !== undefined && operator !== undefined
            ? "eventos, perfil, efemérides, crónica y declarar"
            : "eventos, perfil, efemérides y crónica"
        }
      >
        {mission.events.length > 0 && (
          <ul className="drivers">
            {mission.events.map((event) => (
              <li key={event.ledger_index}>
                <Mark pictogram={eventPictogram(event.kind)}>{EVENT_LABEL[event.kind]}</Mark>: {event.label} ·{" "}
                <span className="num">{met(event.start)}</span> a{" "}
                <span className="num">{met(event.end)}</span>{" "}
                <span className="secondary">(declarado por {event.declared_by})</span>
              </li>
            ))}
          </ul>
        )}
        <p className="secondary">{mission.phase_basis}</p>
        {/* El perfil declarado y lo que una fuente leida dice de el: texto del backend. */}
        {mission.profile != null && <MissionProfileView profile={mission.profile} />}
        {/* Que dias de la mision tienen efemerides en cache (§5.37.18): texto del backend. */}
        {mission.ephemeris_coverage != null && <EphemerisCoverageView coverage={mission.ephemeris_coverage} />}
        <Chronicle status={status} onMoment={onMoment} />
        {onDeclareEvent !== undefined && operator !== undefined && (
          <EventForm operator={operator} subject={status.subject} onDeclare={onDeclareEvent} />
        )}
      </BoardDetail>
    </section>
  );
}

/** `datetime-local` no lleva zona: se interpreta en UTC, la hora de mision. */
function utc(value: string): string {
  return new Date(value + ":00Z").toISOString();
}

/**
 * Una ubicacion se declara igual que una EVA y queda igual de firmada, pero dice ademas de
 * quien es y en que modulo. El modulo sale de la lista del backend y no viene elegido: es
 * una declaracion firmada y elegirla por inercia seria declarar algo que nadie ha mirado.
 */
function EventForm({
  operator,
  subject,
  onDeclare,
}: {
  operator: string;
  /** El tripulante de esta consola: a quien se refiere una ubicacion si no se elige otro. */
  subject: string;
  onDeclare: DeclareEvent;
}) {
  const [kind, setKind] = useState("eva");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [label, setLabel] = useState("");
  const [module, setModule] = useState("");
  const [about, setAbout] = useState(subject);
  const [places, setPlaces] = useState<HabitatModules | null>(null);
  const [shiftBasis, setShiftBasis] = useState<ShiftBasis | null>(null);
  // Aparte del error de la declaracion: que no llegue la base no es que la declaracion fallara.
  const [basisError, setBasisError] = useState<RequestOutcome | null>(null);
  const [crew, setCrew] = useState<string[]>([subject]);
  const [error, setError] = useState<RequestOutcome | null>(null);
  const who = operator.trim();
  const locating = kind === "location";
  const shifting = kind === "shift";

  // Que es un cambio de turno y en que se distingue de un bloque de trabajo: lo redacta el
  // backend, con su fuente leida. Solo se pide al elegir ese tipo.
  useEffect(() => {
    if (!shifting || shiftBasis !== null) return;
    let cancelled = false;
    api
      .missionShift()
      .then((payload) => {
        if (!cancelled) setShiftBasis(payload);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setBasisError(requestOutcome(cause));
      });
    return () => {
      cancelled = true;
    };
  }, [shifting, shiftBasis]);

  // La lista de modulos y la tripulacion solo hacen falta para una ubicacion: se piden entonces.
  useEffect(() => {
    if (!locating) return;
    let cancelled = false;
    api
      .habitatModules()
      .then((payload) => {
        if (!cancelled) setPlaces(payload);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(requestOutcome(cause));
      });
    api
      .crew()
      .then((overview) => {
        if (!cancelled) setCrew(overview.crew.map((member) => member.subject));
      })
      // Sin tripulacion evaluada queda el tripulante de esta consola, que es el de por defecto.
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [locating]);

  return (
    <Fold data-ui="mission-event-form" concept="declare" label="Declarar EVA, bloque de trabajo, cambio de turno o ubicación">
      <form
        className="inline-form"
        onSubmit={(event) => {
          event.preventDefault();
          setError(null);
          onDeclare(
            kind,
            utc(start),
            utc(end),
            label.trim(),
            who,
            locating ? { subject: about, module } : undefined,
          ).catch((cause: unknown) => setError(requestOutcome(cause)));
        }}
      >
        <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Tipo">
          <option value="eva">EVA</option>
          <option value="workload">Bloque de trabajo</option>
          <option value="shift">Cambio de turno o de horario de sueño</option>
          <option value="location">Ubicación</option>
        </select>
        {locating && (
          <>
            <select value={about} onChange={(e) => setAbout(e.target.value)} aria-label="Tripulante">
              {crew.map((member) => (
                <option key={member} value={member}>
                  {member}
                </option>
              ))}
            </select>
            <select value={module} onChange={(e) => setModule(e.target.value)} aria-label="Módulo">
              <option value="">módulo…</option>
              {(places?.modules ?? []).map((place) => (
                <option key={place.key} value={place.key} title={place.description}>
                  {place.display}
                </option>
              ))}
            </select>
          </>
        )}
        <FieldLabel concept="time">
          Inicio (UTC){" "}
          <input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} />
        </FieldLabel>
        <FieldLabel concept="time">
          Fin (UTC){" "}
          <input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} />
        </FieldLabel>
        <input
          value={label}
          maxLength={500}
          placeholder={locating ? "descripción (opcional)" : "descripción"}
          aria-label="Descripción"
          onChange={(e) => setLabel(e.target.value)}
        />
        <Command
          concept="declare"
          type="submit"
          disabled={
            who === "" ||
            start === "" ||
            end === "" ||
            (locating ? module === "" : label.trim() === "")
          }
        >
          Declarar
        </Command>
        {error !== null && (
          <>
            {" "}
            <MarkOf mark={error.mark}>{error.text}</MarkOf>
          </>
        )}
      </form>
      {/* La base de la lista la redacta el backend: es de diseno, no la de una nave. */}
      {locating && places !== null && <p className="secondary">{places.basis}</p>}
      {shifting && shiftBasis !== null && <ShiftBasisView basis={shiftBasis} />}
      {shifting && shiftBasis === null && basisError !== null && (
        <p className="secondary">
          <MarkOf mark={basisError.mark}>{basisError.text}</MarkOf>
        </p>
      )}
    </Fold>
  );
}

/** Que es un cambio de turno, en que se distingue de un bloque de trabajo y su fuente: del backend. */
export function ShiftBasisView({ basis }: { basis: ShiftBasis }) {
  return (
    <div className="secondary">
      <p>{basis.distinction}</p>
      <p>
        {basis.source_says}{" "}
        {basis.source.url !== null ? (
          <a href={basis.source.url} target="_blank" rel="noreferrer">
            {basis.source.title}
          </a>
        ) : (
          basis.source.title
        )}
      </p>
    </div>
  );
}
