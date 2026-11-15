import { useEffect, useState } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { BoardOnly, useLook } from "../components/BoardOnly";
import { Chosen } from "../components/Chosen";
import type { ConsoleSection } from "../components/ConsoleTabs";
import { FieldLabel } from "../components/FieldLabel";
import { Fold } from "../components/Fold";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { FoldDivider, Folded } from "../components/SecondaryFold";
import { StatTile } from "../components/StatTile";
import { MatrixCell } from "../ground/MissionProfilesPanel";
import type { PictogramName } from "../icons/registry";
import { type MissionProfile, type MissionProfileChange, type ProfileMatrix, missionProfilesApi } from "../lib/api";
import { formatNumber } from "../lib/format";
import { tr } from "../lib/i18n";
import { LOADING_MARK, type RequestOutcome, UNAVAILABLE_MARK, UNKNOWN_PICTOGRAM, requestOutcome } from "../lib/marks";
import { useOperator } from "../lib/operator";
import { uiPictogram } from "../lib/uiMarks";
import { AspectStatus, ReadDates, Source } from "./MissionProfileView";
import { capitalized } from "./HazardCards";
import { PlanetThumb } from "./HomeArt";
import { Ring } from "./HomeCharts";
import { aspectPictogram, profilePictogram } from "./missionPictograms";
import { UNKNOWN_PROFILE_MARK, aspectDisplay } from "./missionProfile";
import { markTint } from "./TimelinePieces";

/**
 * Una pestaña por entorno (§5.40): órbita baja dentro de la magnetosfera, Luna, Marte… cada una
 * con lo que el backend sabe de ese perfil. Lo pidió el equipo en sus notas de voz («vistas por
 * entorno») y el usuario después: una pestaña propia por entorno, con sus peculiaridades.
 *
 * Las pestañas salen de los perfiles que sirve `GET /api/mission/profiles`, en su orden, no de
 * una lista de aquí: un perfil nuevo del backend (cislunar, una base) aparece solo, con su nombre y
 * su dibujo (`missionPictograms.ts`; sin dibujo propio, el de «desconocido»). Cada pestaña enseña
 * la columna de su perfil en la matriz perfil × aspecto, casilla a casilla con `MatrixCell` (la
 * misma de la consola de Tierra): la frase leída con sus citas plegadas, o la palabra del backend
 * en cian con el anillo punteado si no hay fuente (tabla F.5-1). Las notas de la matriz —qué es,
 * que el perfil se declara por configuración, lo médico— van debajo, tal cual.
 *
 * Las pestañas no van en el carril sino en su cabecera, debajo de «Entorno de la misión» (el
 * `headerGroup` de `ConsoleTabs`): se elige el entorno donde se dice cuál es el de la misión.
 *
 * Elegir una pestaña es **mirar** ese entorno, no declararlo. Declararlo es un mando aparte, a
 * bordo: «Declarar como entorno de la misión», en la pestaña de un entorno que no es el declarado,
 * firma un asiento por `POST /api/mission/profile` con el operador de la consola y un motivo
 * opcional (petición del usuario, 2026-11-04). El de partida es el de la configuración
 * (`declared_note`); la pestaña del declarado lleva «Perfil declarado» con el anillo de elegido.
 * Tierra lo ve y no lo declara, como el nivel de misión. Descriptivo: declarar no toca niveles,
 * alertas ni riesgo, y el rechazo se enseña con el texto del backend.
 *
 * Tablero (decisión del usuario, 2026-11-07): bajo la concha de la maqueta, encima de los aspectos,
 * el anillo de cuántos aspectos de la matriz tiene este perfil leídos en una fuente (estado `read`
 * del backend; uno sin casilla o con un estado que la interfaz no conoce no cuenta como leído), una
 * píldora por estado con la palabra del backend (`status_text`) y su marca de siempre (cian con el
 * anillo punteado lo sin verificar, gris lo desconocido), y la ficha de las páginas leídas. El anillo
 * es neutro: «leído» no lleva color en este panel y el verde de «Inicio» lo pintaría de nominal. La
 * distancia, el retardo y la gravedad no van como cifras: la matriz solo trae la frase leída de cada
 * aspecto, sin número, y no se saca uno de una frase.
 *
 * Una vista por entorno (lote «muestra», 2026-11-08: cada pestaña medía ~2700 px con diez tarjetas
 * llenas de frases citadas): cada aspecto es un mosaico con su dibujo grande, su nombre y su estado
 * con la palabra y la marca del backend, a la vista; la frase leída, lo buscado y «Frases leídas»
 * van detrás de su «Ver detalle», y las notas de la matriz y las páginas leídas, detrás de otro al
 * final. «Perfil declarado», la nota de alcance de la matriz («descriptivo…»), el texto de un perfil
 * desconocido y el mando de declarar no se pliegan. Las notas y las páginas leídas pasaron después
 * (2026-11-15) a la raya de lo secundario, plegada de partida en las dos conchas.
 * En la clásica, todo como antes salvo esa raya.
 */

/** Firma la declaración de un entorno; lanza lo que diga el backend para pintar su marca. */
export type DeclareProfile = (body: MissionProfileChange) => Promise<void>;

export type MatrixLoad = { matrix: ProfileMatrix | null; failure: RequestOutcome | null };

/**
 * La matriz, leída al montar y otra vez cuando cambia `refreshKey` (el entorno vigente del estado:
 * tras declarar otro, la columna señalada se mueve). Con `until`, la del corte de Tierra.
 */
export function useProfileMatrix(refreshKey?: string, until?: Date): MatrixLoad {
  const [load, setLoad] = useState<MatrixLoad>({ matrix: null, failure: null });
  const cut = until?.toISOString();
  useEffect(() => {
    let current = true;
    missionProfilesApi
      .get(cut === undefined ? undefined : new Date(cut))
      .then((matrix) => {
        if (current) setLoad({ matrix, failure: null });
      })
      .catch((reason: unknown) => {
        if (current) setLoad({ matrix: null, failure: requestOutcome(reason) });
      });
    return () => {
      current = false;
    };
  }, [refreshKey, cut]);
  return load;
}

export const ENVIRONMENTS_GROUP = tr("Entornos", "Environments");

/** La raya de lo secundario, compartida por todas las pestañas de entorno de las dos consolas. */
export const ENV_FOLD = "env";

function environmentPictogram(id: string): PictogramName {
  return profilePictogram(id) ?? UNKNOWN_PICTOGRAM;
}

/**
 * Las secciones del grupo «Entornos», una por perfil del backend. Mientras la matriz no llega (o si
 * falla) queda una sola pestaña que lo dice, para que el grupo no desaparezca sin explicación.
 */
export function environmentSections(load: MatrixLoad, declare?: DeclareProfile): ConsoleSection[] {
  const { matrix, failure } = load;
  if (matrix === null) {
    return [
      {
        key: "env",
        label: ENVIRONMENTS_GROUP,
        pictogram: uiPictogram("compare"),
        group: ENVIRONMENTS_GROUP,
        shared: true,
        panels: [
          <section data-ui="environments" className="panel" aria-label={tr("Entornos de misión", "Mission environments")} key="env">
            <PanelTitle concept="compare">{tr("Entornos de misión", "Mission environments")}</PanelTitle>
            {failure === null ? (
              <p className="secondary">
                <MarkOf mark={LOADING_MARK}>{tr("Consultando los perfiles de misión…", "Fetching the mission profiles…")}</MarkOf>
              </p>
            ) : (
              <p>
                <MarkOf mark={failure.mark}>{tr(`Perfiles de misión no disponibles: ${failure.text}`, `Mission profiles unavailable: ${failure.text}`)}</MarkOf>
              </p>
            )}
          </section>,
        ],
      },
    ];
  }
  return matrix.profiles.map((profile) => ({
    key: `env-${profile.id}`,
    label: capitalized(profile.display),
    pictogram: environmentPictogram(profile.id),
    group: ENVIRONMENTS_GROUP,
    ...(profile.declared ? { note: <Chosen chosen>{tr("Perfil declarado", "Declared profile")}</Chosen> } : {}),
    // Inventario de la misión, sin nada personal: a la vista también en privacidad.
    shared: true,
    panels: [<EnvironmentView matrix={matrix} profileId={profile.id} {...(declare === undefined ? {} : { declare })} />],
  }));
}

/** La columna de un perfil de la matriz, aspecto a aspecto, con las notas de la matriz. */
export function EnvironmentView({
  matrix,
  profileId,
  declare,
}: {
  matrix: ProfileMatrix;
  profileId: string;
  /** Solo a bordo: sin él, la pestaña no ofrece declarar. */
  declare?: DeclareProfile;
}) {
  const board = useLook() === "reference";
  const profile = matrix.profiles.find((item) => item.id === profileId);
  if (profile === undefined) return null;
  return (
    <section data-ui="environment-profile" className="panel" aria-label={profile.display}>
      <PanelTitle pictogram={environmentPictogram(profile.id)}>{capitalized(profile.display)}</PanelTitle>
      {profile.declared && (
        <p>
          <Chosen chosen>{tr("Perfil declarado", "Declared profile")}</Chosen>
        </p>
      )}
      <p className="secondary">{matrix.note}</p>
      <BoardOnly>
        <EnvironmentBoard matrix={matrix} profileId={profile.id} />
      </BoardOnly>
      {!profile.declared && declare !== undefined && <DeclareEnvironment profileId={profile.id} declare={declare} />}
      {profile.declared && matrix.declared_text !== null && (
        <p>
          <MarkOf mark={UNKNOWN_PROFILE_MARK}>{matrix.declared_text}</MarkOf>
        </p>
      )}
      <dl className="environment-aspects">
        {matrix.aspects.map((aspect) => {
          const cell = profile.cells.find((item) => item.key === aspect.key) ?? null;
          return (
            <div key={aspect.key}>
              <dt>
                <Mark pictogram={aspectPictogram(aspect.key)}>{aspect.label}</Mark>
              </dt>
              <dd>
                {/* Mosaico (2026-11-08, la muestra): a la vista, el estado del aspecto con su marca
                    (cian «sin verificar»); la frase leída, lo buscado y «Frases leídas», detrás de
                    «Ver detalle». La matriz no trae cifra propia por aspecto y no se saca de la frase.
                    Que una fuente discrepe se dice en el mosaico (el texto, dentro): un aspecto
                    discutido no se lee como zanjado. Sin casilla, «no disponible» en gris. */}
                {board && (
                  <p className="environment-aspect-state">
                    {cell === null ? (
                      <MarkOf mark={UNAVAILABLE_MARK}>{tr("no disponible", "unavailable")}</MarkOf>
                    ) : (
                      <AspectStatus status={cell.status}>{cell.status_text}</AspectStatus>
                    )}
                    {cell?.discrepancy != null && (
                      <>
                        <br />
                        <span className="secondary">{tr("otra fuente discrepa", "another source disagrees")}</span>
                      </>
                    )}
                  </p>
                )}
                {cell !== null && (
                  <BoardDetail label={aspect.label}>
                    <MatrixCell cell={cell} />
                  </BoardDetail>
                )}
              </dd>
            </div>
          );
        })}
      </dl>
      {/* Lo secundario de la pestaña, bajo la raya de «Inicio» y plegado de partida (decisión del
          usuario, 2026-11-15: «reducir los componentes en interfaz con un botón desplegable como el
          que hay en Inicio en el resto de pestañas»). La pestaña es un solo panel, así que la raya
          va dentro, encima de lo único secundario: las notas de la matriz y las páginas leídas, que
          antes iban detrás de su «Ver detalle» (no se pliegan dos veces). Son de la matriz entera,
          iguales en cada entorno y en las dos consolas: por eso una sola raya, `env`, para todas;
          plegar una pestaña de entorno las pliega todas. Arriba siguen el estado de cada aspecto,
          «Perfil declarado», la nota de alcance, el perfil desconocido y el mando de declarar. */}
      <FoldDivider id={ENV_FOLD} what={tr("Notas de la matriz y páginas leídas", "Matrix notes and pages read")} />
      <Folded id={ENV_FOLD}>
        <div className="environment-notes">
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
        </div>
      </Folded>
    </section>
  );
}

/** Los aspectos de un perfil por estado, en el orden de la matriz: palabra del backend y cuenta. */
export function aspectTally(matrix: ProfileMatrix, profileId: string) {
  const profile = matrix.profiles.find((item) => item.id === profileId);
  const tally = new Map<string, { word: string; count: number }>();
  let read = 0;
  for (const aspect of matrix.aspects) {
    const cell = profile?.cells.find((item) => item.key === aspect.key);
    if (cell === undefined) continue;
    if (cell.status === "read") read += 1;
    const entry = tally.get(cell.status);
    if (entry === undefined) tally.set(cell.status, { word: cell.status_text, count: 1 });
    else entry.count += 1;
  }
  return { read, total: matrix.aspects.length, tally: [...tally].map(([status, entry]) => ({ status, ...entry })) };
}

/** El anillo de aspectos leídos, las píldoras por estado y la ficha de páginas leídas. */
function EnvironmentBoard({ matrix, profileId }: { matrix: ProfileMatrix; profileId: string }) {
  const { read, total, tally } = aspectTally(matrix, profileId);
  return (
    <div className="board-row environment-board">
      {/* La miniatura del destino, la de los botones de ubicación de «Inicio» (adorno, `aria-hidden`):
          la tarjeta de «Ruta activa» de la maqueta lleva su planeta al lado de las cifras. */}
      <span className="environment-planet">
        <PlanetThumb id={profileId} />
      </span>
      <div className="ref-ring-col">
        <Ring done={read} total={total} label={tr("aspectos leídos en una fuente", "aspects read in a source")}>
          <span className="num ref-ring-value">{formatNumber(read)}</span>
          <span className="num secondary">/ {formatNumber(total)}</span>
        </Ring>
        <p className="secondary ref-ring-caption">{tr("leídos", "read")}</p>
      </div>
      {tally.length > 0 && (
        <ul className="board-tally" aria-label={tr("Aspectos por estado", "Aspects by state")}>
          {tally.map((entry) => {
            const look = aspectDisplay(entry.status).mark;
            return (
              <li key={entry.status} className="ref-pill board-pill" style={markTint(look)}>
                <MarkOf mark={look}>{entry.word}</MarkOf> <span className="num">{formatNumber(entry.count)}</span>
              </li>
            );
          })}
        </ul>
      )}
      <div className="board-stats environment-stats">
        <StatTile concept="source" label={tr("Páginas leídas", "Pages read")} value={matrix.pages_read.length} />
      </div>
    </div>
  );
}

/** El entorno declarado de la misión, en la cabecera del carril: siempre a la vista. */
export function ActiveEnvironment({ profile }: { profile: MissionProfile | null | undefined }) {
  if (profile == null) return null;
  return (
    <p className="active-environment">
      <span className="secondary">{tr("Entorno de la misión", "Mission environment")}</span>
      <br />
      <strong>
        <Mark pictogram={environmentPictogram(profile.id)}>{profile.display}</Mark>
      </strong>
    </p>
  );
}

/**
 * «Declarar como entorno de la misión»: quién (el operador de la consola) y un motivo opcional. El
 * backend decide si se puede (`core/mission_profile_changes.py`); un rechazo se enseña con su texto
 * y su marca (`requestOutcome`), como el cambio de nivel de misión.
 */
export function DeclareEnvironment({ profileId, declare }: { profileId: string; declare: DeclareProfile }) {
  const [operator, setOperator] = useOperator();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<RequestOutcome | null>(null);
  // Mientras va una declaración no se pide otra: un doble clic cruzaría dos peticiones.
  const [sending, setSending] = useState(false);
  const send = async () => {
    setError(null);
    setSending(true);
    try {
      await declare({ profile: profileId, reason: reason.trim(), declared_by: operator.trim() });
      setReason("");
    } catch (failure) {
      setError(requestOutcome(failure));
    } finally {
      setSending(false);
    }
  };
  return (
    <Fold data-ui="environment-declare" concept="systems" label={tr("Declarar como entorno de la misión", "Declare as the mission environment")}>
      <div className="silence-form">
        <FieldLabel concept="person">
          {tr("Quién", "Who")} <input value={operator} maxLength={64} onChange={(event) => setOperator(event.target.value)} />
        </FieldLabel>
        <FieldLabel concept="reason">
          {tr("Motivo", "Reason")} <input value={reason} maxLength={300} onChange={(event) => setReason(event.target.value)} />
        </FieldLabel>
        <button className="command" disabled={sending || operator.trim() === ""} onClick={() => void send()}>
          <Mark pictogram="pen">{tr("Declarar como entorno de la misión", "Declare as the mission environment")}</Mark>
        </button>
        {error !== null && (
          <p>
            <MarkOf mark={error.mark}>{error.text}</MarkOf>
          </p>
        )}
      </div>
    </Fold>
  );
}
