import { useEffect, useState } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { BoardOnly, useLook } from "../components/BoardOnly";
import { Command } from "../components/Command";
import { Fold } from "../components/Fold";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { type SensorBindings, api } from "../lib/api";
import { formatMet, formatNumber, missionElapsedSeconds } from "../lib/format";
import { type RequestOutcome, requestOutcome } from "../lib/marks";
import { readingSourcePictogram } from "./readingSources";
import {
  EMPTY_FORM,
  bindBody,
  bindingInstant,
  bindingRows,
  canBind,
  unbindBody,
} from "./sensorBindings";

/**
 * El vinculo sensor-tripulante, tal y como lo declaro una persona (especificacion del equipo
 * §3, «sensor bindings» del astronauta).
 *
 * EMMA no comprueba quien lleva puesto un dispositivo: lo que se ve es lo declarado en la
 * consola y firmado en el registro, y el rotulo del backend va arriba, junto al titulo. Las
 * frases que explican que es un dispositivo, que declaracion vale y para que sirve son del
 * backend. Aqui solo se ordenan las filas (`sensorBindings.ts`): un vinculo de otro tripulante
 * se ensena sin marca de aviso, porque no lo es. La fuente de cada dispositivo lleva el
 * pictograma de su canal junto a su nombre (`readingSources.ts`), sin color.
 *
 * Se puede vincular un dispositivo al tripulante que se esta mirando y retirar un vinculo
 * vigente. Las dos cosas son una declaracion firmada con el operador de la consola; no hay
 * borrar ni editar. El vinculo no cambia nada del estado de arriba.
 *
 * Tablero (decisión del usuario, 2026-11-07): bajo la concha de la maqueta (`BoardOnly`), cuando
 * hay vínculos vigentes, dos píldoras de recuento bajo la frase del backend: cuántos apuntan al
 * tripulante que se mira y cuántos a otros (`bindingRows`), sin color y sin nombrar a nadie (ni al
 * que se mira: «este tripulante»): quién lleva cada dispositivo y quién lo declaró lo dicen las
 * filas de abajo. La flecha es la misma que liga dispositivo y tripulante en esas filas.
 *
 * Una pantalla por sección (lote «muestra», 2026-11-08): en la concha de la maqueta, a la vista
 * quedan las píldoras (la de este tripulante también con cero) y los vínculos vigentes con su mando
 * «Retirar» (un mando no se pliega); la frase de estado del backend, «Cómo leerlo», el historial y
 * el formulario de declarar van detrás de «Ver detalle». El error de una declaración se dice fuera del detalle, para que un «Retirar»
 * fallido no quede escondido. En la clásica, todo en su orden de antes.
 */
export function SensorBindingsPanel({
  subject,
  missionStart,
  referenceTime,
  operator,
}: {
  subject: string;
  missionStart: string;
  /** El instante de los datos, desde el que vale una declaracion. */
  referenceTime: string | null;
  operator: string;
}) {
  const [overview, setOverview] = useState<SensorBindings | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [declared, setDeclared] = useState(0);
  const [error, setError] = useState<RequestOutcome | null>(null);
  const board = useLook() === "reference";

  useEffect(() => {
    let cancelled = false;
    api
      .sensorBindings()
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
  }, [subject, declared]);

  if (overview === null) return null;
  const met = (iso: string) => formatMet(missionElapsedSeconds(missionStart, new Date(iso)));
  const rows = bindingRows(overview, subject);
  const own = rows.filter((row) => row.own).length;
  const others = rows.length - own;
  const since = bindingInstant(referenceTime, new Date());
  const signer = operator.trim();
  const sign = (body: Parameters<typeof api.declareSensorBinding>[0]) => {
    setError(null);
    api
      .declareSensorBinding(body)
      .then(() => {
        setForm(EMPTY_FORM);
        setDeclared((count) => count + 1);
      })
      .catch((cause: unknown) => setError(requestOutcome(cause)));
  };

  const failure = error !== null && (
    <>
      {" "}
      <MarkOf mark={error.mark}>{error.text}</MarkOf>
    </>
  );
  const summary = <p className="secondary">{overview.summary}</p>;
  // Plegables y formulario: en la clásica, en su sitio; en el tablero, detrás de «Ver detalle».
  const declare = (
    <>
      <Fold data-ui="sensor-bindings-how-to-read" concept="howToRead" label="Cómo leerlo">
        <p className="secondary">{overview.note}</p>
        <p className="secondary">{overview.device_basis}</p>
        <p className="secondary">{overview.rule}</p>
        <p className="secondary">{overview.scope}</p>
      </Fold>
      {overview.history.length > 0 && (
        <Fold data-ui="sensor-bindings-history"
          concept="history"
          label={
            <>
              Historial de declaraciones (<span className="num">{formatNumber(overview.history.length)}</span>)
            </>
          }
        >
          <ul className="secondary">
            {overview.history.map((item) => (
              <li key={item.ledger_index}>
                <span className="num">{met(item.since)}</span> ·{" "}
                <Mark pictogram={readingSourcePictogram(item.source)}>{item.source_display}</Mark> ·{" "}
                <span className="num">{item.device_display}</span>{" "}
                {/* Sin tripulante (vínculo retirado) la raya va sola: un dibujo sin palabra no existe. */}
                {item.crew === null ? "—" : <Mark pictogram="arrow-right">{item.crew}</Mark>}
                {item.previous_crew !== null && item.changed && <> (antes: {item.previous_crew})</>}{" "}
                · firma {item.declared_by} · asiento{" "}
                <span className="num">{item.ledger_index}</span>
                {item.note !== null && <> · {item.note}</>}
              </li>
            ))}
          </ul>
        </Fold>
      )}
      <div className="inline-form">
        <select
          value={form.source}
          aria-label="Fuente del dispositivo"
          onChange={(event) => setForm({ ...form, source: event.target.value })}
        >
          <option value="">Fuente…</option>
          {overview.sources.map((source) => (
            <option key={source.key} value={source.key}>
              {source.display}
            </option>
          ))}
        </select>
        <input
          value={form.device}
          maxLength={64}
          placeholder={overview.whole_source_display}
          aria-label="Identificador del dispositivo (opcional)"
          onChange={(event) => setForm({ ...form, device: event.target.value })}
        />
        <input
          value={form.note}
          maxLength={500}
          placeholder="nota de quien declara (opcional)"
          aria-label="Nota de la declaración"
          onChange={(event) => setForm({ ...form, note: event.target.value })}
        />
        <Command
          concept="bind"
          disabled={!canBind(form, operator)}
          onClick={() => sign(bindBody(form, subject, operator, since))}
        >
          Vincular a {subject}
        </Command>
        <span className="secondary">
          vale desde <span className="num">{met(since)}</span> · firma{" "}
          {signer === "" ? "—" : signer}
        </span>
        {!board && failure}
      </div>
    </>
  );

  return (
    <section data-ui="sensor-bindings" className="panel" aria-label="Vínculo sensor-tripulante">
      <PanelTitle concept="devices">
        Dispositivos vinculados <span className="secondary">· {overview.label}</span>
      </PanelTitle>
      {!board && summary}
      {/* La píldora de este tripulante va también con cero vínculos: es una cuenta real, y con la
          frase de estado detrás de «Ver detalle» el panel quedaba sin ninguna cifra. */}
      <BoardOnly>
        <ul className="board-tally" aria-label="Vínculos vigentes, por tripulante">
          <li className="ref-pill board-pill">
            <Mark pictogram="arrow-right">este tripulante</Mark> <span className="num">{formatNumber(own)}</span>
          </li>
          {others > 0 && (
            <li className="ref-pill board-pill">
              <Mark pictogram="arrow-right">otros tripulantes</Mark> <span className="num">{formatNumber(others)}</span>
            </li>
          )}
        </ul>
      </BoardOnly>
      {rows.length > 0 && (
        <ul>
          {rows.map(({ key, binding, own }) => (
            <li key={key}>
              <Mark pictogram={readingSourcePictogram(binding.source)}>{binding.source_display}</Mark> ·{" "}
              <span className="num">{binding.device_display}</span>{" "}
              {/* La flecha que ligaba dispositivo y tripulante era un carácter (→); va como
                  pictograma junto al nombre del tripulante al que apunta. */}
              <Mark pictogram="arrow-right">{own ? <strong>{binding.crew}</strong> : binding.crew}</Mark>
              <span className="secondary">
                {" "}
                · desde <span className="num">{met(binding.since)}</span> · firma{" "}
                {binding.declared_by} · asiento <span className="num">{binding.ledger_index}</span>
                {binding.note !== null && <> · {binding.note}</>}
              </span>{" "}
              <Command
                concept="unbind"
                disabled={signer === ""}
                onClick={() => sign(unbindBody(binding, operator, since))}
              >
                Retirar
              </Command>
              {binding.caveat !== null && <div className="secondary">{binding.caveat}</div>}
            </li>
          ))}
        </ul>
      )}
      {board ? (
        <>
          <BoardDetail label="estado y declaración">
            {summary}
            {declare}
          </BoardDetail>
          {failure !== false && <p>{failure}</p>}
        </>
      ) : (
        declare
      )}
    </section>
  );
}
