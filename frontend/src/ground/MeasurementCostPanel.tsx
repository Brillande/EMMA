import { useEffect, useState } from "react";

import { BoardOnly } from "../components/BoardOnly";
import { Fold } from "../components/Fold";
import { IndicatorName } from "../components/IndicatorName";
import { Mark, MarkOf } from "../components/Mark";
import { Meter } from "../components/Meter";
import { PanelTitle } from "../components/PanelTitle";
import { aspectPictogram, profilePictogram } from "../dashboard/missionPictograms";
import { AspectStatus } from "../dashboard/MissionProfileView";
import {
  type CostKbCoverage,
  type CostSummary,
  type GroundDependence,
  type Indicator,
  type ProfileCitation,
  risksApi,
} from "../lib/api";
import { formatNumber, formatSourceDate } from "../lib/format";
import { tr } from "../lib/i18n";
import { UNKNOWN_PICTOGRAM, type RequestOutcome, requestOutcome } from "../lib/marks";
import {
  GROUND_PICTOGRAM,
  KB_PICTOGRAM,
  UNCLASSIFIED_STYLE,
  cellText,
  countRows,
  coverages,
  groundRows,
  groupByMode,
  modePictogram,
  readRules,
  searchedRows,
  splitCells,
} from "./measurementCost";

/**
 * Coste de medir (base de conocimiento §9): que hace falta para cada indicador y cuanto tiempo
 * de tripulacion cuesta. Agrupado por clase, de lo continuo y pasivo a lo que exige
 * laboratorio. Un tiempo sin fuente se muestra como "sin fuente", nunca como cifra.
 *
 * Desde la novena ronda cada indicador dice además dónde se procesa, cuándo llega el resultado
 * y si gasta consumibles, con el texto que sostiene cada clase. Lo que el repositorio no dice
 * sale «sin clasificar», en cian (dato ausente), y el total va arriba. Todas las palabras son
 * del backend (`GET /api/measurement-cost`); la lógica, en `measurementCost.ts`, que da también
 * el pictograma de cada clase de medida y de cada valor de dimensión, junto a su palabra.
 *
 * Desde la undécima ronda, las reglas que se apoyan en una fuente leída enseñan la frase tal cual
 * (en su idioma), con su sitio y el día de lectura, y al lado lo leído que las matiza o
 * contradice: una discrepancia no se esconde para que la clase parezca más firme.
 *
 * Desde la decimocuarta ronda, «hoy se sabe después» (conversación de ideación ~643 y ~754): lo
 * que depende hoy de Tierra al lado de lo que la fuente de cada perfil de misión dice del
 * reabastecimiento y del regreso, y lo buscado y no encontrado, en cian como lo sin clasificar.
 *
 * Desde la decimosexta ronda, la lista de la base de conocimiento §9 con dónde la tiene EMMA, y
 * cinco dimensiones más (masa, volumen, potencia, calibración, formación y guía del operador).
 * Casi todo sale sin clasificar: lo de cada indicador va junto en una línea cian, para que lo
 * decidido se lea. Una cifra leída se formatea aquí (`lib/format.ts`), con su unidad tal cual.
 *
 * Desde la decimonovena ronda, la lista de la conversación de ideación (~673) al lado de la de KB
 * §9, con el término que no entra («valor clínico») y su motivo, y tres dimensiones más
 * (almacenamiento, frecuencia posible, capacidad de automatización). La automatización la deduce
 * EMMA de la clase de medida: su fila lleva el rótulo del backend que lo dice, y cada palabra lo
 * repite. Las columnas nuevas se pliegan con las demás y no llevan color.
 *
 * Tablero (2026-11-07): bajo la concha de la maqueta el rótulo del plegable lleva, junto al título,
 * cuántos indicadores tienen todas sus dimensiones clasificadas sobre cuántos hay (cifra y medidor
 * neutro, escala la del propio total) y una píldora cian con los pares indicador-dimensión sin
 * clasificar: así se lee cerrado, que es como se queda. Las tres cifras son del backend.
 */
export function MeasurementCostPanel({ indicators }: { indicators: Indicator[] }) {
  const [summary, setSummary] = useState<CostSummary | null>(null);
  const [error, setError] = useState<RequestOutcome | null>(null);

  useEffect(() => {
    let current = true;
    risksApi
      .cost()
      .then((body) => {
        if (current) setSummary(body.summary);
      })
      .catch((reason: unknown) => {
        if (current) setError(requestOutcome(reason));
      });
    return () => {
      current = false;
    };
  }, []);

  const groups = groupByMode(indicators);
  if (groups.length === 0) return null;
  return (
    <Fold data-ui="measurement-cost"
      concept="measurementCost"
      className="panel"
      aria-label={tr("Coste de medir", "Measurement cost")}
      label={
        <>
          <h2 className="inline">{tr("Coste de medir", "Measurement cost")}</h2>
          {summary !== null && (
            <BoardOnly>
              <CostBoard summary={summary} />
            </BoardOnly>
          )}
        </>
      }
    >
      {summary === null ? (
        error !== null && (
          <p>
            <MarkOf mark={error.mark}>{tr("Dimensiones del coste no disponibles:", "Cost dimensions unavailable:")} {error.text}</MarkOf>
          </p>
        )
      ) : (
        <div role="group" aria-label={tr("Dimensiones del coste de medir", "Measurement cost dimensions")}>
          <p className="secondary">{summary.unclassified_note}</p>
          {coverages(summary).map((coverage) => (
            <KbCoverageView key={coverage.display} coverage={coverage} />
          ))}
          <dl className="kv">
            {summary.dimensions.map((dimension) => (
              <div key={dimension.key} className="contents">
                <dt>
                  {dimension.display}
                  {dimension.deduced && (
                    <>
                      {" "}
                      <span className="secondary">({summary.deduced_display})</span>
                    </>
                  )}
                </dt>
                <dd>
                  {/* Lo que EMMA deduce en vez de leer lo dice el backend, una vez, en su fila. */}
                  {dimension.deduced && (
                    <p className="secondary mt-0">
                      {summary.deduced_note}
                    </p>
                  )}
                  <ul className="evidence mt-0">
                    {countRows(dimension, summary).map((row) => (
                      <li key={row.key}>
                        <MarkOf mark={row.style}>{row.display}</MarkOf>{" "}
                        <span className="num">({formatNumber(row.count)})</span>
                      </li>
                    ))}
                  </ul>
                </dd>
              </div>
            ))}
          </dl>
          <GroundDependenceView ground={summary.ground_dependence} indicators={indicators} />
          {summary.searched.length > 0 && (
            <section data-ui="measurement-cost-searched" aria-label={summary.searched_display}>
              <PanelTitle as="h3" pictogram={UNCLASSIFIED_STYLE.pictogram ?? UNKNOWN_PICTOGRAM}>
                {summary.searched_display}
              </PanelTitle>
              <ul className="evidence">
                {searchedRows(summary, indicators).map((row) => (
                  <li key={`${row.names.map((name) => name.key).join("|")}:${row.dimensions}`}>
                    <MarkOf mark={UNCLASSIFIED_STYLE}>
                      {row.names.map((name, index) => (
                        <span key={name.key}>
                          {index > 0 && " · "}
                          <IndicatorName indicatorKey={name.key} displayEs={name.displayEs} />
                        </span>
                      ))}
                    </MarkOf>{" "}
                    <span className="secondary">({row.dimensions})</span>
                    <div>{row.searched}</div>
                    <div className="secondary">
                      {tr("buscado el", "searched on")} <span className="num">{formatSourceDate(row.searchedOn)}</span>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {readRules(summary).map(({ rule, sections }) => (
            <article key={rule.id} className="mt-3" aria-label={tr(`Lo leído: ${rule.id}`, `What was read: ${rule.id}`)}>
              <p>{rule.basis}</p>
              {sections.map((section) => (
                <div key={section.kind}>
                  {/* Lo que sostiene y lo que matiza: el dibujo de su marca (`measurementCost.ts`)
                      como signo del título, y su color si un día lo tiene. */}
                  <PanelTitle
                    as="h4"
                    pictogram={section.style.pictogram ?? UNKNOWN_PICTOGRAM}
                    {...(section.style.className !== undefined && { className: section.style.className })}
                  >
                    {section.label}
                  </PanelTitle>
                  <ul className="evidence">
                    {section.items.map((item) => (
                      <li key={`${item.ref}:${item.quote}`}>
                        <q lang="en">{item.quote}</q>
                        {item.note !== undefined && <div>{item.note}</div>}
                        <div className="secondary">
                          <span lang="en">{item.source}</span> · {item.where} · {tr("leído el", "read on")}{" "}
                          <span className="num">{formatSourceDate(item.read_on)}</span>
                        </div>
                        {item.url !== null && <div className="secondary num url">{item.url}</div>}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </article>
          ))}
        </div>
      )}
      {groups.map(({ mode, label, items }) => (
        <div key={mode}>
          <PanelTitle as="h3" pictogram={modePictogram(mode)}>
            {label}
          </PanelTitle>
          <ul className="drivers">
            {items.map((item) => (
              <li key={item.key}>
                <IndicatorName indicatorKey={item.key} displayEs={item.display_es} />{" "}
                <span className="secondary">— {item.measurement_cost?.equipment}</span>
                {item.measurement_cost?.crew_time_minutes != null && (
                  <>
                    {" "}
                    · <span className="num">{formatNumber(item.measurement_cost.crew_time_minutes)}</span>{" "}
                    min
                  </>
                )}
                <span className="secondary"> · {item.measurement_cost?.crew_time_basis}</span>
                {summary !== null && <IndicatorCells item={item} summary={summary} />}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </Fold>
  );
}

/**
 * Las piezas del rótulo: los indicadores con todo decidido sobre el total, con su medidor, y los pares
 * indicador-dimensión por decidir en cian (el dato ausente). Sin indicadores no hay escala: nada.
 */
function CostBoard({ summary }: { summary: CostSummary }) {
  if (summary.indicators <= 0) return null;
  return (
    <span className="board-row cost-board">
      <span className="cost-board-meter">
        <span>
          <span className="num">{formatNumber(summary.fully_classified)}</span> {tr("de", "of")}{" "}
          <span className="num">{formatNumber(summary.indicators)}</span>{" "}
          {tr("indicadores con todas las dimensiones clasificadas", "indicators with every dimension classified")}
        </span>
        <Meter
          value={summary.fully_classified}
          max={summary.indicators}
          label={tr("Indicadores con todas las dimensiones clasificadas", "Indicators with every dimension classified")}
          outOfRange={{ word: tr("fuera del total de indicadores", "outside the total of indicators") }}
        />
      </span>
      {summary.unclassified > 0 && (
        <span className="ref-pill board-pill">
          {/* Un solo hijo (R4-8): la píldora es flexible y, en la columna estrecha junto al marco,
              partía la frase en tres columnas de dos renglones. */}
          <span>
            <MarkOf mark={UNCLASSIFIED_STYLE}>{summary.unclassified_display}</MarkOf>{" "}
            <span className="num">{formatNumber(summary.unclassified)}</span> {tr("pares indicador-dimensión", "indicator-dimension pairs")}
          </span>
        </span>
      )}
    </span>
  );
}

/**
 * Las dimensiones de un indicador: cada una decidida en su línea, con el texto que la sostiene
 * (una cifra leída, formateada aquí), y las que siguen sin clasificar juntas en una línea cian.
 */
function IndicatorCells({ item, summary }: { item: Indicator; summary: CostSummary }) {
  const { classified, unclassified } = splitCells(item, summary);
  return (
    <ul className="evidence mt-0">
      {classified.map((cell) => (
        <li key={cell.key} title={cell.entry.basis ?? undefined}>
          <span className="secondary">{cell.label}:</span> <MarkOf mark={cell.style}>{cellText(cell.entry)}</MarkOf>
          {cell.entry.basis !== null && <div className="secondary">{cell.entry.basis}</div>}
        </li>
      ))}
      {unclassified.length > 0 && (
        <li>
          <MarkOf mark={UNCLASSIFIED_STYLE}>{summary.unclassified_display}</MarkOf>:{" "}
          <span className="secondary">{unclassified.join(" · ")}</span>
        </li>
      )}
    </ul>
  );
}

/**
 * Una lista del equipo tal cual (la base de conocimiento §9; la conversación de ideación), y al
 * lado dónde la tiene EMMA: un campo de cada indicador, una dimensión de arriba o que no entra, con
 * su motivo en la nota. Todas las palabras son del backend.
 */
function KbCoverageView({ coverage }: { coverage: CostKbCoverage }) {
  return (
    <section data-ui="kb-coverage" aria-label={coverage.display} className="mt-3">
      <PanelTitle as="h3" pictogram={KB_PICTOGRAM}>
        {coverage.display}
      </PanelTitle>
      <p className="secondary">{coverage.origin}</p>
      <dl className="kv">
        {coverage.terms.map((term) => (
          <div key={term.term} className="contents">
            <dt>{term.term}</dt>
            <dd>
              {term.display}
              {term.note !== null && <div className="secondary">{term.note}</div>}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

/**
 * «Hoy se sabe después»: lo que depende hoy de Tierra y, al lado, lo que la fuente de cada perfil
 * dice del reabastecimiento y del regreso. Todas las palabras son del backend; lo que la fuente
 * del perfil no dice sale «EMMA no tiene fuente» en cian, con el mismo estilo que el aspecto «sin
 * verificar» del perfil de misión (`dashboard/missionProfile.ts`): es el mismo dato ausente.
 */
function GroundDependenceView({ ground, indicators }: { ground: GroundDependence; indicators: Indicator[] }) {
  return (
    <section data-ui="ground-dependence" aria-label={ground.display} className="mt-3">
      <PanelTitle as="h3" pictogram={GROUND_PICTOGRAM}>
        {ground.display}
      </PanelTitle>
      <p className="secondary">{ground.origin}</p>
      <p>{ground.note}</p>
      <p>
        <span className="secondary">{ground.value_display}:</span>{" "}
        {groundRows(ground, indicators).map((row, index) => (
          <span key={row.key} title={row.result}>
            {index > 0 && " · "}
            {row.inherited ? (
              <Mark pictogram={modePictogram("derived")}>
                <IndicatorName indicatorKey={row.key} displayEs={row.displayEs} />
              </Mark>
            ) : (
              <IndicatorName indicatorKey={row.key} displayEs={row.displayEs} />
            )}
          </span>
        ))}
      </p>
      {ground.profiles.map((profile) => (
        <div key={profile.id}>
          <PanelTitle as="h4" pictogram={profilePictogram(profile.id) ?? UNKNOWN_PICTOGRAM}>
            {profile.display}
          </PanelTitle>
          <ul className="drivers">
            {profile.aspects.map((aspect) => (
              <li key={aspect.key}>
                <strong>
                  <Mark pictogram={aspectPictogram(aspect.key)}>{aspect.label}</Mark>:
                </strong>{" "}
                {/* La marca la decide el estado del backend (`aspectDisplay`): lo leído va sin
                    señal, lo que falta en cian con el anillo punteado y uno desconocido en gris. */}
                <AspectStatus status={aspect.status}>{aspect.text}</AspectStatus>
                {aspect.searched !== null && <div className="secondary">{aspect.searched}</div>}
                <ProfileCitations items={aspect.citations} />
                {aspect.discrepancy !== null && (
                  <>
                    <div>{aspect.discrepancy.text}</div>
                    <ProfileCitations items={aspect.discrepancy.citations} />
                  </>
                )}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}

/** La frase del perfil tal cual se leyó, con su página, su apartado y el día de lectura. */
function ProfileCitations({ items }: { items: ProfileCitation[] }) {
  return (
    <>
      {items.map((item) => (
        <div key={`${item.ref}|${item.quote}`} className="secondary">
          <q lang="en">{item.quote}</q> — <span lang="en">{item.title}</span>, {item.section}; {tr("leído el", "read on")}{" "}
          <span className="num">{formatSourceDate(item.read_on)}</span>
        </div>
      ))}
    </>
  );
}
