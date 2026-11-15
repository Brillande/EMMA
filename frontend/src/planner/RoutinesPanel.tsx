import { useState } from "react";

import { Command } from "../components/Command";
import { Fold } from "../components/Fold";
import { MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { EMPTY_MARK } from "../lib/marks";
import { dayPeriodLabel } from "./labels";
import { State, memberName, useLoad, useWrite, weekdays } from "./PlannerPanels";
import { type Routine, type RoutineAssignment, type RoutineChore, plannerApi } from "./plannerApi";

/**
 * Las rutinas del planificador (Marplanner) y sus tareas: qué hay que hacer en cada franja del día,
 * de quién es y qué días; desde aquí se añade o se quita una tarea de una rutina.
 *
 * Por qué existe: el tablero de «Tareas del día» enseña lo de hoy, pero las tareas viven en las
 * rutinas de Marplanner (su administración). Esto es esa administración, con el estilo de EMMA y
 * sin colores de miembro (ver `PlannerPanels.tsx`). Quitar una tarea es el borrado blando de
 * Marplanner: sus marcas de días pasados se conservan (y su asiento en el ledger también).
 */

interface RoutineView {
  routine: Routine;
  chores: RoutineChore[];
  assignments: RoutineAssignment[];
}

async function loadRoutines(): Promise<RoutineView[]> {
  const routines = (await plannerApi.routines()).filter((r) => r.active);
  return Promise.all(
    routines.map(async (routine) => {
      const [chores, assignments] = await Promise.all([
        plannerApi.routineChores(routine.id),
        plannerApi.routineAssignments(routine.id),
      ]);
      return {
        routine,
        chores: chores.filter((c) => c.active).sort((a, b) => a.sortOrder - b.sortOrder),
        assignments: assignments.filter((a) => a.active),
      };
    }),
  );
}

export function PlannerRoutinesPanel() {
  const routines = useLoad(loadRoutines, "routines");
  const members = useLoad(() => plannerApi.members(), "members");
  const write = useWrite(routines.reload);
  const [target, setTarget] = useState("");
  const [name, setName] = useState("");
  const [icon, setIcon] = useState("");
  const names = new Map((members.data ?? []).map((m) => [m.id, m.displayName]));
  const chosen = target !== "" ? target : (routines.data?.[0]?.routine.id ?? "");

  return (
    <section data-ui="planner-routines" className="panel" aria-label="Rutinas de la casa">
      <PanelTitle concept="routines">Rutinas de la casa</PanelTitle>
      <State loaded={routines} reading="Leyendo las rutinas…" />
      {write.notice}
      {routines.data !== null && routines.data.length === 0 && (
        <p className="secondary">
          <MarkOf mark={EMPTY_MARK}>No hay rutinas activas.</MarkOf>
        </p>
      )}
      <div className="planner-board">
        {routines.data?.map(({ routine, chores, assignments }) => (
          <div key={routine.id} className="planner-column">
            <h3>
              {routine.name}{" "}
              <span className="secondary">· {dayPeriodLabel(`dayPeriod.${routine.dayPeriodId}`)}</span>
            </h3>
            <p className="secondary">
              {assignments.length === 0
                ? "sin asignar"
                : assignments.map((a) => `${memberName(names, members.data !== null, a.memberId)} (${weekdays(a.weekdays)})`).join(", ")}
            </p>
            <ul className="planner-list">
              {chores.map((chore) => (
                <li key={chore.id} className="planner-row">
                  <span>
                    {chore.icon !== null && <span aria-hidden="true">{chore.icon} </span>}
                    {chore.name}
                  </span>
                  <Command
                    pictogram="cross"
                    disabled={write.busy}
                    aria-label={`Quitar la tarea ${chore.name}`}
                    onClick={() => void write.run(() => plannerApi.removeChore(chore.id))}
                  >
                    Quitar
                  </Command>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      {routines.data !== null && routines.data.length > 0 && (
        <Fold data-ui="planner-routines-add" concept="declare" label="Añadir una tarea a una rutina">
          <div className="inline-form">
            <select value={chosen} aria-label="Rutina" onChange={(e) => setTarget(e.target.value)}>
              {routines.data.map(({ routine }) => (
                <option key={routine.id} value={routine.id}>
                  {routine.name}
                </option>
              ))}
            </select>
            <input
              value={name}
              maxLength={120}
              placeholder="tarea"
              aria-label="Nombre de la tarea"
              onChange={(e) => setName(e.target.value)}
            />
            <input
              value={icon}
              maxLength={8}
              placeholder="emoji (opcional)"
              aria-label="Emoji de la tarea (opcional)"
              onChange={(e) => setIcon(e.target.value)}
            />
            <Command
              concept="register"
              disabled={write.busy || name.trim() === "" || chosen === ""}
              onClick={() =>
                void write.run(async () => {
                  await plannerApi.addChore(chosen, name.trim(), icon.trim() === "" ? null : icon.trim());
                  setName("");
                  setIcon("");
                })
              }
            >
              Añadir
            </Command>
          </div>
        </Fold>
      )}
    </section>
  );
}
