import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { CrewStatus, Followup } from "../lib/api";
import { UNKNOWN_MARK, UNKNOWN_PICTOGRAM } from "../lib/marks";
import { measureOf } from "./cardFixture";
import { OUTCOME_MARKS, STATE_PICTOGRAMS, outcomeMark, stateLabel, statePictogram } from "./followups";
import { FollowupsPanel } from "./FollowupsPanel";
import { markedHtml, taggedPictogram, textLines } from "./visibleText";

/**
 * El panel de seguimiento, pintado (§5.32.5): cada estado con su pictograma junto a la palabra,
 * el dominio con su dibujo, la evaluacion con la flecha de su resultado, y ningun color de alerta.
 * Los textos son los del backend; aqui solo se comprueba que el dibujo los acompana.
 */

const followup = (over: Partial<Followup> = {}): Followup => ({
  adoption_index: 7,
  countermeasure: measureOf({ domain: "behavioral" }),
  domain: "behavioral",
  level_at_adoption: "concern",
  adopted_at: "2026-12-02T08:00:00+00:00",
  adopted_by: "CDR",
  window_ends: "2026-12-04T08:00:00+00:00",
  state: "in_window",
  repeated_checks: [],
  evaluation: null,
  closed_by: null,
  closed_reason: null,
  ...over,
});

// La referencia del estado cae a mitad de la ventana del seguimiento de ejemplo (del día 2 al 4).
const render = (items: Followup[]): string =>
  renderToStaticMarkup(
    createElement(FollowupsPanel, {
      status: {
        followups: items,
        mission: { start: "2026-12-01" },
        data: { reference_time: "2026-12-03T08:00:00+00:00" },
      } as unknown as CrewStatus,
      operator: "CDR",
      onClose: async () => {},
    }),
  );

describe("el estado del seguimiento", () => {
  it("en ventana es «en curso», listo para revisar el triangulo de avance y cerrado la marca de hecho", () => {
    expect(STATE_PICTOGRAMS).toEqual({ in_window: "refresh", due: "play", closed: "check" });
    expect(render([followup()])).toMatch(markedHtml("refresh", "en ventana</span>"));
    expect(render([followup({ state: "due" })])).toMatch(markedHtml("play", "listo para revisar</span>"));
    const closed = render([followup({ state: "closed", closed_by: "CDR", closed_reason: "resuelto" })]);
    expect(closed).toMatch(markedHtml("check", "cerrado</span>"));
    expect(closed).toContain("por CDR: resuelto");
    expect(closed).not.toContain("Cerrar seguimiento");
  });

  it("un estado que esta version no conoce sale con su clave y el dibujo de «desconocido»", () => {
    expect(statePictogram("paused")).toBe(UNKNOWN_PICTOGRAM);
    expect(stateLabel("paused")).toBe("paused");
    const html = render([followup({ state: "paused" as unknown as Followup["state"] })]);
    expect(html).toMatch(markedHtml("dot-small", "paused</span>"));
  });

  it("ya no escribe el triangulo como caracter", () => {
    expect(render([followup({ state: "due" })])).not.toContain("▶");
  });

  it("el dominio lleva su dibujo, sin color", () => {
    expect(render([followup()])).toMatch(markedHtml("domain-behavioral", "Conductual</span> · adoptada por CDR"));
  });
});

describe("el resultado de la evaluacion", () => {
  it("sigue la flecha de la trayectoria de la consola: bajar el nivel es mejorar", () => {
    expect(OUTCOME_MARKS.improved.pictogram).toBe("arrow-down-right");
    expect(OUTCOME_MARKS.worsened.pictogram).toBe("arrow-up-right");
    expect(OUTCOME_MARKS.unchanged.pictogram).toBe("dash");
    // Sin medida repetida no hay con que evaluar: dato ausente, en cian.
    expect(OUTCOME_MARKS.no_repeat).toEqual({ pictogram: "ring-dotted", color: "cyan", className: "c-cyan" });
    for (const outcome of ["improved", "worsened", "unchanged"] as const) {
      expect(OUTCOME_MARKS[outcome].color).toBeNull();
    }
    expect(outcomeMark("otro")).toBe(UNKNOWN_MARK);
  });

  it("acompana al texto del backend, que es lo unico que se lee", () => {
    const text = "El dominio Conductual pasó de PREOCUPACIÓN a VIGILANCIA desde que se adoptó.";
    const html = render([followup({ evaluation: { outcome: "improved", text } })]);
    expect(html).toMatch(markedHtml("arrow-down-right", `${text}</span>`));
    expect(textLines(html)).toContain(text);
    const missing = render([
      followup({ evaluation: { outcome: "no_repeat", text: "No se ha repetido la medida." } }),
    ]);
    expect(missing).toMatch(markedHtml("ring-dotted", "No se ha repetido la medida.</span>", "cyan"));
  });

  it("ningun color de alerta en el panel: un seguimiento no es una alarma", () => {
    const html = render([
      followup({ evaluation: { outcome: "worsened", text: "Empeoró." } }),
      followup({ adoption_index: 8, state: "due", evaluation: { outcome: "no_repeat", text: "Sin medida." } }),
    ]);
    expect(html).not.toMatch(/\bc-(red|yellow)\b/);
  });

  it("el titulo lleva la lupa y el mando de cerrar la marca de «dar por bueno» (§5.33.5)", () => {
    const html = render([followup()]);
    expect(html).toMatch(taggedPictogram("h2", "magnifier", "Seguimiento</h2>"));
    expect(html).toMatch(
      taggedPictogram("button", "check", "Cerrar seguimiento</button>", ' class="command" type="submit" disabled=""'),
    );
  });

  it("sin seguimientos no pinta nada", () => {
    expect(render([])).toBe("");
  });
});

describe("las piezas del tablero (2026-11-07): recuento por estado y avance de la ventana", () => {
  const three = [
    followup(),
    followup({ adoption_index: 8, state: "due" }),
    followup({ adoption_index: 9, state: "closed", closed_by: "CDR", closed_reason: "resuelto" }),
  ];

  it("una píldora por estado presente, con su pictograma, su palabra y su cifra, en el orden de la tabla", () => {
    const html = render(three);
    const tally = /<ul class="board-tally" aria-label="Seguimientos por estado">([\s\S]*?)<\/ul>/.exec(html)?.[1] ?? "";
    expect(textLines(tally)).toEqual(["en ventana 1", "listo para revisar 1", "cerrado 1"]);
    expect(tally).toMatch(markedHtml("refresh", "en ventana</span>"));
    expect(tally).toMatch(markedHtml("play", "listo para revisar</span>"));
    expect(tally).toMatch(markedHtml("check", "cerrado</span>"));
    // Solo los estados que hay: con dos en ventana, una píldora que cuenta dos.
    const two = render([followup(), followup({ adoption_index: 8 })]);
    expect(textLines(/<ul class="board-tally"[^>]*>([\s\S]*?)<\/ul>/.exec(two)?.[1] ?? "")).toEqual(["en ventana 2"]);
  });

  it("el medidor de la ventana va rotulado con las dos fechas de la fila y a medio camino en la referencia", () => {
    const html = render([followup()]);
    expect(html).toContain(
      'role="meter" aria-label="Avance de la ventana de observación: de MET 1/08:00:00 a MET 3/08:00:00" aria-valuemin="0" aria-valuemax="48" aria-valuenow="24"',
    );
    expect(html).toContain('class="meter-fill" style="width:50%"');
    // Las fechas de la fila siguen escritas: el medidor no las sustituye.
    expect(textLines(html).join(" ")).toContain("adoptada por CDR en MET 1/08:00:00 · revisar desde MET 3/08:00:00");
  });

  it("acotado a la escala: una ventana ya pasada llena el medidor y una aún no empezada lo deja vacío; sin color", () => {
    const past = render([followup({ adopted_at: "2026-12-01T08:00:00+00:00", window_ends: "2026-12-02T08:00:00+00:00", state: "due" })]);
    expect(past).toContain('aria-valuemax="24" aria-valuenow="24"');
    expect(past).toContain('style="width:100%"');
    expect(past).not.toContain("meter-oor");
    const ahead = render([followup({ adopted_at: "2026-12-05T08:00:00+00:00", window_ends: "2026-12-06T08:00:00+00:00" })]);
    expect(ahead).toContain('aria-valuenow="0"');
    expect(ahead).toContain('style="width:0%"');
    expect(past + ahead).not.toMatch(/\bc-(red|yellow|cyan|gray)\b/);
  });

  it("un seguimiento cerrado o con la ventana al revés no lleva medidor", () => {
    expect((render(three).match(/role="meter"/g) ?? []).length).toBe(2);
    const reversed = render([followup({ adopted_at: "2026-12-04T08:00:00+00:00", window_ends: "2026-12-02T08:00:00+00:00" })]);
    expect(reversed).not.toContain('role="meter"');
  });
});

describe("con qué reglas se firmaron la adopción y el cierre (§5.39.9)", () => {
  const same = { rules_version: "reglas@abc", same_as_today: true, text: "decidido con reglas@abc; misma versión que hoy" };
  const none = { rules_version: null, same_as_today: null, text: "sin versión registrada: el asiento no la lleva" };

  it("la frase del backend va junto a la adopción y junto al cierre, tal cual y sin color", () => {
    const html = render([
      followup({ state: "closed", closed_by: "CDR", closed_reason: "resuelto", adoption_rules: none, closure_rules: same }),
    ]);
    const text = textLines(html).join(" ");
    expect(text).toContain(`revisar desde MET 3/08:00:00 · ${none.text}`);
    expect(text).toContain(`por CDR: resuelto · ${same.text}`);
    expect(html).not.toMatch(/\bc-(red|yellow|cyan)\b/);
  });

  it("una adopción abierta lleva la de su adopción y nada del cierre", () => {
    const html = render([followup({ adoption_rules: same, closure_rules: null })]);
    expect(textLines(html).join(" ")).toContain(same.text);
    expect(html.match(/decidido con/g)).toHaveLength(1);
  });

  it("un seguimiento sin la frase (una versión anterior del backend) se pinta como antes", () => {
    expect(render([followup()])).not.toContain("decidido con");
  });
});
