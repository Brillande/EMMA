import { type ReactNode, useEffect, useState } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { BoardOnly, useLook } from "../components/BoardOnly";
import { DomainName } from "../components/DomainName";
import { FieldLabel } from "../components/FieldLabel";
import { Fold } from "../components/Fold";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { StatTile } from "../components/StatTile";
import {
  type Framework,
  type GapStatus,
  type ReadBlock,
  type ReadCoverage,
  type ReadQuestion,
  type ReadSources,
  frameworkApi,
} from "../lib/api";
import { formatNumber, formatSourceDate } from "../lib/format";
import { tr } from "../lib/i18n";
import {
  LOADING_MARK,
  OK_MARK,
  type RequestOutcome,
  UNAVAILABLE_MARK,
  requestOutcome,
} from "../lib/marks";
import type { Sign } from "../lib/uiMarks";
import { CredibilityView } from "./CredibilityView";
import { RisksPanel } from "./RisksPanel";
import {
  UNREAD_STYLE,
  countByStatus,
  coverageDisplay,
  extentStyle,
  gapRows,
  gapStatusStyle,
  placeBlocks,
  ridgeGroups,
  ridgePictogram,
  routeText,
  statusStyle,
} from "./framework";
import { coverageMark, coverageRows } from "./hrpCoverageMarks";

/**
 * El marco de NASA en que se inscribe EMMA y las hipótesis de su diseño, a la vista.
 *
 * `GET /api/framework` servía desde la segunda ronda los dos huecos del MDA de los que parte el
 * diseño, la relación con el IMM y el peligro RIDGE de cada dominio, y ninguna pantalla lo
 * enseñaba. Y las siete hipótesis de la base de conocimiento del equipo tenían pieza hecha sin
 * que nada dijera que siguen siendo hipótesis.
 *
 * Todo el texto viene del backend: el nombre, el enunciado y el estado leído de cada hueco (desde
 * la undécima ronda, junto al nombre: ninguno de los dos figura hoy abierto), el de cada
 * hipótesis, la frase de su estado, lo que EMMA no demuestra, el «sin leer» de un anclaje y,
 * desde la décima ronda, lo leído en las fuentes oficiales con su frase literal y su cita. Aquí
 * solo hay rótulos de inventario, y junto a cada palabra su pictograma (`framework.ts`,
 * `lib/marks.ts`): el peligro RIDGE con su dibujo y cada dominio con el suyo. No es un estado
 * clínico: nada de este panel decide sobre la tripulación, y ningún estado de hipótesis es
 * «probada».
 *
 * Desde la segunda pasada (§5.33.6) cada apartado lleva su signo: los conceptos de
 * `lib/uiMarks.ts` donde los hay (lo leído, sin leer, el estado, los documentos) y, para lo que
 * solo nombra Tierra, un dibujo de `icons/sets/ground.ts`: el marco abierto de los huecos, el dado
 * del IMM, el pentágono de las cinco amenazas del RIDGE y la interrogación de las hipótesis.
 *
 * Tablero (2026-11-07): bajo la concha de la maqueta, arriba, cuántos documentos de NASA se leyeron
 * y cuántas hipótesis hay (`StatTile`), una píldora por alcance de lectura con su marca (el cian de
 * lo leído solo por su resumen) y una por hueco del MDA con el estado leído, y el del hueco en que
 * se fusionó. Resumen de lo que va debajo, que no cambia (`BoardOnly`).
 */
export function FrameworkPanel() {
  const [framework, setFramework] = useState<Framework | null>(null);
  const [error, setError] = useState<RequestOutcome | null>(null);

  useEffect(() => {
    let current = true;
    frameworkApi
      .get()
      .then((body) => {
        if (current) setFramework(body);
      })
      .catch((reason: unknown) => {
        if (current) setError(requestOutcome(reason));
      });
    return () => {
      current = false;
    };
  }, []);

  if (framework === null) {
    return (
      <section data-ui="framework" className="panel" aria-label={tr("Marco de NASA e hipótesis de diseño", "NASA framework and design hypotheses")}>
        <PanelTitle concept="nasaFramework">{tr("Marco de NASA e hipótesis de diseño", "NASA framework and design hypotheses")}</PanelTitle>
        {error === null ? (
          <p className="secondary">
            <MarkOf mark={LOADING_MARK}>{tr("Consultando el marco…", "Loading the framework…")}</MarkOf>
          </p>
        ) : (
          <p>
            <MarkOf mark={error.mark}>{tr("Inventario no disponible:", "Inventory unavailable:")} {error.text}</MarkOf>
          </p>
        )}
      </section>
    );
  }

  return <FrameworkView framework={framework} />;
}

/** El marco ya consultado; aparte para poder pintarlo sin red en las pruebas. */
export function FrameworkView({ framework }: { framework: Framework }) {
  const board = useLook() === "reference";
  const { exmc_gaps: gaps, imm, design_hypotheses: inventory, read_sources: read } = framework;
  const placed = placeBlocks(read);
  const coverages = coverageDisplay(read);
  const rows = gapRows(gaps);
  const ridge = ridgeGroups(framework.ridge);
  // Cuarta ronda (R4-8): en el tablero, el recuento por estado en píldoras, como el de los riesgos y
  // el del RIDGE: la lista de viñetas partía cada estado en dos renglones y hacía de esta columna la
  // más alta del marco. La palabra y la marca de cada estado son las mismas.
  const statusCount = board ? (
    <ul className="board-tally" aria-label={tr("Hipótesis por estado", "Hypotheses by status")}>
      {countByStatus(inventory).map((row) => (
        <li key={row.id} className="ref-pill board-pill">
          <span>
            <MarkOf mark={statusStyle(row.id)}>{row.text}</MarkOf> <span className="num">{formatNumber(row.count)}</span>
          </span>
        </li>
      ))}
    </ul>
  ) : (
    <ul className="evidence" aria-label={tr("Hipótesis por estado", "Hypotheses by status")}>
      {countByStatus(inventory).map((row) => (
        <li key={row.id}>
          <MarkOf mark={statusStyle(row.id)}>{row.text}</MarkOf>{" "}
          <span className="num">({formatNumber(row.count)})</span>
        </li>
      ))}
    </ul>
  );

  const hypotheses = (
        <div className="framework-part">
          <PanelTitle as="h3" pictogram="question-circle" className="section-gap">
            {tr("Hipótesis de diseño", "Design hypotheses")}
          </PanelTitle>
          {/* El recuento por estado, a la vista; de dónde salen y cada hipótesis con su estado y su
              enunciado, tras un solo «Ver detalle» (segunda ronda, 2026-11-08). En la clásica, el
              mismo orden de siempre. */}
          {board && statusCount}
          <BoardDetail label={tr(`de dónde salen y ${formatNumber(inventory.hypotheses.length)} hipótesis`, `where they come from and ${formatNumber(inventory.hypotheses.length)} ${inventory.hypotheses.length === 1 ? "hypothesis" : "hypotheses"}`)}>
            <p>{inventory.note}</p>
            <p className="secondary">
              <span className="num">{inventory.source.document}</span> §{inventory.source.section},{" "}
              «{inventory.source.title}»
            </p>
          {!board && statusCount}

      {inventory.hypotheses.map((item) => (
        <article key={item.id} className="mt-3" aria-label={tr(`Hipótesis ${item.label}`, `Hypothesis ${item.label}`)}>
          {/* En el tablero, la cabecera de la ficha: la hipótesis y su estado, siempre a la vista. */}
          <BoardOnly>
            <p className="hypothesis-head">
              <strong className="num">{item.label}</strong>{" "}
              <MarkOf mark={statusStyle(item.status)}>{item.status_text}</MarkOf>
            </p>
          </BoardOnly>
          <BoardDetail label={tr("enunciado", "statement")}>
          <p>
            <strong className="num">{item.label}</strong> {item.statement}
          </p>
          <dl className="kv">
            <FieldLabel as="dt" concept="state">
              {tr("Estado", "Status")}
            </FieldLabel>
            <dd>
              <MarkOf mark={statusStyle(item.status)}>{item.status_text}</MarkOf>
            </dd>
            {item.real_data !== null && (
              <FrameworkRow term={tr("Datos reales y alcance", "Real data and scope")} sign={{ concept: "evidence" }}>
                {item.real_data}
              </FrameworkRow>
            )}
            <FieldLabel as="dt" concept="systems">
              {tr("Piezas de EMMA", "EMMA components")}
            </FieldLabel>
            <dd>
              {item.touches.length === 0 ? (
                <Mark pictogram="slash-circle" color="gray">
                  {tr("ninguna", "none")}
                </Mark>
              ) : (
                <ul className="evidence mt-0">
                  {item.touches.map((touch) => {
                    const route = routeText(touch);
                    return (
                      <li key={`${touch.module}:${route ?? ""}`}>
                        <span className="num">{touch.module}</span>
                        {route !== null && <span className="secondary num"> · {route}</span>}
                        <div>{touch.what}</div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </dd>
            {item.scenario !== null && (
              <FrameworkRow term={tr("Escenario simulado", "Simulated scenario")} sign={{ concept: "changeScenario" }}>
                <span className="num">{item.scenario}</span>
              </FrameworkRow>
            )}
            {item.documents.length > 0 && (
              <FrameworkRow term={tr("Documentos", "Documents")} sign={{ concept: "document" }}>
                <span className="num">{item.documents.join(", ")}</span>
              </FrameworkRow>
            )}
            <FrameworkRow term={tr("EMMA no demuestra", "EMMA does not demonstrate")} sign={{ concept: "decline" }}>
              {item.not_demonstrated}
            </FrameworkRow>
          </dl>
          </BoardDetail>
        </article>
      ))}
          </BoardDetail>
        </div>
  );

  // Quinta ronda (R5-9, 2026-11-09): cada apartado, una constante, para repartirlos en el tablero en
  // cuatro columnas y dejar la clásica en su orden de siempre.
  const gapsPart = (
    <div className="framework-part">
      <PanelTitle as="h3" pictogram="square-open">
        {tr("Huecos del MDA (ExMC): enunciado de 2020 y estado hoy", "MDA gaps (ExMC): 2020 statement and status today")}
      </PanelTitle>
      {/* Segunda ronda (2026-11-08): el enunciado de cada hueco y lo leído de ellos, tras un solo
          «Ver detalle»; el estado de cada hueco (abierto, cerrado, fusionado) sigue en las píldoras
          de arriba, que no se pliegan. */}
      <BoardDetail label={tr("enunciado, estado y lo leído", "statement, status and what was read")}>
        <p>{gaps.note}</p>
        <p className="secondary">
          {gaps.source} · <span className="num url">{gaps.url}</span>
        </p>
        <dl className="kv">
          {rows.map((row) => (
            <FrameworkRow key={row.key} term={row.label}>
              <GapStatusLine status={row.status} />
              {row.mergedInto !== null && (
                <div>
                  <Mark pictogram="arrow-right">
                    <span className="num">{row.mergedInto.id}</span>
                  </Mark>
                  : <GapStatusLine status={row.mergedInto} />
                </div>
              )}
              <q lang="en">{row.gap}</q>
              <div>{row.emma}</div>
            </FrameworkRow>
          ))}
        </dl>
        {placed.gaps !== null && <ReadBlockView block={placed.gaps} coverages={coverages} />}
      </BoardDetail>
    </div>
  );
  const immPart = (
    <div className="framework-part">
      <PanelTitle as="h3" pictogram="dice" className="section-gap">
        Integrated Medical Model (IMM)
      </PanelTitle>
      <BoardDetail label={tr("qué es y lo leído", "what it is and what was read")}>
        <p>{imm.what}</p>
        <p>{imm.not_duplicated}</p>
        <p className="secondary num url">{imm.url}</p>
        {placed.imm !== null && <ReadBlockView block={placed.imm} coverages={coverages} />}
        {placed.medprat !== null && <ReadBlockView block={placed.medprat} coverages={coverages} />}
      </BoardDetail>
    </div>
  );
  const credibilityPart = (
    <div className="framework-part">
      {framework.credibility !== null ? (
        <CredibilityView credibility={framework.credibility} />
      ) : (
        <p className="section-gap">
          <MarkOf mark={UNAVAILABLE_MARK}>{tr("Credibilidad de cada capa: no disponible", "Credibility of each layer: unavailable")}</MarkOf>
        </p>
      )}
    </div>
  );
  const readPart = (
    <div className="framework-part">
      <PanelTitle as="h3" concept="sourceText" className="section-gap">
        {tr("Lo leído en las fuentes de NASA", "What was read in NASA's sources")}
      </PanelTitle>
      <BoardDetail
        label={tr(`${formatNumber(read.sources.length)} ${read.sources.length === 1 ? "documento leído" : "documentos leídos"}`, `${formatNumber(read.sources.length)} ${read.sources.length === 1 ? "document read" : "documents read"}`)}
      >
        <p>{read.note}</p>
        <ul className="evidence" aria-label={tr("Documentos leídos y cuánto de cada uno", "Documents read and how much of each")}>
          {read.sources.map((source) => (
            <li key={source.ref}>
              <span lang="en">{source.title}</span> —{" "}
              <MarkOf mark={extentStyle(source.extent)}>{source.extent_text}</MarkOf> ·{" "}
              <span className="num">{formatSourceDate(source.read_on)}</span>
              <div className="secondary">{source.what}</div>
            </li>
          ))}
        </ul>
        {/* Cada bloque leído, con su propio «Ver detalle» dentro de este (segunda ronda): el
            recuento por alcance de lectura va arriba, en las píldoras. */}
        {placed.rest.map((block) => (
          <ReadBlockView key={block.id} block={block} coverages={coverages} />
        ))}
      </BoardDetail>
    </div>
  );
  const ridgePart = (
    <div className="framework-part">
      <PanelTitle as="h3" pictogram="pentagon" className="section-gap">
        {tr("Peligro RIDGE de cada dominio", "RIDGE hazard of each domain")}
      </PanelTitle>
      {/* En el tablero, cuántos dominios caen en cada peligro; la lista, en el detalle. */}
      <BoardOnly>
        <ul className="board-tally" aria-label={tr("Dominios por peligro RIDGE", "Domains by RIDGE hazard")}>
          {ridge.map((group) => (
            <li key={group.hazard} className="ref-pill board-pill">
              <Mark pictogram={ridgePictogram(group.hazard)}>{group.display}</Mark>{" "}
              <span className="num">{formatNumber(group.domains.length)}</span>
            </li>
          ))}
        </ul>
      </BoardOnly>
      <BoardDetail label={tr("dominios de cada peligro", "domains of each hazard")}>
        <dl className="kv">
          {ridge.map((group) => (
            <FrameworkRow
              key={group.hazard}
              term={<Mark pictogram={ridgePictogram(group.hazard)}>{group.display}</Mark>}
            >
              {group.domains.map((domain, index) => (
                <span key={domain}>
                  {index > 0 && " · "}
                  <DomainName domain={domain} />
                </span>
              ))}
            </FrameworkRow>
          ))}
        </dl>
      </BoardDetail>
    </div>
  );
  const risksPart = (
    <div className="framework-part">
      <RisksPanel />
    </div>
  );
  const anchorsPart = (
    <div className="framework-part">
      <PanelTitle as="h3" concept="withoutReading" className="section-gap">
        {tr("Anclajes de la especificación sin leer", "Specification anchors not read")}
      </PanelTitle>
      {inventory.unread_anchors.length === 0 ? (
        <p className="secondary">
          <MarkOf mark={OK_MARK}>
            {tr("Ninguno declarado. Lo que queda sin leer de cada fuente va en su bloque, arriba.", "None declared. What remains unread of each source is in its block, above.")}
          </MarkOf>
        </p>
      ) : (
        inventory.unread_anchors.map((anchor) => (
          <div key={anchor.anchor} className="mt-2">
            <p>
              <strong>{anchor.anchor}</strong> — <MarkOf mark={UNREAD_STYLE}>{anchor.status_text}</MarkOf>
            </p>
            <BoardDetail label={tr("dónde figura y sus referencias", "where it is listed and its references")}>
              <p className="secondary num url">{anchor.listed_in}</p>
              <ul className="evidence">
                {anchor.references.map((reference) => (
                  <li key={reference.ntrs}>
                    <span className="num">NTRS {reference.ntrs}</span> — <span lang="en">{reference.title}</span>
                    <div className="secondary num url">{reference.url}</div>
                  </li>
                ))}
              </ul>
            </BoardDetail>
          </div>
        ))
      )}
    </div>
  );

  return (
    <section data-ui="framework" className="panel" aria-label={tr("Marco de NASA e hipótesis de diseño", "NASA framework and design hypotheses")}>
      <PanelTitle concept="nasaFramework">{tr("Marco de NASA e hipótesis de diseño", "NASA framework and design hypotheses")}</PanelTitle>
      <p className="secondary mb-2">
        {tr(
          "Inventario: de dónde parte el diseño y qué sigue siendo hipótesis. No interviene en el estado de la tripulación ni en ninguna alerta.",
          "Inventory: where the design starts from and what is still a hypothesis. It plays no part in the crew's status or in any alert.",
        )}
      </p>
      <BoardOnly>
        <div className="board-row framework-board">
          <div className="board-stats" role="group" aria-label={tr("Fuentes leídas e hipótesis", "Sources read and hypotheses")}>
            <StatTile concept="sourceText" label={tr("Documentos leídos", "Documents read")} value={read.sources.length} />
            <StatTile pictogram="question-circle" label={tr("Hipótesis", "Hypotheses")} value={inventory.hypotheses.length} />
          </div>
          <ExtentTally read={read} />
          <ul className="board-tally" aria-label={tr("Huecos del MDA: estado hoy", "MDA gaps: status today")}>
            {rows.map((row) => {
              const shown = gapStatusStyle(row.status.status);
              return (
                <li key={row.key} className="ref-pill board-pill">
                  {/* Un solo hijo: la píldora es flexible y partía la frase en columnas. */}
                  <span>
                    {row.label}: <MarkOf mark={shown}>{row.status.status_text}</MarkOf>
                    {row.mergedInto !== null && (
                      <>
                        {" "}
                        <Mark pictogram="arrow-right">
                          <span className="num">{row.mergedInto.id}</span>
                        </Mark>{" "}
                        <MarkOf mark={gapStatusStyle(row.mergedInto.status)}>{row.mergedInto.status_text}</MarkOf>
                      </>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      </BoardOnly>

      {/* Lote «muestra» (2026-11-08): cada apartado, una baldosa del mosaico (`.framework-part`, en
          columnas bajo la concha de la maqueta); su texto largo, tras «Ver detalle». El estado de
          cada hueco sigue a la vista en las píldoras de arriba. */}
      <div className="framework-parts">
        {board ? (
          <>
            {/* Quinta ronda (R5-9, 2026-11-09): en el tablero, cuatro columnas en vez de tres. Con
                tres, la primera (los huecos, el IMM, la credibilidad y lo leído) y la del centro (el
                RIDGE y las hipótesis) medían 520 px y fijaban el alto del marco, y del de su fila
                con los perfiles; los riesgos, que son el apartado más alto, van solos en la cuarta.
                Orden de lectura: los apartados que solo abren su detalle (huecos, IMM, lo leído), el
                RIDGE y la credibilidad, las hipótesis y los anclajes, los riesgos. */}
            <div className="framework-col">
              {gapsPart}
              {immPart}
              {readPart}
            </div>
            <div className="framework-col">
              {ridgePart}
              {credibilityPart}
            </div>
            <div className="framework-col">
              {hypotheses}
              {anchorsPart}
            </div>
            <div className="framework-col">{risksPart}</div>
          </>
        ) : (
          <>
            <div className="framework-col">
              {gapsPart}
              {immPart}
              {credibilityPart}
              {readPart}
            </div>
            <div className="framework-col">{ridgePart}</div>
            <div className="framework-col">
              {risksPart}
              {hypotheses}
              {anchorsPart}
            </div>
          </>
        )}
      </div>
    </section>
  );
}

/**
 * Cuántos documentos se leyeron con cada alcance (entero, en parte, solo el resumen), con la marca y
 * la palabra del backend del primero que lo lleva, en el orden en que aparecen.
 */
function ExtentTally({ read }: { read: ReadSources }) {
  const extents = new Map<string, { word: string; count: number }>();
  for (const source of read.sources) {
    const entry = extents.get(source.extent);
    if (entry === undefined) extents.set(source.extent, { word: source.extent_text, count: 1 });
    else entry.count += 1;
  }
  if (extents.size === 0) return null;
  return (
    <ul className="board-tally" aria-label={tr("Documentos leídos, por alcance", "Documents read, by extent")}>
      {[...extents].map(([extent, entry]) => {
        const shown = extentStyle(extent);
        return (
          <li key={extent} className="ref-pill board-pill">
            <MarkOf mark={shown}>{entry.word}</MarkOf> <span className="num">{formatNumber(entry.count)}</span>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Un bloque de lo leído: cada frase en el idioma de la fuente, con dónde está y cuánto se leyó
 * del documento; aparte, lo que hace EMMA; y lo que no se leyó o no se encontró. Si el bloque
 * lleva tabla de cobertura (el CDSS de ExMC, punto por punto), va plegada al final.
 */
function ReadBlockView({ block, coverages }: { block: ReadBlock; coverages: Record<string, string> }) {
  return (
    <article className="mt-3" aria-label={block.title}>
      <PanelTitle as="h4" concept="sourceText">
        {block.title}
      </PanelTitle>
      {/* Las frases, lo que hace EMMA y lo no leído, tras «Ver detalle» en el tablero; el plegable
          «punto por punto» queda fuera, a la vista del asistente. */}
      <BoardDetail
        label={tr(`${formatNumber(block.statements.length)} ${block.statements.length === 1 ? "frase leída" : "frases leídas"}`, `${formatNumber(block.statements.length)} ${block.statements.length === 1 ? "statement read" : "statements read"}`)}
      >
      <p className="secondary">{block.about}</p>
      {block.question && <ReadQuestionView question={block.question} />}
      <ul className="evidence">
        {block.statements.map((item) => (
          <li key={item.id}>
            <strong>{item.label}</strong>
            <div>
              <q lang="en">{item.quote}</q>
            </div>
            {item.note !== null && <div>{item.note}</div>}
            <div className="secondary">
              <span lang="en">{item.source}</span> · {item.where} ·{" "}
              <MarkOf mark={extentStyle(item.extent)}>{item.extent_text}</MarkOf> ·{" "}
              <span className="num">{formatSourceDate(item.read_on)}</span>
            </div>
            <div className="secondary num url">{item.url}</div>
          </li>
        ))}
      </ul>
      <dl className="kv">
        <FrameworkRow term="EMMA" sign={{ concept: "systems" }}>{block.emma}</FrameworkRow>
        <FrameworkRow term={tr("No leído o no encontrado", "Not read or not found")} sign={{ concept: "withoutReading" }}>
          <ul className="evidence mt-0">
            {block.not_read.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </FrameworkRow>
      </dl>
      </BoardDetail>
      {block.coverage !== null && (
        <ReadCoverageView title={block.title} coverage={block.coverage} coverages={coverages} />
      )}
    </article>
  );
}

/**
 * Lo que pide cada frase y qué hace EMMA con ello (decimoséptima ronda): lo que pide, en el
 * idioma de la fuente y letra por letra de su frase; la cobertura con la marca de la de los
 * riesgos del HRP; el motivo y los ficheros, del backend. Los recuentos también son del backend:
 * aquí no se cuenta nada. Va plegada, como la de los riesgos: es larga y es inventario.
 */
function ReadCoverageView({
  title,
  coverage,
  coverages,
}: {
  title: string;
  coverage: ReadCoverage;
  coverages: Record<string, string>;
}) {
  return (
    <Fold data-ui="framework-coverage"
      concept="systems"
      className="mt-2"
      aria-label={tr(`Qué hace EMMA con lo que pide: ${title}`, `What EMMA does with what it asks: ${title}`)}
      label={
        <>
          {tr("Punto por punto: qué hace EMMA", "Point by point: what EMMA does")}{" "}
          <span className="secondary num">· {formatNumber(coverage.rows.length)}</span>
        </>
      }
    >
      <p>{coverage.about}</p>
      <ul className="evidence mt-0" aria-label={tr("Recuento por cobertura", "Count by coverage")}>
        {coverageRows(coverage.counts, coverages).map((row) => (
          <li key={row.coverage}>
            <MarkOf mark={coverageMark(row.coverage)}>{row.display}</MarkOf>{" "}
            <span className="num">{formatNumber(row.count)}</span>
          </li>
        ))}
      </ul>
      <ul className="evidence" aria-label={tr("Cada punto y lo que hace EMMA", "Each point and what EMMA does")}>
        {coverage.rows.map((row) => (
          <li key={`${row.statement}:${row.asks}`}>
            <MarkOf mark={coverageMark(row.coverage)}>{row.coverage_text}</MarkOf> ·{" "}
            <strong>{row.label}</strong>
            <div>
              <q lang="en">{row.asks}</q>
            </div>
            <div>{row.emma}</div>
            {/* Una lista de rutas no tiene dónde partirse con `white-space: pre`: llevaba la
                consola de Tierra a 1623 px, también a 1400 (§5.38.12). Se parte (`.num.wrap`). */}
            {row.files.length > 0 && <div className="secondary num wrap">{row.files.join(" · ")}</div>}
          </li>
        ))}
      </ul>
    </Fold>
  );
}

/**
 * La pregunta que contesta lo leído de un bloque, con la respuesta del backend tal cual y las
 * frases en que se apoya, cada una con la fecha de su documento: se ve que la respuesta mira lo
 * más reciente (decimoquinta ronda: si IMPACT ha sustituido al IMM, y desde cuándo).
 */
function ReadQuestionView({ question }: { question: ReadQuestion }) {
  return (
    <dl className="kv">
      <FrameworkRow term={tr("Pregunta", "Question")} sign={{ concept: "search" }}>
        {question.text}
      </FrameworkRow>
      <FrameworkRow term={tr("Lo que responde lo leído", "What the reading answers")} sign={{ concept: "sourceText" }}>
        <div>{question.answer}</div>
        <ul className="evidence mt-0" aria-label={tr("Frases en que se apoya", "Statements it rests on")}>
          {question.rests_on.map((item) => (
            <li key={item.id}>
              {item.label} · <span className="num">{formatSourceDate(item.date)}</span>
            </li>
          ))}
        </ul>
      </FrameworkRow>
    </dl>
  );
}

/** El estado leído de un hueco: pictograma y frase del backend, de dónde sale y cuándo se leyó. */
function GapStatusLine({ status }: { status: GapStatus }) {
  return (
    <div>
      <MarkOf mark={gapStatusStyle(status.status)}>{status.status_text}</MarkOf>
      <span className="secondary">
        {" "}
        · <span lang="en">{status.source}</span> · {status.where} ·{" "}
        <span className="num">{formatSourceDate(status.read_on)}</span>
      </span>
      <div className="secondary num url">{status.url}</div>
    </div>
  );
}

/**
 * Una fila de lista de definiciones. Con `sign`, el rótulo lleva el signo de su concepto
 * (`FieldLabel`, §5.33.6); sin él, el rótulo ya es una marca o una clave del backend (el nombre de
 * un hueco, el peligro RIDGE con su dibujo) y no lleva otro.
 */
function FrameworkRow({ term, sign, children }: { term: ReactNode; sign?: Sign; children: ReactNode }) {
  return (
    <>
      {sign === undefined ? (
        <dt>{term}</dt>
      ) : (
        <FieldLabel as="dt" {...sign}>
          {term}
        </FieldLabel>
      )}
      <dd>{children}</dd>
    </>
  );
}
