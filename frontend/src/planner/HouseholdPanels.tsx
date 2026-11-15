import { useState } from "react";

import { Command } from "../components/Command";
import { Fold } from "../components/Fold";
import { MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { EMPTY_MARK, OK_MARK } from "../lib/marks";
import { addDays, dayPeriodLabel } from "./labels";
import { State, today, useLoad, useWrite } from "./PlannerPanels";
import { plannerApi } from "./plannerApi";

/**
 * Lo que queda de la administración del planificador (Marplanner): los mensajes del día para cada
 * miembro, las franjas del día y los planes de comidas. Mismo estilo que el resto de
 * `planner/`; ninguno es dato de salud.
 */

const MESSAGE_DAYS = 7;

// --- Mensajes del día ------------------------------------------------------------------------

export function PlannerMessagesPanel() {
  const from = today();
  const members = useLoad(() => plannerApi.members(), "members");
  const active = (members.data ?? []).filter((m) => m.lifecycle === "active");
  const [chosen, setChosen] = useState("");
  const memberId = chosen !== "" ? chosen : (active[0]?.id ?? "");
  const messages = useLoad(
    () => (memberId === "" ? Promise.resolve([]) : plannerApi.dailyMessages(memberId, from, MESSAGE_DAYS)),
    `${memberId}|${from}`,
  );
  const write = useWrite(messages.reload);
  const [date, setDate] = useState(from);
  const [text, setText] = useState("");

  return (
    <section data-ui="planner-messages" className="panel" aria-label="Mensajes del día">
      <PanelTitle concept="notes">Mensajes del día</PanelTitle>
      <State loaded={members} reading="Leyendo los miembros…" />
      {write.notice}
      <div className="inline-form">
        <select value={memberId} aria-label="Para quién son los mensajes" onChange={(e) => setChosen(e.target.value)}>
          {active.map((m) => (
            <option key={m.id} value={m.id}>
              {m.displayName}
            </option>
          ))}
        </select>
        <span className="secondary">
          de <span className="num">{from}</span> a <span className="num">{addDays(from, MESSAGE_DAYS - 1)}</span>
        </span>
      </div>
      <State loaded={messages} reading="Leyendo los mensajes…" />
      {messages.data !== null && messages.data.length === 0 && (
        <p className="secondary">
          <MarkOf mark={EMPTY_MARK}>Sin mensajes estos días.</MarkOf>
        </p>
      )}
      <ul className="planner-list">
        {(messages.data ?? []).map((message) => (
          <li key={message.id} className="planner-row">
            <span>
              <span className="num">{message.date}</span>
              {message.date === from && <span className="secondary"> · hoy</span>} · {message.text}
            </span>
            <Command
              pictogram="cross"
              disabled={write.busy}
              aria-label={`Borrar el mensaje del ${message.date}`}
              onClick={() => void write.run(() => plannerApi.deleteDailyMessage(message.memberId, message.date))}
            >
              Borrar
            </Command>
          </li>
        ))}
      </ul>
      {memberId !== "" && (
        <Fold data-ui="planner-messages-add" concept="declare" label="Escribir un mensaje">
          <div className="inline-form">
            <input type="date" value={date} aria-label="Día del mensaje" onChange={(e) => setDate(e.target.value)} />
            <input
              value={text}
              maxLength={280}
              placeholder="mensaje"
              aria-label="Texto del mensaje"
              onChange={(e) => setText(e.target.value)}
            />
            <Command
              concept="register"
              disabled={write.busy || text.trim() === "" || date === ""}
              onClick={() =>
                void write.run(async () => {
                  await plannerApi.setDailyMessage(memberId, date, text.trim());
                  setText("");
                })
              }
            >
              Guardar
            </Command>
            <span className="secondary">un mensaje por persona y día: guardar otro lo sustituye</span>
          </div>
        </Fold>
      )}
    </section>
  );
}

// --- Franjas del día -------------------------------------------------------------------------

export function PlannerDayPeriodsPanel() {
  const periods = useLoad(() => plannerApi.dayPeriods(), "day-periods");
  const write = useWrite(periods.reload);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const list = [...(periods.data ?? [])].sort((a, b) => a.sortOrder - b.sortOrder);
  return (
    <section data-ui="planner-day-periods" className="panel" aria-label="Franjas del día">
      <PanelTitle concept="routines">Franjas del día</PanelTitle>
      <p className="secondary">Cada franja empieza a su hora y acaba cuando empieza la siguiente; ordenan las tareas.</p>
      <State loaded={periods} reading="Leyendo las franjas…" />
      {write.notice}
      <ul className="planner-list">
        {list.map((period) => {
          const value = edits[period.id] ?? period.start;
          return (
            <li key={period.id} className="planner-row">
              <span>{dayPeriodLabel(period.labelKey)}</span>
              <span className="inline-form">
                <input
                  type="time"
                  value={value}
                  aria-label={`Empieza ${dayPeriodLabel(period.labelKey)}`}
                  onChange={(e) => setEdits({ ...edits, [period.id]: e.target.value })}
                />
                <Command
                  concept="confirm"
                  disabled={write.busy || value === period.start}
                  onClick={() =>
                    void write.run(async () => {
                      await plannerApi.setDayPeriodStart(period.id, value);
                      const { [period.id]: _done, ...rest } = edits;
                      setEdits(rest);
                    })
                  }
                >
                  Guardar
                </Command>
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// --- Planes de comidas -----------------------------------------------------------------------

export function PlannerMealPlansPanel() {
  const plans = useLoad(() => plannerApi.mealPlans(), "meal-plans");
  const write = useWrite(plans.reload);
  const [name, setName] = useState("");
  return (
    <section data-ui="planner-meal-plans" className="panel" aria-label="Planes de comidas">
      <PanelTitle concept="nextDays">Planes de comidas</PanelTitle>
      <p className="secondary">El menú de cada día junta los planes activos y lo puntual.</p>
      <State loaded={plans} reading="Leyendo los planes…" />
      {write.notice}
      {plans.data !== null && plans.data.length === 0 && (
        <p className="secondary">
          <MarkOf mark={EMPTY_MARK}>No hay planes.</MarkOf>
        </p>
      )}
      <ul className="planner-list">
        {(plans.data ?? []).map((plan) => (
          <li key={plan.id} className="planner-row">
            <MarkOf mark={plan.active ? OK_MARK : EMPTY_MARK}>
              {plan.name}
              {!plan.active && <span className="secondary"> · desactivado</span>}
            </MarkOf>
            <Command
              pictogram={plan.active ? "ring-dotted" : "check"}
              disabled={write.busy}
              onClick={() => void write.run(() => plannerApi.setMealPlanActive(plan.id, !plan.active))}
            >
              {plan.active ? "Desactivar" : "Activar"}
            </Command>
          </li>
        ))}
      </ul>
      <Fold data-ui="planner-meal-plans-add" concept="declare" label="Añadir un plan">
        <div className="inline-form">
          <input
            value={name}
            maxLength={120}
            placeholder="nombre del plan"
            aria-label="Nombre del plan"
            onChange={(e) => setName(e.target.value)}
          />
          <Command
            concept="register"
            disabled={write.busy || name.trim() === ""}
            onClick={() =>
              void write.run(async () => {
                await plannerApi.createMealPlan(name.trim());
                setName("");
              })
            }
          >
            Añadir
          </Command>
        </div>
      </Fold>
    </section>
  );
}
