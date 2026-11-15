import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { Credibility, CredibilityLayer, CredibilityState } from "../lib/api";
import { UNKNOWN_PICTOGRAM } from "../lib/marks";
import { OBSERVATION_TYPES } from "../lib/provenance";
import { CredibilityView } from "./CredibilityView";
import { factorGroups, layerSign } from "./credibility";

/*
 * La credibilidad de cada capa la redacta el backend (`app/evidence/credibility.py`); la consola
 * de Tierra la agrupa y la pliega. Se comprueba que ningún factor se pierde, que el signo de cada
 * capa es el de su tipo y que la vista pinta cada frase tal cual, sin nivel ni color de nivel.
 */

const state = (group: string, id: string): CredibilityState => ({
  group,
  id,
  name_es: `NOMBRE-${id}`,
  state: `ESTADO-${id}`,
});

const layer = (over: Partial<CredibilityLayer> = {}): CredibilityLayer => ({
  id: "trend-projection",
  display: "CAPA-PROYECCION",
  observation_type: "predicted",
  observation_type_text: "PREDICHO",
  model_version: "trend:ols-contexto@1",
  model_note: null,
  sites: ["analysis/trend.py:projection"],
  served_in: ["/api/status → predictions[]"],
  tests: ["tests/test_observation_provenance.py::test_noise_is_never_projected"],
  factors: [state("capability", "validation"), state("results", "uncertainty")],
  criticality: [
    { axis: "decision", name_es: "EJE-DECISION", state: "CRITICIDAD-decision" },
    { axis: "influence", name_es: "EJE-INFLUENCIA", state: "CRITICIDAD-influence" },
  ],
  ...over,
});

const credibility = (layers: CredibilityLayer[] = [layer()]): Credibility => ({
  note: "NOTA-BACKEND",
  title: "TITULO-BACKEND",
  about: "ACERCA-BACKEND",
  read_on: "2026-10-23",
  sources: [
    {
      ref: "nasa-std-7009b",
      title: "NASA-STD-7009B, Standard for Models and Simulations",
      source: "NASA Office of the Chief Engineer (2024)",
      url: "https://standards.nasa.gov/x.pdf",
      date: "2024-03-05",
      read_on: "2026-10-23",
      extent: "partial",
      extent_text: "leído en parte",
      what: "LO-LEIDO",
    },
  ],
  statements: [
    { id: "no-combining", label: "FRASE-ROTULO", quote: "FRASE-LITERAL", where: "§E.2", source: "NASA-STD-7009B", ref: "nasa-std-7009b" },
  ],
  groups: [
    { id: "capability", name: "M&S Capability", name_es: "GRUPO-CAPACIDAD", requirement: "[M&S 48]", quote: "GQ1", where: "§4.2.1.8", factors: [{ id: "validation", name: "M&S Validation", name_es: "Validación", question: "PREGUNTA-VAL", where: "Tabla 5" }] },
    { id: "results", name: "M&S Results", name_es: "GRUPO-RESULTADOS", requirement: "[M&S 31]", quote: "GQ2", where: "§4.3.6.1", factors: [{ id: "uncertainty", name: "M&S Uncertainty Characterization", name_es: "Incertidumbre", question: "PREGUNTA-INC", where: "Tabla 12" }] },
  ],
  not_assessed: "SIN-EVALUAR-BACKEND",
  emma: "EMMA-BACKEND",
  layers,
  criticality: {
    read_on: "2026-10-26",
    title: "CRITICIDAD-TITULO",
    about: "CRITICIDAD-ACERCA",
    not_applied: "CRITICIDAD-SIN-APLICAR",
    statements: [
      { id: "criticality-who", label: "CRITICIDAD-ROTULO", quote: "CRITICIDAD-LITERAL", where: "§4.1, p. 20", source: "NASA-STD-7009B", ref: "nasa-std-7009b" },
    ],
    axes: [
      { id: "decision", name: "Decision Consequence", name_es: "EJE-DECISION", quote: "EJE-LITERAL-1", where: "§D.2" },
      { id: "influence", name: "M&S Influence", name_es: "EJE-INFLUENCIA", quote: "EJE-LITERAL-2", where: "§D.3" },
    ],
  },
  out_of_scope: ["FUERA-BACKEND"],
  not_read: ["NO-LEIDO-BACKEND"],
});

describe("factores de una capa por grupo", () => {
  it("van en el orden de los grupos del backend, con su nombre", () => {
    const groups = factorGroups(
      credibility(),
      layer({ factors: [state("results", "uncertainty"), state("capability", "validation")] }),
    );
    expect(groups.map((group) => [group.id, group.name, group.rows.map((row) => row.id)])).toEqual([
      ["capability", "GRUPO-CAPACIDAD", ["validation"]],
      ["results", "GRUPO-RESULTADOS", ["uncertainty"]],
    ]);
  });

  it("un factor de un grupo no declarado no se pierde: va después, con su clave", () => {
    const groups = factorGroups(credibility(), layer({ factors: [state("otro", "x"), state("capability", "validation")] }));
    expect(groups.map((group) => [group.id, group.name])).toEqual([
      ["capability", "GRUPO-CAPACIDAD"],
      ["otro", null],
    ]);
    expect(groups.flatMap((group) => group.rows).length).toBe(2);
  });
});

describe("signo de una capa", () => {
  it("es el pictograma del rótulo de la cifra, con la palabra del backend", () => {
    expect(layerSign(layer())).toEqual({
      pictogram: "play",
      word: "PREDICHO",
      meaning: OBSERVATION_TYPES.predicted.meaning,
    });
    expect(layerSign(layer({ observation_type: "inferred", observation_type_text: "PALABRA-BACKEND" }))).toEqual({
      pictogram: "dot-half",
      word: "PALABRA-BACKEND",
      meaning: OBSERVATION_TYPES.inferred.meaning,
    });
  });

  it("un tipo desconocido lleva el dibujo de desconocido y su palabra, sin significado", () => {
    expect(layerSign(layer({ observation_type: "guessed", observation_type_text: "ADIVINADO" }))).toEqual({
      pictogram: UNKNOWN_PICTOGRAM,
      word: "ADIVINADO",
      meaning: null,
    });
  });
});

describe("la vista", () => {
  const html = renderToStaticMarkup(
    createElement(CredibilityView, {
      credibility: credibility([
        layer(),
        layer({
          id: "bone",
          display: "CAPA-HUESO",
          observation_type: "inferred",
          observation_type_text: "INFERIDO",
          model_version: null,
          model_note: "NOTA-MODELO",
        }),
      ]),
    }),
  );

  it("pinta cada frase del backend tal cual", () => {
    for (const text of [
      "TITULO-BACKEND", "ACERCA-BACKEND", "NOTA-BACKEND", "LO-LEIDO", "FRASE-LITERAL",
      "SIN-EVALUAR-BACKEND", "EMMA-BACKEND", "PREGUNTA-VAL", "PREGUNTA-INC", "ESTADO-validation",
      "ESTADO-uncertainty", "CAPA-PROYECCION", "CAPA-HUESO", "NOTA-MODELO", "trend:ols-contexto@1",
      "FUERA-BACKEND", "NO-LEIDO-BACKEND", "PREDICHO", "INFERIDO",
    ]) {
      expect(html).toContain(text);
    }
  });

  it("la dirección, las funciones, las rutas y las pruebas se parten (`.num.url`)", () => {
    // Con `white-space: pre` una cadena larga sin espacios ensancha el panel (lib/urlWrap.test.ts).
    for (const text of [
      "https://standards.nasa.gov/x.pdf",
      "analysis/trend.py:projection",
      "/api/status → predictions[]",
      "tests/test_observation_provenance.py::test_noise_is_never_projected",
    ]) {
      expect(html).toMatch(new RegExp(`class="[^"]*\\bnum url\\b[^"]*">${text.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&")}<`));
    }
  });

  it("un tipo heredado del objeto («toString») no se toma por conocido", () => {
    expect(layerSign(layer({ observation_type: "toString", observation_type_text: "X" })).meaning).toBeNull();
  });

  it("cada capa va plegada", () => {
    // Los once factores, los dos ejes de la matriz y una por capa.
    expect(html.match(/<details/g)?.length).toBe(4);
  });

  it("lo leído del Apéndice D, con su día, y los dos ejes en cada capa, tal cual", () => {
    for (const text of [
      "CRITICIDAD-TITULO", "CRITICIDAD-ACERCA", "CRITICIDAD-SIN-APLICAR", "CRITICIDAD-ROTULO",
      "CRITICIDAD-LITERAL", "EJE-LITERAL-1", "EJE-LITERAL-2", "Decision Consequence",
    ]) {
      expect(html).toContain(text);
    }
    expect(html).toContain('Leído el <span class="num">2026-10-26</span>.');
    // Cada capa dice algo de los dos ejes, con el nombre del eje que da el backend.
    expect(html.match(/<dt>EJE-DECISION<\/dt><dd>CRITICIDAD-decision<\/dd>/g)).toHaveLength(2);
    expect(html.match(/<dt>EJE-INFLUENCIA<\/dt><dd>CRITICIDAD-influence<\/dd>/g)).toHaveLength(2);
  });

  it("sin lo leído del Apéndice D (un backend anterior) el panel se pinta igual", () => {
    const card = layer();
    delete card.criticality;
    const old = credibility([card]);
    delete old.criticality;
    const page = renderToStaticMarkup(createElement(CredibilityView, { credibility: old }));
    expect(page).toContain("CAPA-PROYECCION");
    expect(page).not.toContain("EJE-DECISION");
  });

  it("no puntúa ni pinta un nivel: ni color ni cifra de nivel en el código de la vista", () => {
    const source = readFileSync(fileURLToPath(new URL("./CredibilityView.tsx", import.meta.url)), "utf8");
    const logic = readFileSync(fileURLToPath(new URL("./credibility.ts", import.meta.url)), "utf8");
    for (const code of [source, logic]) {
      expect(code).not.toMatch(/color=/);
      expect(code).not.toMatch(/levels"/);
    }
  });
});
