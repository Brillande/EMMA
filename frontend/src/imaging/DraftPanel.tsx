import { type ReactNode, useCallback, useEffect, useState } from "react";

import {
  type CommitteeDossier,
  type DraftSignoff,
  type InterpretationDraft,
  type SecondSignatureRule,
  type SeenQuote,
  type SourceQuote,
  api,
  sourceQuoteApi,
} from "../lib/api";
import { Command } from "../components/Command";
import { FieldLabel } from "../components/FieldLabel";
import { Fold } from "../components/Fold";
import { Mark } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { formatNumber } from "../lib/format";
import { useOperator } from "../lib/operator";
import { uiPictogram } from "../lib/uiMarks";
import { ReasonLine } from "./Attention";
import {
  type Looked,
  citesReport as isReportCite,
  collationLine,
  isCurrent,
  provenance,
  quoteStyle,
  secondSignatureOffer,
  seenOf,
  viewKey,
} from "./sourceQuote";

/**
 * Borrador de interpretacion del modelo local: se pide, se lee y se firma.
 *
 * Un borrador sin firma se rotula en amarillo —tabla F.5-1, "attention required"— porque es
 * justo eso: algo que una persona tiene que revisar antes de que valga nada. El texto y los
 * motivos de bloqueo los escribe el backend; aqui solo se muestran (invariante 7).
 *
 * El texto del modelo lleva siempre la hoja a trazos (`page-dashed`): es un borrador y se ve como
 * tal, firmado o no, distinto de un hallazgo anotado o de una medida (segregacion Clase C,
 * invariante 6). Las decisiones llevan la marca de hecho (`check`) o la de «no» (`slash-circle`),
 * las mismas de los mandos que las firman (`accept`, `reject` en `lib/uiMarks.ts`).
 * Desde la segunda pasada (§5.33.10) la hoja a trazos tambien va en el titulo y en «Pedir
 * borrador»: es el dibujo del borrador en toda el area, y ningun otro mando lo lleva.
 */
export function DraftPanel({ study, measured }: { study: number; measured: boolean }) {
  const [status, setStatus] = useState<{ available: boolean; note: string | null } | null>(null);
  const [drafts, setDrafts] = useState<InterpretationDraft[]>([]);
  const [busy, setBusy] = useState(false);
  // Lo que salio mal al leer o al pedir el borrador: rechazo del backend o fallo (`ReasonLine`).
  const [failure, setFailure] = useState<{ reason: unknown } | null>(null);

  const load = useCallback(() => {
    Promise.all([api.imaging.interpretation(), api.imaging.drafts(study)])
      .then(([availability, items]) => {
        setStatus(availability);
        setDrafts(items);
      })
      .catch((reason: unknown) => setFailure({ reason }));
  }, [study]);
  useEffect(load, [load]);

  const request = async () => {
    setBusy(true);
    setFailure(null);
    try {
      await api.imaging.requestDraft(study);
    } catch (reason) {
      setFailure({ reason });
    } finally {
      setBusy(false);
      load();
    }
  };

  return (
    <section data-ui="imaging-draft" className="draft-panel" aria-label="Borrador de interpretación">
      <PanelTitle as="h3" pictogram="page-dashed">
        Borrador de interpretación
      </PanelTitle>
      {status !== null && !status.available && (
        <p className="c-gray">
          <Mark pictogram="slash-circle">{status.note}</Mark>
        </p>
      )}
      <div className="measure-actions">
        <Command
          pictogram="page-dashed"
          disabled={busy || !measured || status?.available !== true}
          onClick={() => void request()}
        >
          {busy ? "Redactando…" : "Pedir borrador"}
        </Command>
        {!measured && (
          <span className="secondary">Primero hay que medir el estudio o anotar sus signos.</span>
        )}
      </div>
      {failure !== null && <ReasonLine reason={failure.reason} />}
      {drafts
        .slice()
        .reverse()
        .map((draft) => (
          <DraftCard key={draft.ledger_index} draft={draft} onSigned={load} />
        ))}
    </section>
  );
}

/**
 * Una decision de firma con su palabra: el dibujo del mando que la tomo (`accept`, `reject`), para
 * que «rechazar» y «rechazado» no lleven dos dibujos (§5.33.10). Hasta la segunda pasada el
 * rechazado llevaba la cruz, que es la de «cancelar» y la del fallo de una peticion.
 */
export function Decision({ decision, children }: { decision: "accepted" | "rejected"; children: ReactNode }) {
  return <Mark pictogram={uiPictogram(decision === "accepted" ? "accept" : "reject")}>{children}</Mark>;
}

export function DraftCard({ draft, onSigned }: { draft: InterpretationDraft; onSigned: () => void }) {
  if (draft.status === "blocked") {
    return (
      <div className="draft blocked">
        <p className="c-yellow">
          <Mark pictogram="shape-triangle">Borrador bloqueado antes de mostrarse:</Mark>
        </p>
        <ul>
          {(draft.reasons ?? []).map((reason) => (
            <li key={reason} className="secondary">
              {reason}
            </li>
          ))}
        </ul>
      </div>
    );
  }

  const { signoff, countersign, record } = draft;
  const pendingSecond = signoff !== null && record.second_signature_required && !record.complete;
  return (
    <div className="draft">
      {signoff === null ? (
        <p className="c-yellow">
          <Mark pictogram="shape-triangle">
            BORRADOR SIN VALIDAR · redactado por un modelo local ({draft.model})
          </Mark>
        </p>
      ) : (
        <p className="secondary">
          <Decision decision={signoff.decision}>
            {signoff.decision === "accepted" ? "Aceptado" : "Rechazado"}
          </Decision>{" "}
          por {signoff.signed_by}
          {signoff.comment ? ` — ${signoff.comment}` : ""}
        </p>
      )}
      {signoff !== null && <CitedSource signature={signoff} />}
      {(draft.committee ?? []).length > 0 && (
        <p className="secondary">Revisado por el comité local: {(draft.committee ?? []).join(", ")}</p>
      )}
      {draft.dossier && <Dossier dossier={draft.dossier} />}
      {pendingSecond && (
        <p className="c-yellow">
          <Mark pictogram="shape-triangle">
            Decisión de alto riesgo ({signoff.high_risk?.reason}): falta la segunda firma, de otra
            persona.
          </Mark>
        </p>
      )}
      {countersign !== null && (
        <p className={record.disagreement ? "c-yellow" : "secondary"}>
          {record.disagreement && (
            <>
              <Mark pictogram="shape-triangle">Las dos firmas discrepan.</Mark>{" "}
            </>
          )}
          Segunda firma:{" "}
          <Decision decision={countersign.decision}>
            {countersign.decision === "accepted" ? "aceptado" : "rechazado"}
          </Decision>{" "}
          por {countersign.signed_by}
          {countersign.comment ? ` — ${countersign.comment}` : ""}
        </p>
      )}
      {countersign !== null && <CitedSource signature={countersign} />}
      {countersign !== null && <Collation draft={draft} />}
      {countersign !== null && draft.countersign_note && (
        <p className="c-yellow">
          <Mark pictogram="shape-triangle">{draft.countersign_note}</Mark>
        </p>
      )}
      {signoff === null && (draft.language_notes ?? []).length > 0 && (
        <div>
          <p className="c-yellow">
            <Mark pictogram="shape-triangle">Revisa antes de firmar (no bloquean):</Mark>
          </p>
          <ul>
            {(draft.language_notes ?? []).map((note) => (
              <li key={note} className="secondary">
                {note}
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="draft-text">
        <Mark pictogram="page-dashed">{draft.text}</Mark>
      </p>
      {signoff === null && (
        <SignForm
          acceptLabel="Aceptar borrador"
          rejectLabel="Rechazar borrador"
          onSubmit={(body) => api.imaging.signDraft(draft.ledger_index, { ...body, text_sha256: draft.text_sha256 })}
          preview={(cite) => sourceQuoteApi.preview(draft.ledger_index, cite)}
          onDone={onSigned}
        />
      )}
      {pendingSecond && (
        <SignForm
          acceptLabel="Segunda firma: aceptar"
          rejectLabel="Segunda firma: rechazar"
          onSubmit={(body) =>
            api.imaging.countersignDraft(draft.ledger_index, { ...body, text_sha256: draft.text_sha256 })
          }
          preview={(cite) => sourceQuoteApi.preview(draft.ledger_index, cite)}
          strict
          rule={draft.second_signature_rule}
          onDone={onSigned}
        />
      )}
    </div>
  );
}

/**
 * Si la segunda firma se cotejo con la frase de un informe y, si no, por que: texto del backend
 * (`countersign_collation`), con pictograma, palabra y color. Una contrafirma que citaba otra cosa, o
 * nada, se admitia hasta el 2026-10-15; las que quedan se dicen no cotejadas en vez de verse
 * igual que una cotejada.
 */
export function Collation({ draft }: { draft: Pick<InterpretationDraft, "countersign_collation"> }) {
  const line = collationLine(draft.countersign_collation);
  if (line === null) return null;
  return (
    <p className={`c-${line.color}`}>
      <Mark pictogram={line.pictogram}>{line.text}</Mark>
    </p>
  );
}

/**
 * Lo que objeto el comite, junto y ordenado (Polaris `paso_consolidacion`): primero lo que cita
 * el borrador y cuenta, despues lo que no cita nada (sin fuente trazable, en gris: no bloquea).
 * Nada se esconde: lo que pasa del tope va a "diferidas".
 */
function Dossier({ dossier }: { dossier: CommitteeDossier }) {
  if (dossier.head.length === 0) return null;
  return (
    <Fold data-ui="imaging-objections"
      concept="objections"
      summaryClassName="secondary"
      label={
        <>
          Objeciones del comité (
          <span className="num">{formatNumber(dossier.head.length + dossier.deferred.length)}</span>)
        </>
      }
    >
      <ul className="drivers">
        {dossier.head.map((item, index) => (
          <li key={`${item.source}:${index}`} className={item.source === "?" ? "c-gray" : undefined}>
            <Mark pictogram={item.source === "?" ? "slash-circle" : "shape-triangle"}>{item.title}</Mark>
            {item.quote ? <span className="secondary"> — «{item.quote}»</span> : null}
          </li>
        ))}
      </ul>
      {dossier.deferred.length > 0 && (
        <p className="secondary">
          Diferidas: {dossier.deferred.map((item) => item.title).join("; ")}
        </p>
      )}
      {dossier.warnings.map((warning) => (
        <p key={warning} className="secondary">
          {warning}
        </p>
      ))}
    </Fold>
  );
}

/**
 * La fuente que cita una firma y si existe en su registro (Polaris `_existencia_citas`). Una cita
 * que el registro desmiente se marca; no bloquea la firma (decision del usuario, 2026-09-29).
 */
export function CitedSource({ signature }: { signature: DraftSignoff }) {
  if (!signature.source) return null;
  const check = signature.source_check;
  // Una cita inventada, un fragmento que no esta en el informe o un informe que no acredita ser
  // de este tripulante: hay que mirarlo (F.5-1, amarillo con triangulo). No bloquea la firma.
  const fabricated = ["FABRICADA", "fragmento_ausente", "no_existe", "identidad_ajena"].includes(
    check?.estado ?? "",
  );
  const quote = signature.source_quote;
  return (
    <>
      <p className={fabricated ? "c-yellow" : "secondary"}>
        <Mark pictogram={fabricated ? "shape-triangle" : null}>
          Fuente de {signature.signed_by}: {signature.source}
          {check ? ` · ${check.detalle}` : ""}
        </Mark>
      </p>
      {quote && (
        <>
          <QuotedPhrase quote={quote} />
          {quote.vista === false && (
            <p className="c-yellow">
              <Mark pictogram="shape-triangle">
                La firma no declaró haber visto la frase antes de firmar.
              </Mark>
            </p>
          )}
        </>
      )}
    </>
  );
}

/**
 * La frase literal del informe citado, entre comillas y con su procedencia. Es el texto
 * des-identificado que da el backend, sin tocar (`pre-wrap`: con sus saltos de linea). Si la cita
 * no se localiza no hay frase que enseñar: estado con pictograma, palabra y color, y el motivo
 * del backend.
 */
export function QuotedPhrase({ quote }: { quote: SourceQuote }) {
  const style = quoteStyle(quote);
  const origin = provenance(quote);
  if (quote.estado !== "localizada") {
    return (
      <p className={style.color === null ? "secondary" : `c-${style.color}`}>
        <Mark pictogram={style.pictogram}>Frase {style.word}</Mark>
        {quote.detalle ? ` · ${quote.detalle}` : ""}
      </p>
    );
  }
  return (
    <figure className="draft-quote">
      <blockquote>«{quote.frase}»</blockquote>
      <figcaption className="secondary">
        <Mark pictogram={style.pictogram}>Frase {style.word}</Mark> en {origin}
      </figcaption>
    </figure>
  );
}

interface Cite {
  source: string;
  source_fragment: string;
  signed_by: string;
}

/**
 * Formulario de firma. El motivo de un rechazo del backend se muestra tal cual.
 *
 * Si se cita un informe se puede pedir su frase literal y tenerla delante; cambiar la cita o quien
 * firma obliga a pedirla otra vez. Lo visto se devuelve con la firma (`seen_quote`) y el backend no
 * firma si la boveda ya no da eso.
 *
 * En la primera firma es opcional y nada la cierra: una cita no localizada se firma y asi queda.
 * En la segunda (`strict`, decisiones del usuario del 2026-10-13 y del 2026-10-15) la fuente es
 * obligatoria y tiene que ser un informe guardado; los botones no se ofrecen hasta citarlo, tener
 * su frase localizada delante y declarar que se ha leido. Antes de firmar se dice que falta en
 * cada paso, con el texto del backend (`rule`, y el motivo que da la lectura previa). La regla la
 * impone el backend (422): si aun asi rechaza, su motivo se muestra tal cual.
 */
function SignForm({
  acceptLabel,
  rejectLabel,
  onSubmit,
  preview,
  strict = false,
  rule,
  onDone,
}: {
  acceptLabel: string;
  rejectLabel: string;
  onSubmit: (body: {
    decision: "accepted" | "rejected";
    signed_by: string;
    comment: string;
    source: string;
    source_fragment: string;
    seen_quote?: SeenQuote;
  }) => Promise<unknown>;
  preview?: (cite: Cite) => Promise<{ quote: SourceQuote; second_signature?: Looked["gate"] }>;
  strict?: boolean;
  rule?: SecondSignatureRule | undefined;
  onDone: () => void;
}) {
  const [operator, setOperator] = useOperator();
  const [comment, setComment] = useState("");
  const [source, setSource] = useState("");
  const [fragment, setFragment] = useState("");
  const [failure, setFailure] = useState<{ reason: unknown } | null>(null);
  const [view, setView] = useState<({ key: string } & Looked) | null>(null);
  const [declaredKey, setDeclaredKey] = useState<string | null>(null);
  const citesReport = isReportCite(source);
  const key = viewKey(source, fragment, operator);
  const seen = isCurrent(view, key) ? view : null;
  // La declaracion vale para la frase que hay delante: otra cita, u otra persona, y hay que repetirla.
  const declared = seen !== null && declaredKey === key;
  const offer = strict
    ? secondSignatureOffer({ rule, source, looked: seen, declared })
    : { offered: true, why: null, askDeclaration: false };
  const look = async () => {
    if (preview === undefined) return;
    setFailure(null);
    try {
      const answer = await preview({
        source: source.trim(),
        source_fragment: fragment.trim(),
        signed_by: operator.trim(),
      });
      setDeclaredKey(null);
      setView({ key, quote: answer.quote, gate: answer.second_signature });
    } catch (reason) {
      setView(null);
      setFailure({ reason });
    }
  };
  const sign = async (decision: "accepted" | "rejected") => {
    setFailure(null);
    const seenQuote = citesReport && seen !== null ? seenOf(seen.quote) : undefined;
    try {
      await onSubmit({
        decision,
        signed_by: operator.trim(),
        comment: comment.trim(),
        source: source.trim(),
        source_fragment: citesReport ? fragment.trim() : "",
        ...(seenQuote !== undefined ? { seen_quote: seenQuote } : {}),
      });
      onDone();
    } catch (reason) {
      setFailure({ reason });
    }
  };
  return (
    <div className="silence-form">
      <FieldLabel concept="person" className="operator">
        Revisado por{" "}
        <input
          value={operator}
          maxLength={64}
          onChange={(event) => setOperator(event.target.value)}
          placeholder="nombre o indicativo"
        />
      </FieldLabel>
      <FieldLabel concept="reason">
        Comentario{" "}
        <input value={comment} maxLength={500} onChange={(event) => setComment(event.target.value)} />
      </FieldLabel>
      <FieldLabel concept="source">
        {strict ? "Fuente" : "Fuente (opcional)"}{" "}
        <input
          value={source}
          maxLength={500}
          onChange={(event) => setSource(event.target.value)}
          placeholder={strict ? "informe:<n>" : "PMID, DOI, NCT, informe:<n> o contramedida"}
        />
      </FieldLabel>
      {citesReport && (
        <FieldLabel pictogram="guillemets">
          Fragmento citado del informe{" "}
          <input
            value={fragment}
            maxLength={500}
            size={48}
            onChange={(event) => setFragment(event.target.value)}
            placeholder="copia la frase del informe en la que te apoyas"
          />
        </FieldLabel>
      )}
      {preview !== undefined && citesReport && (
        <div aria-live="polite">
          <div className="measure-actions">
            <Command concept="search" disabled={operator.trim() === ""} onClick={() => void look()}>
              Ver la frase en el informe
            </Command>
          </div>
          {seen !== null && <QuotedPhrase quote={seen.quote} />}
          {offer.askDeclaration && rule !== undefined && (
            <label>
              <input
                type="checkbox"
                checked={declared}
                onChange={(event) => setDeclaredKey(event.target.checked ? key : null)}
              />{" "}
              {rule.declaration}
            </label>
          )}
        </div>
      )}
      {offer.why !== null && (
        <p className="c-yellow">
          <Mark pictogram="shape-triangle">{offer.why}</Mark>
        </p>
      )}
      <div className="measure-actions">
        <Command
          concept="accept"
          disabled={operator.trim() === "" || !offer.offered}
          onClick={() => void sign("accepted")}
        >
          {acceptLabel}
        </Command>
        <Command
          concept="reject"
          disabled={operator.trim() === "" || !offer.offered}
          onClick={() => void sign("rejected")}
        >
          {rejectLabel}
        </Command>
      </div>
      {failure !== null && <ReasonLine reason={failure.reason} />}
    </div>
  );
}
