import { type MouseEvent, useCallback, useEffect, useMemo, useState } from "react";

import {
  type ImagingSample,
  type ImagingStudy,
  type Indicator,
  type MeasureSpec,
  type MeasurementRecord,
  type ProtocolCatalog,
  api,
  frameUrl,
} from "../lib/api";
import { displayUnit, formatNumber } from "../lib/format";
import { useOperator } from "../lib/operator";
import {
  type CaliperState,
  addPoint,
  closeContour,
  currentStep,
  isComplete,
  startCalipers,
  stepsFor,
  toImagePoint,
  toRequest,
  undo,
} from "./calipers";
import { BoardDetail } from "../components/BoardDetail";
import { BoardOnly } from "../components/BoardOnly";
import { Chosen } from "../components/Chosen";
import { Command } from "../components/Command";
import { FieldLabel } from "../components/FieldLabel";
import { Fold } from "../components/Fold";
import { IndicatorName } from "../components/IndicatorName";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { StatTile } from "../components/StatTile";
import { Th } from "../components/Th";
import { Loading } from "../components/Unavailable";
import { SourceGrade } from "../evidence/SourceGrade";
import { markTint } from "../dashboard/TimelinePieces";
import { EMPTY_MARK, MISSING_MARK, OK_MARK, UNAVAILABLE_MARK, type RequestOutcome, requestOutcome } from "../lib/marks";
import { Attention, ReasonLine } from "./Attention";
import { DraftPanel } from "./DraftPanel";
import { type PreviousReading, previousReading } from "./evolution";
import { FindingsPanel } from "./FindingsPanel";
import { measurePictogram, protocolPictogram } from "./protocols";

// Velocidad de revision del cine en pantalla, no la de adquisicion.
const CINE_FPS = 10;

/**
 * Ecografia a bordo: subir un estudio, verlo y medir sobre el.
 *
 * Nada de lo que se lee aqui como indicacion clinica lo escribe la interfaz: que marcar
 * en cada paso, por que se rechaza una medida y que no alertan todavia, llega del backend
 * (invariante 7). La interfaz no valida la medida; la firma y la valida el backend.
 *
 * Cada protocolo y cada medida llevan su pictograma junto a la palabra (`./protocols.ts`), y los
 * avisos la forma que ya tenian como glifo, ahora en SVG (§5.32): nada se dice solo con color.
 * Desde la segunda pasada (§5.33.10) tambien el titulo, los rotulos, las cabeceras y los mandos
 * llevan el signo de lo que son (`lib/uiMarks.ts`), y un fallo de la API la cruz roja.
 *
 * Tablero (decisión del usuario, 2026-11-07): bajo el título, cuántos estudios hay y su reparto en
 * píldoras, por protocolo y por procedencia, con las mismas palabras y los mismos dibujos que la
 * lista de estudios. Solo en la concha de la maqueta (`BoardOnly`); la imagen, el calibre y las
 * medidas no se tocan.
 */
export function UltrasoundPanel({ subject }: { subject: string }) {
  const [catalog, setCatalog] = useState<ProtocolCatalog | null>(null);
  const [indicators, setIndicators] = useState<Record<string, Indicator>>({});
  // `null` hasta la primera respuesta: «sin estudios» antes de preguntar seria falso.
  const [studies, setStudies] = useState<ImagingStudy[] | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  // Dos lecturas, dos fallos: el del catalogo no debe ocultar que los estudios siguen cargando.
  const [catalogError, setCatalogError] = useState<RequestOutcome | null>(null);
  const [studiesError, setStudiesError] = useState<RequestOutcome | null>(null);

  const reload = useCallback(async () => {
    try {
      setStudies(await api.imaging.studies(subject));
      setStudiesError(null);
    } catch (reason) {
      setStudiesError(requestOutcome(reason));
    }
  }, [subject]);

  useEffect(() => {
    Promise.all([api.imaging.protocols(), api.indicators()])
      .then(([protocols, catalogue]) => {
        setCatalog(protocols);
        setIndicators(Object.fromEntries(catalogue.indicators.map((item) => [item.key, item])));
      })
      .catch((reason: unknown) => setCatalogError(requestOutcome(reason)));
    void reload();
  }, [reload]);

  const study = studies?.find((item) => item.ledger_index === selected) ?? null;
  const protocolName = (key: string) =>
    catalog?.protocols.find((item) => item.key === key)?.display ?? key;

  return (
    <section data-ui="ultrasound" className="panel" aria-label="Ecografía">
      <PanelTitle pictogram="probe-fan">Ecografía</PanelTitle>
      {catalog !== null && !catalog.alerting.active && (
        <p className="c-gray">
          <Mark pictogram="slash-circle">{catalog.alerting.note}</Mark>
        </p>
      )}
      {[catalogError, studiesError].map(
        (error, index) =>
          error !== null && (
            <p key={index}>
              <MarkOf mark={error.mark}>{error.text}</MarkOf>
            </p>
          ),
      )}
      {studies !== null && studies.length > 0 && (
        <BoardOnly>
          <StudyBoard
            studies={studies}
            order={catalog?.protocols.map((item) => item.key) ?? []}
            protocolName={protocolName}
            stale={studiesError !== null}
          />
        </BoardOnly>
      )}
      {/* El formulario de subir es secundario: en el tablero va tras «Ver detalle» (lote «muestra»,
          2026-11-08). El aviso de arriba, los fantomas y la lista quedan a la vista. */}
      {catalog !== null && (
        <BoardDetail label="Subir estudio DICOM">
          <UploadForm
            catalog={catalog}
            subject={subject}
            onUploaded={async (index) => {
              await reload();
              setSelected(index);
            }}
          />
        </BoardDetail>
      )}
      {catalog !== null && (
        <PhantomButtons
          catalog={catalog}
          subject={subject}
          onCreated={async (index) => {
            await reload();
            setSelected(index);
          }}
        />
      )}
      {catalog !== null && (
        <SampleButtons
          catalog={catalog}
          subject={subject}
          onCreated={async (index) => {
            await reload();
            setSelected(index);
          }}
        />
      )}
      {studies === null ? (
        // Sin respuesta todavia; si la lectura fallo, ya lo dice la cruz roja de arriba.
        studiesError === null && (
          <Loading />
        )
      ) : studies.length === 0 ? (
        <p className="secondary">
          <MarkOf mark={EMPTY_MARK}>Sin estudios registrados.</MarkOf>
        </p>
      ) : (
        <ul className="studies" aria-label="Estudios">
          {studies.map((item) => (
            <li key={item.ledger_index}>
              <button
                className="command"
                aria-pressed={item.ledger_index === selected}
                onClick={() => setSelected(item.ledger_index)}
              >
                {item.synthetic === true ? "Fantoma simulado · " : ""}
                {item.dataset !== undefined ? "Ejemplo real · " : ""}
                <Mark pictogram={protocolPictogram(item.protocol)}>{protocolName(item.protocol)}</Mark> ·{" "}
                {utc(item.acquired)}
              </button>
            </li>
          ))}
        </ul>
      )}
      {study !== null && catalog !== null && (
        <StudyViewer
          key={study.ledger_index}
          study={study}
          catalog={catalog}
          indicators={indicators}
        />
      )}
    </section>
  );
}

/**
 * Las piezas del tablero de la ecografía: la cifra de estudios y, en píldoras, cuántos hay de cada
 * protocolo (con su dibujo y el nombre del catálogo, como en la lista), cuántos son fantomas
 * simulados o ejemplos reales (las mismas palabras que encabezan su fila) y cuántos no traen
 * calibración (el anillo de puntos en cian del aviso del visor: se ven, no se miden). Un recuento
 * a cero no se pinta: una píldora vacía no dice nada que la cifra de estudios no diga. Los
 * protocolos van en el orden del catálogo (el del selector) y, detrás, los que el catálogo no
 * nombre; si la última lectura falló, la cifra que queda es la anterior y va en cursiva (`stale`).
 */
export function StudyBoard({
  studies,
  order,
  protocolName,
  stale = false,
}: {
  studies: readonly ImagingStudy[];
  order: readonly string[];
  protocolName: (key: string) => string;
  stale?: boolean;
}) {
  const protocols = new Map<string, number>(order.map((key) => [key, 0]));
  for (const item of studies) protocols.set(item.protocol, (protocols.get(item.protocol) ?? 0) + 1);
  const phantoms = studies.filter((item) => item.synthetic === true).length;
  const samples = studies.filter((item) => item.dataset !== undefined).length;
  const uncalibrated = studies.filter((item) => item.calibration.length === 0).length;
  return (
    <div className="board-row ultrasound-board">
      <StatTile pictogram="probe-fan" label="Estudios" value={studies.length} stale={stale} />
      <ul className="board-tally" aria-label="Estudios por protocolo y procedencia">
        {[...protocols].filter(([, count]) => count > 0).map(([key, count]) => (
          <li key={key} className="ref-pill board-pill">
            <Mark pictogram={protocolPictogram(key)}>{protocolName(key)}</Mark>{" "}
            <span className="num">{formatNumber(count)}</span>
          </li>
        ))}
        {phantoms > 0 && (
          <li className="ref-pill board-pill">
            Fantoma simulado <span className="num">{formatNumber(phantoms)}</span>
          </li>
        )}
        {samples > 0 && (
          <li className="ref-pill board-pill">
            Ejemplo real <span className="num">{formatNumber(samples)}</span>
          </li>
        )}
        {uncalibrated > 0 && (
          <li className="ref-pill board-pill" style={markTint(MISSING_MARK)}>
            <MarkOf mark={MISSING_MARK}>sin calibración</MarkOf>{" "}
            <span className="num">{formatNumber(uncalibrated)}</span>
          </li>
        )}
      </ul>
    </div>
  );
}

/** Instante en UTC, que es el reloj de la mision; sin segundos, que aqui no aportan. */
function utc(iso: string): string {
  return `${iso.slice(0, 16).replace("T", " ")} UTC`;
}

/**
 * Fantomas de demostracion: imagenes dibujadas con la medida real conocida. Entran firmados
 * como simulados, asi que nunca pasan por dato de un tripulante (F.4.2: modo distinto).
 */
function PhantomButtons({
  catalog,
  subject,
  onCreated,
}: {
  catalog: ProtocolCatalog;
  subject: string;
  onCreated: (index: number) => Promise<void>;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  // Lo que salio mal al pedir un fantoma: el rechazo del backend o el fallo (`ReasonLine`).
  const [failure, setFailure] = useState<{ reason: unknown } | null>(null);
  const measurable = catalog.protocols.filter((item) => item.measures.length > 0);
  const create = async (protocol: string) => {
    setBusy(protocol);
    setFailure(null);
    try {
      const result = await api.imaging.phantom(protocol, subject);
      await onCreated(result.ledger_index);
    } catch (reason) {
      setFailure({ reason });
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="measure-actions" role="group" aria-label="Fantomas de demostración">
      <span className="secondary">Fantoma simulado:</span>
      {measurable.map((item) => (
        <button
          key={item.key}
          className="command"
          disabled={busy !== null}
          onClick={() => void create(item.key)}
        >
          <Mark pictogram={protocolPictogram(item.key)}>
            {busy === item.key ? "Generando…" : item.display}
          </Mark>
        </button>
      ))}
      {failure !== null && <ReasonLine reason={failure.reason} />}
    </div>
  );
}

/**
 * Ecografias reales de datasets abiertos (CC BY 4.0). Se rotulan con un numero, no con la
 * etiqueta del dataset: quien anota los signos no debe saber de antemano que "tiene".
 */
function SampleButtons({
  catalog,
  subject,
  onCreated,
}: {
  catalog: ProtocolCatalog;
  subject: string;
  onCreated: (index: number) => Promise<void>;
}) {
  const [samples, setSamples] = useState<ImagingSample[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [failure, setFailure] = useState<{ reason: unknown } | null>(null);
  useEffect(() => {
    api.imaging
      .samples()
      .then(setSamples)
      .catch((reason: unknown) => setFailure({ reason }));
  }, []);
  const label = (sample: ImagingSample) => {
    const sameProtocol = samples.filter((item) => item.protocol === sample.protocol);
    const name = catalog.protocols.find((item) => item.key === sample.protocol)?.display;
    return `${name ?? sample.protocol} ${sameProtocol.indexOf(sample) + 1}`;
  };
  const create = async (key: string) => {
    setBusy(key);
    setFailure(null);
    try {
      const result = await api.imaging.sample(key, subject);
      await onCreated(result.ledger_index);
    } catch (reason) {
      setFailure({ reason });
    } finally {
      setBusy(null);
    }
  };
  if (samples.length === 0 && failure === null) return null;
  return (
    <div className="measure-actions" role="group" aria-label="Ecografías reales de ejemplo">
      <span className="secondary">Ecografía real de ejemplo:</span>
      {samples.map((sample) => (
        <button
          key={sample.key}
          className="command"
          disabled={busy !== null}
          onClick={() => void create(sample.key)}
        >
          <Mark pictogram={protocolPictogram(sample.protocol)}>
            {busy === sample.key ? "Cargando…" : label(sample)}
          </Mark>
        </button>
      ))}
      {failure !== null && <ReasonLine reason={failure.reason} />}
    </div>
  );
}

function UploadForm({
  catalog,
  subject,
  onUploaded,
}: {
  catalog: ProtocolCatalog;
  subject: string;
  onUploaded: (index: number) => Promise<void>;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [protocol, setProtocol] = useState(catalog.protocols[0]?.key ?? "");
  const [acquired, setAcquired] = useState("");
  const [busy, setBusy] = useState(false);
  // Registrado (con o sin texto quemado que mirar), o lo que salio mal (`ReasonLine`).
  const [message, setMessage] = useState<
    { kind: "recorded"; attention: boolean; text: string } | { kind: "failed"; reason: unknown } | null
  >(null);

  const upload = async () => {
    if (file === null) return;
    setBusy(true);
    setMessage(null);
    try {
      // datetime-local no lleva zona: se interpreta en la hora de este equipo y se
      // envia en UTC, con zona explicita. El backend rechaza un instante sin zona.
      const when = acquired === "" ? undefined : new Date(acquired).toISOString();
      const result = await api.imaging.upload(file, protocol, subject, when);
      setMessage(
        result.burned_in_annotation === "YES"
          ? {
              kind: "recorded",
              attention: true,
              text:
                "Registrado. El ecógrafo declara texto dibujado en la imagen: puede contener " +
                "datos identificativos que la des-identificación de cabeceras no quita.",
            }
          : { kind: "recorded", attention: false, text: "Registrado y des-identificado." },
      );
      setFile(null);
      await onUploaded(result.ledger_index);
    } catch (reason) {
      setMessage({ kind: "failed", reason });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="silence-form" role="group" aria-label="Subir estudio">
      <FieldLabel concept="document">
        Estudio DICOM{" "}
        <input
          type="file"
          accept=".dcm,application/dicom"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
      </FieldLabel>
      <FieldLabel concept="protocol">
        Protocolo{" "}
        {/* La palabra es la opcion elegida; el pictograma, el del protocolo que nombra. */}
        <Mark pictogram={protocolPictogram(protocol)}>
          <select value={protocol} onChange={(event) => setProtocol(event.target.value)}>
            {catalog.protocols.map((item) => (
              <option key={item.key} value={item.key}>
                {item.display}
              </option>
            ))}
          </select>
        </Mark>
      </FieldLabel>
      <FieldLabel concept="time">
        Hora de adquisición{" "}
        <input
          type="datetime-local"
          value={acquired}
          onChange={(event) => setAcquired(event.target.value)}
        />
        <span className="secondary"> solo si el estudio no la trae con zona horaria</span>
      </FieldLabel>
      <div>
        <Command
          concept="upload"
          disabled={file === null || protocol === "" || busy}
          onClick={() => void upload()}
        >
          {busy ? "Subiendo…" : "Registrar estudio"}
        </Command>
      </div>
      {message !== null &&
        (message.kind === "failed" ? (
          <ReasonLine reason={message.reason} />
        ) : message.attention ? (
          <Attention>{message.text}</Attention>
        ) : (
          <p className="secondary">
            <MarkOf mark={OK_MARK}>{message.text}</MarkOf>
          </p>
        ))}
    </div>
  );
}

function StudyViewer({
  study,
  catalog,
  indicators,
}: {
  study: ImagingStudy;
  catalog: ProtocolCatalog;
  indicators: Record<string, Indicator>;
}) {
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [records, setRecords] = useState<MeasurementRecord[]>([]);
  const [recordsError, setRecordsError] = useState<RequestOutcome | null>(null);
  const [findingsCount, setFindingsCount] = useState(0);
  const [previous, setPrevious] = useState<Record<string, PreviousReading | null>>({});

  useEffect(() => {
    const keys = [...new Set(records.map((record) => record.key))];
    // Del mismo tripulante que el estudio: sin sujeto, comparaba con los valores de crew-01.
    Promise.all(keys.map((key) => api.observations(key, 5000, study.subject)))
      .then((lists) =>
        setPrevious(
          Object.fromEntries(
            keys.map((key, index) => [
              key,
              previousReading(lists[index]?.observations ?? [], study.acquired),
            ]),
          ),
        ),
      )
      .catch(() => setPrevious({})); // sin historial se muestra "—": no oculta la medida
  }, [records, study.acquired, study.subject]);
  const protocol = catalog.protocols.find((item) => item.key === study.protocol);
  const measures = protocol?.measures ?? [];
  const calibrated = study.calibration.length > 0;

  const loadRecords = useCallback(() => {
    api.imaging
      .measurements(study.ledger_index)
      .then((items) => {
        setRecords(items);
        setRecordsError(null);
      })
      // Un fallo aqui no es "sin medidas": puede ser un registro manipulado o una calibracion
      // firmada ilegible (409 del registro roto: cruz en rojo con el motivo del backend, §5.35.12;
      // hasta entonces iba con el triangulo), un «no» con su motivo o una peticion caida.
      .catch((reason: unknown) => setRecordsError(requestOutcome(reason)));
  }, [study.ledger_index]);
  useEffect(loadRecords, [loadRecords]);

  useEffect(() => {
    if (!playing || study.frames < 2) return;
    const timer = setInterval(() => setFrame((current) => (current + 1) % study.frames), 1000 / CINE_FPS);
    return () => clearInterval(timer);
  }, [playing, study.frames]);

  return (
    <div className="study-viewer">
      {study.burned_in_annotation === "YES" && (
        <p className="c-yellow">
          <Mark pictogram="shape-triangle">
            El ecógrafo declara texto dibujado en la imagen: puede contener datos identificativos.
          </Mark>
        </p>
      )}
      {study.synthetic === true && (
        <p className="secondary">
          Fantoma simulado, no un tripulante. {study.phantom_note}{" "}
          {Object.entries(study.ground_truth ?? {}).map(([measure, value]) => (
            <span key={measure}>
              Medida real: <span className="num">{truthValue(measure, value, indicators)}</span>.
            </span>
          ))}
        </p>
      )}
      {study.dataset !== undefined && (
        <p className="secondary">
          Ecografía real de un dataset público, no de este tripulante. {study.dataset.citation}.
          Licencia {study.dataset.license}.
        </p>
      )}
      {!calibrated && (
        <p className="c-cyan">
          <Mark pictogram="ring-dotted">
            Sin calibración declarada por el ecógrafo: se puede ver, no medir en milímetros.
          </Mark>
        </p>
      )}
      {calibrated && measures.length === 0 && (
        <p>
          <MarkOf mark={UNAVAILABLE_MARK}>Este protocolo todavía no tiene medidas: se puede ver.</MarkOf>
        </p>
      )}
      <Measurer
        study={study}
        frame={frame}
        measures={calibrated ? measures : []}
        minContour={catalog.method.min_contour_points?.value ?? 6}
        indicators={indicators}
        onRecorded={loadRecords}
      />
      {study.frames > 1 && (
        <div className="cine">
          <Command concept="cine" onClick={() => setPlaying(!playing)}>
            {playing ? "Pausa" : "Reproducir"}
          </Command>
          <input
            type="range"
            min={0}
            max={study.frames - 1}
            value={frame}
            aria-label="Fotograma"
            onChange={(event) => {
              setPlaying(false);
              setFrame(Number(event.target.value));
            }}
          />
          <span className="num secondary">
            {frame + 1} / {study.frames}
          </span>
        </div>
      )}
      {protocol !== undefined && protocol.source_grades.length > 0 && (
        <Fold data-ui="ultrasound-protocol-sources"
          concept="sourceText"
          label={
            <>
              Fuentes del protocolo (<span className="num">{formatNumber(protocol.source_grades.length)}</span>)
            </>
          }
        >
          <ul className="evidence">
            {protocol.source_grades.map((grade) => (
              <li key={grade.source}>
                {grade.source} <SourceGrade grade={grade} />
              </li>
            ))}
          </ul>
        </Fold>
      )}
      {protocol !== undefined && (
        <FindingsPanel
          study={study.ledger_index}
          protocol={protocol}
          onRecorded={setFindingsCount}
        />
      )}
      <DraftPanel
        key={records.length + findingsCount * 1000}
        study={study.ledger_index}
        measured={records.length > 0 || findingsCount > 0}
      />
      {recordsError !== null && (
        <p>
          <MarkOf mark={recordsError.mark}>{recordsError.text}</MarkOf>
        </p>
      )}
      {records.length > 0 && (
        <div className="quality-table">
        <table className="ledger" aria-label="Medidas del estudio">
          <thead>
            <tr>
              <Th concept="measure">Medida</Th>
              <Th concept="value">Valor</Th>
              <Th concept="previous">Anterior</Th>
              <Th concept="change">Cambio</Th>
              <Th concept="person">Medida por</Th>
            </tr>
          </thead>
          <tbody>
            {records.map((record) => (
              <tr key={record.ledger_index}>
                <td>
                  <IndicatorName
                    indicatorKey={record.key}
                    displayEs={indicators[record.key]?.display_es ?? record.key}
                  />
                </td>
                <td className="num">{shownValue(record.key, record.value, indicators)}</td>
                <EvolutionCells
                  record={record.key}
                  value={record.value}
                  previous={previous[record.key] ?? null}
                  indicators={indicators}
                />
                <td>{record.measured_by}</td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
    </div>
  );
}

/** La medida real de un fantoma. Las medidas con lado usan los decimales de cualquiera de los dos. */
function truthValue(measure: string, value: number, indicators: Record<string, Indicator>): string {
  const key = indicators[measure] !== undefined ? measure : `${measure}-right`;
  return shownValue(key, value, indicators);
}

/**
 * Anterior y cambio, en color neutro: estas medidas aun no alertan, y pintar el cambio en rojo
 * o amarillo seria una alerta sin validar. La flecha dice el sentido, como la palabra; sin color.
 */
export function EvolutionCells({
  record,
  value,
  previous,
  indicators,
}: {
  record: string;
  value: number;
  previous: PreviousReading | null;
  indicators: Record<string, Indicator>;
}) {
  if (previous === null) {
    return (
      <>
        <td className="secondary">primera medida</td>
        <td className="secondary">—</td>
      </>
    );
  }
  const delta = value - previous.value;
  const shownDelta = shownValue(record, Math.abs(delta), indicators);
  return (
    <>
      <td className="num">
        {shownValue(record, previous.value, indicators)}{" "}
        <span className="secondary">({previous.effective.slice(0, 10)})</span>
      </td>
      {/* F.5.6 h: nunca un "+". El sentido va en palabras, y la flecha lo acompana. */}
      <td className="num">
        {delta === 0 ? (
          "sin cambio"
        ) : (
          <Mark pictogram={delta > 0 ? "arrow-up" : "arrow-down"}>
            {delta > 0 ? "sube" : "baja"} {shownDelta}
          </Mark>
        )}
      </td>
    </>
  );
}

/** Toda cifra, por `format.ts`, con los decimales que fija el backend para el indicador. */
function shownValue(key: string, value: number, indicators: Record<string, Indicator>): string {
  const indicator = indicators[key];
  if (indicator === undefined) return formatNumber(value, 1);
  return `${formatNumber(value, indicator.decimals)} ${displayUnit(indicator.unit)}`;
}

function Measurer({
  study,
  frame,
  measures,
  minContour,
  indicators,
  onRecorded,
}: {
  study: ImagingStudy;
  frame: number;
  measures: MeasureSpec[];
  minContour: number;
  indicators: Record<string, Indicator>;
  onRecorded: () => void;
}) {
  const [operator, setOperator] = useOperator();
  const [spec, setSpec] = useState<MeasureSpec | null>(null);
  const [side, setSide] = useState<"right" | "left" | null>(null);
  const [calipers, setCalipers] = useState<CaliperState | null>(null);
  const [busy, setBusy] = useState(false);
  // Una medida registrada (se nombra con su indicador y su pictograma) o lo que salio mal.
  const [outcome, setOutcome] = useState<{ key: string; text: string } | { reason: unknown } | null>(null);

  const choose = (next: MeasureSpec) => {
    setSpec(next);
    setSide(null);
    setCalipers(startCalipers(stepsFor(next, minContour)));
    setOutcome(null);
  };
  const step = calipers === null ? null : currentStep(calipers);
  const complete = calipers !== null && isComplete(calipers);
  const ready = complete && operator.trim() !== "" && (spec?.lateral !== true || side !== null);

  const mark = (event: MouseEvent<SVGSVGElement>) => {
    if (calipers === null || step === null) return;
    const point = toImagePoint(
      event.clientX, event.clientY, event.currentTarget.getBoundingClientRect(),
      study.columns, study.rows,
    );
    // Funcional: dos clics seguidos se agrupan en un solo render, y partir del estado
    // capturado en el cierre perdia el primero de los dos.
    setCalipers((previous) => (previous === null ? previous : addPoint(previous, point, frame)));
  };

  const submit = async () => {
    if (calipers === null || spec === null) return;
    setBusy(true);
    try {
      const result = await api.imaging.measure(
        study.ledger_index,
        toRequest(calipers, spec.name, spec.lateral ? side : null, operator.trim()),
      );
      setOutcome({
        key: result.key,
        text: shownValue(result.key, result.value, indicators),
      });
      setCalipers(startCalipers(stepsFor(spec, minContour)));
      onRecorded();
    } catch (reason) {
      // El motivo del rechazo lo escribe el backend: se muestra tal cual.
      setOutcome({ reason });
    } finally {
      setBusy(false);
    }
  };

  const marks = useMemo(() => Object.entries(calipers?.marks ?? {}), [calipers]);

  return (
    <>
      <div className="frame">
        <img
          src={frameUrl(study.ledger_index, frame)}
          width={study.columns}
          height={study.rows}
          alt={`Fotograma ${frame + 1} del estudio`}
        />
        <svg
          viewBox={`0 0 ${study.columns} ${study.rows}`}
          preserveAspectRatio="none"
          className={step !== null ? "calipers active" : "calipers"}
          onClick={mark}
          role="img"
          aria-label="Marcas de calibre"
        >
          {marks
            .filter(([, item]) => item.frame === frame)
            .map(([label, item]) => (
              <g key={label}>
                {item.points.length > 1 && (
                  <polyline points={item.points.map(([x, y]) => `${x},${y}`).join(" ")} />
                )}
                {item.points.map(([x, y], index) => (
                  <circle key={index} cx={x} cy={y} r={Math.max(study.columns, study.rows) / 150} />
                ))}
              </g>
            ))}
        </svg>
      </div>

      {measures.length > 0 && (
        <div className="silence-form" role="group" aria-label="Medir">
          <div className="measure-actions">
            {measures.map((item) => (
              <button
                key={item.name}
                className="command"
                aria-pressed={spec?.name === item.name}
                onClick={() => choose(item)}
              >
                <Mark pictogram={measurePictogram(item)}>{item.display}</Mark>
              </button>
            ))}
          </div>
          {spec?.lateral === true && (
            <div className="measure-actions" role="group" aria-label="Lado">
              {(["right", "left"] as const).map((value) => (
                <button
                  key={value}
                  className="command"
                  aria-pressed={side === value}
                  onClick={() => setSide(value)}
                >
                  {/* El lado elegido lleva el anillo con punto de «elegido», como todo selector.
                      Sin flecha: el lado es del tripulante, no de la pantalla, y una flecha
                      hacia un lado de la pantalla lo confundiria. */}
                  <Chosen chosen={side === value}>{value === "right" ? "Derecho" : "Izquierdo"}</Chosen>
                </button>
              ))}
            </div>
          )}
          {step !== null && (
            <p className="c-magenta">
              <Mark pictogram="triangle-right-filled">{step.instruction}</Mark>
            </p>
          )}
          {complete && (
            <p className="secondary">
              <MarkOf mark={OK_MARK}>Marcas completas.</MarkOf>
            </p>
          )}
          {calipers !== null && (
            <FieldLabel concept="person" className="operator">
              Medido por{" "}
              <input
                value={operator}
                maxLength={64}
                onChange={(event) => setOperator(event.target.value)}
                placeholder="nombre o indicativo"
              />
            </FieldLabel>
          )}
          {calipers !== null && (
            <div className="measure-actions">
              <Command
                concept="undo"
                onClick={() => setCalipers((previous) => (previous === null ? previous : undo(previous)))}
              >
                Deshacer
              </Command>
              {step !== null && step.exact === null && (
                <Command
                  pictogram="polygon-dots"
                  onClick={() =>
                    setCalipers((previous) => (previous === null ? previous : closeContour(previous)))
                  }
                >
                  Cerrar contorno
                </Command>
              )}
              <Command concept="register" disabled={!ready || busy} onClick={() => void submit()}>
                {busy ? "Registrando…" : "Registrar medida"}
              </Command>
            </div>
          )}
          {outcome !== null &&
            ("key" in outcome ? (
              <p className="c-text">
                <IndicatorName
                  indicatorKey={outcome.key}
                  displayEs={indicators[outcome.key]?.display_es ?? outcome.key}
                />
                : {outcome.text}
              </p>
            ) : (
              <ReasonLine reason={outcome.reason} />
            ))}
        </div>
      )}
    </>
  );
}
