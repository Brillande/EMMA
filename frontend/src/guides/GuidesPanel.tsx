import { useEffect, useState } from "react";

import { BoardOnly, useLook } from "../components/BoardOnly";
import { Fold } from "../components/Fold";
import { MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { StatTile } from "../components/StatTile";
import { Loading } from "../components/Unavailable";
import { EvidenceEntry } from "../evidence/EvidenceEntry";
import { type Glossary, type GuideStep, type MeasurementGuide, type MeasurementGuides, api } from "../lib/api";
import { LOADING_MARK, type RequestOutcome, UNAVAILABLE_MARK, requestOutcome } from "../lib/marks";
import { GUIDES_LABELS, basisCaption, guidePictogram, guideStepsWord, guideSummary, indicatorsLine } from "./guides";
import { tr } from "../lib/i18n";

/**
 * Cómo se toma cada medida, paso a paso, y el glosario de la consola.
 *
 * Por qué existe: el enunciado del reto pide no dar por hecho que la tripulación sabe evaluar su
 * salud, y la consola explicaba cada alerta y cada protocolo ecográfico pero no cómo tomarse la
 * tensión o la temperatura, ni qué es una «línea base» o el «tiempo de luz». Con el retardo de
 * Marte no se puede preguntar a Tierra cómo se coloca un manguito.
 *
 * Todo lo escrito es del backend (`GET /api/guides`, `GET /api/glossary`): los pasos, lo leído de
 * vuelo, lo no encontrado, las definiciones y el rótulo de su origen. Aquí solo se pliega y se
 * ordena. Cada paso lleva plegada la frase de la fuente que lo sostiene, en su idioma
 * (`lang="en"`), con su ficha del registro (`EvidenceEntry`). El panel no pone color propio,
 * porque nada de esto es un aviso; el único que aparece es la marca de alcance que `EvidenceEntry`
 * pone a la salvedad de cada ficha, como en toda lista de evidencia. Las guías dicen cómo medir, no qué hacer con el resultado (invariante 7).
 * Las dos lecturas van cada una por su cuenta: si una falla, la otra se sigue viendo.
 *
 * Tablero (decisión del usuario, 2026-11-07): bajo la concha de la maqueta, encima de todo, dos
 * fichas con cifra —cuántas guías y cuántos términos del glosario sirve el backend—, contadas de
 * las mismas listas que el panel enseña debajo. Mientras una lectura no llega, su ficha dice que
 * carga; si falló, «no disponible» en gris (el motivo va debajo, en su párrafo). Sin color propio.
 */
export function GuidesPanel() {
  const [guides, setGuides] = useState<MeasurementGuides | null>(null);
  const [guidesFailure, setGuidesFailure] = useState<RequestOutcome | null>(null);
  const [glossary, setGlossary] = useState<Glossary | null>(null);
  const [glossaryFailure, setGlossaryFailure] = useState<RequestOutcome | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .measurementGuides()
      .then((body) => {
        if (!cancelled) setGuides(body);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setGuidesFailure(requestOutcome(reason));
      });
    api
      .glossary()
      .then((body) => {
        if (!cancelled) setGlossary(body);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setGlossaryFailure(requestOutcome(reason));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section data-ui="guides" className="panel" aria-label={GUIDES_LABELS.panel}>
      <PanelTitle concept="howToRead">{GUIDES_LABELS.panel}</PanelTitle>
      <BoardOnly>
        <GuidesCounts
          guides={guidesFailure !== null ? "failed" : guides === null ? "loading" : guides.guides.length}
          terms={glossaryFailure !== null ? "failed" : glossary === null ? "loading" : glossary.terms.length}
        />
      </BoardOnly>
      {guidesFailure !== null ? (
        <p>
          <MarkOf mark={guidesFailure.mark}>
            {tr("No se pudieron leer las guías:", "Could not read the guides:")} {guidesFailure.text}
          </MarkOf>
        </p>
      ) : guides === null ? (
        <Loading />
      ) : (
        <GuidesBody guides={guides} />
      )}
      {glossaryFailure !== null ? (
        <p>
          <MarkOf mark={glossaryFailure.mark}>
            {tr("No se pudo leer el glosario:", "Could not read the glossary:")} {glossaryFailure.text}
          </MarkOf>
        </p>
      ) : glossary === null ? (
        <Loading />
      ) : (
        <GlossaryBody glossary={glossary} />
      )}
    </section>
  );
}

/** Una cuenta del tablero: la cifra, o por qué no la hay todavía. */
export type BoardCount = number | "loading" | "failed";

function countTileProps(count: BoardCount, unit?: string) {
  if (count === "loading") return { value: null, status: { mark: LOADING_MARK, word: tr("cargando", "loading") } };
  if (count === "failed") return { value: null, status: { mark: UNAVAILABLE_MARK, word: tr("no disponible", "not available") } };
  return unit === undefined ? { value: count } : { value: count, unit };
}

/** Las dos fichas del tablero: guías y términos del glosario, contados de lo que sirvió el backend. */
export function GuidesCounts({ guides, terms }: { guides: BoardCount; terms: BoardCount }) {
  return (
    <div className="board-stats guides-board" role="group" aria-label={tr("Guías y glosario", "Guides and glossary")}>
      <StatTile concept="measure" label={tr("Guías", "Guides")} {...countTileProps(guides)} />
      <StatTile concept="docs" label={tr("Glosario", "Glossary")} {...countTileProps(terms, tr("términos", "terms"))} />
    </div>
  );
}

/**
 * Las guías, cada una plegada: indicadores, pasos, lo leído de vuelo y lo no encontrado.
 *
 * Bajo la concha de la maqueta (lote «muestra», 2026-11-08), cada guía es una fila de una línea como
 * los accesos de la muestra: el dibujo de la familia de su indicador (`guidePictogram`), su título y,
 * aparte, cuántos pasos tiene. El párrafo de alcance no se pliega: dice que las guías no dicen qué
 * hacer con el resultado (invariante 7). En la clásica, como antes: el dibujo de «medir» y el rótulo
 * de `guideSummary`.
 */
export function GuidesBody({ guides }: { guides: MeasurementGuides }) {
  const board = useLook() === "reference";
  return (
    <>
      {/* El alcance se queda a la vista también en el tablero: es lo que dice que las guías no dicen
          qué hacer con el resultado (invariante 7). */}
      <p className="secondary">{guides.scope}</p>
      {guides.guides.map((guide) => (
        <Fold
          data-ui="guide"
          key={guide.id}
          {...guideSign(board, guide)}
          label={
            board ? (
              <>
                <span className="guide-title" title={guide.title}>
                  {guide.title}
                </span>{" "}
                <span className="guide-steps">{guideStepsWord(guide)}</span>
              </>
            ) : (
              guideSummary(guide)
            )
          }
        >
          <p className="secondary">
            {GUIDES_LABELS.indicators}: {indicatorsLine(guide)}
          </p>
          {guide.steps.length > 0 && <Steps steps={guide.steps} ordered />}
          {guide.in_flight.length > 0 && (
            <>
              {/* La estación, el dibujo del entorno «iss» (`lib/provenance.ts`): lo leído de vuelo es
                  de la ISS. */}
              <PanelTitle as="h4" pictogram="station">
                {GUIDES_LABELS.inFlight}
              </PanelTitle>
              <Steps steps={guide.in_flight} ordered={false} />
            </>
          )}
          {guide.not_found.length > 0 && (
            <Fold data-ui="guides-not-found" concept="searchedNotFound" label={GUIDES_LABELS.notFound}>
              <ul>
                {guide.not_found.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </Fold>
          )}
        </Fold>
      ))}
      {guides.elsewhere.map((item) => (
        <p key={item.id} className="secondary">
          {item.text}
        </p>
      ))}
    </>
  );
}

/** El signo de una guía: en el tablero, el dibujo de su indicador si lo tiene; si no, el de «medir». */
function guideSign(board: boolean, guide: MeasurementGuide) {
  const pictogram = board ? guidePictogram(guide) : null;
  return pictogram === null ? ({ concept: "measure" } as const) : { pictogram };
}

/** Pasos con su fuente plegada al lado: la frase literal, dónde y cuándo se leyó, y la ficha. */
function Steps({ steps, ordered }: { steps: GuideStep[]; ordered: boolean }) {
  const items = steps.map((step) => (
    <li key={step.text}>
      {step.text}
      <Fold data-ui="guide-step-source" concept="source" label={GUIDES_LABELS.sources}>
        {step.basis.map((basis, index) => (
          <figure key={`${basis.citation.id}-${index}`} className="research-quote">
            <blockquote lang="en">{basis.quote}</blockquote>
            <figcaption className="secondary">{basisCaption(basis)}</figcaption>
          </figure>
        ))}
        {uniqueCitations(step).map((citation) => (
          <div key={citation.id}>
            <EvidenceEntry item={citation} />
          </div>
        ))}
      </Fold>
    </li>
  ));
  return ordered ? <ol>{items}</ol> : <ul>{items}</ul>;
}

/** Una ficha citada dos veces en el mismo paso se enseña una vez. */
function uniqueCitations(step: GuideStep) {
  const seen = new Set<string>();
  return step.basis
    .map((basis) => basis.citation)
    .filter((citation) => {
      if (seen.has(citation.id)) return false;
      seen.add(citation.id);
      return true;
    });
}

/** El glosario: cada término con su definición y el rótulo de su origen, del backend. */
export function GlossaryBody({ glossary }: { glossary: Glossary }) {
  return (
    <Fold data-ui="glossary" concept="docs" label={GUIDES_LABELS.glossary}>
      <p className="secondary">{glossary.scope}</p>
      <dl>
        {glossary.terms.map((term) => (
          <div key={term.id}>
            <dt>{term.term}</dt>
            <dd>
              {term.definition}
              <br />
              <span className="secondary">
                {term.origin_display}
                {term.document !== null && (
                  <>
                    {" "}
                    · <code>{term.document}</code>
                  </>
                )}
              </span>
              {term.basis.map((basis, index) => (
                <figure key={`${basis.citation.id}-${index}`} className="research-quote">
                  <blockquote lang="en">{basis.quote}</blockquote>
                  <figcaption className="secondary">{basisCaption(basis)}</figcaption>
                </figure>
              ))}
            </dd>
          </div>
        ))}
      </dl>
    </Fold>
  );
}
