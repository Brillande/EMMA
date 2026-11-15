import { useEffect, useState } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { BoardOnly, useLook } from "../components/BoardOnly";
import { Chosen } from "../components/Chosen";
import { Fold } from "../components/Fold";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { Th } from "../components/Th";
import { AspectStatus, ReadDates, Source } from "../dashboard/MissionProfileView";
import { aspectPictogram, profilePictogram } from "../dashboard/missionPictograms";
import { UNKNOWN_PROFILE_MARK } from "../dashboard/missionProfile";
import { type ProfileCitation, type ProfileMatrix, type ProfileMatrixCell, missionProfilesApi } from "../lib/api";
import { formatNumber, formatSourceDate } from "../lib/format";
import { tr } from "../lib/i18n";
import { LOADING_MARK, type RequestOutcome, requestOutcome } from "../lib/marks";

/**
 * Los perfiles de misión lado a lado (base de conocimiento §15, P1: «ISS vs Artemis vs
 * Mars», matriz de requisitos y autonomía). `/api/status` solo trae el perfil declarado; aquí
 * van todos, una columna por perfil y una fila por aspecto, en el orden del backend, con la
 * columna del perfil declarado señalada con el signo de «elegido».
 *
 * Solo pinta: cada frase, rótulo y nota es de `GET /api/mission/profiles`. Una casilla sin frase
 * lleva la palabra del backend («EMMA no tiene fuente») en cian con el anillo punteado (tabla
 * F.5-1: dato ausente), igual que «sin verificar» en el perfil declarado. Las citas literales van
 * plegadas en cada casilla, con su página y el día de lectura (`formatSourceDate`); la cuenta del
 * plegable, por `formatNumber`. Las cifras de retardo y de duración están dentro de la frase del
 * backend: la interfaz no las saca ni las recompone.
 *
 * Descriptivo: nada de aquí toca niveles, alertas ni el riesgo, que no pasan por este fichero.
 */
export function MissionProfilesPanel() {
  const [matrix, setMatrix] = useState<ProfileMatrix | null>(null);
  const [failure, setFailure] = useState<RequestOutcome | null>(null);

  useEffect(() => {
    let current = true;
    missionProfilesApi
      .get()
      .then((body) => {
        if (current) setMatrix(body);
      })
      .catch((reason: unknown) => {
        if (current) setFailure(requestOutcome(reason));
      });
    return () => {
      current = false;
    };
  }, []);

  if (matrix === null) {
    return (
      <section data-ui="mission-profiles" className="panel" aria-label={tr("Perfiles de misión lado a lado", "Mission profiles side by side")}>
        <PanelTitle concept="compare">{tr("Perfiles de misión lado a lado", "Mission profiles side by side")}</PanelTitle>
        {failure === null ? (
          <p className="secondary">
            <MarkOf mark={LOADING_MARK}>{tr("Consultando los perfiles de misión…", "Fetching the mission profiles…")}</MarkOf>
          </p>
        ) : (
          <p>
            <MarkOf mark={failure.mark}>{tr(`Perfiles de misión no disponibles: ${failure.text}`, `Mission profiles unavailable: ${failure.text}`)}</MarkOf>
          </p>
        )}
      </section>
    );
  }
  return <MissionProfilesView matrix={matrix} />;
}

/** La matriz ya recibida. Aparte del que consulta para poder pintarla en las pruebas sin red. */
export function MissionProfilesView({ matrix }: { matrix: ProfileMatrix }) {
  const board = useLook() === "reference";
  const declared = matrix.declared_text !== null && (
    <p>
      <MarkOf mark={UNKNOWN_PROFILE_MARK}>{matrix.declared_text}</MarkOf>
    </p>
  );
  return (
    <section data-ui="mission-profiles" className="panel" aria-label={tr("Perfiles de misión lado a lado", "Mission profiles side by side")}>
      <PanelTitle concept="compare">{tr("Perfiles de misión lado a lado", "Mission profiles side by side")}</PanelTitle>
      {/* Lote «muestra», segunda ronda (2026-11-08): la tabla (cada casilla con su frase) iba en una
          caja de 24 rem que se recorría dentro. En el tablero, la marca del perfil sin declarar, los
          perfiles y cuántas casillas hay de cada estado de lectura, con la marca de la casilla (la de
          lo no encontrado incluida: no se pliega); la tabla, las notas y las páginas leídas, tras un
          solo «Ver detalle», en el orden de la clásica. */}
      {board && declared}
      <BoardOnly>
        <ProfileTally matrix={matrix} />
      </BoardOnly>
      <BoardDetail label={tr("tabla, notas y páginas leídas", "table, notes and pages read")}>
        <p className="secondary">{matrix.note}</p>
      {!board && declared}
      <div className="quality-table table-scroll" role="region" tabIndex={0} aria-label={tr("Perfil por aspecto", "Profile by aspect")}>
        <table className="recovery profile-matrix">
          <thead>
            <tr>
              <Th concept="detail">{tr("Aspecto", "Aspect")}</Th>
              {matrix.profiles.map((profile) => (
                <th key={profile.id} scope="col">
                  <Mark pictogram={profilePictogram(profile.id)}>{profile.display}</Mark>
                  {profile.declared && (
                    <div className="secondary">
                      <Chosen chosen>{tr("Perfil declarado", "Declared profile")}</Chosen>
                    </div>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.aspects.map((aspect) => (
              <tr key={aspect.key}>
                <th scope="row">
                  <Mark pictogram={aspectPictogram(aspect.key)}>{aspect.label}</Mark>
                </th>
                {matrix.profiles.map((profile) => (
                  <td key={profile.id}>
                    <MatrixCell cell={profile.cells.find((cell) => cell.key === aspect.key) ?? null} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="secondary">{matrix.declared_note}</p>
      <p className="secondary">{matrix.reused_note}</p>
      <p className="secondary">{matrix.medical_note}</p>
      <p className="secondary">
        {tr("Páginas leídas:", "Pages read:")}{" "}
        {matrix.pages_read.map((page, index) => (
          <span key={page.title}>
            {index > 0 && " · "}
            <Source title={page.title} url={page.url} /> (<ReadDates dates={page.read_on} />)
          </span>
        ))}
      </p>
      </BoardDetail>
    </section>
  );
}

/**
 * Las piezas del tablero: un perfil por píldora, con su dibujo (y el anillo del declarado), y cuántas
 * casillas hay de cada estado de lectura, con la marca y la palabra del backend de la primera.
 */
function ProfileTally({ matrix }: { matrix: ProfileMatrix }) {
  const states = new Map<string, { word: string; count: number }>();
  for (const profile of matrix.profiles) {
    for (const cell of profile.cells) {
      const entry = states.get(cell.status);
      if (entry === undefined) states.set(cell.status, { word: cell.status_text, count: 1 });
      else entry.count += 1;
    }
  }
  return (
    <ul className="board-tally" aria-label={tr("Perfiles y casillas por estado", "Profiles and cells by state")}>
      {matrix.profiles.map((profile) => (
        <li key={profile.id} className="ref-pill board-pill">
          <span>
            <Mark pictogram={profilePictogram(profile.id)}>{profile.display}</Mark>
            {profile.declared && (
              <>
                {" "}
                <Chosen chosen>{tr("Perfil declarado", "Declared profile")}</Chosen>
              </>
            )}
          </span>
        </li>
      ))}
      {[...states].map(([status, entry]) => (
        <li key={status} className="ref-pill board-pill">
          <span>
            <AspectStatus status={status}>{entry.word}</AspectStatus>{" "}
            <span className="num">{formatNumber(entry.count)}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

/** La casilla del aspecto en la columna de un perfil, buscada por clave y no por posición. La usan también las pestañas de entorno (`dashboard/Environments.tsx`). */
export function MatrixCell({ cell }: { cell: ProfileMatrixCell | null }) {
  if (cell === null) return null;
  const quotes = [...cell.citations, ...(cell.discrepancy?.citations ?? [])];
  return (
    <>
      {cell.status === "read" ? cell.text : <AspectStatus status={cell.status}>{cell.text}</AspectStatus>}
      {cell.searched !== null && <div className="secondary">{cell.searched}</div>}
      {cell.discrepancy !== null && <div>{cell.discrepancy.text}</div>}
      {cell.emma_note !== null && <div className="secondary">{cell.emma_note}</div>}
      {cell.reused_from.length > 0 && (
        <div className="secondary">{tr("Leída antes para:", "Read earlier for:")} {cell.reused_from.join(" · ")}</div>
      )}
      {quotes.length > 0 && (
        <Fold data-ui="profile-matrix-statements" concept="sourceText" label={<>{tr("Frases leídas", "Statements read")} (<span className="num">{formatNumber(quotes.length)}</span>)</>}>
          <ul className="drivers">
            {quotes.map((item, index) => (
              <Quote key={`${index}|${item.ref}|${item.read_on}`} item={item} />
            ))}
          </ul>
        </Fold>
      )}
    </>
  );
}

/** La frase tal cual se leyó, con su página, su apartado y el día de lectura. */
function Quote({ item }: { item: ProfileCitation }) {
  return (
    <li className="secondary">
      <q lang="en">{item.quote}</q> — <Source title={item.title} url={item.url} />, {item.section}; {tr("leído el", "read on")}{" "}
      <span className="num">{formatSourceDate(item.read_on)}</span>
    </li>
  );
}
