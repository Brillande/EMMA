import { BoardDetail } from "../components/BoardDetail";
import { useLook } from "../components/BoardOnly";
import { Mark, MarkOf } from "../components/Mark";
import { ObservationTypeBadge } from "../components/ObservationTypeBadge";
import { PanelTitle } from "../components/PanelTitle";
import { StatTile } from "../components/StatTile";
import type { HabitatRadiation as Radiation } from "../lib/api";
import { displayUnit, formatNumber } from "../lib/format";
import { tr } from "../lib/i18n";
import { indicatorFamily } from "../lib/indicatorFamily";
import { MISSING_MARK, UNAVAILABLE_MARK } from "../lib/marks";
import { freshnessOf } from "../lib/staleness";
import { uiPictogram } from "../lib/uiMarks";

/**
 * La radiacion en el estado del habitat (especificacion §3, HabitatState «radiation»; base de
 * conocimiento §10, Habitat Twin), decision del usuario del 2026-10-26.
 *
 * Lote «muestra» (2026-11-08): bajo la concha de la maqueta las bases, la nota y el blindaje van
 * tras «Ver detalle»; las cifras, el evento y toda marca de dato ausente o no disponible, a la vista.
 * Segunda ronda (2026-11-08): la lista de dosímetros medía 650 px con una lectura en dos renglones por
 * tripulante. Bajo esa concha cada lectura es una ficha (el tripulante, la cifra con su unidad, su
 * rótulo de tipo y la hora de la lectura, para que una vieja no se lea como de ahora), y la lista con
 * de dónde sale, las dos bases y las notas, en un solo «Ver
 * detalle» al final. La clásica no cambia.
 *
 * Por que existe: la tasa de dosis solo se veia como lectura de cada tripulante y el evento solar
 * solo en el estado de cada uno; el panel del habitat, que es donde se mira lo que comparte la
 * tripulacion, no decia nada de radiacion. Aqui se ensena la ultima tasa de dosis de cada
 * dosimetro y el evento solar vigente, cada cifra con de donde sale (de quien es el dosimetro y
 * que fuente la envio; el evento de NASA DONKI con su fecha en UTC, que no es tiempo de mision).
 *
 * Se muestra y no se evalua: sin color ni forma de aviso (la alerta de radiacion es la de cada
 * tripulante, en su panel). El modulo sin declarar es un dato ausente (cian, anillo punteado),
 * como una ubicacion sin declarar; sin DONKI, o con su dato caducado, tambien. Toda frase es del
 * backend: aqui solo se elige el pictograma (el trebol de la dosis; el sol de la radiacion del
 * entorno, `ridge-radiation`, del nucleo, para el evento: los rayos de la escala aguda son del
 * area de radiacion y no se usan fuera de ella) y la marca de lo que falta.
 *
 * Lo que cada tripulante tiene de tasa de dosis y el estado no lee por su tipo (`set_aside`,
 * §5.39.11) va debajo de la lista, con su nombre delante como en ella y la frase del backend, con
 * la marca de «no disponible» (gris, circulo tachado, `UNAVAILABLE_MARK`): el dato existe y no ha
 * caducado (no es cian) y no hay nada que mirar en la persona (no es amarillo); es que el estado no
 * lo lee. Quien solo tiene tasa de dosis inferida no sale en la lista y aqui se dice por que.
 */
export function HabitatRadiation({
  radiation,
  met,
}: {
  radiation: Radiation;
  met: (iso: string) => string;
}) {
  const dose = radiation.dose_rate;
  const solar = radiation.solar_event;
  const board = useLook() === "reference";
  const list = (
    <ul>
      {dose.readings.map((item) => (
        <li key={item.subject}>
          <Mark pictogram={uiPictogram("person")}>
            <strong>{item.subject}</strong>
          </Mark>{" "}
          <span className="num">{formatNumber(item.value, item.decimals)}</span> {displayUnit(item.unit)}{" "}
          <ObservationTypeBadge type={item.observation_type} context={item.evidence_context} /> ·{" "}
          <Mark pictogram={uiPictogram("time")}>
            <span className="num">{met(item.effective)}</span>
          </Mark>{" "}
          <span className="secondary">{item.origin_text}</span>
        </li>
      ))}
    </ul>
  );
  const doseBasis = <p className="secondary">{dose.basis}</p>;
  const solarBasis = <p className="secondary">{solar.basis}</p>;
  const notes = (
    <>
      <p className="secondary">{radiation.note}</p>
      <p className="secondary">{radiation.shielding}</p>
    </>
  );
  return (
    // La clase solo sirve en el tablero (`shell/mission.css`): el marco del bloque, la columna de
    // claves y el ancho de las fichas de dosis. La clásica no la usa.
    <div className="habitat-radiation">
      <PanelTitle as="h3" concept="radiation">
        {radiation.display}
      </PanelTitle>
      <p className="secondary">
        <MarkOf mark={MISSING_MARK}>{radiation.module_text}</MarkOf>
      </p>
      <dl className="kv">
        <dt>
          <Mark pictogram={indicatorFamily(dose.key)}>{dose.display}</Mark>
        </dt>
        <dd>
          {dose.readings.length === 0 ? (
            <MarkOf mark={MISSING_MARK}>{dose.missing_text}</MarkOf>
          ) : board ? (
            <div className="board-stats" role="group" aria-label={dose.display}>
              {dose.readings.map((item) => (
                <StatTile
                  key={item.subject}
                  concept="person"
                  label={item.subject}
                  value={item.value}
                  decimals={item.decimals}
                  unit={displayUnit(item.unit)}
                >
                  <ObservationTypeBadge type={item.observation_type} context={item.evidence_context} />{" "}
                  <Mark pictogram={uiPictogram("time")}>
                    <span className="num">{met(item.effective)}</span>
                  </Mark>
                </StatTile>
              ))}
            </div>
          ) : (
            list
          )}
          {!board && <BoardDetail label={tr("base de la tasa de dosis", "basis of the dose rate")}>{doseBasis}</BoardDetail>}
          {dose.set_aside !== undefined && dose.set_aside.length > 0 && (
            <div data-dose-set-aside>
              {dose.set_aside_display !== undefined && <p className="secondary">{dose.set_aside_display}</p>}
              <ul>
                {dose.set_aside.map((item) => (
                  <li key={item.subject} data-dose-set-aside-shown={item.shown ? "yes" : "no"}>
                    <Mark pictogram={uiPictogram("person")}>
                      <strong>{item.subject}</strong>
                    </Mark>{" "}
                    <MarkOf mark={UNAVAILABLE_MARK}>{item.text}</MarkOf>
                  </li>
                ))}
              </ul>
              {dose.set_aside_rule !== undefined && dose.set_aside_rule !== null && (
                <p className="secondary">{dose.set_aside_rule}</p>
              )}
            </div>
          )}
        </dd>
        <dt>
          <Mark pictogram="ridge-radiation">{solar.display}</Mark>
        </dt>
        <dd>
          <SolarEventFacts solar={solar} />
          {!board && <BoardDetail label={tr("base del evento solar", "basis of the solar event")}>{solarBasis}</BoardDetail>}
        </dd>
      </dl>
      {board ? (
        <BoardDetail label={tr("lecturas de cada dosímetro, bases y notas", "readings from each dosimeter, bases and notes")}>
          {dose.readings.length > 0 && list}
          {doseBasis}
          {solarBasis}
          {notes}
        </BoardDetail>
      ) : (
        <BoardDetail label={tr("notas", "notes")}>{notes}</BoardDetail>
      )}
    </div>
  );
}

/**
 * El evento solar vigente tal como lo da el backend: su frase (en cian si DONKI no dio dato), su
 * ficha en DONKI y la fuente con su edad (en cian si está caducada). Lo comparte la tripulación
 * ante un evento solar (`radiation/CrewRadiation.tsx`, §5.38.8): un solo dibujo del mismo evento.
 */
export function SolarEventFacts({ solar }: { solar: Radiation["solar_event"] }) {
  const current = freshnessOf(solar.freshness) === "fresh";
  return (
    <>
      {solar.state === "unavailable" ? (
        <MarkOf mark={MISSING_MARK}>{solar.text}</MarkOf>
      ) : (
        <span>{solar.text}</span>
      )}
      {/* La fecha del evento ya va en la frase del backend, en UTC; aqui, su ficha en DONKI. */}
      {solar.event !== null && solar.event.link !== "" && (
        <>
          {" "}
          (
          <a href={solar.event.link} target="_blank" rel="noreferrer">
            {solar.event.event_id}
          </a>
          )
        </>
      )}
      {/* Sin evento vigente, el último de esos datos con su fecha real: no está vigente, y la
          frase lo dice (sin red, el de la instantánea fechada de DONKI). */}
      {solar.latest_recorded != null && (
        <p className="secondary" data-solar-latest>
          {solar.latest_recorded.text}
          {solar.latest_recorded.link !== "" && (
            <>
              {" "}
              (
              <a href={solar.latest_recorded.link} target="_blank" rel="noreferrer">
                {solar.latest_recorded.event_id}
              </a>
              )
            </>
          )}
        </p>
      )}
      {solar.data_age !== null && (
        <p className="secondary">
          {solar.source} ·{" "}
          {current ? (
            solar.data_age
          ) : (
            <MarkOf mark={MISSING_MARK}>
              {solar.data_age} ({solar.freshness.display})
            </MarkOf>
          )}
        </p>
      )}
    </>
  );
}
