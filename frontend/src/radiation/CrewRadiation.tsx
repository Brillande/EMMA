import { useEffect, useState } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { useLook } from "../components/BoardOnly";
import { Mark, MarkOf } from "../components/Mark";
import { ObservationTypeBadge } from "../components/ObservationTypeBadge";
import { PanelTitle } from "../components/PanelTitle";
import { Th } from "../components/Th";
import { SolarEventFacts } from "../habitat/HabitatRadiation";
import { LocationLine } from "../habitat/LocationSource";
import { type CrewRadiation as View, type CrewRadiationMember, crewRadiationApi } from "../lib/api";
import { formatMet, formatNumber, missionElapsedSeconds } from "../lib/format";
import { tr } from "../lib/i18n";
import { MISSING_MARK } from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";
import { CareerMeter, ShelterTimeline, careerOutside } from "./RadiationScales";

/**
 * La tripulación ante un evento solar, de un vistazo (decimoctava ronda, U8, §5.38.8).
 *
 * Por qué existe: ante un evento de partículas solares la conversación de ideación pregunta
 * «¿Dónde está la tripulación? … ¿Cuál es la dosis actual de cada astronauta?», y para contestarlo
 * había que abrir el estado de cada tripulante (la dosis y el refugio, `RadiationScales`) y la
 * lista de la tripulación (la ubicación, sin dosis). Aquí van juntas: el evento solar que eligió
 * el estado, el procedimiento de refugio de su escala aguda y, una fila por tripulante, su
 * ubicación (declarada en la consola o estimada por las anclas de módulo, con su marca: `LocationLine`),
 * su dosis de esta misión y la de carrera con su rótulo de tipo.
 *
 * Solo pinta lo que da `GET /api/crew/radiation`: cifras y frases del backend, por `format.ts`.
 * Se muestra y no se evalúa: ningún color de aviso (la alerta de radiación es la del estado de
 * cada uno). Lo que falta —ubicación sin declarar, dosis sin lecturas, carrera sin dosis previa,
 * DONKI sin dato o caducado— va en cian con su anillo (dato ausente, F.5-1). Sin factores de
 * blindaje ni comparación entre módulos: la frase del backend lo dice. Con `until`, lo que Tierra
 * puede conocer. Si la ruta falla, el resto del panel del hábitat sigue valiendo y esto no se pinta.
 */
export function CrewRadiation({
  missionStart,
  refreshKey,
  until,
}: {
  missionStart: string;
  refreshKey: string;
  until?: Date | undefined;
}) {
  const [view, setView] = useState<View | null>(null);
  const untilKey = until?.toISOString() ?? "";

  useEffect(() => {
    let cancelled = false;
    crewRadiationApi
      .get(until)
      .then((body) => {
        if (!cancelled) setView(body);
      })
      .catch(() => {
        if (!cancelled) setView(null);
      });
    return () => {
      cancelled = true;
    };
    // `until` va por su texto: una fecha nueva con el mismo instante no debe repetir la carga.
  }, [refreshKey, untilKey]);

  if (view === null) return null;
  const met = (iso: string) => formatMet(missionElapsedSeconds(missionStart, new Date(iso)));
  return <CrewRadiationView view={view} met={met} />;
}

/** La vista ya cargada: separada para probarla sin red. */
export function CrewRadiationView({ view, met }: { view: View; met: (iso: string) => string }) {
  const solar = view.solar_event;
  const shelter = view.shelter;
  const board = useLook() === "reference";
  const basis = <p className="secondary">{view.basis}.</p>;
  return (
    // La clase solo da el marco en el tablero (`shell/mission.css`), como la radiación del hábitat.
    <div role="group" aria-label={view.display} className="crew-radiation">
      <PanelTitle as="h3" concept="radiation">
        {view.display}
      </PanelTitle>
      {!board && basis}
      <dl className="kv">
        <dt>
          <Mark pictogram="ridge-radiation">{solar.display}</Mark>
        </dt>
        <dd>
          {/* El mismo dibujo del evento que la radiación del hábitat, y el refugio que la escala
              aguda del estado: piezas compartidas, no copias. */}
          <SolarEventFacts solar={solar} />
        </dd>
        {/* Su propio término: sin evento, la frase de que no hay refugio que contar no se lee como
            parte del evento. */}
        <dt>
          <Mark pictogram="house-door">{tr("Refugio", "Shelter")}</Mark>
        </dt>
        <dd>
          {shelter === null ? (
            <span className="secondary">{view.shelter_missing_text}</span>
          ) : (
            <ShelterTimeline action={shelter} met={met} />
          )}
        </dd>
      </dl>
      <div className="limits-table">
        <table className="ledger">
          <thead>
            <tr>
              <Th concept="person">{tr("Tripulante", "Crew member")}</Th>
              <Th concept="habitat">{tr("Ubicación", "Location")}</Th>
              <Th pictogram="trefoil">{tr("Esta misión", "This mission")}</Th>
              <Th pictogram="bar-capped">{tr("Carrera", "Career")}</Th>
            </tr>
          </thead>
          <tbody>
            {view.crew.map((member) => (
              <MemberRow key={member.subject} member={member} met={met} reference={view.reference_time} />
            ))}
          </tbody>
        </table>
      </div>
      {/* Lote «muestra», segunda ronda (2026-11-08): bajo la concha de la maqueta, qué junta esta
          vista (dos renglones), la base de la ubicación y las dos notas, tras «Ver detalle»; el evento,
          el refugio y la tabla con cada cifra y lo que falta en cian, a la vista. */}
      <BoardDetail label={tr("qué junta, base de la ubicación y notas", "what it combines, location basis and notes")}>
        {board && basis}
        <p className="secondary">{view.location_basis}.</p>
        <p className="secondary">{view.note}</p>
        <p className="secondary">{view.shielding}</p>
      </BoardDetail>
    </div>
  );
}

function MemberRow({
  member,
  met,
  reference,
}: {
  member: CrewRadiationMember;
  met: (iso: string) => string;
  /** La referencia de la tripulación: desde ahí se cuenta la antigüedad de una ubicación estimada. */
  reference: string;
}) {
  const { location, mission, career } = member;
  return (
    <tr>
      <td>
        <Mark pictogram={uiPictogram("person")}>
          <strong>{member.subject}</strong>
        </Mark>
      </td>
      <td>
        {/* Declarada o estimada por las anclas, con su antigüedad frente a la referencia de la
            tripulación; sin ella, la marca de su estado con el texto del backend. */}
        <LocationLine
          location={location}
          state={member.location_state}
          missingText={member.location_missing_text}
          reference={reference}
          met={met}
        />
      </td>
      {career === null ? (
        // Sin estado analizable no hay ninguna de las dos dosis: lo que falta, una vez.
        <td colSpan={2}>
          <MarkOf mark={MISSING_MARK}>{member.state_missing_text}</MarkOf>
        </td>
      ) : (
        <>
          <td>
            {mission !== null ? (
              <>
                <span className="num">{formatNumber(mission.value_msv, 2)}</span> mSv{" "}
                <ObservationTypeBadge type={mission.observation_type} />
              </>
            ) : (
              <MarkOf mark={MISSING_MARK}>{member.mission_missing_text}</MarkOf>
            )}
          </td>
          <td>
            {career.value_msv !== null ? (
              <>
                {/* Fuera de escala la cifra la dice el medidor junto a su flecha, como en el estado. */}
                {!careerOutside(career.value_msv, career.limit_msv) && (
                  <>
                    <span className="num">{formatNumber(career.value_msv, 1)}</span> {tr("de", "of")}{" "}
                    <span className="num">{formatNumber(career.limit_msv)}</span> mSv{" "}
                  </>
                )}
                {career.observation_type !== undefined && <ObservationTypeBadge type={career.observation_type} />}
                <CareerMeter
                  value={career.value_msv}
                  limit={career.limit_msv}
                  label={tr(`Carrera de ${member.subject}: dosis sobre el límite de carrera`, `Career of ${member.subject}: dose against the career limit`)}
                />
                <span className="secondary">({career.limit_source})</span>
              </>
            ) : (
              <MarkOf mark={MISSING_MARK}>{career.basis}</MarkOf>
            )}
          </td>
        </>
      )}
    </tr>
  );
}
