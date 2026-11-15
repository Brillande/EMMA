import { useState } from "react";

import { Command } from "../components/Command";
import { Fold } from "../components/Fold";
import { MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { useVoiceAvailability } from "../components/ReadAloud";
import { EMPTY_MARK, OK_MARK, UNAVAILABLE_MARK } from "../lib/marks";
import { UNAVAILABLE_TEXT } from "../lib/speech";
import { State, useLoad, useWrite, weekdays } from "./PlannerPanels";
import { plannerApi } from "./plannerApi";
import { timePhrase } from "./timePhrase";

/**
 * Los avisos de hora del planificador: a qué horas y qué días la consola dice la hora en voz alta
 * («Son las siete y cuarto»). Quien habla es `TimeAnnouncer.tsx`, con la voz local de la consola;
 * si el equipo no tiene voz local, aquí se dice con la marca gris de «no disponible».
 */

const WEEK = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;
const TIME = /^([01]\d|2[0-3]):[0-5]\d$/;

export function PlannerAnnouncementsPanel() {
  const rules = useLoad(() => plannerApi.timeAnnouncements(), "time-announcements");
  const write = useWrite(rules.reload);
  const voice = useVoiceAvailability();
  const [time, setTime] = useState("07:00");
  const [days, setDays] = useState<string[]>(["mon", "tue", "wed", "thu", "fri"]);
  const toggleDay = (day: string) =>
    setDays(days.includes(day) ? days.filter((d) => d !== day) : WEEK.filter((d) => d === day || days.includes(d)));
  const list = [...(rules.data ?? [])].sort((a, b) => a.time.localeCompare(b.time));

  return (
    <section data-ui="planner-announcements" className="panel" aria-label="Avisos de hora">
      <PanelTitle concept="pvt">Avisos de hora</PanelTitle>
      {voice !== "ready" && (
        <p>
          <MarkOf mark={UNAVAILABLE_MARK}>{UNAVAILABLE_TEXT[voice]}: los avisos de hora no se dirán.</MarkOf>
        </p>
      )}
      <State loaded={rules} reading="Leyendo los avisos…" />
      {write.notice}
      {rules.data !== null && list.length === 0 && (
        <p className="secondary">
          <MarkOf mark={EMPTY_MARK}>No hay avisos de hora.</MarkOf>
        </p>
      )}
      <ul className="planner-list">
        {list.map((rule) => {
          const [hour, minute] = rule.time.split(":").map(Number);
          return (
            <li key={rule.id} className="planner-row">
              <span>
                <MarkOf mark={rule.isActive ? OK_MARK : EMPTY_MARK}>
                  <span className="num">{rule.time}</span>
                </MarkOf>{" "}
                <span className="secondary">
                  · «{timePhrase(hour!, minute!)}» · {weekdays(rule.weekDays)}
                  {!rule.isActive && " · en pausa"}
                </span>
              </span>
              <span>
                <Command
                  pictogram={rule.isActive ? "ring-dotted" : "check"}
                  disabled={write.busy}
                  onClick={() => void write.run(() => plannerApi.setTimeAnnouncementActive(rule.id, !rule.isActive))}
                >
                  {rule.isActive ? "Pausar" : "Reanudar"}
                </Command>{" "}
                <Command
                  pictogram="cross"
                  disabled={write.busy}
                  aria-label={`Borrar el aviso de las ${rule.time}`}
                  onClick={() => void write.run(() => plannerApi.deleteTimeAnnouncement(rule.id))}
                >
                  Borrar
                </Command>
              </span>
            </li>
          );
        })}
      </ul>
      <Fold data-ui="planner-announcements-add" concept="declare" label="Añadir un aviso de hora">
        <div className="inline-form">
          <input type="time" value={time} aria-label="Hora del aviso" onChange={(e) => setTime(e.target.value)} />
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
            disabled={write.busy || !TIME.test(time) || days.length === 0}
            onClick={() => void write.run(() => plannerApi.addTimeAnnouncement(time, days))}
          >
            Añadir
          </Command>
        </div>
      </Fold>
    </section>
  );
}
