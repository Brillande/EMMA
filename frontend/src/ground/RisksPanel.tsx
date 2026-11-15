import { useEffect, useState } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { BoardOnly, useLook } from "../components/BoardOnly";
import { DomainName } from "../components/DomainName";
import { FieldLabel } from "../components/FieldLabel";
import { Fold } from "../components/Fold";
import { IndicatorName } from "../components/IndicatorName";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { StatTile } from "../components/StatTile";
import { Th } from "../components/Th";
import { EvidenceList } from "../evidence/EvidenceList";
import {
  type RiskCountermeasure,
  type RiskDetectionRule,
  type RiskEntity,
  type RiskEquipment,
  type RiskMatrixRef,
  type RiskMmashKey,
  type RiskSensitivity,
  type RisksResponse,
  risksApi,
} from "../lib/api";
import { formatNumber } from "../lib/format";
import { tr } from "../lib/i18n";
import {
  EMPTY_MARK,
  LOADING_MARK,
  MISSING_MARK,
  prefixedPictogram,
  type StateMark,
  type RequestOutcome,
  requestOutcome,
} from "../lib/marks";
import { ridgePictogram } from "./framework";
import { HrpCoverage } from "./HrpCoverage";
import {
  chainSign,
  countermeasureMark,
  dataMark,
  dataPopulationMark,
  evaluationStyle,
  levelRows,
  linkLabel,
  phraseRefs,
  quantifiedUnexpectedly,
  referenceStyle,
  SENSITIVITY_MARK,
  sensitivityMark,
  stepSign,
  validationMark,
} from "./risks";

/**
 * Cada riesgo de EMMA, entero (especificación §3): su peligro RIDGE, la región del cuerpo, la
 * evidencia que cita, el esquema de niveles del motor y lo que EMMA sabe decir de su
 * incertidumbre.
 *
 * Es un inventario: no depende de ningún tripulante y no decide nada. El esquema de niveles es
 * una leyenda —la puntuación desde la que empieza cada nivel—, por eso va sin colores de alarma.
 * La incertidumbre no lleva probabilidad: EMMA no la cuantifica, y la frase que lo dice es del
 * backend, como todas las demás. Cada riesgo es un dominio y lleva su pictograma, el peligro RIDGE
 * el suyo y cada indicador el de su familia; la lógica está en `risks.ts`.
 *
 * Desde la segunda pasada (§5.33.6) cada rótulo de la ficha de un riesgo lleva su signo: el
 * pentágono de las cinco amenazas del RIDGE (el mismo del apartado «Peligro RIDGE» del marco), la
 * figura del cuerpo, la diana del alcance, la regla de los indicadores, la hoja de la evidencia, el
 * poste de las contramedidas, la base del cálculo y el más-menos de la incertidumbre.
 *
 * Desde la decimocuarta ronda (§5.34.11) el panel abre con la matriz de la conversación de
 * ideación: una fila por riesgo con sus seis eslabones —peligro, efecto, variable, dato, detección
 * y contramedida—, cada columna con el signo de su campo (`risks.ts`). El dato separa conjuntos de
 * datos y documentos como los separa el registro; la detección es la frase que compone el backend
 * leyendo el motor, y la regla común va plegada debajo, paso a paso. Ninguna palabra de la tabla se
 * escribe aquí.
 *
 * Desde la decimoquinta ronda (§5.35.10) la variable lleva el equipo de a bordo de cada indicador
 * (coste de medir), agrupado, y la detección dice qué indicadores del riesgo salen de MMASH —las
 * claves del cargador— y que eso valida el motor de medida y la falsa alarma en Tierra, no la
 * fisiología espacial; el riesgo sin ninguno lo dice con la marca de «vacío». La frase es del
 * backend; aquí solo se elige la marca (`validationMark`).
 *
 * Desde la decimosexta ronda (§5.36.2) la detección dice también sobre qué indicadores se ha medido
 * la sensibilidad inyectando deterioros, con cuál y dónde están las cifras —la frase es del backend,
 * leída del inyector—, con la serie que salta (`sensitivityMark`) o, sin ninguno, la de «vacío». La
 * ficha lista cada indicador con sus deterioros y la forma de cada uno.
 */
export function RisksPanel() {
  const [body, setBody] = useState<RisksResponse | null>(null);
  const [error, setError] = useState<RequestOutcome | null>(null);

  useEffect(() => {
    let current = true;
    risksApi
      .get()
      .then((found) => {
        if (current) setBody(found);
      })
      .catch((reason: unknown) => {
        if (current) setError(requestOutcome(reason));
      });
    return () => {
      current = false;
    };
  }, []);

  if (body === null) {
    return (
      <div role="group" aria-label={tr("Riesgos", "Risks")}>
        <PanelTitle as="h3" concept="risks" className="section-gap">
          {tr("Riesgos", "Risks")}
        </PanelTitle>
        {error === null ? (
          <p className="secondary">
            <MarkOf mark={LOADING_MARK}>{tr("Consultando los riesgos…", "Loading the risks…")}</MarkOf>
          </p>
        ) : (
          <p>
            <MarkOf mark={error.mark}>{tr("Inventario de riesgos no disponible:", "Risk inventory unavailable:")} {error.text}</MarkOf>
          </p>
        )}
      </div>
    );
  }

  return <RisksView body={body} />;
}

/** Los riesgos ya consultados; aparte para poder pintarlos sin red en las pruebas. */
export function RisksView({ body }: { body: RisksResponse }) {
  const board = useLook() === "reference";
  const schema = body.severity_schema;
  const quantified = quantifiedUnexpectedly(body.risks);
  const quantifiedMark = quantified.length > 0 && (
    <p>
      <Mark pictogram="slash-circle" color="gray">
        {tr("Esta consola no enseña una incertidumbre cuantificada:", "This console does not show a quantified uncertainty:")}{" "}
        <span className="num">{quantified.join(", ")}</span>
      </Mark>
    </p>
  );

  return (
    <div role="group" aria-label={tr("Riesgos", "Risks")}>
      <PanelTitle as="h3" concept="risks" className="section-gap">
        {tr("Riesgos", "Risks")}
      </PanelTitle>
      {/* Lote «muestra», segunda ronda (2026-11-08): «Marco y fuentes» seguía midiendo unos 6 600 px y
          esta baldosa era la más larga (la matriz de once filas en su caja, la regla, los riesgos del
          HRP, el esquema y una ficha por riesgo). En el tablero queda la marca de lo que esta consola no
          enseña y, en piezas, cuántos riesgos hay y cuántos tienen o no indicadores de MMASH,
          sensibilidad medida y conjunto de datos citado, cada recuento con la marca que lleva en la
          matriz: lo que la matriz dice de la validación no se pliega. Lo demás, tras un solo «Ver
          detalle», en el mismo orden que en la clásica (que lo pinta igual que antes). */}
      {board && quantifiedMark}
      <BoardOnly>
        <RiskTally body={body} />
      </BoardOnly>
      <BoardDetail label={tr(`matriz, regla y ${formatNumber(body.risks.length)} ${body.risks.length === 1 ? "ficha" : "fichas"}`, `matrix, rule and ${formatNumber(body.risks.length)} ${body.risks.length === 1 ? "record" : "records"}`)}>
        <p>{body.uncertainty_statement}</p>
        {!board && quantifiedMark}

        {/* La matriz lleva las marcas de validación, sensibilidad y dato de cada riesgo; su recuento
            va arriba, en las píldoras. */}
        <RiskMatrix body={body} />
        <DetectionRule rule={body.detection_rule} />
        {/* Todos los riesgos del Roadmap y qué hace EMMA con cada uno, plegados (§5.36.9). */}
        <HrpCoverage />

        <PanelTitle as="h4" concept="ratings">
          {tr("Esquema de niveles", "Level scheme")}
        </PanelTitle>
        <ul className="evidence" aria-label={tr("Esquema de niveles", "Level scheme")}>
          {levelRows(schema).map((row) => (
            <li key={row.level}>
              <Mark pictogram={row.pictogram}>{row.label}</Mark>{" "}
              <span className="secondary">
                {row.from !== null && (
                  <>
                    {tr("desde", "from")} <span className="num">{formatNumber(row.from)}</span>
                  </>
                )}
                {row.from !== null && row.below !== null && ", "}
                {row.below !== null && (
                  <>
                    {tr("por debajo de", "below")} <span className="num">{formatNumber(row.below)}</span>
                  </>
                )}{" "}
                {tr("puntos", "points")}
              </span>
            </li>
          ))}
        </ul>
        <p className="secondary">{schema.basis}</p>
        <p className="secondary num">{schema.rules_version}</p>

        {body.risks.map((item) => (
          <RiskArticle
            key={item.risk_id}
            risk={item}
            links={body.chain.links}
            dataset={body.detection_rule.validated_with.dataset}
          />
        ))}
      </BoardDetail>
    </div>
  );
}

/**
 * Las piezas del tablero: cuántos riesgos hay y, de ellos, cuántos tienen indicadores de MMASH (con
 * la marca del conjunto, la de la matriz; las claves del cargador son de MMASH) y cuántos ninguno (la de «vacío»), cuántos tienen la
 * sensibilidad medida y cuántos no, y cuántos no citan ningún conjunto de datos. Son recuentos de lo
 * que la matriz ya enseña fila a fila, con la misma marca.
 */
function RiskTally({ body }: { body: RisksResponse }) {
  const dataset = body.detection_rule.validated_with.dataset;
  const count = (test: (risk: RiskEntity) => boolean) => body.risks.filter(test).length;
  const validated = count((risk) => risk.validation.keys.length > 0);
  const sensed = count((risk) => risk.sensitivity.keys.length > 0);
  const withoutData = count((risk) => risk.data_sources.datasets.length === 0);
  const total = body.risks.length;
  const pills: { key: string; mark: StateMark; word: string; value: number }[] = [
    { key: "validated", mark: dataMark(dataset), word: tr("Con indicadores de MMASH", "With MMASH indicators"), value: validated },
    { key: "unvalidated", mark: EMPTY_MARK, word: tr("Sin indicadores de MMASH", "Without MMASH indicators"), value: total - validated },
    { key: "sensed", mark: SENSITIVITY_MARK, word: tr("Sensibilidad medida", "Sensitivity measured"), value: sensed },
    { key: "unsensed", mark: EMPTY_MARK, word: tr("Sensibilidad sin medir", "Sensitivity not measured"), value: total - sensed },
    { key: "nodata", mark: EMPTY_MARK, word: tr("Sin conjunto de datos citado", "No dataset cited"), value: withoutData },
  ];
  return (
    <div className="board-row risks-board">
      <div className="board-stats" role="group" aria-label={tr("Riesgos del inventario", "Risks in the inventory")}>
        <StatTile concept="risks" label={tr("Riesgos", "Risks")} value={total} />
      </div>
      <ul className="board-tally" aria-label={tr("Riesgos por validación, sensibilidad y dato", "Risks by validation, sensitivity and data")}>
        {pills
          .filter((pill) => pill.value > 0)
          .map((pill) => (
            <li key={pill.key} className="ref-pill board-pill">
              <span>
                <MarkOf mark={pill.mark}>{pill.word}</MarkOf> <span className="num">{formatNumber(pill.value)}</span>
              </span>
            </li>
          ))}
      </ul>
    </div>
  );
}

/**
 * La matriz: una fila por riesgo y una columna por eslabón, en el orden y con las palabras del
 * backend. Es ancha; en pantalla estrecha se desplaza en vez de cortarse (`quality-table`).
 */
function RiskMatrix({ body }: { body: RisksResponse }) {
  const { links } = body.chain;
  return (
    <>
      <p className="secondary">{body.chain.basis}</p>
      <div className="quality-table table-scroll" role="region" tabIndex={0} aria-label={tr("Matriz de riesgos", "Risk matrix")}>
        <table className="recovery">
          <thead>
            <tr>
              <Th concept="risks">{tr("Riesgo", "Risk")}</Th>
              {links.map((link) => (
                <Th key={link.key} {...chainSign(link.key)}>
                  {link.display}
                </Th>
              ))}
            </tr>
          </thead>
          <tbody>
            {body.risks.map((risk) => (
              <tr key={risk.risk_id}>
                <th scope="row">
                  <DomainName domain={risk.risk_id} label={risk.display} />
                </th>
                {links.map((link) => (
                  <td key={link.key}>
                    <MatrixCell risk={risk} link={link.key} dataset={body.detection_rule.validated_with.dataset} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

/** Lo que va en cada celda; un eslabón que la interfaz no conoce se dice, no se calla. */
function MatrixCell({ risk, link, dataset }: { risk: RiskEntity; link: string; dataset: RiskMatrixRef }) {
  switch (link) {
    case "hazard":
      return <Mark pictogram={ridgePictogram(risk.ridge.category)}>{risk.ridge.display}</Mark>;
    case "effect":
      return (
        <>
          {risk.effect.statement}
          {risk.effect.source !== null && <div className="secondary">{risk.effect.source.title}</div>}
        </>
      );
    case "variables":
      return (
        <>
          <span className="num">{formatNumber(risk.indicators.length)}</span>
          <EquipmentGroups equipment={risk.equipment} />
        </>
      );
    case "data":
      return <DataSources risk={risk} />;
    case "detection":
      return (
        <>
          {risk.detection.summary}
          <div className="secondary">
            <MarkOf mark={validationMark(risk.validation, dataset)}>{risk.validation.statement}</MarkOf>
          </div>
          <div className="secondary">
            <MarkOf mark={sensitivityMark(risk.sensitivity)}>{risk.sensitivity.statement}</MarkOf>
          </div>
        </>
      );
    case "countermeasures":
      return <CountermeasureList countermeasures={risk.countermeasures} />;
    default:
      return <MarkOf mark={EMPTY_MARK}>{link}</MarkOf>;
  }
}

function RefItem({ item }: { item: RiskMatrixRef }) {
  return (
    <li>
      <MarkOf mark={dataMark(item)}>{item.title}</MarkOf>{" "}
      <span className="secondary">
        · {item.evidence_type_display} · <MarkOf mark={dataPopulationMark(item)}>{item.population_display}</MarkOf>
      </span>
    </li>
  );
}

/**
 * El equipo de cada variable (coste de medir), agrupado como lo agrupa el backend: cada equipo,
 * con su palabra, y detrás sus indicadores. Es el equipo de a bordo, no el aparato de MMASH.
 */
function EquipmentGroups({ equipment }: { equipment: RiskEquipment }) {
  return (
    <ul className="evidence mt-0" aria-label={tr("Equipo de cada variable", "Equipment for each variable")}>
      {equipment.groups.map((group) => (
        <li key={group.equipment}>
          <span className="secondary">{group.equipment}:</span>
          {group.indicators.map((entry, index) => (
            <span key={entry.key}>
              {index === 0 ? " " : " · "}
              <IndicatorName indicatorKey={entry.key} displayEs={entry.display_es} />
            </span>
          ))}
        </li>
      ))}
    </ul>
  );
}

/** Las claves que salen de MMASH, cada una con el aparato del conjunto de datos del que sale. */
function MmashKeys({ keys }: { keys: RiskMmashKey[] }) {
  if (keys.length === 0) return null;
  return (
    <ul className="evidence mt-0" aria-label={tr("Indicadores que salen de MMASH", "Indicators that come from MMASH")}>
      {keys.map((entry) => (
        <li key={entry.key}>
          <IndicatorName indicatorKey={entry.key} displayEs={entry.display_es} />{" "}
          <span className="secondary">· {entry.source_display}</span>
        </li>
      ))}
    </ul>
  );
}

/**
 * Los indicadores sobre los que se ha medido la sensibilidad, cada uno con sus deterioros de
 * referencia y la forma de cada uno (palabras del backend). Sin ninguno no se pinta: la frase con
 * la marca de «vacío» ya lo dice.
 */
function SensitivityKeys({ sensitivity }: { sensitivity: RiskSensitivity }) {
  if (sensitivity.keys.length === 0) return null;
  return (
    <ul className="evidence mt-0" aria-label={tr("Indicadores con sensibilidad medida", "Indicators with measured sensitivity")}>
      {sensitivity.keys.map((entry) => (
        <li key={entry.key}>
          <IndicatorName indicatorKey={entry.key} displayEs={entry.display_es} />
          {entry.injections.map((item) => (
            <div key={item.label} className="secondary">
              {item.label} · {item.kind_display}
            </div>
          ))}
        </li>
      ))}
    </ul>
  );
}

/** Conjuntos de datos y documentos por separado, como los separa el registro. */
function DataSources({ risk }: { risk: RiskEntity }) {
  const block = risk.data_sources;
  return (
    <>
      {block.datasets.length > 0 ? (
        <ul className="evidence mt-0">
          {block.datasets.map((item) => (
            <RefItem key={item.id} item={item} />
          ))}
        </ul>
      ) : (
        <div className="secondary">
          <MarkOf mark={EMPTY_MARK}>{block.datasets_empty}</MarkOf>
        </div>
      )}
      {block.documents.length > 0 ? (
        <ul className="evidence mt-0">
          {block.documents.map((item) => (
            <RefItem key={item.id} item={item} />
          ))}
        </ul>
      ) : (
        <div className="secondary">
          <MarkOf mark={EMPTY_MARK}>{block.documents_empty}</MarkOf>
        </div>
      )}
    </>
  );
}

function CountermeasureLine({ item }: { item: RiskCountermeasure }) {
  return (
    <li>
      <MarkOf mark={countermeasureMark(item.basis)}>{item.action}</MarkOf>{" "}
      <span className="secondary num">· {item.id}</span>
      {item.family_display !== null && <div className="secondary">{item.family_display}</div>}
      {item.trigger_display !== null && <div className="secondary">{item.trigger_display}</div>}
      <div className="secondary">{item.basis_display}</div>
    </li>
  );
}

function CountermeasureList({ countermeasures }: { countermeasures: RiskEntity["countermeasures"] }) {
  if (countermeasures.items.length === 0) {
    return <MarkOf mark={EMPTY_MARK}>{countermeasures.empty}</MarkOf>;
  }
  return (
    <ul className="evidence mt-0">
      {countermeasures.items.map((item) => (
        <CountermeasureLine key={item.id} item={item} />
      ))}
    </ul>
  );
}

/** La regla común de detección, plegada: cada paso con su signo y la frase del backend. */
function DetectionRule({ rule }: { rule: RiskDetectionRule }) {
  const validated = rule.validated_with;
  return (
    <Fold data-ui="detection-rule" concept="monitoring" label={rule.display} className="mt-2">
      <dl className="kv">
        {rule.steps.map((step) => (
          <StepRow key={step.key} label={step.display} sign={step.key} statement={step.statement} />
        ))}
        <FieldLabel as="dt" concept="evidence">
          {validated.display}
        </FieldLabel>
        <dd>
          <MarkOf mark={dataMark(validated.dataset)}>{validated.dataset.title}</MarkOf>{" "}
          <span className="secondary">
            · <MarkOf mark={dataPopulationMark(validated.dataset)}>{validated.dataset.population_display}</MarkOf>
          </span>
          {validated.scope !== null && <div>{validated.scope}</div>}
          <div className="secondary">{validated.statement}</div>
          <MmashKeys keys={validated.keys} />
          <div className="secondary">{validated.note}</div>
          <div className="secondary">{validated.keys_basis}</div>
        </dd>
      </dl>
      <p className="secondary">{rule.basis}</p>
      <p className="secondary num">{rule.rules_version}</p>
    </Fold>
  );
}

function StepRow({ label, sign, statement }: { label: string; sign: string; statement: string }) {
  return (
    <>
      <FieldLabel as="dt" {...stepSign(sign)}>
        {label}
      </FieldLabel>
      <dd>{statement}</dd>
    </>
  );
}

/**
 * Una región de «Sistema humano»: su nombre, su frase y, debajo, las fichas que la frase nombra
 * (§5.37.16), con `EvidenceList` como toda cita de EMMA: título, nivel, qué es y su salvedad de
 * alcance. Antes la frase de la vejiga nombraba el riesgo de cálculos sin enseñar su ficha.
 */
export function HumanSystemRegion({ region }: { region: RiskEntity["human_system"]["regions"][number] }) {
  const refs = phraseRefs(region);
  return (
    <div>
      {region.display}
      <div className="secondary">{region.note}</div>
      {refs.length > 0 && <EvidenceList items={refs} />}
    </div>
  );
}

function RiskArticle({
  risk,
  links,
  dataset,
}: {
  risk: RiskEntity;
  links: RisksResponse["chain"]["links"];
  dataset: RiskMatrixRef;
}) {
  const { evidence, countermeasures, evaluation } = risk.uncertainty;
  const ridge = <Mark pictogram={ridgePictogram(risk.ridge.category)}>{risk.ridge.display}</Mark>;
  // El plegable lleva delante el dibujo del dominio (el de `DomainName`), y el nombre sin otro:
  // un riesgo es un dominio, y dos dibujos seguidos para lo mismo sobrarían.
  return (
    <Fold data-ui="hrp-risk"
      pictogram={prefixedPictogram("domain", risk.risk_id)}
      className="mt-2"
      aria-label={tr(`Riesgo ${risk.display}`, `Risk ${risk.display}`)}
      label={
        <>
          <strong>{risk.display}</strong>{" "}
          <span className="secondary">
            · {ridge} · <span className="num">{risk.risk_id}</span>
          </span>
        </>
      }
    >
      <dl className="kv">
        <FieldLabel as="dt" pictogram="pentagon">
          RIDGE
        </FieldLabel>
        <dd>
          {ridge}
          <div className="secondary">
            {risk.ridge.source.title}
            {risk.ridge.source.url !== null && <span className="num url"> · {risk.ridge.source.url}</span>}
          </div>
        </dd>
        <FieldLabel as="dt" concept="body">
          {tr("Sistema humano", "Human system")}
        </FieldLabel>
        <dd>
          {risk.human_system.regions.map((region) => (
            <HumanSystemRegion key={region.key} region={region} />
          ))}
          <div className="secondary">{risk.human_system.basis}</div>
        </dd>
        <FieldLabel as="dt" {...chainSign("effect")}>
          {linkLabel(links, "effect")}
        </FieldLabel>
        <dd>
          {risk.effect.statement}
          <div className="secondary">{risk.effect.basis}</div>
        </dd>
        <FieldLabel as="dt" pictogram="crosshair">
          {tr("Alcance", "Scope")}
        </FieldLabel>
        <dd>{risk.amcl_alignment}</dd>
        <FieldLabel as="dt" concept="indicator">
          {tr("Indicadores", "Indicators")}
        </FieldLabel>
        <dd>
          <span className="num">{formatNumber(risk.indicators.length)}</span>
          <EquipmentGroups equipment={risk.equipment} />
          <div className="secondary">{risk.equipment.basis}</div>
        </dd>
        <FieldLabel as="dt" concept="evidence">
          {tr("Evidencia citada", "Evidence cited")}
        </FieldLabel>
        <dd>
          <ul className="evidence mt-0">
            {evidence.references.map((reference) => (
              <li key={reference.id}>
                <MarkOf mark={referenceStyle(reference)}>{reference.title}</MarkOf>
                <div className="secondary">{reference.grade}</div>
                {reference.unverified_display.length > 0 && (
                  <div>
                    <MarkOf mark={MISSING_MARK}>
                      {tr("sin verificar:", "not verified:")} {reference.unverified_display.join(", ")}
                    </MarkOf>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </dd>
        <FieldLabel as="dt" {...chainSign("detection")}>
          {linkLabel(links, "detection")}
        </FieldLabel>
        <dd>
          {risk.detection.summary}
          {risk.detection.danger_limits.length > 0 && (
            <ul className="evidence mt-0">
              {risk.detection.danger_limits.map((limit) => (
                <li key={limit.key}>
                  <IndicatorName indicatorKey={limit.key} displayEs={limit.statement} />
                </li>
              ))}
            </ul>
          )}
          <div>{risk.detection.isolation_statement}</div>
          {risk.detection.environment.map((item) => (
            <div key={item.key}>{item.statement}</div>
          ))}
          <div className="secondary">{risk.detection.basis}</div>
          {/* La frase con los nombres va en la matriz; aquí, qué valida y la lista con el aparato
              de cada clave, para no repetir los nombres dos veces seguidas. */}
          <div>
            <MarkOf mark={validationMark(risk.validation, dataset)}>
              {risk.validation.validates ?? risk.validation.empty ?? risk.validation.statement}
            </MarkOf>
          </div>
          <MmashKeys keys={risk.validation.keys} />
          {risk.validation.note !== null && <div className="secondary">{risk.validation.note}</div>}
          <div className="secondary">{risk.validation.basis}</div>
          {/* Sobre qué indicadores se ha medido la sensibilidad: la marca con «cuáles» y las cifras
              en su referencia; la lista dice el deterioro y su forma, sin repetir la frase. Sin
              ninguno no se remite a la referencia: allí no hay cifras de este riesgo. */}
          <div>
            <MarkOf mark={sensitivityMark(risk.sensitivity)}>
              {risk.sensitivity.measures ?? risk.sensitivity.empty ?? risk.sensitivity.statement}
            </MarkOf>
            {risk.sensitivity.keys.length > 0 && (
              <span className="secondary num"> · {risk.sensitivity.reference}</span>
            )}
          </div>
          <SensitivityKeys sensitivity={risk.sensitivity} />
          <div className="secondary">{risk.sensitivity.basis}</div>
        </dd>
        <FieldLabel as="dt" concept="recommendations">
          {tr("Contramedidas", "Countermeasures")}
        </FieldLabel>
        <dd>
          {/* La lista, una a una, con su respaldo: sustituye al recuento por respaldo, que deja
              fuera la de refugio (va por evento) y junto a la lista daba dos totales. */}
          <CountermeasureList countermeasures={risk.countermeasures} />
          <div className="secondary">{risk.countermeasures.basis}</div>
          <div className="secondary">{countermeasures.note}</div>
        </dd>
        <FieldLabel as="dt" concept="basis">
          {tr("Se evalúa", "Evaluated")}
        </FieldLabel>
        <dd>
          <MarkOf mark={evaluationStyle(evaluation.evaluated_with)}>
            {evaluation.evaluated_with_display}
          </MarkOf>
          {evaluation.calculated.length > 0 && (
            <div className="secondary">
              {evaluation.calculated_display}: <span className="num">{evaluation.calculated.join(", ")}</span>
            </div>
          )}
          {evaluation.inferred_states.map((state) => (
            <div key={state.key}>
              {state.display} <span className="secondary num">· {state.model_version}</span>
              <div className="secondary">{state.note}</div>
            </div>
          ))}
          <div className="secondary">{evaluation.basis}</div>
        </dd>
        <FieldLabel as="dt" pictogram="plus-minus">
          {tr("Incertidumbre", "Uncertainty")}
        </FieldLabel>
        <dd>{risk.uncertainty.statement}</dd>
      </dl>
    </Fold>
  );
}
