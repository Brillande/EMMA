import { useEffect, useState } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { useLook } from "../components/BoardOnly";
import { Fold } from "../components/Fold";
import { MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { StatTile } from "../components/StatTile";
import {
  type People,
  type PeopleNamedBy,
  type PeoplePerson,
  type PeopleReference,
  peopleApi,
} from "../lib/api";
import { tr } from "../lib/i18n";
import { LOADING_MARK, MISSING_MARK, NO_MARK, type RequestOutcome, requestOutcome } from "../lib/marks";
import { ORGANIZATION_CONCEPT, PEOPLE_CONCEPT, authorsLine, countOf, yearCell } from "./people";

/**
 * Personas y organizaciones de las fuentes (la pestaña «People & Organizations» de la
 * conversación de ideación; base de conocimiento §15, P2).
 *
 * Todo sale de `GET /api/people`, que lo deriva del registro de evidencia en cada consulta: cada
 * organización que da una ficha o que una ficha nombra, plegada, con sus fichas, su año y quién las firma; y cada persona
 * con las fichas que la citan y su papel en ellas, como lo compone el backend. La organización de
 * una ficha se enseña como de la ficha, nunca junto a un nombre como si fuera su afiliación: la
 * afiliación solo sale cuando el documento la escribe junto a ese nombre (`affiliation_text`). Una
 * organización que una fuente nombra sin darla sale con las fichas que la nombran, aparte. Son
 * personas reales: aquí no hay más que lo que escriben las fichas, y ningún dato de contacto.
 *
 * Inventario de solo lectura: no interviene en el estado de la tripulación.
 *
 * Tablero (2026-11-07): bajo la concha de la maqueta los tres recuentos pasan de la frase a tres
 * fichas con cifra (`StatTile`); son las mismas cuentas, así que sustituyen a la frase (`useLook`).
 * Ninguna ficha lleva un nombre: solo cuántas organizaciones, personas y fichas hay.
 */
export function PeoplePanel() {
  const [people, setPeople] = useState<People | null>(null);
  const [failure, setFailure] = useState<RequestOutcome | null>(null);

  useEffect(() => {
    let current = true;
    peopleApi
      .get()
      .then((body) => {
        if (current) setPeople(body);
      })
      .catch((reason: unknown) => {
        if (current) setFailure(requestOutcome(reason));
      });
    return () => {
      current = false;
    };
  }, []);

  if (people === null) {
    return (
      <section data-ui="people" className="panel" aria-label={tr("Personas y organizaciones", "People and organizations")}>
        <PanelTitle concept={PEOPLE_CONCEPT}>{tr("Personas y organizaciones", "People and organizations")}</PanelTitle>
        {failure === null ? (
          <p className="secondary">
            <MarkOf mark={LOADING_MARK}>{tr("Consultando personas y organizaciones…", "Loading people and organizations…")}</MarkOf>
          </p>
        ) : (
          <p>
            <MarkOf mark={failure.mark}>{tr("Personas y organizaciones no disponibles:", "People and organizations unavailable:")} {failure.text}</MarkOf>
          </p>
        )}
      </section>
    );
  }
  return <PeopleView people={people} />;
}

/** Lo ya recibido. Aparte del que consulta para poder pintarlo en las pruebas sin red. */
export function PeopleView({ people }: { people: People }) {
  const board = useLook() === "reference";
  return (
    <section data-ui="people" className="panel" aria-label={tr("Personas y organizaciones", "People and organizations")}>
      <PanelTitle concept={PEOPLE_CONCEPT}>{tr("Personas y organizaciones", "People and organizations")}</PanelTitle>
      {/* Lote «muestra» (2026-11-08): las reglas, tras «Ver detalle» en el tablero. */}
      <BoardDetail label={tr("cómo se cuentan", "how they are counted")}>
        <p className="secondary">{people.note}</p>
        <p className="secondary">{people.affiliation_rule}</p>
        <p className="secondary">{people.named_organization_rule}</p>
      </BoardDetail>
      {board ? (
        <div className="board-stats" role="group" aria-label={tr("Personas y organizaciones de las fuentes", "People and organizations in the sources")}>
          <StatTile concept={ORGANIZATION_CONCEPT} label={tr("Organizaciones", "Organizations")} value={people.organizations.length} />
          <StatTile concept={PEOPLE_CONCEPT} label={tr("Personas", "People")} value={people.people.length} />
          <StatTile concept="document" label={tr("Fichas del registro", "Registry records")} value={people.references} />
        </div>
      ) : (
        <p>
          {countOf(people.organizations.length, tr("organización", "organization"), tr("organizaciones", "organizations"))}
          {" · "}
          {countOf(people.people.length, tr("persona", "person"), tr("personas", "people"))}
          {" · "}
          {countOf(people.references, tr("ficha del registro", "registry record"), tr("fichas del registro", "registry records"))}
        </p>
      )}

      {/* Cuarta ronda (R4-8, 2026-11-08): las organizaciones y las personas, dos baldosas lado a lado
          bajo la concha de la maqueta (`.board-parts`). En la clásica los envoltorios no pintan
          nada: el mismo orden de siempre. */}
      <div className="board-parts">
      <div className="board-part">
      <PanelTitle as="h3" concept={ORGANIZATION_CONCEPT} className="section-gap">
        {tr("Organizaciones", "Organizations")}
      </PanelTitle>
      {/* Lote «muestra», segunda ronda (2026-11-08): las filas de organización (pasan del centenar)
          iban en baldosas dentro de una caja con barra de desplazamiento. Ahora, tras «Ver detalle»
          (plegables con `data-ui`: el asistente abre el detalle para llegar a ellos), sin caja: su
          número va en la ficha de arriba. La fila de las fichas sin organización lleva la marca de
          dato ausente y queda fuera, a la vista. */}
      <BoardDetail label={tr("una fila por organización", "one row per organization")}>
      <div className="people-orgs">
      {people.organizations.map((org) => (
        <Fold data-ui="organization"
          key={org.name}
          concept={ORGANIZATION_CONCEPT}
          aria-label={tr(`Organización ${org.name}`, `Organization ${org.name}`)}
          label={
            <>
              <strong>{org.name}</strong>
              <span className="secondary"> · {countOf(org.references.length, tr("ficha", "record"), tr("fichas", "records"))}</span>
              {org.named_by.length > 0 && (
                <span className="secondary">
                  {" "}
                  · {org.named_by.length === 1 ? tr("la nombra", "named by") : tr("la nombran", "named by")}{" "}
                  {countOf(org.named_by.length, tr("ficha", "record"), tr("fichas", "records"))}
                </span>
              )}
            </>
          }
        >
          {org.references.length > 0 && <ReferenceList references={org.references} noYear={people.no_year} />}
          {org.named_by.length > 0 && <NamedByList items={org.named_by} noYear={people.no_year} />}
        </Fold>
      ))}
      </div>
      </BoardDetail>
      {people.without_organization.length > 0 && (
        <Fold data-ui="people-no-organization"
          mark={MISSING_MARK}
          aria-label={people.no_organization}
          label={
            <>
              <strong>{people.no_organization}</strong>
              <span className="secondary">
                {" "}
                · {countOf(people.without_organization.length, tr("ficha", "record"), tr("fichas", "records"))}
              </span>
            </>
          }
        >
          <ReferenceList references={people.without_organization} noYear={people.no_year} />
        </Fold>
      )}
      </div>

      <div className="board-part">
      <PanelTitle as="h3" concept={PEOPLE_CONCEPT} className="section-gap">
        {tr("Personas", "People")}
      </PanelTitle>
      <BoardDetail label={tr("cuándo es la misma persona", "when it is the same person")}>
        <p className="secondary">{people.same_person_rule}</p>
      </BoardDetail>
      <Fold data-ui="people-of-records"
        concept={PEOPLE_CONCEPT}
        aria-label={tr("Personas de las fichas", "People in the records")}
        label={<strong>{countOf(people.people.length, tr("persona", "person"), tr("personas", "people"))}</strong>}
      >
        <ul className="evidence">
          {people.people.map((person) => (
            <PersonLine
              key={person.name}
              person={person}
              noYear={people.no_year}
              noOrganization={people.no_organization}
            />
          ))}
        </ul>
      </Fold>
      </div>
      </div>
    </section>
  );
}

/** Las fichas de una organización: título, año, clase de documento, la cita y quién firma. */
function ReferenceList({ references, noYear }: { references: PeopleReference[]; noYear: string }) {
  return (
    <ul className="evidence">
      {references.map((ref) => {
        const year = yearCell(ref.year, noYear);
        const authors = authorsLine(ref);
        return (
          <li key={ref.id}>
            <span lang="en">{ref.title}</span>
            <span className="secondary">
              {" · "}
              <MarkOf mark={year.mark}>
                <span className={year.mark === NO_MARK ? "num" : undefined}>{year.text}</span>
              </MarkOf>
              {" · "}
              {ref.evidence_type_display}
            </span>
            {authors !== null && (
              <div>
                {tr("Firman:", "Signed by:")} <span lang="en">{authors}</span>
              </div>
            )}
            {ref.named_people.map((named) => (
              <div key={named.name}>
                <strong>{named.name}</strong>: {named.role_text}
              </div>
            ))}
            {ref.affiliations.map((item) => (
              <div key={item.name}>
                <strong>{item.name}</strong>: {item.text}
              </div>
            ))}
            {ref.named_organizations.map((item) => (
              <div key={item.name}>
                <strong>{item.name}</strong>: {item.role_text}
              </div>
            ))}
            <div className="secondary">
              <span lang="en">{ref.source}</span> · <span className="num wrap">{ref.id}</span>
            </div>
            {ref.url !== null && <div className="secondary num url">{ref.url}</div>}
          </li>
        );
      })}
    </ul>
  );
}

/** Las fichas que nombran a una organización sin ser suyas: el papel, el título y su año. */
function NamedByList({ items, noYear }: { items: PeopleNamedBy[]; noYear: string }) {
  return (
    <ul className="evidence">
      {items.map((item) => {
        const year = yearCell(item.year, noYear);
        return (
          <li key={`${item.ref}:${item.role}`}>
            {item.role_text} · <span lang="en">{item.title}</span>
            <span className="secondary">
              {" · "}
              <MarkOf mark={year.mark}>
                <span className={year.mark === NO_MARK ? "num" : undefined}>{year.text}</span>
              </MarkOf>
              {" · "}
              <span className="num wrap">{item.ref}</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Una persona con las fichas que la citan: el papel que compone el backend, el título de la ficha,
 * su año y la organización que da la ficha, dicha como de la ficha.
 */
function PersonLine({
  person,
  noYear,
  noOrganization,
}: {
  person: PeoplePerson;
  noYear: string;
  noOrganization: string;
}) {
  return (
    <li>
      <strong>{person.name}</strong>
      <ul className="mt-0">
        {person.citations.map((citation) => {
          const year = yearCell(citation.year, noYear);
          return (
            <li key={`${citation.ref}:${citation.role}`}>
              {citation.role_text} · <span lang="en">{citation.title}</span>
              <span className="secondary">
                {" · "}
                <MarkOf mark={year.mark}>
                  <span className={year.mark === NO_MARK ? "num" : undefined}>{year.text}</span>
                </MarkOf>
                {" · "}
                {citation.organization !== null ? (
                  <>{tr("organización de la ficha:", "organization of the record:")} {citation.organization}</>
                ) : (
                  <MarkOf mark={MISSING_MARK}>{noOrganization}</MarkOf>
                )}
              </span>
              {citation.affiliation_text !== null && <div>{citation.affiliation_text}</div>}
            </li>
          );
        })}
      </ul>
    </li>
  );
}
