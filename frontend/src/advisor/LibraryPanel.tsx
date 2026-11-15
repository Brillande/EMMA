import { useEffect, useState } from "react";

import { Chosen } from "../components/Chosen";
import { FieldLabel } from "../components/FieldLabel";
import { Fold } from "../components/Fold";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { Th } from "../components/Th";
import { Loading } from "../components/Unavailable";
import { type Countermeasure, type CountermeasureLibrary, type ResearchCountermeasures, api } from "../lib/api";
import { formatNumber, formatSourceDate } from "../lib/format";
import {
  EMPTY_MARK,
  LOADING_MARK,
  OK_MARK,
  type RequestOutcome,
  prefixedPictogram,
  requestOutcome,
} from "../lib/marks";
import {
  ADVERSE_EFFECTS_PICTOGRAM,
  CONTRAINDICATIONS_PICTOGRAM,
  familyOptions,
  familyPictogram,
  libraryGroups,
  RESEARCH_PICTOGRAM,
  timeBasisFolds,
} from "./library";
import { BasisText, EffectsLines, FamilyName, FollowupText } from "./RecommendationCard";
import { contraindicationsLine, effectsView, resourcesLine } from "./recommendation";
import { tr } from "../lib/i18n";

/**
 * La biblioteca entera de contramedidas, agrupada por peligro RIDGE (§5.34.1).
 *
 * Por qué existe: la especificación (§8) pide la biblioteca como datos estructurados —fuente,
 * recursos, tiempo de tripulación, riesgo, seguimiento— y la base de conocimiento (§10, «Countermeasure
 * Twin: ¿qué puede hacerse ahora y qué efecto esperamos?»; §15 P1, «Contramedidas por RIDGE»)
 * quiere poder leerla entera. Estaba en `GET /api/countermeasures` y nadie la llamaba: a bordo
 * solo se veían las recomendadas. Una tripulación con el retardo de Marte no puede preguntar a
 * Tierra qué más hay; por eso va en la consola de a bordo, y también en la de Tierra, que planifica
 * con la misma lista (es un dato fijo del paquete, no del estado: no lleva retardo).
 *
 * Todo lo escrito es del backend: la acción, la indicación, la familia y su criterio, el peligro
 * RIDGE, el respaldo, los tiempos y sus bases. Aquí solo se elige el dibujo de cada familia
 * (`library.ts`) y el de cada peligro (`ridge-*`), sin color: nada de esto es un aviso, y
 * consultarla no adopta nada. Cada grupo va plegado; dentro, una tabla para comparar lo que cuesta
 * cada acción. Una cifra de tiempo lleva su fuente en un plegable al lado, nunca sola.
 *
 * Decimoquinta ronda (§5.35.7): las familias son también el filtro (en el cliente, sobre la lista
 * que ya llegó), y la tabla lleva las contraindicaciones y los efectos, lo que la tarjeta enseña a
 * la vista antes de adoptar y la tabla no tenía. Las dos columnas son texto del backend tal cual,
 * sin color; donde no hay nada escrito, la marca del registro vacío.
 */
export function LibraryPanel() {
  const [library, setLibrary] = useState<CountermeasureLibrary | null>(null);
  const [failure, setFailure] = useState<RequestOutcome | null>(null);
  const [research, setResearch] = useState<ResearchCountermeasures | null>(null);
  const [researchFailure, setResearchFailure] = useState<RequestOutcome | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .countermeasureLibrary()
      .then((body) => {
        if (!cancelled) setLibrary(body);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setFailure(requestOutcome(reason));
      });
    // Aparte y por su cuenta: si una de las dos lecturas falla, la otra se sigue viendo.
    api
      .researchCountermeasures()
      .then((body) => {
        if (!cancelled) setResearch(body);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setResearchFailure(requestOutcome(reason));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section data-ui="countermeasure-library" className="panel" aria-label={tr("Biblioteca de contramedidas", "Countermeasure library")}>
      <PanelTitle concept="countermeasureLibrary">
        {tr("Biblioteca de contramedidas", "Countermeasure library")}
        {library !== null && (
          <span className="secondary">
            {" "}
            · <span className="num">{formatNumber(library.countermeasures.length)}</span> {tr("entradas", "entries")}
          </span>
        )}
      </PanelTitle>
      {failure !== null ? (
        <p>
          <MarkOf mark={failure.mark}>
            {tr("No se pudo leer la biblioteca:", "Could not read the library:")} {failure.text}
          </MarkOf>
        </p>
      ) : library === null ? (
        <Loading />
      ) : (
        <LibraryBody library={library} />
      )}
      <ResearchSection research={research} failure={researchFailure} />
    </section>
  );
}

/**
 * Las contramedidas en investigación (§5.36.15), en una sección aparte y rotulada como tal.
 *
 * Por qué existe: la base de conocimiento (§4) y la conversación de ideación nombran la presión
 * negativa en la parte inferior del cuerpo, los brazaletes de muslo, la gravedad artificial y la
 * realidad virtual, y la biblioteca no tenía ninguna porque ninguna se puede adoptar hoy a bordo.
 * El backend las sirve en su propia ruta, fuera de la huella de reglas y de las recomendaciones;
 * aquí se enseñan plegadas, después de los cinco peligros, con el matraz y no con la tirita: no
 * son de la biblioteca, no tienen familia ni mando de adoptar, y no llevan color (nada es un
 * aviso). Todo lo escrito es del backend; la frase de la fuente va literal, en su idioma
 * (`lang="en"`), con su ficha y su página al lado. Lo buscado y no encontrado, y lo leído y no
 * incluido, van en sus plegables: lo que la fuente no dice no se calla.
 */
export function ResearchSection({
  research,
  failure,
}: {
  research: ResearchCountermeasures | null;
  failure: RequestOutcome | null;
}) {
  if (failure !== null) {
    return (
      <p>
        <MarkOf mark={failure.mark}>
          {tr(
            "No se pudieron leer las contramedidas en investigación:",
            "Could not read the countermeasures under research:",
          )}{" "}
          {failure.text}
        </MarkOf>
      </p>
    );
  }
  // Mientras llega, se dice que llega y qué llega: un hueco se leería como «no hay ninguna», y
  // dos «Cargando…» seguidos (el de la biblioteca y este) no dicen cuál es cuál.
  if (research === null) {
    return (
      <p className="secondary">
        <MarkOf mark={LOADING_MARK}>
          {tr("Cargando las contramedidas en investigación…", "Loading the countermeasures under research…")}
        </MarkOf>
      </p>
    );
  }
  return (
    <Fold data-ui="library-research"
      className="library-research"
      pictogram={RESEARCH_PICTOGRAM}
      label={
        <>
          {tr("En investigación: no se ofrecen", "Under research: not offered")} (<span className="num">{formatNumber(research.entries.length)}</span>)
        </>
      }
    >
      <p className="secondary">{research.note}</p>
      <div className="quality-table">
        <table className="ledger library-table">
          <thead>
            <tr>
              <Th pictogram={RESEARCH_PICTOGRAM}>{tr("Contramedida en investigación", "Countermeasure under research")}</Th>
              <Th concept="risks">{tr("Peligro RIDGE", "RIDGE hazard")}</Th>
              <Th concept="state">{tr("Estado", "Status")}</Th>
              <Th concept="sourceText">{tr("Lo que dice la fuente", "What the source says")}</Th>
            </tr>
          </thead>
          <tbody>
            {research.entries.map((item) => (
              <tr key={item.id}>
                <th scope="row">
                  {item.name}
                  <br />
                  <span className="secondary">{item.targets}</span>
                </th>
                <td>
                  <Mark pictogram={prefixedPictogram("ridge", item.ridge)}>{item.ridge_display}</Mark>
                </td>
                <td>
                  <div className="library-note">
                    {item.status}
                    <br />
                    <span className="secondary">{item.flight_note}</span>
                  </div>
                </td>
                <td>
                  {item.quotes.map((quote, index) => (
                    <figure key={`${quote.ref}-${index}`} className="research-quote">
                      <blockquote lang="en">{quote.quote}</blockquote>
                      {/* La cita de la ficha (`source`), no solo su título: el PDF de 2022 y la
                          página web se titulan igual, y la página solo existe en uno. */}
                      <figcaption className="secondary">
                        {quote.source}, {quote.where}
                      </figcaption>
                    </figure>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Fold data-ui="library-searched-not-found" concept="searchedNotFound" label={tr("Buscado y no encontrado", "Searched and not found")}>
        <ul className="secondary">
          {research.not_found.map((line, index) => (
            <li key={index}>{line}</li>
          ))}
        </ul>
      </Fold>
      <Fold data-ui="library-read-not-included" concept="source" label={tr("Leído y no incluido", "Read and not included")}>
        <ul className="secondary">
          {research.read_not_included.map((line, index) => (
            <li key={index}>{line}</li>
          ))}
        </ul>
      </Fold>
      <Fold data-ui="library-what-was-read" concept="docs" label={<>{tr("Qué se leyó", "What was read")} ({readOnLabel(research.read_on)})</>}>
        <ul className="secondary">
          {Object.entries(research.sources).map(([ref, source]) => (
            <li key={ref}>
              {source.source}: {source.extent_text}
              {/* Una fuente leída otro día que el del rótulo lo dice: sus frases son de ese día. */}
              {source.read_on !== research.read_on && <> {tr("el", "on")} {readOnLabel(source.read_on)}</>}.{" "}
              {source.what}
              {/* La dirección de la ficha, para abrir la fuente de las frases. */}
              {source.url !== null && <div className="num url">{source.url}</div>}
            </li>
          ))}
        </ul>
      </Fold>
    </Fold>
  );
}

/**
 * La fecha de lectura, o su ausencia dicha. `formatSourceDate` lanza ante una forma que no
 * entiende, y aquí ningún límite de errores lo recogería: sin esto, una fecha rara tumbaría el
 * panel entero, biblioteca incluida, cuando la sección se pinta aparte precisamente para que un
 * fallo suyo no se lleve la otra.
 */
export function readOnLabel(readOn: string): string {
  try {
    return formatSourceDate(readOn);
  } catch {
    return tr("fecha de lectura no legible", "reading date not readable");
  }
}

/**
 * El cuerpo del panel. `initialFamily` solo lo usan las pruebas, para pintar sin pulsar un filtro
 * ya elegido; en la consola se empieza con todas.
 */
export function LibraryBody({
  library,
  initialFamily = null,
}: {
  library: CountermeasureLibrary;
  initialFamily?: string | null;
}) {
  const options = familyOptions(library);
  const [chosenFamily, setFamily] = useState<string | null>(initialFamily);
  // Un filtro que ya no tiene entradas (otra lectura de la biblioteca) vuelve a «todas».
  const family = options.some((option) => option.selectable && option.key === chosenFamily) ? chosenFamily : null;
  const { groups, ungrouped } = libraryGroups(library, family);
  return (
    <>
      <p className="secondary">{library.note}</p>
      {/* Los efectos (§5.39.17): que son, cuantas entradas declaran alguno y que ninguna fuente
          leida dice como interactuan dos. Texto del backend; las cifras, con su palabra. */}
      {library.effects_overview !== undefined && library.effects_overview !== null && (
        <p className="secondary" role="note">
          <Mark pictogram={ADVERSE_EFFECTS_PICTOGRAM}>
            {tr("Efectos:", "Effects:")} {library.effects_overview.note}
          </Mark>{" "}
          {tr("Con efecto adverso declarado:", "With a declared adverse effect:")}{" "}
          <span className="num">{formatNumber(library.effects_overview.declared)}</span> ·{" "}
          {tr("no declarado:", "not declared:")}{" "}
          <span className="num">{formatNumber(library.effects_overview.not_declared)}</span>.
          {library.effects_overview.interactions_note != null && (
            <>
              <br />
              {library.effects_overview.interactions_note}
            </>
          )}
        </p>
      )}
      {/* Las familias son el filtro: cada una con su dibujo, su palabra y cuántas entradas
          enseña. La elegida lleva el anillo de «elegido» (`Chosen`), no solo el botón pulsado. */}
      <div className="measure-actions library-filter" role="group" aria-label={tr("Filtrar por familia", "Filter by family")} data-ui-view="">
        <FieldLabel as="span" concept="type" className="secondary">
          {tr("Familia", "Family")}
        </FieldLabel>
        <button type="button" className="command" aria-pressed={family === null} onClick={() => setFamily(null)}>
          <Chosen chosen={family === null}>
            {tr("todas", "all")} <span className="num">{formatNumber(library.countermeasures.length)}</span>
          </Chosen>
        </button>
        {options.map((option) =>
          option.selectable ? (
            <button
              key={option.key}
              type="button"
              className="command"
              aria-pressed={family === option.key}
              onClick={() => setFamily(option.key)}
            >
              <Chosen chosen={family === option.key}>
                <Mark pictogram={option.pictogram}>{option.display}</Mark>{" "}
                <span className="num">{formatNumber(option.count)}</span>
              </Chosen>
            </button>
          ) : (
            // Sin ninguna entrada no hay nada que filtrar: se nombra, sin mando.
            <span key={option.key} className={option.inScope ? undefined : "secondary"}>
              <Mark pictogram={option.pictogram}>{option.display}</Mark>{" "}
              <span className="num">{formatNumber(option.count)}</span>
            </span>
          ),
        )}
      </div>
      <Fold data-ui="library-how-to-read" concept="howToRead" label={tr("Cómo leerlo", "How to read it")}>
        <p className="secondary">{library.family_basis}</p>
        <ul className="secondary">
          {library.families.map((family) => (
            <li key={family.key}>
              <Mark pictogram={familyPictogram(family.key)}>{family.display}</Mark>: {family.criterion}
            </li>
          ))}
        </ul>
        <p className="secondary">{library.ridge_basis}</p>
      </Fold>
      {groups.map((group) => (
        <Fold data-ui="library-ridge-group"
          key={group.ridge}
          pictogram={group.pictogram}
          label={
            <>
              RIDGE: {group.ridgeDisplay} (
              {family !== null && (
                <>
                  <span className="num">{formatNumber(group.items.length)}</span> {tr("de", "of")}{" "}
                </>
              )}
              <span className="num">{formatNumber(group.count)}</span>)
            </>
          }
        >
          {group.items.length > 0 && <LibraryTable items={group.items} />}
          {family !== null && group.items.length === 0 && (
            <p>
              <MarkOf mark={OK_MARK}>
                {tr("Ninguna de esta familia en este peligro.", "None of this family for this hazard.")}
              </MarkOf>
            </p>
          )}
          {group.missing.length > 0 && (
            <p className="secondary">
              {tr("Nombradas sin ficha en la respuesta:", "Named without an entry in the response:")}{" "}
              {group.missing.join(", ")}
            </p>
          )}
        </Fold>
      ))}
      {ungrouped.length > 0 && (
        <Fold data-ui="library-no-ridge" concept="countermeasureLibrary" label={<>{tr("Sin peligro RIDGE", "No RIDGE hazard")} ({formatNumber(ungrouped.length)})</>}>
          <LibraryTable items={ungrouped} />
        </Fold>
      )}
    </>
  );
}

/**
 * La contraindicación tal y como la da el backend, la misma línea que la tarjeta
 * (`contraindicationsLine`): la de la revisión médica o «pendiente de revisión médica», que solo
 * cambia el peso tipográfico. Sin color de aviso: hoy no hay ninguna escrita, y decir que falta
 * revisarla no es una alerta. Un backend que no mande el texto deja la celda en «nada escrito»
 * (el registro vacío), que no se lee como «no tiene».
 */
function ContraindicationsCell({ measure }: { measure: Countermeasure }) {
  const line = contraindicationsLine(measure);
  return (
    <div className="library-note">
      {line === null ? (
        <MarkOf mark={EMPTY_MARK}>{tr("nada escrito", "nothing written")}</MarkOf>
      ) : line.pending ? (
        <span className="secondary">{line.text}</span>
      ) : (
        line.text
      )}
    </div>
  );
}

/**
 * La celda de los efectos: la nota de la biblioteca tal cual y, si el backend manda la ficha de
 * efectos (§5.39.17), las mismas lineas que la tarjeta (beneficio, donde cae cada efecto declarado
 * o «no declarado»). Sin nota ni ficha —nulo, ausente (un backend anterior) o en blanco— la marca
 * del registro vacio, «nada escrito», que no se lee como «no tiene». Con ficha y sin nota, la frase
 * de «no declarado» del backend ocupa ese sitio: dice lo mismo con mas palabras, y son suyas.
 */
function EffectsCell({ measure }: { measure: Countermeasure }) {
  const note = measure.adverse_effects_note?.trim() ?? "";
  const view = effectsView(measure.effects);
  return (
    <div className="library-note">
      {note !== "" ? measure.adverse_effects_note : view === null ? <MarkOf mark={EMPTY_MARK}>{tr("nada escrito", "nothing written")}</MarkOf> : null}
      {view !== null && <EffectsLines effects={view} />}
    </div>
  );
}

function LibraryTable({ items }: { items: readonly Countermeasure[] }) {
  return (
    <div className="quality-table">
      <table className="ledger library-table">
        <thead>
          <tr>
            <Th concept="countermeasureLibrary">{tr("Contramedida", "Countermeasure")}</Th>
            <Th concept="type">{tr("Familia", "Family")}</Th>
            <Th concept="source">{tr("Respaldo", "Backing")}</Th>
            <Th pictogram={CONTRAINDICATIONS_PICTOGRAM}>{tr("Contraindicaciones", "Contraindications")}</Th>
            <Th pictogram={ADVERSE_EFFECTS_PICTOGRAM} className="library-head-whole">
              {tr("Efectos a tener en cuenta", "Effects to bear in mind")}
            </Th>
            <Th concept="during">{tr("Tiempo de tripulación", "Crew time")}</Th>
            <Th concept="followUp">{tr("Seguimiento", "Follow-up")}</Th>
            <Th concept="resources">{tr("Recursos", "Resources")}</Th>
          </tr>
        </thead>
        <tbody>
          {items.map((measure) => (
            <tr key={measure.id}>
              <th scope="row">
                {measure.action}
                <br />
                <span className="secondary">{measure.indication}</span>
              </th>
              <td className="family">
                <FamilyName measure={measure} inColumn />
              </td>
              <td>
                <BasisText measure={measure} />
              </td>
              <td>
                <ContraindicationsCell measure={measure} />
              </td>
              <td>
                <EffectsCell measure={measure} />
              </td>
              <td>
                {/* La base larga (la que cita su fuente literal) se parte en su columna en vez de
                    ensancharla (`.library-note`): antes la tabla entera crecía por dos o tres
                    entradas (§5.34.1). */}
                <div className="library-note">
                  {measure.crew_time_minutes === null ? (
                    timeBasisFolds(measure) ? (
                      // Sin cifra y con una base que cita su fuente literal: en la columna
                      // estrecha era una torre de treinta líneas en una fila de cinco.
                      <Fold data-ui="library-no-figure" concept="source" label={tr("sin cifra", "no figure")}>
                        <p className="secondary">{measure.crew_time_basis}</p>
                      </Fold>
                    ) : (
                      <span className="secondary">{measure.crew_time_basis}</span>
                    )
                  ) : (
                    <>
                      <span className="num">{formatNumber(measure.crew_time_minutes)}</span> min
                      <Fold data-ui="library-source" concept="source" label={tr("fuente", "source")}>
                        <p className="secondary">{measure.crew_time_basis}</p>
                      </Fold>
                    </>
                  )}
                </div>
              </td>
              <td>
                <FollowupText measure={measure} />
              </td>
              <td>{resourcesLine(measure)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
