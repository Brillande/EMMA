import { useCallback, useEffect, useState } from "react";

import { Command } from "../components/Command";
import { FieldLabel } from "../components/FieldLabel";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { Th } from "../components/Th";
import {
  type SpineReview,
  type VolumeCleaning,
  type VolumeSample,
  type VolumeSegmentation,
  type VolumeStudy,
  api,
  postVolume,
} from "../lib/api";
import { displayUnit, formatNumber } from "../lib/format";
import { EMPTY_MARK, LOADING_MARK, MISSING_MARK, type RequestOutcome, requestOutcome } from "../lib/marks";
import { useOperator } from "../lib/operator";
import { LesionComparison } from "./LesionComparison";
import { type DensityBlock, densityCell, densityNotes, densityOf, previousSegmentation } from "./comparison";
import { ContrastPhasePanel } from "./ContrastPhasePanel";
import { ATTENTION_MARK, CLEANED_MARK, UNAVAILABLE_MARK, modalityMark, spineNoticeMark } from "./marks";
import { POLARIS_PRESETS, PolarisViewer } from "./PolarisViewer";
import { cleaningOf, uploadOutcome } from "./upload";
import { VolumeViewer } from "./VolumeViewer";

/** Un volumen que la puerta no dejo entrar: su motivo, la oferta del backend y EL fichero rechazado. */
interface Refusal {
  file: File;
  detail: string;
  offer: { text: string; label: string } | null;
}

/**
 * Volumenes TAC/RM y su segmentacion automatica (visor 3D de Polaris).
 *
 * Hoy no vuela ningun TAC (en la ISS solo hay ecografia): esto es para imagen de referencia previa
 * al vuelo y para Tierra. La segmentacion la hace un programa local (TotalSegmentator) si esta
 * instalado; si no, se declara no disponible en gris (con el circulo tachado, `marks.ts`) y los
 * estudios se ven igual. Todo lo que marca el modelo va rotulado como sin validar. Cada estudio
 * de la lista lleva el dibujo de su modalidad (gantry para CT, iman para MR) junto a la sigla del
 * backend.
 *
 * La puerta de datos personales: un NIfTI con texto en la cabecera no entra, y el backend dice que
 * campo. Si ademas dice que limpiar la cabecera aqui lo dejaria entrar, se ensena su oferta y un
 * boton con su rotulo que reenvia EL MISMO fichero rechazado (el guardado en el rechazo, no lo que
 * haya ahora en el selector) pidiendo la limpieza. Nunca se pide sola: solo al pulsar. Un estudio
 * guardado limpio lo dice despues, con la nota, los campos y las dos huellas que firma el backend.
 *
 * Segunda pasada (§5.33.9): el titulo lleva el gantry (el TAC), cada mando y cada rotulo el signo
 * de su concepto (`lib/uiMarks.ts`), los TAC de ejemplo la pila de cortes de `icons/sets/volumes.ts`,
 * y los estados del panel su marca: el anillo punteado sin color de la lista vacia, la flecha que
 * gira mientras se limpia la cabecera.
 */
export function VolumesPanel({ subject }: { subject: string }) {
  const [studies, setStudies] = useState<VolumeStudy[]>([]);
  const [samples, setSamples] = useState<VolumeSample[]>([]);
  const [segmenter, setSegmenter] = useState<{ available: boolean; note: string | null; presets: { key: string; nombre: string }[] } | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [preset, setPreset] = useState("higado");
  const [file, setFile] = useState<File | null>(null);
  const [modality, setModality] = useState<"CT" | "MR">("CT");
  const [operator, setOperator] = useOperator();
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<RequestOutcome | null>(null);
  const [refusal, setRefusal] = useState<Refusal | null>(null);

  const load = useCallback(() => {
    Promise.all([api.volumes.list(subject), api.volumes.samples(), api.volumes.segmenter()])
      .then(([items, catalog, status]) => {
        setStudies(items);
        setSamples(catalog);
        setSegmenter(status);
      })
      .catch((reason: unknown) => setMessage(requestOutcome(reason)));
  }, [subject]);
  useEffect(load, [load]);

  const run = async (label: string, action: () => Promise<number | null>) => {
    setBusy(label);
    setMessage(null);
    try {
      const index = await action();
      load();
      if (index !== null) setSelected(index);
    } catch (reason) {
      setMessage(requestOutcome(reason));
    } finally {
      setBusy(null);
    }
  };

  // `clean` solo es verdadero desde el boton de la oferta, con el fichero que se rechazo.
  const upload = (target: File, clean: boolean) =>
    run(clean ? "limpiar" : "subir", async () => {
      setRefusal(null);
      const outcome = uploadOutcome(await postVolume(target, modality, subject, operator.trim(), clean));
      if (outcome.kind === "saved") return outcome.ledger_index;
      setRefusal({ file: target, detail: outcome.detail, offer: outcome.offer });
      return null;
    });

  const segment = (study: number) =>
    run("segmentar", async () => {
      const { job } = await api.volumes.segment(study, preset);
      for (;;) {
        await new Promise((resolve) => setTimeout(resolve, 3000));
        const status = await api.volumes.job(job);
        if (status.state === "done") return study;
        if (status.state === "failed") throw new Error(status.error ?? "la segmentación falló");
      }
    });

  const study = studies.find((item) => item.ledger_index === selected) ?? null;
  const latest = study?.segmentations.at(-1) ?? null;
  const previous = latest === null ? null : previousSegmentation(studies, latest);

  return (
    <section data-ui="volumes" className="panel" aria-label="Volúmenes 3D">
      <PanelTitle pictogram="gantry">Volúmenes 3D (TAC/RM)</PanelTitle>
      <p className="secondary">
        Hoy no vuela ningún TAC; en la ISS la única imagen médica es la ecografía. Estos volúmenes son
        imagen de referencia previa al vuelo o de Tierra.
      </p>
      {segmenter !== null && !segmenter.available && (
        <p>
          <MarkOf mark={UNAVAILABLE_MARK}>{segmenter.note}</MarkOf>
        </p>
      )}
      {samples.length > 0 && (
        <div className="measure-actions" role="group" aria-label="TAC reales de ejemplo">
          <span className="secondary">TAC real de ejemplo:</span>
          {samples.map((sample) => (
            <Command
              key={sample.key}
              pictogram="slices-stacked"
              disabled={busy !== null}
              onClick={() => void run(sample.key, async () => (await api.volumes.sample(sample.key, subject)).ledger_index)}
            >
              {busy === sample.key ? "Cargando…" : sample.nombre}
            </Command>
          ))}
        </div>
      )}
      <div className="silence-form">
        <FieldLabel concept="upload">
          Volumen NIfTI (.nii, .nii.gz){" "}
          <input
            type="file"
            accept=".nii,.gz"
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setRefusal(null); // la oferta era para el fichero rechazado, no para el que se elija ahora
            }}
          />
        </FieldLabel>
        <FieldLabel concept="type">
          Modalidad{" "}
          <select value={modality} onChange={(event) => setModality(event.target.value as "CT" | "MR")}>
            <option value="CT">TAC</option>
            <option value="MR">RM</option>
          </select>
        </FieldLabel>
        <FieldLabel concept="person" className="operator">
          Registrado por{" "}
          <input value={operator} maxLength={64} onChange={(event) => setOperator(event.target.value)} />
        </FieldLabel>
        <Command
          concept="upload"
          disabled={busy !== null || file === null || operator.trim() === ""}
          onClick={() => {
            if (file !== null) void upload(file, false);
          }}
        >
          {busy === "subir" ? "Registrando…" : "Registrar volumen"}
        </Command>
      </div>
      {message !== null && (
        <p>
          <MarkOf mark={message.mark}>{message.text}</MarkOf>
        </p>
      )}
      {refusal !== null && (
        <div role="alert" aria-label="Volumen no guardado">
          <p>
            <MarkOf mark={ATTENTION_MARK}>{refusal.detail}</MarkOf>
          </p>
          {refusal.offer !== null && (
            <>
              <p className="secondary">{refusal.offer.text}</p>
              <div className="measure-actions">
                <Command
                  concept="upload"
                  disabled={busy !== null || operator.trim() === ""}
                  onClick={() => void upload(refusal.file, true)}
                >
                  {refusal.offer.label}
                </Command>
              </div>
            </>
          )}
        </div>
      )}
      {busy === "limpiar" && (
        <p className="secondary">
          <MarkOf mark={LOADING_MARK}>Limpiando la cabecera y comprobando de nuevo…</MarkOf>
        </p>
      )}
      {studies.length === 0 ? (
        <p className="secondary">
          <MarkOf mark={EMPTY_MARK}>Sin volúmenes registrados.</MarkOf>
        </p>
      ) : (
        <ul className="studies" aria-label="Volúmenes">
          {studies.map((item) => (
            <li key={item.ledger_index}>
              <button className="command" data-ui-view="" aria-pressed={item.ledger_index === selected} onClick={() => setSelected(item.ledger_index)}>
                {item.dataset !== undefined ? "Ejemplo real · " : ""}
                <MarkOf mark={modalityMark(item.modality)}>{item.modality}</MarkOf> ·{" "}
                <span className="num">{item.shape.map((n) => formatNumber(n)).join("×")}</span> ·{" "}
                {item.recorded.slice(0, 16).replace("T", " ")} UTC
                {cleaningOf(item) !== null ? " · cabecera limpiada" : ""}
              </button>
            </li>
          ))}
        </ul>
      )}
      {study !== null && (
        <>
          {study.dataset !== undefined && (
            <p className="secondary">
              TAC real de un dataset público, no de este tripulante. {study.dataset.citation}. Licencia{" "}
              {study.dataset.license}.
            </p>
          )}
          <CleaningNotice cleaned={cleaningOf(study)} stored={study.sha256 ?? null} />
          {segmenter?.available === true && (
            <div className="measure-actions">
              <FieldLabel concept="segment">
                Segmentar{" "}
                <select value={preset} onChange={(event) => setPreset(event.target.value)}>
                  {segmenter.presets.map((item) => (
                    <option key={item.key} value={item.key}>
                      {item.nombre}
                    </option>
                  ))}
                </select>
              </FieldLabel>
              <Command concept="segment" disabled={busy !== null} onClick={() => void segment(study.ledger_index)}>
                {busy === "segmentar" ? "Segmentando… (minutos)" : "Segmentar en local"}
              </Command>
            </div>
          )}
          {latest?.cadena_vertebral != null && <SpineNotice review={latest.cadena_vertebral} />}
          {latest === null ? (
            <p className="secondary">
              <MarkOf mark={EMPTY_MARK}>Sin segmentación: el volumen está registrado y firmado.</MarkOf>
            </p>
          ) : (
            // El de Polaris donde Polaris sabe pintar el organo; el propio, solo para el resto (ojos).
            POLARIS_PRESETS.has(latest.preset) ? (
              <PolarisViewer key={latest.ledger_index} segmentation={latest} />
            ) : (
              <VolumeViewer key={latest.ledger_index} segmentation={latest} />
            )
          )}
          <ContrastPhasePanel
            key={study.ledger_index}
            study={study}
            operator={operator}
            onOperator={setOperator}
            onDeclared={load}
          />
          {latest !== null && <LesionDensities segmentation={latest} />}
          {latest !== null && previous !== null && (
            <LesionComparison
              key={`${previous.ledger_index}-${latest.ledger_index}`}
              before={previous.ledger_index}
              after={latest.ledger_index}
            />
          )}
        </>
      )}
    </section>
  );
}

/**
 * Aviso del control de la cadena vertebral, junto al visor. Una segmentacion salio con 40 de 60
 * huesos y el visor la enseño como buena: lo que falta se dice aqui. Todo el texto es del backend;
 * la interfaz solo pone el color del nivel que el backend declara, con su significado de la tabla
 * F.5-1 (amarillo, requiere atencion; cian, dato ausente), y un pictograma de forma distinta
 * (`spineNoticeMark`) para que no dependa solo del color (F.5.10 e).
 */
function SpineNotice({ review }: { review: SpineReview }) {
  if (review.nivel === null || review.aviso === null) return null;
  return (
    <div role="status" aria-label="Control de la cadena vertebral">
      <p>
        <MarkOf mark={spineNoticeMark(review.nivel)}>{review.aviso}</MarkOf>
      </p>
      <ul>
        {review.listas.map((list) => (
          <li key={list.titulo} className={spineNoticeMark(list.nivel).className}>
            <Mark pictogram={spineNoticeMark(list.nivel).pictogram}>{list.titulo}</Mark> (
            <span className="num">{formatNumber(list.elementos.length)}</span>): {list.elementos.join(", ")}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Un estudio cuya cabecera se limpio en EMMA al entrar. La nota es del backend y va tal cual; aqui
 * solo hay rotulos, los nombres de campo que el asiento declara (nunca su contenido: el backend no
 * lo guarda) y las dos huellas. Sin color: no es un estado ni una alerta, es procedencia; la goma
 * de borrar junto a la nota dice de que va.
 */
function CleaningNotice({ cleaned, stored }: { cleaned: VolumeCleaning | null; stored: string | null }) {
  if (cleaned === null) return null;
  return (
    <div role="note" aria-label="Cabecera limpiada al entrar">
      <p className="secondary">
        <MarkOf mark={CLEANED_MARK}>{cleaned.note}</MarkOf>
      </p>
      <p className="secondary">
        Campos vaciados (<span className="num">{formatNumber(cleaned.fields.length)}</span>): {cleaned.fields.join(", ")}
      </p>
      <p className="secondary">
        Huella del fichero recibido (SHA-256, <span className="num">{formatNumber(cleaned.received_size_bytes)}</span>{" "}
        bytes): <code>{cleaned.received_sha256}</code>
      </p>
      {stored !== null && (
        <p className="secondary">
          Huella del volumen guardado y firmado (SHA-256): <code>{stored}</code>
        </p>
      )}
    </div>
  );
}

/**
 * Densidad (HU) de las lesiones candidatas de UN estudio. El dato ya viajaba en cada segmentacion
 * de `GET /api/volumes` y solo se veia al comparar dos estudios (`LesionComparison`); aqui se
 * ensena igual: mediana y percentiles 10 y 90 por `lib/format`, la referencia y las notas del
 * backend tal cual, y ningun veredicto. No se colorea por valor: no hay un rango que pintar, y
 * hacerlo seria clasificar. Gris ("no disponible", circulo tachado) con la palabra del backend
 * para la lesion con pocos voxeles; cian (dato ausente, anillo punteado junto a la raya de la
 * celda vacia) si la lesion no trae densidad.
 */
function LesionDensities({ segmentation }: { segmentation: VolumeSegmentation }) {
  const block = (segmentation as { densidad?: DensityBlock | null }).densidad ?? null;
  if (block === null || segmentation.lesiones.length === 0) return null;
  const hu = ` (${displayUnit(block.unidad)})`;
  return (
    <div className="density-notes">
      {block.disponible && (
        <div className="quality-table">
        <table className="ledger" aria-label="Densidad de las lesiones candidatas de este estudio">
          <thead>
            <tr>
              <Th pictogram="blob">Lesión</Th>
              <Th pictogram="square-hatched">Densidad{hu}: mediana (p10 a p90)</Th>
              <Th concept="value">Vóxeles</Th>
            </tr>
          </thead>
          <tbody>
            {segmentation.lesiones.map((lesion) => {
              const cell = densityCell(densityOf(lesion));
              return (
                <tr key={lesion.id}>
                  <th scope="row">L{lesion.id}</th>
                  <td>
                    {cell.kind === "ausente" && <MarkOf mark={MISSING_MARK}>—</MarkOf>}
                    {cell.kind === "no-valorable" && (
                      <MarkOf mark={UNAVAILABLE_MARK} title={cell.motivo ?? undefined}>
                        {block.no_valorable}
                      </MarkOf>
                    )}
                    {cell.kind === "cifra" && (
                      <span className="num">
                        {formatNumber(cell.mediana, 1)} ({formatNumber(cell.p10, 1)} a {formatNumber(cell.p90, 1)})
                      </span>
                    )}
                  </td>
                  <td className="num">
                    {cell.kind === "ausente" ? <MarkOf mark={MISSING_MARK}>—</MarkOf> : formatNumber(cell.voxeles)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>
      )}
      {block.referencia !== null && block.referencia.mediana_hu !== null && (
        <p className="secondary">
          Referencia{hu}: {block.referencia.nombre} ·{" "}
          <span className="num">{formatNumber(block.referencia.mediana_hu, 1)}</span> ·{" "}
          <span className="num">{formatNumber(block.referencia.voxeles)}</span> vóxeles
        </p>
      )}
      <p className="secondary">
        Mínimo de vóxeles para dar cifra: <span className="num">{formatNumber(block.minimo_voxeles)}</span>
      </p>
      {densityNotes({ antes: null, despues: block }).map((note) => (
        <p key={note}>
          <MarkOf mark={ATTENTION_MARK}>{note}</MarkOf>
        </p>
      ))}
    </div>
  );
}
