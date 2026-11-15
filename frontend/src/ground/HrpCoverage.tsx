import { useEffect, useState } from "react";

import { DomainName } from "../components/DomainName";
import { Fold } from "../components/Fold";
import { Mark, MarkOf } from "../components/Mark";
import { EvidenceList } from "../evidence/EvidenceList";
import { type HrpCoverage as Coverage, type HrpCoverageRisk, risksApi } from "../lib/api";
import { formatNumber, formatSourceDate } from "../lib/format";
import { tr } from "../lib/i18n";
import { LOADING_MARK, type RequestOutcome, requestOutcome } from "../lib/marks";
import { ridgePictogram } from "./framework";
import { coverageMark, coverageRows } from "./hrpCoverageMarks";

/**
 * Los riesgos que publica el Human Research Roadmap, todos, y qué hace EMMA con cada uno
 * (§5.36.9): el que cita un dominio, uno vigilado en parte o uno fuera de su alcance. Va plegado
 * dentro del panel de riesgos, porque el panel es un riesgo por dominio y esto es lo que queda
 * alrededor. Tiene su propia petición: si falla, el resto del panel sigue y el fallo se dice aquí,
 * con la marca de `requestOutcome`.
 *
 * Ninguna frase se escribe aquí: la cobertura, su motivo, el eje RIDGE con de dónde sale, el
 * alcance de cada dominio y lo que queda pendiente los da el backend; aquí solo se elige la marca
 * (`hrpCoverageMarks.ts`); los recuentos también son del backend.
 */
export function HrpCoverage() {
  const [body, setBody] = useState<Coverage | null>(null);
  const [error, setError] = useState<RequestOutcome | null>(null);

  useEffect(() => {
    let current = true;
    risksApi
      .hrpCoverage()
      .then((found) => {
        if (current) setBody(found);
      })
      .catch((reason: unknown) => {
        if (current) setError(requestOutcome(reason));
      });
    return () => {
      current = false;
    };
  }, []);

  if (body === null) {
    return error === null ? (
      <p className="secondary">
        <MarkOf mark={LOADING_MARK}>{tr("Consultando los riesgos del HRP…", "Loading the HRP risks…")}</MarkOf>
      </p>
    ) : (
      <p>
        <MarkOf mark={error.mark}>{tr("Cobertura de los riesgos del HRP no disponible:", "HRP risk coverage unavailable:")} {error.text}</MarkOf>
      </p>
    );
  }

  return <HrpCoverageView body={body} />;
}

/** La cobertura ya consultada; aparte para poder pintarla sin red en las pruebas. */
export function HrpCoverageView({ body }: { body: Coverage }) {
  return (
    <Fold data-ui="hrp-risks"
      concept="risks"
      className="mt-2"
      aria-label={tr("Riesgos del HRP", "HRP risks")}
      label={
        <>
          {tr("Riesgos del HRP y cobertura de EMMA", "HRP risks and EMMA coverage")}{" "}
          <span className="secondary num">· {formatNumber(body.count)}</span>
        </>
      }
    >
      <p>{body.summary}</p>
      <ul className="evidence mt-0" aria-label={tr("Recuento por cobertura", "Count by coverage")}>
        {coverageRows(body.counts, body.coverage_display).map((row) => (
          <li key={row.coverage}>
            <MarkOf mark={coverageMark(row.coverage)}>{row.display}</MarkOf>{" "}
            <span className="num">{formatNumber(row.count)}</span>
          </li>
        ))}
      </ul>
      <p className="secondary">{body.note}</p>
      <ul className="evidence" aria-label={tr("Cobertura de cada riesgo", "Coverage of each risk")}>
        {body.risks.map((risk) => (
          <CoverageItem
            key={risk.hrr_id}
            risk={risk}
            pendingNote={body.pending_note}
            inCatalogNote={body.in_catalog_note}
          />
        ))}
      </ul>
      <p className="secondary">{body.ridge_note}</p>
      <p className="secondary">{body.element_basis}</p>
      <p className="secondary">
        {body.listing.source.title} · «{body.listing.count_quote}» ·{" "}
        <span className="num">{formatSourceDate(body.read_on)}</span>
      </p>
      <p className="secondary">{body.listing.updates}</p>
    </Fold>
  );
}

function CoverageItem({
  risk,
  pendingNote,
  inCatalogNote,
}: {
  risk: HrpCoverageRisk;
  pendingNote: string;
  inCatalogNote: string;
}) {
  return (
    <li>
      <strong>{risk.short_title}</strong> <span className="secondary">· {risk.title}</span>
      <div>
        <MarkOf mark={coverageMark(risk.coverage)}>{risk.coverage_statement}</MarkOf>
      </div>
      <div>{risk.reason}</div>
      <div className="secondary">
        <Mark pictogram={ridgePictogram(risk.ridge.category)}>{risk.ridge.display}</Mark> (
        {risk.ridge.basis_display}) · {risk.hrp_element} · {risk.status_display} ·{" "}
        <span className="num">{formatSourceDate(risk.last_published)}</span>
      </div>
      <div className="secondary">{risk.ridge.note}</div>
      <div className="secondary num url">{risk.url}</div>
      {/* El alcance de cada dominio, plegado: la fila de condiciones médicas tiene nueve. Con el
          signo de «dominios», no la diana: esa es la marca de «cubierto», y aquí va en filas
          «en parte». */}
      {risk.domains.length > 0 && (
        <Fold data-ui="hrp-domain-scope" concept="domains" label={tr("Alcance de cada dominio", "Scope of each domain")}>
          {risk.domains.map((domain) => (
            <div key={domain.key}>
              <DomainName domain={domain.key} label={domain.display} />
              <div className="secondary">{domain.scope}</div>
            </div>
          ))}
        </Fold>
      )}
      {/* Las fichas como en el resto de EMMA: con su nivel, su fecha y su salvedad de alcance. */}
      {risk.refs.length > 0 && <EvidenceList items={risk.refs} />}
      {/* Las medidas y analitos de la fuente que el catálogo ya tiene (§5.38.5): nombre, código y unidad del
          backend; si es descriptivo, lo dice con su frase. */}
      {risk.in_catalog.length > 0 && (
        <div>
          <div className="secondary">{inCatalogNote}</div>
          <ul className="evidence mt-0" aria-label={tr("Medidas y analitos del catálogo", "Catalog measures and analytes")}>
            {risk.in_catalog.map((analyte) => {
              // Un cociente («1») no tiene unidad que leer: no se pinta un hueco.
              const unit = analyte.unit_display;
              return (
                <li key={analyte.key}>
                  {analyte.display_es}{" "}
                  <span className="secondary">
                    · {analyte.system_display} <span className="num">{analyte.code}</span>
                    {unit && (
                      <>
                        {" "}
                        · <span className="num">{unit}</span>
                      </>
                    )}
                    {analyte.descriptive_display && <> · {analyte.descriptive_display}</>}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {risk.pending.length > 0 && (
        <div>
          <div className="secondary">{pendingNote}</div>
          <ul className="evidence mt-0" aria-label={tr("Medidas y analitos pendientes", "Pending measures and analytes")}>
            {risk.pending.map((name) => (
              <li key={name}>{name}</li>
            ))}
          </ul>
        </div>
      )}
    </li>
  );
}
