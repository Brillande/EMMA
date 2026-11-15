import { Fragment, useState } from "react";

import { MISSING_MARK, UNAVAILABLE_MARK, scaleMark, type RequestOutcome, requestOutcome } from "../lib/marks";
import { BoardDetail } from "../components/BoardDetail";
import { Command } from "../components/Command";
import { FieldLabel } from "../components/FieldLabel";
import { Fold } from "../components/Fold";
import { Mark, MarkOf } from "../components/Mark";
import { Meter } from "../components/Meter";
import { ObservationTypeBadge } from "../components/ObservationTypeBadge";
import { PanelTitle } from "../components/PanelTitle";
import { Th } from "../components/Th";
import { EvidenceEntry } from "../evidence/EvidenceEntry";
import {
  type CrewStatus,
  type EvidenceItem,
  type LimitCell,
  type RadiationProjection,
  type RadiationReading,
  type RadiationScales as RadiationScalesData,
  type ShortTermLimits,
} from "../lib/api";
import { formatMet, formatNumber, formatSourceDate, missionElapsedSeconds } from "../lib/format";
import { tr } from "../lib/i18n";
import { uiPictogram } from "../lib/uiMarks";
import { MissionHistory } from "./MissionHistory";

/**
 * Radiacion en tres escalas (base de conocimiento §7): aguda con su tiempo hasta la accion, de
 * mision (inferida) y de carrera con la dosis previa que declara el perfil. Lo que falta se dice
 * en cian ("dato ausente", F.5-1) con su anillo; nada se supone cero. Textos y bases, del backend.
 *
 * Cada escala lleva su forma junto a su nombre (`icons/sets/radiation.ts`): rayos para la aguda,
 * trebol para la dosis de mision, barra con tope para la de carrera; y el refugio su casa. Son
 * tres dibujos distintos porque se deciden cosas distintas con cada escala (§5.11). El tipo y la
 * severidad del evento solar no se ensenan aqui, asi que tampoco tienen pictograma.
 *
 * Segunda pasada (§5.33.8): el titulo, el plegable, sus rotulos y el mando llevan el signo del
 * vocabulario comun (`lib/uiMarks.ts`), y la dosis de carrera, ademas de la cifra, el medidor
 * neutro del nucleo hasta el limite de carrera.
 *
 * Decimocuarta ronda (C7, §5.34.7): una cuarta fila, «Al fin de misión», con la dosis de misión
 * proyectada al fin configurado (PREDICHA, con el dibujo del día de misión porque es un horizonte
 * en días), su horquilla por tipo de radiación (INFERIDA, con la fuente de sus dos Q) y, si hay
 * dosis previa declarada, la carrera proyectada en el mismo medidor que la carrera. Debajo, plegada,
 * la Tabla 4.8-1 de NASA-STD-3001 Vol 1 en su unidad (mGy-Eq o mGy), sin convertir: las casillas
 * sin cifra van en gris con su círculo tachado y el texto de la norma que da el backend.
 *
 * Decimoquinta ronda (D19, §5.35.19): junto a la declaración del perfil, plegado, el historial
 * misión a misión (`MissionHistory.tsx`). No cambia ninguna fila de arriba: la carrera sigue
 * leyendo la dosis previa del perfil, y el historial solo dice si su suma casa con ella.
 *
 * Decimosexta ronda (E8, §5.36.8): lo leído junto a la radiación, que no decide nada. Bajo
 * «Aguda», a la vista, que a bordo de Orion el aviso lo da HERA y EMMA no lo lee, y plegado, con el
 * libro de fuente (la casa es solo el refugio montado durante un evento), lo que una fuente dice
 * del fin del refugio. Debajo de la tabla, plegada y con
 * la fecha de la nota en el rótulo, la fase del ciclo solar. Textos, alcances y lo buscado sin
 * encontrar, del backend; las frases, en inglés y con su ficha.
 *
 * Lote «muestra» (2026-11-08, una pantalla por sección): bajo la concha de la maqueta las bases de
 * cada escala, el aviso a bordo (E8: un párrafo que hacía la celda «Aguda» tres veces más alta que
 * las demás) y los cuatro pliegues de debajo van tras «Ver detalle» (`BoardDetail`); la cifra de
 * cada escala, su etiqueta, su medidor (también el de la carrera proyectada, que fuera de escala es
 * lo único que la dice) y las marcas de dato ausente siguen a la vista. La clásica no cambia:
 * `BoardDetail` pinta allí los hijos tal cual.
 */
export function RadiationScales({
  status,
  operator,
  onDeclareProfile,
}: {
  status: CrewStatus;
  operator: string;
  onDeclareProfile: (missions: number, doseMsv: number | null, by: string) => Promise<void>;
}) {
  const radiation = status.radiation;
  const met = (iso: string) => formatMet(missionElapsedSeconds(status.mission.start, new Date(iso)));
  const action = radiation.acute.time_to_action;
  // Un perfil recién declarado cambia el cotejo del historial: se vuelve a leer.
  const [profileVersion, setProfileVersion] = useState(0);
  return (
    <section data-ui="radiation-scales" className="panel" aria-label={tr("Radiación en tres escalas", "Radiation on three scales")}>
      <PanelTitle concept="radiation">{tr("Radiación: aguda, misión y carrera", "Radiation: acute, mission and career")}</PanelTitle>
      <dl className="kv">
        <dt>
          <Mark pictogram="burst">{tr("Aguda", "Acute")}</Mark>
        </dt>
        <dd>
          {action === null ? (
            <span className="secondary">{tr("sin evento solar activo", "no active solar event")}</span>
          ) : (
            <ShelterTimeline action={action} met={met} />
          )}
          {/* Con evento o sin él: quién avisa a bordo (y que EMMA no lo lee) se lee sin abrir
              nada; el fin del refugio, plegado y como fuente (E8, §5.36.8). */}
          {/* Lote «muestra» (2026-11-08): bajo la concha de la maqueta, el aviso a bordo (un párrafo
              largo que alargaba la celda «Aguda» más que las otras tres juntas) y el fin del refugio,
              tras «Ver detalle», con el nombre que da el backend. En la clásica, como siempre. */}
          {(radiation.acute.onboard_warning !== undefined || radiation.acute.shelter_exit !== undefined) && (
            <BoardDetail label={radiation.acute.onboard_warning?.label ?? radiation.acute.shelter_exit?.label ?? tr("fuentes", "sources")}>
              {radiation.acute.onboard_warning !== undefined && (
                <OnboardWarning reading={radiation.acute.onboard_warning} />
              )}
              {radiation.acute.shelter_exit !== undefined && (
                // El libro de lo que dice una fuente, no la casa: la casa es el refugio montado durante
                // un evento, y este pliegue sale también sin evento (revisión de E8).
                <Fold data-ui="radiation-shelter-exit" concept="source" label={radiation.acute.shelter_exit.label}>
                  <Reading reading={radiation.acute.shelter_exit} />
                </Fold>
              )}
            </BoardDetail>
          )}
        </dd>
        <dt>
          <Mark pictogram="trefoil">{tr("Esta misión", "This mission")}</Mark>
        </dt>
        <dd>
          {radiation.mission === null ? (
            <MarkOf mark={MISSING_MARK}>
              {tr("sin tasa de dosis registrada", "no dose rate recorded")}
            </MarkOf>
          ) : (
            <>
              <span className="num">{formatNumber(radiation.mission.value_msv, 2)}</span> mSv{" "}
              <ObservationTypeBadge type="inferred" />
              {/* Rótulos cortos (quinta ronda, 2026-11-09): en la celda de 200 px «base de la dosis
                  de misión» iba en tres renglones; distintos entre sí para el lector de pantalla. */}
              <BoardDetail label={tr("base de la misión", "mission basis")}>
                <p className="secondary">{radiation.mission.basis}</p>
              </BoardDetail>
            </>
          )}
        </dd>
        {/* Sin dosis de misión no hay nada que proyectar: lo dice ya la fila de arriba, en cian. */}
        {radiation.projection != null && (
          <>
            <dt>
              <Mark pictogram={uiPictogram("missionDay")}>{tr("Al fin de misión", "At end of mission")}</Mark>
            </dt>
            <dd>
              <Projection projection={radiation.projection} />
            </dd>
          </>
        )}
        <dt>
          <Mark pictogram="bar-capped">{tr("Carrera", "Career")}</Mark>
        </dt>
        <dd>
          {radiation.career.value_msv === null ? (
            <MarkOf mark={MISSING_MARK}>
              {radiation.career.basis}
            </MarkOf>
          ) : (
            <>
              {/* Fuera de escala la cifra la dice el medidor junto a su flecha: aquí iría dos veces. */}
              {!careerOutside(radiation.career.value_msv, radiation.career.limit_msv) && (
                <>
                  <span className="num">{formatNumber(radiation.career.value_msv, 1)}</span> {tr("de", "of")}{" "}
                  <span className="num">{formatNumber(radiation.career.limit_msv)}</span> mSv{" "}
                </>
              )}
              <span className="secondary">({radiation.career.limit_source})</span>{" "}
              <ObservationTypeBadge type="inferred" />
              <CareerMeter
                value={radiation.career.value_msv}
                limit={radiation.career.limit_msv}
                label={tr("Carrera: dosis sobre el límite de carrera", "Career: dose against the career limit")}
              />
              <BoardDetail label={tr("base de la carrera", "career basis")}>
                <p className="secondary">{radiation.career.basis}</p>
              </BoardDetail>
            </>
          )}
        </dd>
      </dl>
      {/* Tablero (lote «muestra», 2026-11-08): la tabla por órgano, el ciclo solar, la declaración
          del perfil y el historial eran cuatro pliegues seguidos bajo las escalas; van juntos tras
          un solo «Ver detalle». Las cifras de las escalas y sus marcas siguen a la vista. */}
      <BoardDetail label={tr("límites por órgano, ciclo solar e historial", "limits by organ, solar cycle and history")}>
        {radiation.short_term_limits !== undefined && <ShortTermTable limits={radiation.short_term_limits} />}
        {radiation.solar_cycle !== undefined && <SolarCycle reading={radiation.solar_cycle} />}
        <ProfileForm
          operator={operator}
          onDeclare={(missions, doseMsv, by) =>
            onDeclareProfile(missions, doseMsv, by).then(() => setProfileVersion((current) => current + 1))
          }
        />
        <MissionHistory subject={status.subject} operator={operator} refreshKey={String(profileVersion)} />
      </BoardDetail>
    </section>
  );
}

/**
 * El refugio con el procedimiento de Orion: detección, refugio montado y permanencia máxima, en
 * tiempo de misión, con la base y la fuente del backend. Lo comparte la tripulación ante un evento
 * solar (`CrewRadiation.tsx`, §5.38.8), que lo cuenta una vez para todos.
 */
export function ShelterTimeline({
  action,
  met,
}: {
  action: NonNullable<RadiationScalesData["acute"]["time_to_action"]>;
  met: (iso: string) => string;
}) {
  return (
    <>
      {tr("evento detectado en", "event detected at")} <span className="num">{met(action.detected_at)}</span> ·{" "}
      <Mark pictogram="house-door">{tr("refugio", "shelter")}</Mark> {tr("montado antes de", "set up before")}{" "}
      <span className="num">{met(action.shelter_ready_by)}</span> · {tr("permanencia hasta", "stay until")}{" "}
      <span className="num">{met(action.max_stay_until)}</span>
      <p className="secondary">
        {action.basis}.{" "}
        <a href={action.source.url} target="_blank" rel="noreferrer">
          {action.source.source}
        </a>
      </p>
    </>
  );
}

/**
 * La dosis de carrera sobre el límite que da el backend, en el medidor neutro del núcleo. Sin
 * banda: el backend no da una referencia dentro de la escala, y una inventada sería un umbral. Si
 * la dosis pasa del límite, la barra queda vacía y la flecha (que elige el medidor) va con la
 * cifra «x de 600 mSv», que entonces no se escribe también delante (`careerOutside`). Sin límite
 * positivo no hay escala que dibujar.
 */
export function CareerMeter({ value, limit, label }: { value: number; limit: number; label: string }) {
  if (!(limit > 0)) return null;
  return (
    <Meter
      value={value}
      max={limit}
      label={label}
      outOfRange={{ word: tr(`${formatNumber(value, 1)} de ${formatNumber(limit)} mSv`, `${formatNumber(value, 1)} of ${formatNumber(limit)} mSv`) }}
    />
  );
}

/** Si la dosis de carrera cae fuera de la escala de su medidor (y hay medidor que la diga). */
export function careerOutside(value: number, limit: number): boolean {
  return limit > 0 && scaleMark(value, 0, limit) !== null;
}

/**
 * La dosis de misión proyectada al fin configurado (PREDICHA), su horquilla por tipo de radiación
 * (INFERIDA) y la carrera proyectada. Cifras, bases y fuente, del backend. Con la misión ya
 * terminada no hay cifra: queda la base en secundario, que no es un dato ausente sino que no hay
 * tramo que proyectar. Sin dosis previa, la carrera proyectada tampoco va en cian: el dato que
 * falta es el de la fila «Carrera», que ya lo dice.
 */
function Projection({ projection }: { projection: RadiationProjection }) {
  if (projection.value_msv === null) {
    return <span className="secondary">{projection.basis}</span>;
  }
  const byType = projection.by_type;
  const career = projection.career;
  return (
    <>
      <span className="num">{formatNumber(projection.value_msv, 2)}</span> mSv{" "}
      <ObservationTypeBadge type={projection.observation_type} />
      {/* Tablero: la base y la horquilla por tipo, tras «Ver detalle»; la cifra proyectada, su
          etiqueta y la carrera proyectada con su medidor (fuera de escala, lo único que la dice), a
          la vista. */}
      <BoardDetail label={tr("base y horquilla", "basis and range")}>
      <p className="secondary">
        {projection.basis}; {projection.scope}.
      </p>
      {byType !== undefined && (
        <>
          <p>
            {tr("Por tipo de radiación:", "By radiation type:")} <span className="num">{formatNumber(byType.low_msv, 2)}</span> {tr("a", "to")}{" "}
            <span className="num">{formatNumber(byType.high_msv, 2)}</span> mSv{" "}
            <ObservationTypeBadge type={byType.observation_type} />
          </p>
          <p className="secondary">{byType.basis}.</p>
          {/* La ficha entera, con su salvedad (los Q se midieron en el Spacelab, no en personas),
              plegada: en la columna estrecha del panel ocupaba más que las tres escalas juntas, y
              lo esencial del alcance ya lo dice la base de arriba («SLS-1, 1991, órbita baja»). */}
          <Fold data-ui="radiation-quality-factors" concept="source" label={tr("Fuente de los factores de calidad", "Source of the quality factors")}>
            <div className="secondary">
              <EvidenceEntry item={byType.source} />
            </div>
          </Fold>
        </>
      )}
      {/* Sin dosis previa, la frase de por qué la carrera no se proyecta (tres renglones en la
          celda) va al final del mismo «Ver detalle» (quinta ronda, 2026-11-09): no es la marca del
          dato ausente, que sigue a la vista en cian en la celda «Carrera». Como último hijo, la
          clásica la pinta donde siempre, justo después de la horquilla. */}
      {career !== undefined && career.value_msv === null && <p className="secondary">{career.basis}</p>}
      </BoardDetail>
      {career !== undefined && career.value_msv !== null && (
          <>
            <p>
              {tr("Carrera proyectada:", "Projected career:")}{" "}
              {/* Fuera de escala la cifra la dice el medidor junto a su flecha, como en «Carrera». */}
              {!careerOutside(career.value_msv, career.limit_msv) && (
                <>
                  <span className="num">{formatNumber(career.value_msv, 1)}</span> {tr("de", "of")}{" "}
                  <span className="num">{formatNumber(career.limit_msv)}</span> mSv{" "}
                </>
              )}
              <span className="secondary">({career.limit_source})</span>{" "}
              <ObservationTypeBadge type={projection.observation_type} />
            </p>
            <CareerMeter
              value={career.value_msv}
              limit={career.limit_msv}
              label={tr("Carrera proyectada al fin de misión sobre el límite de carrera", "Projected career at end of mission against the career limit")}
            />
            <p className="secondary">{career.basis}</p>
          </>
      )}
    </>
  );
}

/**
 * La Tabla 4.8-1 de NASA-STD-3001 Vol 1, tal cual la da el backend: el órgano, los límites de 30
 * días, 1 año y carrera en la unidad de la norma, y su nota. No se compara con nada (EMMA no tiene
 * dosis por órgano) y por eso no lleva medidor ni color: solo el gris de la casilla sin cifra.
 */
function ShortTermTable({ limits }: { limits: ShortTermLimits }) {
  return (
    <Fold data-ui="radiation-short-term-limits" concept="limits" label={tr("Límites a corto plazo por órgano", "Short-term limits by organ")}>
      <p className="secondary">
        {limits.units}; {limits.scope}.
      </p>
      {/* En la columna estrecha del panel la tabla se desplaza, no se corta (`.limits-table`). La
          unidad va una vez por fila, junto al órgano: repetida en cada casilla no cabía. */}
      <div className="limits-table">
        <table className="ledger">
          <thead>
            <tr>
              <Th concept="body">{tr("Órgano (unidad)", "Organ (unit)")}</Th>
              <Th concept="limits">{tr("30 días", "30 days")}</Th>
              <Th concept="limits">{tr("1 año", "1 year")}</Th>
              <Th concept="limits">{tr("Carrera", "Career")}</Th>
            </tr>
          </thead>
          <tbody>
            {limits.rows.map((row) => (
              <tr key={row.organ}>
                <td>
                  {row.organ_display} ({row.unit})
                  {row.note !== null && <span className="secondary"> · {row.note}</span>}
                </td>
                <td>
                  <Cell cell={row.thirty_day} />
                </td>
                <td>
                  <Cell cell={row.one_year} />
                </td>
                <td>
                  <Cell cell={row.career} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="secondary">
        <EvidenceEntry item={limits.source} />
      </div>
    </Fold>
  );
}

/**
 * El aviso a bordo (E8): a la vista, el texto del backend, que dice que en Orion avisa HERA y que
 * EMMA no lo lee; plegadas, sus frases y fichas. Sin color ni marca de estado: no es un dato.
 */
function OnboardWarning({ reading }: { reading: RadiationReading }) {
  return (
    <>
      <p className="secondary">
        <strong>{reading.label}:</strong> {reading.text}
      </p>
      <Fold data-ui="radiation-onboard-warning" concept="sourceText" label={tr("Fuentes del aviso a bordo", "Sources of the onboard warning")}>
        <p className="secondary">{reading.scope}.</p>
        <ReadingSources reading={reading} />
      </Fold>
    </>
  );
}

/**
 * La fase del ciclo solar (E8): plegada, con la fecha de la nota en el rótulo, porque es una nota
 * fechada y no el estado de hoy. La proyección de arriba no la lee (lo dice su alcance).
 */
function SolarCycle({ reading }: { reading: RadiationReading }) {
  return (
    <Fold data-ui="solar-cycle"
      concept="source"
      label={
        <>
          {reading.label}
          {reading.as_of !== undefined && (
            <>
              {" "}
              ({tr("nota del", "note of")} <span className="num">{formatSourceDate(reading.as_of)}</span>)
            </>
          )}
        </>
      }
    >
      <Reading reading={reading} />
    </Fold>
  );
}

/** Texto y alcance del backend, y debajo sus fuentes. */
function Reading({ reading }: { reading: RadiationReading }) {
  return (
    <>
      <p className="secondary">{reading.text}</p>
      <p className="secondary">{reading.scope}.</p>
      <ReadingSources reading={reading} />
    </>
  );
}

/**
 * Cada ficha una vez (el backend las da sin repetir), con sus frases debajo en su idioma y el sitio
 * de cada una; el día de la lectura; y lo buscado sin encontrar, con su lupa. Una ficha citada tres
 * veces no se repite: en la columna estrecha del panel tres fichas iguales ocupaban más que las
 * tres escalas.
 */
function ReadingSources({ reading }: { reading: RadiationReading }) {
  // Los días de lectura de la entrada, el primero delante: una frase leída otro día (las gráficas
  // de NOAA, decimoctava ronda) suma el suyo al pie, no lo oculta tras el primero.
  const days = [
    ...new Set([reading.read_on, ...reading.quotes.map((item) => item.read_on ?? reading.read_on)]),
  ];
  return (
    <>
      {/* Sin listas anidadas: en la columna de 330 px dos sangrías dejaban la frase a cuatro
          palabras por renglón y partían las palabras (captura de E8). */}
      {reading.sources.map((source: EvidenceItem) => (
        <div key={source.id} className="secondary">
          <EvidenceEntry item={source} />
          {/* La misma frase puede citarse de dos sitios: la clave no puede ser solo la frase. */}
          {reading.quotes.filter((item) => item.ref === source.id).map((item, index) => (
            <p key={`${index}|${item.where}|${item.quote}`}>
              <q lang="en">{item.quote}</q> ({item.where}
              {/* Una frase leída otro día que la entrada lleva el suyo: el pie dice el primero. */}
              {item.read_on !== undefined && item.read_on !== reading.read_on && (
                <>
                  ; {tr("leída el", "read on")} <span className="num">{formatSourceDate(item.read_on)}</span>
                </>
              )}
              )
            </p>
          ))}
        </div>
      ))}
      <p className="secondary">
        {tr("Leído el", "Read on")}{" "}
        {days.map((day, index) => (
          <Fragment key={day}>
            {index > 0 && tr(" y el ", " and ")}
            <span className="num">{formatSourceDate(day)}</span>
          </Fragment>
        ))}
        .{" "}
        <Mark pictogram={uiPictogram("searchedNotFound")}>{tr("Buscado y no encontrado:", "Searched and not found:")}</Mark> {reading.not_found}
      </p>
    </>
  );
}

/** Una casilla: la cifra (su unidad va con el órgano), o en gris lo que la norma dice en su lugar. */
function Cell({ cell }: { cell: LimitCell }) {
  if (cell.value === null) {
    return <MarkOf mark={UNAVAILABLE_MARK}>{cell.absent}</MarkOf>;
  }
  return <span className="num">{formatNumber(cell.value)}</span>;
}

function ProfileForm({
  operator,
  onDeclare,
}: {
  operator: string;
  onDeclare: (missions: number, doseMsv: number | null, by: string) => Promise<void>;
}) {
  const [missions, setMissions] = useState("0");
  const [dose, setDose] = useState("");
  const [error, setError] = useState<RequestOutcome | null>(null);
  const who = operator.trim();
  return (
    <Fold data-ui="radiation-profile-form" concept="declare" label={tr("Declarar historial del tripulante", "Declare crew member history")}>
      <form
        className="inline-form"
        onSubmit={(event) => {
          event.preventDefault();
          setError(null);
          onDeclare(Number(missions), dose.trim() === "" ? null : Number(dose.replace(",", ".")), who)
            // El detalle del backend a secas; de otro fallo, lo que diga. La marca, la de lo que
            // fue (`requestOutcome`, §5.34.14).
            .catch((cause: unknown) => setError(requestOutcome(cause)));
        }}
      >
        <FieldLabel concept="previous">
          {tr("Misiones previas", "Prior missions")}{" "}
          <input type="number" min={0} max={20} value={missions} onChange={(e) => setMissions(e.target.value)} />
        </FieldLabel>
        <FieldLabel concept="radiation">
          {tr("Dosis de carrera previa (mSv, vacío si no se conoce)", "Prior career dose (mSv, blank if unknown)")}{" "}
          <input inputMode="decimal" value={dose} onChange={(e) => setDose(e.target.value)} />
        </FieldLabel>
        <Command concept="declare" type="submit" disabled={who === ""}>
          {tr("Declarar", "Declare")}
        </Command>
        {/* El rechazo del backend, tal cual: amarillo con triángulo, que es «hay que mirarlo»; la
            petición caída, con la cruz en rojo. */}
        {error !== null && (
          <MarkOf mark={error.mark}>{error.text}</MarkOf>
        )}
      </form>
    </Fold>
  );
}
