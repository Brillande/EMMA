import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { FoodAcceptability } from "../lib/api";
import { type Inventory, inventoryApi, inventoryPath } from "../lib/inventoryApi";
import {
  EMPTY_COUNT,
  ReservesMedications,
  ReservesNutrition,
  ReservesResupply,
  ReservesStatus,
  categoryViews,
  countBody,
  coverageRows,
  daysUntil,
  itemIdOf,
  medicationRows,
  pickItem,
} from "./HomeReserves";

/**
 * «Reservas» de «Inicio» (lote «reservas», 2026-11-14). Lo que no puede pasar, sin navegador:
 * - sin recuentos firmados, cada pieza dice «sin declarar» con la marca gris de «no disponible»,
 *   y no aparece ninguna cifra de la maqueta;
 * - la autonomía y lo que está bajo su mínimo son los del backend: aquí no se calculan;
 * - la cobertura proyectada sale solo con autonomía y llegada declaradas;
 * - el recuento no manda un cero que nadie dijo, y va con la cabecera de la consola.
 */

const REFERENCE = Date.parse("2026-11-14T12:00:00Z");

const item = (over: Partial<Inventory["categories"][number]["items"][number]>) => ({
  id: "amoxicillin",
  name: "Amoxicilina",
  family: "antibiotic",
  unit: "u.",
  quantity: 12,
  daily_use: 0.5,
  autonomy_days: 24,
  min_days: 30,
  critical: true,
  alternatives: ["cefalexin"],
  counted_at: "2026-11-14T10:00:00Z",
  declared_by: "crew-01",
  expires: "2027-03-01",
  ...over,
});

const DECLARED: Inventory = {
  declared: true,
  resupply: {
    name: "Carguero",
    eta: "2026-12-12T12:00:00Z",
    capacity_kg: 1200,
    declared_at: "2026-11-10T00:00:00Z",
    declared_by: "tierra",
  },
  categories: [
    {
      id: "medications",
      label: "Medicamentos",
      items: [
        item({}),
        item({ id: "cefalexin", name: "Cefalexina", quantity: 40, daily_use: 1, autonomy_days: 40, critical: false, alternatives: ["amoxicillin"] }),
        item({ id: "ibuprofen", name: "Ibuprofeno", family: null, daily_use: null, autonomy_days: null, min_days: null, critical: null, alternatives: [] }),
      ],
      totals: { units: 64, kinds: 3, critical: 1, available: 3, undeclared_use: 1, min_autonomy_days: 24 },
    },
  ],
};

const EMPTY: Inventory = { declared: false, resupply: null, categories: [] };

const render = (element: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(element);
const ready = <T,>(value: T) => ({ state: "ready" as const, value });

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("categorías", () => {
  it("las tres del contrato, en su orden; sin recuentos, todas sin declarar", () => {
    const views = categoryViews(EMPTY);
    expect(views.map((view) => view.id)).toEqual(["medications", "food", "medical-equipment"]);
    expect(views.every((view) => view.undeclared)).toBe(true);
  });

  it("lo declarado lleva los totales del backend tal cual", () => {
    const [medications, food] = categoryViews(DECLARED);
    expect(medications).toMatchObject({ undeclared: false, units: 64, kinds: 3, belowMinimum: 1, minAutonomyDays: 24 });
    expect(food?.undeclared).toBe(true);
  });
});

describe("sin declarar: gris de «no disponible» y ninguna cifra inventada", () => {
  const pieces = [
    render(createElement(ReservesStatus, { inventory: ready(EMPTY) })),
    render(createElement(ReservesMedications, { inventory: ready(EMPTY) })),
    render(createElement(ReservesResupply, { inventory: ready(EMPTY), reference: REFERENCE, profileId: "mars-transit" })),
  ];

  it.each(pieces)("cada pieza dice «sin declarar» con la marca gris", (html) => {
    expect(html).toContain("c-gray");
    expect(html.toLowerCase()).toMatch(/sin (declarar|existencias declaradas|reabastecimiento declarado)/);
    // Ni anillo con cifra ni porcentaje: no hay nada que contar.
    expect(html).not.toMatch(/\d+ %/);
    expect(html).not.toContain('role="img"');
  });

  it("no aparece ninguna cifra de la maqueta", () => {
    const all = pieces.join("");
    for (const figure of ["1.284", "82", "3.420", "452", "1.200", "36 días"]) expect(all).not.toContain(figure);
  });

  it("el abastecimiento lleva el nombre de la ubicación elegida", () => {
    expect(pieces[2]).toContain("Tránsito a Marte");
  });
});

describe("medicamentos", () => {
  it("bajo su mínimo primero, después la menor autonomía; sin consumo al final", () => {
    const rows = medicationRows(DECLARED.categories[0]);
    expect(rows.map((row) => row.id)).toEqual(["amoxicillin", "cefalexin", "ibuprofen"]);
    expect(rows[0]?.alternatives).toEqual(["Cefalexina"]);
  });

  it("la tabla marca lo que está bajo su mínimo sin color de aviso, y lo que no tiene consumo en gris", () => {
    const html = render(createElement(ReservesMedications, { inventory: ready(DECLARED) }));
    expect(html).toContain("Amoxicilina");
    expect(html).toContain("c-text");
    expect(html).not.toMatch(/c-(red|yellow)/);
    expect(html).toContain("sin consumo");
    expect(html).toContain("sin familia declarada");
  });

  it("el estado enseña el anillo de tipos con existencias y la autonomía mínima del backend", () => {
    const html = render(createElement(ReservesStatus, { inventory: ready(DECLARED) }));
    expect(html).toContain('aria-label="3 de 3 tipos con existencias"');
    expect(html).toContain("24 d");
    expect(html).toContain("Bajo mínimo");
    expect(html).not.toMatch(/[Cc]r[ií]tico/);
  });
});

describe("abastecimiento", () => {
  it("días hasta la llegada desde la referencia de los datos", () => {
    expect(daysUntil("2026-12-12T12:00:00Z", REFERENCE)).toBe(28);
    expect(daysUntil("no es una fecha", REFERENCE)).toBeNull();
  });

  it("cobertura proyectada = autonomía + días hasta la llegada, y el margen", () => {
    expect(coverageRows(DECLARED, REFERENCE)).toEqual([
      { id: "medications", label: "Medicamentos", autonomyDays: 24, projectedDays: 52, marginDays: -4 },
    ]);
  });

  it("sin reabastecimiento declarado no hay cobertura proyectada", () => {
    const rows = coverageRows({ ...DECLARED, resupply: null }, REFERENCE);
    expect(rows[0]?.projectedDays).toBeNull();
    const html = render(createElement(ReservesResupply, { inventory: ready({ ...DECLARED, resupply: null }), reference: REFERENCE, profileId: null }));
    expect(html).toContain("sin reabastecimiento declarado");
    expect(html).toContain("sin llegada declarada");
  });

  it("con todo declarado, la llegada y la cobertura salen con sus cifras", () => {
    const html = render(createElement(ReservesResupply, { inventory: ready(DECLARED), reference: REFERENCE, profileId: "leo" }));
    expect(html).toContain("Carguero");
    expect(html).toContain("28 d");
    expect(html).toContain("52 d");
    expect(html).toContain("antes de la llegada");
  });
});

describe("nutrición: solo lo que mide el backend", () => {
  const food: FoodAcceptability = {
    subject: "crew-01",
    key: "food-acceptability",
    display: "Food acceptability",
    display_es: "Aceptabilidad de la comida",
    criterion: null,
    rated: 0,
    below: null,
    statement: "Sin valoraciones de la comida.",
    not_measured_excluded: 0,
    not_measured_note: "",
    shown: 0,
    ratings: [],
  };

  it("sin lecturas, el cian de dato ausente y la frase del backend", () => {
    const html = render(
      createElement(ReservesNutrition, { nutrition: { food: ready(food), readings: ready([
          { key: "energy-intake-daily", display: "Ingesta energética diaria", latest: null },
          { key: "appetite-rating", display: "Apetito", latest: null },
        ]) } }),
    );
    expect(html).toContain("Sin valoraciones de la comida.");
    expect(html).toContain("c-cyan");
    expect(html).toContain("sin lecturas");
    expect(html).not.toMatch(/Requerimientos|Variedad|Índice de adecuación/);
  });

  it("con lecturas, la cifra, su unidad y su hora", () => {
    const html = render(
      createElement(ReservesNutrition, {
        nutrition: {
          food: ready({ ...food, rated: 4, below: 1, statement: "4 valoraciones." }),
          readings: ready([
            {
              key: "energy-intake-daily",
              display: "Ingesta energética diaria",
              latest: { value: 2450, unit: "kcal/d", at: "2026-11-14T08:00:00Z" },
            },
            { key: "appetite-rating", display: "Apetito", latest: null },
          ]),
        },
      }),
    );
    expect(html).toContain("Ingesta energética diaria");
    expect(html).toContain("2450");
    expect(html).toContain("2026-11-14 08:00 UTC");
    expect(html).not.toContain("appetite-rating");
    expect(html).toContain("kcal/día");
    expect(html).toContain("por debajo del criterio");
  });
});

describe("declarar existencias", () => {
  const form = { ...EMPTY_COUNT, category: "medications", name: "Paracetamol oral", unit: "u.", quantity: "20" };

  it("el id de un artículo nuevo sale del nombre", () => {
    expect(itemIdOf("Ácido acetilsalicílico 100 mg")).toBe("acido-acetilsalicilico-100-mg");
  });

  it("lo opcional vacío no se manda: ningún cero que nadie dijo", () => {
    expect(countBody(form, "crew-01", "2026-11-14T12:00:00.000Z")).toEqual({
      category: "medications",
      item: "paracetamol-oral",
      name: "Paracetamol oral",
      unit: "u.",
      quantity: 20,
      counted_at: "2026-11-14T12:00:00.000Z",
      declared_by: "crew-01",
    });
  });

  it("sin quien firma, sin cantidad o con una cifra que no vale, no hay cuerpo", () => {
    expect(countBody(form, " ", "x")).toBeNull();
    expect(countBody({ ...form, quantity: "" }, "crew-01", "x")).toBeNull();
    expect(countBody({ ...form, dailyUse: "-1" }, "crew-01", "x")).toBeNull();
    expect(countBody({ ...form, expires: "1/3/27" }, "crew-01", "x")).toBeNull();
  });

  it("elegir un artículo existente rellena lo declarado y deja la cantidad por contar", () => {
    const picked = pickItem({ ...EMPTY_COUNT, category: "medications" }, DECLARED, "amoxicillin");
    expect(picked).toMatchObject({ item: "amoxicillin", name: "Amoxicilina", dailyUse: "0.5", minDays: "30", quantity: "" });
    expect(countBody({ ...picked, quantity: "10,5" }, "crew-01", "x")).toMatchObject({ item: "amoxicillin", quantity: 10.5, daily_use: 0.5 });
  });

  it("el POST va a /api/inventory/count con la cabecera de la consola; Tierra lee con su corte", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ledger_index: 7 }), { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);
    const answer = await inventoryApi.count({
      category: "food",
      item: "arroz",
      name: "Arroz",
      unit: "raciones",
      quantity: 10,
      counted_at: "2026-11-14T12:00:00Z",
      declared_by: "crew-01",
    });
    expect(answer.ledger_index).toBe(7);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/inventory/count");
    expect(new Headers(init.headers).get("X-EMMA-Console")).toBe("1");
    expect(inventoryPath(new Date("2026-11-14T12:00:00Z"))).toBe("/inventory?until=2026-11-14T12%3A00%3A00.000Z");
  });
});
