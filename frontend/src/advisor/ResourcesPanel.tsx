import { useEffect, useState } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { BoardOnly } from "../components/BoardOnly";
import { Command } from "../components/Command";
import { Fold } from "../components/Fold";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { type ResourcesOverview, api } from "../lib/api";
import { formatMet, formatNumber, missionElapsedSeconds } from "../lib/format";
import { type RequestOutcome, requestOutcome } from "../lib/marks";
import { RequestWarning } from "./RequestWarning";
import {
  EMPTY_FORM,
  type StateMark,
  canDeclare,
  declarationBody,
  declarationInstant,
  historyRows,
  panelRows,
} from "./resources";

interface StateCount {
  state: string;
  /** La palabra del backend para ese estado, la de sus propias filas. */
  display: string;
  mark: StateMark;
  count: number;
}

/**
 * Cuantos recursos hay en cada estado, en el orden de las filas del panel (`panelRows`: lo declarado
 * no disponible primero; un estado aparece donde aparece su primera fila). La palabra es la de las
 * filas del backend, asi que un estado que esta version no conoce sale tambien, con su palabra y sin
 * significado. Vacio si no hay recursos: no se pinta nada.
 */
export function stateTally(overview: Pick<ResourcesOverview, "resources">): StateCount[] {
  const seen = new Map<string, StateCount>();
  for (const { resource, mark } of panelRows(overview)) {
    const entry = seen.get(resource.state);
    if (entry !== undefined) entry.count += 1;
    else seen.set(resource.state, { state: resource.state, display: resource.state_display, mark, count: 1 });
  }
  return [...seen.values()];
}

/**
 * Los recursos de a bordo, tal y como los declaro una persona (especificacion del equipo §3,
 * `available_resources` del contexto de mision).
 *
 * EMMA no lleva inventario: lo que se ve es lo declarado en la consola y firmado en el
 * registro, y el rotulo del backend va arriba, junto al titulo. Los nombres, las palabras de
 * estado y las frases que explican como leerlo son del backend. Aqui solo se elige la marca
 * (`resources.ts`): «sin declarar» es un dato ausente (cian, anillo punteado), nunca un
 * «disponible»; y cada recurso lleva el dibujo de su familia junto a su nombre, tambien en el
 * historial. En el selector no hay dibujo: un `<option>` no admite mas que texto.
 *
 * Se puede declarar un recurso disponible o no disponible. Es una declaracion firmada con el
 * operador de la consola; no hay borrar ni editar, y no hay cantidades. Lo declarado no cambia
 * que se recomienda ni nada del estado de arriba: sale como aviso junto a cada recomendacion,
 * en la siguiente lectura del estado.
 *
 * Segunda pasada (§5.33.5): el titulo y el plegable de la lista llevan el cubo de «recursos», el
 * de como leerlo la «i», el historial el reloj que mira atras y el mando de declarar la pluma
 * (`lib/uiMarks.ts`). El fallo de una declaracion sigue en amarillo, con el triangulo delante.
 *
 * Tablero (decision del usuario, 2026-11-07): bajo la concha de la maqueta, una pildora por estado
 * con cuantos recursos hay en el (`stateTally`): la palabra del backend y la marca de `resources.ts`
 * (el gris de lo declarado no disponible, el cian de lo sin declarar), solo los estados que hay. La
 * frase del resumen sigue encima, intacta; la clasica no monta las pildoras.
 */
export function ResourcesPanel({
  missionStart,
  referenceTime,
  operator,
}: {
  missionStart: string;
  /** El instante de los datos, desde el que vale una declaracion. */
  referenceTime: string | null;
  operator: string;
}) {
  const [overview, setOverview] = useState<ResourcesOverview | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [declared, setDeclared] = useState(0);
  const [error, setError] = useState<RequestOutcome | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .resources()
      .then((body) => {
        if (!cancelled) setOverview(body);
      })
      // Sin esta lectura el resto de la consola sigue valiendo: aqui no se ensena nada.
      .catch(() => {
        if (!cancelled) setOverview(null);
      });
    return () => {
      cancelled = true;
    };
  }, [declared]);

  if (overview === null) return null;
  const met = (iso: string) => formatMet(missionElapsedSeconds(missionStart, new Date(iso)));
  const rows = panelRows(overview);
  const tally = stateTally(overview);
  const summary = <p className="secondary">{overview.summary}</p>;
  const since = declarationInstant(referenceTime, new Date());
  const signer = operator.trim();
  const sign = () => {
    setError(null);
    api
      .declareResource(declarationBody(form, operator, since))
      .then(() => {
        setForm(EMPTY_FORM);
        setDeclared((count) => count + 1);
      })
      .catch((cause: unknown) => setError(requestOutcome(cause)));
  };

  return (
    <section data-ui="onboard-resources" className="panel" aria-label="Recursos de a bordo">
      <PanelTitle concept="resources">
        Recursos de a bordo <span className="secondary">· {overview.label}</span>
      </PanelTitle>
      {summary}
      <BoardOnly>
        {tally.length > 0 && (
          <ul className="board-tally" aria-label="Recursos por estado">
            {tally.map((entry) => (
              <li key={entry.state} className="ref-pill board-pill">
                <MarkOf mark={entry.mark}>{entry.display}</MarkOf> <span className="num">{formatNumber(entry.count)}</span>
              </li>
            ))}
          </ul>
        )}
      </BoardOnly>
      {/* Lote «muestra» (2026-11-08): la lista, cómo leerlo, el historial y el formulario de
          declarar, tras «Ver detalle»; el resumen y las píldoras por estado (con el cian de lo sin
          declarar y el gris de lo no disponible), a la vista. Quinta ronda (2026-11-09): el resumen
          se queda a la vista aunque alargue la tarjeta: dice que de lo sin declarar EMMA no sabe si
          está a bordo, el texto entero de la marca cian de la píldora. */}
      <BoardDetail label="recursos, historial y declarar">
      <Fold data-ui="onboard-resources-named"
        concept="resources"
        label={<>Recursos que nombran las contramedidas ({formatNumber(rows.length)})</>}
      >
        <ul>
          {rows.map(({ resource, pictogram, mark }) => (
            <li key={resource.key}>
              <Mark pictogram={pictogram}>{resource.name}</Mark> ·{" "}
              <Mark pictogram={mark.pictogram} color={mark.color}>
                {resource.state_display}
              </Mark>
              {resource.since !== null && (
                <span className="secondary">
                  {" "}
                  · desde <span className="num">{met(resource.since)}</span> · firma{" "}
                  {resource.declared_by} · asiento{" "}
                  <span className="num">{resource.ledger_index}</span>
                  {resource.note !== null && <> · {resource.note}</>}
                </span>
              )}
            </li>
          ))}
        </ul>
      </Fold>
      <Fold data-ui="onboard-resources-how-to-read" concept="howToRead" label="Cómo leerlo">
        <p className="secondary">{overview.note}</p>
        <p className="secondary">{overview.undeclared_note}</p>
        <p className="secondary">{overview.vocabulary_basis}</p>
        <p className="secondary">{overview.rule}</p>
        <p className="secondary">{overview.scope}</p>
      </Fold>
      {overview.history.length > 0 && (
        <Fold data-ui="onboard-resources-history"
          concept="history"
          label={<>Historial de declaraciones ({formatNumber(overview.history.length)})</>}
        >
          <ul className="secondary">
            {historyRows(overview).map(({ item, pictogram, mark }) => (
              <li key={item.ledger_index}>
                <span className="num">{met(item.since)}</span> ·{" "}
                <Mark pictogram={pictogram}>{item.name}</Mark> ·{" "}
                <Mark pictogram={mark.pictogram} color={mark.color}>
                  {item.state_display}
                </Mark>
                {item.changed && <> (antes: {item.previous_state_display})</>} · firma{" "}
                {item.declared_by} · asiento <span className="num">{item.ledger_index}</span>
                {item.note !== null && <> · {item.note}</>}
              </li>
            ))}
          </ul>
        </Fold>
      )}
      <div className="inline-form">
        <select
          value={form.resource}
          aria-label="Recurso"
          onChange={(event) => setForm({ ...form, resource: event.target.value })}
        >
          <option value="">Recurso…</option>
          {overview.resources.map((resource) => (
            <option key={resource.key} value={resource.key}>
              {resource.name}
            </option>
          ))}
        </select>
        <select
          value={form.state}
          aria-label="Lo que se declara del recurso"
          onChange={(event) => setForm({ ...form, state: event.target.value })}
        >
          <option value="">Estado…</option>
          {overview.states.map((state) => (
            <option key={state.key} value={state.key}>
              {state.display}
            </option>
          ))}
        </select>
        <input
          value={form.note}
          maxLength={500}
          placeholder="nota de quien declara (opcional)"
          aria-label="Nota de la declaración"
          onChange={(event) => setForm({ ...form, note: event.target.value })}
        />
        <Command concept="declare" disabled={!canDeclare(form, operator)} onClick={sign}>
          Declarar
        </Command>
        <span className="secondary">
          vale desde <span className="num">{met(since)}</span> · firma{" "}
          {signer === "" ? "—" : signer}
        </span>
        {error !== null && <RequestWarning outcome={error} />}
      </div>
      </BoardDetail>
    </section>
  );
}
