import { useEffect, useState } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { useLook } from "../components/BoardOnly";
import { FieldLabel } from "../components/FieldLabel";
import { Fold } from "../components/Fold";
import { MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { SourceFacts } from "../evidence/SourceFacts";
import { SourceGrade } from "../evidence/SourceGrade";
import { type ContextSource, type ContextSourceList, type ContextSources, contextSourcesApi } from "../lib/api";
import { formatDay, formatNumber } from "../lib/format";
import { tr } from "../lib/i18n";
import { LOADING_MARK, MISSING_MARK, type RequestOutcome, requestOutcome } from "../lib/marks";
import { namedLists, sortedSources, statusCounts, statusMark } from "./contextSources";

const TITLE = tr("Fuentes del contexto", "Context sources");

/**
 * Qué fuentes del contexto del equipo se leyeron, cuáles no y para qué las tiene EMMA
 * (especificación §17, `GET /api/context-sources`).
 *
 * Por qué existe: la ruta no tenía vista, y una lista de fuentes que nadie ve acaba citándose como
 * si estuviera leída. Aquí lo no leído va el primero y con su motivo. No es una alarma: va en cian,
 * el dato ausente de F.5-1.
 *
 * Todo el texto viene de la ruta; aquí solo hay rótulos de inventario y la marca de cada estado
 * (`contextSources.ts`). Inventario: no interviene en el estado de la tripulación.
 *
 * Tablero (2026-11-07): bajo la concha de la maqueta la cuenta por estado pasa de la frase a
 * píldoras, cada una con la marca y la palabra de su estado; es la misma cuenta en otra forma, así
 * que sustituye a la frase (`useLook`). La fecha de lectura se queda en su línea.
 */
export function ContextSourcesPanel() {
  const [body, setBody] = useState<ContextSources | null>(null);
  const [failure, setFailure] = useState<RequestOutcome | null>(null);

  useEffect(() => {
    let current = true;
    contextSourcesApi
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
      <section data-ui="context-sources" className="panel" aria-label={TITLE}>
        <PanelTitle concept="sourceText">{TITLE}</PanelTitle>
        {failure === null ? (
          <p className="secondary">
            <MarkOf mark={LOADING_MARK}>{tr("Consultando las fuentes…", "Loading the sources…")}</MarkOf>
          </p>
        ) : (
          <p>
            <MarkOf mark={failure.mark}>{tr("Fuentes del contexto no disponibles:", "Context sources unavailable:")} {failure.text}</MarkOf>
          </p>
        )}
      </section>
    );
  }
  return <ContextSourcesView body={body} />;
}

/** Las fuentes ya recibidas. Aparte del que consulta para poder pintarlas en las pruebas sin red. */
export function ContextSourcesView({ body }: { body: ContextSources }) {
  const board = useLook() === "reference";
  const counts = statusCounts(body.sources);
  return (
    <section data-ui="context-sources" className="panel" aria-label={TITLE}>
      <PanelTitle concept="sourceText">{TITLE}</PanelTitle>
      {/* Lote «muestra» (2026-11-08): la nota, tras «Ver detalle» en el tablero. */}
      <BoardDetail label={tr("de dónde salen", "where they come from")}>
        <p className="secondary">{body.note}</p>
      </BoardDetail>
      <p>
        {tr("Lectura del", "Reading of")} <span className="num">{formatDay(body.read_on)}</span>
        {!board &&
          counts.map((item) => (
            <span key={item.status}>
              {" · "}
              <MarkOf mark={statusMark(item.status)}>{item.text}</MarkOf>:{" "}
              <span className="num">{formatNumber(item.count)}</span>
            </span>
          ))}
      </p>
      {board && counts.length > 0 && (
        <ul className="board-tally" aria-label={tr("Fuentes por estado", "Sources by status")}>
          <li className="ref-pill board-pill">
            <span className="num">{formatNumber(body.sources.length)}</span>{" "}
            {body.sources.length === 1 ? tr("fuente", "source") : tr("fuentes", "sources")}
          </li>
          {counts.map((item) => {
            const shown = statusMark(item.status);
            return (
              <li key={item.status} className="ref-pill board-pill">
                <MarkOf mark={shown}>{item.text}</MarkOf> <span className="num">{formatNumber(item.count)}</span>
              </li>
            );
          })}
        </ul>
      )}
      {/* Lote «muestra», segunda ronda (2026-11-08): las filas de fuente iban en baldosas dentro de
          una caja con barra de desplazamiento. Ahora, tras «Ver detalle» (plegables con `data-ui`: el
          asistente abre el detalle para llegar a ellos), sin caja; cuántas hay de cada estado, con su
          marca (el cian de lo sin leer incluido), sigue en las píldoras de arriba. */}
      <BoardDetail label={tr(`${formatNumber(body.sources.length)} ${body.sources.length === 1 ? "fuente" : "fuentes"}, una por fila`, `${formatNumber(body.sources.length)} ${body.sources.length === 1 ? "source" : "sources"}, one per row`)}>
        <div className="context-folds">
          {sortedSources(body.sources).map((source) => (
            <SourceFold key={source.ref} source={source} lists={body.lists} />
          ))}
        </div>
      </BoardDetail>
    </section>
  );
}

/** Una fuente, plegada: su título y su estado en el rótulo; dentro, de dónde sale y qué se leyó. */
function SourceFold({ source, lists }: { source: ContextSource; lists: readonly ContextSourceList[] }) {
  // El signo del plegable es el de su estado, no uno común: cerrado, una fuente sin leer no abre
  // su rótulo con el libro de lo leído (`Fold`, «la marca de un estado»).
  const shown = statusMark(source.status);
  return (
    <Fold data-ui="context-source"
      mark={shown}
      aria-label={tr(`Fuente ${source.card.title}`, `Source ${source.card.title}`)}
      label={
        <>
          <strong>{source.card.title}</strong> · <span className={shown.className}>{source.status_text}</span>
        </>
      }
    >
      <dl className="kv">
        {source.not_read !== null && (
          <>
            <FieldLabel as="dt" concept="searchedNotFound">
              {tr("Sin leer", "Not read")}
            </FieldLabel>
            <dd>
              <MarkOf mark={MISSING_MARK}>{source.not_read}</MarkOf>
            </dd>
          </>
        )}
        {source.listed_as !== null && (
          <>
            <FieldLabel as="dt" concept="document">
              {tr("Lista del equipo", "Team list")}
            </FieldLabel>
            <dd>
              {source.listed_as}
              {namedLists(source.lists, lists).map((list) => (
                <div key={typeof list === "string" ? list : list.id} className="secondary">
                  {typeof list === "string" ? list : `${list.title} · ${list.document} ${list.section}`}
                </div>
              ))}
            </dd>
          </>
        )}
        {source.why_added !== null && (
          <>
            <FieldLabel as="dt" concept="document">
              {tr("Por qué se añadió", "Why it was added")}
            </FieldLabel>
            <dd>{source.why_added}</dd>
          </>
        )}
        <FieldLabel as="dt" concept="whyEmma">
          {tr("Para qué en EMMA", "What for in EMMA")}
        </FieldLabel>
        <dd>{source.emma_use}</dd>
      </dl>
      <p className="secondary">{source.card.source}</p>
      <SourceGrade grade={source.card.grade} />
      <SourceFacts source={source.card} />
      {source.card.url === null ? (
        <p>
          <MarkOf mark={MISSING_MARK}>{tr("sin dirección en la ficha", "no address in the record")}</MarkOf>
        </p>
      ) : (
        <p className="secondary">
          <a className="num url" href={source.card.url} target="_blank" rel="noreferrer">
            {source.card.url}
          </a>
        </p>
      )}
      {source.card.notes !== null && <p className="secondary">{source.card.notes}</p>}
    </Fold>
  );
}
