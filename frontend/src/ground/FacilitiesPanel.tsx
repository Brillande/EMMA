import { useEffect, useState } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { FieldLabel } from "../components/FieldLabel";
import { Fold } from "../components/Fold";
import { MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { populationMark, SCOPE_MARK } from "../evidence/sourceMarks";
import { type Facilities, type Facility, type FacilityLink, type FacilityQuote, facilitiesApi } from "../lib/api";
import { formatSourceDate } from "../lib/format";
import { tr } from "../lib/i18n";
import { EMPTY_MARK, LOADING_MARK, MISSING_MARK, type RequestOutcome, requestOutcome } from "../lib/marks";
import { FACILITIES_PICTOGRAM, statusMark, stepSign } from "./facilities";

const TITLE = tr("Instalaciones de Columbus: EPM y Biolab", "Columbus facilities: EPM and Biolab");

/**
 * EPM y Biolab, de la instalación a la aplicación (base de conocimiento §9).
 *
 * La base de conocimiento pide seguir cada instalación de Columbus por nueve eslabones —instalación,
 * experimento, equipo, parámetro, investigador, proveedor, conjunto de datos, publicación,
 * aplicación—. Este panel enseña, por instalación y para uno de sus experimentos, cada eslabón con
 * su estado y sus frases (literales, en su idioma, con su ficha), y donde no se encontró la fuente,
 * qué falta y dónde se buscó: el eslabón no se quita ni se rellena.
 *
 * Todo el texto viene de `GET /api/facilities`; aquí solo hay rótulos de inventario y el signo de
 * cada cosa (`facilities.ts`). Inventario: no interviene en el estado de la tripulación.
 */
export function FacilitiesPanel() {
  const [facilities, setFacilities] = useState<Facilities | null>(null);
  const [failure, setFailure] = useState<RequestOutcome | null>(null);

  useEffect(() => {
    let current = true;
    facilitiesApi
      .get()
      .then((body) => {
        if (current) setFacilities(body);
      })
      .catch((reason: unknown) => {
        if (current) setFailure(requestOutcome(reason));
      });
    return () => {
      current = false;
    };
  }, []);

  if (facilities === null) {
    return (
      <section data-ui="facilities" className="panel" aria-label={TITLE}>
        <PanelTitle pictogram={FACILITIES_PICTOGRAM}>{TITLE}</PanelTitle>
        {failure === null ? (
          <p className="secondary">
            <MarkOf mark={LOADING_MARK}>{tr("Consultando las instalaciones…", "Loading the facilities…")}</MarkOf>
          </p>
        ) : (
          <p>
            <MarkOf mark={failure.mark}>{tr("Instalaciones no disponibles:", "Facilities unavailable:")} {failure.text}</MarkOf>
          </p>
        )}
      </section>
    );
  }
  return <FacilitiesView facilities={facilities} />;
}

/** Las cadenas ya recibidas. Aparte del que consulta para poder pintarlas en las pruebas sin red. */
export function FacilitiesView({ facilities }: { facilities: Facilities }) {
  return (
    <section data-ui="facilities" className="panel" aria-label={TITLE}>
      <PanelTitle pictogram={FACILITIES_PICTOGRAM}>{TITLE}</PanelTitle>
      {/* Lote «muestra» (2026-11-08): la nota y la cadena, tras «Ver detalle» en el tablero; la fila
          de cada instalación, a la vista. */}
      <BoardDetail label={tr("la cadena de cada instalación", "the chain of each facility")}>
        <p className="secondary">{facilities.note}</p>
        <p>{facilities.chain.text}</p>
        <p className="secondary">{facilities.chain.where}</p>
      </BoardDetail>

      {facilities.facilities.map((facility) => (
        <FacilityFold key={facility.id} facility={facility} readOn={facilities.read_on} />
      ))}

      <PanelTitle as="h3" concept="searchedNotFound" className="section-gap">
        {tr("Buscado y no encontrado", "Searched and not found")}
      </PanelTitle>
      <BoardDetail label={tr("lo buscado", "what was searched")}>
        <ul className="evidence">
          {facilities.not_found.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </BoardDetail>
    </section>
  );
}

/**
 * Una instalación, plegada: el matraz del laboratorio y su experimento en el rótulo; dentro, lo que
 * dice de ella la base de conocimiento, la salvedad de alcance si la cadena no mide solo personas,
 * los eslabones sin ninguna fuente y los nueve eslabones uno a uno.
 */
function FacilityFold({ facility, readOn }: { facility: Facility; readOn: string }) {
  return (
    <Fold data-ui="facility"
      pictogram={FACILITIES_PICTOGRAM}
      aria-label={tr(`Instalación ${facility.name}`, `Facility ${facility.name}`)}
      label={
        <>
          <strong>{facility.name}</strong> <span lang="en">({facility.full_name})</span>
          <span className="secondary">
            {" "}
            · <span lang="en">{facility.experiment}</span>
          </span>
        </>
      }
    >
      <p>
        {facility.kb_role.text} <span className="secondary">· {facility.kb_role.where}</span>
      </p>
      {facility.scope_caveat !== null && (
        <p>
          <MarkOf mark={SCOPE_MARK}>{facility.scope_caveat}</MarkOf>
        </p>
      )}
      <dl className="kv">
        <FieldLabel as="dt" concept="searchedNotFound">
          {tr("Eslabones sin fuente", "Links with no source")}
        </FieldLabel>
        <dd>
          {facility.unsourced.length === 0 ? (
            <MarkOf mark={EMPTY_MARK}>{tr("ninguno", "none")}</MarkOf>
          ) : (
            <MarkOf mark={MISSING_MARK}>{facility.unsourced.join(" · ")}</MarkOf>
          )}
        </dd>
        {facility.links.map((link) => (
          <LinkRow key={link.step} link={link} readOn={readOn} />
        ))}
      </dl>
    </Fold>
  );
}

/** Un eslabón: su rótulo con su signo, su estado, sus frases y, si lo hay, su hueco. */
function LinkRow({ link, readOn }: { link: FacilityLink; readOn: string }) {
  return (
    <>
      <FieldLabel as="dt" {...stepSign(link.step)}>
        {link.label}
      </FieldLabel>
      <dd>
        <div>
          <MarkOf mark={statusMark(link.status)}>{link.status_text}</MarkOf>
        </div>
        {link.quotes.length > 0 && (
          <ul className="evidence mt-0">
            {link.quotes.map((item) => (
              <li key={`${item.ref}:${item.quote}`}>
                <QuoteLine item={item} readOn={readOn} />
              </li>
            ))}
          </ul>
        )}
        {link.missing !== null && (
          <dl className="kv">
            <FieldLabel as="dt" concept="decline">
              {tr("Falta", "Missing")}
            </FieldLabel>
            <dd>
              <MarkOf mark={MISSING_MARK}>{link.missing.what}</MarkOf>
            </dd>
            <FieldLabel as="dt" concept="search">
              {tr("Buscado en", "Searched in")}
            </FieldLabel>
            <dd>
              <ul className="evidence mt-0">
                {link.missing.searched.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </dd>
          </dl>
        )}
      </dd>
    </>
  );
}

/**
 * Una frase de la fuente, en su idioma, con su ficha: de quién es, dónde está, cuándo se leyó, sobre
 * quién se midió (en amarillo si no son solo personas, como en toda ficha) y lo que la ficha no
 * tiene verificado, en cian.
 */
function QuoteLine({ item, readOn }: { item: FacilityQuote; readOn: string }) {
  return (
    <>
      <q lang="en">{item.quote}</q>
      <div className="secondary">
        <span lang="en">{item.source}</span> · {item.where} · {tr("leído el", "read on")}{" "}
        <span className="num">{formatSourceDate(readOn)}</span>
        {item.population !== null && (
          <>
            {" "}
            · <MarkOf mark={populationMark(item.population)}>{item.population_display}</MarkOf>
          </>
        )}
        {item.unverified_display.length > 0 && (
          <>
            {" "}
            · <MarkOf mark={MISSING_MARK}>{tr(`sin verificar: ${item.unverified_display.join(", ")}`, `not verified: ${item.unverified_display.join(", ")}`)}</MarkOf>
          </>
        )}
      </div>
      {item.url !== null && <div className="secondary num url">{item.url}</div>}
    </>
  );
}
