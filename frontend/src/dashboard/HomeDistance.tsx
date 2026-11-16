import { useEffect, useState } from "react";

import { Command } from "../components/Command";
import { FieldLabel } from "../components/FieldLabel";
import { Mark, MarkOf } from "../components/Mark";
import { OperatorInput } from "../components/OperatorInput";
import { PanelTitle } from "../components/PanelTitle";
import { Loading, Unavailable } from "../components/Unavailable";
import { type CrewOverview, type CrewStatus, type LinkSync, type Sharing, api, sharingApi } from "../lib/api";
import { commsMark, commsStatusOf } from "../lib/commsStatus";
import { type BodyDistance, type Distances, type EarthLink, type IssOrbit, distanceApi, epochOf } from "../lib/distanceApi";
import { formatMinutes, formatNumber, formatUtc } from "../lib/format";
import { tr } from "../lib/i18n";
import { LINK_DOWN_MARK, LINK_OFFSETS_HOURS, backlogMark, linkChange, linkInstant } from "../lib/linkSync";
import {
  LOADING_MARK,
  MISSING_MARK,
  OK_MARK,
  type RequestOutcome,
  type StateMark,
  UNAVAILABLE_MARK,
  requestOutcome,
} from "../lib/marks";
import { freshnessOf } from "../lib/staleness";
import { uiPictogram } from "../lib/uiMarks";
import type { Fetched } from "./HomeBoard";
import { PlanetThumb } from "./HomeArt";
import "./referenceDashboard.css";
import "./homeDistance.css";

/**
 * Las filas «Distancia y comunicaciones» y «Sincronización y datos» de la maqueta de la ISS (lote
 * «reservas», 2026-11-14), con el estilo de «Inicio» y «Radiación», y adaptadas a la ubicación
 * elegida en «Ubicación de la tripulación» (Ellande: «se tiene que adaptar al resto de ubicaciones y
 * distancia y nodos»). Quien la monta le pasa el perfil enseñado (`home.shownRoute`), el estado y el
 * enlace simulado que la consola ya tiene; no lee estado global nuevo.
 *
 * De dónde sale cada cifra (nada de la maqueta: ni «400 km (ISS)», ni «Luna 384.400 km», ni «Marte
 * 55 M-401 M km», ni «Almacenamiento 76 %», ni «Versión v1.6.5 / Actualizar»):
 * - La distancia geocéntrica de la Luna y de Marte, y su tiempo de luz: `GET /api/distances`, el
 *   cálculo local con SPICE (`environment/distances.py`). Sin núcleos, «sin dato» en cian con el
 *   motivo del backend.
 * - El retardo con Tierra: con el perfil declarado, el del estado (`comms`, `comms_status`), el mismo
 *   de la franja; con otro perfil, el de `/api/distances` (SPICE o la caché de Horizons, sin red). Un
 *   perfil sin objetivo de efemérides dice «No aplica» en gris (`lib/commsStatus.ts`), no un número.
 * - En órbita baja, la distancia de la ISS al centro de la Tierra, de las efemérides de SSCweb
 *   (`/api/orbit/iss`): solo con ese perfil declarado, y es una efeméride, no telemetría.
 * - Nodos: EMMA no tiene red de relés declarada. Lo que hay de verdad son los otros tripulantes con
 *   lecturas (`/api/crew`, con su módulo si consta), la consola de Tierra (con el retardo de arriba) y
 *   el enlace simulado (`/api/link-sync`). Ni «Gateway», ni «Lunar Base-1», ni «Mars Relay».
 * - Sincronización: el modo sin red (`/api/sharing`, `EMMA_OFFLINE`, el modo nominal de misión, no
 *   uno degradado), el enlace simulado declarado por una persona (lo pendiente de enviar y hasta dónde
 *   tiene Tierra) y el registro firmado del estado. El espacio en disco no lo expone el backend: se
 *   dice «no disponible» en gris.
 */

/** Nombre corto por perfil, el mismo de «Inicio»; el del backend va en `title`. */
const PROFILE_SHORT: Record<string, string> = {
  leo: tr("Órbita baja", "Low Earth orbit"),
  cislunar: "Cislunar",
  "lunar-surface": tr("Luna", "Moon"),
  "mars-transit": tr("Tránsito a Marte", "Mars transit"),
  "mars-surface": tr("Marte", "Mars"),
};

/** Dibujo de cada fila (decorado: `PlanetThumb` elige la textura por el prefijo). */
const THUMB: Record<string, string> = { earth: "earth", moon: "lunar", mars: "mars" };

/** Una distancia legible: kilómetros enteros hasta un millón; después, millones con un decimal. */
export function formatKm(km: number): string {
  return km < 1_000_000 ? `${formatNumber(km)} km` : `${formatNumber(km / 1_000_000, 1)} M km`;
}

/** Un tiempo de luz: segundos con dos decimales (o uno desde 10 s) por debajo del minuto; si no, minutos. */
export function formatLightTime(seconds: number): string {
  if (seconds < 60) return `${formatNumber(seconds, seconds < 10 ? 2 : 1)} s`;
  return formatMinutes(seconds / 60);
}

/** El retardo que se enseña: una cifra (con su fuente y si está caducada) o la marca y su palabra. */
export type LinkFigure =
  | { kind: "shown"; seconds: number; source: string | null; stale: boolean; text: string | null }
  | { kind: "absent"; mark: StateMark; word: string; text: string | null };

const ABSENT_WORD: Record<"not_applicable" | "missing", string> = {
  not_applicable: tr("No aplica", "Not applicable"),
  missing: tr("Sin efemérides", "No ephemeris"),
};

/**
 * El retardo con Tierra del perfil enseñado. Con el declarado manda el estado (la misma cifra que la
 * franja y «Rutas espaciales»); con otro, `earth_link` de `/api/distances`.
 */
export function linkFigure(
  profileId: string | null,
  status: Pick<CrewStatus, "comms" | "freshness" | "mission">,
  distances: Fetched<Distances>,
): LinkFigure {
  const declared = status.mission.profile?.id ?? null;
  if (profileId !== null && profileId === declared) {
    const said = commsStatusOf(status);
    if (said.state === "available" && status.comms !== null) {
      return {
        kind: "shown",
        seconds: status.comms.one_way_minutes * 60,
        source: said.source_text,
        stale: freshnessOf(status.freshness?.comms) !== "fresh",
        text: said.text || null,
      };
    }
    const state = said.state === "available" ? "missing" : said.state;
    // «Disponible» sin ventana no es un retardo: se dice como el dato ausente, no con la palabra del backend.
    const word = state === said.state && said.word !== "" ? said.word : ABSENT_WORD[state];
    return { kind: "absent", mark: commsMark(state), word, text: said.text || null };
  }
  if (distances.state === "loading") return { kind: "absent", mark: LOADING_MARK, word: tr("Cargando…", "Loading…"), text: null };
  if (distances.state === "failed") {
    return { kind: "absent", mark: distances.outcome.mark, word: tr("Sin datos", "No data"), text: distances.outcome.text };
  }
  return earthLinkFigure(distances.value.earth_link, distances.value.unknown_text);
}

function earthLinkFigure(link: EarthLink | null, unknownText: string | null): LinkFigure {
  if (link === null) {
    return { kind: "absent", mark: UNAVAILABLE_MARK, word: tr("Perfil no reconocido", "Unrecognized profile"), text: unknownText };
  }
  if (link.state === "available" && link.one_way_seconds !== null) {
    return { kind: "shown", seconds: link.one_way_seconds, source: link.source, stale: false, text: link.text };
  }
  const state = link.state === "available" ? "missing" : link.state;
  return { kind: "absent", mark: commsMark(state), word: ABSENT_WORD[state], text: link.text };
}

/** Un nodo con el que la tripulación se comunica: solo los que existen en EMMA. */
export interface CommsNode {
  key: string;
  name: string;
  where: string;
  /** El retardo con ese nodo: el de Tierra, «a bordo» para la tripulación (sin cifra inventada). */
  delay: LinkFigure | { kind: "onboard" };
  /** El estado del enlace con ese nodo, si lo hay. */
  link: { mark: StateMark | null; word: string; title: string } | null;
}

/**
 * Los nodos: los otros tripulantes con lecturas (del mismo vehículo: a bordo, sin distancia, porque
 * EMMA no mide entre personas) y la consola de Tierra, con el retardo del perfil y el enlace simulado.
 * Sin red de relés declarada, no se añade ninguno.
 */
export function commsNodes(
  subject: string,
  crew: CrewOverview["crew"] | null,
  figure: LinkFigure,
  sync: LinkSync | null,
): CommsNode[] {
  const mates: CommsNode[] = (crew ?? [])
    .filter((member) => member.subject !== subject)
    .map((member) => ({
      key: `crew-${member.subject}`,
      name: member.subject,
      where: member.location?.display ?? member.location_missing_text ?? tr("módulo sin declarar", "module not declared"),
      delay: { kind: "onboard" },
      link: null,
    }));
  const ground: CommsNode = {
    key: "ground",
    name: tr("Consola de Tierra", "Earth console"),
    where: tr("Tierra", "Earth"),
    delay: figure,
    link:
      sync === null
        ? null
        : {
            mark: sync.state === "down" ? LINK_DOWN_MARK : null,
            word: tr(`enlace ${sync.state_display}`, `link ${sync.state_display}`),
            title: sync.label,
          },
  };
  return [...mates, ground];
}

/** Si la tripulación está en el cuerpo de esa fila según el perfil. */
export function isCrewPlace(distances: Fetched<Distances>, body: string): boolean {
  return distances.state === "ready" && distances.value.crew_place?.body === body;
}

/** El modo de trabajo: sin red es el nominal de misión (`EMMA_OFFLINE`), no un modo degradado. */
export function workMode(sharing: Fetched<Sharing>): { word: string; text: string | null; mark: StateMark | null } {
  if (sharing.state === "loading") return { word: tr("Cargando…", "Loading…"), text: null, mark: LOADING_MARK };
  if (sharing.state === "failed") {
    return { word: tr("Sin datos", "No data"), text: sharing.outcome.text, mark: sharing.outcome.mark };
  }
  const { offline, offline_text } = sharing.value.internet;
  return {
    word: offline ? tr("Autónomo, sin red (modo de misión)", "Autonomous, offline (mission mode)") : tr("Con red", "Online"),
    text: offline_text,
    mark: null,
  };
}

function fetched<T>(promise: Promise<T>, alive: () => boolean, set: (next: Fetched<T>) => void): void {
  promise
    .then((value) => {
      if (alive()) set({ state: "ready", value });
    })
    .catch((reason: unknown) => {
      if (alive()) set({ state: "failed", outcome: requestOutcome(reason) });
    });
}

function Figure({ figure }: { figure: LinkFigure }) {
  if (figure.kind === "absent") {
    return (
      <MarkOf mark={figure.mark} title={figure.text ?? undefined}>
        {figure.word}
      </MarkOf>
    );
  }
  const shown = <span className="num">{formatLightTime(figure.seconds)}</span>;
  return figure.stale ? (
    <MarkOf mark={MISSING_MARK} title={figure.text ?? undefined}>
      {shown}
    </MarkOf>
  ) : (
    <span title={figure.text ?? undefined}>{shown}</span>
  );
}

function BodyRow({ row, here }: { row: BodyDistance; here: boolean }) {
  return (
    <li className="dist-row" data-here={here ? "true" : "false"}>
      <PlanetThumb id={THUMB[row.id] ?? row.id} />
      <span className="dist-name" title={row.note}>
        {row.label}
        {here && <small className="secondary"> {tr("(tripulación)", "(crew)")}</small>}
      </span>
      {row.state === "available" && row.distance_km !== null && row.one_way_seconds !== null ? (
        <>
          <span className="num dist-km" title={row.source ?? undefined}>
            {formatKm(row.distance_km)}
          </span>
          <span className="num dist-lt">{formatLightTime(row.one_way_seconds)}</span>
        </>
      ) : (
        <span className="dist-missing">
          <MarkOf mark={MISSING_MARK} title={row.text ?? undefined}>
            {tr("sin dato", "no data")}
          </MarkOf>
        </span>
      )}
    </li>
  );
}

/** La fila de la Tierra: dónde está la tripulación respecto de ella y el retardo del perfil. */
function EarthRow({
  profileId,
  distances,
  orbit,
  figure,
}: {
  profileId: string | null;
  distances: Fetched<Distances>;
  orbit: Fetched<IssOrbit> | null;
  figure: LinkFigure;
}) {
  const here = isCrewPlace(distances, "earth");
  let distance;
  if (profileId === "leo" && orbit !== null) {
    if (orbit.state === "loading") distance = <MarkOf mark={LOADING_MARK}>…</MarkOf>;
    else if (orbit.state === "failed") {
      distance = (
        <MarkOf mark={orbit.outcome.mark} title={orbit.outcome.text}>
          {tr("sin dato", "no data")}
        </MarkOf>
      );
    }
    else if (orbit.value.available && orbit.value.position !== undefined) {
      distance = (
        <span
          className="num"
          title={`${orbit.value.kind ?? ""} · ${orbit.value.age ?? ""} · ${tr("al centro de la Tierra", "to Earth's center")}`}
        >
          {formatKm(orbit.value.position.radial_km)}
        </span>
      );
    } else {
      distance = (
        <MarkOf mark={orbit.value.applies ? MISSING_MARK : UNAVAILABLE_MARK} title={orbit.value.reason}>
          {orbit.value.applies ? tr("sin dato", "no data") : tr("no aplica", "not applicable")}
        </MarkOf>
      );
    }
  } else {
    const place = distances.state === "ready" ? distances.value.crew_place : null;
    distance = (
      <span className="secondary dist-place" title={place?.text}>
        {place?.text ?? ""}
      </span>
    );
  }
  return (
    <li className="dist-row" data-here={here ? "true" : "false"}>
      <PlanetThumb id="earth" />
      <span className="dist-name">
        {tr("Tierra", "Earth")}
        {here && <small className="secondary"> {tr("(tripulación)", "(crew)")}</small>}
      </span>
      <span className="dist-km">{distance}</span>
      <span className="dist-lt">
        <Figure figure={figure} />
      </span>
    </li>
  );
}

function NodeDelay({ delay }: { delay: CommsNode["delay"] }) {
  if (delay.kind === "onboard") return <span className="secondary">{tr("a bordo", "on board")}</span>;
  return <Figure figure={delay} />;
}

/**
 * Lo que la consola de a bordo presta al mando del enlace: quién está en ella (el mismo campo que el
 * de «Alertas activas», `useOperator`), si la privacidad lo oculta y qué releer tras firmar.
 */
export interface LinkControl {
  operator: string;
  setOperator: (value: string) => void;
  privacy: boolean;
  /** Tras firmar: relee el estado, y con él el enlace y el corte de Tierra. */
  onDeclared: () => Promise<void>;
}

/**
 * Firma el cambio contrario al vigente (`POST /api/link-sync`, un asiento del registro con el nombre
 * de quien lo declara) desde `hoursAgo` horas antes de la última lectura de a bordo, y relee. Es la
 * misma petición que la del panel apartado (`components/LinkSync.tsx`), sin nota.
 */
export async function declareLink(
  sync: Pick<LinkSync, "state">,
  referenceTime: string | null,
  hoursAgo: number,
  operator: string,
  onDeclared: () => Promise<void>,
  now: Date = new Date(),
): Promise<void> {
  await api.setLinkSync(linkChange(sync, linkInstant(referenceTime, hoursAgo, now), operator, ""));
  await onDeclared();
}

/**
 * El mando compacto del enlace en «Sincronización y datos» (lote «botones», 2026-11-15): quién,
 * desde cuándo y el botón de declararlo caído o restablecido. El enlace es simulado y lo declara una
 * persona; no mueve el riesgo ni las alertas (`api/link_sync.py`). La frase de un fallo (un 409 si
 * el cambio va hacia atrás o repite el estado) es la del backend.
 */
function LinkDeclare({
  sync,
  referenceTime,
  control,
}: {
  sync: LinkSync;
  referenceTime: string | null;
  control: LinkControl;
}) {
  const [hoursAgo, setHoursAgo] = useState<number>(0);
  const [error, setError] = useState<RequestOutcome | null>(null);
  // Mientras va un cambio no se pide otro: un doble clic cruzaba dos peticiones (como el panel).
  const [sending, setSending] = useState(false);
  const down = sync.state === "down";
  const unnamed = control.operator.trim() === "";

  const declare = async () => {
    setError(null);
    setSending(true);
    try {
      await declareLink(sync, referenceTime, hoursAgo, control.operator, control.onDeclared);
      setHoursAgo(0);
    } catch (failure) {
      setError(requestOutcome(failure));
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="dist-link-declare">
      <FieldLabel concept="person">
        {tr("Quién", "Who")}{" "}
        <OperatorInput value={control.operator} onChange={control.setOperator} privacy={control.privacy} />
      </FieldLabel>
      <FieldLabel concept="time">
        {tr("Desde", "Since")}{" "}
        <select value={hoursAgo} onChange={(event) => setHoursAgo(Number(event.target.value))}>
          {LINK_OFFSETS_HOURS.map((hours) => (
            <option key={hours} value={hours}>
              {hours === 0
                ? tr("la última lectura", "the last reading")
                : tr(`${formatNumber(hours, 0)} h antes`, `${formatNumber(hours, 0)} h before`)}
            </option>
          ))}
        </select>
      </FieldLabel>
      <Command
        concept="declare"
        type="button"
        disabled={sending || unnamed}
        title={
          unnamed
            ? tr("Escribe quién lo declara: queda firmado en el registro.", "Enter who declares it: it is signed in the record.")
            : tr(
                "Enlace simulado: se firma en el registro con tu nombre. No cambia el riesgo ni las alertas.",
                "Simulated link: signed in the record with your name. It does not change the risk or the alerts.",
              )
        }
        onClick={() => void declare()}
      >
        {down ? tr("Declarar restablecido", "Declare restored") : tr("Declarar caído", "Declare down")}
      </Command>
      {error !== null && (
        <p>
          <MarkOf mark={error.mark}>{error.text}</MarkOf>
        </p>
      )}
    </div>
  );
}

/**
 * Las dos tarjetas: «Distancia y comunicaciones» (cuerpos, retardo, nodos) y «Sincronización y datos».
 * `sync` es el enlace simulado que la consola ya pide para el corte de Tierra (`null`: no llegó).
 */
export function HomeDistance({
  profileId,
  status,
  sync,
  active = true,
  linkControl,
}: {
  profileId: string | null;
  status: CrewStatus;
  sync: LinkSync | null;
  /** Oculto (otra sección abierta), no se pide nada; al volver, se relee. */
  active?: boolean;
  /** El mando para declarar el enlace; sin él, solo se enseña el estado. */
  linkControl?: LinkControl;
}) {
  const [distances, setDistances] = useState<Fetched<Distances>>({ state: "loading" });
  const [orbit, setOrbit] = useState<Fetched<IssOrbit> | null>(null);
  const [crew, setCrew] = useState<Fetched<CrewOverview>>({ state: "loading" });
  const [sharing, setSharing] = useState<Fetched<Sharing>>({ state: "loading" });
  const epoch = epochOf(status.data.reference_time);

  useEffect(() => {
    if (!active || profileId === null) return undefined;
    let current = true;
    const alive = () => current;
    setDistances({ state: "loading" });
    fetched(distanceApi.get(profileId, epoch), alive, setDistances);
    if (profileId === "leo") {
      setOrbit({ state: "loading" });
      fetched(distanceApi.iss(), alive, setOrbit);
    } else {
      setOrbit(null);
    }
    return () => {
      current = false;
    };
  }, [profileId, epoch, active]);

  useEffect(() => {
    if (!active) return undefined;
    let current = true;
    const alive = () => current;
    fetched(api.crew(), alive, setCrew);
    fetched(sharingApi.get(), alive, setSharing);
    return () => {
      current = false;
    };
  }, [active, status.subject]);

  const figure =
    profileId === null
      ? ({ kind: "absent", mark: UNAVAILABLE_MARK, word: tr("Sin perfil", "No profile"), text: null } as const)
      : linkFigure(profileId, status, distances);
  const short = profileId === null ? null : (PROFILE_SHORT[profileId] ?? profileId);
  const nodes = commsNodes(status.subject, crew.state === "ready" ? crew.value.crew : null, figure, sync);
  const mode = workMode(sharing);
  const pending = sync === null ? null : backlogMark(sync.to_send.count);

  return (
    <>
      <section
        data-ui="home-distance"
        className="ref-frame dist-comms"
        aria-label={tr("Distancia y comunicaciones", "Distance and communications")}
      >
        <PanelTitle concept="lightTime" className="ref-h ref-frame-h">
          {tr("Distancia y comunicaciones", "Distance and communications")}
          {short !== null && <span className="secondary"> ({short})</span>}
        </PanelTitle>
        <div className="dist-grid">
          <div className="ref-card dist-bodies">
            {profileId === null ? (
              <p className="secondary">
                <MarkOf mark={UNAVAILABLE_MARK}>
                  {tr(
                    "Sin perfil de misión declarado ni ubicación elegida.",
                    "No mission profile declared and no location chosen.",
                  )}
                </MarkOf>
              </p>
            ) : (
              <ul aria-label={tr("Distancias desde la Tierra", "Distances from Earth")}>
                <EarthRow profileId={profileId} distances={distances} orbit={orbit} figure={figure} />
                {distances.state === "loading" && (
                  <li>
                    <Loading />
                  </li>
                )}
                {distances.state === "failed" && (
                  <li>
                    <Unavailable outcome={distances.outcome} />
                  </li>
                )}
                {distances.state === "ready" &&
                  distances.value.bodies.map((row) => (
                    <BodyRow key={row.id} row={row} here={isCrewPlace(distances, row.id)} />
                  ))}
              </ul>
            )}
            {distances.state === "ready" && (
              <p className="secondary dist-foot ref-clamp" title={`${distances.value.observer}. ${distances.value.scope}`}>
                {tr("Luna y Marte", "Moon and Mars")} {distances.value.observer}
                {distances.value.spice.source !== null && ` · ${distances.value.spice.source}`}
              </p>
            )}
          </div>

          <div className="ref-card dist-delay" data-acc="distance">
            <h3 className="ref-h3">{tr("Retardo de comunicación", "Communication delay")}</h3>
            <p className="dist-big">
              <Figure figure={figure} />
            </p>
            <p className="secondary">
              {figure.kind === "shown"
                ? `${tr("de ida, con Tierra", "one way, to Earth")}${figure.source !== null ? ` · ${figure.source}` : ""}`
                : tr("con Tierra", "to Earth")}
            </p>
          </div>

          <div className="ref-card dist-nodes">
            <h3 className="ref-h3">{tr("Nodos de comunicación", "Communication nodes")}</h3>
            {crew.state === "failed" && <Unavailable outcome={crew.outcome} />}
            <ul aria-label={tr("Nodos", "Nodes")}>
              {nodes.map((node) => (
                <li key={node.key} className="dist-node">
                  <span className="ref-ellipsis" title={node.name}>
                    {node.name}
                  </span>
                  <span className="ref-ellipsis secondary" title={node.where}>
                    {node.where}
                  </span>
                  <span className="dist-node-delay">
                    <NodeDelay delay={node.delay} />
                  </span>
                  {node.link !== null && (
                    <span className="dist-node-link" title={node.link.title}>
                      {node.link.mark === null ? (
                        <Mark pictogram={uiPictogram("lightTime")}>{node.link.word}</Mark>
                      ) : (
                        <MarkOf mark={node.link.mark}>{node.link.word}</MarkOf>
                      )}
                    </span>
                  )}
                </li>
              ))}
              {crew.state === "loading" && (
                <li>
                  <Loading />
                </li>
              )}
              <li className="dist-node dist-relays">
                <MarkOf mark={UNAVAILABLE_MARK}>
                  {tr("Relés: sin nodos declarados en EMMA", "Relays: no nodes declared in EMMA")}
                </MarkOf>
              </li>
            </ul>
          </div>
        </div>
      </section>

      <section
        data-ui="home-sync"
        className="ref-frame dist-sync"
        aria-label={tr("Sincronización y datos", "Synchronization and data")}
      >
        <PanelTitle concept="received" className="ref-h ref-frame-h">
          {tr("Sincronización y datos", "Synchronization and data")}
        </PanelTitle>
        <div className="dist-sync-grid">
          <div className="ref-card">
            <dl className="dist-kv">
              <FieldLabel as="dt" concept="state">
                {tr("Modo de trabajo", "Working mode")}
              </FieldLabel>
              <dd title={mode.text ?? undefined}>
                {mode.mark === null ? mode.word : <MarkOf mark={mode.mark}>{mode.word}</MarkOf>}
              </dd>
              <FieldLabel as="dt" concept="lightTime">
                {tr("Enlace con Tierra", "Link to Earth")}
              </FieldLabel>
              <dd title={sync?.label}>
                {sync === null ? (
                  <MarkOf mark={UNAVAILABLE_MARK}>{tr("no recibido", "not received")}</MarkOf>
                ) : sync.state === "down" ? (
                  <MarkOf mark={LINK_DOWN_MARK}>{sync.state_display}</MarkOf>
                ) : (
                  <>
                    {sync.state_display} <small className="secondary">{tr("(simulado, declarado)", "(simulated, declared)")}</small>
                  </>
                )}
                {sync !== null && linkControl !== undefined && (
                  <LinkDeclare sync={sync} referenceTime={status.data.reference_time} control={linkControl} />
                )}
              </dd>
              <FieldLabel as="dt" concept="waiting">
                {tr("Pendiente de enviar", "Waiting to send")}
              </FieldLabel>
              <dd>
                {sync === null ? (
                  <MarkOf mark={UNAVAILABLE_MARK}>{tr("no recibido", "not received")}</MarkOf>
                ) : pending === null ? (
                  <span className="num">
                    {formatNumber(sync.to_send.count)} {tr("asientos", sync.to_send.count === 1 ? "entry" : "entries")}
                  </span>
                ) : (
                  <MarkOf mark={pending} title={sync.crew_sentence}>
                    {formatNumber(sync.to_send.count)} {tr("asientos", sync.to_send.count === 1 ? "entry" : "entries")}
                  </MarkOf>
                )}
              </dd>
              <FieldLabel as="dt" concept="received">
                {tr("Tierra tiene hasta", "Earth has up to")}
              </FieldLabel>
              <dd title={sync?.ground_sentence}>
                {sync === null ? (
                  <MarkOf mark={UNAVAILABLE_MARK}>{tr("no recibido", "not received")}</MarkOf>
                ) : sync.cut === null ? (
                  tr("todo lo de a bordo", "everything on board")
                ) : sync.held ? (
                  <MarkOf mark={MISSING_MARK}>{formatUtc(new Date(sync.cut))}</MarkOf>
                ) : (
                  <span className="num">{formatUtc(new Date(sync.cut))}</span>
                )}
              </dd>
            </dl>
            {sync !== null && (
              <p className="secondary ref-clamp dist-sync-note" title={sync.not_measured}>
                {sync.not_measured}
              </p>
            )}
          </div>

          <div className="ref-card">
            <dl className="dist-kv">
              <FieldLabel as="dt" concept="signedLedger">
                {tr("Registro firmado", "Signed ledger")}
              </FieldLabel>
              <dd>
                {status.data.integrity_ok ? (
                  <MarkOf mark={OK_MARK}>{tr("Íntegro", "Intact")}</MarkOf>
                ) : (
                  <Mark pictogram="cross" color="red">
                    {tr("Integridad comprometida", "Integrity compromised")}
                  </Mark>
                )}
              </dd>
              <FieldLabel as="dt" concept="measured">
                {tr("Lecturas analizadas", "Readings analyzed")}
              </FieldLabel>
              <dd className="num">{formatNumber(status.data.observations)}</dd>
              <FieldLabel as="dt" concept="time">
                {tr("Última lectura", "Last reading")}
              </FieldLabel>
              <dd className="num">{formatUtc(new Date(status.data.reference_time))}</dd>
              <FieldLabel as="dt" concept="resources">
                {tr("Almacenamiento local", "Local storage")}
              </FieldLabel>
              <dd>
                <MarkOf mark={UNAVAILABLE_MARK}>{tr("el backend no lo expone", "not exposed by the backend")}</MarkOf>
              </dd>
            </dl>
          </div>
        </div>
      </section>
    </>
  );
}
