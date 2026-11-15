import { type ReactElement, type ReactNode, isValidElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CrewStatus, DiaryCatalog, Followup } from "../lib/api";
import {
  type FollowupCloser,
  FollowupItemView,
  HomeLogbookView,
  type HomeLinks,
  followupClosure,
  quickDiaryEntry,
  sendQuickDiary,
} from "./HomeBoard";
import { canSubmit } from "../diary/entry";

/**
 * Lo que «Inicio» escribe sin salir de él (2026-11-15: «que si pulso el botón pasen cosas»): el «+»
 * de la bitácora anota por la ruta del diario (firmada y en el ledger, invariante 4), y un
 * seguimiento abierto de «Próximas acciones» se cierra con el cierre de la consola. Sin DOM en la
 * suite: las vistas sin estado se despliegan llamando a sus componentes, y lo que envían se
 * comprueba en la petición (`fetch` simulado) o en el cierre recibido.
 */

type Props = Record<string, unknown> & { children?: ReactNode };

/** Los elementos nativos del árbol (`button`, `form`, `input`…), con sus props. */
function elements(node: ReactNode): ReactElement<Props>[] {
  const found: ReactElement<Props>[] = [];
  const walk = (child: ReactNode): void => {
    if (Array.isArray(child)) {
      child.forEach(walk);
      return;
    }
    if (!isValidElement(child)) return;
    const element = child as ReactElement<Props>;
    if (typeof element.type === "function") {
      walk((element.type as (p: Props) => ReactNode)(element.props));
      return;
    }
    found.push(element);
    walk(element.props.children);
  };
  walk(node);
  return found;
}

function text(child: ReactNode): string {
  if (typeof child === "string" || typeof child === "number") return String(child);
  if (Array.isArray(child)) return child.map(text).join("");
  if (isValidElement(child)) return text((child.props as Props).children);
  return "";
}

const labelOf = (element: ReactElement<Props>) =>
  typeof element.props["aria-label"] === "string" ? element.props["aria-label"] : text(element.props.children);

const buttons = (node: ReactNode) =>
  elements(node).filter((element) => element.type === "button" && typeof element.props.onClick === "function");

const status = {
  subject: "CM-1",
  data: { reference_time: "2026-11-09T00:00:00Z" },
  mission: { start: "2026-11-01T00:00:00Z" },
} as unknown as CrewStatus;

const followup = {
  adoption_index: 3,
  countermeasure: { id: "cm-a", action: "Ejercicio de resistencia" },
  domain: "cardiovascular",
  window_ends: "2026-11-12T00:00:00Z",
  state: "in_window",
} as unknown as Followup;

const catalog = {
  indicators: [
    {
      key: "mood",
      display_es: "Estado de ánimo",
      unit_display: "puntos",
      physical_min: 1,
      physical_max: 10,
      range_text: "1 a 10",
      food_item: null,
    },
    {
      key: "food-acceptability",
      display_es: "Aceptabilidad de la comida",
      unit_display: "puntos",
      physical_min: 1,
      physical_max: 9,
      range_text: "1 a 9",
      food_item: { label: "Alimento", required: true, max_length: 80 },
    },
  ],
  recorded_by: { required: true, label: "Quién anota", note: "", missing_display: "", legacy_note: "" },
} as unknown as DiaryCatalog;

describe("el «+» de la bitácora", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("abre y cierra el formulario en la misma tarjeta, sin ir a otra sección", () => {
    const onWrite = vi.fn();
    const view = HomeLogbookView({ status, diary: { state: "ready", value: [] }, writing: false, onWrite });
    const plus = buttons(view).filter((button) => labelOf(button) === "Escribir en el diario");
    expect(plus).toHaveLength(1);
    expect(plus[0]?.props["aria-expanded"]).toBe(false);
    (plus[0]?.props.onClick as () => void)();
    expect(onWrite).toHaveBeenCalledTimes(1);
  });

  it("fuera de la consola de tripulación no hay «+»", () => {
    const view = HomeLogbookView({ status, diary: { state: "ready", value: [] }, writing: false, onWrite: null });
    expect(buttons(view)).toEqual([]);
  });

  it("anota por POST /api/diary/entries con el tripulante, la cifra y quién la teclea", async () => {
    const fetched = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async () =>
        new Response(JSON.stringify({ ledger_index: 41, content_hash: "abc" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetched);
    const prepared = quickDiaryEntry(catalog, "CM-1", "mood", "7,5", "  CMO  ");
    expect(canSubmit(prepared)).toBe(true);
    const outcome = await sendQuickDiary(prepared);
    expect(outcome).toEqual({ saved: ["mood"], failed: null });
    expect(fetched).toHaveBeenCalledTimes(1);
    const [url, init] = fetched.mock.calls[0] ?? [];
    expect(url).toBe("/api/diary/entries");
    expect(init?.method).toBe("POST");
    // Solo de quién es, qué, cuánto y quién teclea: fuente, tipo y hora los pone el backend.
    expect(JSON.parse(String(init?.body))).toEqual({ key: "mood", value: 7.5, subject: "CM-1", recorded_by: "CMO" });
  });

  it("dice el «no» del backend tal cual, y no da por anotado lo que no entró", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: "Fuera del catálogo." }), { status: 422, headers: { "Content-Type": "application/json" } })),
    );
    const outcome = await sendQuickDiary(quickDiaryEntry(catalog, "CM-1", "mood", "4", "CMO"));
    expect(outcome.saved).toEqual([]);
    expect(outcome.failed?.key).toBe("mood");
  });

  it("no envía nada fuera de rango, sin elegir qué, sin quién teclea o sin el alimento que se pide", () => {
    expect(canSubmit(quickDiaryEntry(catalog, "CM-1", "mood", "11", "CMO"))).toBe(false);
    expect(quickDiaryEntry(catalog, "CM-1", "mood", "11", "CMO").problems).toHaveLength(1);
    expect(canSubmit(quickDiaryEntry(catalog, "CM-1", "", "5", "CMO"))).toBe(false);
    expect(quickDiaryEntry(catalog, "CM-1", "mood", "5", "  ").unnamed).toBe(true);
    expect(canSubmit(quickDiaryEntry(catalog, "CM-1", "food-acceptability", "6", "CMO"))).toBe(false);
    const withFood = quickDiaryEntry(catalog, "CM-1", "food-acceptability", "6", "CMO", "lentejas");
    expect(withFood.bodies).toEqual([
      { key: "food-acceptability", value: 6, subject: "CM-1", recorded_by: "CMO", food: "lentejas" },
    ]);
  });
});

describe("un seguimiento abierto en «Próximas acciones»", () => {
  const closer = (close = vi.fn(async () => undefined)): FollowupCloser => ({
    close,
    operator: "CMO",
    setOperator: () => undefined,
    privacy: false,
  });
  const base = {
    item: followup,
    status,
    open: false,
    onToggle: () => undefined,
    reason: "",
    onReason: () => undefined,
    busy: false,
    error: null,
    onSubmit: () => undefined,
  };

  it("se pulsa y despliega su cierre", () => {
    const onToggle = vi.fn();
    const row = FollowupItemView({ ...base, closer: closer(), onToggle });
    const found = buttons(row);
    expect(found.map(labelOf)).toEqual(["Cerrar seguimiento: Ejercicio de resistencia"]);
    (found[0]?.props.onClick as () => void)();
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("abierto, el formulario envía el cierre con quién y por qué", () => {
    const onSubmit = vi.fn();
    const row = FollowupItemView({ ...base, closer: closer(), open: true, reason: "hecho", onSubmit });
    const form = elements(row).find((element) => element.type === "form");
    const preventDefault = vi.fn();
    (form?.props.onSubmit as (event: { preventDefault: () => void }) => void)({ preventDefault });
    expect(preventDefault).toHaveBeenCalled();
    expect(onSubmit).toHaveBeenCalledTimes(1);
    const submit = elements(row).find((element) => element.type === "button" && element.props.type === "submit");
    expect(submit?.props.disabled).toBe(false);
  });

  it("sin motivo o sin quién, el mando de cerrar no se puede pulsar ni se envía", async () => {
    const row = FollowupItemView({ ...base, closer: { ...closer(), operator: " " }, open: true, reason: "hecho" });
    const submit = elements(row).find((element) => element.type === "button" && element.props.type === "submit");
    expect(submit?.props.disabled).toBe(true);
    expect(followupClosure(followup, "CMO", "  ")).toBeNull();
    expect(followupClosure(followup, " ", "hecho")).toBeNull();
    // La regla del backend: al menos una letra o cifra en el nombre.
    expect(followupClosure(followup, "-", "hecho")).toBeNull();
    // Lo que recibe el cierre de la consola (`countermeasureActions.close`).
    const close = vi.fn(async () => undefined);
    const args = followupClosure(followup, " CMO ", " hecho ");
    expect(args).toEqual([3, "CMO", "hecho"]);
    if (args !== null) await closer(close).close(...args);
    expect(close).toHaveBeenCalledWith(3, "CMO", "hecho");
  });

  it("sin el cierre de la consola, lleva a «Peligros y alertas» (no desaparece)", () => {
    const opened: string[] = [];
    const links: HomeLinks = {
      openSection: (key) => opened.push(key),
      sectionName: (key) => (key === "hazards" ? "Peligros y alertas" : null),
    };
    const found = buttons(FollowupItemView({ ...base, closer: null, links }));
    expect(found.map(labelOf)).toEqual(["Abrir Peligros y alertas: Ejercicio de resistencia"]);
    (found[0]?.props.onClick as () => void)();
    expect(opened).toEqual(["hazards"]);
  });
});
