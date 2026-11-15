import { useEffect, useState } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { BoardOnly, useLook } from "../components/BoardOnly";
import { DomainName } from "../components/DomainName";
import { FlowSteps } from "../components/FlowSteps";
import { Fold } from "../components/Fold";
import { LevelBadge } from "../components/LevelBadge";
import { Mark, MarkOf } from "../components/Mark";
import { Meter } from "../components/Meter";
import { ObservationTypeBadge } from "../components/ObservationTypeBadge";
import { PanelTitle } from "../components/PanelTitle";
import { StatTile } from "../components/StatTile";
import { LevelPill } from "../dashboard/HomeCharts";
import {
  type CrewHypothesis,
  type CrewOverview,
  type HabitatDisplayOnly,
  type HabitatExcursion,
  type HabitatModules,
  type HabitatParameter,
  type HabitatReading,
  type HabitatState,
  type PersonalLightExposure,
  api,
} from "../lib/api";
import {
  displayUnit,
  formatMet,
  formatNumber,
  formatSourceDate,
  missionElapsedSeconds,
} from "../lib/format";
import { LEVEL_ORDER } from "../lib/levels";
import { tr } from "../lib/i18n";
import { MISSING_MARK, type RequestOutcome, requestOutcome } from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";
import { CountermeasureFacts } from "../advisor/RecommendationCard";
import { EvidenceEntry } from "../evidence/EvidenceEntry";
import { CrewRadiation } from "../radiation/CrewRadiation";
import { CrewComparison } from "./CrewComparison";
import { HabitatRadiation } from "./HabitatRadiation";
import { HypothesisReview } from "./HypothesisReview";
import { LocationAnchors } from "./LocationAnchors";
import { LocationLine } from "./LocationSource";
import { SystemsStatus } from "./SystemsStatus";
import {
  decimalsFor,
  healthRange,
  limitLabels,
  limitMark,
  meterScale,
  referenceFigure,
} from "./flow";
import {
  CABIN_AIR_PICTOGRAM,
  FLOW_STEPS_PICTOGRAM,
  groupPictogram,
  hypothesisMark,
  modulePictogram,
  parameterPictogram,
  presenceMark,
} from "./pictograms";

/**
 * Tripulacion frente a habitat (especificacion del equipo §7, §10).
 *
 * Arriba, las hipotesis de causa que redacta el backend, siempre rotuladas "correlacion, no
 * causa". Debajo, la atmosfera de cabina con su limite normativo, y cada tripulante con su
 * nivel: si todos cambian a la vez y el CO2 esta fuera de limite, se ve de un vistazo. Al
 * final, el mismo indicador en cada tripulante sobre el mismo eje (`CrewComparison`).
 *
 * Colores de la tabla F.5-1: fuera del limite normativo es precaucion (amarillo, triangulo);
 * fuera solo de la zona de confort es aviso (azul, rombo). Nunca solo color (F.5.10 e). Con
 * `until`, lo que Tierra puede conocer.
 *
 * Cada medida va bajo el modulo donde se tomo y cada tripulante con el modulo que alguien
 * declaro para el (especificacion §3, "module/location"). Una ubicacion sin declarar es un
 * dato ausente (cian, anillo punteado), no un "no disponible". Por que una hipotesis baja en el
 * orden lo redacta el backend; aqui solo se listan los nombres.
 *
 * Cada hipotesis ensena los siete pasos del flujo (§7) con su estado: nombre, estado y frase
 * los da el backend; aqui solo se elige pictograma y color (`flow.ts`). La luz de cabina se
 * muestra con la frase que da el backend (la norma no fija un limite general) y sin ningun
 * aviso: no se evalua. El agua potable y la microbiologia del aire y las superficies, igual,
 * cada una en su bloque (`HabitatSamples`) y no bajo «Atmosfera de cabina».
 *
 * Cada nombre del backend —parametro, modulo, clase de hipotesis, donde estaba cada
 * tripulante— lleva al lado su pictograma (`pictograms.ts`), siempre con la palabra y sin color
 * propio: nombrar no es avisar. Titulos, plegables, mandos y rotulos llevan el signo de lo que son
 * (`lib/uiMarks.ts`, §5.33.4), y cada fila de atmosfera, si su limite lo permite sin inventar una
 * escala, un medidor neutro con la banda de ese limite (`CabinMeter`).
 *
 * El estado de los sistemas del habitat (`SystemsStatus`) es lo que declaro una persona, no
 * telemetria: va en su propio bloque, con ese rotulo, y no cambia nada de lo de arriba.
 *
 * La radiacion (`HabitatRadiation`, 2026-10-26): la ultima tasa de dosis de cada dosimetro y el
 * evento solar vigente, con de donde sale cada cifra, el modulo sin declarar y sin factores de
 * blindaje. Se muestra y no se evalua.
 *
 * Tablero (decision del usuario, 2026-11-07): bajo la concha de la maqueta el panel abre con lo que
 * se lee de un vistazo (`HabitatBoard`): las pildoras de cuantas hipotesis propone el sistema (con
 * su magenta), cuantas veces se salio del limite normativo en la ventana (la forma de esa clase,
 * sin su color: la vigente la pinta su baldosa) y cuantos tripulantes hay en cada nivel (`LevelPill`,
 * solo cifras y niveles: nunca quien); y las ultimas lecturas de cabina como baldosas, una por
 * parametro y modulo en el orden de la tabla, con su unidad y, si la fila de abajo lleva marca (el
 * limite normativo vigente, o el aviso de confort o de rango objetivo), la misma marca y palabra.
 * Son las cifras que la tabla de atmosfera ya da, en otra forma; nada nuevo, y ninguna marca de
 * caducado porque el backend no da la frescura de una lectura de cabina. La clasica no monta nada
 * de esto (`BoardOnly`).
 *
 * Lote «muestra» (2026-11-08, una pantalla por sección): el panel medía casi 6000 px. Ahora, bajo la
 * concha de la maqueta, quedan a la vista las pildoras, las baldosas (tambien la «sin dato» de un
 * parametro sin lectura, para que el hueco de la tabla siga viendose), cada hipotesis con su marca,
 * a quien afecta, donde y su revision, la tripulacion con su nivel, la radiacion con sus cifras y
 * marcas, y lo que falta en agua y microbiologia y el recuento por estado de los sistemas. Tras «Ver
 * detalle» (`BoardDetail`): lo que se sabe de cada hipotesis y sus pasos, la tabla de atmosfera, las
 * filas de agua y microbiologia, la lista de sistemas con su formulario y las graficas de la
 * comparacion. La clasica no cambia.
 *
 * Segunda ronda (2026-11-08): el panel seguia midiendo 2300 px. Cada hipotesis junta sus tres
 * detalles en uno tras la revision (`HypothesisCard`), las lecturas de dosis son fichas
 * (`HabitatRadiation`) y, con sitio, la hipotesis va junto a la atmosfera y la tripulacion, y los
 * sistemas junto a la comparacion (`shell/mission.css`, sin cambiar el orden del DOM).
 *
 * Cuarta ronda (2026-11-08, «todavia se puede asemejar mas»): el panel va a 9 columnas junto a las
 * preguntas de los gemelos y por dentro en una rejilla de 12 (`shell/mission.css`). Bajo la concha de
 * la maqueta, las comprobaciones de cada hipotesis van a su «Ver detalle»; lo que se supone de donde
 * esta cada tripulante, bajo la lista de la tripulacion. La clasica no cambia.
 */
export function HabitatPanel({
  missionStart,
  refreshKey,
  until,
  onboardUntil,
  operator,
}: {
  missionStart: string;
  /** Cambia cuando cambia el estado: vuelve a pedir el habitat. */
  refreshKey: string;
  until?: Date;
  /** Solo en Tierra: por donde van a bordo, para marcar en las series lo que esta en transito. */
  onboardUntil?: Date;
  /** Solo a bordo: quien confirma o descarta una hipotesis. En Tierra, lectura. */
  operator?: string;
}) {
  const [reviewed, setReviewed] = useState(0);
  const [habitat, setHabitat] = useState<HabitatState | null>(null);
  const [parameters, setParameters] = useState<HabitatParameter[]>([]);
  const [displayOnly, setDisplayOnly] = useState<HabitatDisplayOnly[]>([]);
  const [modules, setModules] = useState<HabitatModules | null>(null);
  const [crew, setCrew] = useState<CrewOverview | null>(null);
  const [error, setError] = useState<RequestOutcome | null>(null);
  const board = useLook() === "reference";
  const untilKey = until?.toISOString() ?? "";

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.habitat(until),
      api.habitatParameters(),
      api.crew(until).catch(() => null),
      // Sin la lista, cada modulo se muestra con su clave: el dato sigue viendose.
      api.habitatModules().catch(() => null),
    ])
      .then(([state, catalog, overview, declared]) => {
        if (cancelled) return;
        setHabitat(state);
        setParameters(catalog.parameters);
        setDisplayOnly(catalog.display_only ?? []);
        setCrew(overview);
        setModules(declared);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(requestOutcome(reason));
      });
    return () => {
      cancelled = true;
    };
    // `until` va por su texto: una fecha nueva con el mismo instante no debe repetir la carga.
  }, [refreshKey, untilKey, reviewed]);

  if (error !== null) {
    return (
      <p className="panel error">
        <MarkOf mark={error.mark}>{tr(`No se pudo cargar el hábitat: ${error.text}`, `Could not load the habitat: ${error.text}`)}</MarkOf>
      </p>
    );
  }
  if (habitat === null) return null;
  const met = (iso: string) => formatMet(missionElapsedSeconds(missionStart, new Date(iso)));
  const moduleName = (key: string) =>
    modules?.modules.find((item) => item.key === key)?.display ?? key;
  // Los modulos con medidas, en el orden de la lista declarada; los que no esten en ella
  // (lecturas firmadas antes de que hubiera lista) van detras, con su clave.
  const listed = (modules?.modules ?? []).map((item) => item.key);
  const inListOrder = (keys: Iterable<string>) =>
    [...new Set(keys)].sort(
      (a, b) =>
        (listed.includes(a) ? listed.indexOf(a) : listed.length) -
          (listed.includes(b) ? listed.indexOf(b) : listed.length) || a.localeCompare(b),
    );
  // La atmosfera de cabina es lo evaluado y lo que el backend agrupa con ello (la luz); el agua
  // y la microbiologia van en su bloque (`HabitatSamples`) y no cuentan como telemetria de cabina.
  const cabinShown = displayOnly.filter((spec) => groupOf(spec) === CABIN_GROUP);
  const samples = displayOnly.filter((spec) => groupOf(spec) !== CABIN_GROUP);
  const sampleKeys = new Set(samples.map((spec) => spec.key));
  const cabinLatest = habitat.latest.filter((item) => !sampleKeys.has(item.parameter));
  const measured = inListOrder(cabinLatest.map((item) => item.module));
  const healthExcursions = habitat.excursions.filter((item) => item.kind === "health");
  // Lo que se supone de dónde está cada tripulante (cuarta ronda del lote «muestra», 2026-11-08):
  // en la clásica, bajo las hipótesis que lo usan; en el tablero, bajo la lista de la tripulación,
  // junto a sus «ubicación sin declarar», donde el bloque de la derecha tiene sitio y la tarjeta de la
  // hipótesis no crece. Se dice solo cuando hay hipótesis, como antes.
  const assumption =
    crew !== null && crew.correlation.hypotheses.length > 0 ? (
      <p className="secondary">{crew.correlation.assumption}</p>
    ) : null;

  return (
    <section data-ui="habitat" className="panel" aria-label={tr("Tripulación y hábitat", "Crew and habitat")}>
      <PanelTitle concept="habitat">{tr("Tripulación y hábitat", "Crew and habitat")}</PanelTitle>
      <BoardOnly>
        <HabitatBoard
          habitat={habitat}
          crew={crew}
          specs={[...parameters, ...cabinShown]}
          cabinLatest={cabinLatest}
          measured={measured}
          moduleName={moduleName}
        />
      </BoardOnly>
      {crew !== null && crew.correlation.hypotheses.length > 0 && (
        <div className="hypotheses">
          {crew.correlation.hypotheses.map((item) => (
            <HypothesisCard
              key={hypothesisKey(item)}
              item={item}
              moduleName={moduleName}
              operator={operator}
              onReviewed={() => setReviewed((count) => count + 1)}
            />
          ))}
          {!board && assumption}
        </div>
      )}

      <div className="grid-2">
        <div>
          <PanelTitle as="h3" pictogram={CABIN_AIR_PICTOGRAM}>
            {tr("Atmósfera de cabina", "Cabin atmosphere")}{" "}
            {cabinLatest[0] !== undefined && (
              <ObservationTypeBadge type="measured" context={cabinLatest[0].evidence_context} />
            )}
          </PanelTitle>
          {cabinLatest.length === 0 && (
            <p>
              <MarkOf mark={MISSING_MARK}>{tr("Sin telemetría de cabina.", "No cabin telemetry.")}</MarkOf>
            </p>
          )}
          {/* Tablero (lote «muestra», 2026-11-08): las filas con sus límites y lo que dice la norma, la
              última lectura y las salidas del límite ya cerradas, tras «Ver detalle»; cada cifra con
              su «fuera de …» o su «sin dato» ya va en las baldosas de arriba, y la cuenta de salidas
              en su píldora. */}
          {(cabinLatest.length > 0 || habitat.reference_time !== null || healthExcursions.length > 0) && (
            <BoardDetail label={tr("la tabla por módulo, sus límites y las salidas", "the table by module, its limits and the excursions")}>
            {cabinLatest.length > 0 && measured.map((module) => (
              <div key={module}>
                <ModuleLine module={module} moduleName={moduleName} />
                <dl className="kv">
                  {parameters.map((spec) => {
                    const here = (item: { module: string; parameter: string }) =>
                      item.module === module && item.parameter === spec.key;
                    const reading = habitat.latest.find(here);
                    const active = habitat.active.find(here);
                    // Aviso: zona de confort o rango objetivo, los dos sin ser limite normativo.
                    const comfort = habitat.excursions.find(
                      (item) =>
                        here(item) &&
                        item.kind !== "health" &&
                        reading !== undefined &&
                        item.end === reading.effective,
                    );
                    return (
                      <HabitatRow
                        key={spec.key}
                        spec={spec}
                        value={reading?.value ?? null}
                        active={active ?? null}
                        comfort={comfort ?? null}
                      />
                    );
                  })}
                  {cabinShown.map((spec) => (
                    <DisplayOnlyRow
                      key={spec.key}
                      spec={spec}
                      value={
                        habitat.latest.find(
                          (item) => item.module === module && item.parameter === spec.key,
                        )?.value ?? null
                      }
                    />
                  ))}
                </dl>
              </div>
            ))}
          {habitat.reference_time !== null && (
            <p className="secondary">
              <Mark pictogram={uiPictogram("time")}>{tr("Última lectura", "Latest reading")}</Mark>{" "}
              <span className="num">{met(habitat.reference_time)}</span> · {tr("límites de NASA-STD-3001 Vol 2", "limits from NASA-STD-3001 Vol 2")}
              {parameters[0] !== undefined && (
                <>
                  {" "}
                  (
                  <a href={parameters[0].source.url} target="_blank" rel="noreferrer">
                    OCHMO-TB-002
                  </a>
                  )
                </>
              )}
            </p>
          )}
          {healthExcursions.length > 0 && (
            <ul className="secondary">
              {healthExcursions.map((item) => (
                <li key={`${item.module}:${item.parameter}:${item.requirement}:${item.start}`}>
                  <Mark pictogram={parameterPictogram(item.parameter)}>{item.display}</Mark> {tr("en", "in")}{" "}
                  <Mark pictogram={modulePictogram(item.module)}>{moduleName(item.module)}</Mark>{" "}
                  {/* La forma de la clase del limite, sin su color: una excursion ya cerrada no
                      pide atencion; la vigente la pinta la tabla de arriba. */}
                  <Mark pictogram={limitMark(item.kind).pictogram}>{tr(`fuera de ${item.requirement}`, `outside ${item.requirement}`)}</Mark>{" "}
                  {tr(`de ${met(item.start)} a ${met(item.end)}; peor valor`, `from ${met(item.start)} to ${met(item.end)}; worst value`)}{" "}
                  <span className="num">{formatNumber(item.worst, 1)}</span>{" "}
                  {displayUnit(item.unit)}
                </li>
              ))}
            </ul>
          )}
            </BoardDetail>
          )}
        </div>

        {crew !== null && (
          <div>
            <PanelTitle as="h3" concept="person">
              {tr("Tripulación", "Crew")}
            </PanelTitle>
            <ul className="crew-list">
              {crew.crew.map((member) => (
                <li key={member.subject}>
                  <Mark pictogram={uiPictogram("person")}>
                    <strong>{member.subject}</strong>
                  </Mark>{" "}
                  <LevelBadge level={member.overall_level} />
                  {Object.keys(member.domains).length > 0 && (
                    <span className="secondary">
                      {" "}
                      ·{" "}
                      {Object.keys(member.domains).map((domain, index) => (
                        <span key={domain}>
                          {index > 0 && ", "}
                          <DomainName domain={domain} />
                        </span>
                      ))}
                    </span>
                  )}{" "}
                  {/* Declarada o estimada por las anclas, con su marca (`LocationLine`); sin ella, la
                      marca de su estado con el texto del backend. Solo un backend anterior, que no da
                      ni el estado ni el texto, deja el rótulo de siempre (con su cian de siempre). */}
                  <span className={member.location != null ? "secondary" : undefined}>
                    {member.location != null && <>· {tr("ubicación:", "location:")} </>}
                    <LocationLine
                      location={member.location}
                      state={member.location_state}
                      missingText={
                        member.location_missing_text ??
                        (member.location_state === undefined ? tr("ubicación sin declarar", "location not declared") : null)
                      }
                      reference={member.reference_time}
                      met={met}
                    />
                  </span>
                </li>
              ))}
            </ul>
            {board && assumption}
            {/* Dónde está instalada cada ancla de módulo (2026-11-10): es lo que deja estimar la
                ubicación de arriba cuando nadie la declara. A bordo, se declara aquí. */}
            <LocationAnchors
              missionStart={missionStart}
              refreshKey={refreshKey}
              operator={operator}
              referenceTime={habitat.reference_time}
              modules={modules}
              onDeclared={() => setReviewed((count) => count + 1)}
              until={until}
            />
          </div>
        )}
      </div>

      {/* La radiacion del habitat (2026-10-26): se muestra y no se evalua (`HabitatRadiation`). */}
      <HabitatRadiation radiation={habitat.radiation} met={met} />

      {/* Ante un evento solar, la tripulacion de un vistazo (§5.38.8): ubicacion y dosis de cada
          uno con el evento y el refugio. Pide su propia ruta; si falla, no se pinta. */}
      <CrewRadiation missionStart={missionStart} refreshKey={refreshKey} until={until} />

      {samples.length > 0 && (
        <HabitatSamples
          specs={samples}
          latest={habitat.latest}
          moduleName={moduleName}
          inListOrder={inListOrder}
          met={met}
        />
      )}

      <SystemsStatus
        missionStart={missionStart}
        refreshKey={refreshKey}
        until={until}
        operator={operator}
        referenceTime={habitat.reference_time}
        modules={modules}
      />

      {crew !== null && (
        <CrewComparison
          missionStart={missionStart}
          crew={crew}
          parameters={parameters}
          refreshKey={refreshKey}
          until={until}
          onboardUntil={onboardUntil}
        />
      )}
    </section>
  );
}

/**
 * Lo que el panel enseña de un vistazo en el tablero (ver la cabecera del fichero). Exportado solo
 * para pintarlo a HTML estatico en las pruebas. Sin nada que contar (sin tripulacion evaluada, sin
 * hipotesis, sin excursiones y sin lecturas) no pinta nada.
 */
export function HabitatBoard({
  habitat,
  crew,
  specs,
  cabinLatest,
  measured,
  moduleName,
}: {
  habitat: Pick<HabitatState, "active" | "excursions">;
  crew: CrewOverview | null;
  /** Los parametros de cabina con nombre y unidad, en el orden del catalogo: los evaluados y los que solo se muestran. */
  specs: readonly Pick<HabitatParameter, "key" | "display" | "unit">[];
  cabinLatest: readonly HabitatReading[];
  /** Los modulos con lecturas, en el orden de la lista declarada: con mas de uno, cada baldosa dice el suyo. */
  measured: readonly string[];
  moduleName: (key: string) => string;
}) {
  // Solo los niveles del vocabulario (`LEVEL_ORDER`): uno desconocido ya es un fallo en toda la
  // consola (`levelStyle` lanza y la insignia de la lista de abajo no se pinta), no algo que contar.
  const byLevel = LEVEL_ORDER.map((level) => ({
    level,
    count: crew === null ? 0 : crew.crew.filter((member) => member.overall_level === level).length,
  })).filter((entry) => entry.count > 0);
  const hypotheses = crew?.correlation.hypotheses.length ?? 0;
  // Las salidas del limite normativo en la ventana, vigentes o ya cerradas: la misma lista que el
  // panel da debajo de la tabla. Que una siga vigente lo dice su baldosa, no esta pildora.
  const healthCount = habitat.excursions.filter((item) => item.kind === "health").length;
  // En el orden de la tabla de abajo: modulo a modulo, y dentro el orden del catalogo. Una lectura
  // de un parametro sin ficha no tiene nombre ni unidad de lectura: no se inventan.
  // Un parametro con ficha y sin lectura en un modulo medido lleva su baldosa «sin dato» (cian, anillo
  // punteado), como su fila de la tabla: con la tabla tras «Ver detalle» (lote «muestra», 2026-11-08)
  // el hueco tiene que seguir viendose.
  const tiles = measured.flatMap((module) =>
    specs.map((spec) => ({
      module,
      spec,
      reading: cabinLatest.find((item) => item.module === module && item.parameter === spec.key) ?? null,
    })),
  );
  const pills = hypotheses > 0 || healthCount > 0 || byLevel.length > 0;
  if (!pills && tiles.length === 0) return null;
  return (
    <>
      {pills && (
        <div className="board-tally" role="group" aria-label={tr("Tripulación y hábitat de un vistazo", "Crew and habitat at a glance")}>
          {hypotheses > 0 && (
            <span className="ref-pill board-pill">
              <span className="source-tag c-magenta">{tr("Hipótesis del sistema", "System hypotheses")}</span>{" "}
              <span className="num">{formatNumber(hypotheses)}</span>
            </span>
          )}
          {healthCount > 0 && (
            <span className="ref-pill board-pill">
              <Mark pictogram={limitMark("health").pictogram}>{tr("salidas del límite en la ventana", "limit excursions in the window")}</Mark>{" "}
              <span className="num">{formatNumber(healthCount)}</span>
            </span>
          )}
          {byLevel.map((entry) => (
            <LevelPill key={entry.level} level={entry.level} count={entry.count} />
          ))}
        </div>
      )}
      {tiles.length > 0 && (
        <div className="board-stats">
          {tiles.map(({ module, reading, spec }) => {
            const label =
              measured.length > 1 ? (
                <>
                  {spec.display} <span className="secondary">· {moduleName(module)}</span>
                </>
              ) : (
                spec.display
              );
            if (reading === null) {
              return (
                <StatTile
                  key={`${module}:${spec.key}`}
                  pictogram={parameterPictogram(spec.key)}
                  label={label}
                  value={null}
                  status={{ mark: MISSING_MARK, word: tr("sin dato", "no data") }}
                />
              );
            }
            const here = (item: { module: string; parameter: string }) =>
              item.module === reading.module && item.parameter === reading.parameter;
            const active = habitat.active.find(here) ?? null;
            // Como la fila de la tabla (`HabitatRow`): el limite normativo vigente o, si no, el aviso
            // de confort o de rango objetivo que acaba en esta lectura, con la misma marca y palabra.
            const comfort =
              active === null
                ? (habitat.excursions.find(
                    (item) => here(item) && item.kind !== "health" && item.end === reading.effective,
                  ) ?? null)
                : null;
            const status =
              active !== null
                ? { mark: limitMark(active.kind), word: tr(`fuera de ${active.requirement}`, `outside ${active.requirement}`) }
                : comfort !== null
                  ? {
                      mark: limitMark(comfort.kind),
                      word:
                        comfort.kind === "target"
                          ? tr(`fuera de ${comfort.requirement}`, `outside ${comfort.requirement}`)
                          : tr(`fuera de la zona de confort ${comfort.requirement}`, `outside the comfort zone ${comfort.requirement}`),
                    }
                  : null;
            return (
              <StatTile
                key={`${reading.module}:${reading.parameter}`}
                pictogram={parameterPictogram(reading.parameter)}
                label={label}
                value={reading.value}
                decimals={decimalsFor(reading.value)}
                unit={displayUnit(spec.unit)}
                {...(status === null ? {} : { status })}
              />
            );
          })}
        </div>
      )}
    </>
  );
}

/**
 * Una hipótesis del sistema en su tarjeta: el rótulo magenta, el título con su marca, por qué baja
 * en el orden, a quién afecta, dónde, qué comprobar y la revisión con sus mandos.
 *
 * Segunda ronda del lote «muestra» (2026-11-08): la tarjeta medía 720 px con tres mandos de detalle
 * repartidos (lo que se sabe, contramedidas y flujo, evidencia). Bajo la concha de la maqueta los tres
 * van en un solo «Ver detalle» al final, tras la revisión; la marca, a quién afecta, dónde, las
 * comprobaciones y los mandos de revisión, a la vista. El pliegue de la evidencia conserva su
 * `data-ui`: el asistente abre el detalle que lo guarda. La clásica conserva su orden.
 *
 * Cuarta ronda (2026-11-08, «todavía se puede asemejar más»): la lista de comprobaciones (tres
 * frases, 110 px) también va en ese detalle, la primera; a la vista quedan la marca, a quién afecta,
 * dónde y los mandos de revisión.
 */
function HypothesisCard({
  item,
  moduleName,
  operator,
  onReviewed,
}: {
  item: CrewHypothesis;
  moduleName: (key: string) => string;
  operator: string | undefined;
  onReviewed: () => void;
}) {
  const board = useLook() === "reference";
  const sources = item.what_is_known_sources ?? [];
  const countermeasures = item.countermeasures ?? [];
  const flow = item.flow ?? [];
  const hasKnowledge =
    item.what_is_known !== null || item.what_is_known_basis != null || sources.length > 0 || item.knowledge_note != null;
  const knowledge = (
    <>
      {item.what_is_known !== null && <p>{item.what_is_known}</p>}
      {item.what_is_known_basis != null && <p className="secondary">{item.what_is_known_basis}</p>}
      {sources.length > 0 && (
        <Fold data-ui="habitat-source-text" concept="sourceText" label={tr(`Texto de la fuente (${formatNumber(sources.length)})`, `Source text (${formatNumber(sources.length)})`)}>
          <ul>
            {sources.map((source) => (
              <li key={`${source.locator}|${source.quote}`}>
                <span lang="en">«{source.quote}»</span>{" "}
                <span className="secondary">
                  {source.requirement} · {source.locator} · {tr("lectura del documento:", "document read on:")} {formatSourceDate(source.read_on)}
                </span>
              </li>
            ))}
          </ul>
        </Fold>
      )}
      {item.knowledge_note != null && <p className="secondary">{item.knowledge_note}</p>}
    </>
  );
  const measures = (
    <>
      {countermeasures.length > 0 && (
        <Fold
          data-ui="habitat-countermeasures"
          concept="environmentalCountermeasures"
          label={tr(`Contramedidas ambientales (${formatNumber(countermeasures.length)})`, `Environmental countermeasures (${formatNumber(countermeasures.length)})`)}
        >
          {countermeasures.map((measure) => (
            <div key={measure.id}>
              <p>{measure.action}</p>
              <CountermeasureFacts measure={measure} />
            </div>
          ))}
        </Fold>
      )}
      {flow.length > 0 && (
        <>
          <p className="secondary">
            <Mark pictogram={FLOW_STEPS_PICTOGRAM}>{tr("Pasos del flujo:", "Flow steps:")}</Mark>
          </p>
          <FlowSteps steps={item.flow ?? []} />
        </>
      )}
    </>
  );
  const checks = item.checks.length > 0 && (
    <>
      {/* «Qué comprobar», como en el detalle de una alerta: la lupa (§5.33.12). */}
      <p className="secondary">
        <Mark pictogram={uiPictogram("followUp")}>{tr("Comprobaciones:", "Checks:")}</Mark>
      </p>
      <ul>
        {item.checks.map((check) => (
          <li key={check}>{check}</li>
        ))}
      </ul>
    </>
  );
  const evidence = item.evidence.length > 0 && (
    <Fold data-ui="habitat-evidence" concept="evidence" label={tr(`Evidencia (${formatNumber(item.evidence.length)})`, `Evidence (${formatNumber(item.evidence.length)})`)}>
      <ul className="evidence">
        {item.evidence.map((entry) => (
          <li key={entry.id}>
            <EvidenceEntry item={entry} />
          </li>
        ))}
      </ul>
    </Fold>
  );
  return (
    <article className="hypothesis">
      <span className="source-tag c-magenta">{tr("Hipótesis del sistema", "System hypothesis")} · {item.label}</span>
      <p>
        <MarkOf mark={hypothesisMark(item)}>
          <strong>{item.title}</strong>
        </MarkOf>
      </p>
      {item.likelihood_reason != null && <p>{item.likelihood_reason}</p>}
      <p className="secondary">
        {/* Un rotulo de texto, no de formulario: `Mark`, no `FieldLabel` (`<label>`). */}
        <Mark pictogram={uiPictogram("person")}>{tr("Afecta a:", "Affects:")}</Mark> {item.affected.join(", ")}
      </p>
      <HypothesisPlaceLine item={item} moduleName={moduleName} />
      {!board && hasKnowledge && knowledge}
      {!board && checks}
      {!board && measures}
      <HypothesisReview hypothesis={item} operator={operator} onReviewed={onReviewed} />
      {!board && evidence}
      {board &&
        (item.checks.length > 0 || hasKnowledge || countermeasures.length > 0 || flow.length > 0 || item.evidence.length > 0) && (
        <BoardDetail label={tr("comprobaciones, lo que se sabe, contramedidas, flujo y evidencia", "checks, what is known, countermeasures, flow and evidence")}>
          {checks}
          {hasKnowledge && knowledge}
          {measures}
          {evidence}
        </BoardDetail>
      )}
    </article>
  );
}

/**
 * Dónde está lo que la hipótesis señala: el módulo de la excursión medida o el del sistema
 * declarado (§5.34.4), con su rótulo. Null si no señala un módulo (un sistema entero, o ninguna
 * excursión). Debajo, quién estaba allí según la ubicación declarada, que el backend da igual
 * para las dos.
 */
function hypothesisPlace(item: CrewHypothesis): { module: string; label: string } | null {
  if (item.excursion !== null) return { module: item.excursion.module, label: tr("Medida en:", "Measured in:") };
  const module = item.system?.module ?? null;
  return module === null ? null : { module, label: tr("Declarado en:", "Declared in:") };
}

export function HypothesisPlaceLine({
  item,
  moduleName,
}: {
  item: CrewHypothesis;
  moduleName: (key: string) => string;
}) {
  const place = hypothesisPlace(item);
  if (place === null) return null;
  return (
    <p className="secondary">
      {place.label}{" "}
      <Mark pictogram={modulePictogram(place.module)}>
        {moduleName(place.module)}
      </Mark>
      {item.location !== undefined && (
        <>
          {item.location.present.length > 0 && (
            <>
              {" · "}
              <MarkOf mark={presenceMark("present")}>{tr("estaban allí", "were there")}</MarkOf>:{" "}
              {item.location.present.join(", ")}
            </>
          )}
          {item.location.elsewhere.length > 0 && (
            <>
              {" · "}
              <MarkOf mark={presenceMark("elsewhere")}>{tr("en otro módulo", "in another module")}</MarkOf>:{" "}
              {item.location.elsewhere.join(", ")}
            </>
          )}
          {item.location.undeclared.length > 0 && (
            <>
              {" · "}
              <MarkOf mark={presenceMark("undeclared")}>{tr("sin ubicación declarada", "no declared location")}</MarkOf>:{" "}
              {item.location.undeclared.join(", ")}
            </>
          )}
        </>
      )}
    </p>
  );
}

/**
 * Dos excursiones del mismo parametro en modulos distintos dan el mismo titulo: la clave
 * lleva tambien el modulo, el requisito y el inicio para que React no las confunda.
 */
function hypothesisKey(item: CrewHypothesis): string {
  const excursion = item.excursion;
  return excursion === null
    ? `${item.kind}:${item.title}`
    : `${item.kind}:${excursion.module}:${excursion.parameter}:${excursion.requirement}:${excursion.start}`;
}

/**
 * Una fila de la tabla de atmosfera: el parametro con su pictograma, la cifra, y la clase del
 * limite que se ha salido —normativo: triangulo amarillo; confort o rango objetivo: rombo azul—
 * con la palabra al lado. Sin lectura es un dato ausente (cian, anillo punteado). Exportada solo
 * para pintarla a HTML estatico en las pruebas.
 */
export function HabitatRow({
  spec,
  value,
  active,
  comfort,
}: {
  spec: HabitatParameter;
  value: number | null;
  active: HabitatExcursion | null;
  comfort: HabitatExcursion | null;
}) {
  const unit = displayUnit(spec.unit);
  const digits = decimalsFor;
  const range = healthRange(spec);
  const labels = limitLabels(spec);
  return (
    <>
      <dt>
        <Mark pictogram={parameterPictogram(spec.key)}>{spec.display}</Mark>
      </dt>
      <dd>
        {value === null ? (
          <MarkOf mark={MISSING_MARK}>{tr("sin dato", "no data")}</MarkOf>
        ) : (
          <>
            <span className="num">{formatNumber(value, digits(value))}</span> {unit}{" "}
            {active !== null ? (
              <MarkOf mark={limitMark(active.kind)}>{tr(`fuera de ${active.requirement}`, `outside ${active.requirement}`)}</MarkOf>
            ) : comfort !== null ? (
              <MarkOf mark={limitMark(comfort.kind)}>
                {comfort.kind === "target"
                  ? tr(`fuera de ${comfort.requirement}`, `outside ${comfort.requirement}`)
                  : tr(`fuera de la zona de confort ${comfort.requirement}`, `outside the comfort zone ${comfort.requirement}`)}
              </MarkOf>
            ) : (
              <span className="secondary">{tr("límite", "limit")} {range}</span>
            )}
            <CabinMeter spec={spec} value={value} active={active} />
            {labels.length > 0 && (
              <Fold data-ui="habitat-limits" concept="limits" summaryClassName="secondary" label={tr("Qué dice la norma de estos límites", "What the standard says about these limits")}>
                <ul className="secondary">
                  {labels.map((text) => (
                    <li key={text}>{text}</li>
                  ))}
                </ul>
              </Fold>
            )}
          </>
        )}
      </dd>
    </>
  );
}

/**
 * Donde cae la lectura respecto a su limite normativo (§5.33.4): un medidor neutro, con la banda
 * de lo permitido, sobre la escala que `meterScale` deriva del propio limite. No hay medidor
 * donde esa escala no se puede dar sin inventarla (varios limites, figura conjunta, unidad sin
 * cero fisico): la cifra y la palabra de la fila siguen diciendo lo mismo.
 *
 * Fuera de la escala, el medidor no recorta la barra (Open MCT): la deja vacia y lleva al lado la
 * marca y la palabra que la fila ya pinta, «fuera de …» con su requisito. Esa palabra solo existe
 * si el backend declara la excursion vigente; si la lectura se sale de la escala sin ella (una
 * lectura suelta por encima mientras la media de una hora sigue dentro), no se pinta medidor:
 * no hay palabra del backend que lo diga, y la interfaz no la escribe.
 *
 * El caso contrario —la media de una hora fuera y la ultima lectura ya dentro— pinta la barra
 * dentro de la banda junto a «fuera de …»: es lo que dicen la cifra y la palabra de la misma fila
 * (la lectura y el juicio sobre la media), y el medidor solo situa la cifra.
 */
function CabinMeter({
  spec,
  value,
  active,
}: {
  spec: HabitatParameter;
  value: number;
  active: HabitatExcursion | null;
}) {
  const scale = meterScale(spec);
  if (scale === null) return null;
  const inScale = value >= scale.min && value <= scale.max;
  if (!inScale && active === null) return null;
  return (
    <Meter
      value={value}
      min={scale.min}
      max={scale.max}
      label={spec.display}
      band={scale.band}
      {...(active === null
        ? {}
        : { outOfRange: { mark: limitMark(active.kind), word: tr(`fuera de ${active.requirement}`, `outside ${active.requirement}`) } })}
    />
  );
}

/**
 * Una lectura que se muestra y no se evalua: la cifra y la frase del backend, sin pictograma de
 * aviso ni color de alerta (el pictograma del parametro, la bombilla, solo nombra). Sin lectura
 * es un dato ausente (cian, anillo punteado), como en las demas. Exportada solo para pintarla a
 * HTML estatico en las pruebas.
 */
export function DisplayOnlyRow({ spec, value }: { spec: HabitatDisplayOnly; value: number | null }) {
  // Requisitos leidos que NO se evaluan: se listan con su condicion, sin compararlos con la
  // lectura y sin pictograma ni color de aviso. El rotulo y cada frase son del backend.
  const references = spec.reference_requirements ?? [];
  return (
    <>
      <dt>
        <Mark pictogram={parameterPictogram(spec.key)}>{spec.display}</Mark>
      </dt>
      <dd>
        {value === null ? (
          <MarkOf mark={MISSING_MARK}>{tr("sin dato", "no data")}</MarkOf>
        ) : (
          <>
            {/* Un recuento de colonias es entero: «12,0 UFC/mL» diria una precision que no tiene. */}
            <span className="num">
              {formatNumber(value, spec.unit.startsWith("{CFU}") ? 0 : decimalsFor(value))}
            </span>{" "}
            {displayUnit(spec.unit)}
          </>
        )}{" "}
        <span className="secondary">{spec.limit_note}</span>
        {references.length > 0 && (
          // `source` y no `limits`: lo que se lista se leyó en la norma y no se evalúa (§5.33.4).
          <Fold data-ui="habitat-references"
            concept="source"
            label={`${spec.reference_label ?? ""} (${formatNumber(references.length)})`}
          >
            <ul>
              {references.map((item) => {
                // Un requisito sin cifra (la microbiologia) se lista sin cifra: no se pinta una
                // casilla vacia donde iria un numero que nadie ha leido.
                const figure = referenceFigure(item);
                return (
                  <li key={item.source_row}>
                    {item.label}:{" "}
                    {figure !== "" && (
                      <>
                        <span className="num">{figure}</span>{" "}
                      </>
                    )}
                    ({item.requirement}, {item.table}){" "}
                    <span className="secondary">{item.condition}</span>
                  </li>
                );
              })}
            </ul>
            {spec.reference_source != null && (
              <p className="secondary">
                {spec.reference_source.title} · {tr("lectura del documento:", "document read on:")}{" "}
                {formatSourceDate(spec.reference_source.read_on)}
              </p>
            )}
          </Fold>
        )}
        {spec.personal_exposure != null && (
          <PersonalLightDetails reading={spec.personal_exposure} />
        )}
      </dd>
    </>
  );
}

/** El grupo de un parametro del habitat; sin grupo declarado, el de la atmosfera de cabina. */
const CABIN_GROUP = "cabin";
function groupOf(spec: { group?: string }): string {
  return spec.group ?? CABIN_GROUP;
}

/** La linea «Módulo: …» de un bloque de lecturas: la misma en la atmosfera y en las muestras. */
function ModuleLine({ module, moduleName }: { module: string; moduleName: (key: string) => string }) {
  return (
    <p className="secondary">
      {tr("Módulo:", "Module:")}{" "}
      <Mark pictogram={modulePictogram(module)} color="text">
        <strong>{moduleName(module)}</strong>
      </Mark>
    </p>
  );
}

/**
 * El agua potable y la microbiologia del aire y las superficies (decision del 2026-10-22): se
 * muestran y no se evaluan. Un bloque por grupo del backend, con su nombre (`group_display`) y
 * el pictograma del bloque; dentro, cada lectura con su cifra y los valores guia o el requisito
 * leidos, en las mismas filas que la luz (`DisplayOnlyRow`), sin color ni forma de aviso. Sin
 * ninguna lectura del grupo, sus parametros se listan igual, con «sin dato» (dato ausente) y lo
 * leido al lado: lo que se sabe del limite no depende de que haya muestra.
 *
 * Una muestra se toma de vez en cuando, no a cada hora: cada modulo dice cuando se tomo su
 * ultima muestra, para que una de hace un mes no se lea como de ahora. Y el bloque lleva una
 * marca de entorno por cada entorno distinto de sus muestras, no solo el de la primera.
 */
export function HabitatSamples({
  specs,
  latest,
  moduleName,
  inListOrder,
  met,
}: {
  specs: HabitatDisplayOnly[];
  latest: HabitatState["latest"];
  moduleName: (key: string) => string;
  inListOrder: (keys: Iterable<string>) => string[];
  met: (iso: string) => string;
}) {
  const groups = [...new Set(specs.map(groupOf))];
  return (
    <div className="grid-2">
      {groups.map((group) => {
        const members = specs.filter((spec) => groupOf(spec) === group);
        const keys = new Set(members.map((spec) => spec.key));
        const readings = latest.filter((item) => keys.has(item.parameter));
        const places = inListOrder(readings.map((item) => item.module));
        const contexts = [...new Set(readings.map((item) => item.evidence_context))].sort();
        const rows =(module: string | null) => (
          <dl className="kv">
            {members.map((spec) => (
              <DisplayOnlyRow
                key={spec.key}
                spec={spec}
                value={
                  module === null
                    ? null
                    : (readings.find((item) => item.module === module && item.parameter === spec.key)
                        ?.value ?? null)
                }
              />
            ))}
          </dl>
        );
        return (
          <div key={group}>
            <PanelTitle as="h3" pictogram={groupPictogram(group)}>
              {members[0]?.group_display ?? group}{" "}
              {contexts.map((context) => (
                <ObservationTypeBadge
                  key={context}
                  type={members[0]?.observation_type ?? "measured"}
                  context={context}
                />
              ))}
            </PanelTitle>
            {/* Tablero (lote «muestra», 2026-11-08): las filas, con sus valores guía y lo leído de la
                norma, tras «Ver detalle»; a la vista, cada lectura en su baldosa, sin color ni forma
                de aviso porque no se evalúa, y la que falta con la marca de dato ausente de su fila. */}
            <BoardOnly>
              <div className="board-stats">
                {(places.length === 0 ? [null] : places).flatMap((module) =>
                  members.map((spec) => {
                    const value =
                      module === null
                        ? null
                        : (readings.find((item) => item.module === module && item.parameter === spec.key)?.value ??
                          null);
                    const label =
                      module !== null && places.length > 1 ? (
                        <>
                          {spec.display} <span className="secondary">· {moduleName(module)}</span>
                        </>
                      ) : (
                        spec.display
                      );
                    return (
                      <StatTile
                        key={`${module ?? ""}:${spec.key}`}
                        pictogram={parameterPictogram(spec.key)}
                        label={label}
                        value={value}
                        decimals={value === null ? 0 : spec.unit.startsWith("{CFU}") ? 0 : decimalsFor(value)}
                        unit={displayUnit(spec.unit)}
                        {...(value === null ? { status: { mark: MISSING_MARK, word: tr("sin dato", "no data") } } : {})}
                      />
                    );
                  }),
                )}
              </div>
            </BoardOnly>
            <BoardDetail label={members[0]?.group_display ?? group}>
            {places.length === 0
              ? rows(null)
              : places.map((module) => {
                  const last = readings
                    .filter((item) => item.module === module)
                    .map((item) => item.effective)
                    .sort()
                    .at(-1);
                  return (
                    <div key={module}>
                      <ModuleLine module={module} moduleName={moduleName} />
                      {rows(module)}
                      {last !== undefined && (
                        <p className="secondary">
                          <Mark pictogram={uiPictogram("time")}>{tr("Última muestra", "Latest sample")}</Mark>{" "}
                          <span className="num">{met(last)}</span>
                        </p>
                      )}
                    </div>
                  );
                })}
            </BoardDetail>
          </div>
        );
      })}
    </div>
  );
}

/**
 * Lo leido sobre la luz que recibe cada persona: que NASA no publica un limite, la
 * recomendacion de Tierra con a quien se aplica, y las frases tal cual. Sin pictograma ni color
 * de aviso y sin compararlo con la lectura: el backend dice que no se evalua, y por que.
 */
function PersonalLightDetails({ reading }: { reading: PersonalLightExposure }) {
  const { recommendations } = reading;
  return (
    <Fold data-ui="habitat-personal-light" pictogram={parameterPictogram("cabin-light")} label={`${reading.display} (${reading.label})`}>
      {reading.status !== null && <p>{reading.status}</p>}
      <p className="secondary">{reading.not_measured}</p>
      <p className="secondary">
        {recommendations.quantity} · {recommendations.setting}. {recommendations.note}
      </p>
      <ul>
        {recommendations.items.map((item) => (
          <li key={item.period}>
            {item.label}: <span className="num">{referenceFigure({ ...item, stated: null })}</span>{" "}
            <span className="secondary">
              <q lang="en">{item.statement.quote}</q> ({item.statement.where})
            </span>
          </li>
        ))}
      </ul>
      <ul>
        {[...recommendations.scope, ...reading.context].map((item) => (
          <li key={item.id}>
            {item.label}: <q lang="en">{item.quote}</q>{" "}
            <span className="secondary">
              {item.title} · {item.where} · {item.extent_text}, {tr("lectura del", "read on")}{" "}
              {formatSourceDate(item.read_on)}
            </span>
          </li>
        ))}
      </ul>
      <ul className="secondary">
        {reading.searched.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </Fold>
  );
}
