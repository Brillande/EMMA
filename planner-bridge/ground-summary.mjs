// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * El resumen del planificador que ve Tierra: lo que pasaba a bordo hasta el corte del retardo.
 *
 * Por qué existe: decisión del usuario (2026-11-12): en Tierra no se ve el planificador entero,
 * sino «cuánto juegan y demás que les pueda servir para su salud mental»: ocio en el calendario,
 * tareas y rachas, pasatiempos de la hoja diaria, y cuántos mensajes y recordatorios tiene cada
 * uno. Solo cifras descriptivas por miembro y día; nada de juicio clínico (invariante 7).
 *
 * Cómo: el backend de EMMA pasa por la entrada estándar los registros del ledger anotados HASTA el
 * corte. Aquí se reconstruye con ellos la base de Marplanner en memoria, de solo lectura (modo
 * `snapshot:` del puente), y se calcula con las propias funciones de Marplanner (su tablero, sus
 * rachas, su calendario), no con una copia de su lógica. Sale JSON por la salida estándar.
 *
 * Entrada:  {"records": ["<b64>", ...], "until_day": "AAAA-MM-DD", "days": 7,
 *            "leisure_words": ["ocio", ...]}
 * Uso:      node --import <register.mjs> --import tsx planner-bridge/ground-summary.mjs  (cwd: marplanner/)
 *           o, compilado: EMMA_PLANNER_SUMMARY_BUNDLE=<summary-modules.js> node --import <register.mjs> …
 */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const PASTIMES = [
  "dadJoke", "wordOfDay", "phonics", "animalFact", "numberFact", "trivia", "riddle",
  "wouldYouRather", "wordSearch", "drawingPrompt",
];
// Los que vienen activos cuando nadie los tocó (`defaultEnabled`, src/shared/dailyBriefingBlocks.ts).
const PASTIME_DEFAULT_OFF = new Set(["phonics"]);

function addDays(iso, days) {
  const at = new Date(`${iso}T12:00:00Z`);
  at.setUTCDate(at.getUTCDate() + days);
  return at.toISOString().slice(0, 10);
}

function hoursOf(event) {
  if (event.allDay || !event.occurrenceEnd) return 0;
  const ms = Date.parse(event.occurrenceEnd) - Date.parse(event.occurrenceStart);
  return Number.isFinite(ms) && ms > 0 ? ms / 3_600_000 : 0;
}

function isLeisure(event, words) {
  const text = `${event.title ?? ""} ${event.decoratedTitle ?? ""}`.toLowerCase();
  return words.some((word) => word !== "" && text.includes(word.toLowerCase()));
}

async function readInput() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

/**
 * El resumen de un corte. Cambia `process.env` y deja módulos de Marplanner cargados con la base de
 * ESE corte: cada llamada va en un proceso o en un hilo nuevo (`summary-worker.mjs`), nunca dos en
 * el mismo.
 */
export async function runSummary(input) {
  const days = Math.max(1, Math.min(31, Number(input.days ?? 7)));
  const untilDay = String(input.until_day);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(untilDay)) throw new Error("until_day no es AAAA-MM-DD");
  const leisureWords = Array.isArray(input.leisure_words) ? input.leisure_words.map(String) : [];
  const from0 = addDays(untilDay, -(days - 1));
  if (!Array.isArray(input.records) || input.records.length === 0) {
    // Nada anotado antes del corte: a Tierra aún no ha llegado nada del planificador. Sin
    // registros no hay ni esquema que reconstruir; se dice vacío, no se falla.
    return { from: from0, until_day: untilDay, records: 0, members: [] };
  }

  // La base del corte, en memoria y de solo lectura, en una carpeta temporal que se borra al final.
  globalThis.__EMMA_PLANNER_SNAPSHOT = input.records ?? [];
  process.env.EMMA_PLANNER_LEDGER = "snapshot:";
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "emma-planner-cut-"));
  process.env.DATA_DIR = dir;
  process.env.DATABASE_PATH = "marplanner.db";
  try {
    // En el instalador, un solo fichero compilado (`build-marplanner.mjs`); en el repositorio, el
    // código de la copia, con tsx.
    let mods;
    if (process.env.EMMA_PLANNER_SUMMARY_BUNDLE) {
      mods = await import(pathToFileURL(process.env.EMMA_PLANNER_SUMMARY_BUNDLE).href);
    } else {
      const root = pathToFileURL(path.resolve("src/server/modules")).href;
      const load = (rel) => import(`${root}/${rel}`);
      mods = {
        members: await load("members/index.ts"),
        routines: await load("routines/index.ts"),
        calendar: await load("calendar/index.ts"),
        messages: await load("daily-messages/index.ts"),
        reminders: await load("reminders/index.ts"),
        briefing: await load("daily-briefing/index.ts"),
        briefingSettings: await load("daily-briefing/settings.ts"),
      };
    }
    const { members, routines, calendar, messages, reminders, briefing, briefingSettings } = mods;

    const from = addDays(untilDay, -(days - 1));
    const dates = Array.from({ length: days }, (_, i) => addDays(from, i));
    let people;
    try {
      people = members.listMembers();
    } catch (err) {
      // Los primeros asientos de Marplanner son su tabla de migraciones, antes de la migración
      // base: hasta que esta llega al corte no hay miembros que leer. No ha llegado nada todavía.
      if (/no such table/i.test(String(err?.message))) {
        return { from: addDays(untilDay, -(days - 1)), until_day: untilDay, records: input.records.length, members: [] };
      }
      throw err;
    }

    const boards = new Map(dates.map((date) => [date, routines.getBoard(date)]));
    const events = calendar.getEvents({ source: "local", range: { from, to: untilDay } });
    const allReminders = reminders.listReminders();
    const optIns = new Map(briefing.listOptIns().map((o) => [o.memberId, o.enabled]));
    const settings = briefingSettings.readAllSettings();
    const own = (memberId, type) =>
      settings.memberBlockSettings.find((s) => s.memberId === memberId && s.blockType === type)?.enabled;

    const result = people.map((member) => {
      const memberMessages = messages.listMessages(member.id, from, days);
      const perDay = dates.map((date) => {
        const column = boards.get(date).find((c) => c.memberId === member.id);
        const dayEvents = events.filter(
          (e) => e.assignedTo.includes(member.id) && e.occurrenceStart.slice(0, 10) === date,
        );
        const leisure = dayEvents.filter((e) => isLeisure(e, leisureWords));
        return {
          date,
          chores_done: column?.todayProgress?.completed ?? null,
          chores_total: column?.todayProgress?.total ?? null,
          streak: column?.streak ?? null,
          events: dayEvents.length,
          leisure_events: leisure.length,
          leisure_hours: Math.round(leisure.reduce((h, e) => h + hoursOf(e), 0) * 10) / 10,
          messages: memberMessages.filter((m) => m.date === date).length,
        };
      });
      const activeReminders = allReminders.filter(
        (r) =>
          r.active &&
          (r.targetingMode === "apply_to_all" ||
            (r.assignments ?? []).some((a) => a.active && a.memberId === member.id)),
      );
      const receivesSheet = optIns.get(member.id) === true;
      return {
        member_id: member.id,
        name: member.displayName,
        receives_sheet: receivesSheet,
        pastimes: receivesSheet
          ? PASTIMES.filter((type) => own(member.id, type) ?? !PASTIME_DEFAULT_OFF.has(type))
          : [],
        reminders: activeReminders.length,
        days: perDay,
      };
    });
    return { from, until_day: untilDay, records: input.records?.length ?? 0, members: result };
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

// Como programa (`node … ground-summary.mjs` con la entrada por stdin): en el repositorio.
// (En Windows la letra de unidad puede venir en mayúscula o minúscula: se compara sin distinguir.)
const invoked = process.argv[1] ? path.resolve(process.argv[1]).toLowerCase() : "";
if (invoked === path.resolve(fileURLToPath(import.meta.url)).toLowerCase()) {
  readInput()
    .then(runSummary)
    .then((result) => process.stdout.write(JSON.stringify(result)))
    .catch((err) => {
      process.stderr.write(`${err?.stack ?? err}
`);
      process.exit(1);
    });
}
