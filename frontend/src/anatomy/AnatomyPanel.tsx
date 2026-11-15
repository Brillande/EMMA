import { useEffect, useState } from "react";

import { BoardOnly } from "../components/BoardOnly";
import { Chosen } from "../components/Chosen";
import { FieldLabel } from "../components/FieldLabel";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { Loading } from "../components/Unavailable";
import { RECOMPUTED_PICTOGRAM } from "../dashboard/alertHistory";
import { Segments, levelToken } from "../dashboard/HomeCharts";
import { Pictogram } from "../icons";
import { type AnatomyRegionState, type AnatomyState, type CrewStatus, type MissionMilestones, api } from "../lib/api";
import { formatNumber } from "../lib/format";
import { type RequestOutcome, requestOutcome } from "../lib/marks";
import { NO_STATE, regionPictogram, stateStyle } from "./chain";
import { RegionChain, RegionLevel } from "./RegionChain";
import type { AnatomyView } from "./useAnatomyState";

/** El panel, para que la crónica lo traiga a la vista al elegir un momento desde un hito suyo. */
export const ANATOMY_PANEL_ID = "anatomy-panel";

/**
 * Modo anatomico (especificacion del equipo §10): CUERPO → ORGANO → estado → variables →
 * evidencia → tendencia → contramedida.
 *
 * Es un cliente del estado, no una fuente propia (§4): la cadena entera de cada region llega de
 * `/api/anatomy/state`, que el backend compone con el mismo analisis que `/status`. Este panel
 * calculaba antes el nivel de cada region (el peor de sus dominios, "nominal" si faltaba): la
 * interfaz decidia, y una region sin una sola lectura salia nominal. Ya no calcula nada: ensena
 * el nivel que llega y, donde no hay, dice "sin datos". La especificacion deja el render 3D como
 * opcional; aqui se recorre como lista navegable, accesible por teclado y lector de pantalla. El
 * mapa de dolor en 3D sigue aparte y con su regla propia (una zona de dolor nunca es roja ni
 * amarilla).
 *
 * La respuesta y la region elegida las tiene la consola (`useAnatomyState`), porque la silueta
 * del resumen ensena el mismo estado y pulsar una region alli la abre aqui: un solo estado por
 * regiones y una sola eleccion, para que las dos vistas no discrepen nunca.
 *
 * EL MOMENTO (conversacion de ideacion: «Pre-flight → Day 30 → … → Recovery»). El selector ofrece
 * los momentos que da el backend (`moments`: cambios de fase, regreso y dias L- y R+) y, al elegir uno,
 * la cadena se pide con `until`. Ese estado es un recalculo hecho hoy, sin asiento: lleva el
 * rotulo y los limites que redacta el backend (`moment`), los niveles van sin la insignia de un
 * nivel vigente y no se ofrece adoptar nada. Solo este panel cambia de momento: la silueta del
 * resumen sigue en el estado de ahora.
 *
 * Decimoquinta ronda (§5.35.8): el momento elegido lo tiene la consola (`momentKey`), porque la
 * crónica de la línea temporal también lo elige —pulsar un hito suyo abre aquí ese momento—; los
 * días posvuelo llegan agrupados en hitos R+ con su base al lado (`postflight_milestones`), y en
 * un momento pasado las tarjetas de recomendación llevan su forma sin su color (`past`).
 *
 * Decimosexta ronda (§5.36.13): los días prevuelo llegan igual, en hitos L- con su base al lado
 * (`preflight_milestones`); la base de cada lado dice de qué fuente sale cada hito y qué cubre.
 *
 * Tablero (2026-11-07): en la concha de la maqueta, encima de la lista de regiones va la tira de
 * segmentos (`RegionStrip`), uno por región en el color real de su nivel, con el recuento de regiones
 * con datos; solo con el estado de ahora, porque en un momento recalculado la consola quita el color a
 * los niveles.
 */
export function AnatomyPanel({
  status,
  view,
  selected,
  onSelect,
  momentKey,
  onMoment,
  operator,
  following,
  onAdopt,
}: {
  status: CrewStatus;
  view: AnatomyView;
  selected: string | null;
  onSelect: (region: string | null) => void;
  /** El momento elegido (clave de `moments.items`); `null`, el de ahora. */
  momentKey: string | null;
  onMoment: (key: string | null) => void;
  operator: string;
  /** Contramedidas con seguimiento abierto. */
  following: ReadonlySet<string>;
  onAdopt: (countermeasureId: string, by: string) => Promise<void>;
}) {
  const { state, error, stale } = view;
  // Los momentos los da el estado de ahora; si el elegido deja de estar (otro tripulante, datos
  // nuevos, el día de un tramo abierto que avanza), se vuelve a ahora en vez de pedir un instante
  // que ya no se ofrece, y se olvida: si no, volvería a abrirse solo cuando reapareciera.
  const moments = state?.moments ?? null;
  const chosen = moments?.items.find((item) => item.key === momentKey) ?? null;
  // La base de los hitos del lado del elegido; ninguna junto a un cambio de fase o al regreso.
  const chosenMilestones =
    chosen?.kind === "postflight_milestone" ? moments?.postflight_milestones
    : chosen?.kind === "preflight_milestone" ? moments?.preflight_milestones
    : undefined;
  const offered = moments !== null && !stale;
  useEffect(() => {
    if (offered && momentKey !== null && chosen === null) onMoment(null);
  }, [offered, momentKey, chosen, onMoment]);
  const past = usePastState(status.subject, chosen?.until ?? null);
  const shown = chosen === null ? state : past.state;
  const current = shown?.regions.find((region) => region.key === selected) ?? null;

  return (
    <section data-ui="anatomy" className="panel" aria-label="Modo anatómico" id={ANATOMY_PANEL_ID}>
      <PanelTitle concept="body">Cuerpo</PanelTitle>
      {error !== null && (
        <p>
          <MarkOf mark={error.mark}>No se pudo obtener el estado por regiones: {error.text}</MarkOf>
        </p>
      )}
      {state === null && error === null && (
        <Loading />
      )}
      {state !== null && (
        <>
          {/* F.4.3.1 c: si lo que se ve es de otro instante o de otro tripulante que el estado
              de la consola (mientras llega la respuesta nueva, o si no llega), se dice. */}
          {stale && (
            <p>
              <Mark pictogram={NO_STATE.pictogram} color={NO_STATE.color}>
                El estado por regiones es anterior al que muestra la consola; se está actualizando.
              </Mark>
            </p>
          )}
          {moments !== null && moments.items.length > 0 && (
            <div className="summary" role="group" aria-label="Momento de la misión">
              <FieldLabel as="span" concept="history">
                Momento
              </FieldLabel>
              <button
                className="command"
                aria-pressed={chosen === null}
                onClick={() => onMoment(null)}
              >
                <Chosen chosen={chosen === null}>{moments.current_display}</Chosen>
              </button>
              {moments.items.map((item) => (
                <button
                  key={item.key}
                  className="command"
                  aria-pressed={chosen?.key === item.key}
                  onClick={() => onMoment(item.key)}
                >
                  <Chosen chosen={chosen?.key === item.key}>{item.display}</Chosen>
                </button>
              ))}
            </div>
          )}
          {moments !== null && chosen !== null && (
            <>
              <p className="secondary">{moments.basis}</p>
              {/* De dónde salen los hitos posvuelo y prevuelo: los leídos, con lo que cubre cada
                  fuente, y los de diseño, con las palabras del backend. Junto a un hito, no junto a
                  un cambio de fase. */}
              {chosenMilestones !== undefined && <MilestonesBasis milestones={chosenMilestones} />}
              {past.failed !== null && (
                <p>
                  <MarkOf mark={past.failed.mark}>
                    No se pudo recalcular el estado en ese momento: {past.failed.text}
                  </MarkOf>
                </p>
              )}
              {past.failed === null && past.state === null && <Loading />}
              {/* Lo que es este estado, con las palabras del backend: un recálculo de hoy, sin
                  asiento. Va arriba y a la vista, no en un plegable. */}
              {past.state !== null && past.state.moment !== null && (
                <div>
                  <p>
                    <Mark pictogram={RECOMPUTED_PICTOGRAM}>{past.state.moment.label}</Mark>
                    {" · "}
                    {chosen.display}
                  </p>
                  {past.state.moment.basis.map((line) => (
                    <p key={line} className="secondary">
                      {line}
                    </p>
                  ))}
                </div>
              )}
            </>
          )}
          {shown !== null && chosen === null && (
            <BoardOnly>
              <RegionStrip regions={shown.regions} />
            </BoardOnly>
          )}
          {shown !== null && (
            <div className="anatomy">
              {/* Una lista de botones que se pulsan y se sueltan (`aria-pressed`), como la silueta y
                  los momentos de arriba. Era un `listbox` con `option` dentro de `<li>`: el lector
                  de pantalla no encontraba las opciones bajo la lista (axe aria-required-children
                  y aria-required-parent, §5.41) y cada opción estaba además en el tabulador. */}
              <ul className="regions" aria-label="Regiones del cuerpo">
                {shown.regions.map((region) => {
                  const isChosen = region.key === selected;
                  return (
                    <li key={region.key}>
                      <button
                        type="button"
                        className="region"
                        aria-pressed={isChosen}
                        onClick={() => onSelect(isChosen ? null : region.key)}
                      >
                        {/* La eleccion no se marca solo con color (F.5.10 e): lleva su pictograma.
                            La palabra es el `display` de la region, con el dibujo de cada uno de
                            sus dominios delante, como en la silueta del resumen. */}
                        <Chosen chosen={isChosen}>
                          {/* El de su dominio o, sin dominio (el hígado), el de su órgano. */}
                          <Pictogram name={regionPictogram(region)} />
                          {region.display}
                        </Chosen>
                        {/* Sin nivel propio, la frase del backend en lugar de la insignia. */}
                        <RegionLevel region={region} recomputed={chosen !== null} />
                      </button>
                    </li>
                  );
                })}
              </ul>
              {current !== null && (
                <RegionChain
                  key={`${current.key}|${chosen?.key ?? ""}`}
                  region={current}
                  status={status}
                  operator={operator}
                  following={following}
                  onAdopt={onAdopt}
                  pastUntil={chosen === null ? null : (shown.moment?.until ?? chosen.until)}
                />
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}

/**
 * Un segmento por región, en el color real de su nivel (`levelToken`), junto a la lista que lo dice
 * con palabra e insignia: de un vistazo, cuántas regiones llevan alerta. Sin nivel («sin datos»), el
 * cian del dato ausente que ya lleva su insignia (F.5-1), no el gris; una región cuyo nivel es de un
 * dominio ajeno (el hígado) no tiene nivel propio y va en el color del contorno, como su zona en la
 * silueta. El recuento que acompaña es el `has_data` del backend: regiones con alguna lectura o
 * hallazgo. La tira es adorno (`aria-hidden`); lo que dice está en la lista de debajo.
 */
function RegionStrip({ regions }: { regions: readonly AnatomyRegionState[] }) {
  const tones = regions.map((region) =>
    region.level_of !== null ? "textSecondary" : region.level === null ? NO_STATE.color : levelToken(region.level),
  );
  const titles = regions.map(
    (region) => `${region.display}: ${region.level_of !== null ? (region.level_note ?? "") : stateStyle(region.level).label}`,
  );
  const withData = regions.filter((region) => region.has_data).length;
  return (
    <p className="board-row anatomy-strip">
      <Segments tones={tones} titles={titles} />
      <span className="secondary">
        <span className="num">{formatNumber(withData)}</span> de <span className="num">{formatNumber(regions.length)}</span>{" "}
        regiones con datos
      </span>
    </p>
  );
}

interface PastState {
  /** El estado del momento pedido; `null` mientras llega o si falló. */
  readonly state: AnatomyState | null;
  /** Rechazo del backend (4xx, amarillo) o petición caída (5xx o sin red, rojo). */
  readonly failed: RequestOutcome | null;
}

/**
 * La cadena en un momento pasado (`until`), pedida solo cuando hay uno elegido. Mientras llega la
 * de otro momento no se enseña la anterior: la respuesta se guarda con su clave y solo vale para
 * la misma.
 */
function usePastState(subject: string, until: string | null): PastState {
  const [held, setHeld] = useState<{
    key: string;
    state: AnatomyState | null;
    failed: PastState["failed"];
  } | null>(null);
  const key = `${subject}|${until ?? ""}`;

  useEffect(() => {
    if (until === null) return;
    let cancelled = false;
    api
      .anatomyState(subject, until)
      .then((body) => {
        if (!cancelled) setHeld({ key, state: body, failed: null });
      })
      .catch((reason: unknown) => {
        if (!cancelled) setHeld({ key, state: null, failed: requestOutcome(reason) });
      });
    return () => {
      cancelled = true;
    };
  }, [key, subject, until]);

  if (until === null || held === null || held.key !== key) return { state: null, failed: null };
  return { state: held.state, failed: held.failed };
}

/**
 * La base de los hitos de un lado y, debajo, cada fuente leída con lo que cubre (`scope`), con las
 * palabras del backend: que el calendario de un estudio o de una prueba no se lea como el de todos
 * los indicadores lo dice la ficha misma, no solo la frase de la base.
 */
export function MilestonesBasis({ milestones }: { milestones: MissionMilestones }) {
  const sources = milestones.sources ?? [];
  return (
    <>
      <p className="secondary">{milestones.basis}</p>
      {sources.length > 0 && (
        <ul className="secondary" aria-label="Fuentes de los hitos">
          {sources.map((item) => (
            <li key={item.source.id} data-milestone-source={item.source.id}>
              {item.source.url !== null ? (
                <a href={item.source.url} target="_blank" rel="noreferrer">
                  {item.source.title}
                </a>
              ) : (
                item.source.title
              )}
              {" — "}
              {item.scope}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
