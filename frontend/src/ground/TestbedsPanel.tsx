import { useEffect, useState } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { BoardOnly, useLook } from "../components/BoardOnly";
import { FieldLabel } from "../components/FieldLabel";
import { Fold } from "../components/Fold";
import { MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { StatTile } from "../components/StatTile";
import { Th } from "../components/Th";
import { type Testbed, type TestbedQuote, type TestbedRidgeCell, type Testbeds, testbedsApi } from "../lib/api";
import { formatNumber, formatSourceDate } from "../lib/format";
import { tr } from "../lib/i18n";
import {
  EMPTY_MARK,
  LOADING_MARK,
  MISSING_MARK,
  type RequestOutcome,
  mark,
  requestOutcome,
} from "../lib/marks";
import { ridgePictogram } from "./framework";
import {
  NOT_FOUND_MARK,
  TESTBEDS_PICTOGRAM,
  bankNames,
  columnPictogram,
  contextCell,
  emmaStatusMark,
  leftOutMark,
  ridgeStatusMark,
  validationMark,
} from "./testbeds";

/**
 * Bancos de prueba y las dos validaciones (base de conocimiento §3 y §3.1).
 *
 * Ningún banco reproduce una misión a Marte entera: cada uno aísla unas condiciones y deja fuera
 * otras. Este panel enseña, por banco, lo que reproduce (frase literal de su página, con la ficha
 * del registro), lo que deja fuera (de la fuente o deducido por EMMA, y se dice cuál), el entorno
 * de evidencia que llevaría un dato suyo (el dibujo de la procedencia de una observación) y qué
 * validación permitiría; y las columnas que pedía la conversación de ideación (duración,
 * participantes, datos y proveedores), con la frase de la fuente o, donde ninguna página leída la
 * da, dónde se buscó, con la lupa. La matriz banco × peligro RIDGE (decimosexta ronda) va en una
 * tabla antes de los bancos y, celda a celda con su motivo, dentro de cada uno: es deducción de
 * EMMA salvo donde la ficha de NASA nombra el peligro, y cada celda dice cuál de las dos es.
 * Arriba, lo que EMMA tiene de cada una: la científica en parte y la
 * operacional, ninguna. La frase la compone el backend a partir de la lista vacía, no se escribe
 * aquí.
 *
 * Todo el texto viene de `GET /api/testbeds`; aquí solo hay rótulos de inventario y la marca de
 * cada palabra (`testbeds.ts`). Inventario: no interviene en el estado de la tripulación.
 *
 * Tablero (2026-11-07): bajo la concha de la maqueta, arriba, cuántos bancos hay (`StatTile`) y una
 * píldora por validación con la marca y la frase de lo que EMMA tiene de ella, y cuántos bancos la
 * permitirían. Es un resumen de lo que va debajo, que no cambia (`BoardOnly`).
 */
export function TestbedsPanel() {
  const [testbeds, setTestbeds] = useState<Testbeds | null>(null);
  const [failure, setFailure] = useState<RequestOutcome | null>(null);

  useEffect(() => {
    let current = true;
    testbedsApi
      .get()
      .then((body) => {
        if (current) setTestbeds(body);
      })
      .catch((reason: unknown) => {
        if (current) setFailure(requestOutcome(reason));
      });
    return () => {
      current = false;
    };
  }, []);

  if (testbeds === null) {
    return (
      <section data-ui="testbeds" className="panel" aria-label={tr("Bancos de prueba y validación", "Testbeds and validation")}>
        <PanelTitle pictogram={TESTBEDS_PICTOGRAM}>{tr("Bancos de prueba y validación", "Testbeds and validation")}</PanelTitle>
        {failure === null ? (
          <p className="secondary">
            <MarkOf mark={LOADING_MARK}>{tr("Consultando los bancos de prueba…", "Loading the testbeds…")}</MarkOf>
          </p>
        ) : (
          <p>
            <MarkOf mark={failure.mark}>{tr("Bancos de prueba no disponibles:", "Testbeds unavailable:")} {failure.text}</MarkOf>
          </p>
        )}
      </section>
    );
  }
  return <TestbedsView testbeds={testbeds} />;
}

/** El mapa ya recibido. Aparte del que consulta para poder pintarlo en las pruebas sin red. */
export function TestbedsView({ testbeds }: { testbeds: Testbeds }) {
  const { banks, ladder } = testbeds;
  const board = useLook() === "reference";
  // La palabra de «no se sabe» la da el backend; la celda que falte sale con ella, no en blanco.
  const unknownStatus =
    testbeds.ridge.statuses.find((status) => status.id === "unknown")?.text ?? "unknown";
  const validationsDetail = (
    <>
      {/* Lote «muestra», segunda ronda (2026-11-08): el panel medía unos 1 900 px. Lo que EMMA tiene de
          cada validación va en las píldoras de arriba, con su marca; las dos fichas, tras «Ver
          detalle». La matriz de peligros, sus catorce filas y su leyenda, también, con cuántas
          casillas hay de cada estado a la vista (las de «no se sabe» incluidas); y los catorce bancos
          (plegables con `data-ui`: el asistente abre el detalle para llegar a ellos), con su recuento
          en el rótulo. Nada de caja con barra de desplazamiento: el detalle ya la guarda. */}
      <BoardDetail label={tr(`${formatNumber(testbeds.validations.length)} ${testbeds.validations.length === 1 ? "validación" : "validaciones"}`, `${formatNumber(testbeds.validations.length)} ${testbeds.validations.length === 1 ? "validation" : "validations"}`)}>
      <div className="testbeds-validations">
      {testbeds.validations.map((validation) => (
        <article key={validation.id} aria-label={validation.name} className="mt-3">
          <PanelTitle as="h3" pictogram={validationMark(validation.id).pictogram ?? TESTBEDS_PICTOGRAM}>
            {validation.name}
          </PanelTitle>
          <BoardDetail label={tr("qué es", "what it is")}>
            <p>{validation.what}</p>
          </BoardDetail>
          <p>
            <strong>
              <MarkOf mark={emmaStatusMark(validation.emma_status.status)}>{validation.emma_status.text}</MarkOf>
            </strong>
          </p>
          {/* El entorno de evidencia de cada parte, con su marca (gris si no hay), a la vista. */}
          <BoardOnly>
            <ul className="board-tally" aria-label={tr(`Entorno de evidencia: ${validation.name}`, `Evidence setting: ${validation.name}`)}>
              {validation.emma.map((part) => {
                const context = contextCell({ evidence_context: part.context, outside_enum_text: null });
                return (
                  <li key={part.id} className="ref-pill board-pill">
                    <MarkOf mark={context.mark}>{context.word}</MarkOf>
                  </li>
                );
              })}
            </ul>
          </BoardOnly>
          <BoardDetail label={tr("lo que tiene EMMA y lo que no cubre", "what EMMA has and what it does not cover")}>
          <dl className="kv">
            {validation.emma.map((part) => {
              const context = contextCell({ evidence_context: part.context, outside_enum_text: null });
              return (
                <div key={part.id} className="contents">
                  <dt>
                    <MarkOf mark={context.mark}>{context.word}</MarkOf>
                  </dt>
                  <dd>
                    <div>{part.what}</div>
                    <dl className="kv">
                      <FieldLabel as="dt" concept="decline">
                        {tr("No muestra", "Does not show")}
                      </FieldLabel>
                      <dd>{part.does_not_show}</dd>
                      <FieldLabel as="dt" concept="source">
                        {tr("Cifras en", "Figures in")}
                      </FieldLabel>
                      <dd className="num">{part.figures_in}</dd>
                      <FieldLabel as="dt" concept="document">
                        {tr("Ficha", "Record")}
                      </FieldLabel>
                      <dd className="secondary">
                        {part.source}
                        {part.url !== null && <div className="num url">{part.url}</div>}
                      </dd>
                    </dl>
                  </dd>
                </div>
              );
            })}
            <FieldLabel as="dt" concept="decline">
              {tr("Sin cubrir", "Not covered")}
            </FieldLabel>
            <dd>{validation.not_covered}</dd>
            <FieldLabel as="dt" pictogram={TESTBEDS_PICTOGRAM}>
              {tr("Bancos", "Testbeds")}
            </FieldLabel>
            <dd>{bankNames(validation.banks, banks).join(" · ")}</dd>
          </dl>
          </BoardDetail>
        </article>
      ))}
      </div>
      </BoardDetail>
    </>
  );
  return (
    <section data-ui="testbeds" className="panel" aria-label={tr("Bancos de prueba y validación", "Testbeds and validation")}>
      <PanelTitle pictogram={TESTBEDS_PICTOGRAM}>{tr("Bancos de prueba y validación", "Testbeds and validation")}</PanelTitle>
      {/* Lote «muestra» (2026-11-08): la nota, el principio, lo que tiene cada validación, la
          escalera y lo no encontrado, tras «Ver detalle» en el tablero; las cifras, el estado de
          cada validación, la matriz de peligros y la fila de cada banco, a la vista. */}
      <BoardDetail label={tr("principio", "principle")}>
        <p className="secondary">{testbeds.note}</p>
        <p>
          <q lang="en">{testbeds.principle.text}</q>{" "}
          <span className="secondary">· {testbeds.principle.where}</span>
        </p>
      </BoardDetail>
      <BoardOnly>
        <div className="board-row testbeds-board">
          <div className="board-stats" role="group" aria-label={tr("Bancos de prueba", "Testbeds")}>
            <StatTile pictogram={TESTBEDS_PICTOGRAM} label={tr("Bancos", "Testbeds")} value={banks.length} />
          </div>
          {/* Quinta ronda (R5-9, 2026-11-09): el «Ver detalle» de las validaciones, bajo sus píldoras y
              al lado de la ficha, en vez de un renglón propio debajo (45 px del panel). */}
          <div className="board-side">
            {testbeds.validations.length > 0 && (
              <ul className="board-tally" aria-label={tr("Lo que EMMA tiene de cada validación", "What EMMA has of each validation")}>
                {testbeds.validations.map((validation) => {
                  const shown = emmaStatusMark(validation.emma_status.status);
                  return (
                    <li key={validation.id} className="ref-pill board-pill">
                      {/* Un solo hijo: la píldora es flexible y, a cinco columnas, partía el recuento
                          de bancos en una columna aparte (segunda ronda, 2026-11-08). */}
                      <span>
                        <MarkOf mark={shown}>{validation.emma_status.text}</MarkOf>{" "}
                        <span className="secondary">
                          · <span className="num">{formatNumber(validation.banks.length)}</span>{" "}
                          {validation.banks.length === 1 ? tr("banco", "testbed") : tr("bancos", "testbeds")}
                        </span>
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
            {validationsDetail}
          </div>
        </div>
      </BoardOnly>

      {!board && validationsDetail}

      {/* Cuarta ronda (R4-8, 2026-11-08): los cuatro apartados, baldosas en dos columnas fijas bajo la
          concha de la maqueta (`.board-parts`; la escalera y los peligros, los bancos y lo no
          encontrado). En la clásica los envoltorios no pintan nada: el mismo orden de siempre. */}
      <div className="board-parts">
      <div className="board-col">
      <div className="board-part">
      <PanelTitle as="h3" concept="sourceText" className="section-gap">
        {ladder.title}
      </PanelTitle>
      <BoardDetail label={tr(`${formatNumber(ladder.rungs.length)} ${ladder.rungs.length === 1 ? "peldaño" : "peldaños"} y la regla`, `${formatNumber(ladder.rungs.length)} ${ladder.rungs.length === 1 ? "rung" : "rungs"} and the rule`)}>
      <p className="secondary">{ladder.where}</p>
      <dl className="kv">
        {ladder.rungs.map((rung) => (
          <div key={rung.id} className="contents">
            <dt>{rung.environment}</dt>
            <dd>
              <dl className="kv">
                <FieldLabel as="dt" concept="basis">
                  {tr("Fortaleza", "Strength")}
                </FieldLabel>
                <dd>{rung.strength}</dd>
                <FieldLabel as="dt" concept="limits">
                  {tr("Limitación", "Limitation")}
                </FieldLabel>
                <dd>{rung.limitation}</dd>
                <FieldLabel as="dt" concept="systems">
                  {tr("Uso", "Use")}
                </FieldLabel>
                <dd>{rung.use}</dd>
                <FieldLabel as="dt" pictogram={TESTBEDS_PICTOGRAM}>
                  {tr("Bancos", "Testbeds")}
                </FieldLabel>
                <dd>
                  {rung.banks.length === 0 ? (
                    <MarkOf mark={EMPTY_MARK}>{tr("ninguno", "none")}</MarkOf>
                  ) : (
                    bankNames(rung.banks, banks).join(" · ")
                  )}
                </dd>
              </dl>
            </dd>
          </div>
        ))}
      </dl>
      <p>{testbeds.rule.text}</p>
      <p className="secondary">{testbeds.rule.where}</p>
      </BoardDetail>
      </div>

      <div className="board-part">
      <PanelTitle as="h3" concept="inferred" className="section-gap">
        {tr("Peligros RIDGE por banco", "RIDGE hazards by testbed")}
      </PanelTitle>
      <BoardOnly>
        <RidgeTally testbeds={testbeds} />
      </BoardOnly>
      <BoardDetail label={tr("cómo se lee y la matriz", "how to read it and the matrix")}>
        <p className="secondary">{testbeds.ridge.note}</p>
      <p className="secondary" role="note" aria-label={tr("Leyenda de la matriz RIDGE", "RIDGE matrix legend")}>
        {testbeds.ridge.statuses.map((status, index) => (
          <span key={status.id}>
            {index > 0 && " · "}
            <MarkOf mark={ridgeStatusMark(status.id)}>{status.text}</MarkOf>
          </span>
        ))}
      </p>
      <div className="ridge-matrix table-scroll" role="region" tabIndex={0} aria-label={tr("Peligros RIDGE por banco", "RIDGE hazards by testbed")}>
        <table className="recovery">
          <thead>
            <tr>
              <Th pictogram={TESTBEDS_PICTOGRAM}>{tr("Banco", "Testbed")}</Th>
              {testbeds.ridge.hazards.map((hazard) => (
                <Th key={hazard.id} pictogram={ridgePictogram(hazard.id)}>
                  {hazard.display}
                </Th>
              ))}
            </tr>
          </thead>
          <tbody>
            {banks.map((bank) => (
              <tr key={bank.id}>
                <th scope="row">{bank.name}</th>
                {testbeds.ridge.hazards.map((hazard) => {
                  // Por su peligro, no por su posición: la cabecera y las celdas llegan en dos listas.
                  const cell = bank.ridge.find((item) => item.hazard === hazard.id);
                  return (
                    <td key={hazard.id}>
                      {cell === undefined ? (
                        <MarkOf mark={ridgeStatusMark("unknown")}>{unknownStatus}</MarkOf>
                      ) : (
                        <>
                          <MarkOf mark={ridgeStatusMark(cell.status)}>{cell.status_text}</MarkOf>
                          {cell.basis === "source" && (
                            <div className="secondary">
                              <MarkOf mark={leftOutMark(cell)}>{cell.basis_text}</MarkOf>
                            </div>
                          )}
                        </>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      </BoardDetail>
      </div>
      </div>

      <div className="board-col">
      <div className="board-part">
      <PanelTitle as="h3" pictogram={TESTBEDS_PICTOGRAM} className="section-gap">
        {tr("Bancos de prueba", "Testbeds")}
      </PanelTitle>
      <BoardOnly>
        <ContextTally items={banks} label={tr("Bancos por entorno de evidencia", "Testbeds by evidence setting")} />
      </BoardOnly>
      <BoardDetail label={tr(`${formatNumber(banks.length)} ${banks.length === 1 ? "banco" : "bancos"}, uno por fila`, `${formatNumber(banks.length)} ${banks.length === 1 ? "testbed" : "testbeds"}, one per row`)}>
      <div className="testbeds-banks">
        {banks.map((bank) => (
          <BankFold key={bank.id} bank={bank} />
        ))}
      </div>
      </BoardDetail>
      </div>

      <div className="board-part">
      <PanelTitle as="h3" concept="searchedNotFound" className="section-gap">
        {tr("Buscado y no encontrado", "Searched and not found")}
      </PanelTitle>
      <BoardDetail
        label={tr(`${formatNumber(testbeds.not_found.length)} ${testbeds.not_found.length === 1 ? "búsqueda" : "búsquedas"} sin resultado`, `${formatNumber(testbeds.not_found.length)} ${testbeds.not_found.length === 1 ? "search" : "searches"} with no result`)}
      >
        <ul className="evidence">
          {testbeds.not_found.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </BoardDetail>
      </div>
      </div>
      </div>
    </section>
  );
}

/**
 * Cuántas filas hay de cada entorno de evidencia, con la marca de su plegable (el gris de «no
 * disponible» si ninguno lo cubre): lo que cada fila dice cerrada sigue a la vista con las filas
 * tras «Ver detalle». La usan también los conjuntos de datos.
 */
export function ContextTally({ items, label }: { items: readonly Parameters<typeof contextCell>[0][]; label: string }) {
  const contexts = new Map<string, { cell: ReturnType<typeof contextCell>; count: number }>();
  for (const item of items) {
    const cell = contextCell(item);
    const entry = contexts.get(cell.word);
    if (entry === undefined) contexts.set(cell.word, { cell, count: 1 });
    else entry.count += 1;
  }
  if (contexts.size === 0) return null;
  return (
    <ul className="board-tally" aria-label={label}>
      {[...contexts].map(([word, { cell, count }]) => (
        <li key={word} className="ref-pill board-pill">
          <span>
            <MarkOf mark={cell.mark}>{word}</MarkOf> <span className="num">{formatNumber(count)}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

/**
 * Cuántas casillas de la matriz RIDGE hay de cada estado, con la marca y la palabra del backend; la
 * casilla que falta cuenta como «no se sabe», igual que la pinta la tabla.
 */
function RidgeTally({ testbeds }: { testbeds: Testbeds }) {
  const counts = new Map<string, number>();
  for (const bank of testbeds.banks) {
    for (const hazard of testbeds.ridge.hazards) {
      const status = bank.ridge.find((item) => item.hazard === hazard.id)?.status ?? "unknown";
      counts.set(status, (counts.get(status) ?? 0) + 1);
    }
  }
  const words = new Map(testbeds.ridge.statuses.map((status) => [status.id, status.text]));
  return (
    <ul className="board-tally" aria-label={tr("Casillas de la matriz RIDGE por estado", "RIDGE matrix cells by status")}>
      {[...counts].map(([status, count]) => (
        <li key={status} className="ref-pill board-pill">
          <span>
            <MarkOf mark={ridgeStatusMark(status)}>{words.get(status) ?? status}</MarkOf>{" "}
            <span className="num">{formatNumber(count)}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

/**
 * Un banco, plegado: el signo del plegable es su entorno de evidencia (el dibujo de la procedencia,
 * o el gris de «no disponible» si ninguno lo cubre), y dentro lo que reproduce, lo que deja fuera,
 * la validación que permitiría y para qué le serviría a EMMA.
 */
function BankFold({ bank }: { bank: Testbed }) {
  const context = contextCell(bank);
  const validation = validationMark(bank.validation);
  return (
    <Fold data-ui="testbed"
      mark={context.mark}
      aria-label={tr(`Banco ${bank.name}`, `Testbed ${bank.name}`)}
      label={
        <>
          <strong>{bank.name}</strong>
          {bank.full_name !== null && <span lang="en"> ({bank.full_name})</span>}
          <span className="secondary"> · {context.word}</span>
        </>
      }
    >
      <dl className="kv">
        <FieldLabel as="dt" concept="provenance">
          {tr("Entorno de evidencia", "Evidence setting")}
        </FieldLabel>
        <dd>
          <MarkOf mark={context.mark}>{context.word}</MarkOf>
          <div className="secondary">{bank.context_basis}</div>
        </dd>
        <FieldLabel as="dt" concept="zone">
          {tr("Dónde", "Where")}
        </FieldLabel>
        <dd>{bank.where}</dd>
        <FieldLabel as="dt" pictogram={validation.pictogram ?? TESTBEDS_PICTOGRAM}>
          {tr("Validación", "Validation")}
        </FieldLabel>
        <dd>
          <MarkOf mark={validation}>{bank.validation_text}</MarkOf>
        </dd>
        <FieldLabel as="dt" concept="sourceText">
          {tr("Qué reproduce", "What it reproduces")}
        </FieldLabel>
        <dd>
          <ul className="evidence mt-0">
            {bank.reproduces.map((item) => (
              <li key={`${item.ref}:${item.quote}`}>
                <QuoteLine item={item} />
              </li>
            ))}
          </ul>
        </dd>
        <FieldLabel as="dt" concept="decline">
          {tr("Qué deja fuera", "What it leaves out")}
        </FieldLabel>
        <dd>
          <ul className="evidence mt-0">
            {bank.leaves_out.map((item) => (
              <li key={item.what}>
                {item.what} — <MarkOf mark={leftOutMark(item)}>{item.basis_text}</MarkOf>
                {item.why !== null && <div className="secondary">{item.why}</div>}
                {item.cited !== null && (
                  <div>
                    <QuoteLine item={item.cited} />
                  </div>
                )}
              </li>
            ))}
          </ul>
        </dd>
        {bank.columns.map((column) => (
          <div key={column.id} className="contents">
            <FieldLabel as="dt" pictogram={columnPictogram(column.id)}>
              {column.label}
            </FieldLabel>
            <dd>
              {column.quotes.length > 0 ? (
                <ul className="evidence mt-0">
                  {column.quotes.map((item) => (
                    <li key={`${item.ref}:${item.quote}`}>
                      <QuoteLine item={item} />
                    </li>
                  ))}
                </ul>
              ) : (
                <>
                  <MarkOf mark={NOT_FOUND_MARK}>{column.not_found ?? ""}</MarkOf>
                  <div className="secondary">
                    {tr("buscado el", "searched on")} <span className="num">{formatSourceDate(column.read_on)}</span>
                  </div>
                </>
              )}
            </dd>
          </div>
        ))}
        <FieldLabel as="dt" concept="inferred">
          {tr("Peligros RIDGE", "RIDGE hazards")}
        </FieldLabel>
        <dd>
          <ul className="evidence mt-0">
            {bank.ridge.map((cell) => (
              <li key={cell.hazard}>
                <RidgeLine cell={cell} />
              </li>
            ))}
          </ul>
          <div className="secondary">
            {tr("hecha el", "made on")} <span className="num">{formatSourceDate(bank.ridge_read_on)}</span>
          </div>
        </dd>
        {bank.variables_kb !== null && (
          <>
            <FieldLabel as="dt" concept="measure">
              {tr("Variables (base de conocimiento §3.1)", "Variables (knowledge base §3.1)")}
            </FieldLabel>
            <dd>{bank.variables_kb}</dd>
          </>
        )}
        <FieldLabel as="dt" concept="systems">
          {tr("Para EMMA", "For EMMA")}
        </FieldLabel>
        <dd>{bank.emma_use}</dd>
      </dl>
    </Fold>
  );
}

/**
 * Un peligro RIDGE de un banco: el dibujo y el nombre del peligro y qué reproduce de él; debajo,
 * cómo se sabe (lo nombra una página del banco o lo deduce EMMA) con el motivo, y la frase. Todo del
 * backend. La base va en su propia línea porque la mitad derecha de «en parte» y el medio punto de
 * «lo deduce EMMA», uno junto al otro, solo se distinguían por la palabra.
 */
function RidgeLine({ cell }: { cell: TestbedRidgeCell }) {
  return (
    <>
      <MarkOf mark={mark(ridgePictogram(cell.hazard), null)}>{cell.hazard_display}</MarkOf> —{" "}
      <MarkOf mark={ridgeStatusMark(cell.status)}>{cell.status_text}</MarkOf>
      <div className="secondary">
        <MarkOf mark={leftOutMark(cell)}>{cell.basis_text}</MarkOf>
        {cell.why !== null && <>: {cell.why}</>}
      </div>
      {cell.cited !== null && (
        <div>
          <QuoteLine item={cell.cited} />
        </div>
      )}
    </>
  );
}

/**
 * Una frase de la fuente, en su idioma, con su ficha: de quién es, dónde está en la página, de
 * cuándo es y cuándo se leyó. La fecha de la fuente va en la cita del registro (`source`: el
 * registro exige que el año de la ficha esté en ella), así que no se repite aparte. Una fecha que
 * la página no muestra se dice sin verificar, en cian.
 */
function QuoteLine({ item }: { item: TestbedQuote }) {
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
