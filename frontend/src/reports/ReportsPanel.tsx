import { useCallback, useEffect, useState } from "react";

import {
  type CrewIdentity,
  type Indicator,
  type LabIncongruences,
  type ReportKind,
  type ScannedReport,
  api,
  reportPageUrl,
} from "../lib/api";
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
import { Loading } from "../components/Unavailable";
import { formatNumber } from "../lib/format";
import { markTint } from "../dashboard/TimelinePieces";
import { EMPTY_MARK, OK_MARK, REFUSED_MARK, type RequestOutcome, requestOutcome } from "../lib/marks";
import { useOperator } from "../lib/operator";
import { ReasonLine } from "../imaging/Attention";
import { LabReadings } from "./LabReadings";
import { identityMark, kindPictogram } from "./marks";

const KINDS: Record<ReportKind, string> = {
  analitica: "Analítica",
  "informe-especialista": "Informe de especialista",
  alta: "Informe de alta",
  otro: "Otro",
};

/**
 * Informes clinicos escaneados: se suben, se guarda el original firmado y se lee su texto.
 *
 * El texto lo saca el backend con OCR local y se muestra tal cual. Una pagina con confianza baja
 * se marca en amarillo con triangulo (tabla F.5-1, "attention required"): tesseract adivino, y
 * una cifra de esa pagina no se lee sin mirar el original, que esta siempre al lado. Sin OCR
 * instalado, la funcion se declara no disponible en gris y el original se sigue viendo.
 *
 * Cada clase de informe y cada veredicto de identidad llevan su pictograma junto a la palabra
 * (`./marks.ts`); los avisos conservan la forma que tenian como glifo, ahora en SVG (§5.32).
 * Desde la segunda pasada (§5.33.10) cada informe es un plegable con la hoja de su clase como
 * signo, y el resultado de subirlo lleva su marca: hecho, el triangulo de mirar o la cruz del
 * fallo; antes iba en gris sin forma, y un rechazo se leia igual que un «Registrado».
 *
 * Tablero (decisión del usuario, 2026-11-07): bajo el título, cuántos informes hay y cuántas
 * páginas guardan, y en píldoras cuántos hay de cada clase, con la hoja y la palabra de su
 * plegable. Solo en la concha de la maqueta (`BoardOnly`); el texto leído no se toca.
 */
export function ReportsPanel({ subject }: { subject: string }) {
  // `null` hasta la primera respuesta: «sin informes» antes de preguntar seria falso.
  const [reports, setReports] = useState<ScannedReport[] | null>(null);
  const [ocrNote, setOcrNote] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState<ReportKind>("analitica");
  const [operator, setOperator] = useOperator();
  const [busy, setBusy] = useState(false);
  // El resultado de subir un informe, y aparte la lectura del panel que fallo: compartir un solo
  // estado hacia que un rechazo posterior borrase la cruz y volviera «Cargando…» sin peticion.
  const [message, setMessage] = useState<UploadOutcome | null>(null);
  const [loadError, setLoadError] = useState<RequestOutcome | null>(null);
  const [identity, setIdentity] = useState<CrewIdentity | null>(null);
  const [crossed, setCrossed] = useState<LabIncongruences | null>(null);
  // El catalogo, para nombrar un analito con su nombre y su pictograma, no con su clave.
  const [indicators, setIndicators] = useState<Record<string, Indicator>>({});

  const load = useCallback(() => {
    Promise.all([
      api.reports.ocr(),
      api.reports.list(subject),
      api.reports.identity(subject),
      api.reports.incongruences(subject),
      api.indicators(),
    ])
      .then(([status, items, declared, found, catalogue]) => {
        setOcrNote(status.available ? null : status.note);
        setReports(items);
        setIdentity(declared);
        setCrossed(found);
        setIndicators(Object.fromEntries(catalogue.indicators.map((item) => [item.key, item])));
        setLoadError(null);
      })
      .catch((reason: unknown) => setLoadError(requestOutcome(reason)));
  }, [subject]);
  useEffect(load, [load]);

  const upload = async () => {
    if (file === null) return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await api.reports.upload(file, kind, subject, operator.trim());
      setMessage(
        result.low_confidence_pages.length > 0
          ? {
              kind: "recorded",
              attention: true,
              text: `Registrado. Páginas con lectura poco fiable: ${result.low_confidence_pages.join(", ")}.`,
            }
          : { kind: "recorded", attention: false, text: "Registrado." },
      );
      setFile(null);
      load();
    } catch (reason) {
      setMessage({ kind: "failed", reason });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section data-ui="reports" className="panel" aria-label="Informes escaneados">
      <PanelTitle pictogram="pages-stack">Informes escaneados</PanelTitle>
      {ocrNote !== null && (
        <p className="c-gray">
          <Mark pictogram="slash-circle">{ocrNote}</Mark>
        </p>
      )}
      {reports !== null && reports.length > 0 && (
        <BoardOnly>
          <ReportBoard reports={reports} stale={loadError !== null} />
        </BoardOnly>
      )}
      <IdentityForm subject={subject} identity={identity} onSaved={load} />
      {/* Formulario secundario: en el tablero, tras «Ver detalle» (lote «muestra», 2026-11-08). El
          resultado de subirlo, los avisos y la lista quedan fuera, a la vista. */}
      <BoardDetail label="Subir informe escaneado">
        <div className="silence-form">
          <FieldLabel concept="document">
            Documento (PDF, PNG, JPEG o TIFF){" "}
            <input
              type="file"
              accept="application/pdf,image/png,image/jpeg,image/tiff"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </FieldLabel>
          <FieldLabel concept="type">
            Tipo{" "}
            {/* La palabra es la opcion elegida; el pictograma, el de la clase que nombra. */}
            <Mark pictogram={kindPictogram(kind)}>
              <select value={kind} onChange={(event) => setKind(event.target.value as ReportKind)}>
                {(Object.keys(KINDS) as ReportKind[]).map((key) => (
                  <option key={key} value={key}>
                    {KINDS[key]}
                  </option>
                ))}
              </select>
            </Mark>
          </FieldLabel>
          <FieldLabel concept="person" className="operator">
            Registrado por{" "}
            <input value={operator} maxLength={64} onChange={(event) => setOperator(event.target.value)} />
          </FieldLabel>
          <Command
            concept="upload"
            disabled={busy || file === null || operator.trim() === ""}
            onClick={() => void upload()}
          >
            {busy ? "Leyendo…" : "Registrar informe"}
          </Command>
        </div>
      </BoardDetail>
      {loadError !== null && (
        <p>
          <MarkOf mark={loadError.mark}>{loadError.text}</MarkOf>
        </p>
      )}
      {message !== null && <UploadLine outcome={message} />}
      {crossed !== null && <Incongruences crossed={crossed} indicators={indicators} />}
      {reports === null ? (
        // Sin respuesta todavia; si la lectura fallo, ya lo dice la cruz roja de arriba.
        loadError === null && (
          <Loading />
        )
      ) : reports.length === 0 ? (
        <p className="secondary">
          <MarkOf mark={EMPTY_MARK}>Sin informes registrados.</MarkOf>
        </p>
      ) : (
        reports
          .slice()
          .reverse()
          .map((report) => (
            <ReportView key={report.ledger_index} report={report} operator={operator} onChanged={load} />
          ))
      )}
    </section>
  );
}

/**
 * Las piezas del tablero de los informes: la cifra de informes, la de páginas guardadas (las de
 * todos, también las de un informe que no se usa: el original firmado está ahí) y, en píldoras,
 * cuántos hay de cada clase en el orden del selector, y cuántos no son de este tripulante (el
 * triángulo amarillo y la palabra «no se usa» de su plegable). Una clase sin informes no se pinta;
 * si la última lectura falló, las cifras que quedan son las anteriores y van en cursiva.
 */
export function ReportBoard({ reports, stale = false }: { reports: readonly ScannedReport[]; stale?: boolean }) {
  const pages = reports.reduce((sum, report) => sum + report.pages, 0);
  const kinds = (Object.keys(KINDS) as ReportKind[])
    .map((kind) => ({ kind, count: reports.filter((report) => report.kind === kind).length }))
    .filter((entry) => entry.count > 0);
  const unusable = reports.filter((report) => report.identity !== undefined && !report.identity.usable).length;
  return (
    <div className="board-row reports-board">
      <div className="board-stats" role="group" aria-label="Informes registrados">
        <StatTile pictogram="pages-stack" label="Informes" value={reports.length} stale={stale} />
        <StatTile concept="document" label="Páginas" value={pages} stale={stale} />
      </div>
      <ul className="board-tally" aria-label="Informes por tipo">
        {kinds.map((entry) => (
          <li key={entry.kind} className="ref-pill board-pill">
            <Mark pictogram={kindPictogram(entry.kind)}>{KINDS[entry.kind]}</Mark>{" "}
            <span className="num">{formatNumber(entry.count)}</span>
          </li>
        ))}
        {/* El filete en el amarillo de su marca, como el triángulo (`markTint`). */}
        {unusable > 0 && (
          <li className="ref-pill board-pill" style={markTint(REFUSED_MARK)}>
            <Mark pictogram="shape-triangle" color="yellow">
              no se usa
            </Mark>{" "}
            <span className="num">{formatNumber(unusable)}</span>
          </li>
        )}
      </ul>
    </div>
  );
}

/**
 * Nombre y fecha de nacimiento del tripulante: con ellos se coteja que cada informe subido es
 * suyo (Polaris `identidad_paciente`). Se guardan firmados en el ledger, aparte del perfil.
 */
function IdentityForm({
  subject,
  identity,
  onSaved,
}: {
  subject: string;
  identity: CrewIdentity | null;
  onSaved: () => void;
}) {
  const [operator] = useOperator();
  const [givenName, setGivenName] = useState("");
  const [surnames, setSurnames] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [failure, setFailure] = useState<{ reason: unknown } | null>(null);
  const save = async () => {
    setFailure(null);
    try {
      await api.reports.declareIdentity({
        subject,
        given_name: givenName.trim(),
        surnames: surnames.trim(),
        birth_date: birthDate,
        declared_by: operator.trim(),
      });
      onSaved();
    } catch (reason) {
      setFailure({ reason });
    }
  };
  return (
    <Fold data-ui="reports-identity"
      concept="identity"
      className="report"
      label={
        <>
          Identidad para cotejar informes:{" "}
          {identity?.declared ? (
            `${identity.given_name} ${identity.surnames}`
          ) : (
            <Mark pictogram="ring-dotted">sin declarar</Mark>
          )}
        </>
      }
    >
      <div className="silence-form">
        <FieldLabel concept="person">
          Nombre de pila <input value={givenName} maxLength={80} onChange={(e) => setGivenName(e.target.value)} />
        </FieldLabel>
        <FieldLabel concept="person">
          Apellidos <input value={surnames} maxLength={120} onChange={(e) => setSurnames(e.target.value)} />
        </FieldLabel>
        <FieldLabel concept="date">
          Fecha de nacimiento <input type="date" value={birthDate} onChange={(e) => setBirthDate(e.target.value)} />
        </FieldLabel>
        <Command
          concept="identity"
          disabled={givenName.trim() === "" || birthDate === "" || operator.trim() === ""}
          onClick={() => void save()}
        >
          Declarar identidad
        </Command>
        {failure !== null && <ReasonLine reason={failure.reason} />}
      </div>
    </Fold>
  );
}

export function ReportView({
  report,
  operator,
  onChanged,
}: {
  report: ScannedReport;
  operator: string;
  onChanged: () => void;
}) {
  const [page, setPage] = useState(1);
  const read = report.ocr.pages.find((item) => item.page === page);
  const check = report.identity;
  // El signo del plegable es la hoja de su clase, y la palabra de la clase va justo detras.
  const kind = kindPictogram(report.kind);
  const recorded = `${report.recorded.slice(0, 16).replace("T", " ")} UTC`;
  if (check !== undefined && !check.usable) {
    // No es de este tripulante: ni su texto ni su original se muestran (son datos de otra persona).
    return (
      <Fold data-ui="report"
        pictogram={kind}
        className="report"
        label={
          <>
            {KINDS[report.kind]} · {recorded} ·{" "}
            <Mark pictogram="shape-triangle" color="yellow">
              no se usa
            </Mark>
          </>
        }
      >
        <p className="c-yellow">
          <Mark pictogram="shape-triangle">
            Este informe no es de este tripulante: {check.explanation}.
          </Mark>
        </p>
      </Fold>
    );
  }
  const identity = check === undefined ? null : identityMark(check.verdict);
  return (
    <Fold data-ui="report"
      pictogram={kind}
      className="report"
      label={
        <>
          {KINDS[report.kind]} · {recorded} · <span className="num">{formatNumber(report.pages)}</span> págs. ·{" "}
          {report.recorded_by}
        </>
      }
    >
      <div className="measure-actions">
        {Array.from({ length: report.pages }, (_, index) => index + 1).map((number) => (
          <button
            key={number}
            className="command"
            aria-pressed={number === page}
            onClick={() => setPage(number)}
          >
            {/* Sin signo de concepto: un numero de pagina. El anillo con punto dice cual se ve. */}
            <Chosen chosen={number === page}>{formatNumber(number)}</Chosen>
          </button>
        ))}
      </div>
      {check !== undefined && identity !== null && check.verdict !== "coincide" && (
        <p className={identity.className ?? "secondary"}>
          <Mark pictogram={identity.pictogram}>Identidad: {check.explanation}.</Mark>
        </p>
      )}
      <div className="report-page">
        <img src={reportPageUrl(report.ledger_index, page)} alt={`Página ${page} del original`} />
        <div>
          {!report.ocr.available && (
            <p className="c-gray">
              <Mark pictogram="slash-circle">{report.ocr.note}</Mark>
            </p>
          )}
          {read?.low_confidence === true && (
            <p className="c-yellow">
              <Mark pictogram="shape-triangle">
                Lectura poco fiable (confianza{" "}
                <span className="num">{formatNumber(read.confidence ?? 0)}</span> de 100): no leas
                cifras de esta página sin mirar el original.
              </Mark>
            </p>
          )}
          {read?.deidentification?.verified === false && (
            <p className="c-yellow">
              <Mark pictogram="shape-triangle">
                Texto retenido: quedaban datos identificativos que no se pudieron enmascarar (
                {read.deidentification.remaining.join(", ")}). Consulta el original.
              </Mark>
            </p>
          )}
          {read !== undefined && read.text !== "" && <pre className="report-text">{read.text}</pre>}
        </div>
      </div>
      {report.lab_readings !== undefined && report.lab_readings.readings.length > 0 && (
        <LabReadings
          report={report.ledger_index}
          readings={report.lab_readings.readings}
          reportDate={report.lab_readings.date}
          operator={operator}
          onConfirmed={onChanged}
        />
      )}
    </Fold>
  );
}

/**
 * Dos informes de la misma extraccion que no dicen lo mismo: hay que mirarlo con los dos papeles
 * delante (F.5-1, amarillo con triangulo). No decide cual es el bueno.
 */
export function Incongruences({
  crossed,
  indicators,
}: {
  crossed: LabIncongruences;
  indicators: Record<string, Indicator>;
}) {
  if (crossed.incongruences.length === 0 && crossed.undated_reports === 0) return null;
  return (
    <div>
      {crossed.incongruences.map((item) => (
        <p key={`${item.sample}:${item.key}`} className="c-yellow">
          <Mark pictogram="shape-triangle">
            <IndicatorName indicatorKey={item.key} displayEs={indicators[item.key]?.display_es ?? item.key} />,{" "}
            {item.sample}: no coinciden{" "}
            {item.readings.map((reading, index) => (
              <span key={reading.report}>
                {index > 0 ? " / " : ""}
                <span className="num">{formatNumber(reading.value, 2)}</span> ({reading.report})
              </span>
            ))}
          </Mark>
        </p>
      ))}
      {crossed.undated_reports > 0 && (
        <p className="c-gray">
          <Mark pictogram="slash-circle">
            <span className="num">{formatNumber(crossed.undated_reports)}</span> analíticas sin fecha
            legible: no se cruzan con las demás
          </Mark>
        </p>
      )}
    </div>
  );
}

/** Registrado (con paginas poco fiables que mirar, o sin nada), o lo que salio mal al subirlo. */
type UploadOutcome = { kind: "recorded"; attention: boolean; text: string } | { kind: "failed"; reason: unknown };

/**
 * El resultado de subir un informe con su marca: hecho; el triangulo amarillo si hay paginas poco
 * fiables; o `ReasonLine`, que separa el rechazo del backend del fallo de la peticion.
 */
function UploadLine({ outcome }: { outcome: UploadOutcome }) {
  if (outcome.kind === "failed") return <ReasonLine reason={outcome.reason} />;
  if (outcome.attention) {
    return (
      <p className="c-yellow">
        <Mark pictogram="shape-triangle">{outcome.text}</Mark>
      </p>
    );
  }
  return (
    <p className="secondary">
      <MarkOf mark={OK_MARK}>{outcome.text}</MarkOf>
    </p>
  );
}
