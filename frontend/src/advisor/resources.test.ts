import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
// Sin los `data-ui` del asistente: estas pruebas miran el marcado del panel.
import { renderToStaticMarkup } from "../assistant/staticMarkup";
import { describe, expect, it } from "vitest";

import { isPictogramName } from "../icons";
import type { Countermeasure, Recommendation, ResourceRow, ResourceStatus } from "../lib/api";
import { UNKNOWN_MARK } from "../lib/marks";
import { TEXT_TOKENS } from "../lib/palette";
import { RecommendationCard } from "./RecommendationCard";
import {
  EMPTY_FORM,
  canDeclare,
  declarationBody,
  declarationInstant,
  historyRows,
  panelRows,
  resourceKeysWithPictogram,
  resourcePictogram,
  resourceStatus,
  stateMark,
  statusPictogram,
} from "./resources";
import { markedHtml, textNodes } from "./visibleText";

/**
 * Los recursos de a bordo en la interfaz: «sin declarar» nunca se pinta como «disponible», el
 * color no va solo, los textos son los del backend y el aviso no quita la recomendacion. Y desde
 * el rediseno pictografico (§5.32.5): cada estado con su pictograma SVG, cada recurso del
 * vocabulario con el dibujo de su familia, y ninguno de los dos sin su palabra.
 */

const LABEL = "declarado por una persona; EMMA no lleva inventario";
const CAVEAT =
  "Sin declarar no es disponible: de un recurso del que nadie ha declarado nada, EMMA no sabe " +
  "si está a bordo ni si funciona. La contramedida se ofrece igual: si se puede hacer lo valora " +
  "una persona.";

/** El vocabulario del backend: la interfaz no tiene uno propio. */
const vocabulary = JSON.parse(
  readFileSync(
    fileURLToPath(new URL("../../../backend/app/data/resources.json", import.meta.url)),
    "utf-8",
  ),
) as { resources: { key: string; name: string }[] };

const row = (over: Partial<ResourceRow> = {}): ResourceRow => ({
  key: "ultrasound-scanner",
  name: "ecógrafo",
  state: "undeclared",
  state_display: "sin declarar",
  since: null,
  note: null,
  declared_by: null,
  ledger_index: null,
  recorded: null,
  ...over,
});

const status = (over: Partial<ResourceStatus> = {}): ResourceStatus => ({
  state: "some-unavailable",
  label: LABEL,
  items: [
    {
      ...row({
        state: "unavailable",
        state_display: "declarado no disponible",
        since: "2026-12-08T12:00:00+00:00",
        note: "sonda averiada",
        declared_by: "CDR",
        ledger_index: 40,
      }),
      description: "ecógrafo",
    },
    { ...row({ key: "trained-operator", name: "operador entrenado" }), description: "operador entrenado" },
  ],
  unavailable: ["ecógrafo"],
  undeclared: ["operador entrenado"],
  text: "Consta como no disponible: ecógrafo. Sin declarar: operador entrenado.",
  caveat: CAVEAT,
  ...over,
});

const measure: Countermeasure = {
  id: "sans-repeat-both-eyes",
  scope: "crew",
  domain: "sans",
  ridge: "gravity",
  ridge_display: "Campos de gravedad",
  action: "Repetir la ecografía en ambos ojos.",
  indication: "i",
  resources: ["ecógrafo", "operador entrenado"],
  resources_note: null,
  crew_time_minutes: null,
  crew_time_basis: "sin fuente",
  protocol_ref: null,
  followup_checks: [],
  followup_checks_display: [],
  followup_window_hours: 48,
  followup_basis: "diseño EMMA",
  contraindications_note: null,
  contraindications_display: "pendiente",
  adverse_effects_note: null,
  basis: "demo",
};

const recommendation = (over: Partial<Recommendation> = {}): Recommendation => ({
  domain: "sans",
  action: "Repetir la ecografía en ambos ojos.",
  rationale: "r",
  urgency: "soon",
  notify_ground: false,
  evidence: [],
  countermeasure: measure,
  decision: null,
  resource_status: status(),
  ...over,
});

const noop = async () => {};
const render = (item: Recommendation) =>
  renderToStaticMarkup(
    createElement(RecommendationCard, { item, operator: "CDR", onAdopt: noop, onDecline: noop }),
  );

describe("la marca de cada estado", () => {
  it("sin declarar es dato ausente (cian, anillo punteado), nunca la marca de disponible", () => {
    expect(stateMark("undeclared")).toEqual({ pictogram: "ring-dotted", color: "cyan", className: "c-cyan" });
    expect(stateMark("undeclared")).not.toEqual(stateMark("available"));
    expect(stateMark("available")).toEqual({ pictogram: "check", color: "text", className: "c-text" });
  });

  it("no disponible va en el gris de la tabla F.5-1, no en un color de alerta", () => {
    expect(stateMark("unavailable")).toEqual({ pictogram: "slash-circle", color: "gray", className: "c-gray" });
    for (const state of ["available", "unavailable", "undeclared"]) {
      expect(["red", "yellow"]).not.toContain(stateMark(state).color);
    }
  });

  it("el color nunca va solo: cada estado tiene su pictograma, y todo token es de texto", () => {
    const marks = ["available", "unavailable", "undeclared"].map(stateMark);
    expect(new Set(marks.map((mark) => mark.pictogram)).size).toBe(3);
    for (const mark of marks) {
      expect(TEXT_TOKENS as readonly string[]).toContain(mark.color);
      expect(mark.className).toBe(`c-${mark.color}`);
    }
  });

  it("un estado desconocido no se disfraza de otro", () => {
    expect(stateMark("en-camino")).toBe(UNKNOWN_MARK);
    expect(stateMark("en-camino")).toEqual({ pictogram: "dot-small", color: "text", className: "c-text" });
  });

  it("el bloque lleva la forma del peor estado presente, la misma que lleva ese estado en su fila", () => {
    expect(statusPictogram("some-unavailable")).toBe(stateMark("unavailable").pictogram);
    expect(statusPictogram("some-undeclared")).toBe(stateMark("undeclared").pictogram);
    expect(statusPictogram("all-available")).toBe(stateMark("available").pictogram);
    expect(statusPictogram("none-required")).toBe("dash");
    expect(statusPictogram("otro")).toBe(UNKNOWN_MARK.pictogram);
  });
});

describe("el dibujo de familia de cada recurso", () => {
  it("todo el vocabulario del backend tiene dibujo, y ninguna clave sobra", () => {
    const keys = vocabulary.resources.map((item) => item.key);
    expect([...resourceKeysWithPictogram()].sort()).toEqual([...keys].sort());
    for (const key of keys) {
      const name = resourcePictogram(key);
      expect(isPictogramName(name), `${key}: «${name}»`).toBe(true);
      expect(name, key).not.toBe(UNKNOWN_MARK.pictogram);
    }
  });

  it("agrupa por familia: las masas de blindaje, los sensores y las personas comparten dibujo", () => {
    expect(resourcePictogram("shielded-area")).toBe(resourcePictogram("module-with-more-shielding-mass"));
    expect(resourcePictogram("same-sensor")).toBe(resourcePictogram("second-co2-sensor-or-portable-analyzer"));
    expect(resourcePictogram("trained-operator")).toBe(resourcePictogram("onboard-physician"));
    // El agua potable y la recogida de orina no se confunden.
    expect(resourcePictogram("onboard-drinking-water")).not.toBe(resourcePictogram("urine-24h-collection"));
  });

  it("una clave que esta version no conoce sale con el dibujo de «desconocido»", () => {
    expect(resourcePictogram("ultrasound-gel")).toBe(UNKNOWN_MARK.pictogram);
  });
});

describe("lo que se pinta junto a una recomendacion", () => {
  it("cada recurso con el texto y la palabra del backend, y su marca", () => {
    const view = resourceStatus(recommendation());
    expect(view).not.toBeNull();
    expect(view?.label).toBe(LABEL);
    expect(view?.text).toBe("Consta como no disponible: ecógrafo. Sin declarar: operador entrenado.");
    expect(view?.caveat).toBe(CAVEAT);
    expect(view?.statusPictogram).toBe("slash-circle");
    expect(view?.lines).toEqual([
      {
        key: "ultrasound-scanner",
        state: "unavailable",
        description: "ecógrafo",
        pictogram: "probe-arcs",
        stateDisplay: "declarado no disponible",
        mark: stateMark("unavailable"),
        note: "sonda averiada",
      },
      {
        key: "trained-operator",
        state: "undeclared",
        description: "operador entrenado",
        pictogram: "person",
        stateDisplay: "sin declarar",
        mark: stateMark("undeclared"),
        note: null,
      },
    ]);
  });

  it("sin bloque, sin recursos o sin rotulo no se pinta nada: no se inventa", () => {
    expect(resourceStatus(recommendation({ resource_status: null }))).toBeNull();
    const absent = recommendation();
    delete absent.resource_status;
    expect(resourceStatus(absent)).toBeNull();
    expect(
      resourceStatus(recommendation({ resource_status: status({ items: [], state: "none-required" }) })),
    ).toBeNull();
    expect(resourceStatus(recommendation({ resource_status: status({ label: "  " }) }))).toBeNull();
  });

  it("la tarjeta lo pinta con pictograma, palabra y rotulo, y la recomendacion sigue ahi", () => {
    const html = render(recommendation());
    expect(html).toContain("Repetir la ecografía en ambos ojos.");
    expect(html).toContain("Adoptar y seguir");
    expect(html).toContain(LABEL);
    expect(html).toMatch(markedHtml("slash-circle", "declarado no disponible</span>", "gray"));
    expect(html).toMatch(markedHtml("ring-dotted", "sin declarar</span>", "cyan"));
    expect(html).toContain("sonda averiada");
    expect(html).toContain("Consta como no disponible: ecógrafo. Sin declarar: operador entrenado.");
    expect(html).toContain("La contramedida se ofrece igual");
    // Ningun color de alerta en el aviso: no es una alarma.
    const block = html.slice(html.indexOf("Recursos a bordo"), html.indexOf("Adoptar y seguir"));
    expect(block).not.toMatch(/c-(red|yellow)/);
  });

  it("cada recurso lleva el dibujo de su familia junto a su nombre, y el bloque la forma del peor estado", () => {
    const html = render(recommendation());
    expect(html).toMatch(markedHtml("probe-arcs", "ecógrafo</span>"));
    expect(html).toMatch(markedHtml("person", "operador entrenado</span>"));
    expect(html).toMatch(markedHtml("slash-circle", "Recursos a bordo</span>"));
    expect(html).toContain('<summary class="lead"><span class="mark"><svg');
    // El dibujo nunca va solo: la palabra del backend es el unico texto de cada fila.
    const row = html.slice(html.indexOf("<li>"), html.indexOf("</li>"));
    expect(textNodes(row)).toEqual(["ecógrafo", "·", "declarado no disponible", "· sonda averiada"]);
  });

  it("con todo declarado disponible no hay advertencia, y sin bloque la tarjeta no cambia", () => {
    const available = status({
      state: "all-available",
      items: [
        { ...row({ state: "available", state_display: "declarado disponible" }), description: "ecógrafo" },
      ],
      unavailable: [],
      undeclared: [],
      text: "Todos los recursos que pide constan declarados disponibles.",
      caveat: null,
    });
    const html = render(recommendation({ resource_status: available }));
    expect(html).toMatch(markedHtml("check", "declarado disponible</span>", "text"));
    expect(html).toMatch(markedHtml("check", "Recursos a bordo</span>"));
    expect(html).not.toContain("Sin declarar no es disponible");
    expect(render(recommendation({ resource_status: null }))).not.toContain("Recursos a bordo");
  });
});

describe("el panel de declaracion", () => {
  const overview = {
    resources: vocabulary.resources.map((item, index) => ({
      ...row({
        key: item.key,
        name: item.name,
        ...(index === 3
          ? { state: "available" as const, state_display: "declarado disponible" }
          : index === 5
            ? { state: "unavailable" as const, state_display: "declarado no disponible" }
            : {}),
      }),
      declarations: 0,
      used_by: ["x"],
    })),
  };

  it("ensena todo el vocabulario del backend: primero lo que falta, al final lo sin declarar", () => {
    const rows = panelRows(overview);
    expect(rows).toHaveLength(vocabulary.resources.length);
    expect(rows[0]?.resource.key).toBe(vocabulary.resources[5]?.key);
    expect(rows[1]?.resource.key).toBe(vocabulary.resources[3]?.key);
    expect(rows.slice(2).every((item) => item.resource.state === "undeclared")).toBe(true);
    expect(rows.slice(2).every((item) => item.mark.color === "cyan")).toBe(true);
    // Cada fila lleva el dibujo de familia de su recurso.
    for (const item of rows) expect(item.pictogram).toBe(resourcePictogram(item.resource.key));
    // Dentro de cada grupo, el orden del vocabulario.
    expect(rows.slice(2).map((item) => item.resource.key)).toEqual(
      vocabulary.resources.filter((_, index) => index !== 3 && index !== 5).map((item) => item.key),
    );
  });

  it("el historial: cada declaracion con el dibujo de su recurso y la marca del estado declarado", () => {
    const entry = {
      resource: "ared",
      name: "ARED (ejercicio resistivo)",
      state: "unavailable",
      state_display: "declarado no disponible",
      previous_state: "undeclared",
      previous_state_display: "sin declarar",
      changed: true,
      since: "2026-12-08T12:00:00+00:00",
      note: null,
      declared_by: "CDR",
      ledger_index: 40,
      recorded: "2026-12-08T12:00:00+00:00",
    };
    expect(historyRows({ history: [entry] })).toEqual([
      { item: entry, pictogram: "dumbbell", mark: stateMark("unavailable") },
    ]);
  });

  it("firmar exige recurso, estado y quien declara; la nota es opcional", () => {
    const form = { resource: "ared", state: "unavailable", note: "" };
    expect(canDeclare(form, "CDR")).toBe(true);
    expect(canDeclare(EMPTY_FORM, "CDR")).toBe(false);
    expect(canDeclare({ ...form, resource: "" }, "CDR")).toBe(false);
    expect(canDeclare({ ...form, state: "" }, "CDR")).toBe(false);
    expect(canDeclare(form, "   ")).toBe(false);
    expect(canDeclare(form, undefined)).toBe(false);
  });

  it("el cuerpo lleva recurso, estado, instante, nota y firma, y ninguna cantidad", () => {
    const body = declarationBody(
      { resource: "ared", state: "unavailable", note: "  cable roto " },
      " CDR ",
      "2026-12-08T12:00:00+00:00",
    );
    expect(body).toEqual({
      resource: "ared",
      state: "unavailable",
      since: "2026-12-08T12:00:00+00:00",
      note: "cable roto",
      declared_by: "CDR",
    });
  });

  it("vale desde el instante de los datos si lo hay; si no, desde ahora", () => {
    const now = new Date("2026-12-10T00:00:00Z");
    expect(declarationInstant("2026-12-08T12:00:00+00:00", now)).toBe("2026-12-08T12:00:00+00:00");
    expect(declarationInstant(null, now)).toBe("2026-12-10T00:00:00.000Z");
  });
});

describe("el mobiliario del asesor y la evidencia, en el codigo (§5.33.5)", () => {
  // El panel de recursos lee la API en un efecto y a HTML estatico no pinta nada, y el fallo de
  // una peticion solo aparece tras una promesa rechazada: lo que se promete se mira en la fuente.
  // Sin comentarios: varios nombran `<details>` o un `<h2>` para explicar el porque.
  const source = (path: string): string =>
    readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf-8")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/(^|[^:"'`\\])\/\/.*$/gm, "$1");
  const FILES = [
    "./FollowupsPanel.tsx",
    "./RecommendationCard.tsx",
    "./RecommendationList.tsx",
    "./RequestWarning.tsx",
    "./ResourcesPanel.tsx",
    "../evidence/EvidenceEntry.tsx",
    "../evidence/EvidenceList.tsx",
    "../evidence/SourceFacts.tsx",
    "../evidence/SourceGrade.tsx",
  ];

  it("el panel de recursos: titulo, plegables y mando con su concepto", () => {
    const code = source("./ResourcesPanel.tsx");
    expect(code).toContain('<PanelTitle concept="resources">');
    expect(code).toMatch(/<Fold\s+(?:data-ui="[^"]+"\s+)?concept="resources"/);
    expect(code).toMatch(/<Fold (?:data-ui="[^"]+" )?concept="howToRead" label="Cómo leerlo">/);
    expect(code).toMatch(/<Fold\s+(?:data-ui="[^"]+"\s+)?concept="history"/);
    expect(code).toContain('<Command concept="declare"');
  });

  it.each(FILES)("%s: ni titulo, ni mando, ni color de aviso sin su pieza", (path) => {
    const code = source(path);
    expect(code).not.toMatch(/<h[234][\s>]/);
    expect(code).not.toMatch(/<button[\s>]/);
    // El color de un estado va en una marca, con su forma: ninguna clase de aviso escrita a mano,
    // ni siquiera compuesta, ni una marca sin dibujo. (El magenta del rotulo de la tarjeta no es
    // un estado: es «lo dirige el sistema», tabla F.5-2.)
    expect(code).not.toMatch(/className=[{"'][^>]*\bc-(yellow|gray|red|cyan|orange|green)\b/);
    expect(code).not.toMatch(/className=\{`[^`]*c-\$\{/);
    expect(code).not.toMatch(/pictogram=\{null\}/);
  });

  it("cada fallo de una peticion pasa por `RequestWarning`, con la marca de lo que fue (§5.34.14)", () => {
    for (const path of ["./FollowupsPanel.tsx", "./RecommendationCard.tsx", "./ResourcesPanel.tsx"]) {
      const code = source(path);
      const shown = code.match(/error !== null && [^\n]*/g) ?? [];
      expect(shown.length, path).toBeGreaterThan(0);
      for (const line of shown) expect(line, path).toContain("<RequestWarning outcome={error} />");
      expect(code, path).toContain("setError(requestOutcome(cause))");
      expect(code, path).not.toContain("String(cause)");
    }
  });

  it("los unicos <details> a mano son los dos cuyo rotulo es un estado (recursos, respuesta previa)", () => {
    for (const path of FILES) {
      const expected = path === "./RecommendationCard.tsx" ? 2 : 0;
      expect(source(path).match(/<details[\s>]/g)?.length ?? 0, path).toBe(expected);
    }
  });
});
