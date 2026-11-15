/**
 * Los mandos de «Aislamiento» (unidad 7 de «que si pulso el botón pasen cosas», 2026-11-15):
 * «Reconocer» en las alertas conductuales firma con la acción de la consola, y cada casilla de
 * «Pruebas cognitivas» abre debajo su consola de registro (la PVT, la suya; las demás, la batería).
 *
 * Sin DOM en la suite (como `HomeBoard.links.test.ts`): se despliega el árbol de elementos llamando
 * a cada componente, con un `useState` de juguete que guarda el estado entre dos «renders» por orden
 * de llamada. Las consolas de registro no se despliegan: basta con ver que se montan, con qué.
 */
import { type ReactElement, type ReactNode, createElement, isValidElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const slots: unknown[] = [];
let cursor = 0;

vi.mock("react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react")>();
  return {
    ...actual,
    useState: (initial: unknown) => {
      const index = cursor++;
      if (!(index in slots)) slots[index] = typeof initial === "function" ? (initial as () => unknown)() : initial;
      const set = (next: unknown) => {
        slots[index] = typeof next === "function" ? (next as (prev: unknown) => unknown)(slots[index]) : next;
      };
      return [slots[index], set];
    },
  };
});

import { CognitionPanel } from "../cognition/CognitionPanel";
import { OperatorInput } from "../components/OperatorInput";
import type { AlertActions } from "../dashboard/AlertRow";
import { PvtPanel } from "../pvt/PvtPanel";
import { ISOLATION_KEYS, IsoAlerts, IsoTests, type IsoAlertControl, type IsolationData } from "./IsolationBoard";

type Props = Record<string, unknown> & { children?: ReactNode };
type Found = { label: string; click: () => void; disabled: boolean };
type Tree = { buttons: Found[]; mounted: ReactElement<Props>[]; text: string };

const NOT_EXPANDED = new Set<unknown>([PvtPanel, CognitionPanel, OperatorInput]);

function textOf(child: ReactNode): string {
  if (typeof child === "string" || typeof child === "number") return String(child);
  if (Array.isArray(child)) return child.map(textOf).join("");
  if (isValidElement(child)) return textOf((child.props as Props).children);
  return "";
}

/** El botón de ese nombre, o la prueba falla: un clic que no encuentra su botón no pasa en silencio. */
function press(tree: Tree, label: string): void {
  const button = tree.buttons.find((item) => item.label === label);
  if (button === undefined) throw new Error(`sin botón «${label}»: ${tree.buttons.map((item) => item.label).join(" | ")}`);
  button.click();
}

/** Un «render»: despliega el árbol, con los botones, las consolas montadas y el texto visible. */
function render(node: ReactElement): Tree {
  cursor = 0;
  const tree: Tree = { buttons: [], mounted: [], text: "" };
  const walk = (child: ReactNode): void => {
    if (typeof child === "string" || typeof child === "number") {
      tree.text += String(child);
      return;
    }
    if (Array.isArray(child)) {
      child.forEach(walk);
      return;
    }
    if (!isValidElement(child)) return;
    const element = child as ReactElement<Props>;
    const { props } = element;
    if (NOT_EXPANDED.has(element.type)) {
      tree.mounted.push(element);
      return;
    }
    if (typeof element.type === "function") {
      walk((element.type as (p: Props) => ReactNode)(props));
      return;
    }
    if (element.type === "button" && typeof props.onClick === "function") {
      const label = typeof props["aria-label"] === "string" ? props["aria-label"] : textOf(props.children);
      tree.buttons.push({ label, click: props.onClick as () => void, disabled: props.disabled === true });
    }
    walk(props.children);
  };
  walk(node);
  return tree;
}

const REFERENCE = Date.parse("2026-11-08T12:00:00Z");
const ready = <T,>(value: T) => ({ state: "ready" as const, value });
const reload = vi.fn();

function isolation(alerts: unknown[]): IsolationData {
  return {
    home: {
      reference: REFERENCE,
      catalog: new Map(),
      status: {
        subject: "crew-01",
        mission: { profile: { display: "" } },
        domains: { behavioral: { level: "watch", score: 0.4, drivers: [], trajectory: null } },
        alerts,
        recommendations: [],
        data: { reference_time: new Date(REFERENCE).toISOString() },
      },
    },
    series: ready(Object.fromEntries(ISOLATION_KEYS.map((key) => [key, []]))),
    energy: ready([]),
    protocol: ready({
      tests: [
        { abbrev: "PVT", sigla: "PVT", name: "Vigilancia psicomotora", recorded_here: false, fields: [], measures: null, measures_note: null },
        {
          abbrev: "DSST",
          sigla: "DSST",
          name: "Sustitución de dígitos",
          recorded_here: true,
          fields: [{ key: "dsst-accuracy", measure: "accuracy" }],
          measures: null,
          measures_note: null,
        },
      ],
    }),
    sessions: ready({ sessions: [], count: 0 }),
    food: ready({ rated: 0, below: 0, statement: "" }),
    correlations: ready({ pairs: [], tested: 0, pairs_basis: "", simulated_text: "" }),
    risk: ready(null),
    habitat: ready({ readings: [] }),
    planner: ready({ members: [], leisure_rule: "" }),
    links: undefined,
    reload,
  } as unknown as IsolationData;
}

function control(operator: string): IsoAlertControl & { actions: { acknowledge: ReturnType<typeof vi.fn> } } {
  const acknowledge = vi.fn(() => Promise.resolve());
  const actions = { acknowledge } as unknown as AlertActions & { acknowledge: typeof acknowledge };
  return { actions, operator, onOperator: vi.fn(), privacy: false };
}

const ALERT = { id: "behavioral:watch", domain: "behavioral", level: "watch", acknowledged: false, acknowledged_by: null, annunciation: "normal" };

beforeEach(() => {
  slots.length = 0;
  reload.mockClear();
});

describe("«Aislamiento»: reconocer una alerta conductual", () => {
  it("«Reconocer» firma con la acción de la consola, con dominio, nivel y quien firma", () => {
    const ctl = control("  CDR ");
    const tree = render(createElement(IsoAlerts, { iso: isolation([ALERT]), control: ctl }));
    expect(tree.buttons.find((item) => item.label === "Reconocer")?.disabled).toBe(false);
    press(tree, "Reconocer");
    expect(ctl.actions.acknowledge).toHaveBeenCalledWith(
      { id: "behavioral:watch", domain: "behavioral", level: "watch", drivers: [] },
      "CDR",
    );
  });

  it("sin nombre de quien firma, el mando está y no firma; el campo del nombre es el de la consola", () => {
    const ctl = control("");
    const tree = render(createElement(IsoAlerts, { iso: isolation([ALERT]), control: ctl }));
    expect(tree.buttons.find((item) => item.label === "Reconocer")?.disabled).toBe(true);
    expect(tree.text).toContain("Para reconocer hace falta el nombre de quien firma:");
    const field = tree.mounted.find((item) => item.type === OperatorInput);
    (field?.props.onChange as (value: string) => void)("FE");
    expect(ctl.onOperator).toHaveBeenCalledWith("FE");
    // Con nombre, el campo ya no se pide.
    expect(render(createElement(IsoAlerts, { iso: isolation([ALERT]), control: control("CDR") })).mounted).toHaveLength(0);
  });

  it("una alerta silenciada no ofrece «Reconocer» (como `AlertRow`: lo suyo es «Habilitar…»)", () => {
    for (const annunciation of ["suppressed", "inhibited"]) {
      const tree = render(createElement(IsoAlerts, { iso: isolation([{ ...ALERT, annunciation }]), control: control("CDR") }));
      expect(tree.buttons.some((item) => item.label === "Reconocer")).toBe(false);
    }
  });

  it("una alerta ya reconocida no lo vuelve a ofrecer; sin acciones de la consola, tampoco", () => {
    const seen = render(createElement(IsoAlerts, { iso: isolation([{ ...ALERT, acknowledged: true, acknowledged_by: "CDR" }]), control: control("CDR") }));
    expect(seen.buttons.some((item) => item.label === "Reconocer")).toBe(false);
    const bare = render(createElement(IsoAlerts, { iso: isolation([ALERT]) }));
    expect(bare.buttons.some((item) => item.label === "Reconocer")).toBe(false);
  });
});

describe("«Aislamiento»: cada prueba cognitiva abre su consola de registro", () => {
  it("la casilla de la batería monta `CognitionPanel`; al registrar, se relee la sección", () => {
    const iso = isolation([]);
    const before = render(createElement(IsoTests, { iso }));
    expect(before.mounted).toHaveLength(0);
    press(before, "Registrar la batería Cognition: Sustitución de dígitos (DSST)");
    const after = render(createElement(IsoTests, { iso }));
    expect(after.mounted.map((item) => item.type)).toEqual([CognitionPanel]);
    expect(after.mounted[0]?.props.subject).toBe("crew-01");
    (after.mounted[0]?.props.onRecorded as () => void)();
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("la casilla de la PVT monta `PvtPanel`; «Cerrar» la quita", () => {
    const iso = isolation([]);
    press(render(createElement(IsoTests, { iso })), "Hacer la prueba PVT: Vigilancia psicomotora");
    const open = render(createElement(IsoTests, { iso }));
    expect(open.mounted.map((item) => item.type)).toEqual([PvtPanel]);
    // Volver a tocar la casilla no la cierra (no tira una prueba a medias); «Cerrar» sí.
    press(open, "Hacer la prueba PVT: Vigilancia psicomotora");
    expect(render(createElement(IsoTests, { iso })).mounted.map((item) => item.type)).toEqual([PvtPanel]);
    press(render(createElement(IsoTests, { iso })), "Cerrar");
    expect(render(createElement(IsoTests, { iso })).mounted).toHaveLength(0);
  });
});
