import { useEffect, useState } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { useLook } from "../components/BoardOnly";
import { Fold } from "../components/Fold";
import { LevelBadge } from "../components/LevelBadge";
import { MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { Loading, Unavailable } from "../components/Unavailable";
import { type TwinQuestion, type TwinQuestions, twinsApi } from "../lib/api";
import { OK_MARK, type RequestOutcome, UNAVAILABLE_MARK, requestOutcome } from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";
import { type PictogramTable, pictogramFor } from "./pictogramTable";
import { tr } from "../lib/i18n";

/**
 * Las cinco preguntas de los gemelos (base de conocimiento §10), respondidas para un tripulante.
 *
 * Por qué existe: cada respuesta ya estaba en la consola, repartida en cinco paneles, y nadie las
 * juntaba con la pregunta que el equipo les hizo. Aquí van las cinco, con la pregunta literal del
 * documento y la respuesta que compone el backend (`app/twins.py`) con lo que el estado ya calculó.
 * Esta vista no escribe ninguna frase: la pregunta, la respuesta, sus partes, sus reservas y de
 * dónde sale son del backend; aquí solo se elige el dibujo de cada capa, la insignia del nivel y la
 * marca de «nada que contar» o «no disponible».
 *
 * El dibujo de cada capa es el del panel que la responde (los dominios, el hábitat, el día de
 * misión, «Qué hacer», «Espera por una persona»): un concepto, un dibujo (§5.32 c). Una capa que la
 * interfaz no conoce va con su palabra y el dibujo de «desconocido».
 *
 * Se vuelve a leer con cada estado (`refreshKey`): las respuestas son las de ese estado.
 *
 * En la consola de Tierra va con `until`, el corte del retardo (§5.36.3): el backend responde con
 * lo llegado hasta él y lo dice en su nota. El corte se lee al pedir, no gobierna cuándo se pide:
 * se mueve con cada tiempo de luz y la respuesta tarda; se vuelve a pedir cuando cambia el estado
 * recibido (`refreshKey`), que es lo que cambia lo que Tierra sabe.
 */
const LAYER_PICTOGRAMS: PictogramTable = {
  human: uiPictogram("domains"),
  habitat: uiPictogram("habitat"),
  mission: uiPictogram("missionDay"),
  countermeasure: uiPictogram("recommendations"),
  decision: uiPictogram("waiting"),
};

export function TwinQuestionsPanel({
  subject,
  refreshKey,
  until = null,
}: {
  subject: string;
  refreshKey: string;
  /** El corte de Tierra; sin él (a bordo), el estado de ahora. */
  until?: Date | null;
}) {
  const [data, setData] = useState<TwinQuestions | null>(null);
  const [unavailable, setUnavailable] = useState<RequestOutcome | null>(null);

  // Otro tripulante: lo pintado era del anterior.
  useEffect(() => {
    setData(null);
    setUnavailable(null);
  }, [subject]);

  useEffect(() => {
    let alive = true;
    twinsApi
      .questions(subject, until ?? undefined)
      .then((body) => {
        if (!alive) return;
        setData(body);
        setUnavailable(null);
      })
      .catch((reason: unknown) => {
        if (alive) setUnavailable(requestOutcome(reason));
      });
    return () => {
      alive = false;
    };
  }, [subject, refreshKey]);

  return <TwinQuestionsView data={data} unavailable={unavailable} />;
}

/** Solo pinta. Separado de la carga para poder probar lo que se lee en pantalla. */
export function TwinQuestionsView({
  data,
  unavailable,
}: {
  data: TwinQuestions | null;
  unavailable: RequestOutcome | null;
}) {
  if (data === null) {
    return (
      <section data-ui="twin-questions" className="panel" aria-label={tr("Las cinco preguntas de los gemelos", "The twins' five questions")}>
        <PanelTitle concept="twinQuestions">{tr("Las cinco preguntas de los gemelos", "The twins' five questions")}</PanelTitle>
        {unavailable !== null ? <Unavailable outcome={unavailable} /> : <Loading />}
      </section>
    );
  }
  return <TwinQuestionsLoaded data={data} unavailable={unavailable} />;
}

/**
 * Segunda ronda del lote «muestra» (2026-11-08): las cinco columnas medían 500 px con un «Ver detalle»
 * por pregunta, y en filas seguían midiendo 410. Bajo la concha de la maqueta las cinco preguntas son
 * cinco mosaicos en fila (la pregunta, su respuesta y las insignias de nivel: la respuesta es lo que
 * importa, también cuando no lleva marca —lo señaló la revisión—), y lo demás de las cinco —qué cubre
 * la capa, las partes, las notas, de dónde
 * sale cada una— con la nota del panel y de dónde salen las preguntas, tras un solo «Ver detalle»
 * debajo, cada respuesta con el nombre de su gemelo delante. La clásica no cambia.
 */
function TwinQuestionsLoaded({
  data,
  unavailable,
}: {
  data: TwinQuestions;
  unavailable: RequestOutcome | null;
}) {
  // Si la última lectura falló, lo pintado es lo de antes: caducado (cursiva) y con el motivo.
  const stale = unavailable !== null;
  const board = useLook() === "reference";
  const note = <p className="secondary">{data.note}</p>;
  const source = (
    <Fold data-ui="twin-questions-source" concept="source" label={tr("De dónde salen las preguntas", "Where the questions come from")}>
      <p className="secondary">{data.source}</p>
    </Fold>
  );
  return (
    <section data-ui="twin-questions" className="panel" aria-label={tr("Las cinco preguntas de los gemelos", "The twins' five questions")} data-twin-questions>
      <PanelTitle concept="twinQuestions">{tr("Las cinco preguntas de los gemelos", "The twins' five questions")}</PanelTitle>
      {unavailable !== null && <Unavailable outcome={unavailable} />}
      {!board && note}
      {data.questions.map((item) => (
        <Answer key={item.key} item={item} stale={stale} board={board} />
      ))}
      {board ? (
        <BoardDetail className="twin-questions-notes" label={tr("respuestas, nota y de dónde salen", "answers, note and where they come from")}>
          {data.questions.map((item) => (
            <div key={item.key} data-twin-detail={item.key} className={stale ? "stale" : undefined}>
              <p>
                <strong>{item.twin}</strong>
              </p>
              <AnswerBody item={item} board />
            </div>
          ))}
          {note}
          {source}
        </BoardDetail>
      ) : (
        source
      )}
    </section>
  );
}

/** La respuesta con su marca: «nada que contar» con el visto, «no disponible» en gris. */
function AnswerLine({ item }: { item: TwinQuestion }) {
  return (
    <p>
      {item.state === "nothing" ? (
        <MarkOf mark={OK_MARK}>{item.answer}</MarkOf>
      ) : item.state === "unavailable" ? (
        <MarkOf mark={UNAVAILABLE_MARK}>{item.answer}</MarkOf>
      ) : (
        item.answer
      )}
    </p>
  );
}



function Parts({ item }: { item: TwinQuestion }) {
  if (item.items.length === 0) return null;
  return (
    <ul className="drivers">
      {item.items.map((part, index) => (
        <li key={`${index}:${part.text}`}>
          {part.level !== null && (
            <>
              <LevelBadge level={part.level} />{" "}
            </>
          )}
          {part.text}
        </li>
      ))}
    </ul>
  );
}

/**
 * Lo que de una respuesta va al detalle: en el tablero, qué cubre la capa y
 * las partes con su insignia; en las dos conchas, las notas y de dónde sale.
 */
function AnswerBody({ item, board }: { item: TwinQuestion; board: boolean }) {
  return (
    <>
      {board && <p className="secondary">{item.content}</p>}
      {board && <Parts item={item} />}
      {item.notes.map((note) => (
        <p key={note} className="secondary">
          {note}
        </p>
      ))}
      <Fold data-ui="twin-answer-provenance" concept="provenance" label={tr("De dónde sale", "Where it comes from")}>
        <ul className="drivers">
          {item.sources.map((source) => (
            <li key={source}>{source}</li>
          ))}
        </ul>
      </Fold>
    </>
  );
}

/**
 * Una pregunta y su respuesta. Lote «muestra» (2026-11-08, una pantalla por sección): bajo la concha
 * de la maqueta van a la vista la pregunta, la respuesta si lleva marca («nada que contar», «no
 * disponible») y las insignias de nivel de sus partes (un nivel no se pliega); lo demás, en el detalle
 * común del panel (`AnswerBody`). En la clásica, todo en su orden de siempre.
 */
function Answer({ item, stale, board }: { item: TwinQuestion; stale: boolean; board: boolean }) {
  const pictogram = pictogramFor(LAYER_PICTOGRAMS, item.key);
  const leveled = item.items.flatMap((part) => (part.level === null ? [] : [part.level]));
  return (
    <div data-twin={item.key} className={stale ? "stale" : undefined}>
      {pictogram === null ? (
        <h3>
          {item.twin}: {item.question}
        </h3>
      ) : (
        <PanelTitle as="h3" pictogram={pictogram} className="section-gap">
          {item.twin}: {item.question}
        </PanelTitle>
      )}
      {!board && <p className="secondary">{item.content}</p>}
      <AnswerLine item={item} />
      {board && leveled.length > 0 && (
        <p className="board-tally">
          {leveled.map((level, index) => (
            <LevelBadge key={`${index}:${level}`} level={level} />
          ))}
        </p>
      )}
      {!board && <Parts item={item} />}
      {!board && <AnswerBody item={item} board={false} />}
    </div>
  );
}
