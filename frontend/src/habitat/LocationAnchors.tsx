import { useEffect, useState } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { Command } from "../components/Command";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { type HabitatModules, type LocationAnchors as Anchors, api } from "../lib/api";
import { formatMet, formatNumber, missionElapsedSeconds } from "../lib/format";
import { tr } from "../lib/i18n";
import { EMPTY_MARK, type RequestOutcome, requestOutcome } from "../lib/marks";
import { modulePictogram } from "./pictograms";
import { declarationInstant } from "./systems";

/**
 * Las anclas de módulo: qué emisor fijo de la nave está en qué módulo (2026-11-10).
 *
 * Por qué existe: la sububicación ya no se simula. Sin declaración en la consola, la estiman las
 * anclas que oye el wearable, y para eso EMMA tiene que saber dónde está instalada cada una. Las
 * anclas son equipo de la nave, certificado y alimentado por ella (el patrón de REALM y de DLR
 * Compose); EMMA no añade emisores ni pilas, solo escucha. Esto es lo único que se declara aquí:
 * «el ancla X está en el módulo Y desde tal instante». Va al registro firmado con el operador de la
 * consola, como las demás declaraciones; no se borra ni se edita, se corrige declarando de nuevo y
 * vale la última (como los dispositivos vinculados).
 *
 * El identificador es el que anuncia el ancla tal cual (iBeacon `uuid:major:minor`, Eddystone-UID):
 * la interfaz no lo interpreta ni lo valida, eso lo hace el backend. La base (de dónde sale la
 * estimación y lo que no se sabe de ella en un módulo metálico) es texto del backend. En Tierra (sin
 * operador), solo lectura.
 */
export function LocationAnchors({
  missionStart,
  refreshKey,
  operator,
  referenceTime,
  modules,
  onDeclared,
  until,
}: {
  missionStart: string;
  /** Solo en Tierra: el corte de lo que ya ha llegado. */
  until?: Date | undefined;
  /** Cambia cuando cambia el estado: vuelve a pedir las anclas. */
  refreshKey: string;
  /** Solo a bordo: quien declara. En Tierra (`undefined`), lectura. */
  operator: string | undefined;
  /** El instante de los datos, al que se refiere una declaración (como en los sistemas). */
  referenceTime: string | null;
  modules: HabitatModules | null;
  /** Tras declarar: el panel vuelve a pedir la tripulación, cuya ubicación estimada cambia. */
  onDeclared?: () => void;
}) {
  const [anchors, setAnchors] = useState<Anchors | null>(null);
  const [loadError, setLoadError] = useState<RequestOutcome | null>(null);
  const [form, setForm] = useState(EMPTY_ANCHOR_FORM);
  const [declared, setDeclared] = useState(0);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<RequestOutcome | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .locationAnchors()
      .then((body) => {
        if (cancelled) return;
        setAnchors(body);
        setLoadError(null);
      })
      // El resto del hábitat sigue valiendo; aquí se dice qué pasó, con la marca de la petición.
      .catch((reason: unknown) => {
        if (cancelled) return;
        setAnchors(null);
        setLoadError(requestOutcome(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey, declared]);

  if (anchors === null) {
    if (loadError === null) return null;
    return (
      <div className="hypotheses" role="group" aria-label={tr("Anclas de módulo", "Module anchors")}>
        <PanelTitle as="h3" pictogram="sensor-arcs">
          {tr("Anclas de módulo", "Module anchors")}
        </PanelTitle>
        <p>
          <MarkOf mark={loadError.mark}>{tr(`No se pudieron cargar las anclas: ${loadError.text}`, `Could not load the anchors: ${loadError.text}`)}</MarkOf>
        </p>
      </div>
    );
  }
  const met = (iso: string) => formatMet(missionElapsedSeconds(missionStart, new Date(iso)));
  const since = declarationInstant(referenceTime, new Date());
  // En Tierra, lo que aún no ha llegado no se enseña. La ruta del contrato no admite `until`, así que
  // se aproxima por el `since` de cada ancla (el instante de los datos al declararla).
  const known: Anchors =
    until === undefined
      ? anchors
      : { ...anchors, anchors: anchors.anchors.filter((anchor) => Date.parse(anchor.since) <= until.getTime()) };
  const declare = () => {
    // Una sola petición a la vez: un doble clic firmaría dos asientos que no se pueden borrar.
    if (operator === undefined || pending) return;
    setError(null);
    setPending(true);
    api
      .declareAnchor(anchorBody(form, operator, since))
      .then(() => {
        setForm(EMPTY_ANCHOR_FORM);
        setDeclared((count) => count + 1);
        // La ubicación estimada de la tripulación depende de las anclas: que se vuelva a pedir.
        onDeclared?.();
      })
      .catch((cause: unknown) => setError(requestOutcome(cause)))
      .finally(() => setPending(false));
  };
  return (
    <LocationAnchorsView
      anchors={known}
      modules={modules}
      met={met}
      operator={operator}
      form={form}
      onForm={setForm}
      since={since}
      onDeclare={declare}
      pending={pending}
      error={error}
    />
  );
}

export interface AnchorForm {
  anchorId: string;
  module: string;
}

export const EMPTY_ANCHOR_FORM: AnchorForm = { anchorId: "", module: "" };

/** Se puede declarar con identificador, módulo y quien firma; lo demás lo decide el backend. */
export function canDeclareAnchor(form: AnchorForm, operator: string | undefined): boolean {
  return form.anchorId.trim() !== "" && form.module !== "" && (operator ?? "").trim() !== "";
}

/** El cuerpo de `POST /location/anchors`, tal cual lo fija el contrato. */
export function anchorBody(
  form: AnchorForm,
  operator: string,
  since: string,
): { anchor_id: string; module: string; since: string; declared_by: string } {
  return { anchor_id: form.anchorId.trim(), module: form.module, since, declared_by: operator.trim() };
}

/**
 * La lista y, a bordo, el formulario. Separada del que pide los datos para pintarla a HTML estático
 * en las pruebas.
 */
export function LocationAnchorsView({
  anchors,
  modules,
  met,
  operator,
  form,
  onForm,
  since,
  onDeclare,
  pending = false,
  error,
}: {
  anchors: Anchors;
  modules: HabitatModules | null;
  met: (iso: string) => string;
  operator: string | undefined;
  form: AnchorForm;
  onForm: (form: AnchorForm) => void;
  since: string;
  onDeclare: () => void;
  /** Una declaración en curso: el mando se apaga hasta que conteste el backend. */
  pending?: boolean;
  error: RequestOutcome | null;
}) {
  return (
    <div className="hypotheses" role="group" aria-label={tr("Anclas de módulo", "Module anchors")}>
      <PanelTitle as="h3" pictogram="sensor-arcs">
        {tr("Anclas de módulo", "Module anchors")}
      </PanelTitle>
      {anchors.anchors.length === 0 ? (
        // Ninguna declarada: aún no se ha registrado nada (no es un dato que falte ni caduque).
        <p>
          <MarkOf mark={EMPTY_MARK}>{tr("Ninguna ancla declarada", "No anchor declared")}</MarkOf>
        </p>
      ) : (
        <ul className="secondary">
          {anchors.anchors.map((anchor) => (
            <li key={anchor.anchor_id}>
              <code>{anchor.anchor_id}</code> {tr("en", "in")}{" "}
              <Mark pictogram={modulePictogram(anchor.module)}>{anchor.display}</Mark> {tr("desde", "since")}{" "}
              <span className="num">{met(anchor.since)}</span> · {tr("asiento", "ledger entry")}{" "}
              <span className="num">{formatNumber(anchor.ledger_index)}</span>
            </li>
          ))}
        </ul>
      )}
      <BoardDetail label={tr("de dónde sale la ubicación estimada", "where the estimated location comes from")}>
        <p className="secondary">{anchors.basis}</p>
      </BoardDetail>
      {operator !== undefined && (
        <div className="inline-form">
          <input
            value={form.anchorId}
            maxLength={200}
            placeholder={tr("identificador del ancla", "anchor identifier")}
            aria-label={tr("Identificador del ancla", "Anchor identifier")}
            onChange={(event) => onForm({ ...form, anchorId: event.target.value })}
          />
          <select
            value={form.module}
            aria-label={tr("Módulo donde está instalada", "Module where it is installed")}
            onChange={(event) => onForm({ ...form, module: event.target.value })}
          >
            <option value="">{tr("Módulo…", "Module…")}</option>
            {(modules?.modules ?? []).map((item) => (
              <option key={item.key} value={item.key}>
                {item.display}
              </option>
            ))}
          </select>
          <Command concept="declare" disabled={pending || !canDeclareAnchor(form, operator)} onClick={onDeclare}>
            {tr("Declarar ancla", "Declare anchor")}
          </Command>
          <span className="secondary">
            {tr("desde", "since")} <span className="num">{met(since)}</span> · {tr("firma", "signed by")} {operator.trim() === "" ? "—" : operator.trim()}
          </span>
          {error !== null && <MarkOf mark={error.mark}>{error.text}</MarkOf>}
        </div>
      )}
    </div>
  );
}
