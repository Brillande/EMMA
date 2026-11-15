import { type CSSProperties, type ReactNode, useLayoutEffect, useRef, useState } from "react";

import { Chosen } from "../components/Chosen";
import { DomainName } from "../components/DomainName";
import { Mark, MarkOf } from "../components/Mark";
import { Loading } from "../components/Unavailable";
import {
  SILHOUETTE_HEIGHT,
  type SiteAnchor,
  Silhouette,
  type SitedRegion,
  isSitedRegion,
  reachBetween,
  siteAnchor,
} from "../icons/Silhouette";
import type { AnatomyRegionState } from "../lib/api";
import { tr } from "../lib/i18n";
import { NO_STATE, regionPictogram, stateStyle } from "./chain";
import { RegionLevel } from "./RegionChain";
import { placeSites } from "./siteLayout";
import type { AnatomyView } from "./useAnatomyState";

/**
 * La silueta del resumen: cada dominio sobre su región del cuerpo, con su nivel en palabra y forma.
 *
 * Decisión del usuario (2026-10-20): una silueta 2D en el resumen de la consola de tripulación,
 * junto a la rejilla de dominios, no en su lugar. Es un cliente del mismo estado que el modo
 * anatómico (`/api/anatomy/state`, especificación §4 y §10): no calcula ningún nivel, pinta el
 * que llega con la misma insignia que el resto de la consola (`StateBadge`: la palabra del
 * backend, el pictograma del nivel y su color de la tabla F.5-1; «sin datos» en cian, nunca
 * nominal). El dibujo (`icons/Silhouette.tsx`) dice dónde está cada región; las palabras las da
 * el backend (`display` de la región, nombre del dominio, palabra del nivel). La interfaz no
 * redacta nada aquí.
 *
 * Las regiones sin órgano propio (el sistema inmune y «todo el cuerpo», para la radiación) no
 * tienen sitio en la figura: van en una franja al pie, con los mismos rótulos. Una región del
 * backend que esta figura no conozca va también al pie, no se pierde; la prueba compara la lista
 * con `anatomy.py` para que eso no pase sin verse.
 *
 * Pulsar una región la elige en el modo anatómico (la cadena entera está allí); la elección es
 * de la consola, que la reparte a los dos, igual que la respuesta y su aviso de «anterior al
 * estado de la consola» (`useAnatomyState`): lo que diga esta figura lo dice también el panel
 * «Cuerpo». Accesible: cada región es un botón cuyo nombre es el `display` del backend y cuya
 * descripción es lo que se ve en él (dominio y nivel), con `aria-pressed` para la elegida, que
 * además lleva el pictograma de «elegido» (`ring-dot`): la elección no se marca solo con color
 * (F.5.10 e).
 *
 * No es una imagen del tripulante ni un diagnóstico: es un esquema de dónde cae cada dominio. La
 * consola de Tierra no la monta: allí mandan la densidad y el retardo.
 *
 * Una región sin nivel propio (el hígado, decimoquinta ronda) no lleva insignia de nivel ni su zona
 * color de nivel: su rótulo es su nombre con el dibujo de su órgano y, debajo, la frase del backend
 * que dice de qué dominio es el nivel («El nivel es del dominio nutrición.»), con el dibujo de ese
 * dominio y sin color.
 *
 * Los rótulos van a la altura de su zona, pero colocados por su alto medido (`siteLayout.ts`):
 * con el texto agrandado se apartan lo justo para no montarse y, si para eso tendrían que alejarse
 * de su zona, pasan todos a la lista de debajo de la figura (§5.35.11).
 */

/** Regiones del backend sin sitio en la figura: van al pie. La prueba exige que, con las de la figura, sean todas. */
export const UNSITED_REGIONS = ["immune", "whole-body"] as const;

export function BodySilhouette({
  view,
  selected,
  onSelect,
  backdrop,
}: {
  view: AnatomyView;
  selected: string | null;
  onSelect: (region: string | null) => void;
  /**
   * Lo que va detrás del contorno, dentro de la figura (adorno): «Cuerpo» pone ahí el cuerpo de la
   * maqueta bajo la concha nueva, alineado con la silueta por el mismo alto (`shell/body.css`).
   */
  backdrop?: ReactNode;
}) {
  const { state, error, stale } = view;
  return (
    <div className="body-silhouette" role="group" aria-label={tr("Regiones del cuerpo", "Body regions")}>
      {error !== null && (
        <p>
          <MarkOf mark={error.mark}>{tr("No se pudo obtener el estado por regiones:", "Could not get the state by region:")} {error.text}</MarkOf>
        </p>
      )}
      {state === null && error === null && (
        <Loading />
      )}
      {stale && (
        <p>
          <Mark pictogram={NO_STATE.pictogram} color={NO_STATE.color}>
            {tr("El estado por regiones es anterior al que muestra la consola; se está actualizando.", "The state by region is older than the one the console shows; it is updating.")}
          </Mark>
        </p>
      )}
      {state !== null && <Figure regions={state.regions} selected={selected} onSelect={onSelect} backdrop={backdrop} />}
    </div>
  );
}

function Figure({
  regions,
  selected,
  onSelect,
  backdrop,
}: {
  regions: readonly AnatomyRegionState[];
  selected: string | null;
  onSelect: (region: string | null) => void;
  backdrop?: ReactNode;
}) {
  const sited = new Map<SitedRegion, AnatomyRegionState>();
  const footed: AnatomyRegionState[] = [];
  for (const region of regions) {
    if (isSitedRegion(region.key)) sited.set(region.key, region);
    else footed.push(region);
  }
  // Sin nivel propio, la zona no lleva color de nivel: hereda el del contorno.
  const zoneClassName = (key: SitedRegion) => {
    const region = sited.get(key);
    return region === undefined || region.level_of !== null ? undefined : `c-${stateStyle(region.level).color}`;
  };
  // Lo que se lee en cada rótulo: si cambia (otro nivel, otra frase), cambia su alto.
  const content = [...sited.values()].map((item) => `${item.key}:${item.level ?? ""}:${item.level_note ?? ""}`).join("|");
  const { figure, layout } = useSiteLayout([...sited.keys()], content);
  const listed = layout?.listed ?? false;
  const anchorOf = (key: SitedRegion): SiteAnchor => layout?.anchors[key] ?? siteAnchor(key);
  return (
    <>
      <div className="body-silhouette-figure" ref={figure}>
        {backdrop}
        {/* La zona también se pulsa: en «Inicio» y «Radiación» los rótulos no se ven (solo con el
            teclado) y era lo único a mano. Solo las regiones que llegaron del backend. */}
        <Silhouette
          zoneClassName={zoneClassName}
          selected={selected}
          onZone={(key) => {
            if (sited.has(key)) onSelect(selected === key ? null : key);
          }}
        />
        {!listed &&
          [...sited].map(([key, region]) => (
            <Site key={key} region={region} anchor={anchorOf(key)} selected={selected} onSelect={onSelect} />
          ))}
      </div>
      {listed && (
        <ul className="body-silhouette-foot body-silhouette-list">
          {[...sited].map(([key, region]) => (
            <li key={key}>
              <Site region={region} anchor={null} selected={selected} onSelect={onSelect} />
            </li>
          ))}
        </ul>
      )}
      {footed.length > 0 && (
        <ul className="body-silhouette-foot">
          {footed.map((region) => (
            <li key={region.key}>
              <Site region={region} anchor={null} selected={selected} onSelect={onSelect} />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

interface SiteLayout {
  /** Para qué se calculó: alto de la figura, tamaño del texto, regiones y lo que dicen. */
  readonly key: string;
  /** Ancho de la figura con que se calculó (px). */
  readonly width: number;
  readonly listed: boolean;
  /** El ancla de cada rótulo colocado: su centro y el alcance del contorno en su franja real. */
  readonly anchors: Partial<Record<SitedRegion, SiteAnchor>>;
  /** Los altos medidos con que se calculó (unidades del lienzo). */
  readonly heights: Readonly<Record<string, number>>;
}

/**
 * Cuántas veces se recoloca para las mismas medidas antes de dejarlo: alto, ancho y alcance se
 * influyen (el alcance cambia el ancho del rótulo y el ancho su alto), y no debe quedarse oscilando.
 */
const MAX_PASSES = 6;

/**
 * Cuánto tiene que cambiar el ancho de la figura (px) para volver a probar los rótulos junto a ella
 * desde la lista: pasar a la lista alarga la página, puede sacar la barra de desplazamiento y
 * estrechar la figura unos 15 px; con eso solo no se vuelve, o alternaría sin parar.
 */
const WIDTH_SLACK = 40;

/**
 * Coloca los rótulos de la figura por su alto real (`siteLayout.ts`). Mide antes de pintar
 * (`useLayoutEffect`) y vuelve a medir cuando cambia el tamaño de la figura o de un rótulo (el
 * texto agrandado lo cambia). En la lista no hay altos que valgan (allí un rótulo ocupa menos
 * líneas): con las mismas medidas de figura y texto se queda en la lista, y si cambian se vuelve a
 * probar junto a la figura antes de pintar. Sin navegador (la prueba a HTML estático) no mide, y
 * cada rótulo va a la altura de su zona.
 */
function useSiteLayout(keys: readonly SitedRegion[], content: string) {
  const figure = useRef<HTMLDivElement | null>(null);
  const passes = useRef<{ key: string; count: number }>({ key: "", count: 0 });
  const [layout, setLayout] = useState<SiteLayout | null>(null);
  const [tick, setTick] = useState(0);
  const regionsKey = keys.join(",");

  useLayoutEffect(() => {
    const node = figure.current;
    const drawing = node?.querySelector("svg") ?? null;
    if (node === null || drawing === null) return;
    const pixels = drawing.getBoundingClientRect().height;
    if (pixels <= 0) return;
    const font = getComputedStyle(document.documentElement).fontSize;
    const width = node.getBoundingClientRect().width;
    const key = `${pixels}|${font}|${regionsKey}|${content}`;
    if (layout?.listed === true) {
      // En la lista se queda mientras nada cambie; si algo cambió, se prueba otra vez arriba.
      if (layout.key !== key || Math.abs(layout.width - width) > WIDTH_SLACK) setLayout(null);
      return;
    }
    // En pantalla estrecha el CSS ya pone los rótulos debajo, en el flujo: no hay que colocarlos.
    const sample = node.querySelector<HTMLElement>("button.site[data-region]");
    if (sample !== null && getComputedStyle(sample).position === "static") {
      if (layout !== null) setLayout(null);
      return;
    }
    const passKey = `${key}|${width}`;
    if (passes.current.key !== passKey) passes.current = { key: passKey, count: 0 };
    if (passes.current.count >= MAX_PASSES) return;
    const regions = regionsKey === "" ? [] : (regionsKey.split(",") as SitedRegion[]);
    const scale = SILHOUETTE_HEIGHT / pixels;
    const heights: Record<string, number> = {};
    for (const button of node.querySelectorAll<HTMLElement>("button.site[data-region]")) {
      const region = button.dataset.region;
      if (region !== undefined) heights[region] = button.offsetHeight * scale;
    }
    if (regions.some((region) => heights[region] === undefined)) return;
    const same =
      layout !== null &&
      layout.key === key &&
      layout.width === width &&
      regions.every((region) => Math.abs((layout.heights[region] ?? 0) - (heights[region] ?? 0)) < 1);
    if (same) return;
    passes.current.count += 1;
    const placed = placeSites(
      regions.map((region) => {
        const anchor = siteAnchor(region);
        return { key: region, side: anchor.side, anchor: anchor.y * SILHOUETTE_HEIGHT, height: heights[region] ?? 0 };
      }),
      SILHOUETTE_HEIGHT,
    );
    const anchors: Partial<Record<SitedRegion, SiteAnchor>> = {};
    if (!placed.listed) {
      for (const region of regions) {
        const centre = placed.centres[region] ?? siteAnchor(region).y * SILHOUETTE_HEIGHT;
        const half = (heights[region] ?? 0) / 2;
        anchors[region] = {
          y: Math.round((centre / SILHOUETTE_HEIGHT) * 10_000) / 10_000,
          side: siteAnchor(region).side,
          reach: reachBetween(centre - half, centre + half),
        };
      }
    }
    setLayout({ key, width, listed: placed.listed, anchors, heights });
  }, [layout, tick, regionsKey, content]);

  // El tamaño de la figura o de un rótulo cambia sin que cambie el estado (el texto del navegador,
  // el ancho de la ventana): se vuelve a medir en el cuadro siguiente, no dentro del aviso.
  useLayoutEffect(() => {
    const node = figure.current;
    if (node === null || typeof ResizeObserver === "undefined") return;
    let frame = 0;
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => setTick((value) => value + 1));
    });
    observer.observe(node);
    for (const button of (node.parentElement ?? node).querySelectorAll("button.site")) observer.observe(button);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [layout?.listed, regionsKey]);

  return { figure, layout };
}

/**
 * Dónde va el rótulo de una zona: a su altura (`top`) y, en `--reach`, hasta dónde llega la
 * figura a esa altura (unidades del lienzo); el CSS lo convierte a píxeles con el alto de la
 * figura y pone el rótulo justo pasado ese punto. Son los dos únicos estilos en línea.
 */
function anchorStyle(anchor: SiteAnchor): CSSProperties {
  return { top: `${anchor.y * 100}%`, ["--reach" as string]: anchor.reach };
}

/**
 * Una región: el pictograma de su dominio con su nombre, y el nivel con palabra y forma. Con
 * ancla, se coloca a la altura de su zona en el dibujo y por el lado que el dibujo dice; sin
 * ancla, va en el flujo del pie.
 */
function Site({
  region,
  anchor,
  selected,
  onSelect,
}: {
  region: AnatomyRegionState;
  anchor: ReturnType<typeof siteAnchor> | null;
  selected: string | null;
  onSelect: (region: string | null) => void;
}) {
  const pressed = region.key === selected;
  const described = `site-${region.key}-state`;
  const classes = ["site", `site-${region.key}`, anchor === null ? undefined : `site-${anchor.side}`]
    .filter((item) => item !== undefined)
    .join(" ");
  return (
    <button
      type="button"
      className={classes}
      style={anchor === null ? undefined : anchorStyle(anchor)}
      data-region={region.key}
      aria-label={region.display}
      aria-describedby={described}
      aria-pressed={pressed}
      title={region.display}
      onClick={() => onSelect(pressed ? null : region.key)}
    >
      <span id={described} className="site-state">
        {region.domains.map((domain) => (
          <Chosen key={domain} chosen={pressed}>
            <DomainName domain={domain} />
          </Chosen>
        ))}
        {/* Sin dominio: el nombre de la región con el dibujo de su órgano; debajo, la frase del
            backend con el dibujo del dominio de su nivel, sin color ni insignia de nivel. */}
        {region.domains.length === 0 && (
          <Chosen chosen={pressed}>
            <Mark pictogram={regionPictogram(region)}>{region.display}</Mark>
          </Chosen>
        )}
        <RegionLevel region={region} />
      </span>
    </button>
  );
}
