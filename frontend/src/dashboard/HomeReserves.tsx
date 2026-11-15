import { type ReactNode, useEffect, useState } from "react";

import { Command } from "../components/Command";
import { LevelBadge } from "../components/LevelBadge";
import { MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { Loading, Unavailable } from "../components/Unavailable";
import { Pictogram } from "../icons";
import type { PictogramName } from "../icons/registry";
import { type FhirObservation, type FoodAcceptability, type Indicator, api, nutritionApi } from "../lib/api";
import { displayUnit, formatNumber, formatUtc } from "../lib/format";
import { language, tr } from "../lib/i18n";
import {
  INVENTORY_CATEGORIES,
  type Inventory,
  type InventoryCategory,
  type InventoryCountBody,
  type InventoryItem,
  inventoryApi,
} from "../lib/inventoryApi";
import { MISSING_MARK, OK_MARK, type RequestOutcome, type StateMark, UNAVAILABLE_MARK, mark, requestOutcome } from "../lib/marks";
import { useOperator } from "../lib/operator";
import { Ring } from "./HomeCharts";
import "./homeReserves.css";

/**
 * «Reservas» de «Inicio» (lote «reservas», 2026-11-14): la fila de abajo de la maqueta ISS
 * —«Recursos e inventario», «Medicamentos», «Alimentación y nutrición» y «Abastecimiento»— con el
 * estilo de «Inicio» y «Radiación» (`ref-card`, `PanelTitle`, el anillo de `HomeCharts`). La sesión
 * principal la coloca bajo un separador; aquí solo las cuatro tarjetas, que caen en la rejilla de 12
 * columnas de `.ref-home`.
 *
 * Por qué así (decisión del usuario, 2026-11-14: «Inventario real firmado»): EMMA no tenía cifras de
 * existencias, y la maqueta trae unas (1.284 u., 82 %, 36 días…) que no se copian. Todo sale de
 * `GET /api/inventory`, que son recuentos declarados por una persona y firmados en el registro; sin
 * recuentos, cada tarjeta dice «sin declarar» con la marca de «no disponible» (gris), y hay un mando
 * para declarar existencias que firma un asiento `inventory-count`.
 *
 * Lo que NO se copió de la maqueta, a propósito:
 * - El anillo no es un «índice»: cuenta artículos con existencias de los declarados, y lo dice.
 * - «Críticos» pasa a «bajo mínimo»: es la autonomía por debajo del mínimo que declaró una persona,
 *   no un nivel del análisis (la palabra de nivel es del backend), y va con el triángulo en el color
 *   del texto, sin color de aviso, como la marca de la comida (`nutrition/foodAcceptability.ts`):
 *   nada de esto toca el análisis ni las alertas.
 * - Nutrición: solo lo que el backend mide (nivel del dominio si quien monta lo pasa, la última
 *   ingesta energética y el apetito firmados, y la aceptabilidad de la comida con su frase). Sin
 *   «requerimientos cumplidos», «variedad» ni «índice de adecuación»: EMMA no los calcula.
 * - Abastecimiento: el reabastecimiento declarado; la cobertura proyectada es aritmética de dos
 *   cifras declaradas (autonomía + días hasta la llegada) y se dice de qué sale.
 *
 * Cada pieza se adapta a la ubicación elegida (`profileId`, el perfil enseñado en «Ubicación de la
 * tripulación»): su nombre va en el título del abastecimiento. No se inventa una cadencia de
 * reabastecimiento por perfil: si no hay uno declarado, se dice.
 */

/** Nombre corto de rótulo por perfil, el mismo de «Inicio» y «Radiación». */
const PROFILE_SHORT: Record<string, string> = {
  leo: tr("Órbita baja", "Low Earth orbit"),
  cislunar: "Cislunar",
  "lunar-surface": tr("Luna", "Moon"),
  "mars-transit": tr("Tránsito a Marte", "Mars transit"),
  "mars-surface": tr("Marte", "Mars"),
};

const DAY_MS = 24 * 3600 * 1000;

/** El dibujo de cada categoría del contrato; una desconocida lleva el cubo de «recursos». */
const CATEGORY_PICTOGRAM: Record<string, PictogramName> = {
  medications: "vial",
  food: "fork-knife",
  "medical-equipment": "kit-case",
};

/** Rótulo de reserva de una categoría, solo para el selector cuando el backend no la trae aún. */
const CATEGORY_FALLBACK: Record<string, string> = {
  medications: tr("Medicamentos", "Medications"),
  food: tr("Alimentos", "Food"),
  "medical-equipment": tr("Equipamiento médico", "Medical equipment"),
};

/**
 * Por debajo del mínimo declarado: el triángulo común en el color del texto. No es una alerta ni un
 * nivel: es la comparación de dos cifras que declaró una persona.
 */
export const BELOW_MINIMUM_MARK: StateMark = mark("shape-triangle", "text");

/** Lo que mide la nutrición del backend y se enseña aquí, en este orden. */
export const NUTRITION_KEYS = ["energy-intake-daily", "appetite-rating"] as const;

// ------------------------------------------------------------------------------------ lógica pura

type Load<T> = { state: "loading" } | { state: "ready"; value: T } | { state: "failed"; outcome: RequestOutcome };

export interface CategoryView {
  id: string;
  label: string;
  pictogram: PictogramName;
  /** Sin artículos declarados en la categoría: se dice «sin declarar». */
  undeclared: boolean;
  units: number;
  kinds: number;
  available: number;
  belowMinimum: number;
  undeclaredUse: number;
  minAutonomyDays: number | null;
}

/** Las tres categorías del contrato, en su orden; una que el backend no trae sale sin declarar. */
export function categoryViews(inventory: Inventory | null): CategoryView[] {
  const byId = new Map((inventory?.categories ?? []).map((item) => [item.id, item]));
  const extra = (inventory?.categories ?? []).filter(
    (item) => !(INVENTORY_CATEGORIES as readonly string[]).includes(item.id),
  );
  const ids = [...INVENTORY_CATEGORIES, ...extra.map((item) => item.id)];
  return ids.map((id) => {
    const category = byId.get(id);
    const totals = category?.totals;
    return {
      id,
      label: category?.label ?? CATEGORY_FALLBACK[id] ?? id,
      pictogram: CATEGORY_PICTOGRAM[id] ?? "cube",
      undeclared: category === undefined || category.items.length === 0 || totals === undefined || totals.kinds === 0,
      units: totals?.units ?? 0,
      kinds: totals?.kinds ?? 0,
      available: totals?.available ?? 0,
      belowMinimum: totals?.critical ?? 0,
      undeclaredUse: totals?.undeclared_use ?? 0,
      minAutonomyDays: totals?.min_autonomy_days ?? null,
    };
  });
}

/** Días (con decimales) desde la referencia de los datos hasta un instante; `null` si no se lee. */
export function daysUntil(iso: string, reference: number): number | null {
  const at = Date.parse(iso);
  if (Number.isNaN(at) || !Number.isFinite(reference)) return null;
  return (at - reference) / DAY_MS;
}

/** Una cifra de días como se lee: entera desde 10, con un decimal por debajo. */
export function formatDays(days: number): string {
  return `${formatNumber(days, Math.abs(days) < 10 ? 1 : 0)} d`;
}

export interface MedicationRow {
  id: string;
  name: string;
  family: string | null;
  stock: string;
  autonomyDays: number | null;
  minDays: number | null;
  belowMinimum: boolean;
  /** Nombres de las alternativas con existencias de la misma familia. */
  alternatives: string[];
  expires: string | null;
  countedAt: string;
  declaredBy: string;
}

/** Orden de la tabla: lo que está bajo su mínimo primero, después la menor autonomía; sin consumo al final. */
function byUrgency(a: MedicationRow, b: MedicationRow): number {
  if (a.belowMinimum !== b.belowMinimum) return a.belowMinimum ? -1 : 1;
  const left = a.autonomyDays ?? Number.POSITIVE_INFINITY;
  const right = b.autonomyDays ?? Number.POSITIVE_INFINITY;
  if (left !== right) return left - right;
  // Los nombres los teclea quien declara; se ordenan con las reglas del idioma de la interfaz.
  return a.name.localeCompare(b.name, language());
}

export function medicationRows(category: InventoryCategory | undefined): MedicationRow[] {
  if (category === undefined) return [];
  const names = new Map(category.items.map((item) => [item.id, item.name]));
  return category.items
    .map((item: InventoryItem) => ({
      id: item.id,
      name: item.name,
      family: item.family,
      stock: `${formatNumber(item.quantity, Number.isInteger(item.quantity) ? 0 : 1)} ${item.unit}`.trim(),
      autonomyDays: item.autonomy_days,
      minDays: item.min_days,
      belowMinimum: item.critical === true,
      alternatives: item.alternatives.map((id) => names.get(id) ?? id),
      expires: item.expires,
      countedAt: item.counted_at,
      declaredBy: item.declared_by,
    }))
    .sort(byUrgency);
}

export interface CoverageRow {
  id: string;
  label: string;
  autonomyDays: number | null;
  /** Autonomía mínima + días hasta la llegada; `null` si falta alguna de las dos. */
  projectedDays: number | null;
  /** Autonomía mínima − días hasta la llegada: lo que sobra (o falta) al llegar. */
  marginDays: number | null;
}

export interface ResupplyView {
  name: string;
  eta: string;
  daysToEta: number | null;
  capacityKg: number | null;
  declaredBy: string;
  declaredAt: string;
}

export function resupplyView(inventory: Inventory | null, reference: number): ResupplyView | null {
  const resupply = inventory?.resupply ?? null;
  if (resupply === null) return null;
  return {
    name: resupply.name,
    eta: resupply.eta,
    daysToEta: daysUntil(resupply.eta, reference),
    capacityKg: resupply.capacity_kg,
    declaredBy: resupply.declared_by,
    declaredAt: resupply.declared_at,
  };
}

/** La cobertura de cada categoría con autonomía declarada, frente al reabastecimiento declarado. */
export function coverageRows(inventory: Inventory | null, reference: number): CoverageRow[] {
  const resupply = resupplyView(inventory, reference);
  const toEta = resupply?.daysToEta ?? null;
  return categoryViews(inventory)
    .filter((item) => !item.undeclared)
    .map((item) => {
      const autonomy = item.minAutonomyDays;
      const both = autonomy !== null && toEta !== null && toEta >= 0;
      return {
        id: item.id,
        label: item.label,
        autonomyDays: autonomy,
        projectedDays: both ? autonomy + toEta : null,
        marginDays: both ? autonomy - toEta : null,
      };
    });
}

/** Lo que se teclea en el formulario de recuento: texto, como lo da cada campo. */
export interface CountForm {
  category: string;
  /** El `id` del artículo existente, o «» para uno nuevo (se saca del nombre). */
  item: string;
  name: string;
  unit: string;
  quantity: string;
  dailyUse: string;
  family: string;
  minDays: string;
  expires: string;
}

export const EMPTY_COUNT: CountForm = {
  category: "",
  item: "",
  name: "",
  unit: "",
  quantity: "",
  dailyUse: "",
  family: "",
  minDays: "",
  expires: "",
};

/** El `id` de un artículo nuevo, sacado de su nombre: minúsculas, sin acentos, guiones. */
export function itemIdOf(name: string): string {
  return name
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/** Una cifra del formulario: `undefined` si el campo va vacío, `null` si no es una cifra válida. */
function numberOf(text: string): number | null | undefined {
  const trimmed = text.trim().replace(",", ".");
  if (trimmed === "") return undefined;
  const value = Number(trimmed);
  return Number.isFinite(value) && value >= 0 ? value : null;
}

/**
 * El cuerpo de `POST /api/inventory/count`, o `null` si falta algo obligatorio o una cifra no vale.
 * Lo opcional vacío no se manda: no se declara un cero que nadie dijo.
 */
export function countBody(form: CountForm, operator: string, countedAt: string): InventoryCountBody | null {
  const name = form.name.trim();
  const unit = form.unit.trim();
  const signer = operator.trim();
  const item = form.item !== "" ? form.item : itemIdOf(name);
  const quantity = numberOf(form.quantity);
  const dailyUse = numberOf(form.dailyUse);
  const minDays = numberOf(form.minDays);
  const expires = form.expires.trim();
  if (form.category === "" || name === "" || unit === "" || signer === "" || item === "") return null;
  if (quantity === undefined || quantity === null || dailyUse === null || minDays === null) return null;
  if (expires !== "" && !/^\d{4}-\d{2}-\d{2}$/.test(expires)) return null;
  const body: InventoryCountBody = {
    category: form.category,
    item,
    name,
    unit,
    quantity,
    counted_at: countedAt,
    declared_by: signer,
  };
  if (dailyUse !== undefined) body.daily_use = dailyUse;
  if (minDays !== undefined) body.min_days = minDays;
  if (form.family.trim() !== "") body.family = form.family.trim();
  if (expires !== "") body.expires = expires;
  return body;
}

/** El formulario con un artículo existente elegido: se rellenan sus datos declarados. */
export function pickItem(form: CountForm, inventory: Inventory | null, id: string): CountForm {
  const item = inventory?.categories.find((cat) => cat.id === form.category)?.items.find((it) => it.id === id);
  if (item === undefined) return { ...form, item: "" };
  return {
    ...form,
    item: item.id,
    name: item.name,
    unit: item.unit,
    quantity: "",
    dailyUse: item.daily_use === null ? "" : String(item.daily_use),
    family: item.family ?? "",
    minDays: item.min_days === null ? "" : String(item.min_days),
    expires: item.expires ?? "",
  };
}

/** Un indicador de nutrición con su última lectura firmada; sin lecturas, `latest` es `null`. */
export interface LatestReading {
  key: string;
  /** El nombre del catálogo (`display_es`); sin catálogo, la clave. */
  display: string;
  latest: { value: number; unit: string; at: string } | null;
}

export function latestReading(
  key: string,
  observations: readonly FhirObservation[],
  catalog: ReadonlyMap<string, Indicator>,
): LatestReading {
  const last = [...observations].sort((a, b) => Date.parse(a.effectiveDateTime) - Date.parse(b.effectiveDateTime)).at(-1);
  const indicator = catalog.get(key);
  return {
    key,
    display: indicator?.display_es ?? key,
    latest:
      last === undefined
        ? null
        : { value: last.valueQuantity.value, unit: indicator?.unit ?? last.valueQuantity.unit, at: last.effectiveDateTime },
  };
}

// ------------------------------------------------------------------------------------ piezas

function utc(iso: string): string {
  const at = new Date(iso);
  return Number.isNaN(at.getTime()) ? iso : formatUtc(at);
}

function unitText(ucum: string): string {
  try {
    return displayUnit(ucum);
  } catch {
    return ucum;
  }
}

function Pending({ item }: { item: Load<unknown> }) {
  if (item.state === "loading") return <Loading />;
  if (item.state === "failed") return <Unavailable outcome={item.outcome} />;
  return null;
}

/** «sin declarar» con la marca de «no disponible» (gris): nadie ha firmado un recuento. */
function Undeclared({ children = tr("sin declarar", "not declared") }: { children?: ReactNode }) {
  return <MarkOf mark={UNAVAILABLE_MARK}>{children}</MarkOf>;
}

/** Una categoría: anillo de artículos con existencias, autonomía mínima y las dos píldoras. */
export function CategoryLine({ view }: { view: CategoryView }) {
  const share = view.kinds === 0 ? 0 : Math.round((100 * view.available) / view.kinds);
  return (
    <li className="res-category">
      <span className="res-category-art" aria-hidden="true">
        <Pictogram name={view.pictogram} />
      </span>
      <span className="res-category-name">
        <strong>{view.label}</strong>
        {view.undeclared ? (
          <Undeclared />
        ) : (
          <small className="secondary">
            <span className="num">{formatNumber(view.units)}</span> {tr("u.", view.units === 1 ? "unit" : "units")} ·{" "}
            <span className="num">{formatNumber(view.kinds)}</span> {view.kinds === 1 ? tr("tipo", "kind") : tr("tipos", "kinds")}
          </small>
        )}
      </span>
      {view.undeclared ? (
        <span className="res-ring-empty" aria-hidden="true" />
      ) : (
        <Ring done={view.available} total={view.kinds} label={tr("tipos con existencias", "kinds in stock")}>
          <span className="num res-ring-value">{formatNumber(share)} %</span>
        </Ring>
      )}
      <span className="res-category-side">
        <span className="secondary">{tr("Autonomía mínima", "Minimum autonomy")}</span>
        {view.undeclared ? (
          <Undeclared />
        ) : view.minAutonomyDays === null ? (
          <Undeclared>{tr("sin consumo declarado", "no declared use")}</Undeclared>
        ) : (
          <strong
            className="num"
            title={tr(
              "La del artículo que antes se acaba, de los que tienen consumo declarado",
              "That of the item that runs out first, among those with a declared use",
            )}
          >
            {formatDays(view.minAutonomyDays)}
          </strong>
        )}
        {!view.undeclared && (
          <span className="res-pills">
            <span
              className="res-pill"
              title={tr(
                "Autonomía por debajo del mínimo declarado para el artículo",
                "Autonomy below the minimum declared for the item",
              )}
            >
              <MarkOf mark={BELOW_MINIMUM_MARK}>
                {tr("Bajo mínimo", "Below minimum")} (<span className="num">{formatNumber(view.belowMinimum)}</span>)
              </MarkOf>
            </span>
            <span className="res-pill" title={tr("Artículos con existencias declaradas", "Items with declared stock")}>
              <MarkOf mark={OK_MARK}>
                {tr("Con existencias", "In stock")} (<span className="num">{formatNumber(view.available)}</span>)
              </MarkOf>
            </span>
          </span>
        )}
      </span>
    </li>
  );
}

export function ReservesStatus({
  inventory,
  children,
  only,
}: {
  inventory: Load<Inventory>;
  /** Las categorías que se enseñan; sin pasarla, todas (la maqueta V2 solo lleva medicamentos y equipo). */
  only?: readonly string[] | undefined;
  /** El mando y el formulario de declarar, si quien monta lo permite. */
  children?: ReactNode;
}) {
  const value = inventory.state === "ready" ? inventory.value : null;
  return (
    <section
      data-ui="home-reserves-status"
      className="ref-card res-status"
      aria-label={tr("Recursos e inventario", "Resources and inventory")}
    >
      <PanelTitle concept="resources" className="ref-h">
        {tr("Recursos e inventario: estado y autonomía", "Resources and inventory: status and autonomy")}
      </PanelTitle>
      <Pending item={inventory} />
      {value !== null && (
        <>
          {!value.declared && (
            <p className="secondary">
              <Undeclared>
                {tr(
                  "Sin existencias declaradas: nadie ha firmado un recuento.",
                  "No stock declared: nobody has signed a count.",
                )}
              </Undeclared>
            </p>
          )}
          <ul className="res-categories">
            {categoryViews(value)
              .filter((view) => only === undefined || only.includes(view.id))
              .map((view) => (
              <CategoryLine key={view.id} view={view} />
            ))}
          </ul>
        </>
      )}
      {children}
    </section>
  );
}

export function ReservesMedications({ inventory }: { inventory: Load<Inventory> }) {
  const value = inventory.state === "ready" ? inventory.value : null;
  const rows = medicationRows(value?.categories.find((item) => item.id === "medications"));
  return (
    <section
      data-ui="home-reserves-medications"
      className="ref-card res-medications"
      aria-label={tr("Medicamentos", "Medications")}
    >
      <PanelTitle concept="resources" className="ref-h">
        {tr("Medicamentos: gestión", "Medications: management")}
      </PanelTitle>
      <Pending item={inventory} />
      {value !== null &&
        (rows.length === 0 ? (
          <p>
            <Undeclared />
          </p>
        ) : (
          <div className="res-scroll">
            <table className="res-table">
              <thead>
                <tr>
                  <th scope="col">{tr("Artículo", "Item")}</th>
                  <th scope="col">{tr("Existencias", "Stock")}</th>
                  <th scope="col">{tr("Autonomía", "Autonomy")}</th>
                  <th scope="col">{tr("Alternativas (misma familia)", "Alternatives (same family)")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={row.id}
                    title={
                      tr(`Recuento de ${row.declaredBy}, ${utc(row.countedAt)}`, `Count by ${row.declaredBy}, ${utc(row.countedAt)}`) +
                      (row.expires === null ? "" : tr(`; caduca ${row.expires}`, `; expires ${row.expires}`))
                    }
                  >
                    <th scope="row">
                      {row.name}
                      {row.family !== null && <small className="secondary"> · {row.family}</small>}
                    </th>
                    <td className="num">{row.stock}</td>
                    <td>
                      {row.autonomyDays === null ? (
                        <Undeclared>{tr("sin consumo", "no declared use")}</Undeclared>
                      ) : row.belowMinimum ? (
                        <MarkOf
                          mark={BELOW_MINIMUM_MARK}
                          title={
                            row.minDays === null
                              ? undefined
                              : tr(
                                  `Por debajo del mínimo declarado de ${formatDays(row.minDays)}`,
                                  `Below the declared minimum of ${formatDays(row.minDays)}`,
                                )
                          }
                        >
                          <span className="num">{formatDays(row.autonomyDays)}</span>
                        </MarkOf>
                      ) : (
                        <span className="num">{formatDays(row.autonomyDays)}</span>
                      )}
                    </td>
                    <td>
                      {row.family === null ? (
                        <Undeclared>{tr("sin familia declarada", "no family declared")}</Undeclared>
                      ) : row.alternatives.length === 0 ? (
                        <span className="secondary">{tr("ninguna con existencias", "none in stock")}</span>
                      ) : (
                        row.alternatives.join(", ")
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
    </section>
  );
}

export interface NutritionData {
  food: Load<FoodAcceptability>;
  readings: Load<LatestReading[]>;
}

export function ReservesNutrition({ nutrition, level }: { nutrition: NutritionData; level?: string | null | undefined }) {
  const { food, readings } = nutrition;
  return (
    <section
      data-ui="home-reserves-nutrition"
      className="ref-card res-nutrition"
      aria-label={tr("Alimentación y nutrición", "Food and nutrition")}
    >
      <PanelTitle pictogram="fork-knife" className="ref-h">
        {tr("Alimentación y nutrición", "Food and nutrition")}
      </PanelTitle>
      <dl className="res-kv">
        {level !== undefined && (
          <div className="res-kv-row">
            <dt>{tr("Dominio nutrición", "Nutrition domain")}</dt>
            <dd>{level === null ? <Undeclared>{tr("sin nivel", "no level")}</Undeclared> : <LevelBadge level={level} />}</dd>
          </div>
        )}
        {readings.state !== "ready" ? (
          <div className="res-kv-row">
            <dt>{tr("Lecturas", "Readings")}</dt>
            <dd>
              <Pending item={readings} />
            </dd>
          </div>
        ) : (
          readings.value.map(({ key, display, latest }) => (
            <div key={key} className="res-kv-row">
              <dt>{display}</dt>
              <dd>
                {latest === null ? (
                  <MarkOf mark={MISSING_MARK}>{tr("sin lecturas", "no readings")}</MarkOf>
                ) : (
                  <span>
                    <span className="num">{formatNumber(latest.value)}</span> <small>{unitText(latest.unit)}</small>{" "}
                    <small className="secondary">· {utc(latest.at)}</small>
                  </span>
                )}
              </dd>
            </div>
          ))
        )}
      </dl>
      {food.state !== "ready" ? (
        <Pending item={food} />
      ) : (
        <div className="res-food">
          <span className="ref-h3">{food.value.display_es}</span>
          <p>
            {food.value.rated === 0 ? <MarkOf mark={MISSING_MARK}>{food.value.statement}</MarkOf> : food.value.statement}
          </p>
          {food.value.rated > 0 && (
            <p className="secondary">
              <span className="num">{formatNumber(food.value.rated)}</span> {tr("valoraciones", food.value.rated === 1 ? "rating" : "ratings")}
              {food.value.below !== null && (
                <>
                  {" "}
                  · <span className="num">{formatNumber(food.value.below)}</span> {tr("por debajo del criterio", "below the criterion")}
                </>
              )}
              {food.value.dishes !== undefined && (
                <>
                  {" "}
                  · <span className="num">{formatNumber(food.value.dishes.length)}</span> {tr("platos", food.value.dishes.length === 1 ? "dish" : "dishes")}
                </>
              )}
            </p>
          )}
        </div>
      )}
    </section>
  );
}

export function ReservesResupply({
  inventory,
  reference,
  profileId,
}: {
  inventory: Load<Inventory>;
  reference: number;
  profileId: string | null;
}) {
  const value = inventory.state === "ready" ? inventory.value : null;
  const resupply = resupplyView(value, reference);
  const coverage = coverageRows(value, reference);
  const place = profileId === null ? null : (PROFILE_SHORT[profileId] ?? profileId);
  return (
    <section
      data-ui="home-reserves-resupply"
      className="ref-card res-resupply"
      aria-label={tr("Abastecimiento", "Resupply")}
    >
      <PanelTitle pictogram="rocket" className="ref-h">
        {tr("Abastecimiento", "Resupply")}
      </PanelTitle>
      {/* El perfil va en su línea: en el título partía la tarjeta estrecha en dos renglones. */}
      {place !== null && (
        <p className="secondary res-place">
          {tr("Ubicación:", "Location:")} {place}
        </p>
      )}
      <Pending item={inventory} />
      {value !== null && (
        <>
          <div className="res-next">
            <span className="ref-h3">{tr("Próximo reabastecimiento", "Next resupply")}</span>
            {resupply === null ? (
              <Undeclared>{tr("sin reabastecimiento declarado", "no resupply declared")}</Undeclared>
            ) : (
              <dl className="res-kv">
                <dt>{tr("Vehículo", "Vehicle")}</dt>
                <dd>{resupply.name}</dd>
                <dt>{tr("Llegada declarada", "Declared arrival")}</dt>
                <dd>
                  <span className="num">{utc(resupply.eta)}</span>
                  {resupply.daysToEta !== null && (
                    <small className="secondary">
                      {" "}
                      ·{" "}
                      {resupply.daysToEta < 0 && language() === "en" ? (
                        <>
                          <span className="num">{formatDays(Math.abs(resupply.daysToEta))}</span> ago
                        </>
                      ) : (
                        <>
                          {resupply.daysToEta >= 0 ? tr("en", "in") : "hace"}{" "}
                          <span className="num">{formatDays(Math.abs(resupply.daysToEta))}</span>
                        </>
                      )}
                    </small>
                  )}
                </dd>
                <dt>{tr("Capacidad", "Capacity")}</dt>
                <dd>
                  {resupply.capacityKg === null ? (
                    <Undeclared />
                  ) : (
                    <>
                      <span className="num">{formatNumber(resupply.capacityKg)}</span> <small>kg</small>
                    </>
                  )}
                </dd>
                <dt>{tr("Declarado", "Declared")}</dt>
                <dd className="secondary">
                  {resupply.declaredBy} · {utc(resupply.declaredAt)}
                </dd>
              </dl>
            )}
          </div>
          <div className="res-coverage">
            <span
              className="ref-h3"
              title={tr(
                "Autonomía mínima declarada más los días hasta la llegada declarada",
                "Declared minimum autonomy plus the days until the declared arrival",
              )}
            >
              {tr("Cobertura proyectada (con reabastecimiento)", "Projected coverage (with resupply)")}
            </span>
            {coverage.length === 0 ? (
              <Undeclared />
            ) : (
              <ul>
                {coverage.map((row) => (
                  <li key={row.id}>
                    <span>{row.label}</span>
                    {row.projectedDays === null || row.marginDays === null ? (
                      <Undeclared>
                        {row.autonomyDays === null
                          ? tr("sin consumo declarado", "no declared use")
                          : tr("sin llegada declarada", "no arrival declared")}
                      </Undeclared>
                    ) : (
                      <span
                        title={tr(
                          `Autonomía ${formatDays(row.autonomyDays ?? 0)} + ${formatDays(row.projectedDays - (row.autonomyDays ?? 0))} hasta la llegada. Supone que el reabastecimiento repone lo que se gaste hasta entonces.`,
                          `Autonomy ${formatDays(row.autonomyDays ?? 0)} + ${formatDays(row.projectedDays - (row.autonomyDays ?? 0))} until arrival. Assumes the resupply replaces what is used up by then.`,
                        )}
                      >
                        <span className="num">{formatDays(row.projectedDays)}</span>{" "}
                        {row.marginDays < 0 ? (
                          <MarkOf mark={BELOW_MINIMUM_MARK}>
                            <small>
                              {tr("se acaba", "runs out")} <span className="num">{formatDays(-row.marginDays)}</span>{" "}
                              {tr("antes de la llegada", "before arrival")}
                            </small>
                          </MarkOf>
                        ) : (
                          <small className="secondary">
                            ({tr("margen", "margin")} <span className="num">{formatDays(row.marginDays)}</span>)
                          </small>
                        )}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </section>
  );
}

/** El formulario pequeño de recuento: firma un asiento `inventory-count` con quien está en la consola. */
export function CountFormView({
  inventory,
  form,
  setForm,
  operator,
  setOperator,
  countedAt,
  onSign,
  busy,
  error,
  signed,
}: {
  inventory: Inventory | null;
  form: CountForm;
  setForm: (next: CountForm) => void;
  operator: string;
  setOperator: (next: string) => void;
  countedAt: string;
  onSign: () => void;
  busy: boolean;
  error: RequestOutcome | null;
  signed: number | null;
}) {
  const categories = categoryViews(inventory);
  const items = inventory?.categories.find((item) => item.id === form.category)?.items ?? [];
  const ready = countBody(form, operator, countedAt) !== null;
  const field = (key: keyof CountForm) => ({
    value: form[key],
    onChange: (event: { target: { value: string } }) => setForm({ ...form, [key]: event.target.value }),
  });
  return (
    <form
      className="res-form"
      aria-label={tr("Declarar existencias", "Declare stock")}
      onSubmit={(event) => {
        event.preventDefault();
        if (ready && !busy) onSign();
      }}
    >
      <select
        aria-label={tr("Categoría", "Category")}
        value={form.category}
        onChange={(event) => setForm({ ...EMPTY_COUNT, category: event.target.value })}
      >
        <option value="">{tr("Categoría…", "Category…")}</option>
        {categories.map((item) => (
          <option key={item.id} value={item.id}>
            {item.label}
          </option>
        ))}
      </select>
      <select
        aria-label={tr("Artículo", "Item")}
        value={form.item}
        disabled={form.category === ""}
        onChange={(event) => setForm(pickItem(form, inventory, event.target.value))}
      >
        <option value="">{tr("Artículo nuevo…", "New item…")}</option>
        {items.map((item) => (
          <option key={item.id} value={item.id}>
            {item.name}
          </option>
        ))}
      </select>
      {/* Los rótulos y las pistas se traducen; lo que se teclea se firma tal cual, sin traducir. */}
      <input
        aria-label={tr("Nombre del artículo", "Item name")}
        placeholder={tr("nombre", "name")}
        maxLength={120}
        {...field("name")}
      />
      <input
        aria-label={tr("Unidad", "Unit")}
        placeholder={tr("unidad (u., raciones…)", "unit (u., servings…)")}
        maxLength={30}
        {...field("unit")}
      />
      <input
        aria-label={tr("Cantidad", "Quantity")}
        placeholder={tr("cantidad", "quantity")}
        inputMode="decimal"
        {...field("quantity")}
      />
      <input
        aria-label={tr("Consumo diario (opcional)", "Daily use (optional)")}
        placeholder={tr("consumo/día (opcional)", "use/day (optional)")}
        inputMode="decimal"
        {...field("dailyUse")}
      />
      <input
        aria-label={tr("Familia (opcional)", "Family (optional)")}
        placeholder={tr("familia (opcional)", "family (optional)")}
        maxLength={60}
        {...field("family")}
      />
      <input
        aria-label={tr("Mínimo de días (opcional)", "Minimum days (optional)")}
        placeholder={tr("mínimo de días (opcional)", "minimum days (optional)")}
        inputMode="decimal"
        {...field("minDays")}
      />
      <input aria-label={tr("Caducidad (opcional)", "Expiry (optional)")} type="date" {...field("expires")} />
      {operator.trim() === "" && (
        <input
          aria-label={tr("Quién declara", "Declared by")}
          placeholder={tr("quién declara", "declared by")}
          maxLength={80}
          value={operator}
          onChange={(event) => setOperator(event.target.value)}
        />
      )}
      <Command concept="declare" type="submit" disabled={!ready || busy}>
        {tr("Firmar recuento", "Sign count")}
      </Command>
      <span className="secondary">
        {tr("recuento a", "count at")} <span className="num">{utc(countedAt)}</span> · {tr("firma", "signed by")}{" "}
        {operator.trim() === "" ? "—" : operator.trim()}
        {signed !== null && (
          <>
            {" "}
            ·{" "}
            <MarkOf mark={OK_MARK}>
              {tr("firmado, asiento", "signed, entry")} <span className="num">{formatNumber(signed)}</span>
            </MarkOf>
          </>
        )}
      </span>
      {error !== null && <MarkOf mark={error.mark}>{error.text}</MarkOf>}
    </form>
  );
}

// ------------------------------------------------------------------------------------ el bloque

const V2_CATEGORIES = ["medications", "medical-equipment"] as const;

export interface HomeReservesProps {
  /** El perfil enseñado en «Ubicación de la tripulación» (`home.shownRoute`). */
  profileId: string | null;
  /** El tripulante de la consola: de él es la nutrición. */
  subject: string;
  /** La referencia de los datos, en milisegundos (`home.reference`): días hasta la llegada y hora del recuento. */
  reference: number;
  /** El nivel del dominio de nutrición del estado, si quien monta lo pasa; sin pasarlo no se pinta. */
  nutritionLevel?: string | null;
  /** Corte de reloj (consola de Tierra): lo declarado hasta ese instante. */
  until?: Date;
  /** Si se puede declarar existencias desde aquí (la consola de a bordo). */
  canDeclare?: boolean;
  /** Si «Inicio» está a la vista: oculto, no se piden los datos. */
  active?: boolean;
  /**
   * La maqueta V2 de la ISS (2026-11-14): sin la tarjeta de nutrición y sin la fila de alimentos en
   * el estado; medicamentos y abastecimiento, más anchos (`res-v2` en `homeReserves.css`).
   */
  v2?: boolean;
}

function load<T>(promise: Promise<T>, alive: () => boolean, set: (next: Load<T>) => void): void {
  promise
    .then((value) => {
      if (alive()) set({ state: "ready", value });
    })
    .catch((reason: unknown) => {
      if (alive()) set({ state: "failed", outcome: requestOutcome(reason) });
    });
}

export function HomeReserves({
  profileId,
  subject,
  reference,
  nutritionLevel,
  until,
  canDeclare = true,
  active = true,
  v2 = false,
}: HomeReservesProps) {
  const [inventory, setInventory] = useState<Load<Inventory>>({ state: "loading" });
  const [food, setFood] = useState<Load<FoodAcceptability>>({ state: "loading" });
  const [readings, setReadings] = useState<Load<LatestReading[]>>({ state: "loading" });
  const [reload, setReload] = useState(0);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<CountForm>(EMPTY_COUNT);
  const [operator, setOperator] = useOperator();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<RequestOutcome | null>(null);
  const [signed, setSigned] = useState<number | null>(null);
  const untilIso = until?.toISOString();

  useEffect(() => {
    if (!active) return undefined;
    let current = true;
    load(inventoryApi.get(untilIso === undefined ? undefined : new Date(untilIso)), () => current, setInventory);
    return () => {
      current = false;
    };
  }, [active, untilIso, reload]);

  useEffect(() => {
    // Sin la tarjeta de nutrición (V2) no se piden sus datos.
    if (!active || v2) return undefined;
    let current = true;
    const alive = () => current;
    load(nutritionApi.foodAcceptability(subject, 1), alive, setFood);
    load(
      Promise.all([
        api.indicators().then((body) => new Map(body.indicators.map((item) => [item.key, item]))),
        ...NUTRITION_KEYS.map((key) => api.observations(key, 1, subject, untilIso).then((body) => body.observations)),
      ]).then(([catalog, ...series]) =>
        NUTRITION_KEYS.map((key, index) =>
          latestReading(key, (series[index] ?? []) as FhirObservation[], catalog as Map<string, Indicator>),
        ),
      ),
      alive,
      setReadings,
    );
    return () => {
      current = false;
    };
  }, [active, v2, subject, untilIso]);

  const countedAt = Number.isFinite(reference) ? new Date(reference).toISOString() : new Date().toISOString();
  const value = inventory.state === "ready" ? inventory.value : null;
  const sign = () => {
    const body = countBody(form, operator, countedAt);
    if (body === null) return;
    setBusy(true);
    setError(null);
    inventoryApi
      .count(body)
      .then((answer) => {
        setSigned(answer.ledger_index);
        setForm(EMPTY_COUNT);
        setReload((count) => count + 1);
      })
      .catch((cause: unknown) => setError(requestOutcome(cause)))
      .finally(() => setBusy(false));
  };

  return (
    <>
      <ReservesStatus inventory={inventory} only={v2 ? V2_CATEGORIES : undefined}>
        {canDeclare && (
          <div className="res-declare">
            <Command concept="declare" type="button" aria-expanded={open} onClick={() => setOpen(!open)}>
              {open ? tr("Cerrar", "Close") : tr("Declarar existencias", "Declare stock")}
            </Command>
            {open && (
              <CountFormView
                inventory={value}
                form={form}
                setForm={setForm}
                operator={operator}
                setOperator={setOperator}
                countedAt={countedAt}
                onSign={sign}
                busy={busy}
                error={error}
                signed={signed}
              />
            )}
          </div>
        )}
      </ReservesStatus>
      <ReservesMedications inventory={inventory} />
      {!v2 && <ReservesNutrition nutrition={{ food, readings }} level={nutritionLevel} />}
      <ReservesResupply inventory={inventory} reference={reference} profileId={profileId} />
    </>
  );
}

