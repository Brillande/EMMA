import { type KeyboardEvent, useLayoutEffect, useRef, useState, useSyncExternalStore } from "react";

import { Pictogram } from "../icons";
import { formatNumber } from "../lib/format";
import { tr } from "../lib/i18n";
import { type PreferenceStore, browserStore, nextTabIndex } from "./displayModes";

import "../shell/rowPages.css";

/**
 * Las pestañas por páginas de dos filas (decisión del usuario, 2026-11-16): «respetar la forma visual de
 * las filas, pero limitar a dos y carrusel». Cada fila de la pestaña se queda como siempre (las mismas
 * cosas, los mismos anchos, las que sean), la página enseña dos filas a toda la pantalla y las demás
 * pasan con las flechas o deslizando, en los dos sentidos y dando la vuelta.
 *
 * Por qué se mide y no se declara: las filas no están escritas en ningún sitio, salen de la rejilla de
 * cada pestaña (12 columnas, `span` por panel en su hoja, repartos por contenedor). Así ninguna hoja
 * cambia: con todo a la vista se mira dónde empieza cada panel (`offsetTop`), los que empiezan a la
 * misma altura son una fila, y luego se apagan (`data-row-off`) los de las filas que no tocan. Se vuelve
 * a medir al cambiar el ancho, al cambiar los paneles y al cambiar de página; medir y apagar van en el
 * mismo paso de pintado, sin parpadeo.
 *
 * Lo que va fijo (`data-row-pin`: la ubicación, las barras de anclas) no cuenta como fila y se ve en
 * todas las páginas. La página abierta se recuerda por equipo (`emma.rows.<consola>.<pestaña>`).
 * Apagar una fila no cambia ningún dato ni desmonta nada: lo escrito y lo cargado se quedan.
 */

const PREFIX = "emma.rows.";
const ROWS_PER_PAGE = 2;
/** Por debajo de esta diferencia de `top`, dos paneles empiezan en la misma fila. */
const SAME_ROW_PX = 4;
/** Lo que se deja libre bajo la pestaña (el pie de la concha va aparte, `--shell-below`). */
const BOTTOM_GAP_PX = 10;

export function rowsKey(id: string): string {
  return PREFIX + id;
}

export function readRowsPage(store: PreferenceStore | null, id: string): number {
  try {
    const raw = Number(store?.getItem(rowsKey(id)));
    return Number.isInteger(raw) && raw >= 0 ? raw : 0;
  } catch {
    return 0;
  }
}

export function writeRowsPage(store: PreferenceStore | null, id: string, page: number): void {
  try {
    store?.setItem(rowsKey(id), String(page));
  } catch {
    // Sin almacén dura lo que la sesión.
  }
}

const state = new Map<string, number>();
/** Hacia dónde se pasó la última página de cada pestaña: de ahí sale el sentido del deslizamiento. */
const direction = new Map<string, "next" | "previous">();
const listeners = new Set<() => void>();

function current(id: string): number {
  if (!state.has(id)) state.set(id, readRowsPage(browserStore(), id));
  return state.get(id) ?? 0;
}

export function setRowsPage(id: string, page: number): void {
  state.set(id, page);
  writeRowsPage(browserStore(), id, page);
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function useRowsPage(id: string): number {
  const read = () => current(id);
  return useSyncExternalStore(subscribe, read, read);
}

/** Solo para pruebas. */
export function resetRowsForTests(): void {
  state.clear();
}

/** Agrupa en filas por dónde empiezan: los `top` a menos de `SAME_ROW_PX` son la misma fila. */
export function groupRows(tops: readonly number[]): number[] {
  const order = tops.map((top, index) => ({ top, index })).sort((a, b) => a.top - b.top);
  const rowOf: number[] = new Array<number>(tops.length).fill(0);
  let row = -1;
  let last = Number.NEGATIVE_INFINITY;
  for (const { top, index } of order) {
    if (top - last > SAME_ROW_PX) {
      row += 1;
      last = top;
    }
    rowOf[index] = row;
  }
  return rowOf;
}

/**
 * La página de cada panel. Sin corte, de dos filas en dos filas. Con corte (`pageBreak()` de
 * `ConsoleTabs`, donde estaba la raya), la primera página son todas las filas de lo que va antes del
 * corte —lo que la pestaña enseñaba al abrirla— y lo de después, de dos en dos.
 */
export function pagesFor(rowOf: readonly number[], breakAt: number | undefined, free: readonly boolean[] = []): number[] {
  // Una fila de cabecera (todos sus paneles `data-row-free`: la franja de título de la pestaña) no
  // cuenta: va en la página de la fila de datos que la sigue. Así la primera página lleva siempre dos
  // filas de datos (decisión del usuario, 2026-11-16).
  const rows = [...new Set(rowOf)].sort((a, b) => a - b);
  const isFree = (row: number) => rowOf.every((r, at) => r !== row || free[at] === true);
  const pageOfRow = new Map<number, number>();
  let counted = 0;
  const pending: number[] = [];
  for (const row of rows) {
    if (isFree(row)) {
      pending.push(row);
      continue;
    }
    const page = Math.floor(counted / ROWS_PER_PAGE);
    for (const waiting of pending.splice(0)) pageOfRow.set(waiting, page);
    pageOfRow.set(row, page);
    counted += 1;
  }
  const last = Math.max(0, Math.floor((counted - 1) / ROWS_PER_PAGE));
  for (const waiting of pending) pageOfRow.set(waiting, last);
  if (breakAt === undefined || breakAt <= 0 || breakAt >= rowOf.length) {
    return rowOf.map((row) => pageOfRow.get(row) ?? 0);
  }
  const firstRows = new Set(rowOf.slice(0, breakAt));
  const rest = [...new Set(rowOf.slice(breakAt).filter((row) => !firstRows.has(row)))].sort((a, b) => a - b);
  return rowOf.map((row, at) => {
    if (at < breakAt || firstRows.has(row)) return 0;
    return 1 + Math.floor(rest.indexOf(row) / ROWS_PER_PAGE);
  });
}

export function pageCount(rows: number): number {
  return Math.max(1, Math.ceil(rows / ROWS_PER_PAGE));
}

export function stepRowsPage(count: number, index: number, direction: "next" | "previous"): number {
  return nextTabIndex(count, index, direction === "next" ? "ArrowRight" : "ArrowLeft") ?? 0;
}

/**
 * Los elementos de la rejilla de la sección: los `display: contents` (`.slot`, `.slot-body`) no cuentan,
 * cuentan sus hijos. Lo fijo (`data-row-pin`) y la propia barra de páginas quedan fuera.
 */
function gridItems(body: HTMLElement): HTMLElement[] & { breakAt?: number } {
  const items: HTMLElement[] & { breakAt?: number } = [];
  const walk = (parent: Element) => {
    for (const child of Array.from(parent.children)) {
      if (!(child instanceof HTMLElement)) continue;
      if (child.dataset.rowBreak !== undefined) {
        items.breakAt ??= items.length;
        continue;
      }
      if (child.dataset.rowPin !== undefined || child.classList.contains("row-pages")) continue;
      // Un bloque con su propia rejilla que por dentro ocupa varias filas (`data-row-group`, p. ej.
      // `.grav-main` de «Gravedad») cuenta por sus piezas, no como una sola fila.
      if (getComputedStyle(child).display === "contents" || child.dataset.rowGroup !== undefined) walk(child);
      else items.push(child);
    }
  };
  walk(body);
  return items;
}

/**
 * Estira un panel hasta `height` y centra en vertical lo que lleva dentro (decisión del usuario,
 * 2026-11-16: «centra los datos»: al crecer, el contenido se quedaba arriba con un hueco debajo). En una
 * caja en columna (flex) se centra con `justify-content`; en una rejilla o un bloque, con
 * `align-content`. Lo que ya crece para llenar (filas `1fr`, gráficas) no deja hueco y no se mueve.
 */
/** Lo más que se amplía el contenido de una tarjeta estirada. */
const MAX_GROW = 1.15; // «no tan grande», «más pequeña» (decisión del usuario, 2026-11-16): antes 1,8 y 1,3

function stretch(item: HTMLElement, height: number): void {
  item.style.minHeight = `${height}px`;
  const style = getComputedStyle(item);
  const column = style.display.includes("flex") && style.flexDirection.startsWith("column");
  const kids = Array.from(item.children).filter(
    (kid): kid is HTMLElement => kid instanceof HTMLElement && getComputedStyle(kid).display !== "none",
  );
  if (kids.length === 0) return;
  item.dataset.rowCentered = "";
  if (column && kids.length >= 2) {
    // El título se queda arriba, a la misma altura en toda la fila, como en el original; lo de debajo
    // (los datos) se centra en el alto que sobra. Lo que se estiraba para empujar al pie (una lista con
    // `flex: 1`, un botón con `margin-top: auto`) se recoge mientras el panel está estirado.
    for (const kid of kids) if (parseFloat(getComputedStyle(kid).flexGrow) > 0) kid.style.flexGrow = "0";
    const gap = parseFloat(style.rowGap) || 0;
    kids.forEach((kid, at) => {
      if (at < 2) return;
      const before = kids[at - 1]!;
      const space = kid.getBoundingClientRect().top - before.getBoundingClientRect().bottom;
      if (space > gap + 24) kid.style.marginTop = gap > 0 ? "0" : "0.45rem";
    });
    kids[1]!.style.marginTop = "auto";
    kids[kids.length - 1]!.style.marginBottom = "auto";
  } else if (style.display === "block" && kids.length >= 2 && /^H[1-6]$/.test(kids[0]!.tagName)) {
    // Un marco en bloque con su título y un cuerpo (las rutas de «Inicio»): mientras está estirado,
    // en columna, y el cuerpo ocupa todo el alto de debajo (decisión del usuario, 2026-11-16: «puede
    // ocupar toda su parte»); sus tarjetas, en rejilla, se estiran con él.
    item.style.display = "flex";
    item.style.flexDirection = "column";
    item.dataset.rowFill = "";
  } else if (!style.display.includes("flex")) {
    // Una caja en bloque o en rejilla: todo su contenido, centrado en el alto.
    item.style.alignContent = "center";
  }
  // Los textos crecen hasta llenar su tarjeta (decisión del usuario, 2026-11-16: «amplía los textos para
  // que ocupen las ventanas que les corresponden»). Las hojas miden en `rem`, así que el tamaño de letra
  // no basta: se amplía con `zoom` lo de debajo del título (el título se queda, alineado en la fila),
  // lo más que quepa sin que la tarjeta crezca ni se desborde, hasta `MAX_GROW`. Un `zoom` en el hijo
  // reparte su ancho de nuevo, así que no se sale por los lados.
  // Una tarjeta en fila (texto al lado de un dibujo, como el pie de «Inicio»): ampliar el texto lo
  // empujaría contra el dibujo; se queda con su tamaño.
  if (item.dataset.rowFill === undefined && style.display.includes("flex") && !column) return;
  const titled = (column || item.dataset.rowFill !== undefined) && kids.length >= 2;
  const grow = titled ? kids.slice(1) : kids;
  // Cabe si la tarjeta no crece ni se desborda, y si nada de lo ampliado se sale de su caja por los lados
  // («que no se salgan de donde tienen que estar»): se compara cada caja de dentro con cómo estaba sin
  // ampliar (lo que ya se recortaba con puntos suspensivos en el original no cuenta).
  const inner = grow.flatMap((kid) => [kid, ...Array.from(kid.querySelectorAll<HTMLElement>("*"))]);
  const spill = (box: HTMLElement) => (box.clientWidth > 0 ? box.scrollWidth - box.clientWidth : 0);
  for (const kid of grow) kid.style.zoom = "1";
  const before = new Map(inner.map((box) => [box, spill(box)]));
  const fits = () =>
    item.scrollHeight <= item.clientHeight + 1 &&
    item.getBoundingClientRect().height <= height + 1 &&
    item.scrollWidth <= item.clientWidth + 1 &&
    inner.every((box) => spill(box) <= (before.get(box) ?? 0) + 1);
  let low = 1;
  let high = MAX_GROW;
  for (let step = 0; step < 6; step += 1) {
    const mid = (low + high) / 2;
    for (const kid of grow) kid.style.zoom = String(mid);
    if (fits()) low = mid;
    else high = mid;
  }
  for (const kid of grow) {
    if (low > 1.02) kid.style.zoom = low.toFixed(3);
    else kid.style.removeProperty("zoom");
  }
  if (item.dataset.rowFill !== undefined) kids[kids.length - 1]!.style.flexGrow = "1";
}

function unstretch(item: HTMLElement): void {
  item.style.removeProperty("min-height");
  if (item.dataset.rowFill !== undefined) {
    delete item.dataset.rowFill;
    item.style.removeProperty("display");
    item.style.removeProperty("flex-direction");
  }
  item.style.removeProperty("align-content");
  if (item.dataset.rowCentered !== undefined) {
    delete item.dataset.rowCentered;
    for (const kid of Array.from(item.children)) {
      if (!(kid instanceof HTMLElement)) continue;
      kid.style.removeProperty("flex-grow");
      kid.style.removeProperty("margin-top");
      kid.style.removeProperty("margin-bottom");
      kid.style.removeProperty("zoom");
    }
  }
}

/** Las cajas de lo fijo (`data-row-pin`): si el contenedor es `display: contents`, las de dentro. */
function pinnedBoxes(body: HTMLElement): HTMLElement[] {
  const boxes: HTMLElement[] = [];
  const walk = (element: HTMLElement) => {
    if (getComputedStyle(element).display !== "contents") {
      boxes.push(element);
      return;
    }
    for (const child of Array.from(element.children)) if (child instanceof HTMLElement) walk(child);
  };
  for (const pin of Array.from(body.querySelectorAll<HTMLElement>("[data-row-pin]"))) {
    if (pin.parentElement?.closest("[data-row-pin]")) continue;
    walk(pin);
  }
  return boxes;
}

/** Abre la página donde está `element` y devuelve si la cambió. Para enlaces y anclas a un panel. */
export function showRowOf(element: Element | null): boolean {
  const item = element?.closest<HTMLElement>("[data-row]");
  const body = item?.closest<HTMLElement>("[data-rows-id]");
  if (!item || !body) return false;
  const page = Number(item.dataset.rowPage);
  const id = body.dataset.rowsId ?? "";
  if (!Number.isInteger(page) || current(id) === page) return false;
  setRowsPage(id, page);
  return true;
}

function pageName(index: number, count: number): string {
  return tr(
    `página ${formatNumber(index + 1)} de ${formatNumber(count)}`,
    `page ${formatNumber(index + 1)} of ${formatNumber(count)}`,
  );
}

/**
 * La barra de páginas de una sección por filas. Se pinta dentro de la `.section-body` (al final) y desde
 * ahí mide y apaga las filas de su sección.
 */
export function RowPages({ id, label, folded = true }: { id: string; label: string; folded?: boolean }) {
  const navRef = useRef<HTMLElement | null>(null);
  const saved = useRowsPage(id);
  const [count, setCount] = useState(1);
  const page = Math.min(saved, count - 1);
  // Si la pestaña estaba oculta. Al abrirla se empieza por la primera página: ahí van lo que nunca se
  // oculta (HMI §2.7 y §2.8), y una página recordada podría dejar fuera de la vista una alerta nueva.
  const wasHidden = useRef(true);
  const lastShown = useRef<number | null>(null);
  const lastWidth = useRef(0);

  useLayoutEffect(() => {
    const nav = navRef.current;
    const body = nav?.parentElement;
    if (!nav || !body || typeof window === "undefined") return;
    body.dataset.rowsId = id;
    let frame = 0;
    const apply = () => {
      const width = body.getBoundingClientRect().width;
      lastWidth.current = width;
      if (width === 0) {
        wasHidden.current = true; // pestaña oculta: se mide al abrirla
        return;
      }
      if (wasHidden.current) {
        wasHidden.current = false;
        if (current(id) !== 0) {
          setRowsPage(id, 0); // vuelve a medir con la página nueva (cambia `saved`)
          return;
        }
      }
      const items = gridItems(body);
      delete body.dataset.folded;
      for (const item of items) {
        item.removeAttribute("data-row-off");
        unstretch(item);
      }
      const rowOf = groupRows(items.map((item) => item.offsetTop));
      const pageOf = pagesFor(rowOf, items.breakAt, items.map((item) => item.dataset.rowFree !== undefined));
      const pages = pageOf.length === 0 ? 1 : Math.max(...pageOf) + 1;
      setCount(pages);
      const shown = Math.min(current(id), pages - 1);
      items.forEach((item, at) => {
        item.dataset.row = String(rowOf[at] ?? 0);
        item.dataset.rowPage = String(pageOf[at] ?? 0);
        if ((pageOf[at] ?? 0) !== shown) item.setAttribute("data-row-off", "");
      });
      // El carrusel: al cambiar de página, la nueva entra deslizándose desde la derecha («siguiente»,
      // o el dedo hacia la izquierda) o desde la izquierda («anterior»). Solo al cambiar de página.
      if (lastShown.current !== null && lastShown.current !== shown) {
        const towards = direction.get(id) ?? (shown > lastShown.current ? "next" : "previous");
        body.dataset.rowSlide = "";
        void body.offsetWidth; // reinicia la animación si se pulsa seguido
        body.dataset.rowSlide = towards;
      }
      lastShown.current = shown;
      // Las dos filas a la vista llenan la pantalla: cada panel, al menos la mitad de lo que queda bajo
      // lo fijo, descontada la barra. Si su contenido pide más, crece y la página se desplaza.
      // La primera página se ve como se veía la pestaña al abrirla, con lo secundario plegado: las hojas
      // de cada tablero tienen su aspecto de partida bajo `data-folded` y `--fold-fill` (lote
      // «responsivo»), y se respetan tal cual (decisión del usuario: «respetar el estilo que tenía»).
      // Las demás páginas son las filas de debajo, como se veían desplegadas.
      if (shown === 0 && folded) {
        body.dataset.folded = "true";
        const fill = Math.max(0, Math.floor(window.innerHeight - (body.getBoundingClientRect().top + window.scrollY) - BOTTOM_GAP_PX));
        body.style.setProperty("--fold-fill", `${fill}px`);
      } else {
        delete body.dataset.folded;
        body.style.removeProperty("--fold-fill");
      }
      const visibleRows = new Set(rowOf.filter((_, at) => (pageOf[at] ?? 0) === shown)).size;
      const firstVisible = items.find((item) => !item.hasAttribute("data-row-off"));
      if (firstVisible !== undefined && visibleRows > 0) {
        const top = firstVisible.getBoundingClientRect().top + window.scrollY;
        const gap = parseFloat(getComputedStyle(body).rowGap) || 0;
        const below = nav.getBoundingClientRect().height + gap + BOTTOM_GAP_PX + shellBelow(body);
        // `.app` está fuera de lo observado (la sonda va ahí), así que medir no vuelve a disparar esto.
        // Lo fijo que va por debajo de la primera fila (p. ej. «Ayuda urgente» al pie de «Inicio») también
        // tiene que caber: se descuenta su alto, una vez por cada altura distinta a la que empieza.
        // Lo fijo que va al lado de una fila visible (p. ej. «Ayuda urgente» junto al diagnóstico) ya
        // cabe en esa fila: solo cuenta lo que va en una fila suya.
        const visibleTops = items
          .filter((item) => !item.hasAttribute("data-row-off"))
          .map((item) => item.getBoundingClientRect().top + window.scrollY);
        const pinnedBelow = new Map<number, number>();
        for (const pin of pinnedBoxes(body)) {
          const box = pin.getBoundingClientRect();
          const at = Math.round(box.top + window.scrollY);
          if (at <= top + SAME_ROW_PX) continue;
          if (visibleTops.some((rowTop) => Math.abs(rowTop - at) <= SAME_ROW_PX)) continue;
          pinnedBelow.set(at, Math.max(pinnedBelow.get(at) ?? 0, box.height + gap));
        }
        const fixedBelow = [...pinnedBelow.values()].reduce((sum, height) => sum + height, 0);
        const room = window.innerHeight - top - below - fixedBelow - gap * (visibleRows - 1);
        // Lo que sobra se reparte en proporción al alto natural de cada fila: una franja fina (una
        // cabecera) apenas crece y una fila de tarjetas se queda con casi todo; si no sobra nada, cada
        // fila se queda con el suyo. Un panel que ocupa varias filas (`grid-row: span N`) no marca el
        // alto de ninguna: se estira solo con las filas que cubre.
        const spans = (item: HTMLElement) => /span\s+([2-9]|\d{2,})/.test(getComputedStyle(item).gridRowEnd);
        const natural = new Map<number, number>();
        items.forEach((item, at) => {
          if (item.hasAttribute("data-row-off") || spans(item)) return;
          const row = rowOf[at] ?? 0;
          natural.set(row, Math.max(natural.get(row) ?? 0, item.getBoundingClientRect().height));
        });
        const used = [...natural.values()].reduce((sum, height) => sum + height, 0);
        const scale = used > 0 ? room / used : 1;
        // En la primera página manda la hoja de la pestaña (su aspecto plegado ya llena la ventana con
        // `--fold-fill` y sabe qué crece: la tendencia, el dibujo…); estirar aquí lo descuadraba.
        if (scale > 1 && (shown > 0 || !folded)) {
          items.forEach((item, at) => {
            if (item.hasAttribute("data-row-off") || spans(item)) return;
            stretch(item, Math.floor((natural.get(rowOf[at] ?? 0) ?? 0) * scale));
          });
        }
      }
    };
    const schedule = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(apply);
    };
    apply();
    window.addEventListener("resize", schedule);
    // Abrir la pestaña (de oculta a visible) o estrechar el tablero (carril, asistente acoplado) cambia
    // el ancho sin cambiar la ventana. Solo el ancho: el alto lo cambia esta misma medida.
    const sizes =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(() => {
            if (Math.round(body.getBoundingClientRect().width) !== Math.round(lastWidth.current)) schedule();
          });
    sizes?.observe(body);
    // Un panel que aparece o desaparece (datos que llegan) cambia las filas; apagar no es un cambio de hijos.
    const mutations = typeof MutationObserver === "undefined" ? null : new MutationObserver(schedule);
    mutations?.observe(body, { childList: true, subtree: true });
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", schedule);
      mutations?.disconnect();
      sizes?.disconnect();
      for (const item of gridItems(body)) {
        item.removeAttribute("data-row-off");
        unstretch(item);
      }
    };
  }, [id, saved, folded]);

  const many = count > 1;
  const previous = stepRowsPage(count, page, "previous");
  const next = stepRowsPage(count, page, "next");
  const go = (to: number, towards: "next" | "previous" = to >= page ? "next" : "previous") => {
    direction.set(id, towards);
    setRowsPage(id, to);
    navRef.current?.parentElement?.scrollIntoView({ block: "start", behavior: "smooth" });
  };
  const onKey = (event: KeyboardEvent<HTMLElement>) => {
    if (!many || (event.key !== "ArrowLeft" && event.key !== "ArrowRight")) return;
    event.preventDefault();
    if (event.key === "ArrowRight") go(next, "next");
    else go(previous, "previous");
  };

  // Deslizar con el dedo sobre la sección: de derecha a izquierda, la siguiente; al revés, la anterior.
  useLayoutEffect(() => {
    const body = navRef.current?.parentElement;
    if (!body || !many) return;
    let start: { x: number; y: number } | null = null;
    const down = (event: PointerEvent) => {
      // Dentro de un mando que ya usa el gesto (deslizador, lienzo, visor, campo) no se cambia de página.
      const target = event.target as Element | null;
      const owned = target?.closest("input, textarea, select, canvas, iframe, [role='slider'], [contenteditable='true']");
      start = event.pointerType === "mouse" || owned ? null : { x: event.clientX, y: event.clientY };
    };
    const up = (event: PointerEvent) => {
      const from = start;
      start = null;
      if (from === null) return;
      const dx = event.clientX - from.x;
      const dy = event.clientY - from.y;
      if (Math.abs(dx) < 60 || Math.abs(dx) < 1.5 * Math.abs(dy)) return;
      direction.set(id, dx < 0 ? "next" : "previous");
      setRowsPage(id, dx < 0 ? next : previous);
    };
    body.addEventListener("pointerdown", down);
    body.addEventListener("pointerup", up);
    return () => {
      body.removeEventListener("pointerdown", down);
      body.removeEventListener("pointerup", up);
    };
  }, [id, many, next, previous]);

  return (
    <nav
      ref={navRef}
      className="row-pages"
      hidden={!many}
      aria-label={tr(`Páginas de ${label}`, `${label} pages`)}
      onKeyDown={onKey}
    >
      <button
        type="button"
        className="row-pages-arrow row-pages-previous"
        aria-label={tr(`Ir a la ${pageName(previous, count)}`, `Go to ${pageName(previous, count)}`)}
        onClick={() => go(previous, "previous")}
      >
        <Pictogram name="arrow-right" />
      </button>
      <span className="row-pages-where num" aria-live="polite">
        {formatNumber(page + 1)} / {formatNumber(count)}
      </span>
      <span className="row-pages-dots">
        {Array.from({ length: count }, (_, at) => (
          <button
            key={at}
            type="button"
            className="row-pages-dot"
            aria-label={pageName(at, count)}
            aria-current={at === page ? "true" : undefined}
            onClick={() => go(at)}
          />
        ))}
      </span>
      <button
        type="button"
        className="row-pages-arrow row-pages-next"
        aria-label={tr(`Ir a la ${pageName(next, count)}`, `Go to ${pageName(next, count)}`)}
        onClick={() => go(next, "next")}
      >
        <Pictogram name="arrow-right" />
      </button>
    </nav>
  );
}

/** El pie de la concha bajo la sección (`--shell-below`, `consoleShell.css`), en px. */
function shellBelow(body: HTMLElement): number {
  const probe = document.createElement("div");
  probe.style.cssText = "position:absolute;visibility:hidden;height:var(--shell-below,0px)";
  // Fuera de la sección: un hijo nuevo dentro dispararía el observador de cambios y otra medida.
  (body.closest(".app") ?? document.body).appendChild(probe);
  const height = probe.getBoundingClientRect().height;
  probe.remove();
  return height;
}
