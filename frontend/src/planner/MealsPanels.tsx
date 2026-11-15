import { useState } from "react";

import { Command } from "../components/Command";
import { Fold } from "../components/Fold";
import { MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { formatNumber } from "../lib/format";
import { EMPTY_MARK, REFUSED_MARK } from "../lib/marks";
import { MEAL_SLOT_ORDER, mealSlotLabel } from "./labels";
import { State, today, useLoad, useWrite, weekdays } from "./PlannerPanels";
import { type Recipe, plannerApi } from "./plannerApi";

/**
 * Las comidas del planificador (Marplanner) más allá de hoy: el menú de la semana, las recetas y
 * los planes semanales que se repiten.
 *
 * Por qué así: en Marplanner el menú de un día es la unión de los planes semanales activos y lo
 * puntual (su ADR-045); aquí se enseña lo que él compone, sin recalcularlo. Borrar una receta en
 * Marplanner borra también las comidas que la usan (borrado informado, ADR-046): antes se dice
 * cuántas son y hay que confirmarlo, con el triángulo amarillo de «atención» (tabla F.5-1:
 * «caution… attention required»), porque es una acción que no se deshace.
 */

const WEEK = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;

export function PlannerWeekMenuPanel() {
  const date = today();
  const week = useLoad(() => plannerApi.weekMenu(date), `week|${date}`);
  const days = Object.keys(week.data ?? {}).sort();
  return (
    <section data-ui="planner-week-menu" className="panel" aria-label="Menú de la semana">
      <PanelTitle concept="nextDays">Menú de la semana</PanelTitle>
      <State loaded={week} reading="Leyendo el menú de la semana…" />
      {days.length > 0 && (
        <div className="planner-table-wrap">
          <table className="planner-table">
            <thead>
              <tr>
                <th scope="col">Día</th>
                {MEAL_SLOT_ORDER.map((slot) => (
                  <th key={slot} scope="col">
                    {mealSlotLabel(slot)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {days.map((day) => (
                <tr key={day}>
                  <th scope="row">
                    <span className="num">{day}</span>
                    {day === date && <span className="secondary"> · hoy</span>}
                  </th>
                  {MEAL_SLOT_ORDER.map((slot) => {
                    const entries = (week.data?.[day]?.[slot] ?? []).filter((e) => !e.isTombstone);
                    // Lo mismo dos veces (del plan y puntual) se dice una vez.
                    const labels = [...new Set(entries.map((e) => e.label))];
                    return <td key={slot}>{labels.length === 0 ? <span className="secondary">—</span> : labels.join(", ")}</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function splitList(text: string): string[] {
  return text
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item !== "");
}

export function PlannerRecipesPanel() {
  const recipes = useLoad(() => plannerApi.recipes(), "recipes");
  const plans = useLoad(() => plannerApi.mealPlans(), "meal-plans");
  const write = useWrite(recipes.reload);
  const [form, setForm] = useState({ name: "", ingredients: "", instructions: "", slots: ["dinner"] as string[] });
  const [pending, setPending] = useState<{ recipe: Recipe; recurring: number; oneOff: number } | null>(null);
  const [toPlan, setToPlan] = useState({ recipeId: "", planId: "", weekday: "mon", slot: "dinner" });
  const list = [...(recipes.data ?? [])].sort((a, b) => a.name.localeCompare(b.name));
  const activePlans = (plans.data ?? []).filter((p) => p.active);
  const chosenRecipe = toPlan.recipeId !== "" ? toPlan.recipeId : (list[0]?.id ?? "");
  const chosenPlan = toPlan.planId !== "" ? toPlan.planId : (activePlans[0]?.id ?? "");

  const askDelete = (recipe: Recipe) =>
    void write.run(async () => {
      const deps = await plannerApi.recipeDependents(recipe.id);
      setPending({ recipe, recurring: deps.recurringCount, oneOff: deps.oneOffCount });
    });

  return (
    <section data-ui="planner-recipes" className="panel" aria-label="Recetas">
      <PanelTitle concept="docs">Recetas</PanelTitle>
      <State loaded={recipes} reading="Leyendo las recetas…" />
      {write.notice}
      {pending !== null && (
        <div className="inline-form" role="alert">
          <MarkOf mark={REFUSED_MARK}>
            Borrar «{pending.recipe.name}» quita también{" "}
            <span className="num">{formatNumber(pending.recurring)}</span>{" "}
            {pending.recurring === 1 ? "comida del plan semanal" : "comidas del plan semanal"} y{" "}
            <span className="num">{formatNumber(pending.oneOff)}</span>{" "}
            {pending.oneOff === 1 ? "puntual" : "puntuales"}. No se deshace.
          </MarkOf>
          <Command
            pictogram="cross"
            hazard
            disabled={write.busy}
            onClick={() =>
              void write.run(async () => {
                await plannerApi.deleteRecipe(pending.recipe.id);
                setPending(null);
              })
            }
          >
            Borrar la receta
          </Command>
          <Command concept="cancel" disabled={write.busy} onClick={() => setPending(null)}>
            No borrar
          </Command>
        </div>
      )}
      {recipes.data !== null && list.length === 0 && (
        <p className="secondary">
          <MarkOf mark={EMPTY_MARK}>No hay recetas.</MarkOf>
        </p>
      )}
      <ul className="planner-list">
        {list.map((recipe) => (
          <li key={recipe.id} className="planner-row">
            <span>
              {recipe.name}{" "}
              <span className="secondary">
                · {recipe.slots.map(mealSlotLabel).join(", ")}
                {recipe.ingredients.length > 0 && <> · {recipe.ingredients.join(", ")}</>}
              </span>
            </span>
            <Command
              pictogram="cross"
              disabled={write.busy}
              aria-label={`Borrar la receta ${recipe.name}`}
              onClick={() => askDelete(recipe)}
            >
              Borrar
            </Command>
          </li>
        ))}
      </ul>
      <Fold data-ui="planner-recipes-add" concept="declare" label="Añadir una receta">
        <div className="inline-form">
          <input
            value={form.name}
            maxLength={120}
            placeholder="nombre"
            aria-label="Nombre de la receta"
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <input
            value={form.ingredients}
            maxLength={500}
            placeholder="ingredientes, separados por comas"
            aria-label="Ingredientes, separados por comas"
            onChange={(e) => setForm({ ...form, ingredients: e.target.value })}
          />
          <input
            value={form.instructions}
            maxLength={2000}
            placeholder="cómo se hace"
            aria-label="Cómo se hace"
            onChange={(e) => setForm({ ...form, instructions: e.target.value })}
          />
          <span role="group" aria-label="Para qué comidas">
            {MEAL_SLOT_ORDER.map((slot) => (
              <label key={slot}>
                <input
                  type="checkbox"
                  checked={form.slots.includes(slot)}
                  onChange={() =>
                    setForm({
                      ...form,
                      slots: form.slots.includes(slot)
                        ? form.slots.filter((s) => s !== slot)
                        : MEAL_SLOT_ORDER.filter((s) => s === slot || form.slots.includes(s)),
                    })
                  }
                />
                {mealSlotLabel(slot)}{" "}
              </label>
            ))}
          </span>
          <Command
            concept="register"
            disabled={write.busy || form.name.trim() === "" || form.slots.length === 0}
            onClick={() =>
              void write.run(async () => {
                await plannerApi.createRecipe({
                  name: form.name.trim(),
                  ingredients: splitList(form.ingredients),
                  instructions: form.instructions.trim(),
                  slots: form.slots,
                });
                setForm({ name: "", ingredients: "", instructions: "", slots: ["dinner"] });
              })
            }
          >
            Añadir
          </Command>
        </div>
      </Fold>
      {list.length > 0 && activePlans.length > 0 && (
        <Fold data-ui="planner-recipes-plan" concept="declare" label="Poner una receta en el plan semanal">
          <div className="inline-form">
            <select
              value={chosenRecipe}
              aria-label="Receta"
              onChange={(e) => setToPlan({ ...toPlan, recipeId: e.target.value })}
            >
              {list.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
            <select value={chosenPlan} aria-label="Plan" onChange={(e) => setToPlan({ ...toPlan, planId: e.target.value })}>
              {activePlans.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <select
              value={toPlan.weekday}
              aria-label="Día de la semana"
              onChange={(e) => setToPlan({ ...toPlan, weekday: e.target.value })}
            >
              {WEEK.map((d) => (
                <option key={d} value={d}>
                  {weekdays([d])}
                </option>
              ))}
            </select>
            <select value={toPlan.slot} aria-label="Comida" onChange={(e) => setToPlan({ ...toPlan, slot: e.target.value })}>
              {MEAL_SLOT_ORDER.map((s) => (
                <option key={s} value={s}>
                  {mealSlotLabel(s)}
                </option>
              ))}
            </select>
            <Command
              concept="register"
              disabled={write.busy || chosenRecipe === "" || chosenPlan === ""}
              onClick={() =>
                void write.run(() =>
                  plannerApi.addRecurringMeal(chosenPlan, toPlan.weekday, toPlan.slot, chosenRecipe),
                )
              }
            >
              Añadir al plan
            </Command>
          </div>
        </Fold>
      )}
    </section>
  );
}
