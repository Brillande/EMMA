import { MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { formatNumber, formatUtc } from "../lib/format";
import { EMPTY_MARK, MISSING_MARK } from "../lib/marks";
import { blockLabel } from "./BriefingPanel";
import { State, useLoad } from "./PlannerPanels";
import { type GroundDay, groundSummary } from "./plannerApi";
import { tr } from "../lib/i18n";

/**
 * Lo que Tierra ve del planificador de a bordo (Marplanner): un resumen por persona y día, hasta
 * su corte del retardo.
 *
 * Por qué así: decisión del usuario (2026-11-12): «en Tierra ven datos de cuánto juegan y demás
 * que les pueda servir para su salud mental», no el planificador entero. Son cifras descriptivas
 * del backend (`app/planner_ground.py`): ocio en el calendario, tareas y rachas, pasatiempos de la
 * hoja diaria, cuántos mensajes y recordatorios. Sin color de aviso, sin umbral y sin veredicto
 * (invariante 7): quien interpreta es la persona de Tierra. Qué cuenta como ocio lo dice el
 * backend con sus palabras, y se enseña tal cual.
 */

function cell(value: number | null, decimals = 0) {
  return value === null ? <span className="secondary">{tr("sin dato", "no data")}</span> : <span className="num">{formatNumber(value, decimals)}</span>;
}

function chores(day: GroundDay) {
  if (day.chores_done === null || day.chores_total === null) return <span className="secondary">{tr("sin dato", "no data")}</span>;
  return (
    <>
      <span className="num">{formatNumber(day.chores_done)}</span> {tr("de", "of")} <span className="num">{formatNumber(day.chores_total)}</span>
    </>
  );
}

/** Cada cuánto se rehace el corte: el resumen se reconstruye entero, no en cada pintado. */
const CUT_STEP_MS = 5 * 60 * 1000;

/**
 * El corte del planificador: la hora REAL menos el retardo de ida. No el de la consola de Tierra,
 * que sale del reloj de la misión (en simulación, semanas por delante del calendario): Marplanner
 * vive en las fechas reales de la casa, y con el corte de la misión Tierra veía días que aún no
 * habían pasado (visto el 2026-11-12). Redondeado hacia atrás a `CUT_STEP_MS`.
 */
export function plannerCut(oneWayMinutes: number | null, now: number): Date | null {
  if (oneWayMinutes === null) return null;
  const cut = now - oneWayMinutes * 60_000;
  return new Date(cut - (cut % CUT_STEP_MS));
}

export function GroundPlannerPanel({ oneWayMinutes }: { oneWayMinutes: number | null }) {
  const until = plannerCut(oneWayMinutes, Date.now());
  const iso = until === null ? undefined : until.toISOString();
  const summary = useLoad(() => groundSummary(iso), `ground-planner|${iso ?? "ahora"}`);
  return (
    <section data-ui="ground-planner" className="panel" aria-label={tr("Planificador de a bordo", "On-board planner")}>
      <PanelTitle concept="nextDays">{tr("Planificador de a bordo", "On-board planner")}</PanelTitle>
      {until === null ? (
        <p className="secondary">
          <MarkOf mark={MISSING_MARK}>
            {tr(
              "Sin corte del retardo: se muestra todo lo anotado a bordo.",
              "No delay cut: everything noted on board is shown.",
            )}
          </MarkOf>
        </p>
      ) : (
        <p className="secondary">
          {tr("Lo anotado a bordo hasta", "What was noted on board up to")}{" "}
          <span className="num">{formatUtc(until)}</span>
          {tr("; lo posterior está en camino.", "; anything later is on its way.")}
        </p>
      )}
      <State loaded={summary} reading={tr("Reconstruyendo el planificador hasta el corte…", "Rebuilding the planner up to the cut…")} />
      {summary.data !== null && (
        <>
          <p className="secondary">{summary.data.leisure_rule}</p>
          {summary.data.members.length === 0 && (
            <p className="secondary">
              <MarkOf mark={EMPTY_MARK}>
                {tr("Aún no ha llegado nada del planificador.", "Nothing from the planner has arrived yet.")}
              </MarkOf>
            </p>
          )}
          {summary.data.members.map((member) => (
            <div key={member.member_id} className="planner-day">
              <h3>
                {member.name}{" "}
                <span className="secondary">
                  · <span className="num">{formatNumber(member.reminders)}</span>{" "}
                  {tr("recordatorios activos", "active reminders")} ·{" "}
                  {member.receives_sheet
                    ? member.pastimes.length === 0
                      ? tr("hoja diaria sin pasatiempos", "daily sheet without pastimes")
                      : `${tr("pasatiempos de su hoja:", "pastimes on their sheet:")} ${member.pastimes.map(blockLabel).join(", ")}`
                    : tr("no recibe hoja diaria", "does not receive a daily sheet")}
                </span>
              </h3>
              <div className="planner-table-wrap">
                <table className="planner-table">
                  <thead>
                    <tr>
                      <th scope="col">{tr("Día", "Day")}</th>
                      <th scope="col">{tr("Tareas hechas", "Chores done")}</th>
                      <th scope="col">{tr("Racha (días)", "Streak (days)")}</th>
                      <th scope="col">{tr("Eventos", "Events")}</th>
                      <th scope="col">{tr("De ocio", "Leisure")}</th>
                      <th scope="col">{tr("Horas de ocio", "Leisure hours")}</th>
                      <th scope="col">{tr("Mensajes", "Messages")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {member.days.map((day) => (
                      <tr key={day.date}>
                        <th scope="row">
                          <span className="num">{day.date}</span>
                        </th>
                        <td>{chores(day)}</td>
                        <td>{cell(day.streak)}</td>
                        <td>{cell(day.events)}</td>
                        <td>{cell(day.leisure_events)}</td>
                        <td>{cell(day.leisure_hours, 1)}</td>
                        <td>{cell(day.messages)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </>
      )}
    </section>
  );
}
