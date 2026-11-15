import { useCallback, useEffect, useState } from "react";

import { BoardOnly } from "../components/BoardOnly";
import { Chosen } from "../components/Chosen";
import { Command } from "../components/Command";
import { FieldLabel } from "../components/FieldLabel";
import { IndicatorName } from "../components/IndicatorName";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { StatTile } from "../components/StatTile";
import { Loading } from "../components/Unavailable";
import { DAY_SECONDS, type Reading, Sparkline } from "../dashboard/HomeCharts";
import { type PainCatalog, type PainReport, api } from "../lib/api";
import { formatNumber } from "../lib/format";
import { hasIndicatorFamily, indicatorFamily } from "../lib/indicatorFamily";
import { type StateMark, EMPTY_MARK, OK_MARK, UNKNOWN_PICTOGRAM, requestOutcome } from "../lib/marks";
import { useOperator } from "../lib/operator";
import { uiPictogram } from "../lib/uiMarks";
import { BodyMap } from "./BodyMap";
import { characterMark } from "./characters";
import { PainEvolution } from "./PainHistory";
import { type NoteOrigin, PainNote } from "./PainNote";
import {
  INTENSITIES,
  type PainForm,
  missingIntensities,
  toBody,
  toggleCharacter,
  toggleZone,
  withIntensity,
} from "./report";

/**
 * Mapa corporal de dolor en la consola de tripulacion.
 *
 * Se toca la zona en el cuerpo (o se elige en la lista, sin 3D), se dice cuanto duele de 1
 * a 10 y, si se quiere, como. Lo que se puede elegir lo declara el backend
 * (`/api/pain/catalog`); aqui no se escribe texto clinico. Tras registrar se vuelve a pedir
 * lo firmado: lo que se ve es lo que el backend tiene.
 *
 * Pictogramas (§5.32): el rayo de la familia del indicador junto al rotulo de intensidad, el
 * anillo con punto de «elegido» (`ring-dot`; el disco lleno es «medido») junto a la cifra elegida
 * (ademas del estado pulsado del boton), y el dibujo de cada caracter (`characters.ts`) junto a su
 * palabra. Ninguno en rojo ni amarillo (§5.2). Segunda pasada (§5.33.9): el título, los rótulos,
 * la leyenda de cada zona y los mandos llevan el signo de su concepto (`lib/uiMarks.ts`), y el
 * formulario vacío, el anillo punteado sin color de «nada aquí» (como las listas vacías de la
 * ecografía y los informes): no es un dato ausente, es que aún no se ha marcado nada.
 *
 * Tablero (decisión del usuario, 2026-11-07): bajo la concha de la maqueta van tres fichas con cifra
 * (`PainBoard`; desde el 2026-11-08, arriba, antes del cuerpo: el resumen primero): la intensidad máxima del último informe sobre la escala
 * del catálogo, con la curva de la intensidad de todos los informes debajo; cuántas zonas lleva ese
 * informe; y cuántos informes hay. La intensidad de un «sin dolor» (informe sin zonas) no se pinta
 * como un cero: la ficha lo dice con la palabra que ya usa este panel y la marca de visto (sus zonas
 * sí son cero, y así se cuentan). El lienzo del cuerpo, las
 * zonas y los tipos del backend no cambian.
 */
export function PainPanel({ subject }: { subject: string }) {
  const [catalog, setCatalog] = useState<PainCatalog | null>(null);
  const [reports, setReports] = useState<PainReport[]>([]);
  const [form, setForm] = useState<PainForm>([]);
  const [operator, setOperator] = useOperator();
  const [message, setMessage] = useState<PanelMessage | null>(null);
  const [busy, setBusy] = useState(false);
  // Si la última lectura de los informes falló: las fichas del tablero conservan lo de antes, en cursiva.
  const [reportsFailed, setReportsFailed] = useState(false);
  const [note, setNote] = useState("");
  const [noteOrigin, setNoteOrigin] = useState<NoteOrigin>("escrita");

  const load = useCallback(() => {
    Promise.all([api.pain.catalog(), api.pain.reports(subject)])
      .then(([zones, recorded]) => {
        setCatalog(zones);
        setReports(recorded);
        setReportsFailed(false);
      })
      .catch((reason: unknown) => {
        setReportsFailed(true);
        setMessage(requestOutcome(reason));
      });
  }, [subject]);
  useEffect(load, [load]);

  if (catalog === null) {
    return (
      <section data-ui="pain" className="panel" aria-label="Dolor">
        <PanelTitle concept="pain">Dolor</PanelTitle>
        {/* Mientras no llega la primera respuesta el panel lo dice: sin la marca de carga, al
            volver de Tierra se veía vacío durante segundos (§5.33.11). */}
        {message === null ? <Loading /> : <Message message={message} />}
      </section>
    );
  }

  const names = Object.fromEntries(catalog.zones.map((zone) => [zone.key, zone.display]));
  const marked = form.map((entry) => entry.zone);
  const missing = missingIntensities(form);
  const body = toBody(form, operator);

  const submit = async () => {
    if (body === null) return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await api.pain.record({
        subject,
        ...body,
        ...(note.trim() === "" ? {} : { note: note.trim(), note_origin: noteOrigin }),
      });
      setMessage({
        mark: OK_MARK,
        text:
          body.zones.length === 0
            ? "Registrado: sin dolor."
            : `Registrado: ${body.zones.length} zonas, máximo ${formatNumber(result.intensity)}.`,
      });
      setForm([]);
      setNote("");
      setNoteOrigin("escrita");
      load();
    } catch (reason) {
      setMessage(requestOutcome(reason));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section data-ui="pain" className="panel" aria-label="Dolor">
      <PanelTitle concept="pain">Dolor</PanelTitle>
      {/* Tablero (2026-11-08, una pantalla por sección): el resumen del último informe arriba, antes
          del cuerpo y del formulario; la evolución sigue abajo. */}
      <BoardOnly>
        <PainBoard reports={reports} catalog={catalog} stale={reportsFailed} />
      </BoardOnly>
      <div className="pain-layout">
        <BodyMap
          selected={marked}
          names={names}
          onToggle={(zone) => setForm((current) => toggleZone(current, zone))}
        />

        <div className="silence-form">
          <FieldLabel concept="add">
            Añadir zona desde la lista{" "}
            <select
              value=""
              onChange={(event) => setForm((current) => toggleZone(current, event.target.value))}
            >
              <option value="" disabled>
                — elegir —
              </option>
              {catalog.zones
                .filter((zone) => !marked.includes(zone.key))
                .map((zone) => (
                  <option key={zone.key} value={zone.key}>
                    {zone.display}
                  </option>
                ))}
            </select>
          </FieldLabel>

          {form.length === 0 && (
            <p className="secondary">
              <MarkOf mark={EMPTY_MARK}>
                Ninguna zona marcada. Si no le duele nada, regístrelo con «Sin dolor».
              </MarkOf>
            </p>
          )}

          {form.map((entry) => (
            <fieldset key={entry.zone} className="view-signs">
              <FieldLabel as="legend" concept="zone">
                {names[entry.zone] ?? entry.zone}
              </FieldLabel>
              <div className="measure-actions" role="group" aria-label="Intensidad">
                <span className="secondary">
                  <IndicatorName indicatorKey="pain-intensity" displayEs="Intensidad" />
                </span>
                {INTENSITIES.map((value) => (
                  <button
                    key={value}
                    className="command num"
                    aria-pressed={entry.intensity === value}
                    onClick={() => setForm((current) => withIntensity(current, entry.zone, value))}
                  >
                    <Chosen chosen={entry.intensity === value}>{formatNumber(value)}</Chosen>
                  </button>
                ))}
              </div>
              <div className="measure-actions" role="group" aria-label="Tipo de dolor">
                <span className="secondary">
                  <Mark pictogram={uiPictogram("type")}>Tipo (opcional)</Mark>
                </span>
                {catalog.characters.map((character) => (
                  <label key={character.key}>
                    <input
                      type="checkbox"
                      checked={entry.characters.includes(character.key)}
                      onChange={() =>
                        setForm((current) => toggleCharacter(current, entry.zone, character.key))
                      }
                    />{" "}
                    <Mark pictogram={characterMark(character.key).pictogram}>{character.display}</Mark>
                  </label>
                ))}
              </div>
              <div>
                <Command
                  concept="removeZone"
                  onClick={() => setForm((current) => toggleZone(current, entry.zone))}
                >
                  Quitar zona
                </Command>
              </div>
            </fieldset>
          ))}

          <PainNote
            note={note}
            origin={noteOrigin}
            onChange={(text, origin) => {
              setNote(text);
              setNoteOrigin(origin);
            }}
          />

          <FieldLabel concept="person" className="operator">
            Informa{" "}
            <input
              value={operator}
              maxLength={64}
              onChange={(event) => setOperator(event.target.value)}
              placeholder="nombre o indicativo"
            />
          </FieldLabel>
          <div className="measure-actions">
            {form.length > 0 ? (
              <Command
                concept="register"
                disabled={body === null || busy}
                onClick={() => void submit()}
              >
                {busy ? "Registrando…" : "Registrar dolor"}
              </Command>
            ) : (
              <Command
                concept="noPain"
                disabled={body === null || busy}
                onClick={() => void submit()}
              >
                {busy ? "Registrando…" : "Sin dolor"}
              </Command>
            )}
            {missing > 0 && (
              <span className="secondary">
                Falta la intensidad de <span className="num">{missing}</span> zonas.
              </span>
            )}
            {operator.trim() === "" && (
              <span className="secondary">Falta quién informa.</span>
            )}
          </div>
          {message !== null && <Message message={message} />}
        </div>
      </div>

      <PanelTitle as="h3" concept="trends">
        Evolución
      </PanelTitle>
      <PainEvolution reports={reports} catalog={catalog} />
    </section>
  );
}

/** Una semana: el suelo de la ventana de la curva de la intensidad. */
const WEEK_MS = 7 * DAY_SECONDS * 1000;

/**
 * Las fichas de la evolución. La curva es la intensidad máxima de cada informe (`intensity`, la
 * cifra que entra en el análisis) por su hora firmada, con la ventana de la propia serie (del primer
 * informe al último, con una semana de suelo para que dos informes del mismo día no se estiren a todo
 * el ancho); solo con dos o más informes, y sin escala vertical propia: la cifra escrita es la que se
 * lee. Va también bajo «sin dolor»: un último informe sin zonas no borra la serie de antes. Sin
 * informes no hay fichas: la lista de abajo ya lo dice con su marca. Si la última lectura falló, las
 * fichas conservan lo que había, en cursiva (`stale`).
 */
function PainBoard({ reports, catalog, stale }: { reports: readonly PainReport[]; catalog: PainCatalog; stale: boolean }) {
  const latest = reports.at(-1);
  if (latest === undefined) return null;
  const readings: Reading[] = reports
    .map((report) => ({ at: new Date(report.effective).getTime(), value: report.intensity }))
    .filter((reading) => Number.isFinite(reading.at))
    .sort((a, b) => a.at - b.at);
  const first = readings[0];
  const last = readings.at(-1);
  const curve =
    first !== undefined && last !== undefined && readings.length >= 2 ? (
      <Sparkline readings={readings} until={last.at} windowMs={Math.max(last.at - first.at, WEEK_MS)} />
    ) : null;
  const intensity = hasIndicatorFamily("pain-intensity") ? indicatorFamily("pain-intensity") : UNKNOWN_PICTOGRAM;
  return (
    <div className="board-stats pain-board" role="group" aria-label="Último informe de dolor">
      {latest.zones.length === 0 ? (
        <StatTile pictogram={intensity} label="Intensidad máxima" value={null} status={{ mark: OK_MARK, word: "sin dolor" }} stale={stale}>
          {curve}
        </StatTile>
      ) : (
        <StatTile
          pictogram={intensity}
          label="Intensidad máxima"
          value={latest.intensity}
          unit={`de ${formatNumber(catalog.scale.max)}`}
          stale={stale}
        >
          {curve}
        </StatTile>
      )}
      <StatTile concept="zone" label="Zonas" value={latest.zones.length} stale={stale} />
      <StatTile concept="history" label="Informes" value={reports.length} stale={stale} />
    </div>
  );
}

/**
 * El mensaje del panel con la forma de su significado (F.5-1): anillo punteado en cian si no se
 * pudo cargar (dato ausente), triangulo en amarillo si el registro fallo (requiere atencion), y
 * la marca de visto sin color, en texto secundario, cuando confirma el registro (`OK_MARK`, §5.33).
 */
interface PanelMessage {
  mark: StateMark;
  text: string;
}

function Message({ message }: { message: PanelMessage }) {
  return (
    <p className={message.mark.color === null ? "secondary" : undefined}>
      <Mark pictogram={message.mark.pictogram} color={message.mark.color}>
        {message.text}
      </Mark>
    </p>
  );
}
