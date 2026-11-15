import { type ReactNode, useEffect, useLayoutEffect, useRef, useState } from "react";

import { BodySilhouette } from "../anatomy/BodySilhouette";
import { NO_STATE, regionPictogram } from "../anatomy/chain";
import { RegionChain } from "../anatomy/RegionChain";
import type { AnatomyView } from "../anatomy/useAnatomyState";
import { Command } from "../components/Command";
import { Mark } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import type { AnatomyRegionState, CrewStatus } from "../lib/api";
import { tr } from "../lib/i18n";
import { useOperator } from "../lib/operator";
import "../shell/regionPopover.css";

/**
 * La silueta de «Inicio» y de «Radiación» con la ficha de la región que se pulsa, junto al cuerpo.
 *
 * Por qué existe (2026-11-15, «que si pulso el botón pasen cosas»): pulsar una región de la silueta
 * elegía la región de la consola, y esa elección solo la leía el modo anatómico (`AnatomyPanel`),
 * que está en una pestaña apartada de esta versión. Quien pulsaba veía, como mucho, el anillo de la
 * zona. Ahora el mismo clic abre aquí la cadena de esa región, con el componente de siempre
 * (`RegionChain`): todo lo que se lee lo calculó y lo redactó el backend (`/api/anatomy/state`, la
 * misma respuesta que pinta la silueta). La interfaz no redacta nada clínico aquí.
 *
 * La elección sigue siendo de la consola (`region`), pero la ficha abierta es de esta figura: solo
 * se abre por un clic en ella. Elegir una región en otra pestaña no abre fichas en las demás, y un
 * clic fuera de esta ficha no borra lo elegido en otro sitio.
 *
 * Una región sin lecturas ni hallazgos (`has_data` falso) no abre la cadena vacía: su nombre y la
 * frase del backend que lo dice, en gris (texto secundario), sin color de nivel ni de alarma. Si el
 * estado por regiones es anterior al de la consola se dice, como en la silueta; si es de otro
 * tripulante, no se abre (su cadena se leería con el estado de este).
 *
 * Es de solo lectura: adoptar una contramedida se hace en «Recomendaciones», donde la consola
 * vuelve a leer el estado al firmar; aquí la tarjeta de la contramedida va sin ese mando.
 *
 * Se cierra con Esc, con su botón o pulsando fuera; al cerrarla con el teclado o el botón, el foco
 * vuelve a donde estaba. Una pestaña visitada sigue montada pero oculta (`ConsoleTabs`): la ficha de
 * una pestaña oculta no atiende ni teclas ni clics.
 */
export function RegionFigure({
  view,
  region,
  setRegion,
  status,
}: {
  view: AnatomyView;
  /** La región elegida en la consola; `null`, ninguna. */
  region: string | null;
  setRegion: (region: string | null) => void;
  status: CrewStatus;
}) {
  const [open, setOpen] = useState<string | null>(null);
  // Si la elección cambia en otro sitio, esta ficha se olvida: no reaparece sola si vuelve.
  if (open !== null && open !== region) setOpen(null);
  const select = (key: string | null) => {
    setRegion(key);
    setOpen(key);
  };
  const close = () => {
    setOpen(null);
    // Se suelta la elección solo si sigue siendo la que abrió esta ficha.
    if (region === open) setRegion(null);
  };
  return (
    <>
      <BodySilhouette view={view} selected={region} onSelect={select} />
      <RegionPopover view={view} region={open === region ? open : null} status={status} onClose={close} />
    </>
  );
}

/** La ficha de una región elegida, si está en la respuesta; nada si no hay ninguna. */
export function RegionPopover({
  view,
  region,
  status,
  onClose,
}: {
  view: AnatomyView;
  region: string | null;
  status: CrewStatus;
  onClose: () => void;
}) {
  const { state, stale } = view;
  if (region === null || state === null || state.subject !== status.subject) return null;
  const found = state.regions.find((item) => item.key === region) ?? null;
  if (found === null) return null;
  const known = new Set(state.regions.map((item) => item.key));
  return <RegionCard key={found.key} region={found} status={status} stale={stale} known={known} onClose={onClose} />;
}

/** Hacia dónde se abre la ficha: a la derecha del cuerpo si cabe, si no a la izquierda, si no debajo. */
export type PopoverSide = "right" | "left" | "below";

/** Separación entre el cuerpo y la ficha, y margen con el borde de la ventana (px). */
const GAP = 8;

export function popoverSide(
  anchor: { readonly left: number; readonly right: number },
  width: number,
  viewport: number,
): PopoverSide {
  if (anchor.right + GAP + width <= viewport - GAP) return "right";
  if (anchor.left - GAP - width >= GAP) return "left";
  return "below";
}

/**
 * Lo que cierra la ficha. Esc, si nadie lo ha atendido ya y el foco está en la ficha o junto al
 * cuerpo (no en otro diálogo o campo). Pulsar fuera de ella, salvo en otra región de la misma figura
 * (esa la cambia).
 */
export type PopoverEvent =
  | { readonly kind: "key"; readonly key: string; readonly handled: boolean; readonly focusNear: boolean }
  | { readonly kind: "pointer"; readonly inside: boolean; readonly onRegion: boolean };

export function closesPopover(event: PopoverEvent): boolean {
  if (event.kind === "key") return event.key === "Escape" && !event.handled && event.focusNear;
  return !event.inside && !event.onRegion;
}

/** Contramedidas con seguimiento abierto: no se ofrecen como nuevas (la regla de `CrewConsole`). */
export function followingOf(status: Pick<CrewStatus, "followups">): ReadonlySet<string> {
  return new Set(status.followups.filter((item) => item.state !== "closed").map((item) => item.countermeasure.id));
}

function RegionCard({
  region,
  status,
  stale,
  known,
  onClose,
}: {
  region: AnatomyRegionState;
  status: CrewStatus;
  stale: boolean;
  /** Las regiones de la respuesta: pulsar otra de la figura la cambia, no cierra. */
  known: ReadonlySet<string>;
  onClose: () => void;
}) {
  const card = useRef<HTMLDivElement | null>(null);
  const opener = useRef<Element | null>(null);
  const [side, setSide] = useState<PopoverSide>("right");
  const [operator] = useOperator();
  // El cierre y las regiones cambian con cada vuelta de la consola; los avisos se ponen una vez.
  const latest = useRef({ onClose, known });
  latest.current = { onClose, known };

  // En una pestaña oculta la ficha existe pero no se ve: ni se enfoca ni atiende nada.
  const hidden = () => card.current === null || card.current.closest("[hidden]") !== null;
  const restoreFocus = () => {
    const previous = opener.current;
    if (previous instanceof HTMLElement && previous.isConnected) previous.focus({ preventScroll: true });
  };
  const close = () => {
    latest.current.onClose();
    restoreFocus();
  };
  const closeRef = useRef(close);
  closeRef.current = close;

  useEffect(() => {
    opener.current = document.activeElement;
    if (!hidden()) card.current?.focus({ preventScroll: true });
    const onKey = (event: KeyboardEvent) => {
      const node = card.current;
      if (node === null || hidden()) return;
      const focused = document.activeElement;
      const anchor = node.parentElement;
      const focusNear =
        focused === null || focused === document.body || node.contains(focused) || (anchor?.contains(focused) ?? false);
      if (!closesPopover({ kind: "key", key: event.key, handled: event.defaultPrevented, focusNear })) return;
      event.preventDefault();
      closeRef.current();
    };
    const onPointer = (event: PointerEvent) => {
      const node = card.current;
      if (node === null || hidden()) return;
      const target = event.target instanceof Element ? event.target : null;
      const inside = target !== null && node.contains(target);
      const zone = target !== null && (node.parentElement?.contains(target) ?? false) ? target.closest("[data-region]") : null;
      const onRegion = zone !== null && latest.current.known.has(zone.getAttribute("data-region") ?? "");
      if (closesPopover({ kind: "pointer", inside, onRegion })) latest.current.onClose();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, []);

  // Junto al cuerpo: se mide la tarjeta que lo contiene y se elige el lado con sitio.
  useLayoutEffect(() => {
    const place = () => {
      const node = card.current;
      const anchor = node?.parentElement ?? null;
      if (node === null || anchor === null) return;
      setSide(popoverSide(anchor.getBoundingClientRect(), node.offsetWidth, window.innerWidth));
    };
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, []);

  let body: ReactNode;
  if (region.has_data) {
    body = <RegionChain region={region} status={status} operator={operator} following={followingOf(status)} />;
  } else {
    body = (
      <div className="region-detail">
        <PanelTitle as="h3" pictogram={regionPictogram(region)}>
          {region.display}
        </PanelTitle>
        {/* Sin lecturas ni hallazgos: las palabras del backend, en gris; no es un nivel. */}
        <p className="secondary">{region.data_note ?? region.note}</p>
      </div>
    );
  }

  return (
    <div
      ref={card}
      className="region-popover"
      data-side={side}
      role="dialog"
      aria-modal="false"
      aria-label={region.display}
      tabIndex={-1}
    >
      {/* El título es el de la cadena (`RegionChain`): aquí solo el mando de cerrar. */}
      <div className="region-popover-head">
        <Command type="button" concept="cancel" onClick={close}>
          {tr("Cerrar", "Close")}
        </Command>
      </div>
      {/* F.4.3.1 c: lo que se ve es de otro instante que el estado de la consola; se dice. */}
      {stale && (
        <p>
          <Mark pictogram={NO_STATE.pictogram} color={NO_STATE.color}>
            {tr(
              "El estado por regiones es anterior al que muestra la consola; se está actualizando.",
              "The state by region is older than the one the console shows; it is updating.",
            )}
          </Mark>
        </p>
      )}
      {body}
    </div>
  );
}
