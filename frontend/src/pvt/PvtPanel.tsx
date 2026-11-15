import {
  type CSSProperties,
  Fragment,
  type KeyboardEvent,
  type RefObject,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { BoardDetail } from "../components/BoardDetail";
import { BoardOnly, useLook } from "../components/BoardOnly";
import { Command } from "../components/Command";
import { FieldLabel } from "../components/FieldLabel";
import { Fold } from "../components/Fold";
import { IndicatorName } from "../components/IndicatorName";
import { Mark, MarkOf } from "../components/Mark";
import { ObservationTypeBadge } from "../components/ObservationTypeBadge";
import { PanelTitle } from "../components/PanelTitle";
import { StatTile } from "../components/StatTile";
import { Th } from "../components/Th";
import { Loading, Unavailable } from "../components/Unavailable";
import { positionMark } from "../diary/position";
import {
  type PvtProtocol,
  type PvtRecordedSession,
  type PvtSubmitted,
  pvtApi,
} from "../lib/api";
import { formatNumber, formatUtc } from "../lib/format";
import { hasIndicatorFamily, indicatorFamily } from "../lib/indicatorFamily";
import { EMPTY_MARK, LOADING_MARK, UNKNOWN_PICTOGRAM, recordedByMark, type RequestOutcome, requestOutcome } from "../lib/marks";
import { useOperator } from "../lib/operator";
import { cssVar } from "../lib/palette";
import { type Sign, uiPictogram } from "../lib/uiMarks";
import { divergencesView } from "./divergences";
import { basisMark, phaseMark } from "./marks";
import { type Cited, publishedContext, publishedRows } from "./published";
import {
  type Clock,
  IDLE,
  type Session,
  type Snapshot,
  createSession,
  operatorName,
  resultRows,
  running,
  submission,
  usable,
} from "./session";

/**
 * La prueba PVT, hecha en la consola.
 *
 * El backend ya puntuaba y registraba la prueba, pero ninguna pantalla la pasaba: solo
 * llegaba del simulador. Aquí se pasa. Los parámetros, las instrucciones y el límite de
 * hacerla con un navegador y un teclado los da el backend (`GET /api/pvt/protocol`); al
 * acabar se envían los tiempos tal cual y lo que se enseña es la puntuación que devuelve el
 * backend y lo que quedó en el registro firmado. Bajo el protocolo, plegado, va en qué cuenta
 * EMMA distinto de la fuente leída: quien hace la prueba puede ver que sus lapsos no se cuentan
 * como en lo publicado.
 *
 * Con la prueba va quién está en la consola (el operador, que puede no ser el tripulante del
 * dato): el backend lo firma en cada lectura y lo exige, así que sin nombre no se empieza. De
 * cada prueba ya registrada se enseña con qué fuente entró y quién tecleó, con las palabras
 * del backend; de una que no lo lleva, que no consta.
 *
 * La marca no es una alarma: no usa rojo ni amarillo (tabla F.5-1), no parpadea, y cambia de
 * forma y de palabra además de tono. Se responde con teclado o con un toque, y la prueba se
 * puede abandonar en cualquier momento sin que se envíe nada.
 *
 * Toda forma va junto a su palabra y sale de `pvt/marks.ts` o de las insignias comunes
 * (§5.32): aquí no se escribe ningún trazo ni ningún carácter de forma. Desde la segunda pasada
 * (§5.33.8) los títulos, los plegables, los mandos, las cabeceras y el rótulo de quién está en la
 * consola llevan el signo del vocabulario común (`lib/uiMarks.ts`), y el vacío del registro su
 * marca de dato ausente.
 *
 * Tablero (decisión del usuario, 2026-11-07): bajo la concha de la maqueta, las lecturas de la
 * última prueba del registro (`sessions[0]`, la primera fila de la tabla) van además como fichas
 * con cifra (`LastSessionTiles`), encima de la tabla y solo cuando no hay prueba en curso: la cifra
 * es `value_text`, tal como la escribió el backend, en cursiva si la relectura falló. El recuadro de
 * respuesta no cambia.
 *
 * Una pantalla por sección (2026-11-08): en el tablero van arriba lo que quedó en el registro (las
 * fichas, y la tabla en «Ver detalle»), quién está en la consola y el mando de empezar; el protocolo
 * —identidad, instrucciones, límites, parámetros, lo publicado y las divergencias— en un «Ver
 * detalle» debajo. La clásica conserva su orden.
 */

const browserClock: Clock = {
  now: () => performance.now(),
  setTimer: (run, afterMs) => window.setTimeout(run, afterMs),
  clearTimer: (handle) => window.clearTimeout(handle as number),
};

/**
 * `onRecorded`: tras firmarse una prueba en el registro, para que quien la monta (la tarjeta de
 * pruebas de «Aislamiento») vuelva a leer lo suyo. No toca la prueba ni lo que se envía.
 */
export function PvtPanel({ subject, onRecorded }: { subject: string; onRecorded?: () => void }) {
  const [protocol, setProtocol] = useState<PvtProtocol | null>(null);
  // `null` hasta que el registro se ha leído: una lista vacía es «no hay pruebas», no «aún no se sabe».
  const [sessions, setSessions] = useState<PvtRecordedSession[] | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot>(IDLE);
  const [sending, setSending] = useState(false);
  const [submitted, setSubmitted] = useState<PvtSubmitted | null>(null);
  const [failure, setFailure] = useState<RequestOutcome | null>(null);
  const [unavailable, setUnavailable] = useState<RequestOutcome | null>(null);
  const [operator, setOperator] = useOperator();
  const session = useRef<Session | null>(null);
  const target = useRef<HTMLButtonElement | null>(null);
  // Cambia con el tripulante: una respuesta del backend que llega tarde no se pinta a otro.
  const epoch = useRef(0);

  const loadSessions = useCallback(() => {
    pvtApi
      .sessions(subject)
      .then((recorded) => setSessions(recorded.sessions))
      .catch((reason: unknown) => setUnavailable(requestOutcome(reason)));
  }, [subject]);

  useEffect(() => {
    pvtApi
      .protocol()
      .then((offered) => {
        setProtocol(offered);
        setUnavailable(null);
      })
      .catch((reason: unknown) => setUnavailable(requestOutcome(reason)));
  }, []);
  useEffect(loadSessions, [loadSessions]);

  // Una prueba es de quien estaba en pantalla: al cambiar de tripulante se abandona, y lo
  // anotado no se envía a nombre de otro. Al desmontar, igual.
  useEffect(() => {
    return () => {
      epoch.current += 1;
      session.current?.dispose();
      session.current = null;
      setSessions(null);
      setSnapshot(IDLE);
      setSubmitted(null);
      setFailure(null);
    };
  }, [subject]);

  const send = useCallback(
    (finished: Snapshot) => {
      // El nombre es el de quien empezó la prueba: mientras dura no se puede cambiar.
      const body = submission(finished, subject, operator);
      if (body === null) return;
      const sentAt = epoch.current;
      const mine = () => epoch.current === sentAt;
      setSending(true);
      pvtApi
        .submit(body)
        .then((result) => {
          // Quedó en el registro aunque el panel ya se haya cerrado: quien lo montó lo relee igual.
          onRecorded?.();
          if (mine()) setSubmitted(result);
        })
        // El rechazo del backend se enseña tal cual; lo que quedó o no en el registro lo dice
        // la lista de abajo, que se vuelve a leer.
        .catch((reason: unknown) => {
          if (mine()) setFailure(requestOutcome(reason));
        })
        .finally(() => {
          setSending(false);
          if (mine()) loadSessions();
        });
    },
    [subject, operator, loadSessions, onRecorded],
  );

  const start = () => {
    if (protocol === null || !usable(protocol.session) || sending) return;
    // Sin nombre no se empieza: una prueba acabada que no se puede firmar se perdería.
    if (operatorName(operator) === null) return;
    session.current?.dispose();
    setSubmitted(null);
    setFailure(null);
    const created = createSession(protocol.session, browserClock, Math.random, (next) => {
      setSnapshot(next);
      if (next.phase === "finished") send(next);
    });
    session.current = created;
    created.start();
  };

  const active = running(snapshot);
  // El foco va al recuadro al empezar: desde ahí se responde con el teclado.
  useEffect(() => {
    if (active) target.current?.focus();
  }, [active]);

  return (
    <PvtView
      protocol={protocol}
      sessions={sessions}
      snapshot={snapshot}
      sending={sending}
      submitted={submitted}
      failure={failure}
      unavailable={unavailable}
      operator={operator}
      onOperator={setOperator}
      targetRef={target}
      onStart={start}
      onRespond={() => session.current?.respond()}
      onAbandon={() => session.current?.abandon()}
    />
  );
}

const TITLE = "Prueba PVT";

/** El dibujo de la familia de un indicador, o el de «desconocido» si el registro trae uno nuevo (como `IndicatorName`). */
function familyPictogram(key: string) {
  return hasIndicatorFamily(key) ? indicatorFamily(key) : UNKNOWN_PICTOGRAM;
}

/** Las lecturas de la última prueba del registro, una ficha por indicador, con el dibujo de su familia. */
function LastSessionTiles({ session, stale }: { session: PvtRecordedSession; stale: boolean }) {
  if (session.values.length === 0) return null;
  return (
    <div className="board-stats pvt-board" role="group" aria-label="Última prueba en el registro">
      {session.values.map((value) => (
        <StatTile key={value.key} pictogram={familyPictogram(value.key)} label={value.display_es} value={value.value_text} stale={stale} />
      ))}
    </div>
  );
}

// El recuadro de respuesta. Tonos neutros de la paleta: ni rojo ni amarillo, que son de
// alerta, ni cian o gris, que dicen «sin dato» y «no disponible». Sin animación.
const targetStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  gap: 4,
  width: "100%",
  // Recuadro grande para el dedo (tableta, §5.40): nunca por debajo de 10rem (160 px, más del
  // doble de los 48 px táctiles) y con un tercio del alto que se ve si hay sitio (`--fit-h`, que
  // corrige la vista girada y la ampliación de baja visión). Solo tamaño: sin transición ni nada
  // que se anime, así no añade latencia a la respuesta.
  minHeight: "clamp(10rem, calc(35 * var(--fit-h, 1vh)), 22rem)",
  margin: "8px 0",
  font: "inherit",
  background: `var(${cssVar("raised")})`,
  border: `1px solid var(${cssVar("line")})`,
  borderRadius: "var(--radius)",
  cursor: "pointer",
  touchAction: "manipulation",
  userSelect: "none",
};

/** Solo pinta. Separado del estado para poder probar lo que se lee en pantalla. */
export function PvtView({
  protocol,
  sessions,
  snapshot,
  sending,
  submitted,
  failure,
  unavailable,
  operator,
  onOperator,
  targetRef,
  onStart,
  onRespond,
  onAbandon,
}: {
  protocol: PvtProtocol | null;
  /** Las pruebas del registro; `null` si aún no se han leído o la lectura falló. */
  sessions: PvtRecordedSession[] | null;
  snapshot: Snapshot;
  sending: boolean;
  submitted: PvtSubmitted | null;
  failure: RequestOutcome | null;
  unavailable: RequestOutcome | null;
  /** Quién está en la consola: se firma con cada lectura de la prueba. */
  operator: string;
  onOperator: (value: string) => void;
  targetRef?: RefObject<HTMLButtonElement | null>;
  onStart: () => void;
  onRespond: () => void;
  onAbandon: () => void;
}) {
  // En el tablero: lo último medido, quién está y el mando de empezar arriba; el protocolo, sus
  // instrucciones y sus fuentes, en un «Ver detalle». En la clásica, todo como siempre.
  const board = useLook() === "reference";
  if (protocol === null) {
    return (
      <section data-ui="pvt" className="panel" aria-label={TITLE}>
        <PanelTitle concept="pvt">{TITLE}</PanelTitle>
        {/* Mientras no llega la primera respuesta el panel lo dice: sin la marca de carga, al
            volver de Tierra se veía vacío durante segundos (§5.33.11). */}
        {unavailable !== null ? (
          <Unavailable outcome={unavailable} />
        ) : (
          <Loading />
        )}
      </section>
    );
  }

  const active = running(snapshot);
  const shown = snapshot.phase === "stimulus";
  const tone = cssVar(shown ? "text" : "textSecondary");
  const unnamed = operatorName(operator) === null;
  const canStart = usable(protocol.session) && !sending && !unnamed;

  const keys = (event: KeyboardEvent) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onAbandon();
    }
  };
  const answer = (event: KeyboardEvent) => {
    if (event.key !== " " && event.key !== "Enter") return;
    // Sin esto, la barra desplaza la página; y una tecla mantenida no es otra respuesta.
    event.preventDefault();
    if (!event.repeat) onRespond();
  };

  // Las piezas del panel en reposo; la clásica las pinta en su orden de siempre.
  const protocolBlock = (
    <>
      {protocol.identity !== undefined && <p>{protocol.identity}</p>}
      <ol>
        {protocol.instructions.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ol>

      <PanelTitle as="h3" concept="limits">
        Límites de esta prueba
      </PanelTitle>
      <ul>
        {protocol.limits.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>

      <div className="quality-table">
        <table className="ledger">
          <thead>
            <tr>
              <Th concept="indicator">Parámetro</Th>
              <Th concept="value">Valor</Th>
              <Th concept="basis">Respaldo</Th>
            </tr>
          </thead>
          <tbody>
            {protocol.parameters.map((item) => {
              // De dónde sale el valor: la forma de su respaldo y la palabra del backend.
              const basis = basisMark(item.basis);
              return (
                <tr key={item.key}>
                  <th scope="row">{item.display}</th>
                  <td className="num">{item.value_text}</td>
                  <td>
                    <Mark pictogram={basis.pictogram} color={basis.color}>
                      {item.basis_display}
                    </Mark>
                    <span className="secondary"> · {item.note}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <PublishedView protocol={protocol} />
      <DivergencesBlock protocol={protocol} />

      <p className="secondary">
        Se firma como{" "}
        <ObservationTypeBadge
          type={protocol.provenance.observation_type}
          context={protocol.provenance.evidence_context}
        />{" "}
        · fuente: {protocol.provenance.source_display} · queda en el registro:{" "}
        {protocol.records.map((item, index) => (
          <Fragment key={item.key}>
            {index > 0 && "; "}
            <IndicatorName indicatorKey={item.key} displayEs={item.display_es} />
          </Fragment>
        ))}
      </p>
      <p className="secondary">{protocol.provenance.effective_note}</p>
      {protocol.notes.map((note) => (
        <p className="secondary" key={note}>
          {note}
        </p>
      ))}
    </>
  );
  const operatorField = (
    <FieldLabel concept="person" className="operator">
      {protocol.recorded_by.label}{" "}
      <input
        value={operator}
        maxLength={64}
        autoComplete="off"
        aria-describedby="pvt-operator-note"
        aria-invalid={unnamed}
        onChange={(event) => onOperator(event.target.value)}
      />
    </FieldLabel>
  );
  const operatorNote = (
    <p className="secondary" id="pvt-operator-note">
      {protocol.recorded_by.note}
    </p>
  );
  const startActions = (
    <div className="measure-actions">
      {/* Mientras se envía, el dibujo es el de «cargando»: el mando cambia de estado. */}
      <Command {...startSign(sending)} type="button" disabled={!canStart} onClick={onStart}>
        {sending ? "Enviando…" : "Empezar la prueba"}
      </Command>
      {unnamed && (
        <span className="secondary">
          Falta el nombre de quien está en la consola: sin él la prueba no se empieza.
        </span>
      )}
    </div>
  );

  // Lo que queda en el registro: en la clásica, al final; en el tablero, arriba (la última prueba
  // en fichas y la tabla en su «Ver detalle»), como la cifra principal del panel.
  const history = (
    <>
      <PanelTitle as="h3" concept="history">
        Últimas pruebas en el registro
      </PanelTitle>
      {/* Sin leer el registro no se dice que esté vacío: lo que falló ya lo dice el aviso. */}
      {sessions === null ? null : sessions.length === 0 ? (
        <p className="secondary">
          <MarkOf mark={EMPTY_MARK}>Ninguna prueba de este tripulante en el registro.</MarkOf>
        </p>
      ) : (
        <>
        {/* Tablero: las lecturas de la última prueba, grandes, encima de la tabla; `sessions[0]`
            es la primera fila. Solo en la concha de la maqueta. */}
        {sessions[0] !== undefined && (
          <BoardOnly>
            <LastSessionTiles session={sessions[0]} stale={unavailable !== null} />
          </BoardOnly>
        )}
        <BoardDetail label="tabla de pruebas">
        <div className="quality-table">
          {sessions.some((item) => item.recorded_by === null) && (
            <p className="secondary">{protocol.recorded_by.legacy_note}</p>
          )}
          <table className="ledger">
            <thead>
              <tr>
                <Th concept="time">Hora</Th>
                <Th concept="value">Lecturas</Th>
                <Th concept="provenance">Procedencia</Th>
                <Th concept="person">{protocol.recorded_by.label}</Th>
                <Th concept="state">En el estado</Th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((item) => (
                // Dos pruebas del mismo instante con fuentes (o tipos) distintos son dos filas.
                <tr key={`${item.effective}|${item.source}|${item.observation_type}`}>
                  <th scope="row" className="num">
                    {formatUtc(new Date(item.effective))}
                  </th>
                  <td>
                    {item.values.map((value) => (
                      <div key={value.key}>
                        <IndicatorName indicatorKey={value.key} displayEs={value.display_es} />:{" "}
                        <span className="num">{value.value_text}</span>
                      </div>
                    ))}
                  </td>
                  <td>
                    <ObservationTypeBadge
                      type={item.observation_type}
                      context={item.evidence_context}
                    />{" "}
                    · {item.source_display}
                  </td>
                  {/* El nombre firmado, o las palabras del backend para quien no consta:
                      gris con el círculo tachado, «no disponible», la misma marca que en el
                      diario y los descriptivos (`recordedByMark`, §5.33.12). */}
                  <td data-recorded-by={item.recorded_by === null ? "missing" : "named"}>
                    <MarkOf mark={recordedByMark(item.recorded_by)}>{item.recorded_by_display}</MarkOf>
                  </td>
                  {/* Dónde cae respecto al estado, con la tabla del diario (`diary/position.ts`):
                      la misma regla del backend, la misma marca. */}
                  <td data-position={item.position}>
                    <MarkOf mark={positionMark(item.position)}>{item.position_note}</MarkOf>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        </BoardDetail>
        </>
      )}
    </>
  );

  return (
    <section data-ui="pvt" className="panel" aria-label={protocol.title}>
      <PanelTitle concept="pvt">{protocol.title}</PanelTitle>

      {!active && !board && (
        <>
          {protocolBlock}
          {operatorField}
          {operatorNote}
          {startActions}
        </>
      )}
      {!active && board && (
        <>
          {history}
          {operatorField}
          {startActions}
          <BoardDetail label="protocolo, instrucciones y fuentes">
            {protocolBlock}
            {operatorNote}
          </BoardDetail>
        </>
      )}

      {active && (
        <div onKeyDown={keys}>
          <p className="secondary">
            Estímulo <span className="num">{formatNumber(snapshot.done + 1)}</span> de{" "}
            <span className="num">{formatNumber(snapshot.total)}</span>
          </p>
          <button
            type="button"
            ref={targetRef}
            data-pvt-target={snapshot.phase}
            aria-label={shown ? "Marca en pantalla: responda" : "Espere a la marca"}
            style={{ ...targetStyle, color: `var(${tone})` }}
            onKeyDown={answer}
            onPointerDown={onRespond}
          >
            {/* Cuadrado vacío mientras se espera, lleno con la marca: la forma grande sobre la
                palabra (`.pvt-target`), y cambia con la fase además del tono. */}
            <Mark pictogram={phaseMark(snapshot.phase).pictogram} className="pvt-target">
              {shown ? "Responda" : "Espere"}
            </Mark>
          </button>
          <p className="secondary" role="status" aria-live="polite">
            {snapshot.premature ? protocol.notices.premature : " "}
          </p>
          <div className="measure-actions">
            <Command concept="abandon" type="button" onClick={onAbandon}>
              Abandonar (Esc)
            </Command>
          </div>
        </div>
      )}

      <div role="status" aria-live="polite">
        {snapshot.phase === "abandoned" && (
          <p className="secondary">
            <Mark pictogram={phaseMark(snapshot.phase).pictogram}>
              {snapshot.abandoned === "no-response"
                ? protocol.notices.no_response
                : protocol.notices.abandoned}
            </Mark>
          </p>
        )}
        {failure !== null && (
          <p role="alert">
            <MarkOf mark={failure.mark}>El backend no confirmó la prueba: {failure.text}</MarkOf>
          </p>
        )}
        {unavailable !== null && <Unavailable outcome={unavailable} />}
      </div>

      {submitted !== null && (
        <>
          <h3>
            <Mark pictogram={phaseMark("finished").pictogram}>Resultado, puntuado por el backend</Mark>
          </h3>
          <div className="quality-table">
            <table className="ledger">
              <tbody>
                {resultRows(protocol, submitted).map((row) => (
                  <tr key={row.key}>
                    <th scope="row">
                      {/* Lo que queda en el registro es un indicador: lleva el dibujo de su familia. */}
                      {row.recordedAs === null ? (
                        row.display
                      ) : (
                        <IndicatorName indicatorKey={row.recordedAs} displayEs={row.display} />
                      )}
                    </th>
                    <td className="num">{row.text}</td>
                    <td className="secondary">
                      {row.recordedAs !== null && <Mark pictogram="check">queda en el registro</Mark>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="secondary">
            Asientos del registro:{" "}
            <span className="num">
              {submitted.recorded.map((index) => formatNumber(index)).join(", ")}
            </span>
          </p>
        </>
      )}

      {!active && !board && history}
    </section>
  );
}

/** Una frase de la fuente, en su idioma, con su sección, su cita y cuándo se leyó. */
function CitedView({ item }: { item: Cited }) {
  return (
    <>
      <div>
        <q lang="en">{item.quote}</q>
      </div>
      <div className="secondary">
        <span lang="en">{item.origin}</span>
        {item.url !== null && <span className="num url"> · {item.url}</span>}
      </div>
    </>
  );
}

/**
 * Lo que dan las fuentes para cada parámetro, versión a versión, y en qué difiere EMMA.
 * Todo el texto es del backend; aquí solo se pinta. Cómo queda el valor de EMMA va con forma
 * (`marks.ts`) y palabra, sin color: no es un estado de alarma. La marca de cada valor
 * («= es el valor de EMMA»…) la redacta el backend y se enseña tal cual.
 */
function PublishedView({ protocol }: { protocol: PvtProtocol }) {
  const rows = publishedRows(protocol.parameters);
  const context = publishedContext(protocol);
  if (rows.length === 0 && context === null) return null;
  return (
    <Fold data-ui="pvt-published" concept="compare" label="Lo publicado y lo que hace EMMA">
      {context !== null && <p className="secondary">{context.note}</p>}
      {rows.map((row) => (
        <article key={row.key} data-pvt-published={row.key} style={{ marginTop: 12 }}>
          <PanelTitle as="h4" concept="indicator">
            {row.display}: <span className="num">{row.emmaValue}</span>
            {row.scores && <span className="secondary"> · entra en la puntuación</span>}
          </PanelTitle>
          <div data-status-mark="">
            <Mark pictogram={row.statusMark.pictogram} color={row.statusMark.color}>
              {row.status}
            </Mark>
          </div>
          <ul className="evidence">
            {row.values.map((value) => (
              <li key={value.key}>
                <strong>{value.variant}</strong>:{" "}
                <span className="num" lang="en">
                  {value.literal}
                </span>{" "}
                {row.comparable && value.marker !== null && (
                  <span className="secondary">{value.marker}</span>
                )}
                <CitedView item={value.cited} />
              </li>
            ))}
            {row.seeAlso.map((item) => (
              <li key={item.id}>
                {item.label}
                <CitedView item={item} />
              </li>
            ))}
          </ul>
          <div>{row.difference}</div>
        </article>
      ))}
      {context !== null && (
        <>
          <ul className="evidence">
            {context.context.map((item) => (
              <li key={item.id}>
                {item.label}
                <CitedView item={item} />
              </li>
            ))}
          </ul>
          <p>{context.outcomesNote}</p>
          <PanelTitle as="h4" concept="sourceText">
            Fuentes leídas
          </PanelTitle>
          <ul className="evidence">
            {context.sources.map((source) => (
              <li key={source.key}>
                <span lang="en">{source.text}</span>
                {source.url !== null && <div className="secondary num url">{source.url}</div>}
              </li>
            ))}
          </ul>
          <PanelTitle as="h4" concept="searchedNotFound">
            Buscado y no encontrado, o no leído
          </PanelTitle>
          <ul className="evidence">
            {context.notFound.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </>
      )}
    </Fold>
  );
}

/**
 * En qué cuenta EMMA distinto de la fuente leída, plegado bajo el protocolo. Todo el texto es
 * del backend; aquí solo se pinta (`divergences.ts`). El estado va con forma y palabra, y solo
 * «sin valor publicado» lleva color: el gris de «no disponible». Ninguna es una alerta.
 */
function DivergencesBlock({ protocol }: { protocol: PvtProtocol }) {
  const view = divergencesView(protocol);
  if (view === null) return null;
  return (
    <Fold data-ui="pvt-divergences"
      concept="divergences"
      data-pvt-divergences=""
      label={
        <>
          Divergencias con lo publicado: <span className="num">{view.count}</span>
        </>
      }
    >
      <p className="secondary">{view.note}</p>
      {view.kept !== null && <p className="secondary">{view.kept}</p>}
      {view.rows.map((row) => (
        <article key={row.key} data-pvt-divergence={row.key} style={{ marginTop: 12 }}>
          <PanelTitle as="h4" concept="measure">
            {row.display}
            {row.scores && <span className="secondary"> · entra en la puntuación</span>}
          </PanelTitle>
          <div data-status-mark="">
            <Mark pictogram={row.mark.pictogram} color={row.mark.color}>
              {row.statusDisplay}
            </Mark>
          </div>
          <dl className="kv">
            {/* Las tres claves con el signo que ya tienen en Tierra y en el detalle de una alerta
                (§5.33.12): lo que hace EMMA, el engranaje de sus piezas (como en cada bloque leído
                de Tierra); lo publicado, el libro abierto de lo leído en la fuente; la
                consecuencia, el bocadillo de «por qué puede importar». */}
            <FieldLabel as="dt" concept="systems">
              EMMA
            </FieldLabel>
            <dd>{row.emma}</dd>
            <FieldLabel as="dt" concept="sourceText">
              Lo publicado
            </FieldLabel>
            <dd>{row.published}</dd>
            <FieldLabel as="dt" concept="reason">
              Consecuencia
            </FieldLabel>
            <dd>{row.consequence}</dd>
          </dl>
          {row.kept !== null && <p className="secondary">{row.kept}</p>}
          {row.sources.length > 0 && (
            <ul className="evidence">
              {row.sources.map((item) => (
                <li key={item.id}>
                  {item.label}
                  <CitedView item={item} />
                </li>
              ))}
            </ul>
          )}
          {row.notFound.length > 0 && (
            <>
              <div className="secondary">
                <Mark pictogram={uiPictogram("searchedNotFound")}>Buscado y no encontrado en lo leído:</Mark>
              </div>
              <ul className="evidence">
                {row.notFound.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </>
          )}
        </article>
      ))}
    </Fold>
  );
}

/**
 * El signo del mando de empezar: el cronómetro, o el de «cargando» mientras se envía. La
 * comprobación de `null` es para el tipo (`StateMark` admite marca sin dibujo); la de cargando
 * siempre lo tiene.
 */
function startSign(sending: boolean): Sign {
  return sending && LOADING_MARK.pictogram !== null
    ? { pictogram: LOADING_MARK.pictogram }
    : { concept: "startTest" };
}
