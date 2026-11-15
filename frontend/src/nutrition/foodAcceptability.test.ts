import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml, pictogramSvg, taggedPictogram, thSign } from "../advisor/visibleText";
import type { FoodAcceptability, FoodDish, FoodRating } from "../lib/api";
import { formatNumber } from "../lib/format";
import { uiPictogram } from "../lib/uiMarks";
import { FoodAcceptabilityView } from "./FoodAcceptabilityPanel";
import { dishesView, foodMark, foodView } from "./foodAcceptability";
import { ApiError } from "../lib/api";
import { type RequestOutcome, requestOutcome } from "../lib/marks";

/** Una lectura que cayó (5xx): la marca de fallo con el motivo tal cual (§5.34.14). */
const down = (text: string): RequestOutcome => requestOutcome(new ApiError(503, text));

/**
 * La comida frente a su criterio: la marca y la frase son del backend y se pintan tal cual,
 * sin color de alerta. Aquí no se decide si una valoración queda por debajo ni cómo se lee su
 * cifra (por eso los textos de prueba son marcadores, no frases de verdad).
 */
const rating = (value: number, over: Partial<FoodRating> = {}): FoodRating => ({
  effective: "2026-12-01T07:00:00+00:00",
  value,
  value_text: `CIFRA-${value}`,
  source: "simulator:menu-fatigue",
  source_display: "PROCEDENCIA",
  observation_type: "measured",
  evidence_context: "simulated",
  below: value < 6,
  mark: value < 6 ? "MARCA-DEL-BACKEND" : null,
  ...over,
});

const body = (over: Partial<FoodAcceptability> = {}): FoodAcceptability => ({
  subject: "crew-01",
  key: "food-acceptability",
  display: "Food acceptability, 9-point hedonic scale",
  display_es: "Aceptabilidad de la comida en la escala hedónica de 9 puntos",
  criterion: {
    value: 6,
    value_text: "6,0",
    literal: "6.0 or better",
    language: "en",
    statement: {
      id: "v2-7002-acceptable-6",
      label: "ROTULO-DE-LA-FRASE",
      quote: "FRASE-DE-LA-NORMA",
      ref: "nasa-std-3001-vol2-rev-f",
      source: "CITA-DE-LA-NORMA",
      title: "TITULO",
      url: "https://www.nasa.gov/norma.pdf",
      where: "7.1.1.2 · página 119",
      read_on: "2026-10-16",
      extent: "partial",
      extent_text: "leído en parte",
    },
    mark: "MARCA-DEL-BACKEND",
    rule: "REGLA-DEL-BACKEND",
    applies_to: "A-QUE-SE-APLICA",
    scope: "ALCANCE-DEL-BACKEND",
  },
  rated: 2,
  below: 1,
  statement: "RECUENTO-DEL-BACKEND",
  not_measured_excluded: 0,
  not_measured_note: "NOTA-NO-MEDIDAS",
  shown: 2,
  ratings: [rating(5.2, { effective: "2026-12-02T07:00:00+00:00" }), rating(7.1)],
  ...over,
});

describe("la comida frente a su criterio de aceptable", () => {
  it("cada valoración marcada lleva la palabra del backend, con el triángulo y sin color de alerta", () => {
    expect(foodMark(rating(5.2))).toEqual({
      mark: { pictogram: "shape-triangle", color: "text", className: "c-text" },
      text: "MARCA-DEL-BACKEND",
    });
    expect(foodMark(rating(7.1))).toBeNull();
  });

  it("sin criterio leído no se marca nada, ni como «por debajo» ni como lo contrario", () => {
    expect(foodMark(rating(2, { below: null, mark: null }))).toBeNull();
    const view = foodView(body({ criterion: null, below: null }));
    expect(view.criterion).toBeNull();
  });

  it("las cifras y el recuento son los del backend, tal cual", () => {
    const view = foodView(body());
    expect(view.statement).toBe("RECUENTO-DEL-BACKEND");
    expect(view.rows.map((row) => row.value)).toEqual(["CIFRA-5.2", "CIFRA-7.1"]);
    expect(view.rows.map((row) => row.mark?.text ?? null)).toEqual(["MARCA-DEL-BACKEND", null]);
    expect(view.shown).toBeNull();
    expect(view.notMeasured).toBeNull();
  });

  it("la frase de la norma va con su ubicación, su cita, cuánto se leyó y cuándo", () => {
    const criterion = foodView(body()).criterion!;
    expect(criterion.quote).toEqual({
      id: "v2-7002-acceptable-6",
      label: "ROTULO-DE-LA-FRASE",
      quote: "FRASE-DE-LA-NORMA",
      origin: "7.1.1.2 · página 119 · CITA-DE-LA-NORMA · leído en parte · leído el 2026-10-16",
      url: "https://www.nasa.gov/norma.pdf",
    });
    expect([criterion.rule, criterion.appliesTo, criterion.scope]).toEqual([
      "REGLA-DEL-BACKEND", "A-QUE-SE-APLICA", "ALCANCE-DEL-BACKEND",
    ]);
  });

  it("si la lista no trae todas, lo dice con los números formateados", () => {
    const view = foodView(body({ rated: 12000, shown: 60, not_measured_excluded: 1 }));
    // Millares con espacio fino (F.5.6 j), como en todo número de la interfaz.
    expect(view.shown).toBe("Las 60 últimas de 12 000.");
    expect(view.notMeasured).toBe("1 apartadas. NOTA-NO-MEDIDAS");
  });
});

describe("el panel de la aceptabilidad de la comida", () => {
  const html = (data: FoodAcceptability | null, failed: string | null = null) =>
    renderToStaticMarkup(createElement(FoodAcceptabilityView, { data, unavailable: failed === null ? null : down(failed) }));

  it("pinta el recuento, la regla, el alcance y la frase en su idioma", () => {
    const page = html(body());
    for (const text of [
      "RECUENTO-DEL-BACKEND", "REGLA-DEL-BACKEND", "ALCANCE-DEL-BACKEND", "A-QUE-SE-APLICA",
    ]) {
      expect(page).toContain(text);
    }
    expect(page).toContain('<q lang="en">FRASE-DE-LA-NORMA</q>');
  });

  it("el título con los cubiertos de su familia, y la regla del criterio con la escalera", () => {
    const page = html(body());
    const title = new RegExp(`<h2><span class="mark">${pictogramSvg("fork-knife")}Aceptabilidad de la comida</span></h2>`);
    expect(page).toMatch(title);
    // También sin datos: el título es el mismo.
    expect(html(null, "sin conexión")).toMatch(title);
    expect(page).toMatch(
      new RegExp(`<p class="secondary"><span class="mark">${pictogramSvg("stairs")}REGLA-DEL-BACKEND</span></p>`),
    );
    // Dos escaleras: la de la regla y la del plegable de las valoraciones (concepto `ratings`,
    // segunda pasada §5.33.7), que son puntos de esa misma escala.
    expect(page.match(/data-pictogram="stairs"/g)).toHaveLength(2);
    expect(page).toMatch(
      taggedPictogram("summary", uiPictogram("ratings"), "Valoraciones, la última primero</summary>"),
    );
  });

  it("el plegable de la norma, las cabeceras y la carga llevan su signo (§5.33.7)", () => {
    const page = html(body());
    expect(page).toMatch(taggedPictogram("summary", uiPictogram("sourceText"), "La frase de la norma</summary>"));
    const headers: [Parameters<typeof uiPictogram>[0], string][] = [
      ["time", "Hora"],
      ["value", "Valoración"],
      ["limits", "Frente al criterio"],
      ["provenance", "Procedencia"],
    ];
    for (const [concept, word] of headers) {
      expect(page).toMatch(thSign(uiPictogram(concept), `${word}</span></th>`, ' scope="col"'));
    }
    expect(page).not.toMatch(/<th scope="col">[^<]/);
    // Sin respuesta todavía (ni datos ni fallo): cargando, con su marca y sin color.
    const loading = html(null);
    expect(loading).toMatch(markedHtml("refresh", "Cargando…"));
    expect(loading).not.toContain("Sin datos");
  });

  it("si la última lectura falló, las cifras de antes van en cursiva: caducadas", () => {
    expect(html(body())).not.toContain("stale");
    const page = html(body(), "sin conexión");
    expect(page).toContain('<td class="num stale">CIFRA-5.2</td>');
    expect(page).toContain('<p class="stale">RECUENTO-DEL-BACKEND</p>');
    expect(page).toMatch(markedHtml("cross", "Sin datos: sin conexión", "red"));
  });

  it("la marca va en su fila, con el triángulo, y ninguna lleva color de alerta", () => {
    const page = html(body());
    expect(page.match(/data-food-below="yes"/g)).toHaveLength(1);
    expect(page.match(/data-food-below="no"/g)).toHaveLength(1);
    const [below, above] = page.split("<tr ").slice(1).map((row) => row.split("</tr>")[0]!);
    expect(below).toMatch(
      new RegExp(`<td><span class="mark c-text">${pictogramSvg("shape-triangle")}MARCA-DEL-BACKEND</span></td>`),
    );
    expect(above).not.toContain("shape-triangle");
    expect(page).not.toMatch(/c-red|c-yellow/);
  });

  it("sin criterio no pinta frase ni marca", () => {
    const page = html(body({ criterion: null, below: null, ratings: [rating(2, { below: null, mark: null })] }));
    expect(page).not.toContain("FRASE-DE-LA-NORMA");
    expect(page).not.toContain('data-food-below="yes"');
    expect(page).not.toContain("shape-triangle");
    // Ni la regla con su escalera: la única que queda es la del plegable de las valoraciones.
    expect(page).not.toContain("REGLA-DEL-BACKEND");
    expect(page.match(/data-pictogram="stairs"/g)).toHaveLength(1);
    expect(page).toMatch(
      taggedPictogram("summary", uiPictogram("ratings"), "Valoraciones, la última primero</summary>"),
    );
  });

  it("sin valoraciones no pinta tabla; sin respuesta lo dice con la marca de la petición", () => {
    const none = html(body({ rated: 0, below: 0, shown: 0, ratings: [] }));
    expect(none).not.toContain("<table");
    // El recuento del backend, con la marca de registro vacío, sin color (§5.34.14; era la de dato
    // ausente, §5.33.7); con valoraciones, sin ella.
    expect(none).toMatch(new RegExp(`<p>${markedHtml("ring-dotted", "RECUENTO-DEL-BACKEND").source}</span></p>`));
    expect(none).not.toContain("c-cyan");
    expect(html(body())).toContain("<p>RECUENTO-DEL-BACKEND</p>");
    expect(html(null, "sin conexión")).toMatch(
      new RegExp(`<p><span class="mark c-red">${pictogramSvg("cross")}Sin datos: sin conexión</span></p>`),
    );
  });
});

describe("plato a plato (decisión del usuario, 2026-10-26)", () => {
  const dish = (over: Partial<FoodDish> = {}): FoodDish => ({
    food: "PLATO-A",
    times: 3,
    distinct_days: 2,
    first_effective: "2026-12-01T07:00:00+00:00",
    last_effective: "2026-12-03T07:00:00+00:00",
    below: 1,
    statement: "RECUENTO-DEL-PLATO",
    series: [
      { effective: "2026-12-01T07:00:00+00:00", value: 7, value_text: "CIFRA-7", below: false, mark: null },
      { effective: "2026-12-01T13:00:00+00:00", value: 6, value_text: "CIFRA-6", below: false, mark: null },
      { effective: "2026-12-03T07:00:00+00:00", value: 4, value_text: "CIFRA-4", below: true, mark: "MARCA-DEL-BACKEND" },
    ],
    ...over,
  });
  const withDishes = (over: Partial<FoodAcceptability> = {}): FoodAcceptability =>
    body({
      ratings: [
        rating(5.2, { effective: "2026-12-02T07:00:00+00:00", food: "PLATO-A", food_display: "PLATO-A" }),
        rating(7.1, { food: null, food_display: "SIN-ALIMENTO-DEL-BACKEND" }),
      ],
      dishes: [dish(), dish({ food: "PLATO-B", times: 1200, distinct_days: 1, below: 0, statement: "OTRO", series: [] })],
      dishes_statement: "RECUENTO-DE-PLATOS",
      without_food: 1,
      without_food_note: "NOTA-SIN-ALIMENTO",
      repetition_note: "NOTA-DESCRIPTIVA",
      grouping: "REGLA-DE-AGRUPAR",
      ...over,
    });

  it("una respuesta sin el campo no inventa platos", () => {
    expect(dishesView(body())).toBeNull();
    expect(foodView(body()).dishes).toBeNull();
  });

  it("cada plato con su recuento del backend, sus números formateados y su serie en el tiempo", () => {
    const view = dishesView(withDishes())!;
    expect(view.statement).toBe("RECUENTO-DE-PLATOS");
    expect([view.repetition, view.grouping, view.withoutFood]).toEqual([
      "NOTA-DESCRIPTIVA", "REGLA-DE-AGRUPAR", "NOTA-SIN-ALIMENTO",
    ]);
    const [first, second] = view.rows;
    expect([first!.food, first!.statement, first!.times, first!.days]).toEqual(["PLATO-A", "RECUENTO-DEL-PLATO", "3", "2"]);
    // Por `lib/format.ts`, como todo número de la interfaz.
    expect(second!.times).toBe(formatNumber(1200));
    expect(first!.first).toBe("2026-12-01 07:00 UTC");
    expect(first!.series.map((point) => [point.when, point.value, point.mark?.text ?? null])).toEqual([
      ["2026-12-01 07:00 UTC", "CIFRA-7", null],
      ["2026-12-01 13:00 UTC", "CIFRA-6", null],
      ["2026-12-03 07:00 UTC", "CIFRA-4", "MARCA-DEL-BACKEND"],
    ]);
    // Sin valoraciones sin alimento, sin nota.
    expect(dishesView(withDishes({ without_food: 0 }))!.withoutFood).toBeNull();
  });

  it("dos valoraciones del mismo instante y valor tienen claves distintas", () => {
    const point = { effective: "2026-12-01T07:00:00+00:00", value: 7, value_text: "CIFRA-7", below: false, mark: null };
    const view = dishesView(withDishes({ dishes: [dish({ series: [point, point] })] }))!;
    const keys = view.rows[0]!.series.map((item) => item.key);
    expect(new Set(keys).size).toBe(2);
  });

  it("cada valoración dice su alimento; sin él, la palabra del backend", () => {
    const rows = foodView(withDishes()).rows;
    expect(rows.map((row) => [row.food, row.hasFood])).toEqual([
      ["PLATO-A", true], ["SIN-ALIMENTO-DEL-BACKEND", false],
    ]);
  });

  const html = (data: FoodAcceptability) =>
    renderToStaticMarkup(createElement(FoodAcceptabilityView, { data, unavailable: null }));

  it("el panel pinta «Por plato» con los cubiertos, la escalera y sin color de alerta", () => {
    const page = html(withDishes());
    expect(page).toMatch(taggedPictogram("summary", uiPictogram("ratings"), "Por plato</summary>"));
    expect(page).toMatch(thSign("fork-knife", "Plato</span></th>", ' scope="col"'));
    expect(page).toMatch(thSign("fork-knife", "Alimento</span></th>", ' scope="col"'));
    expect(page).toMatch(thSign(uiPictogram("date"), "Días distintos</span></th>", ' scope="col"'));
    for (const text of ["RECUENTO-DE-PLATOS", "NOTA-DESCRIPTIVA", "REGLA-DE-AGRUPAR", "NOTA-SIN-ALIMENTO", "RECUENTO-DEL-PLATO"]) {
      expect(page).toContain(text);
    }
    expect(page.match(/data-food-dish=/g)).toHaveLength(2);
    // La valoración del plato por debajo del criterio lleva la marca de siempre, en el color del texto.
    const plate = page.split('data-food-dish="PLATO-A"')[1]!.split("</tr>")[0]!;
    expect(plate).toMatch(new RegExp(`<span class="mark c-text">${pictogramSvg("shape-triangle")}MARCA-DEL-BACKEND</span>`));
    expect(page).not.toMatch(/c-red|c-yellow/);
    // La valoración sin alimento lleva la marca de «no disponible»; la que lo lleva, ninguna.
    expect(page).toContain('data-food-item="missing"');
    expect(page).toMatch(/data-food-item="named"><span class="mark">PLATO-A<\/span>/);
  });

  it("sin platos pero con valoraciones sin alimento, lo dice sin tabla de platos", () => {
    const page = html(withDishes({ dishes: [] }));
    expect(page).not.toContain("Por plato");
    expect(page).toContain("RECUENTO-DE-PLATOS NOTA-SIN-ALIMENTO");
  });

  describe("de la primera a la última, y la fracción rechazada al lado (decimonovena ronda, 2026-10-31)", () => {
    const point = (effective: string, value: number) => ({ effective, value, value_text: `CIFRA-${value}` });
    // Un plato tal como lo da el backend desde ese día: la comparación y la fracción, con sus frases.
    const compared = (over: Partial<FoodDish> = {}): FoodDish =>
      dish({
        change: {
          first: point("2026-12-01T07:00:00+00:00", 7),
          last: point("2026-12-03T07:00:00+00:00", 4),
          statement: "DE-LA-PRIMERA-A-LA-ULTIMA",
        },
        rejected: {
          times: 2,
          first: point("2026-12-01T08:00:00+00:00", 10),
          last: point("2026-12-03T08:00:00+00:00", 60),
          statement: "FRACCION-DEL-PLATO",
          series: [point("2026-12-01T08:00:00+00:00", 10), point("2026-12-03T08:00:00+00:00", 60)],
        },
        rejected_display: "FRACCION-DEL-PLATO",
        ...over,
      });
    const described = (over: Partial<FoodAcceptability> = {}): FoodAcceptability =>
      withDishes({
        dishes: [
          compared(),
          compared({ food: "PLATO-B", rejected: null, rejected_display: "SIN-FRACCION-DEL-BACKEND" }),
        ],
        change_note: "NOTA-DEL-CAMBIO",
        rejected_note: "NOTA-DE-LA-FRACCION",
        ...over,
      });

    it("una respuesta anterior a los campos no inventa comparación ni fracción", () => {
      const view = dishesView(withDishes())!;
      expect(view.rows.map((row) => [row.change, row.rejected])).toEqual([[null, null], [null, null]]);
      expect([view.changeNote, view.rejectedNote]).toEqual([null, null]);
      expect(html(withDishes())).not.toMatch(/data-food-change|data-food-rejected/);
    });

    it("cada plato trae las frases del backend tal cual: la comparación, y la fracción o las palabras para «sin declarar»", () => {
      const view = dishesView(described())!;
      expect(view.rows.map((row) => [row.change, row.rejected])).toEqual([
        ["DE-LA-PRIMERA-A-LA-ULTIMA", "FRACCION-DEL-PLATO"],
        ["DE-LA-PRIMERA-A-LA-ULTIMA", "SIN-FRACCION-DEL-BACKEND"],
      ]);
      expect([view.changeNote, view.rejectedNote]).toEqual(["NOTA-DEL-CAMBIO", "NOTA-DE-LA-FRACCION"]);
      // Sin `rejected_display`, la frase de `rejected`; y sin ninguna de las dos, nada: no se redacta.
      const { rejected_display: _display, ...withoutDisplay } = compared();
      const bare = dishesView(
        described({ dishes: [withoutDisplay, { ...withoutDisplay, rejected: null }] }),
      )!;
      expect(bare.rows.map((row) => row.rejected)).toEqual(["FRACCION-DEL-PLATO", null]);
    });

    it("el panel las pinta como texto secundario: sin color, sin flecha y sin dibujo nuevo", () => {
      const page = html(described());
      for (const text of ["NOTA-DEL-CAMBIO", "NOTA-DE-LA-FRACCION", "SIN-FRACCION-DEL-BACKEND"]) {
        expect(page).toContain(text);
      }
      expect(page.match(/<p class="secondary" data-food-change="true">DE-LA-PRIMERA-A-LA-ULTIMA<\/p>/g)).toHaveLength(2);
      expect(page).toMatch(/<div class="secondary" data-food-rejected="true">FRACCION-DEL-PLATO<\/div>/);
      expect(page).not.toMatch(/c-red|c-yellow|c-green|c-cyan/);
      // Los mismos dibujos que sin los campos: dos cifras no son un veredicto ni un concepto nuevo.
      const same = html(withDishes({ dishes: [dish(), dish({ food: "PLATO-B" })] }));
      expect(page.match(/data-pictogram=/g)).toHaveLength(same.match(/data-pictogram=/g)!.length);
    });

    it("si la última lectura falló, van en cursiva: caducadas", () => {
      const page = renderToStaticMarkup(
        createElement(FoodAcceptabilityView, { data: described(), unavailable: down("sin conexión") }),
      );
      expect(page).toContain('<p class="secondary stale" data-food-change="true">DE-LA-PRIMERA-A-LA-ULTIMA</p>');
      expect(page).toContain('<div class="secondary stale" data-food-rejected="true">FRACCION-DEL-PLATO</div>');
    });
  });
});
