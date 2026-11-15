import { useEffect, useState } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { BoardOnly, useLook } from "../components/BoardOnly";
import { FieldLabel } from "../components/FieldLabel";
import { Fold } from "../components/Fold";
import { MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { StatTile } from "../components/StatTile";
import { Th } from "../components/Th";
import { populationMark } from "../evidence/sourceMarks";
import {
  type DatasetAccess,
  type DatasetAreas,
  type DatasetCatalog,
  type DatasetControls,
  type DatasetEmmaUse,
  type DatasetLadderCell,
  type DatasetPhase,
  type DatasetQuote,
  type DatasetRole,
  type DatasetScheduleStep,
  type HumanDataset,
  type HumanDatasets,
  humanDatasetsApi,
} from "../lib/api";
import { formatNumber, formatSourceDate } from "../lib/format";
import { tr } from "../lib/i18n";
import { LOADING_MARK, MISSING_MARK, type RequestOutcome, mark, requestOutcome } from "../lib/marks";
import {
  CATALOG_PICTOGRAM,
  DATASETS_PICTOGRAM,
  accessMark,
  cellMark,
  controlStatusMark,
  emmaUseMark,
  phaseStatusMark,
} from "./datasets";
import { contextCell } from "./testbeds";
import { ContextTally } from "./TestbedsPanel";

/**
 * Mapa de conjuntos de datos humanos y CIPHER (base de conocimiento §8 y tarea P0 de §15).
 *
 * Una fila por conjunto —OSD-569, Inspiration4/SOMA, el Twins Study, OSD-343, OSD-288, MMASH y los
 * reposos en cama AGBRESA y OSD-51— con a quién mide (y sobre quién son los ficheros abiertos, que
 * en OSD-343 no es lo mismo), sus variables (las diez áreas del Twins Study, enteras), sus tomas
 * antes, durante y después del vuelo o, en un análogo, su propio calendario, sus controles, su
 * acceso, su uso en EMMA y su papel en la estrategia de datos (INPUT, KNOWLEDGE, CONTEXT) con
 * para qué sirve al modelo, que el backend rotula como deducción de EMMA y aquí se pinta sin
 * marca; arriba, la escalera de hitos de la conversación de ideación con los días
 * leídos en su tramo; después, los catálogos de §8, que no miden a nadie; abajo, CIPHER con sus
 * catorce estudios y sus tres duraciones, sin un solo día que sus páginas no den.
 *
 * Todo el texto viene de `GET /api/human-datasets`; aquí solo hay rótulos de inventario y la marca
 * de cada palabra (`datasets.ts`). Inventario: no interviene en el estado de la tripulación.
 *
 * Tablero (2026-11-07): bajo la concha de la maqueta, arriba, cuántos conjuntos, catálogos y
 * estudios de CIPHER hay (`StatTile`) y una píldora por población con la marca de su plegable (la
 * huella en amarillo si no son solo personas) y cuántos conjuntos la miden. Resumen de lo que va
 * debajo, que no cambia (`BoardOnly`).
 */
export function DatasetsPanel() {
  const [body, setBody] = useState<HumanDatasets | null>(null);
  const [failure, setFailure] = useState<RequestOutcome | null>(null);

  useEffect(() => {
    let current = true;
    humanDatasetsApi
      .get()
      .then((received) => {
        if (current) setBody(received);
      })
      .catch((reason: unknown) => {
        if (current) setFailure(requestOutcome(reason));
      });
    return () => {
      current = false;
    };
  }, []);

  if (body === null) {
    return (
      <section data-ui="datasets" className="panel" aria-label={tr("Conjuntos de datos humanos", "Human datasets")}>
        <PanelTitle pictogram={DATASETS_PICTOGRAM}>{tr("Conjuntos de datos humanos y CIPHER", "Human datasets and CIPHER")}</PanelTitle>
        {failure === null ? (
          <p className="secondary">
            <MarkOf mark={LOADING_MARK}>{tr("Consultando el mapa de conjuntos de datos…", "Loading the dataset map…")}</MarkOf>
          </p>
        ) : (
          <p>
            <MarkOf mark={failure.mark}>{tr("Mapa de conjuntos de datos no disponible:", "Dataset map unavailable:")} {failure.text}</MarkOf>
          </p>
        )}
      </section>
    );
  }
  return <DatasetsView body={body} />;
}

/** El mapa ya recibido. Aparte del que consulta para poder pintarlo en las pruebas sin red. */
export function DatasetsView({ body }: { body: HumanDatasets }) {
  const board = useLook() === "reference";
  const notFound = (
    <div className="board-part">
    <PanelTitle as="h3" concept="searchedNotFound" className="section-gap">
      {tr("Buscado y no encontrado", "Searched and not found")}
    </PanelTitle>
    <BoardDetail
      label={tr(`${formatNumber(body.not_found.length)} ${body.not_found.length === 1 ? "búsqueda" : "búsquedas"} sin resultado`, `${formatNumber(body.not_found.length)} ${body.not_found.length === 1 ? "search" : "searches"} with no result`)}
    >
      <ul className="evidence">
        {body.not_found.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </BoardDetail>
    </div>
  );
  return (
    <section data-ui="datasets" className="panel" aria-label={tr("Conjuntos de datos humanos", "Human datasets")}>
      <PanelTitle pictogram={DATASETS_PICTOGRAM}>{tr("Conjuntos de datos humanos y CIPHER", "Human datasets and CIPHER")}</PanelTitle>
      {/* Lote «muestra» (2026-11-08): las reglas y frases de la conversación, la pauta de los
          controles, lo que es CIPHER y lo no encontrado, tras «Ver detalle» en el tablero; las cifras,
          la escalera de hitos, la fila de cada conjunto y catálogo y el estado de cada fase, a la vista. */}
      <BoardDetail label={tr("reglas de la conversación", "rules from the conversation")}>
      <p className="secondary">{body.note}</p>
      <p>
        {body.rule.text} <span className="secondary">· {body.rule.where}</span>
      </p>
      <p>
        {body.task.text} <span className="secondary">· {body.task.where}</span>
      </p>
      <p>
        {tr("De cada fuente, la conversación pregunta:", "Of each source, the conversation asks:")} «{body.fitness_rule.text}»{" "}
        <span className="secondary">· {body.fitness_rule.where}</span>
      </p>
      </BoardDetail>
      <BoardOnly>
        <DatasetsBoard body={body} />
      </BoardOnly>

      {/* Cuarta ronda (R4-8, 2026-11-08): los apartados, baldosas en tres columnas fijas bajo la concha
          de la maqueta (`.board-parts`: la escalera; los conjuntos y los catálogos;
          CIPHER y lo no encontrado), en el orden de siempre. Desde la quinta ronda (R5-9), en el
          tablero lo no encontrado va en la primera columna, bajo la escalera (ver abajo). En la clásica los envoltorios no pintan nada. */}
      <div className="board-parts">
      <div className="board-col">
      <div className="board-part">
      <PanelTitle as="h3" concept="date" className="section-gap">
        {tr("Escalera de hitos", "Milestone ladder")}
      </PanelTitle>
      {/* Lote «muestra», segunda ronda (2026-11-08): el panel medía unos 1 900 px. La escalera (quince
          filas en una caja de 24 rem) y los catorce conjuntos (plegables con `data-ui`: el asistente
          abre el detalle para llegar a ellos), tras «Ver detalle»; a la vista, cuántas casillas de la
          escalera hay de cada estado con su marca (lo no encontrado, en cian, incluido) y cuántos
          conjuntos de cada entorno de evidencia (su población va en las píldoras de arriba). */}
      <BoardOnly>
        <LadderTally body={body} />
      </BoardOnly>
      <BoardDetail label={tr("de dónde sale y la escalera", "where it comes from and the ladder")}>
        <p>
          <span className="num wrap">{body.milestones.text}</span>{" "}
          <span className="secondary">· {body.milestones.where}</span>
        </p>
      <div className="quality-table table-scroll" role="region" tabIndex={0} aria-label={tr("Días de toma por tramo", "Collection days by segment")}>
        <table className="recovery">
          <thead>
            <tr>
              <Th pictogram={DATASETS_PICTOGRAM}>{tr("Conjunto", "Dataset")}</Th>
              {body.milestones.segments.map((segment) => (
                <Th key={segment.label} concept="date">
                  <span className="num">{segment.label}</span>
                </Th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[
              ...body.datasets.map((dataset) => ({ id: dataset.id, name: dataset.name, cells: dataset.ladder })),
              { id: "cipher", name: body.cipher.name, cells: body.cipher.ladder_cells },
            ].map((row) => (
              <tr key={row.id}>
                <th scope="row">{row.name}</th>
                {row.cells.map((cell) => (
                  <td key={cell.segment}>
                    <MarkOf mark={cellMark(cell)}>
                      {cell.labels.length > 0 ? <span className="num">{cell.labels.join(" · ")}</span> : cell.text}
                    </MarkOf>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      </BoardDetail>
      </div>
      {/* Quinta ronda (R5-9, 2026-11-09): en el tablero, lo no encontrado bajo la escalera, en la
          primera columna, que era la más corta; con CIPHER, la tercera medía 480 px y fijaba el alto
          del panel y de su fila con los bancos. En la clásica, en su sitio de siempre, al final. */}
      {board && notFound}
      </div>

      <div className="board-col">
      <div className="board-part">
      <PanelTitle as="h3" pictogram={DATASETS_PICTOGRAM} className="section-gap">
        {tr("Conjuntos", "Datasets")}
      </PanelTitle>
      <BoardOnly>
        <ContextTally items={body.datasets} label={tr("Conjuntos por entorno de evidencia", "Datasets by evidence setting")} />
      </BoardOnly>
      <BoardDetail label={tr(`controles, pauta y ${formatNumber(body.datasets.length)} ${body.datasets.length === 1 ? "conjunto" : "conjuntos"}`, `controls, pattern and ${formatNumber(body.datasets.length)} ${body.datasets.length === 1 ? "dataset" : "datasets"}`)}>
      <dl className="kv">
        <FieldLabel as="dt" concept="comparison">
          {tr("Controles", "Controls")}
        </FieldLabel>
        <dd>
          <span lang="en">{body.controls_rule.points.join(" · ")}</span>
          <div className="secondary">{body.controls_rule.where}</div>
        </dd>
        <FieldLabel as="dt" concept="during">
          {tr("Pauta de un análogo", "Pattern of an analog")}
        </FieldLabel>
        <dd>
          <span lang="en">{body.analog_pattern.text}</span>
          <div className="secondary">{body.analog_pattern.where}</div>
        </dd>
      </dl>
      <div className="datasets-folds">
        {body.datasets.map((dataset) => (
          <DatasetFold key={dataset.id} dataset={dataset} phases={body.phases} />
        ))}
      </div>
      </BoardDetail>
      </div>

      <div className="board-part">
      <PanelTitle as="h3" pictogram={CATALOG_PICTOGRAM} className="section-gap">
        {tr("Catálogos", "Catalogs")}
      </PanelTitle>
      <div className="datasets-folds">
        {body.catalogs.map((catalog) => (
          <CatalogFold key={catalog.id} catalog={catalog} />
        ))}
      </div>
      </div>
      </div>

      <div className="board-col">
      <div className="board-part">
      <CipherBlock cipher={body.cipher} phases={body.phases} />
      </div>

      {!board && notFound}
      </div>
      </div>
    </section>
  );
}

/**
 * Las cifras del mapa y el reparto de los conjuntos por población, en el orden en que aparecen, con
 * la palabra del backend del primero que la lleva.
 */
function DatasetsBoard({ body }: { body: HumanDatasets }) {
  const populations = new Map<string, { word: string; count: number }>();
  for (const dataset of body.datasets) {
    const entry = populations.get(dataset.population);
    if (entry === undefined) populations.set(dataset.population, { word: dataset.population_display, count: 1 });
    else entry.count += 1;
  }
  return (
    <div className="board-row datasets-board">
      <div className="board-stats" role="group" aria-label={tr("Conjuntos, catálogos y estudios", "Datasets, catalogs and studies")}>
        <StatTile pictogram={DATASETS_PICTOGRAM} label={tr("Conjuntos", "Datasets")} value={body.datasets.length} />
        <StatTile pictogram={CATALOG_PICTOGRAM} label={tr("Catálogos", "Catalogs")} value={body.catalogs.length} />
        <StatTile concept="protocol" label={tr(`Estudios de ${body.cipher.name}`, `${body.cipher.name} studies`)} value={body.cipher.studies.length} />
      </div>
      {populations.size > 0 && (
        <ul className="board-tally" aria-label={tr("Conjuntos por población", "Datasets by population")}>
          {[...populations].map(([population, entry]) => {
            const shown = populationMark(population);
            return (
              <li key={population} className="ref-pill board-pill">
                <MarkOf mark={shown}>{entry.word}</MarkOf> <span className="num">{formatNumber(entry.count)}</span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

/**
 * Cuántas casillas de la escalera de hitos (los conjuntos y CIPHER) hay de cada estado, con la marca
 * de la casilla y la frase del backend; las casillas con días (que no traen frase: llevan los días)
 * se cuentan juntas con el calendario, «con días de toma», como dice el rótulo de la tabla.
 */
function LadderTally({ body }: { body: HumanDatasets }) {
  const cells = [...body.datasets.flatMap((dataset) => dataset.ladder), ...body.cipher.ladder_cells];
  const states = new Map<string, { cell: DatasetLadderCell; word: string | null; count: number }>();
  for (const cell of cells) {
    const key = cell.labels.length > 0 ? "labels" : `${cell.status}|${cell.text ?? ""}`;
    const entry = states.get(key);
    if (entry === undefined) states.set(key, { cell, word: cell.labels.length > 0 ? null : cell.text, count: 1 });
    else entry.count += 1;
  }
  return (
    <ul className="board-tally" aria-label={tr("Casillas de la escalera por estado", "Ladder cells by status")}>
      {[...states].map(([key, { cell, word, count }]) => (
        <li key={key} className="ref-pill board-pill">
          <span>
            <MarkOf mark={cellMark(cell)}>{word ?? (cell.labels.length > 0 ? tr("con días de toma", "with collection days") : cell.status)}</MarkOf>{" "}
            <span className="num">{formatNumber(count)}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

/**
 * Un conjunto, plegado: el signo del plegable es su población (la persona, o la huella en
 * amarillo si no son solo personas), y dentro todo lo demás con la frase de la que sale.
 */
function DatasetFold({ dataset, phases }: { dataset: HumanDataset; phases: Record<string, string> }) {
  const context = contextCell(dataset);
  const population = populationMark(dataset.population);
  return (
    <Fold data-ui="dataset"
      mark={population}
      aria-label={tr(`Conjunto ${dataset.name}`, `Dataset ${dataset.name}`)}
      label={
        <>
          <strong>{dataset.name}</strong>
          <span className="secondary">
            {" "}
            · {dataset.population_display} · {context.word}
          </span>
        </>
      }
    >
      <dl className="kv">
        <FieldLabel as="dt" concept="person">
          {tr("Población", "Population")}
        </FieldLabel>
        <dd>
          <MarkOf mark={population}>{dataset.population_display}</MarkOf>
        </dd>
        {dataset.open_population_display !== null && (
          <>
            <FieldLabel as="dt" pictogram="padlock-open">
              {tr("Ficheros abiertos", "Open files")}
            </FieldLabel>
            <dd>
              <MarkOf mark={populationMark(dataset.open_population)}>{dataset.open_population_display}</MarkOf>
              {dataset.open_population_note !== null && <div>{dataset.open_population_note}</div>}
            </dd>
          </>
        )}
        <FieldLabel as="dt" concept="provenance">
          {tr("Entorno de evidencia", "Evidence setting")}
        </FieldLabel>
        <dd>
          <MarkOf mark={context.mark}>{context.word}</MarkOf>
        </dd>
        <KbRow kbRow={dataset.kb_row} kbWhere={dataset.kb_where} />
        <FieldLabel as="dt" concept="person">
          {tr("A quién", "Subjects")}
        </FieldLabel>
        <dd>
          <QuoteList items={dataset.subjects} />
        </dd>
        <FieldLabel as="dt" concept="measure">
          Variables
        </FieldLabel>
        <dd>
          <ul className="evidence mt-0">
            {dataset.variables.map((item) => (
              <li key={`${item.ref}:${item.quote}`}>
                {item.what}
                <div>
                  <QuoteLine item={item} />
                </div>
              </li>
            ))}
          </ul>
        </dd>
        {dataset.areas !== null && <AreasRow areas={dataset.areas} />}
        <PhaseRows phases={dataset.phases} names={phases} />
        {dataset.analog_schedule !== null && <ScheduleRow schedule={dataset.analog_schedule} />}
        <ControlsRow controls={dataset.controls} />
        <AccessRow access={dataset.access} />
        <EmmaUse use={dataset.emma_use} />
        <RoleRow role={dataset.role} />
        <FieldLabel as="dt" concept="decline">
          {tr("Qué no es", "What it is not")}
        </FieldLabel>
        <dd>{dataset.caveat}</dd>
        <FieldLabel as="dt" concept="document">
          {tr("Ficha", "Record")}
        </FieldLabel>
        <dd className="secondary">
          {dataset.source}
          {dataset.url !== null && <div className="num url">{dataset.url}</div>}
        </dd>
      </dl>
    </Fold>
  );
}

/** La fila de la base de conocimiento, con su apartado (§8, o §3.1 para los análogos). */
function KbRow({ kbRow, kbWhere }: { kbRow: string | null; kbWhere: string | null }) {
  if (kbRow === null) return null;
  return (
    <>
      <FieldLabel as="dt" concept="docs">
        {tr("Base de conocimiento", "Knowledge base")} {kbWhere}
      </FieldLabel>
      <dd>{kbRow}</dd>
    </>
  );
}

/** Las áreas de un estudio, enteras: la frase que las cuenta y cada una con la suya. */
function AreasRow({ areas }: { areas: DatasetAreas }) {
  return (
    <>
      <FieldLabel as="dt" concept="measure">
        {tr("Áreas", "Areas")}
      </FieldLabel>
      <dd>
        <QuoteLine item={areas.cited} />
        <ol className="evidence">
          {areas.items.map((area) => (
            <li key={area.name}>
              <span lang="en">{area.name}</span> · {area.what}
              <div>
                <QuoteLine item={area} />
              </div>
            </li>
          ))}
        </ol>
      </dd>
    </>
  );
}

/** El calendario de un análogo: cada paso con sus etapas de la pauta y la frase que lo dice. */
function ScheduleRow({ schedule }: { schedule: DatasetScheduleStep[] }) {
  return (
    <>
      <FieldLabel as="dt" concept="during">
        {tr("Calendario del análogo", "Analog schedule")}
      </FieldLabel>
      <dd>
        <ul className="evidence mt-0">
          {schedule.map((step) => (
            <li key={`${step.ref}:${step.quote}`}>
              <span lang="en">{step.stages.join(" · ")}</span>
              <div>
                <QuoteLine item={step} />
              </div>
            </li>
          ))}
        </ul>
      </dd>
    </>
  );
}

/**
 * Los controles: el estado con su marca y cada control con la población que mide (la huella si
 * son animales: los de OSD-288 son ratones), su palabra del backend y la frase que lo nombra.
 */
function ControlsRow({ controls }: { controls: DatasetControls }) {
  return (
    <>
      <FieldLabel as="dt" concept="comparison">
        {tr("Controles", "Controls")}
      </FieldLabel>
      <dd>
        <MarkOf mark={controlStatusMark(controls.status)}>{controls.status_text}</MarkOf>
        {controls.items.length > 0 && (
          <ul className="evidence mt-0">
            {controls.items.map((control) => (
              <li key={control.kind}>
                <MarkOf mark={populationMark(control.population)}>
                  {control.kind_text} · {control.population_display}
                </MarkOf>
                <div>
                  <QuoteLine item={control} />
                </div>
              </li>
            ))}
          </ul>
        )}
        {controls.why !== null && <div>{controls.why}</div>}
        {controls.searched !== null && <div className="secondary">{controls.searched}</div>}
        {controls.absent.length > 0 && (
          <>
            {/* Separadas de las que sostienen un control: estas dicen cuál no hay. */}
            <div className="secondary">{tr("Lo que la fuente dice que no hay:", "What the source says is not there:")}</div>
            <QuoteList items={controls.absent} />
          </>
        )}
      </dd>
    </>
  );
}

/** Un catálogo de §8, plegado: qué es (frase), su acceso, su uso en EMMA y lo que no es. */
function CatalogFold({ catalog }: { catalog: DatasetCatalog }) {
  return (
    <Fold data-ui="dataset-catalog"
      mark={mark(CATALOG_PICTOGRAM, null)}
      aria-label={tr(`Catálogo ${catalog.name}`, `Catalog ${catalog.name}`)}
      label={<strong>{catalog.name}</strong>}
    >
      <dl className="kv">
        <KbRow kbRow={catalog.kb_row} kbWhere={catalog.kb_where} />
        <FieldLabel as="dt" concept="sourceText">
          {tr("Qué es", "What it is")}
        </FieldLabel>
        <dd>
          <QuoteList items={catalog.what} />
        </dd>
        <AccessRow access={catalog.access} />
        <EmmaUse use={catalog.emma_use} />
        <FieldLabel as="dt" concept="decline">
          {tr("Qué no es", "What it is not")}
        </FieldLabel>
        <dd>{catalog.caveat}</dd>
        <FieldLabel as="dt" concept="document">
          {tr("Ficha", "Record")}
        </FieldLabel>
        <dd className="secondary">
          {catalog.source}
          {catalog.url !== null && <div className="num url">{catalog.url}</div>}
        </dd>
      </dl>
    </Fold>
  );
}

/** CIPHER: lo que es, sus catorce estudios, sus tres duraciones y lo que sus páginas no dan. */
function CipherBlock({ cipher, phases }: { cipher: HumanDatasets["cipher"]; phases: Record<string, string> }) {
  return (
    <article aria-label={cipher.name}>
      <PanelTitle as="h3" concept="protocol" className="section-gap">
        {cipher.name} <span lang="en">({cipher.full_name})</span>
      </PanelTitle>
      {/* En el tablero, el estado de cada fase con su marca, a la vista; la ficha entera, en el detalle. */}
      <BoardOnly>
        <ul className="board-tally" aria-label={tr(`Fases de ${cipher.name}`, `${cipher.name} phases`)}>
          {Object.entries(cipher.phases).map(([key, phase]) => (
            <li key={key} className="ref-pill board-pill">
              <span>
                {phases[key] ?? key}: <MarkOf mark={phaseStatusMark(phase.status)}>{phase.status_text}</MarkOf>
              </span>
            </li>
          ))}
          {/* El acceso y el uso en EMMA, con su marca, también a la vista. */}
          <li className="ref-pill board-pill">
            <span>
              {tr("Acceso:", "Access:")} <MarkOf mark={accessMark(cipher.access.level)}>{cipher.access.level_text}</MarkOf>
            </span>
          </li>
          <li className="ref-pill board-pill">
            <span>
              {tr("Uso en EMMA:", "Use in EMMA:")} <MarkOf mark={emmaUseMark(cipher.emma_use)}>{cipher.emma_use.used_text}</MarkOf>
            </span>
          </li>
        </ul>
      </BoardOnly>
      <BoardDetail label={tr(`ficha de ${cipher.name}`, `${cipher.name} record`)}>
      <div>
        <QuoteLine item={cipher.what} />
      </div>
      <dl className="kv">
        <FieldLabel as="dt" concept="protocol">
          {tr("Estudios", "Studies")}
        </FieldLabel>
        <dd>
          <span lang="en">{cipher.studies.join(" · ")}</span>
          <div className="secondary">{cipher.studies_where}</div>
        </dd>
        <FieldLabel as="dt" concept="person">
          {tr("A quién", "Subjects")}
        </FieldLabel>
        <dd>
          <QuoteLine item={cipher.cohort} />
        </dd>
        <FieldLabel as="dt" concept="during">
          {tr("Duraciones", "Durations")}
        </FieldLabel>
        <dd>
          <QuoteList items={cipher.ladder} />
        </dd>
        <PhaseRows phases={cipher.phases} names={phases} />
        <AccessRow access={cipher.access} />
        <EmmaUse use={cipher.emma_use} />
        <RoleRow role={cipher.role} />
      </dl>
      </BoardDetail>
    </article>
  );
}

/** Las tres fases: el estado con su marca, los días leídos y de dónde sale cada cosa. */
function PhaseRows({ phases, names }: { phases: Record<string, DatasetPhase>; names: Record<string, string> }) {
  return (
    <>
      {Object.entries(phases).map(([key, phase]) => (
        <div key={key} className="contents">
          <FieldLabel as="dt" concept="date">
            {names[key] ?? key}
          </FieldLabel>
          <dd>
            <MarkOf mark={phaseStatusMark(phase.status)}>{phase.status_text}</MarkOf>
            {phase.labels.length > 0 && <span className="num"> · {phase.labels.join(" · ")}</span>}
            {phase.why !== null && <div>{phase.why}</div>}
            {phase.searched !== null && <div className="secondary">{phase.searched}</div>}
            {phase.cited.length > 0 && <QuoteList items={phase.cited} />}
          </dd>
        </div>
      ))}
    </>
  );
}

/** El acceso: el nivel con su marca, de dónde sale y su frase, su fichero o dónde se buscó. */
function AccessRow({ access }: { access: DatasetAccess }) {
  return (
    <>
      <FieldLabel as="dt" pictogram="key-bit">
        {tr("Acceso", "Access")}
      </FieldLabel>
      <dd>
        <MarkOf mark={accessMark(access.level)}>{access.level_text}</MarkOf>
        <span className="secondary"> · {access.basis_text}</span>
        {access.why !== null && <div>{access.why}</div>}
        {access.searched !== null && <div className="secondary">{access.searched}</div>}
        {access.path !== null && <div className="secondary num url">{access.path}</div>}
        {access.cited.length > 0 && <QuoteList items={access.cited} />}
      </dd>
    </>
  );
}

function EmmaUse({ use }: { use: DatasetEmmaUse }) {
  return (
    <>
      <FieldLabel as="dt" concept="systems">
        {tr("Uso en EMMA", "Use in EMMA")}
      </FieldLabel>
      <dd>
        <MarkOf mark={emmaUseMark(use)}>{use.used_text}</MarkOf>
        <div>{use.text}</div>
        {use.where !== null && <div className="secondary num url">{use.where}</div>}
      </dd>
    </>
  );
}

/**
 * El papel en la estrategia de datos y para qué sirve al modelo. Sin marca ni color: no es un
 * estado de nada, es una deducción de EMMA, y el rótulo del backend lo dice junto a cada valor.
 */
function RoleRow({ role }: { role: DatasetRole }) {
  return (
    <>
      <FieldLabel as="dt" concept="inferred">
        {tr("Papel y aptitud", "Role and fitness")}
      </FieldLabel>
      <dd>
        <div>
          <span lang="en">{role.level}</span> · {role.level_text}
          <span className="secondary"> · {role.basis_text}</span>
        </div>
        <div>{role.level_why}</div>
        <div>
          {role.fitness_text}
          <span className="secondary"> · {role.basis_text}</span>
        </div>
        <div>{role.fitness_why}</div>
      </dd>
    </>
  );
}

function QuoteList({ items }: { items: DatasetQuote[] }) {
  return (
    <ul className="evidence mt-0">
      {items.map((item) => (
        <li key={`${item.ref}:${item.quote}`}>
          <QuoteLine item={item} />
        </li>
      ))}
    </ul>
  );
}

/**
 * Una frase de la fuente, en su idioma, con su ficha: de quién es, dónde está y cuándo se leyó (el
 * día de la frase, que el backend resuelve). Un campo de la ficha que la fuente no muestra se dice
 * sin verificar, en cian.
 */
function QuoteLine({ item }: { item: DatasetQuote }) {
  return (
    <>
      <q lang="en">{item.quote}</q>
      <div className="secondary">
        <span lang="en">{item.source}</span> · {item.where} · {tr("leído el", "read on")}{" "}
        <span className="num">{formatSourceDate(item.read_on)}</span>
        {item.unverified_display.length > 0 && (
          <>
            {" "}
            · <MarkOf mark={MISSING_MARK}>{tr(`sin verificar: ${item.unverified_display.join(", ")}`, `not verified: ${item.unverified_display.join(", ")}`)}</MarkOf>
          </>
        )}
      </div>
      {item.url !== null && <div className="secondary num url">{item.url}</div>}
    </>
  );
}
