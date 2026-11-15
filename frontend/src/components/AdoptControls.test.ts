import { type FormEvent, type ReactElement, type ReactNode, createElement, isValidElement } from "react";
import { describe, expect, it, vi } from "vitest";

import { renderToStaticMarkup } from "../assistant/staticMarkup";
import type { HomeData } from "../dashboard/HomeBoard";
import { GravExercises, type GravityData } from "../gravity/GravityBoard";
import { IsoRecommendations, type IsolationData } from "../isolation/IsolationBoard";
import type { CrewStatus, Recommendation } from "../lib/api";
import { RadRecommendations, type RadiationData } from "../radiation/RadiationBoard";
import { ADOPT_FORM_IDLE, AdoptControls, AdoptControlsView, type AdoptFormState, type BoardDecisions } from "./AdoptControls";

/**
 * «Adoptar» y «No adoptar» en las listas de los tableros (unidad «botones-06»): pulsar llama a la
 * acción de la consola —la misma de «Peligros y alertas», que firma en el ledger— con la
 * contramedida y quien firma, y tras releer el estado se ve lo decidido.
 *
 * Sin DOM en la suite: se despliega el árbol llamando a cada componente; `AdoptControls` (con su
 * gancho) se sustituye por `AdoptControlsView` con un estado de formulario que la prueba controla.
 */

type Props = Record<string, unknown> & { children?: ReactNode };
type Found = { tag: string; label: string; props: Props };

function text(child: ReactNode): string {
  if (typeof child === "string" || typeof child === "number") return String(child);
  if (Array.isArray(child)) return child.map(text).join("");
  if (isValidElement(child)) return text((child.props as Props).children);
  return "";
}

/** Los botones y formularios del árbol, con `AdoptControls` pintado con el estado `form`. */
function controls(node: ReactNode, form: AdoptFormState, update = vi.fn()): Found[] {
  const found: Found[] = [];
  const walk = (child: ReactNode): void => {
    if (Array.isArray(child)) {
      child.forEach(walk);
      return;
    }
    if (!isValidElement(child)) return;
    const element = child as ReactElement<Props>;
    const { props } = element;
    if (element.type === AdoptControls) {
      walk(AdoptControlsView({ ...(props as unknown as Parameters<typeof AdoptControls>[0]), form, update }));
      return;
    }
    if (typeof element.type === "function") {
      walk((element.type as (p: Props) => ReactNode)(props));
      return;
    }
    if (element.type === "button" || element.type === "form") {
      found.push({ tag: element.type, label: text(props.children), props });
    }
    walk(props.children);
  };
  walk(node);
  return found;
}

const button = (found: Found[], label: string) => {
  const hit = found.find((item) => item.tag === "button" && item.label === label);
  if (hit === undefined) throw new Error(`sin botón «${label}»: ${found.map((item) => item.label).join(" | ")}`);
  return hit.props;
};

const recommendation = (domain: string, id: string, extra: Partial<Recommendation> = {}): Recommendation =>
  ({
    domain,
    action: `Acción del backend (${id})`,
    rationale: "Motivo del backend.",
    urgency: "soon",
    notify_ground: false,
    evidence: [],
    countermeasure: { id },
    decision: null,
    ...extra,
  }) as unknown as Recommendation;

const homeWith = (recommendations: Recommendation[]): HomeData =>
  ({ status: { subject: "CM-1", recommendations } as unknown as CrewStatus }) as unknown as HomeData;

const decisions = (overrides: Partial<BoardDecisions> = {}): BoardDecisions => ({
  subject: "CM-1",
  operator: "CDR",
  setOperator: vi.fn(),
  privacy: false,
  following: new Set<string>(),
  adopt: vi.fn(() => Promise.resolve()),
  decline: vi.fn(() => Promise.resolve()),
  ...overrides,
});

const radBoard = (items: Recommendation[], decide: BoardDecisions) =>
  createElement(RadRecommendations, { rad: { home: homeWith(items) } as unknown as RadiationData, decide });

const isoBoard = (items: Recommendation[], decide: BoardDecisions) =>
  createElement(IsoRecommendations, {
    iso: { home: homeWith(items), risk: { state: "ready", value: null } } as unknown as IsolationData,
    decide,
  });

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("Radiación: adoptar desde la lista", () => {
  it("«Adoptar» llama a la acción de la consola con la contramedida y quien firma", async () => {
    const decide = decisions();
    const update = vi.fn();
    const found = controls(radBoard([recommendation("radiation", "rad-shelter")], decide), ADOPT_FORM_IDLE, update);
    (button(found, "Adoptar").onClick as () => void)();
    expect(decide.adopt).toHaveBeenCalledWith("rad-shelter", "CDR");
    await flush();
    // Esperando respuesta y después libre otra vez, sin fallo.
    const states = update.mock.calls.map(([change]) => (change as (s: AdoptFormState) => AdoptFormState)(ADOPT_FORM_IDLE));
    expect(states.some((state) => state.busy)).toBe(true);
    expect(states.every((state) => state.error === null)).toBe(true);
  });

  it("tras releer el estado, la fila dice que está adoptada y no ofrece los mandos", () => {
    const decide = decisions({ following: new Set(["rad-shelter"]) });
    const html = renderToStaticMarkup(radBoard([recommendation("radiation", "rad-shelter")], decide));
    expect(html).toContain("Adoptada: en seguimiento.");
    expect(html).not.toContain(">Adoptar<");
    expect(controls(radBoard([recommendation("radiation", "rad-shelter")], decide), ADOPT_FORM_IDLE)).toEqual([]);
  });

  it("sin quien firma los mandos están apagados y se pide el nombre en la misma tarjeta", () => {
    const decide = decisions({ operator: "  " });
    const found = controls(radBoard([recommendation("radiation", "rad-shelter")], decide), ADOPT_FORM_IDLE);
    expect(button(found, "Adoptar").disabled).toBe(true);
    expect(button(found, "No adoptar").disabled).toBe(true);
    const html = renderToStaticMarkup(radBoard([recommendation("radiation", "rad-shelter")], decide));
    expect(html).toContain("nombre o indicativo");
  });

  it("sin la consola (`decide`), la lista se lee como antes, sin mandos", () => {
    const html = renderToStaticMarkup(
      createElement(RadRecommendations, {
        rad: { home: homeWith([recommendation("radiation", "rad-shelter")]) } as unknown as RadiationData,
      }),
    );
    expect(html).toContain("Acción del backend (rad-shelter)");
    expect(html).not.toContain("Adoptar");
  });

  it("un rechazo del backend se dice junto a la fila", async () => {
    const decide = decisions({ adopt: vi.fn(() => Promise.reject(new Error("409 no estaba recomendada"))) });
    const update = vi.fn();
    const found = controls(radBoard([recommendation("radiation", "rad-shelter")], decide), ADOPT_FORM_IDLE, update);
    (button(found, "Adoptar").onClick as () => void)();
    await flush();
    const states = update.mock.calls.map(([change]) => (change as (s: AdoptFormState) => AdoptFormState)(ADOPT_FORM_IDLE));
    expect(states.some((state) => state.error !== null)).toBe(true);
  });
});

describe("Aislamiento: no adoptar, con su motivo", () => {
  const item = recommendation("behavioral", "beh-sleep-hygiene");

  it("«No adoptar» abre el motivo; sin motivo no se firma", () => {
    const decide = decisions();
    const update = vi.fn();
    const found = controls(isoBoard([item], decide), ADOPT_FORM_IDLE, update);
    (button(found, "No adoptar").onClick as () => void)();
    const opened = (update.mock.calls[0]?.[0] as (s: AdoptFormState) => AdoptFormState)(ADOPT_FORM_IDLE);
    expect(opened.declining).toBe(true);
    const form = controls(isoBoard([item], decide), opened);
    expect(button(form, "No adoptar").disabled).toBe(true);
    expect(decide.decline).not.toHaveBeenCalled();
  });

  it("con motivo, firmar llama a la acción con la contramedida, quien firma y el motivo", () => {
    const decide = decisions();
    const found = controls(isoBoard([item], decide), { ...ADOPT_FORM_IDLE, declining: true, reason: "  sin tiempo hoy " });
    const form = found.find((entry) => entry.tag === "form");
    expect(form).toBeDefined();
    const preventDefault = vi.fn();
    (form?.props.onSubmit as (event: FormEvent) => void)({ preventDefault } as unknown as FormEvent);
    expect(preventDefault).toHaveBeenCalled();
    expect(decide.decline).toHaveBeenCalledWith("beh-sleep-hygiene", "CDR", "sin tiempo hoy");
    expect(decide.adopt).not.toHaveBeenCalled();
  });

  it("tras releer, la nota de lo decidido es el texto del backend y se puede adoptar después", () => {
    const decided = recommendation("behavioral", "beh-sleep-hygiene", {
      decision: { text: "No adoptada (CDR): sin tiempo hoy.", meaning: "No retira la recomendación." },
    } as unknown as Partial<Recommendation>);
    const decide = decisions();
    const html = renderToStaticMarkup(isoBoard([decided], decide));
    expect(html).toContain("No adoptada (CDR): sin tiempo hoy.");
    const found = controls(isoBoard([decided], decide), ADOPT_FORM_IDLE);
    (button(found, "Adoptar").onClick as () => void)();
    expect(decide.adopt).toHaveBeenCalledWith("beh-sleep-hygiene", "CDR");
  });
});

describe("el formulario va con su tripulante y su contramedida", () => {
  it("otra contramedida en el mismo hueco u otro tripulante dan otro formulario (otra `key`)", () => {
    const keyOf = (item: Recommendation, subject: string) =>
      (AdoptControls({ item, decide: decisions({ subject }) }) as ReactElement).key;
    const a = recommendation("behavioral", "beh-a");
    expect(keyOf(a, "CM-1")).toBe(keyOf(a, "CM-1"));
    expect(keyOf(a, "CM-1")).not.toBe(keyOf(recommendation("behavioral", "beh-b"), "CM-1"));
    expect(keyOf(a, "CM-1")).not.toBe(keyOf(a, "CM-2"));
  });

  it("con la privacidad, los mandos salen del foco y del lector", () => {
    const html = renderToStaticMarkup(radBoard([recommendation("radiation", "rad-shelter")], decisions({ privacy: true })));
    expect(html).toMatch(/class="adopt-controls" inert=""/);
  });
});

describe("Gravedad: solo lo recomendado se decide", () => {
  it("las contramedidas de la biblioteca (sin recomendación) no llevan mandos", () => {
    const grav = {
      home: homeWith([]),
      risks: {
        state: "ready",
        value: [{ countermeasures: { items: [{ id: "ex-ared", action: "Ejercicio", family_display: null }] } }],
      },
    } as unknown as GravityData;
    expect(controls(createElement(GravExercises, { grav, decide: decisions() }), ADOPT_FORM_IDLE)).toEqual([]);
  });

  it("una recomendación de su dominio sí, con la misma acción", () => {
    const grav = { home: homeWith([recommendation("musculoskeletal", "msk-resistive")]), risks: { state: "loading" } } as unknown as GravityData;
    const decide = decisions();
    const found = controls(createElement(GravExercises, { grav, decide }), ADOPT_FORM_IDLE);
    (button(found, "Adoptar").onClick as () => void)();
    expect(decide.adopt).toHaveBeenCalledWith("msk-resistive", "CDR");
  });
});
