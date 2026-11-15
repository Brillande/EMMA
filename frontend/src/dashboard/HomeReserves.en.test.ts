/**
 * «Reservas» en inglés (`lib/i18n.ts`): los rótulos de las cuatro tarjetas y del formulario de
 * recuento. Lo que se firma no se traduce: el cuerpo del `POST` lleva lo tecleado, tal cual, también
 * con la interfaz en inglés. Cifras y marcas, en `HomeReserves.test.ts`.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { FoodAcceptability } from "../lib/api";
import type { Inventory } from "../lib/inventoryApi";
import {
  CountFormView,
  EMPTY_COUNT,
  ReservesMedications,
  ReservesNutrition,
  ReservesResupply,
  ReservesStatus,
  categoryViews,
  countBody,
  medicationRows,
} from "./HomeReserves";

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
  alternatives: [],
  counted_at: "2026-11-14T10:00:00Z",
  declared_by: "crew-01",
  expires: "2027-03-01",
  ...over,
});

const DECLARED: Inventory = {
  declared: true,
  resupply: { name: "Cargo", eta: "2026-12-12T12:00:00Z", capacity_kg: 1200, declared_at: "2026-11-10T00:00:00Z", declared_by: "ground" },
  categories: [
    {
      id: "medications",
      label: "Medications",
      items: [
        item({}),
        item({ id: "ibuprofen", name: "Ibuprofeno", family: null, daily_use: null, autonomy_days: null, min_days: null, critical: null }),
      ],
      totals: { units: 24, kinds: 2, critical: 1, available: 2, undeclared_use: 1, min_autonomy_days: 24 },
    },
  ],
};

const EMPTY: Inventory = { declared: false, resupply: null, categories: [] };
const ready = <T,>(value: T) => ({ state: "ready" as const, value });
const render = (element: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(element);

describe("«Reservas» en inglés", () => {
  it("sin recuentos: «not declared» y los rótulos de reserva de las categorías", () => {
    expect(categoryViews(EMPTY).map((view) => view.label)).toEqual(["Medications", "Food", "Medical equipment"]);
    const html = render(createElement(ReservesStatus, { inventory: ready(EMPTY) }));
    expect(html).toContain('aria-label="Resources and inventory"');
    expect(html).toContain("Resources and inventory: status and autonomy");
    expect(html).toContain("No stock declared: nobody has signed a count.");
    expect(html).toContain("not declared");
    expect(html).not.toMatch(/Recursos e inventario|sin declarar|Sin existencias|Medicamentos|Alimentos/);
  });

  it("con recuentos: unidades, tipos, autonomía y las dos píldoras", () => {
    const html = render(createElement(ReservesStatus, { inventory: ready(DECLARED) }));
    for (const text of ["units ·", "kinds", "Minimum autonomy", "Below minimum (", "In stock (", "kinds in stock"]) {
      expect(html).toContain(text);
    }
    expect(html).not.toMatch(/Autonomía|Bajo mínimo|Con existencias|tipos/);
  });

  it("la tabla de medicamentos", () => {
    const html = render(createElement(ReservesMedications, { inventory: ready(DECLARED) }));
    for (const text of [
      'aria-label="Medications"',
      "Medications: management",
      ">Item<",
      ">Stock<",
      ">Autonomy<",
      "Alternatives (same family)",
      "Count by crew-01,",
      "; expires 2027-03-01",
      "Below the declared minimum of",
      "no declared use",
      "no family declared",
      "none in stock",
    ]) {
      expect(html).toContain(text);
    }
    expect(html).not.toMatch(/Artículo|Existencias|Alternativas|Recuento de|caduca|sin consumo|ninguna con/);
    // El nombre que tecleó quien declaró no se toca.
    expect(html).toContain("Amoxicilina");
  });

  it("el abastecimiento: ubicación, llegada y cobertura", () => {
    const html = render(createElement(ReservesResupply, { inventory: ready(DECLARED), reference: REFERENCE, profileId: "leo" }));
    for (const text of [
      'aria-label="Resupply"',
      "Location: Low Earth orbit",
      "Next resupply",
      "Vehicle",
      "Declared arrival",
      "· in ",
      "Capacity",
      "Declared",
      "Projected coverage (with resupply)",
      "runs out",
      "before arrival",
      "until arrival. Assumes the resupply replaces what is used up by then.",
    ]) {
      expect(html).toContain(text);
    }
    expect(html).not.toMatch(/Abastecimiento|Ubicación|Próximo|Vehículo|Llegada|Capacidad|Cobertura|se acaba/);
    const past = render(createElement(ReservesResupply, { inventory: ready(DECLARED), reference: Date.parse("2026-12-20T12:00:00Z"), profileId: null }));
    expect(past).toMatch(/<span class="num">[^<]+ d<\/span> ago/);
    expect(past).not.toContain("hace");
    const none = render(createElement(ReservesResupply, { inventory: ready({ ...DECLARED, resupply: null }), reference: REFERENCE, profileId: null }));
    expect(none).toContain("no resupply declared");
    expect(none).toContain("no arrival declared");
  });

  it("la nutrición: rótulos de la interfaz; la frase y el nombre son del backend", () => {
    const food = { display_es: "BACKEND NAME", statement: "BACKEND SENTENCE", rated: 4, below: 1, dishes: [{}, {}] } as unknown as FoodAcceptability;
    const html = render(
      createElement(ReservesNutrition, {
        nutrition: { food: ready(food), readings: ready([{ key: "appetite-rating", display: "BACKEND READING", latest: null }]) },
        level: null,
      }),
    );
    for (const text of [
      'aria-label="Food and nutrition"',
      "Nutrition domain",
      "no level",
      "no readings",
      "ratings",
      "below the criterion",
      "dishes",
      "BACKEND NAME",
      "BACKEND SENTENCE",
      "BACKEND READING",
    ]) {
      expect(html).toContain(text);
    }
    expect(html).not.toMatch(/Alimentación|Dominio|sin nivel|sin lecturas|valoraciones|platos/);
  });
});

describe("el recuento en inglés", () => {
  const form = { ...EMPTY_COUNT, category: "medications", name: "Ácido fólico", unit: "raciones", quantity: "3,5" };

  it("el formulario: rótulos y pistas en inglés", () => {
    const html = render(
      createElement(CountFormView, {
        inventory: DECLARED,
        form,
        setForm: () => undefined,
        operator: "",
        setOperator: () => undefined,
        countedAt: "2026-11-14T12:00:00Z",
        onSign: () => undefined,
        busy: false,
        error: null,
        signed: 7,
      }),
    );
    for (const text of [
      'aria-label="Declare stock"',
      'aria-label="Category"',
      "Category…",
      "New item…",
      'aria-label="Item name"',
      'placeholder="unit (u., servings…)"',
      'aria-label="Daily use (optional)"',
      'aria-label="Minimum days (optional)"',
      'aria-label="Expiry (optional)"',
      'aria-label="Declared by"',
      "Sign count",
      "count at",
      "signed by",
      "signed, entry",
    ]) {
      expect(html).toContain(text);
    }
    expect(html).not.toMatch(/Declarar|Categoría|Artículo|Cantidad|Caducidad|Quién|Firmar|recuento a|asiento/);
    // Lo tecleado sigue en su campo, sin traducir.
    expect(html).toContain('value="Ácido fólico"');
  });

  it("lo que se firma va como se tecleó: ni el nombre ni la unidad pasan por `tr`", () => {
    expect(countBody(form, "CMO", "2026-11-14T12:00:00Z")).toEqual({
      category: "medications",
      item: "acido-folico",
      name: "Ácido fólico",
      unit: "raciones",
      quantity: 3.5,
      counted_at: "2026-11-14T12:00:00Z",
      declared_by: "CMO",
    });
  });

  it("el orden de la tabla sigue al idioma de la interfaz y no cambia las existencias", () => {
    const rows = medicationRows({
      id: "medications",
      label: "Medications",
      items: [
        item({ id: "b", name: "Zinc", daily_use: null, autonomy_days: null, critical: null }),
        item({ id: "a", name: "Aspirin", daily_use: null, autonomy_days: null, critical: null }),
      ],
      totals: DECLARED.categories[0]!.totals,
    });
    expect(rows.map((row) => row.name)).toEqual(["Aspirin", "Zinc"]);
    expect(rows[0]?.stock).toBe("12 u.");
  });
});
