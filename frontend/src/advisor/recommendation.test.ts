import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ApiError, type Countermeasure, type Recommendation } from "../lib/api";
import { REFUSED_MARK, UNKNOWN_PICTOGRAM, requestOutcome } from "../lib/marks";
import { CONTRAINDICATIONS_PICTOGRAM } from "./library";
import { RecommendationCard } from "./RecommendationCard";
import { RequestWarning } from "./RequestWarning";
import {
  BASIS_PICTOGRAMS,
  basisPictogram,
  contraindicationsLine,
  decisionNote,
  declineState,
  DECLINE_REASON_MAX,
  priorPictogram,
  resourcesLine,
  URGENCY_PICTOGRAMS,
  urgencyPictogram,
} from "./recommendation";
import { markedHtml, pictogramSvg, taggedPictogram } from "./visibleText";

/**
 * La tercera accion de la tarjeta («no adoptar») y lo que ahora no se calla. La tarjeta se pinta
 * de verdad, a HTML estatico, para comprobar que los textos son los del backend y que decir que
 * no no hace desaparecer la recomendacion.
 */

const PENDING = "sin contraindicaciones escritas: pendiente de revisión médica";

const measure = (override: Partial<Countermeasure> = {}): Countermeasure => ({
  id: "bh-protect-sleep",
  scope: "crew",
  domain: "behavioral",
  ridge: "isolation",
  ridge_display: "Aislamiento y confinamiento",
  action: "Proteger el periodo de sueño.",
  indication: "Pérdida de sueño.",
  resources: ["planificación del turno"],
  resources_note: null,
  crew_time_minutes: null,
  crew_time_basis: "sin fuente",
  protocol_ref: null,
  followup_checks: ["sleep-duration"],
  followup_checks_display: ["Duración del sueño"],
  followup_window_hours: 48,
  followup_basis: "diseño EMMA: dos periodos de sueño",
  contraindications_note: null,
  contraindications_display: PENDING,
  adverse_effects_note: null,
  basis: "demo",
  ...override,
});

const DECISION_TEXT = "Se decidió no adoptarla el 2026-12-10 12:00 UTC (CDR): el turno no lo admite";
const DECISION_MEANING = "Es el registro de una decisión humana, no una evaluación.";

const recommendation = (override: Partial<Recommendation> = {}): Recommendation => ({
  domain: "behavioral",
  action: "Proteger el periodo de sueño.",
  rationale: "Sueño por debajo de lo habitual.",
  urgency: "soon",
  notify_ground: false,
  evidence: [],
  countermeasure: measure(),
  decision: null,
  ...override,
});

const declined = (): Recommendation =>
  recommendation({
    decision: {
      action: "declined",
      ledger_index: 41,
      decided_at: "2026-12-10T12:00:00+00:00",
      decided_by: "CDR",
      reason: "el turno no lo admite",
      text: DECISION_TEXT,
      meaning: DECISION_MEANING,
    },
  });

/** Lo que manda un backend anterior a este cambio: el campo no viene. */
function without<T extends object, K extends keyof T>(value: T, key: K): T {
  const copy = { ...value };
  delete copy[key];
  return copy;
}

const noop = async () => {};
const render = (props: Parameters<typeof RecommendationCard>[0]) =>
  renderToStaticMarkup(createElement(RecommendationCard, props));

describe("declineState", () => {
  const base = { hasHandler: true, adopted: false, operator: "CDR", reason: "motivo", busy: false };

  it("firma solo con quien decide y con un motivo que no sea blanco", () => {
    expect(declineState(base)).toEqual({ offered: true, ready: true, missing: null });
    expect(declineState({ ...base, reason: "   " }).ready).toBe(false);
    expect(declineState({ ...base, reason: "" }).missing).toMatch(/motivo/);
    expect(declineState({ ...base, operator: "  " }).ready).toBe(false);
    expect(declineState({ ...base, operator: "" }).missing).toMatch(/quién está en consola/);
  });

  it("no se ofrece sobre lo que ya se esta siguiendo, ni sin a quien llamar", () => {
    expect(declineState({ ...base, adopted: true })).toEqual({
      offered: false,
      ready: false,
      missing: null,
    });
    expect(declineState({ ...base, hasHandler: false }).offered).toBe(false);
  });

  it("mientras se firma no se firma otra vez", () => {
    expect(declineState({ ...base, busy: true })).toEqual({
      offered: true,
      ready: false,
      missing: null,
    });
  });

  it("el tope del motivo es el de la API", () => {
    expect(DECLINE_REASON_MAX).toBe(500);
  });
});

describe("lo que la tarjeta ya no calla", () => {
  it("los recursos, o lo que la entrada declara cuando no lista ninguno", () => {
    expect(resourcesLine(measure({ resources: ["ecógrafo", "operador"] }))).toBe(
      "ecógrafo · operador",
    );
    expect(resourcesLine(measure({ resources: [], resources_note: "no requiere recursos" }))).toBe(
      "no requiere recursos",
    );
    // Un backend anterior no manda la nota: no se inventa.
    expect(resourcesLine(without(measure({ resources: [] }), "resources_note"))).toBeNull();
  });

  it("la contraindicacion es el texto del backend, y dice si esta pendiente", () => {
    expect(contraindicationsLine(measure())).toEqual({ text: PENDING, pending: true });
    expect(
      contraindicationsLine(
        measure({ contraindications_note: "escrita", contraindications_display: "escrita" }),
      ),
    ).toEqual({ text: "escrita", pending: false });
    expect(contraindicationsLine(without(measure(), "contraindications_display"))).toBeNull();
  });

  it("la nota de lo decidido solo existe si el backend la da", () => {
    expect(decisionNote(recommendation())).toBeNull();
    expect(decisionNote(without(recommendation(), "decision"))).toBeNull();
    expect(decisionNote(declined())).toEqual({ text: DECISION_TEXT, meaning: DECISION_MEANING });
  });
});

describe("los pictogramas de la tarjeta (§5.32.5)", () => {
  it("la urgencia lleva uno, dos o tres galones junto a su palabra", () => {
    expect(URGENCY_PICTOGRAMS).toEqual({
      routine: "chevron-right",
      soon: "chevrons-right-double",
      immediate: "chevrons-right-triple",
    });
    for (const [urgency, word] of [["routine", "Rutina"], ["soon", "Pronto"], ["immediate", "Inmediata"]] as const) {
      const html = render({ item: recommendation({ urgency }) });
      expect(html).toMatch(markedHtml(URGENCY_PICTOGRAMS[urgency], `urgencia ${word}</span>`));
    }
    expect(urgencyPictogram("otra")).toBe(UNKNOWN_PICTOGRAM);
  });

  it("el dominio va con su dibujo, sin color: nombrar no es avisar", () => {
    const html = render({ item: recommendation() });
    expect(html).toMatch(markedHtml("domain-behavioral", "Conductual</span>"));
  });

  it("el respaldo: una hoja si hay documento, el guion de «no aplica» si es demo", () => {
    expect(BASIS_PICTOGRAMS).toEqual({ "evidence-backed": "sheet-lines", demo: "dash" });
    expect(basisPictogram("otro")).toBe(UNKNOWN_PICTOGRAM);
    const demo = render({ item: recommendation() });
    expect(demo).toMatch(markedHtml("dash", "demo: solo la respalda el riesgo del dominio</span>"));
    expect(demo).toMatch(markedHtml("ridge-isolation", "RIDGE: Aislamiento y confinamiento</span>"));
  });

  it("la respuesta previa: guion sin adopciones, en curso si sigue abierta, hecho si se cerro", () => {
    expect(priorPictogram("none")).toBe("dash");
    expect(priorPictogram("open")).toBe("refresh");
    expect(priorPictogram("closed")).toBe("check");
    expect(priorPictogram("otro")).toBe(UNKNOWN_PICTOGRAM);
  });
});

describe("RecommendationCard", () => {
  it("ofrece las dos decisiones y pinta la contraindicacion pendiente", () => {
    const html = render({
      item: recommendation(),
      operator: "CDR",
      onAdopt: noop,
      onDecline: noop,
    });
    expect(html).toContain("Adoptar y seguir");
    expect(html).toContain("No adoptar");
    expect(html).toContain('aria-label="Motivo de no adoptarla"');
    expect(html).toContain(`maxLength="${DECLINE_REASON_MAX}"`);
    expect(html).toMatch(taggedPictogram("dt", CONTRAINDICATIONS_PICTOGRAM, "Contraindicaciones</dt>"));
    expect(html).toContain(PENDING);
    // Sin motivo escrito no se puede firmar. Los dos mandos con su signo (§5.33.5): la marca de
    // «dar algo por bueno» y el circulo tachado de «no».
    expect(html).toMatch(
      new RegExp(`<button class="command" type="submit" disabled=""[^>]*>${pictogramSvg("slash-circle")}No adoptar</button>`),
    );
    expect(html).toMatch(taggedPictogram("button", "check", "Adoptar y seguir</button>", ' class="command"'));
    // El motivo con el bocadillo de «lo que alguien dice», y el respaldo con el libro de la fuente.
    expect(html).toMatch(markedHtml("bubble-lines", "Motivo: "));
    expect(html).toMatch(taggedPictogram("dt", "book-open", "Respaldo</dt>"));
  });

  it("una recomendacion que se decidio no adoptar sigue ahi, con la nota del backend", () => {
    const html = render({ item: declined(), operator: "CDR", onAdopt: noop, onDecline: noop });
    expect(html).toContain("Proteger el periodo de sueño.");
    expect(html).toContain(DECISION_TEXT);
    expect(html).toContain(DECISION_MEANING);
    // Pictograma ademas de texto, y ningun color de alerta: no es una alarma ni la apaga.
    expect(html).toMatch(markedHtml("slash-circle", "Se decidió no adoptarla"));
    expect(html).not.toContain("⊘");
    expect(html).not.toMatch(/c-(red|yellow|orange|green)/);
    // Se puede cambiar de opinion: adoptar sigue ofrecido.
    expect(html).toContain("Adoptar y seguir");
    expect(html).toContain("No adoptar");
  });

  it("sobre lo que se esta siguiendo no se ofrece decir que no", () => {
    const html = render({
      item: recommendation(),
      operator: "CDR",
      adopted: true,
      onAdopt: noop,
      onDecline: noop,
    });
    expect(html).toContain("Adoptada: en seguimiento");
    expect(html).not.toContain("No adoptar");
  });

  it("donde no se le da la accion, la tarjeta no la ofrece", () => {
    const html = render({ item: recommendation(), operator: "CDR", onAdopt: noop });
    expect(html).toContain("Adoptar y seguir");
    expect(html).not.toContain("No adoptar");
  });

  it("una entrada sin recursos dice por que, y una contraindicacion escrita se lee entera", () => {
    const html = render({
      item: recommendation({
        countermeasure: measure({
          resources: [],
          resources_note: "no requiere recursos",
          contraindications_note: "texto de la revisión médica",
          contraindications_display: "texto de la revisión médica",
        }),
      }),
    });
    expect(html).toMatch(taggedPictogram("dt", "cube", "Recursos</dt><dd>no requiere recursos</dd>"));
    expect(html).toMatch(
      taggedPictogram("dt", CONTRAINDICATIONS_PICTOGRAM, "Contraindicaciones</dt><dd>texto de la revisión médica</dd>"),
    );
  });
});

describe("RequestWarning", () => {
  it("un rechazo del backend: el triangulo en amarillo y el texto devuelto, tal cual (§5.33.5)", () => {
    const refused = requestOutcome(new ApiError(409, "ya adoptada"));
    const html = renderToStaticMarkup(createElement(RequestWarning, { outcome: refused }));
    expect(REFUSED_MARK).toEqual({ pictogram: "shape-triangle", color: "yellow", className: "c-yellow" });
    expect(html).toMatch(new RegExp(`^ ${markedHtml("shape-triangle", "ya adoptada</span>", "yellow").source}$`));
  });

  it("una peticion caida (5xx o sin red): la cruz en rojo, no el triangulo (§5.34.14)", () => {
    for (const reason of [new ApiError(500, "ROTO"), new TypeError("Failed to fetch")]) {
      const html = renderToStaticMarkup(createElement(RequestWarning, { outcome: requestOutcome(reason) }));
      expect(html).toMatch(/<span class="mark c-red"><svg [^>]*data-pictogram="cross"/);
      expect(html).not.toContain("c-yellow");
    }
  });
});
