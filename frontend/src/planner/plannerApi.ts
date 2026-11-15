/**
 * Lo que la consola lee y escribe del planificador (Marplanner), a través de EMMA.
 *
 * Por qué existe aparte de `lib/api.ts`: el planificador no es dato de salud ni pasa por el
 * análisis. Su API es la de Marplanner (`marplanner/docs/api/openapi.json`), servida por el
 * backend en `/api/planner/app/*` (`backend/app/planner_link.py`), que guarda su clave de
 * dispositivo: la consola no maneja credenciales de Marplanner. Los tipos son solo los campos que
 * enseñan las pantallas; lo demás que mande Marplanner se ignora.
 */

import { ApiError, withConsoleHeader } from "../lib/api";
import type { TimeRule } from "./announcements";

const BASE = "/api/planner/app";

export interface PlannerMember {
  id: string;
  displayName: string;
  role: string;
  lifecycle: string;
}

export interface BoardChore {
  id: string;
  name: string;
  icon: string | null;
  completed: boolean;
}

export interface BoardPeriod {
  id: string;
  labelKey: string;
  chores: BoardChore[];
}

export interface BoardColumn {
  memberId: string;
  displayName: string;
  dayPeriods: BoardPeriod[];
  streak: number;
  todayProgress: { completed: number; total: number };
}

export interface MenuEntry {
  entryId: string;
  slot: string;
  label: string;
  isTombstone: boolean;
  source: string;
  note: string | null;
}

export interface CalendarEvent {
  id: string;
  occurrenceStart: string;
  occurrenceEnd: string | null;
  source: string;
  title: string;
  allDay: boolean;
  assignedTo: string[];
  tzid: string | null;
}

export interface ReminderAssignment {
  memberId: string;
  weekdays: string[] | null;
  active: boolean;
}

export interface Reminder {
  id: string;
  kind: string;
  text: string | null;
  active: boolean;
  weekdays: string[] | null;
  targetingMode: string;
  assignments: ReminderAssignment[];
}

/** Un evento nuevo, como lo pide Marplanner: de día entero (fin exclusivo) o con hora en una zona. */
export type NewEvent =
  | { title: string; allDay: true; startDate: string; endDate: string }
  | { title: string; allDay: false; startUtc: string; endUtc: string; tzid: string };

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, withConsoleHeader(init));
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: unknown; error?: unknown; message?: unknown };
      const said = body.detail ?? body.message ?? body.error;
      if (said !== undefined) detail = typeof said === "string" ? said : JSON.stringify(said);
    } catch {
      // cuerpo no JSON: se queda el texto de estado
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const q = (params: Record<string, string>) => new URLSearchParams(params).toString();

export const plannerApi = {
  // Todos, también los archivados: Marplanner, sin `lifecycle`, da solo los activos, y un archivado
  // tiene que seguir con su nombre en lo que hizo y poder recuperarse (visto el 2026-11-12).
  members: () => call<PlannerMember[]>("/members?lifecycle=all"),
  board: (date: string) => call<BoardColumn[]>(`/chores/board?${q({ date })}`),
  complete: (choreId: string, memberId: string, date: string) =>
    call<void>(`/chores/${encodeURIComponent(choreId)}/completions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ memberId, date }),
    }),
  uncomplete: (choreId: string, memberId: string, date: string) =>
    call<void>(`/chores/${encodeURIComponent(choreId)}/completions?${q({ memberId, date })}`, {
      method: "DELETE",
    }),
  menu: (date: string) => call<MenuEntry[]>(`/menu?${q({ date })}`),
  events: (from: string, to: string) => call<CalendarEvent[]>(`/calendar/events?${q({ from, to })}`),
  reminders: () => call<Reminder[]>("/reminders"),
  createEvent: (body: NewEvent) =>
    call<{ id: string }>("/calendar/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  deleteEvent: (id: string) => call<void>(`/calendar/events/${encodeURIComponent(id)}`, { method: "DELETE" }),
  addMeal: (date: string, slot: string, note: string) =>
    call<{ id: string }>("/meal-entries", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: "oneoff", date, slot, note }),
    }),
  deleteMeal: (entryId: string) =>
    call<void>(`/meal-entries/${encodeURIComponent(entryId)}`, { method: "DELETE" }),
  routines: () => call<Routine[]>("/routines"),
  routineChores: (routineId: string) => call<RoutineChore[]>(`/routines/${encodeURIComponent(routineId)}/chores`),
  routineAssignments: (routineId: string) =>
    call<RoutineAssignment[]>(`/routines/${encodeURIComponent(routineId)}/assignments`),
  addChore: (routineId: string, name: string, icon: string | null) =>
    call<RoutineChore>(`/routines/${encodeURIComponent(routineId)}/chores`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(icon === null ? { name } : { name, icon }),
    }),
  removeChore: (choreId: string) => call<void>(`/chores/${encodeURIComponent(choreId)}`, { method: "DELETE" }),
  createMember: (displayName: string, role: "parent" | "child") =>
    call<PlannerMember>("/members", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ displayName, role }),
    }),
  archiveMember: (id: string) =>
    call<PlannerMember>(`/members/${encodeURIComponent(id)}/archive`, { method: "POST" }),
  restoreMember: (id: string) =>
    call<PlannerMember>(`/members/${encodeURIComponent(id)}/restore`, { method: "POST" }),
  createReminder: (body: NewReminder) =>
    call<Reminder>("/reminders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: "scheduled", contentType: "text", ...body }),
    }),
  setReminderActive: (id: string, active: boolean) =>
    call<Reminder>(`/reminders/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active }),
    }),
  deleteReminder: (id: string) => call<void>(`/reminders/${encodeURIComponent(id)}`, { method: "DELETE" }),
  recipes: () => call<Recipe[]>("/recipes"),
  createRecipe: (body: { name: string; ingredients: string[]; instructions: string; slots: string[] }) =>
    call<Recipe>("/recipes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  recipeDependents: (id: string) =>
    call<{ recurringCount: number; oneOffCount: number }>(`/recipes/${encodeURIComponent(id)}/dependents`),
  deleteRecipe: (id: string) => call<void>(`/recipes/${encodeURIComponent(id)}`, { method: "DELETE" }),
  mealPlans: () => call<MealPlan[]>("/meal-plans"),
  createMealPlan: (name: string) =>
    call<MealPlan>("/meal-plans", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),
  setMealPlanActive: (id: string, active: boolean) =>
    call<MealPlan>(`/meal-plans/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active }),
    }),
  dailyMessages: (memberId: string, from: string, days: number) =>
    call<DailyMessage[]>(`/daily-messages?${q({ memberId, from, days: String(days) })}`),
  setDailyMessage: (memberId: string, date: string, text: string) =>
    call<DailyMessage>("/daily-messages", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ memberId, date, text }),
    }),
  deleteDailyMessage: (memberId: string, date: string) =>
    call<void>(`/daily-messages?${q({ memberId, date })}`, { method: "DELETE" }),
  dayPeriods: () => call<DayPeriod[]>("/day-periods"),
  setDayPeriodStart: (id: string, start: string) =>
    call<DayPeriod>(`/day-periods/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ start }),
    }),
  weekMenu: (date: string) => call<Record<string, Record<string, MenuEntry[]>>>(`/menu/week?${q({ date })}`),
  addRecurringMeal: (mealPlanId: string, weekday: string, slot: string, recipeId: string) =>
    call<{ id: string }>("/meal-entries", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: "recurring", mealPlanId, weekday, slot, recipeId }),
    }),
  timeAnnouncements: () => call<TimeRule[]>("/time-announcements"),
  addTimeAnnouncement: (time: string, weekDays: string[]) =>
    call<TimeRule>("/time-announcements", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ time, weekDays, isActive: true }),
    }),
  setTimeAnnouncementActive: (id: string, isActive: boolean) =>
    call<TimeRule>(`/time-announcements/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ isActive }),
    }),
  deleteTimeAnnouncement: (id: string) =>
    call<void>(`/time-announcements/${encodeURIComponent(id)}`, { method: "DELETE" }),
  briefingSettings: () => call<BriefingSettings>("/daily-briefing/settings"),
  setBriefingBlock: (memberId: string, blockType: string, enabled: boolean) =>
    call<unknown>(`/daily-briefing/block-settings/${encodeURIComponent(memberId)}/${encodeURIComponent(blockType)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    }),
  briefingOptIns: () => call<{ memberId: string; enabled: boolean }[]>("/daily-briefing/opt-in"),
  setBriefingOptIn: (memberId: string, enabled: boolean) =>
    call<unknown>(`/daily-briefing/opt-in/${encodeURIComponent(memberId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    }),
  briefing: (memberId: string, date: string) =>
    call<BriefingRead>(`/daily-briefing/${encodeURIComponent(memberId)}/${date}`),
  generateBriefing: (memberId: string, date: string) =>
    call<Briefing>("/daily-briefing/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ memberId, date }),
    }),
};

export interface Recipe {
  id: string;
  name: string;
  ingredients: string[];
  instructions: string;
  slots: string[];
}

export interface DailyMessage {
  id: string;
  memberId: string;
  date: string;
  text: string;
}

export interface DayPeriod {
  id: string;
  labelKey: string;
  start: string;
  sortOrder: number;
}

export interface MealPlan {
  id: string;
  name: string;
  active: boolean;
}

export interface GroundDay {
  date: string;
  chores_done: number | null;
  chores_total: number | null;
  streak: number | null;
  events: number;
  leisure_events: number;
  leisure_hours: number;
  messages: number;
}

export interface GroundMember {
  member_id: string;
  name: string;
  receives_sheet: boolean;
  pastimes: string[];
  reminders: number;
  days: GroundDay[];
}

export interface GroundSummary {
  from: string;
  until_day: string;
  cut: string;
  leisure_rule: string;
  members: GroundMember[];
}

/** El resumen que ve Tierra, hasta su corte del retardo (`backend/app/planner_ground.py`). */
export async function groundSummary(until: string | undefined, days = 7): Promise<GroundSummary> {
  const params = new URLSearchParams({ days: String(days) });
  if (until !== undefined) params.set("until", until);
  const response = await fetch(`/api/planner/ground-summary?${params.toString()}`);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // cuerpo no JSON
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as GroundSummary;
}

/** La URL de la imagen de la hoja (la que Marplanner manda a la impresora térmica). */
export function briefingPreviewUrl(memberId: string, date: string, version: string): string {
  return `${BASE}/daily-briefing/${encodeURIComponent(memberId)}/${date}/preview.png?v=${encodeURIComponent(version)}`;
}

export interface BriefingSettings {
  generationTime: string;
  blockOrder: { type: string }[];
  memberBlockSettings: { memberId: string; blockType: string; enabled: boolean }[];
}

export interface BriefingBlock {
  type: string;
  status: string;
  index: number;
  title: string;
}

export interface Briefing {
  id: string;
  memberId: string;
  date: string;
  status: string;
  payload: { blocks: BriefingBlock[] };
}

export interface BriefingRead {
  generated: boolean;
  briefing?: Briefing;
}

/** Un recordatorio programado nuevo: para todos unos días, o para miembros concretos. */
export type NewReminder =
  | { targetingMode: "apply_to_all"; text: string; weekdays: string[] }
  | { targetingMode: "specific"; text: string; assignments: { memberId: string; weekdays: string[] }[] };

export interface Routine {
  id: string;
  name: string;
  dayPeriodId: string;
  active: boolean;
}

export interface RoutineChore {
  id: string;
  routineId: string;
  name: string;
  icon: string | null;
  sortOrder: number;
  active: boolean;
}

export interface RoutineAssignment {
  memberId: string;
  weekdays: string[];
  active: boolean;
}
