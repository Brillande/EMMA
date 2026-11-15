import { useCallback, useEffect, useState } from "react";

import { Command } from "../components/Command";
import { Fold } from "../components/Fold";
import { MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { formatHouseholdTime, formatNumber } from "../lib/format";
import {
  EMPTY_MARK,
  LOADING_MARK,
  OK_MARK,
  type RequestOutcome,
  requestOutcome,
} from "../lib/marks";
import { type EventForm, eventBody } from "./forms";
import { MEAL_SLOT_ORDER, addDays, dayPeriodLabel, householdDate, mealSlotLabel } from "./labels";
import {
  type BoardColumn,
  type CalendarEvent,
  type MenuEntry,
  type NewReminder,
  type PlannerMember,
  type Reminder,
  plannerApi,
} from "./plannerApi";
import { tr } from "../lib/i18n";

/**
 * El planificador de Marplanner (`marplanner/`) en la consola de tripulación, con el estilo de EMMA.
 *
 * Por qué existe: decisión del usuario (2026-11-12) de adoptar Marplanner entero y adaptar su
 * interfaz a la de EMMA. Sus pantallas originales (React + Tailwind, pensadas para la tableta de
 * una cocina) no se montan: cada pantalla útil a bordo se rehace aquí con los componentes, la
 * paleta y los formatos de EMMA. Los datos son de Marplanner, leídos por el backend de EMMA
 * (`/api/planner/app/*`), y su base es el ledger firmado (`planner-bridge/`).
 *
 * Reglas de EMMA que se respetan a propósito:
 *   - Color: ninguno propio. Marplanner da a cada miembro un color (azul, rojo…); en EMMA esos
 *     colores significan aviso o alerta (tabla F.5-1), así que aquí los nombres van sin color.
 *     Una tarea hecha lleva la marca común sin color (`OK_MARK`, el visto); una por hacer, el
 *     anillo punteado sin color (`EMPTY_MARK`), nunca el cian de «dato ausente».
 *   - Cifras y horas por `lib/format.ts`; la hora de un evento, en la zona del hogar que lo apuntó.
 *   - Nada de esto es dato de salud: no entra en el análisis ni en las alertas.
 *
 * El día de hoy es el del navegador (la zona del hogar en Marplanner es la de la casa; a bordo,
 * la consola y el planificador corren en la misma máquina).
 */

const TIME_ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone;

export function today(): string {
  return householdDate(new Date(), TIME_ZONE);
}

export interface Loaded<T> {
  data: T | null;
  failed: RequestOutcome | null;
  reload: () => void;
}

/** Carga con la forma de los demás paneles: lo último leído se queda si una relectura falla. */
export function useLoad<T>(load: () => Promise<T>, key: string): Loaded<T> {
  const [data, setData] = useState<{ key: string; value: T } | null>(null);
  const [failed, setFailed] = useState<RequestOutcome | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    load()
      .then((value) => {
        if (!alive) return;
        setData({ key, value });
        setFailed(null);
      })
      .catch((reason: unknown) => {
        if (alive) setFailed(requestOutcome(reason));
      });
    return () => {
      alive = false;
    };
    // `load` cambia con cada render; lo que decide releer es la clave y el pulso.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, tick]);
  const reload = useCallback(() => setTick((n) => n + 1), []);
  return { data: data?.key === key ? data.value : null, failed, reload };
}

export function State({ loaded, reading }: { loaded: Loaded<unknown>; reading: string }) {
  if (loaded.failed !== null) {
    return (
      <p>
        <MarkOf mark={loaded.failed.mark}>
          {loaded.data === null
            ? tr("No se pudo leer el planificador", "Could not read the planner")
            : tr("No se pudo actualizar", "Could not refresh")}
          :{" "}
          {loaded.failed.text}
        </MarkOf>
      </p>
    );
  }
  if (loaded.data === null) {
    return (
      <p className="secondary">
        <MarkOf mark={LOADING_MARK}>{reading}</MarkOf>
      </p>
    );
  }
  return null;
}

// --- Tareas del día ------------------------------------------------------------------------

export function PlannerChoresPanel() {
  const date = today();
  const board = useLoad(() => plannerApi.board(date), date);
  const [busy, setBusy] = useState<string | null>(null);
  const [writeFailed, setWriteFailed] = useState<RequestOutcome | null>(null);

  const toggle = async (column: BoardColumn, choreId: string, completed: boolean) => {
    const key = `${column.memberId}|${choreId}`;
    setBusy(key);
    setWriteFailed(null);
    try {
      if (completed) await plannerApi.uncomplete(choreId, column.memberId, date);
      else await plannerApi.complete(choreId, column.memberId, date);
      board.reload();
    } catch (reason: unknown) {
      setWriteFailed(requestOutcome(reason));
    } finally {
      setBusy(null);
    }
  };

  return (
    <section data-ui="planner-chores" className="panel" aria-label="Tareas del día">
      <PanelTitle concept="routines">Tareas del día</PanelTitle>
      <State loaded={board} reading="Leyendo las tareas…" />
      {writeFailed !== null && (
        <p>
          <MarkOf mark={writeFailed.mark}>No se guardó: {writeFailed.text}</MarkOf>
        </p>
      )}
      {board.data !== null && board.data.length === 0 && (
        <p className="secondary">
          <MarkOf mark={EMPTY_MARK}>No hay tareas asignadas hoy.</MarkOf>
        </p>
      )}
      <div className="planner-board">
      {board.data?.map((column) => (
        <div key={column.memberId} className="planner-column">
          <h3>
            {column.displayName}{" "}
            <span className="secondary">
              <span className="num">{formatNumber(column.todayProgress.completed)}</span> de{" "}
              <span className="num">{formatNumber(column.todayProgress.total)}</span> hechas · racha{" "}
              <span className="num">{formatNumber(column.streak)}</span>{" "}
              {column.streak === 1 ? "día" : "días"}
            </span>
          </h3>
          {column.dayPeriods
            .filter((period) => period.chores.length > 0)
            .map((period) => (
              <div key={period.id} className="planner-period">
                <h4>{dayPeriodLabel(period.labelKey)}</h4>
                <ul className="planner-list">
                  {period.chores.map((chore) => {
                    const key = `${column.memberId}|${chore.id}`;
                    return (
                      <li key={chore.id}>
                        <Command
                          pictogram={chore.completed ? "check" : "ring-dotted"}
                          aria-pressed={chore.completed}
                          disabled={busy !== null}
                          onClick={() => void toggle(column, chore.id, chore.completed)}
                        >
                          {chore.icon !== null && <span aria-hidden="true">{chore.icon} </span>}
                          {chore.name}
                          {busy === key && <span className="secondary"> · guardando…</span>}
                        </Command>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
        </div>
      ))}
      </div>
    </section>
  );
}

// --- Menú del día --------------------------------------------------------------------------

function slotRank(slot: string): number {
  const rank = (MEAL_SLOT_ORDER as readonly string[]).indexOf(slot);
  return rank === -1 ? MEAL_SLOT_ORDER.length : rank;
}

/** Una escritura en Marplanner: si se está guardando, y el último fallo, con la forma de la consola. */
export function useWrite(onDone: () => void) {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<RequestOutcome | null>(null);
  const run = async (write: () => Promise<unknown>) => {
    setBusy(true);
    setFailed(null);
    try {
      await write();
      onDone();
    } catch (reason: unknown) {
      setFailed(requestOutcome(reason));
    } finally {
      setBusy(false);
    }
  };
  const notice =
    failed === null ? null : (
      <p>
        <MarkOf mark={failed.mark}>No se guardó: {failed.text}</MarkOf>
      </p>
    );
  return { busy, run, notice };
}

export function PlannerMenuPanel() {
  const date = today();
  const menu = useLoad(() => plannerApi.menu(date), date);
  const write = useWrite(menu.reload);
  const [slot, setSlot] = useState<string>("dinner");
  const [note, setNote] = useState("");
  const entries: MenuEntry[] = (menu.data ?? [])
    .filter((entry) => !entry.isTombstone)
    .sort((a, b) => slotRank(a.slot) - slotRank(b.slot));
  return (
    <section data-ui="planner-menu" className="panel" aria-label="Menú del día">
      <PanelTitle concept="notes">Menú del día</PanelTitle>
      <State loaded={menu} reading="Leyendo el menú…" />
      {write.notice}
      {menu.data !== null && entries.length === 0 && (
        <p className="secondary">
          <MarkOf mark={EMPTY_MARK}>No hay comidas planificadas hoy.</MarkOf>
        </p>
      )}
      {entries.length > 0 && (
        <dl className="planner-menu">
          {entries.map((entry) => (
            <div key={entry.entryId}>
              <dt>{mealSlotLabel(entry.slot)}</dt>
              <dd>
                {entry.label}
                {entry.note !== null && entry.note !== "" && entry.note !== entry.label && (
                  <span className="secondary"> · {entry.note}</span>
                )}
                {/* Aquí solo se quita lo puntual de hoy; lo semanal es del plan de comidas. */}
                {entry.source === "oneoff" && (
                  <>
                    {" "}
                    <Command
                      pictogram="cross"
                      disabled={write.busy}
                      aria-label={`Quitar ${entry.label}`}
                      onClick={() => void write.run(() => plannerApi.deleteMeal(entry.entryId))}
                    >
                      Quitar
                    </Command>
                  </>
                )}
              </dd>
            </div>
          ))}
        </dl>
      )}
      <Fold data-ui="planner-menu-add" concept="declare" label="Añadir una comida para hoy">
        <div className="inline-form">
          <select value={slot} aria-label="Comida del día" onChange={(e) => setSlot(e.target.value)}>
            {MEAL_SLOT_ORDER.map((s) => (
              <option key={s} value={s}>
                {mealSlotLabel(s)}
              </option>
            ))}
          </select>
          <input
            value={note}
            maxLength={200}
            placeholder="qué se come"
            aria-label="Qué se come"
            onChange={(e) => setNote(e.target.value)}
          />
          <Command
            concept="register"
            disabled={write.busy || note.trim() === ""}
            onClick={() =>
              void write.run(async () => {
                await plannerApi.addMeal(date, slot, note.trim());
                setNote("");
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

// --- Calendario: hoy y los próximos días ---------------------------------------------------

const CALENDAR_DAYS = 7;

function eventDay(event: CalendarEvent): string {
  return householdDate(new Date(event.occurrenceStart), event.tzid ?? TIME_ZONE);
}

export function PlannerCalendarPanel() {
  const from = today();
  const to = addDays(from, CALENDAR_DAYS - 1);
  const events = useLoad(() => plannerApi.events(from, to), `${from}|${to}`);
  const members = useLoad(() => plannerApi.members(), "members");
  const write = useWrite(events.reload);
  const [form, setForm] = useState<EventForm>({ title: "", date: from, allDay: false, start: "09:00", end: "10:00" });
  const body = eventBody(form, TIME_ZONE);
  const names = new Map((members.data ?? []).map((m: PlannerMember) => [m.id, m.displayName]));
  const byDay = new Map<string, CalendarEvent[]>();
  for (const event of [...(events.data ?? [])].sort((a, b) => a.occurrenceStart.localeCompare(b.occurrenceStart))) {
    const day = event.allDay ? event.occurrenceStart.slice(0, 10) : eventDay(event);
    byDay.set(day, [...(byDay.get(day) ?? []), event]);
  }
  return (
    <section data-ui="planner-calendar" className="panel" aria-label="Calendario">
      <PanelTitle concept="nextDays">Calendario, próximos {formatNumber(CALENDAR_DAYS)} días</PanelTitle>
      <State loaded={events} reading="Leyendo el calendario…" />
      {write.notice}
      {events.data !== null && events.data.length === 0 && (
        <p className="secondary">
          <MarkOf mark={EMPTY_MARK}>Nada en el calendario estos días.</MarkOf>
        </p>
      )}
      {[...byDay].map(([day, list]) => (
        <div key={day} className="planner-day">
          <h3>
            <span className="num">{day}</span>
            {day === from && <span className="secondary"> · hoy</span>}
          </h3>
          <ul className="planner-list">
            {list.map((event) => (
              <li key={`${event.id}|${event.occurrenceStart}`}>
                <span className="num">
                  {event.allDay
                    ? "todo el día"
                    : formatHouseholdTime(event.occurrenceStart, event.tzid ?? TIME_ZONE)}
                </span>{" "}
                {event.title}
                {event.assignedTo.length > 0 && (
                  <span className="secondary">
                    {" "}
                    · {event.assignedTo.map((id) => memberName(names, members.data !== null, id)).join(", ")}
                  </span>
                )}
                {/* Solo los eventos locales se borran aquí; los de un calendario externo, en su origen. */}
                {event.source === "local" && (
                  <>
                    {" "}
                    <Command
                      pictogram="cross"
                      disabled={write.busy}
                      aria-label={`Borrar ${event.title}`}
                      onClick={() => void write.run(() => plannerApi.deleteEvent(event.id))}
                    >
                      Borrar
                    </Command>
                  </>
                )}
              </li>
            ))}
          </ul>
        </div>
      ))}
      <Fold data-ui="planner-calendar-add" concept="declare" label="Añadir un evento">
        <div className="inline-form">
          <input
            value={form.title}
            maxLength={200}
            placeholder="título"
            aria-label="Título del evento"
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
          <input
            type="date"
            value={form.date}
            aria-label="Día del evento"
            onChange={(e) => setForm({ ...form, date: e.target.value })}
          />
          <label>
            <input
              type="checkbox"
              checked={form.allDay}
              onChange={(e) => setForm({ ...form, allDay: e.target.checked })}
            />{" "}
            todo el día
          </label>
          {!form.allDay && (
            <>
              <input
                type="time"
                value={form.start}
                aria-label="Hora de inicio"
                onChange={(e) => setForm({ ...form, start: e.target.value })}
              />
              <input
                type="time"
                value={form.end}
                aria-label="Hora de fin"
                onChange={(e) => setForm({ ...form, end: e.target.value })}
              />
            </>
          )}
          <Command
            concept="register"
            disabled={write.busy || typeof body === "string"}
            onClick={() => {
              if (typeof body === "string") return;
              void write.run(async () => {
                await plannerApi.createEvent(body);
                setForm({ ...form, title: "" });
              });
            }}
          >
            Añadir
          </Command>
          <span className="secondary">{typeof body === "string" ? body : `hora de ${TIME_ZONE}`}</span>
        </div>
      </Fold>
    </section>
  );
}

// --- Recordatorios -------------------------------------------------------------------------

const WEEKDAYS: Record<string, string> = {
  mon: "lu", tue: "ma", wed: "mi", thu: "ju", fri: "vi", sat: "sá", sun: "do",
};

/**
 * El nombre de un miembro para enseñarlo. Mientras la lista de miembros no ha llegado, «…»: el
 * identificador interno de Marplanner (`demo:member:bart`) no es un nombre y no se enseña.
 */
export function memberName(names: ReadonlyMap<string, string>, loaded: boolean, id: string): string {
  return names.get(id) ?? (loaded ? id : "…");
}

export function weekdays(days: string[] | null): string {
  return days === null || days.length === 0 ? "todos los días" : days.map((d) => WEEKDAYS[d] ?? d).join(" ");
}

const WEEK = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;

/**
 * Los recordatorios del planificador: los activos y los pausados, y desde aquí se crea uno, se
 * pausa o reanuda y se borra. Solo los de texto programados: los que dependen del calendario
 * (`calendar_gated`) se ven pero se administran en Marplanner.
 */
export function PlannerRemindersPanel() {
  const reminders = useLoad(() => plannerApi.reminders(), "reminders");
  const members = useLoad(() => plannerApi.members(), "members");
  const write = useWrite(reminders.reload);
  const [text, setText] = useState("");
  const [who, setWho] = useState("");
  const [days, setDays] = useState<string[]>([...WEEK]);
  const names = new Map((members.data ?? []).map((m: PlannerMember) => [m.id, m.displayName]));
  const shown: Reminder[] = (reminders.data ?? []).filter((r) => r.text !== null);
  const toggleDay = (day: string) =>
    setDays(days.includes(day) ? days.filter((d) => d !== day) : WEEK.filter((d) => d === day || days.includes(d)));
  const create = () => {
    const body: NewReminder =
      who === ""
        ? { targetingMode: "apply_to_all", text: text.trim(), weekdays: days }
        : { targetingMode: "specific", text: text.trim(), assignments: [{ memberId: who, weekdays: days }] };
    void write.run(async () => {
      await plannerApi.createReminder(body);
      setText("");
    });
  };
  return (
    <section data-ui="planner-reminders" className="panel" aria-label="Recordatorios">
      <PanelTitle concept="waiting">Recordatorios</PanelTitle>
      <State loaded={reminders} reading="Leyendo los recordatorios…" />
      {write.notice}
      {reminders.data !== null && shown.length === 0 && (
        <p className="secondary">
          <MarkOf mark={EMPTY_MARK}>No hay recordatorios.</MarkOf>
        </p>
      )}
      <ul className="planner-list">
        {shown.map((reminder) => (
          <li key={reminder.id} className="planner-row">
            <span>
              {/* Pausado: el anillo sin color; activo, el visto común. Ninguno es una alerta. */}
              <MarkOf mark={reminder.active ? OK_MARK : EMPTY_MARK}>{reminder.text}</MarkOf>
              <span className="secondary">
                {" "}
                ·{" "}
                {reminder.targetingMode === "specific"
                  ? reminder.assignments
                      .filter((a) => a.active)
                      .map((a) => `${memberName(names, members.data !== null, a.memberId)} (${weekdays(a.weekdays)})`)
                      .join(", ")
                  : `todos (${weekdays(reminder.weekdays)})`}
                {!reminder.active && " · en pausa"}
              </span>
            </span>
            {reminder.kind === "scheduled" && (
              <span>
                <Command
                  pictogram={reminder.active ? "ring-dotted" : "check"}
                  disabled={write.busy}
                  onClick={() => void write.run(() => plannerApi.setReminderActive(reminder.id, !reminder.active))}
                >
                  {reminder.active ? "Pausar" : "Reanudar"}
                </Command>{" "}
                <Command
                  pictogram="cross"
                  disabled={write.busy}
                  aria-label={`Borrar el recordatorio ${reminder.text ?? ""}`}
                  onClick={() => void write.run(() => plannerApi.deleteReminder(reminder.id))}
                >
                  Borrar
                </Command>
              </span>
            )}
          </li>
        ))}
      </ul>
      <Fold data-ui="planner-reminders-add" concept="declare" label="Añadir un recordatorio">
        <div className="inline-form">
          <input
            value={text}
            maxLength={200}
            placeholder="qué hay que recordar"
            aria-label="Texto del recordatorio"
            onChange={(e) => setText(e.target.value)}
          />
          <select value={who} aria-label="Para quién" onChange={(e) => setWho(e.target.value)}>
            <option value="">todos</option>
            {(members.data ?? [])
              .filter((m) => m.lifecycle === "active")
              .map((m) => (
                <option key={m.id} value={m.id}>
                  {m.displayName}
                </option>
              ))}
          </select>
          <span role="group" aria-label="Días de la semana">
            {WEEK.map((day) => (
              <label key={day}>
                <input type="checkbox" checked={days.includes(day)} onChange={() => toggleDay(day)} />
                {weekdays([day])}{" "}
              </label>
            ))}
          </span>
          <Command
            concept="register"
            disabled={write.busy || text.trim() === "" || days.length === 0}
            onClick={create}
          >
            Añadir
          </Command>
        </div>
      </Fold>
    </section>
  );
}
